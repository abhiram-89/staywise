from typing import Any, Dict
import os, pandas as pd
from pymongo import MongoClient
from fastmcp import FastMCP
from config import MONGO_URI, DB_NAME, PREPROCESS_COLLECTION_NAME

mcp = FastMCP()

@mcp.tool
def generate_report(report_type: str="monthly", output_path: str="./reports/report.xlsx") -> Dict[str, Any]:
    """Aggregate data into monthly/yearly report and save to Excel."""
    try:
        client = MongoClient(MONGO_URI)
        df = pd.DataFrame(list(client[DB_NAME][PREPROCESS_COLLECTION_NAME].find({})))
        client.close()
        if df.empty: return {"status":"error","message":"No data"}

        df.rename(columns={"Room_Revenue_per_month":"Room Revenue","occupancy (%)":"occupancy"}, inplace=True)
        for c in ["Room Revenue","avg_adr","occupancy"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        if report_type=="monthly":
            rep = df.groupby(["year","month"]).agg({"Room Revenue":"sum","avg_adr":"mean","occupancy":"mean"}).reset_index()
        elif report_type=="yearly":
            rep = df.groupby("year").agg({"Room Revenue":"sum","avg_adr":"mean","occupancy":"mean"}).reset_index()
        else:
            rep = df.describe().reset_index()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        rep.to_excel(output_path, index=False)

        return {"status":"success","file_path":output_path,"rows_in_report":len(rep)}
    except Exception as e:
        return {"status":"error","message":str(e)}
