from typing import Any, Dict
from pymongo import MongoClient
from fastmcp import FastMCP
from config import MONGO_URI, DB_NAME, FORECAST_COLLECTION_NAME

mcp = FastMCP()

@mcp.tool
def evaluate_collection(collection_name: str = FORECAST_COLLECTION_NAME) -> Dict[str, Any]:
    """Evaluate forecasted data and clean values."""
    try:
        client = MongoClient(MONGO_URI)
        coll = client[DB_NAME][collection_name]
        docs = list(coll.find({}))
        if not docs: return {"status":"success","rows_updated":0,"message":"No docs"}

        updated = 0
        for d in docs:
            set_fields = {}
            try:
                if "occupancy" in d: set_fields["occupancy"] = round(max(0,min(100,float(d["occupancy"]))),2)
                if "avg_adr" in d: set_fields["avg_adr"] = int(round(float(d["avg_adr"])))
                if "room_revenue" in d: set_fields["room_revenue"] = round(float(d["room_revenue"]),2)
                if set_fields:
                    coll.update_one({"_id": d["_id"]},{"$set":set_fields})
                    updated+=1
            except: continue
        return {"status":"success","rows_updated":updated}
    except Exception as e:
        return {"status":"error","message":str(e)}
    finally:
        client.close()