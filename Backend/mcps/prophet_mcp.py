from typing import Any
import pandas as pd
from prophet import Prophet
from pymongo import MongoClient
from fastmcp import FastMCP
from config import MONGO_URI, DB_NAME, PREPROCESS_COLLECTION_NAME, FORECAST_COLLECTION_NAME

mcp = FastMCP()

@mcp.tool
def forecast_tool_from_mongodb(months_to_forecast: int = 12) -> Any:
    """Forecast occupancy, ADR, and revenue using Prophet."""
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        data = list(db[PREPROCESS_COLLECTION_NAME].find({}))
        if not data:
            return {"error": "No preprocessed data"}

        df = pd.DataFrame(data)
        df['ds'] = pd.to_datetime(df[['year','month']].assign(day=1))
        df['avg_adr'] = df['Room_Revenue_per_month']/df['rooms_sold_per_month']
        df = df.dropna(subset=['Room_Revenue_per_month','rooms_sold_per_month','occupancy (%)','avg_adr'])

        def forecast_metric(metric):
            d = df[['ds',metric]].rename(columns={metric:'y'})
            m = Prophet(yearly_seasonality=True)
            m.fit(d)
            f = m.make_future_dataframe(periods=months_to_forecast, freq="MS")
            out = m.predict(f)
            return out[['ds','yhat']][out['ds']>df['ds'].max()]

        occ = forecast_metric("occupancy (%)")
        adr = forecast_metric("avg_adr")
        rev = forecast_metric("Room_Revenue_per_month")

        out_df = pd.DataFrame({
            "ds": occ["ds"],
            "occupancy": occ["yhat"].round(2).clip(0,100),
            "avg_adr": adr["yhat"].round(2),
            "room_revenue": rev["yhat"].round(2)
        })
        records = out_df.to_dict(orient="records")

        if records:
            for r in records:
                db[FORECAST_COLLECTION_NAME].update_one({"ds": r["ds"]},{"$set": r},upsert=True)

        return {"status":"success","result":records,"saved":len(records)}
    except Exception as e:
        return {"status":"error","message":str(e)}
    finally:
        client.close()
