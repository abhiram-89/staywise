"""Budget forecast engine.

Primary method uses the graph: analog months that share a season and overlapping
city events, then a variable-length NEXT path for recent growth. Prophet is used
as a blend when it is installed.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from config import HOTEL_ID
from db import GraphDB
import queries as Q

try:
    import pandas as pd
    from prophet import Prophet

    HAS_PROPHET = True
except Exception:
    HAS_PROPHET = False


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(filter(None, a)), set(filter(None, b))
    if not sa and not sb:
        return 0.35
    if not sa or not sb:
        return 0.1
    return len(sa & sb) / len(sa | sb)


def _month_id(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_abbr[month]} {year}"


def _month_date(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last:02d}"


def _season_for(month: int) -> str:
    if month in {11, 12, 1, 2}:
        return "Peak"
    if month in {6, 7, 8}:
        return "Monsoon"
    if month in {4, 5}:
        return "Summer"
    return "Shoulder"


EVENT_TYPES_BY_MONTH = {
    1: ["festival", "wedding", "holiday", "conference"],
    2: ["wedding", "conference"],
    3: ["sport"],
    4: ["sport", "seasonal"],
    5: ["sport", "seasonal"],
    6: ["weather"],
    7: ["weather"],
    8: ["weather", "holiday"],
    9: ["conference", "festival"],
    10: ["conference", "festival"],
    11: ["wedding", "conference", "festival"],
    12: ["wedding", "holiday"],
}


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + n
    return total // 12, total % 12 + 1


def _pct(new: float, old: float) -> float:
    if not old:
        return 0.0
    return round(((new - old) / old) * 100, 1)


def _trend_sentence(metric: str, pct: float, window: int) -> str:
    if pct >= 0:
        verb = "increase" if metric == "Revenue" else "grow"
        return f"{metric} is expected to {verb} by {pct}% versus the last {window} months."
    return f"{metric} is expected to decrease by {abs(pct)}% versus the last {window} months."


def load_history(db: GraphDB, hotel_id: str = HOTEL_ID) -> List[Dict[str, Any]]:
    return db.run(Q.HOTEL_MONTHS, hotel_id=hotel_id, start_id=None, end_id=None)


def _prophet_forecast(history: List[Dict[str, Any]], horizon: int) -> Optional[List[Dict[str, Any]]]:
    if not HAS_PROPHET or len(history) < 8:
        return None
    try:
        frame = pd.DataFrame(history)
        frame["ds"] = pd.to_datetime(frame["id"] + "-01")

        def fit(column: str, log: bool = False) -> List[float]:
            data = frame[["ds", column]].rename(columns={column: "y"}).dropna()
            if log:
                data["y"] = (data["y"].clip(lower=1)).apply(lambda x: __import__("numpy").log(x))
            model = Prophet(yearly_seasonality=True, seasonality_mode="additive")
            model.fit(data)
            future = model.make_future_dataframe(periods=horizon, freq="MS")
            pred = model.predict(future).tail(horizon)["yhat"]
            if log:
                pred = pred.apply(lambda x: float(__import__("numpy").exp(x)))
            return [float(v) for v in pred]

        revenues = fit("revenue", log=True)
        occupancies = fit("occupancy", log=False)
        adrs = fit("adr", log=False)
        last = history[-1]
        last_y, last_m = int(last["year"]), int(last["month"])
        rows = []
        for i in range(horizon):
            y, m = _add_months(last_y, last_m, i + 1)
            occ = max(35.0, min(99.5, occupancies[i]))
            rev = max(0.0, revenues[i])
            rows.append({"year": y, "month": m, "revenue": rev, "occupancy": occ, "adr": max(0.0, adrs[i])})
        return rows
    except Exception as exc:
        print(f"[forecast] Prophet unavailable, using graph analogs: {exc}")
        return None


def _graph_analog_forecast(db: GraphDB, history: List[Dict[str, Any]], horizon: int, hotel_id: str) -> List[Dict[str, Any]]:
    last = history[-1]
    last_y, last_m = int(last["year"]), int(last["month"])
    recent = history[-12:] if len(history) >= 12 else history
    prior = history[-24:-12] if len(history) >= 24 else history[: max(1, len(history) // 2)]
    recent_rev = sum(r["revenue"] for r in recent) / len(recent)
    prior_rev = sum(r["revenue"] for r in prior) / len(prior) if prior else recent_rev
    growth = max(-0.05, min(0.18, (recent_rev / prior_rev - 1) if prior_rev else 0.06))

    by_id = {r["id"]: r for r in history}
    rows = []
    for i in range(horizon):
        y, m = _add_months(last_y, last_m, i + 1)
        analogs = db.run(
            Q.ANALOG_MONTHS,
            hotel_id=hotel_id,
            year=y,
            month=m,
            season=_season_for(m),
            target_events=EVENT_TYPES_BY_MONTH.get(m, []),
        )
        weights, rev_acc, occ_acc, adr_acc = 0.0, 0.0, 0.0, 0.0
        for analog in analogs:
            years_ago = max(1, y - int(analog["year"]))
            recency = 1.0 / years_ago
            event_sim = _jaccard(analog.get("analog_events") or [], analog.get("target_events") or [])
            same_month = 0.5 if int(analog["month"]) == m else 0.0
            weight = 0.35 + 0.25 * event_sim + 0.15 * recency + same_month
            hist_row = by_id.get(analog["id"])
            adr = hist_row["adr"] if hist_row else analog["revenue"] / 8000
            weights += weight
            rev_acc += analog["revenue"] * weight
            occ_acc += analog["occupancy"] * weight
            adr_acc += adr * weight
        if weights == 0:
            same_month = [r for r in history if int(r["month"]) == m]
            base = same_month[-1] if same_month else last
            revenue = base["revenue"] * (1 + growth)
            occupancy = base["occupancy"]
            adr = base.get("adr") or 1000
        else:
            revenue = (rev_acc / weights) * (1 + growth)
            occupancy = occ_acc / weights
            adr = adr_acc / weights
        occupancy = max(38.0, min(99.2, occupancy + i * 0.15))
        rows.append({"year": y, "month": m, "revenue": revenue, "occupancy": occupancy, "adr": adr})
    return rows


def _blend(prophet_rows: Optional[List[Dict[str, Any]]], analog_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not prophet_rows:
        return analog_rows
    blended = []
    for p, a in zip(prophet_rows, analog_rows):
        blended.append({
            "year": a["year"],
            "month": a["month"],
            "revenue": 0.65 * p["revenue"] + 0.35 * a["revenue"],
            "occupancy": 0.65 * p["occupancy"] + 0.35 * a["occupancy"],
            "adr": 0.65 * p["adr"] + 0.35 * a["adr"],
        })
    return blended


def _apply_cost_drivers(
    db: GraphDB,
    history: List[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    hotel_id: str,
) -> List[Dict[str, Any]]:
    drivers = db.run(Q.COST_DRIVER_ELASTICITIES, hotel_id=hotel_id)
    last = history[-1]
    last_occ = float(last["occupancy"])
    last_rev = float(last["revenue"])
    last_exp = float(last["expenses"])
    ratio = last_exp / last_rev if last_rev else 0.68
    occupancy_elasticity = 0.0
    if drivers:
        occupancy_elasticity = sum(d["elasticity"] for d in drivers if d["driver"] == "Occupancy") / max(
            1, len([d for d in drivers if d["driver"] == "Occupancy"])
        )

    out = []
    for row in rows:
        occ_delta = (row["occupancy"] - last_occ) / 100.0
        expenses = last_exp * (row["revenue"] / last_rev if last_rev else 1) * (1 + occupancy_elasticity * occ_delta * 0.5)
        expenses = max(row["revenue"] * (ratio - 0.06), min(row["revenue"] * (ratio + 0.04), expenses))
        out.append({
            **row,
            "revenue": round(row["revenue"], 2),
            "expenses": round(expenses, 2),
            "net_profit": round(row["revenue"] - expenses, 2),
            "occupancy": round(row["occupancy"], 2),
            "adr": round(row["adr"], 2),
        })
    return out


def _insights(db: GraphDB, history: List[Dict[str, Any]], forecast: List[Dict[str, Any]], hotel_id: str) -> List[str]:
    notes: List[str] = []
    if not history or not forecast:
        return notes

    last_hist = history[-6:] if len(history) >= 6 else history
    hist_rev = sum(r["revenue"] for r in last_hist) / len(last_hist)
    fc_rev = sum(r["revenue"] for r in forecast) / len(forecast)
    hist_profit = sum(r["net_profit"] for r in last_hist) / len(last_hist)
    fc_profit = sum(r["net_profit"] for r in forecast) / len(forecast)
    hist_occ = sum(r["occupancy"] for r in last_hist) / len(last_hist)
    fc_occ = sum(r["occupancy"] for r in forecast) / len(forecast)

    notes.append(_trend_sentence("Revenue", _pct(fc_rev, hist_rev), len(last_hist)))
    notes.append(_trend_sentence("Net profit", _pct(fc_profit, hist_profit), len(last_hist)))
    if fc_occ >= hist_occ:
        notes.append("Occupancy rate is expected to improve steadily as peak-season demand returns.")
    else:
        notes.append("Occupancy eases slightly - watch monsoon and shoulder months in the horizon.")

    events = db.run(Q.EVENT_COST_CASCADE, hotel_id=hotel_id, min_impact=0.6)
    if events:
        top = events[0]
        notes.append(
            f"{top['event']} historically lifted occupancy to {top['occupancy']:.1f}% "
            f"and pulled {top['department']} spend with it (graph cascade)."
        )

    latest = db.run(Q.LATEST_MONTH, hotel_id=hotel_id)
    if latest:
        comps = db.run(Q.COMPETITOR_OCCUPANCY, hotel_id=hotel_id, month_id=latest[0]["id"])
        if comps:
            leader = comps[0]
            if leader["occupancy_gap"] >= 0:
                notes.append(
                    f"You outpaced {leader['competitor']} by {leader['occupancy_gap']:.1f} occupancy points last month."
                )

    start = history[0]
    end = history[-1]
    try:
        growth = db.run(
            Q.REVENUE_PATH_GROWTH,
            hotel_id=hotel_id,
            start_id=start["id"],
            end_id=end["id"],
        )
        if growth:
            hops = growth[0]["hops"]
            notes.append(
                f"Followed {hops} month-to-month NEXT hops from {start['label']} to {end['label']} "
                f"to estimate the growth path used in this run."
            )
    except Exception:
        pass

    return notes[:5]


def generate_forecast(db: GraphDB, horizon: int = 6, hotel_id: str = HOTEL_ID) -> Dict[str, Any]:
    horizon = max(3, min(12, int(horizon)))
    history = load_history(db, hotel_id)
    if len(history) < 6:
        raise ValueError("Need at least 6 months of historical snapshots in the graph before forecasting.")

    analog_rows = _graph_analog_forecast(db, history, horizon, hotel_id)
    prophet_rows = _prophet_forecast(history, horizon)
    model = "prophet+graph-analog" if prophet_rows else "graph-analog"
    blended = _blend(prophet_rows, analog_rows)
    finalized = _apply_cost_drivers(db, history, blended, hotel_id)

    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    db.run_write(
        Q.CREATE_FORECAST_RUN,
        hotel_id=hotel_id,
        run_id=run_id,
        created_at=created_at,
        horizon_months=horizon,
        model=model,
    )
    for row in finalized:
        mid = _month_id(row["year"], row["month"])
        db.run_write(
            Q.UPSERT_FORECAST_MONTH,
            hotel_id=hotel_id,
            run_id=run_id,
            month_id=mid,
            year=row["year"],
            month=row["month"],
            label=_month_label(row["year"], row["month"]),
            date=_month_date(row["year"], row["month"]),
            snapshot_id=f"{run_id}:{mid}",
            revenue=row["revenue"],
            expenses=row["expenses"],
            net_profit=row["net_profit"],
            occupancy=row["occupancy"],
            adr=row["adr"],
        )

    insights = _insights(db, history, finalized, hotel_id)
    return {
        "run_id": run_id,
        "created_at": created_at,
        "horizon_months": horizon,
        "model": model,
        "rows": [
            {
                **row,
                "id": _month_id(row["year"], row["month"]),
                "label": _month_label(row["year"], row["month"]),
                "date": _month_date(row["year"], row["month"]),
            }
            for row in finalized
        ],
        "insights": insights,
    }


def latest_forecast(db: GraphDB, hotel_id: str = HOTEL_ID) -> Optional[Dict[str, Any]]:
    rows = db.run(Q.GET_LATEST_FORECAST, hotel_id=hotel_id)
    if not rows:
        return None
    first = rows[0]
    return {
        "run_id": first["run_id"],
        "created_at": first["created_at"],
        "horizon_months": first["horizon_months"],
        "model": first["model"],
        "rows": [
            {
                "id": r["id"],
                "label": r["label"],
                "year": r["year"],
                "month": r["month"],
                "date": r["date"],
                "revenue": r["revenue"],
                "expenses": r["expenses"],
                "net_profit": r["net_profit"],
                "occupancy": r["occupancy"],
                "adr": r["adr"],
            }
            for r in rows
        ],
        "insights": _insights(db, load_history(db, hotel_id), rows, hotel_id),
    }
