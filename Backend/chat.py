"""Workspace assistant answers using imported hotel data, with optional Gemini."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config import GEMINI_API_KEY, HOTEL_ID
import queries as Q


def _gemini(prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 280},
    }).encode()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode())
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        return text or None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None


def answer(db, user: dict[str, Any], message: str, hotel_id: str = HOTEL_ID) -> str:
    text = (message or "").strip()
    lowered = text.lower()
    months = db.run(Q.HOTEL_MONTHS, hotel_id=hotel_id, start_id=None, end_id=None)
    latest_run = db.run(Q.GRAPH_FORECAST, hotel_id=hotel_id)
    hotel_rows = db.run(Q.GET_HOTEL, hotel_id=hotel_id)
    hotel = hotel_rows[0] if hotel_rows else {}
    name = user.get("name") or "there"

    if not months:
        if any(word in lowered for word in ("import", "upload", "file", "excel", "csv")):
            return (
                f"{name}, import a report first. Use Import report, then choose an Excel, CSV, or JSON file "
                "with year, month, and Room Revenue. Overview, Historical, Rooms & rates, and Forecasts fill from that file."
            )
        if "forecast" in lowered:
            return "A forecast needs imported history. Upload a report, then open Forecasts and click Run forecast."
        if "verify" in lowered or "otp" in lowered or "email" in lowered:
            return "After sign-up we email a 6-digit code. Enter it on Verify email, then sign in. Unverified accounts cannot sign in."
        return (
            f"Hi {name}. I am MIRA — I can help with import, forecasts, rooms, and this workspace. "
            "There is no imported history yet — start with Import report."
        )

    last = months[-1]
    revenue = sum(float(row.get("revenue") or 0) for row in months[-6:])
    occupancy = sum(float(row.get("occupancy") or 0) for row in months[-6:]) / max(1, min(6, len(months)))

    if any(word in lowered for word in ("hello", "hi", "help")):
        return (
            f"Hi {name}. I am MIRA. Ask me how to import a file, run a forecast, export Excel, or read rooms and rates. "
            f"Your latest imported period is {last.get('label')}."
        )
    if "import" in lowered or "upload" in lowered:
        return "Click Import report, then upload Excel/CSV/JSON with year, month, and Room Revenue. That file replaces the live history used everywhere."
    if "export" in lowered or "excel" in lowered:
        return "Open Forecasts, generate a horizon, then click Export Excel. The spreadsheet contains month, revenue, expenses, profit, and occupancy."
    if "room" in lowered or "rate" in lowered:
        return f"{hotel.get('name') or 'Your hotel'} has {hotel.get('rooms') or '—'} rooms. Open Rooms & rates to see types, availability, and demand from the latest imported month."
    if "forecast" in lowered:
        if latest_run and latest_run[0].get("months"):
            return f"A forecast is already saved ({latest_run[0]['months']} months). Open Forecasts to review it, change the horizon, or export Excel."
        return "Open Forecasts, pick 3 / 6 / 12 months, and click Run forecast. It uses only the file you imported."
    if "occupancy" in lowered:
        return f"Average occupancy across the latest imported window is {occupancy:.1f}%. Latest month ({last.get('label')}) is {float(last.get('occupancy') or 0):.1f}%."
    if "revenue" in lowered or "kpi" in lowered or "overview" in lowered:
        return f"Imported revenue for the latest window is about {revenue:,.0f}. Latest month {last.get('label')} recorded {float(last.get('revenue') or 0):,.0f}."
    if "graph" in lowered:
        return "Graph explorer shows the hotel node linked to city, imported months, departments, room types, and any forecast run. Click a node for details."
    if "verify" in lowered or "otp" in lowered:
        return "Sign-up stores your user in the graph, emails a hashed 6-digit code, and login is blocked until that code is verified."

    context = (
        f"You are a concise assistant for staywise hotel budget forecasting. "
        f"User: {name}. Hotel: {hotel.get('name')}. Imported months: {len(months)}. "
        f"Latest: {last.get('label')} revenue {last.get('revenue')} occupancy {last.get('occupancy')}. "
        f"Answer only about this app. Question: {text}"
    )
    generated = _gemini(context)
    if generated:
        return generated
    return (
        f"Your workspace has {len(months)} imported months through {last.get('label')}. "
        "Ask about import, forecast, export, rooms, or occupancy if you want a specific step."
    )
