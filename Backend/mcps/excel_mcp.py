from typing import Any, Dict
import os
import pandas as pd
from pymongo import MongoClient
from fastmcp import FastMCP
from config import MONGO_URI, DB_NAME 

mcp = FastMCP()

@mcp.tool
def process_excel_and_save(source_excel_path: str, collection_name: str) -> Dict[str, Any]:
    """Reads Excel, processes, saves CSV, and inserts into MongoDB."""
    if not os.path.exists(source_excel_path):
        return {"status": "error", "message": f"File not found: {source_excel_path}"}
    try:
        df = pd.read_excel(source_excel_path)
        required_cols = ["year", "month", "Room_Revenue_per_month"]
        df.dropna(subset=required_cols, inplace=True)
        if df.empty:
            return {"status": "warning", "message": "No valid data after cleaning."}

        df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))

        base_dir = os.path.dirname(source_excel_path)
        base_name = os.path.splitext(os.path.basename(source_excel_path))[0]
        save_path = os.path.join(base_dir, f"{base_name}_processed.csv")
        df.to_csv(save_path, index=False)

        with MongoClient(MONGO_URI) as client:
            db = client[DB_NAME]
            collection = db[collection_name]
            records = df.to_dict(orient="records")
            collection.insert_many(records)

        return {
            "status": "success",
            "details": {
                "local_save": f"Saved to {save_path}",
                "mongodb_save": f"Inserted {len(records)} records into {collection_name}"
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
