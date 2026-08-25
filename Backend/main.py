from __future__ import annotations

import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from auth_utils import create_access_token, decode_token, generate_otp, hash_password, otp_matches, verify_password
from config import DEBUG_RETURN_OTP, FRONTEND_ORIGIN, HOTEL_ID, OTP_RESEND_SECONDS, OTP_TTL_SECONDS
from db import DatabaseUnavailable, close_db, get_db
from email_service import email_configured, mailjet_configured, resend_configured, send_otp_email, smtp_configured
from forecast_engine import generate_forecast, latest_forecast
from ingest import ensure_skeleton, normalize_rows, replace_hotel_history
import chat as assistant
import queries as Q


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(default="", max_length=80)


class OtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)


class EmailRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForecastRequest(BaseModel):
    months: int = Field(default=6, ge=3, le=12)


class UploadRequest(BaseModel):
    rows: list[dict[str, Any]]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class ClientRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    city: str = Field(default="", max_length=80)
    rooms: int = Field(default=0, ge=0, le=5000)


class QueryRequest(BaseModel):
    query: str = ""
    months: int = Field(default=6, ge=3, le=12)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _display_name(email: str) -> str:
    local = email.split("@")[0].replace(".", " ").replace("_", " ")
    return local.title() or "Admin"


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        get_db().verify()
        print("Connected to CognoDB.")
    except DatabaseUnavailable as exc:
        print(f"Warning: CognoDB is not reachable at startup: {exc}")
    yield
    close_db()


