"""FastMCP tools backed by CognoDB. Used by FastAgent when GEMINI_API_KEY is set."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Dict

from fastmcp import FastMCP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db import get_db  # noqa: E402
from forecast_engine import generate_forecast, load_history  # noqa: E402

mcp = FastMCP()


@mcp.tool
def process_excel_and_save(source_excel_path: str = "") -> Dict[str, Any]:
    """Validate that historical snapshots already live in CognoDB."""
    db = get_db()
    rows = load_history(db)
    if not rows:
        return {"status": "error", "message": "No historical snapshots in CognoDB. Run python -m scripts.seed"}
    return {"status": "success", "message": f"Found {len(rows)} monthly snapshots in the graph.", "latest": rows[-1]["label"]}


@mcp.tool
def forecast_tool_from_mongodb(months_to_forecast: int = 12) -> Dict[str, Any]:
    """Generate a forecast from CognoDB historical snapshots (name kept for the existing agent prompt)."""
    db = get_db()
    result = generate_forecast(db, horizon=months_to_forecast)
    return {"status": "success", "result": result["rows"], "insights": result["insights"], "model": result["model"]}


@mcp.tool
def evaluate_collection(collection_name: str = "predicted_data") -> Dict[str, Any]:
    """Forecast rows are already clipped and rounded when written to CognoDB."""
    db = get_db()
    rows = load_history(db)
    return {"status": "success", "message": "Graph snapshots are already normalized.", "historical_months": len(rows)}


@mcp.tool
def generate_report(output_dir: str = "./predicted_data") -> Dict[str, Any]:
    """Export the latest forecast rows to a timestamped Excel file."""
    import pandas as pd

    from forecast_engine import latest_forecast

    db = get_db()
    data = latest_forecast(db)
    if not data:
        return {"status": "error", "message": "No forecast run found. Generate a forecast first."}
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(output_dir, f"forecast_report_{ts}.xlsx")
    pd.DataFrame(data["rows"]).to_excel(file_path, index=False)
    return {"status": "success", "file_path": file_path, "rows": len(data["rows"])}


if __name__ == "__main__":
    mcp.run()
