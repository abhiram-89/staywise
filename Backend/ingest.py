"""Normalize uploaded P&L rows and write them into the CognoDB graph."""

from __future__ import annotations

import calendar
import re
from typing import Any, Dict, Iterable, List

from config import HOTEL_ID
from db import GraphDB

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAME = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

DEPARTMENTS = [
    {"id": "payroll", "name": "Payroll", "color": "#1B365D", "sort_order": 1, "share": 0.30, "elasticity": 0.35},
    {"id": "marketing", "name": "Marketing", "color": "#5B4FC7", "sort_order": 2, "share": 0.20, "elasticity": 0.10},
    {"id": "utilities", "name": "Utilities", "color": "#7C9CBF", "sort_order": 3, "share": 0.15, "elasticity": 0.80},
    {"id": "maintenance", "name": "Maintenance", "color": "#A78BFA", "sort_order": 4, "share": 0.15, "elasticity": 0.20},
    {"id": "others", "name": "Others", "color": "#C4B5FD", "sort_order": 5, "share": 0.20, "elasticity": 0.45},
]

ROOM_TYPES = [
    {"id": "deluxe", "name": "Deluxe Suite", "share": 0.22, "base_rate": 14500},
    {"id": "executive", "name": "Executive Room", "share": 0.18, "base_rate": 11800},
    {"id": "presidential", "name": "Presidential Suite", "share": 0.08, "base_rate": 32000},
    {"id": "standard", "name": "Standard Room", "share": 0.28, "base_rate": 7800},
    {"id": "family", "name": "Family Room", "share": 0.14, "base_rate": 13200},
    {"id": "luxury", "name": "Luxury Suite", "share": 0.10, "base_rate": 21000},
]


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("₹", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _pick(row: Dict[str, Any], *names: str) -> Any:
    lookup = {re.sub(r"[^a-z0-9]+", "", str(key).lower()): value for key, value in row.items()}
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "", name.lower())
        if key in lookup and lookup[key] not in (None, ""):
            return lookup[key]
    return None


def _month_from_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        month = int(value)
        return month if 1 <= month <= 12 else None
    text = str(value).strip().lower()
    if text.isdigit():
        month = int(text)
        return month if 1 <= month <= 12 else None
    return MONTH_NAME.get(text)