app = FastAPI(title="Hotel Budget Forecasting", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseUnavailable)
async def db_unavailable_handler(_: Request, exc: DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def db_or_503():
    try:
        db = get_db()
        return db
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.")
    db = db_or_503()
    users = db.run(Q.GET_USER, email=payload["sub"])
    if not users:
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.")
    return {"email": users[0]["email"], "name": users[0].get("name") or payload.get("name") or "Admin"}


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return (text[:40] or "client")


def _list_or_bootstrap_hotels(db, email: str, name: str) -> list[dict[str, Any]]:
    hotels = db.run(Q.LIST_USER_HOTELS, email=email)
    if hotels:
        return hotels
    existing = db.run(Q.GET_HOTEL, hotel_id=HOTEL_ID)
    if existing:
        db.run_write(Q.LINK_USER_HOTEL, email=email, hotel_id=HOTEL_ID)
    else:
        hotel_id = f"{_slug(name)}-{secrets.token_hex(3)}"
        db.run_write(
            Q.CREATE_USER_HOTEL,
            email=email,
            hotel_id=hotel_id,
            name=(name or "My property").strip() or "My property",
            rooms=0,
            city_id="unspecified",
            city_name="Unspecified",
        )
        ensure_skeleton(db, hotel_id)
    return db.run(Q.LIST_USER_HOTELS, email=email)


def resolve_hotel_id(
    user: dict = Depends(current_user),
    x_hotel_id: Optional[str] = Header(default=None, alias="X-Hotel-Id"),
) -> str:
    db = db_or_503()
    hotels = _list_or_bootstrap_hotels(db, user["email"], user["name"])
    if not hotels:
        raise HTTPException(status_code=400, detail="No workspace is available yet.")
    if x_hotel_id and any(item["id"] == x_hotel_id for item in hotels):
        return x_hotel_id
    return hotels[0]["id"]


def _issue_otp(db, email: str, purpose: str = "signup") -> tuple[str, bool]:
    code = generate_otp()
    expires = (_now() + timedelta(seconds=OTP_TTL_SECONDS)).timestamp()
    db.run_write(
        Q.REPLACE_OTP,
        email=email.lower(),
        code=hash_password(code),
        expires_at=expires,
        purpose=purpose,
        created_at=_now().isoformat(),
    )
    try:
        delivered = send_otp_email(email, code)
    except Exception as exc:
        print(f"[OTP] Failed to send email to {email}: {exc}")
        if email_configured():
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        delivered = False
    return code, delivered


def _pct(new: float, old: float) -> float:
    if not old:
        return 0.0
    return round(((new - old) / old) * 100, 1)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    try:
        get_db().verify()
        provider = "mailjet" if mailjet_configured() else "resend" if resend_configured() else "smtp" if smtp_configured() else "none"
        return {"status": "ok", "database": "connected", "email": provider, "smtp": smtp_configured()}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/api/auth/signup")
@app.post("/api/auth/register")
@app.post("/auth/register")
def signup(body: SignupRequest):
    db = db_or_503()
    email = body.email.lower()
    try:
        existing = db.run(Q.GET_USER, email=email)
        if existing and existing[0]["verified"]:
            raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.")
        name = (body.name or "").strip() or _display_name(email)
        hashed = hash_password(body.password)
        if existing:
            db.run_write(Q.UPDATE_UNVERIFIED_USER, email=email, password_hash=hashed, name=name)
        else:
            db.run_write(
                Q.CREATE_USER,
                email=email,
                password_hash=hashed,
                name=name,
                created_at=_now().isoformat(),
            )
        code, delivered = _issue_otp(db, email, "signup")
        payload: dict[str, Any] = {
            "status": "otp_sent",
            "email": email,
            "name": name,
            "email_sent": delivered,
            "message": "We sent a 6-digit OTP to your email." if delivered else "We generated a 6-digit OTP.",
            "resend_after": OTP_RESEND_SECONDS,
        }
        if DEBUG_RETURN_OTP and not delivered:
            payload["dev_otp"] = code
        return payload
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/auth/verify-otp")
@app.post("/api/auth/verify-email")
@app.post("/auth/verify-email")
def verify_otp(body: OtpRequest):
    db = db_or_503()
    email = body.email.lower()
    try:
        rows = db.run(Q.GET_OTP, email=email, purpose="signup")
        if not rows:
            raise HTTPException(status_code=400, detail="No OTP found. Please request a new code.")
        row = rows[0]
        if float(row["expires_at"]) < _now().timestamp():
            raise HTTPException(status_code=400, detail="This OTP has expired. Please request a new code.")
        if not otp_matches(str(row["code"]), body.otp):
            raise HTTPException(status_code=400, detail="The OTP you entered is incorrect.")
        db.run_write(Q.SET_USER_VERIFIED, email=email)
        return {"status": "verified", "message": "Email verified. You can sign in now."}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/auth/resend-otp")
def resend_otp(body: EmailRequest):
    db = db_or_503()
    email = body.email.lower()
    try:
        users = db.run(Q.GET_USER, email=email)
        if not users:
            raise HTTPException(status_code=404, detail="No account found for this email.")
        if users[0]["verified"]:
            raise HTTPException(status_code=400, detail="This account is already verified. Please sign in.")
        code, delivered = _issue_otp(db, email, "signup")
        payload: dict[str, Any] = {
            "status": "otp_sent",
            "email_sent": delivered,
            "resend_after": OTP_RESEND_SECONDS,
        }
        if DEBUG_RETURN_OTP and not delivered:
            payload["dev_otp"] = code
        return payload
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/auth/login")
@app.post("/auth/login")
def login(body: LoginRequest):
    db = db_or_503()
    email = body.email.lower()
    try:
        users = db.run(Q.GET_USER, email=email)
        if not users:
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        user = users[0]
        if not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        if not user["verified"]:
            raise HTTPException(status_code=403, detail="Please verify the OTP sent to your email before signing in.")
        token = create_access_token(user["email"], user["name"] or "Admin")
        return {"access_token": token, "token_type": "bearer", "name": user["name"], "email": user["email"]}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user), hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        hotels = db.run(Q.LIST_USER_HOTELS, email=user["email"])
        hotel = db.run(Q.GET_HOTEL, hotel_id=hotel_id)
        return {
            "email": user["email"],
            "name": user["name"],
            "hotel": hotel[0] if hotel else None,
            "hotel_id": hotel_id,
            "hotels": hotels,
        }
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.patch("/api/auth/profile")
def update_profile(body: ProfileRequest, user: dict = Depends(current_user)):
    db = db_or_503()
    name = body.name.strip()
    try:
        rows = db.run_write(Q.UPDATE_USER_NAME, email=user["email"], name=name)
        if not rows:
            raise HTTPException(status_code=404, detail="Account not found.")
        return {"email": user["email"], "name": name}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Dashboard / historical / forecast
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        months = db.run(Q.HOTEL_MONTHS, hotel_id=hotel_id, start_id=None, end_id=None)
        if not months:
            return {"kpis": None, "trend": [], "breakdown": [], "empty": True}
        window = months[-6:] if len(months) >= 6 else months
        prior = months[-12:-6] if len(months) >= 12 else (months[:-len(window)] or window)
        def _sum(items, key):
            return sum(float(item.get(key) or 0) for item in items)
        def _avg(items, key):
            return _sum(items, key) / max(1, len(items))
        latest = months[-1]
        breakdown = db.run(Q.EXPENSE_BREAKDOWN, hotel_id=hotel_id, month_id=latest["id"])
        if not breakdown:
            total_exp = _sum(window, "expenses") or 1
            breakdown = [
                {"id": "payroll", "name": "Payroll", "color": "#1B365D", "amount": total_exp * 0.30},
                {"id": "marketing", "name": "Marketing", "color": "#5B4FC7", "amount": total_exp * 0.20},
                {"id": "utilities", "name": "Utilities", "color": "#7C9CBF", "amount": total_exp * 0.15},
                {"id": "maintenance", "name": "Maintenance", "color": "#A78BFA", "amount": total_exp * 0.15},
                {"id": "others", "name": "Others", "color": "#C4B5FD", "amount": total_exp * 0.20},
            ]
        total_break = sum(item["amount"] for item in breakdown) or 1
        start_label = window[0]["label"]
        end_label = window[-1]["label"]
        return {
            "empty": False,
            "as_of": end_label,
            "period": f"{start_label} – {end_label}" if start_label != end_label else end_label,
            "months_used": len(window),
            "kpis": {
                "revenue": _sum(window, "revenue"),
                "revenue_delta": _pct(_sum(window, "revenue"), _sum(prior, "revenue")),
                "expenses": _sum(window, "expenses"),
                "expenses_delta": _pct(_sum(window, "expenses"), _sum(prior, "expenses")),
                "net_profit": _sum(window, "net_profit"),
                "profit_delta": _pct(_sum(window, "net_profit"), _sum(prior, "net_profit")),
                "occupancy": round(_avg(window, "occupancy"), 1),
                "occupancy_delta": _pct(_avg(window, "occupancy"), _avg(prior, "occupancy")),
            },
            "trend": window,
            "breakdown": [
                {**item, "percent": round(item["amount"] / total_break * 100, 1)}
                for item in breakdown
            ],
        }
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/historical")
def historical(
    start: Optional[str] = None,
    end: Optional[str] = None,
    category: str = "All",
    hotel_id: str = Depends(resolve_hotel_id),
):
    db = db_or_503()
    start_id = start[:7] if start else None
    end_id = end[:7] if end else None
    try:
        rows = db.run(Q.HOTEL_MONTHS, hotel_id=hotel_id, start_id=start_id, end_id=end_id)
        categories = db.run(Q.DEPARTMENT_NAMES, hotel_id=hotel_id)
        if category and category != "All":
            extras = db.run(
                Q.FILTERED_EXPENSES,
                hotel_id=hotel_id,
                start_id=start_id,
                end_id=end_id,
                category=category,
            )
            by_id = {item["id"]: item["category_expenses"] for item in extras}
            for row in rows:
                row["expenses"] = by_id.get(row["id"], 0)
                row["net_profit"] = round((row["revenue"] or 0) - (row["expenses"] or 0), 2)
        return {
            "rows": list(reversed(rows)),
            "categories": ["All"] + [c["name"] for c in categories],
            "count": len(rows),
        }
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/historical/upload")
def upload_historical(body: UploadRequest, hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    if not body.rows:
        raise HTTPException(status_code=400, detail="The file did not contain any rows.")
    try:
        normalized = normalize_rows(body.rows)
        count = replace_hotel_history(db, normalized, hotel_id=hotel_id)
        first, last = normalized[0], normalized[-1]
        return {
            "status": "success",
            "count": count,
            "from": f"{first['year']}-{first['month']:02d}",
            "to": f"{last['year']}-{last['month']:02d}",
            "message": f"Loaded {count} months into CognoDB. Dashboard and forecasts now use this file.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/forecast")
def get_forecast(hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        data = latest_forecast(db, hotel_id=hotel_id)
        if not data:
            return {"empty": True, "rows": [], "insights": []}
        return {"empty": False, **data}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/forecast/generate")
def post_forecast(body: ForecastRequest, hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        result = generate_forecast(db, horizon=body.months, hotel_id=hotel_id)
        return {"empty": False, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/insights")
def insights(hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        cascade = db.run(Q.EVENT_COST_CASCADE, hotel_id=hotel_id, min_impact=0.5)
        drivers = db.run(Q.COST_DRIVER_ELASTICITIES, hotel_id=hotel_id)
        latest = db.run(Q.LATEST_MONTH, hotel_id=hotel_id)
        competitors = []
        if latest:
            competitors = db.run(Q.COMPETITOR_OCCUPANCY, hotel_id=hotel_id, month_id=latest[0]["id"])
        return {"event_cost_cascade": cascade, "cost_drivers": drivers, "competitors": competitors}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/settings")
def settings(user: dict = Depends(current_user), hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        hotel = db.run(Q.GET_HOTEL, hotel_id=hotel_id)
        hotels = db.run(Q.LIST_USER_HOTELS, email=user["email"])
        return {"user": user, "hotel": hotel[0] if hotel else None, "hotels": hotels, "hotel_id": hotel_id}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _demand(occupancy: float, share: float) -> str:
    score = occupancy * max(share, 0.08)
    if score >= 14:
        return "High"
    if score >= 8:
        return "Medium"
    return "Low"


@app.get("/api/rooms")
def rooms(hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        hotel_rows = db.run(Q.GET_HOTEL, hotel_id=hotel_id)
        hotel = hotel_rows[0] if hotel_rows else {"name": None, "rooms": 0}
        latest = db.run(Q.LATEST_MONTH, hotel_id=hotel_id)
        month_id = latest[0]["id"] if latest else ""
        occupancy = 0.0
        if month_id:
            months = db.run(Q.HOTEL_MONTHS, hotel_id=hotel_id, start_id=month_id, end_id=month_id)
            if months:
                occupancy = float(months[0].get("occupancy") or 0)
        rows = db.run(Q.GET_ROOMS, hotel_id=hotel_id, month_id=month_id) if month_id else []
        unique_rows: dict[str, dict[str, Any]] = {}
        for row in rows:
            name_key = (row.get("name") or row.get("id") or "").strip().lower()
            if name_key and name_key not in unique_rows:
                unique_rows[name_key] = row
        total_rooms = int(hotel.get("rooms") or 0)
        inventory = []
        for row in unique_rows.values():
            share = float(row.get("share") or 0)
            count = max(1, round(total_rooms * share)) if total_rooms and share else 0
            inventory.append({
                "id": row["id"],
                "name": row["name"],
                "base_rate": row["base_rate"],
                "rooms": count,
                "revenue": row["revenue"],
                "demand": _demand(occupancy, share) if month_id else "—",
            })
        inventory.sort(key=lambda item: (-(item["base_rate"] or 0), item["name"]))
        return {
            "empty": not bool(month_id),
            "hotel": hotel,
            "as_of": latest[0]["label"] if latest else None,
            "occupancy": occupancy,
            "rows": inventory,
        }
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/graph")
def graph(hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        hotel_rows = db.run(Q.GET_HOTEL, hotel_id=hotel_id)
        hotel = hotel_rows[0] if hotel_rows else {"name": "Hotel", "rooms": 0, "city": ""}
        months = db.run(Q.HOTEL_MONTHS, hotel_id=hotel_id, start_id=None, end_id=None)
        raw_rooms = db.run(Q.GET_ROOMS, hotel_id=hotel_id, month_id=months[-1]["id"] if months else "")
        room_count = len({(row.get("name") or row.get("id") or "").strip().lower() for row in raw_rooms if row.get("name") or row.get("id")})
        depts = db.run(Q.GRAPH_DEPARTMENTS, hotel_id=hotel_id)
        comps = db.run(Q.GRAPH_COMPETITORS, hotel_id=hotel_id)
        forecast_run = db.run(Q.GRAPH_FORECAST, hotel_id=hotel_id)
        nodes = [
            {
                "id": "hotel",
                "type": "hotel",
                "label": hotel.get("name") or "Hotel",
                "detail": f"{hotel.get('city') or 'City'} · {hotel.get('rooms') or 0} rooms",
            },
            {
                "id": "city",
                "type": "city",
                "label": hotel.get("city") or "City",
                "detail": "LOCATED_IN",
            },
            {
                "id": "history",
                "type": "history",
                "label": "Imported history",
                "detail": f"{len(months)} monthly snapshots" if months else "No file imported yet",
            },
            {
                "id": "forecast",
                "type": "forecast",
                "label": "Forecast run",
                "detail": (
                    f"{forecast_run[0]['months']} projected months"
                    if forecast_run and forecast_run[0].get("months")
                    else "Not generated"
                ),
            },
            {
                "id": "rooms",
                "type": "rooms",
                "label": "Rooms & rates",
                "detail": f"{room_count} room types",
            },
            {
                "id": "departments",
                "type": "departments",
                "label": "Departments",
                "detail": f"{len(depts)} cost centers",
            },
        ]
        edges = [
            {"from": "hotel", "to": "city", "rel": "LOCATED_IN"},
            {"from": "hotel", "to": "history", "rel": "RECORDED"},
            {"from": "hotel", "to": "forecast", "rel": "RAN_FORECAST"},
            {"from": "hotel", "to": "rooms", "rel": "OFFERS"},
            {"from": "hotel", "to": "departments", "rel": "HAS_DEPARTMENT"},
        ]
        for comp in comps:
            node_id = f"comp-{comp['id']}"
            nodes.append({
                "id": node_id,
                "type": "competitor",
                "label": comp.get("name") or "Competitor",
                "detail": f"{comp.get('rooms') or 0} rooms · COMPETES_WITH",
            })
            edges.append({"from": "hotel", "to": node_id, "rel": "COMPETES_WITH"})
        return {
            "empty": not bool(months),
            "nodes": nodes,
            "edges": edges,
            "hotel": hotel,
            "months": len(months),
            "as_of": months[-1]["label"] if months else None,
        }
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/workspaces")
def list_workspaces(user: dict = Depends(current_user)):
    db = db_or_503()
    try:
        hotels = _list_or_bootstrap_hotels(db, user["email"], user["name"])
        return {"hotels": hotels}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/workspaces")
def create_workspace(body: ClientRequest, user: dict = Depends(current_user)):
    db = db_or_503()
    name = body.name.strip()
    city_name = (body.city or "").strip() or "Unspecified"
    hotel_id = f"{_slug(name)}-{secrets.token_hex(3)}"
    try:
        rows = db.run_write(
            Q.CREATE_USER_HOTEL,
            email=user["email"],
            hotel_id=hotel_id,
            name=name,
            rooms=body.rooms,
            city_id=_slug(city_name),
            city_name=city_name,
        )
        ensure_skeleton(db, hotel_id)
        hotel = rows[0] if rows else {"id": hotel_id, "name": name, "rooms": body.rooms, "city": city_name}
        hotels = db.run(Q.LIST_USER_HOTELS, email=user["email"])
        return {"hotel": hotel, "hotels": hotels}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/chat")
def chat(body: ChatRequest, user: dict = Depends(current_user), hotel_id: str = Depends(resolve_hotel_id)):
    db = db_or_503()
    try:
        return {"reply": assistant.answer(db, user, body.message, hotel_id=hotel_id)}
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/forecast_data")
def forecast_data(request: QueryRequest, hotel_id: str = Depends(resolve_hotel_id)):
    """Kept for the FastAgent workflow. The UI uses /api/forecast/generate."""
    db = db_or_503()
    text = (request.query or "").lower()
    months = request.months
    for token in ("3", "6", "12"):
        if token in text:
            months = int(token)
            break
    try:
        result = generate_forecast(db, horizon=months, hotel_id=hotel_id)
        return {"status": "success", "data": {"result": result["rows"], "insights": result["insights"]}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
