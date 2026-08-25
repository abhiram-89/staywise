"""Load a realistic hotel budget graph into CognoDB.

Run from the Backend folder:
    python -m scripts.seed
"""

from __future__ import annotations

import calendar
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import HOTEL_ID  # noqa: E402
from db import close_db, get_db  # noqa: E402

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

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

EVENTS = [
    {"id": "sankranti", "name": "Sankranti / Pongal", "type": "festival", "impact": 0.85, "months": {1}},
    {"id": "wedding-peak", "name": "Wedding season", "type": "wedding", "impact": 0.92, "months": {11, 12, 1, 2}},
    {"id": "new-year", "name": "New Year", "type": "holiday", "impact": 0.88, "months": {12, 1}},
    {"id": "conference", "name": "Corporate conference circuit", "type": "conference", "impact": 0.70, "months": {1, 2, 9, 10, 11}},
    {"id": "ipl", "name": "IPL season (Hyderabad)", "type": "sport", "impact": 0.65, "months": {3, 4, 5}},
    {"id": "summer", "name": "Summer leisure travel", "type": "seasonal", "impact": 0.55, "months": {4, 5}},
    {"id": "monsoon", "name": "Monsoon lull", "type": "weather", "impact": -0.45, "months": {6, 7, 8}},
    {"id": "independence", "name": "Independence Day weekend", "type": "holiday", "impact": 0.40, "months": {8}},
    {"id": "ganesh", "name": "Ganesh Chaturthi", "type": "festival", "impact": 0.58, "months": {9}},
    {"id": "dussehra", "name": "Dussehra", "type": "festival", "impact": 0.62, "months": {10}},
    {"id": "diwali", "name": "Diwali", "type": "festival", "impact": 0.90, "months": {10, 11}},
    {"id": "christmas", "name": "Christmas", "type": "holiday", "impact": 0.80, "months": {12}},
]


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


def load_csv_rows() -> list[dict]:
    path = ROOT / "data" / "historicaldata_processed.csv"
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for rec in csv.DictReader(handle):
            rows.append({
                "year": int(rec["year"]),
                "month": int(rec["month"]),
                "revenue": float(rec["Room Revenue"]),
                "adr": float(rec["avg_adr"]),
                "occupancy": float(rec["occupancy"]),
            })
    return rows


def extend_2026(rows: list[dict]) -> list[dict]:
    by_month_2025 = {r["month"]: r for r in rows if r["year"] == 2025}
    extra = []
    for month in range(1, 9):
        base = by_month_2025[month]
        extra.append({
            "year": 2026,
            "month": month,
            "revenue": round(base["revenue"] * 1.085, 2),
            "adr": round(base["adr"] * 1.06, 2),
            "occupancy": round(min(99.4, base["occupancy"] + 0.8), 2),
        })
    return rows + extra


def expense_total(revenue: float, occupancy: float) -> float:
    # Operating leverage: higher occupancy improves margin slightly.
    ratio = 0.72 - (occupancy / 100.0) * 0.10
    return round(revenue * max(0.58, min(0.74, ratio)), 2)