def _parse_date_parts(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    text = str(value).strip()
    match = re.search(r"(20\d{2})[-/](\d{1,2})", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"(\d{1,2})[-/](20\d{2})", text)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            return int(match.group(2)), month
    return None, None


def season_for(month: int) -> str:
    if month in {11, 12, 1, 2}:
        return "Peak"
    if month in {6, 7, 8}:
        return "Monsoon"
    if month in {4, 5}:
        return "Summer"
    return "Shoulder"


def month_id(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def month_label(year: int, month: int) -> str:
    return f"{MONTH_ABBR[month - 1]} {year}"


def month_date(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last:02d}"


def expense_total(revenue: float, occupancy: float) -> float:
    ratio = 0.72 - (occupancy / 100.0) * 0.10
    return round(revenue * max(0.58, min(0.74, ratio)), 2)


def normalize_rows(raw_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        year = _num(_pick(row, "year", "Year"))
        month = _month_from_value(_pick(row, "month", "Month", "month_name"))
        if year is None or month is None:
            y2, m2 = _parse_date_parts(_pick(row, "date", "ds", "Date", "period"))
            year = year or y2
            month = month or m2
        if year is None or month is None:
            continue
        year_i, month_i = int(year), int(month)
        if month_i < 1 or month_i > 12:
            continue
        revenue = _num(_pick(row, "Room Revenue", "Room_Revenue_per_month", "revenue", "Revenue", "total_revenue", "room_revenue"))
        occupancy = _num(_pick(row, "occupancy", "occupancy (%)", "Occupancy", "occ"))
        adr = _num(_pick(row, "avg_adr", "ADR", "adr", "average_adr"))
        expenses = _num(_pick(row, "expenses", "Expenses", "total_expenses", "Total Expenses"))
        if revenue is None:
            continue
        occupancy = 0.0 if occupancy is None else max(0.0, min(100.0, occupancy))
        if expenses is None:
            expenses = expense_total(revenue, occupancy)
        if adr is None:
            adr = round(revenue / max(1.0, occupancy * 50.0), 2)
        key = month_id(year_i, month_i)
        normalized[key] = {
            "year": year_i,
            "month": month_i,
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "net_profit": round(revenue - expenses, 2),
            "occupancy": round(occupancy, 2),
            "adr": round(adr, 2),
        }
    rows = sorted(normalized.values(), key=lambda item: (item["year"], item["month"]))
    if not rows:
        raise ValueError(
            "No usable rows. Include year, month (or a date) and a revenue column such as 'Room Revenue'."
        )
    return rows


def ensure_skeleton(db: GraphDB, hotel_id: str = HOTEL_ID) -> None:
    db.run_write(
        """
        MERGE (h:Hotel {id: $hotel_id})
        SET h.name = coalesce(h.name, 'Grand Metropolitan Plaza'),
            h.rooms = coalesce(h.rooms, 180),
            h.star_rating = coalesce(h.star_rating, 5)
        MERGE (drv:DemandDriver {name: 'Occupancy'})
        MERGE (peak:Season {name: 'Peak'})
        MERGE (shoulder:Season {name: 'Shoulder'})
        MERGE (summer:Season {name: 'Summer'})
        MERGE (monsoon:Season {name: 'Monsoon'})
        """,
        hotel_id=hotel_id,
    )
    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})
        WHERE NOT (h)-[:LOCATED_IN]->(:City)
        MERGE (c:City {id: 'hyderabad'})
        SET c.name = 'Hyderabad'
        MERGE (h)-[:LOCATED_IN]->(c)
        """,
        hotel_id=hotel_id,
    )
    for dept in DEPARTMENTS:
        db.run_write(
            """
            MATCH (h:Hotel {id: $hotel_id})
            MATCH (drv:DemandDriver {name: 'Occupancy'})
            MERGE (d:Department {id: $id})
            SET d.name = $name, d.color = $color, d.sort_order = $sort_order
            MERGE (h)-[:HAS_DEPARTMENT]->(d)
            MERGE (d)-[:COST_DRIVEN_BY {elasticity: $elasticity}]->(drv)
            """,
            hotel_id=hotel_id,
            **dept,
        )
    for room in ROOM_TYPES:
        db.run_write(
            """
            MATCH (h:Hotel {id: $hotel_id})
            MERGE (r:RoomType {id: $id})
            SET r.name = $name, r.base_rate = $base_rate, r.share = $share
            MERGE (h)-[:OFFERS]->(r)
            """,
            hotel_id=hotel_id,
            **room,
        )


def replace_hotel_history(db: GraphDB, rows: List[Dict[str, Any]], hotel_id: str = HOTEL_ID) -> int:
    ensure_skeleton(db, hotel_id)
    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})-[:RECORDED]->(s:MonthlySnapshot)
        DETACH DELETE s
        """,
        hotel_id=hotel_id,
    )
    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})-[:RAN_FORECAST]->(r:ForecastRun)
        OPTIONAL MATCH (r)-[:PROJECTS]->(f:ForecastSnapshot)
        DETACH DELETE f, r
        """,
        hotel_id=hotel_id,
    )
    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})-[:HAS_DEPARTMENT]->(d:Department)-[sp:SPENT_IN]->(:Month)
        DELETE sp
        """,
        hotel_id=hotel_id,
    )
    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})-[:OFFERS]->(r:RoomType)-[c:CONTRIBUTED_IN]->(:Month)
        DELETE c
        """,
        hotel_id=hotel_id,
    )

    months_payload = []
    spend_payload = []
    room_payload = []
    next_payload = []
    prev = None
    for rec in rows:
        mid = month_id(rec["year"], rec["month"])
        months_payload.append({
            "mid": mid,
            "year": rec["year"],
            "month": rec["month"],
            "label": month_label(rec["year"], rec["month"]),
            "date": month_date(rec["year"], rec["month"]),
            "season": season_for(rec["month"]),
            "snap_id": f"{hotel_id}:{mid}",
            "revenue": rec["revenue"],
            "expenses": rec["expenses"],
            "profit": rec["net_profit"],
            "occupancy": rec["occupancy"],
            "adr": rec["adr"],
        })
        if prev:
            next_payload.append({"prev": prev, "curr": mid})
        prev = mid
        for dept in DEPARTMENTS:
            spend_payload.append({
                "dept_id": dept["id"],
                "mid": mid,
                "amount": round(rec["expenses"] * dept["share"], 2),
            })
        for room in ROOM_TYPES:
            room_payload.append({
                "room_id": room["id"],
                "mid": mid,
                "amount": round(rec["revenue"] * room["share"], 2),
                "share": room["share"],
            })

    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})
        UNWIND $rows AS rec
        MATCH (season:Season {name: rec.season})
        MERGE (mo:Month {id: rec.mid})
        SET mo.year = rec.year, mo.month = rec.month, mo.label = rec.label, mo.date = rec.date
        MERGE (mo)-[:IN_SEASON]->(season)
        MERGE (s:MonthlySnapshot {id: rec.snap_id})
        SET s.revenue = rec.revenue, s.expenses = rec.expenses, s.net_profit = rec.profit,
            s.occupancy = rec.occupancy, s.adr = rec.adr, s.source = 'upload'
        MERGE (h)-[:RECORDED]->(s)
        MERGE (s)-[:IN_MONTH]->(mo)
        """,
        hotel_id=hotel_id,
        rows=months_payload,
    )
    if next_payload:
        db.run_write(
            """
            UNWIND $rows AS rec
            MATCH (a:Month {id: rec.prev})
            MATCH (b:Month {id: rec.curr})
            MERGE (a)-[:NEXT]->(b)
            """,
            rows=next_payload,
        )
    db.run_write(
        """
        UNWIND $rows AS rec
        MATCH (d:Department {id: rec.dept_id})
        MATCH (mo:Month {id: rec.mid})
        MERGE (d)-[sp:SPENT_IN]->(mo)
        SET sp.amount = rec.amount
        """,
        rows=spend_payload,
    )
    db.run_write(
        """
        UNWIND $rows AS rec
        MATCH (r:RoomType {id: rec.room_id})
        MATCH (mo:Month {id: rec.mid})
        MERGE (r)-[c:CONTRIBUTED_IN]->(mo)
        SET c.revenue = rec.amount, c.occupancy_share = rec.share
        """,
        rows=room_payload,
    )
    return len(rows)
