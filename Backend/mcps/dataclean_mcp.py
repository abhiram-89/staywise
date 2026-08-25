from typing import Any, Dict
import pandas as pd
from pymongo import MongoClient
from fastmcp import FastMCP
from config import MONGO_URI, DB_NAME, SOURCE_COLLECTION_NAME, SOURCE_COLLECTION_NAME

mcp = FastMCP()

@mcp.tool
def preprocess_data(input: Dict[str, str] = None) -> Dict[str, Any]:
    """Fetch raw data, preprocess, and save cleaned version."""
    if input is None:
        input = {}
    db_name = input.get("db_name", DB_NAME)
    source_collection_name = input.get("collection_name", SOURCE_COLLECTION_NAME)
    target_collection_name = input.get("target_collection", SOURCE_COLLECTION_NAME)

    try:
        client = MongoClient(MONGO_URI)
        db = client[db_name]
        data = list(db[source_collection_name].find({}))
        if not data:
            return {"status": "error", "message": "No data found"}

        df = pd.DataFrame(data)
        required_cols = ["year","month","Room_Revenue_per_month","rooms_sold_per_month","occupancy (%)"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return {"status": "error", "message": f"Missing cols: {missing}"}

        df["ds"] = pd.to_datetime(df[["year","month"]].assign(day=1)).dt.to_pydatetime()
        for col in ["Room_Revenue_per_month","rooms_sold_per_month","occupancy (%)"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(df[col].median())

        df["avg_adr"] = df.apply(lambda r: r["Room_Revenue_per_month"]/r["rooms_sold_per_month"] if r["rooms_sold_per_month"]>0 else 0, axis=1)
        df.dropna(inplace=True)
        df = df.drop(columns=["_id"], errors="ignore")

        processed = df.to_dict(orient="records")
        tgt = db[target_collection_name]
        tgt.delete_many({})
        if processed:
            tgt.insert_many(processed)

        return {"status": "success","processed_records": len(processed)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        client.close()