def run() -> None:
    db = get_db()
    db.verify()
    rows = extend_2026(load_csv_rows())
    now = datetime.now(timezone.utc).isoformat()

    db.run_write(
        """
        MATCH (n)
        WHERE n:Hotel OR n:City OR n:Department OR n:Month OR n:Season
           OR n:CityEvent OR n:MonthlySnapshot OR n:DemandDriver OR n:RoomType
           OR n:ForecastRun OR n:ForecastSnapshot
        DETACH DELETE n
        """
    )

    db.run_write(
        """
        MERGE (c:City {id: 'hyderabad'})
        SET c.name = 'Hyderabad'
        MERGE (h:Hotel {id: $hotel_id})
        SET h.name = 'Grand Metropolitan Plaza',
            h.rooms = 180,
            h.star_rating = 5,
            h.updated_at = $now
        MERGE (h)-[:LOCATED_IN]->(c)
        MERGE (comp1:Hotel {id: 'cityview-inn'})
        SET comp1.name = 'Cityview Inn', comp1.rooms = 120, comp1.star_rating = 4
        MERGE (comp2:Hotel {id: 'urban-retreat'})
        SET comp2.name = 'The Urban Retreat', comp2.rooms = 95, comp2.star_rating = 4
        MERGE (comp1)-[:LOCATED_IN]->(c)
        MERGE (comp2)-[:LOCATED_IN]->(c)
        MERGE (h)-[:COMPETES_WITH]->(comp1)
        MERGE (h)-[:COMPETES_WITH]->(comp2)
        MERGE (drv:DemandDriver {name: 'Occupancy'})
        SET drv.description = 'Paid occupancy that scales variable hotel costs'
        MERGE (peak:Season {name: 'Peak'})
        MERGE (shoulder:Season {name: 'Shoulder'})
        MERGE (summer:Season {name: 'Summer'})
        MERGE (monsoon:Season {name: 'Monsoon'})
        """,
        hotel_id=HOTEL_ID,
        now=now,
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
            hotel_id=HOTEL_ID,
            **dept,
        )

    db.run_write(
        """
        MATCH (mkt:Department {id: 'marketing'})
        MATCH (drv:DemandDriver {name: 'Occupancy'})
        MERGE (mkt)-[:STIMULATES {lag_months: 1}]->(drv)
        """
    )

    for room in ROOM_TYPES:
        db.run_write(
            """
            MATCH (h:Hotel {id: $hotel_id})
            MERGE (r:RoomType {id: $id})
            SET r.name = $name, r.base_rate = $base_rate
            MERGE (h)-[:OFFERS]->(r)
            """,
            hotel_id=HOTEL_ID,
            **room,
        )

    for event in EVENTS:
        db.run_write(
            """
            MATCH (c:City {id: 'hyderabad'})
            MERGE (e:CityEvent {id: $id})
            SET e.name = $name, e.type = $type, e.impact_score = $impact
            MERGE (c)-[:HOSTED]->(e)
            """,
            id=event["id"],
            name=event["name"],
            type=event["type"],
            impact=event["impact"],
        )

    months_payload = []
    next_payload = []
    spend_payload = []
    room_payload = []
    event_payload = []
    competitor_payload = []
    prev_mid = None

    for rec in rows:
        y, m = rec["year"], rec["month"]
        mid = month_id(y, m)
        expenses = expense_total(rec["revenue"], rec["occupancy"])
        profit = round(rec["revenue"] - expenses, 2)
        months_payload.append({
            "mid": mid,
            "year": y,
            "month": m,
            "label": month_label(y, m),
            "date": month_date(y, m),
            "season": season_for(m),
            "snap_id": f"{HOTEL_ID}:{mid}",
            "revenue": rec["revenue"],
            "expenses": expenses,
            "profit": profit,
            "occupancy": rec["occupancy"],
            "adr": rec["adr"],
        })
        if prev_mid:
            next_payload.append({"prev": prev_mid, "curr": mid})
        prev_mid = mid
        for dept in DEPARTMENTS:
            spend_payload.append({
                "dept_id": dept["id"],
                "mid": mid,
                "amount": round(expenses * dept["share"], 2),
            })
        for room in ROOM_TYPES:
            room_payload.append({
                "room_id": room["id"],
                "mid": mid,
                "revenue": round(rec["revenue"] * room["share"], 2),
                "share": room["share"],
            })
        for event in EVENTS:
            if m in event["months"]:
                event_payload.append({"eid": event["id"], "mid": mid, "delta": event["impact"]})
        for hotel, offset in (("cityview-inn", -4.2), ("urban-retreat", -7.5)):
            occ = round(max(35.0, min(98.0, rec["occupancy"] + offset)), 2)
            competitor_payload.append({
                "hid": hotel,
                "mid": mid,
                "snap_id": f"{hotel}:{mid}",
                "occ": occ,
                "rev": round(rec["revenue"] * 0.62, 2),
                "exp": round(expenses * 0.70, 2),
                "profit": round(rec["revenue"] * 0.62 - expenses * 0.70, 2),
                "adr": round(rec["adr"] * 0.88, 2),
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
            s.occupancy = rec.occupancy, s.adr = rec.adr
        MERGE (h)-[:RECORDED]->(s)
        MERGE (s)-[:IN_MONTH]->(mo)
        """,
        hotel_id=HOTEL_ID,
        rows=months_payload,
    )
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
        SET c.revenue = rec.revenue, c.occupancy_share = rec.share
        """,
        rows=room_payload,
    )
    db.run_write(
        """
        MATCH (h:Hotel {id: $hotel_id})
        UNWIND $rows AS rec
        MATCH (e:CityEvent {id: rec.eid})
        MATCH (mo:Month {id: rec.mid})
        MERGE (e)-[:OCCURS_IN]->(mo)
        MERGE (e)-[:IMPACTS {delta: rec.delta}]->(h)
        """,
        hotel_id=HOTEL_ID,
        rows=event_payload,
    )
    db.run_write(
        """
        UNWIND $rows AS rec
        MATCH (h:Hotel {id: rec.hid})
        MATCH (mo:Month {id: rec.mid})
        MERGE (s:MonthlySnapshot {id: rec.snap_id})
        SET s.occupancy = rec.occ, s.revenue = rec.rev, s.expenses = rec.exp,
            s.net_profit = rec.profit, s.adr = rec.adr
        MERGE (h)-[:RECORDED]->(s)
        MERGE (s)-[:IN_MONTH]->(mo)
        """,
        rows=competitor_payload,
    )

    counts = db.run(
        """
        MATCH (n) WITH count(n) AS nodes
        MATCH ()-[r]->()
        RETURN nodes AS nodes, count(r) AS relationships
        """
    )
    print(f"Seeded CognoDB for {HOTEL_ID}: {len(rows)} months, {counts[0] if counts else counts}")
    print(f"Range {rows[0]['year']}-{rows[0]['month']:02d} to {rows[-1]['year']}-{rows[-1]['month']:02d}")
    close_db()


if __name__ == "__main__":
    run()
