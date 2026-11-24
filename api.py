"""
FastAPI endpoints that read from the "A_crimesRecord" table.

Run:
    export DB_PASSWORD="your-password"
    uvicorn api:app --reload

Endpoints:
    GET /incidents/last/7-days
    GET /incidents/last/10-days
    GET /incidents/last/15-days
    GET /incidents/last/30-days
    GET /incidents/last/2-months
    GET /incidents/last/3-months
    GET /incidents/last/6-months
    GET /incidents/last/10-months
    GET /incidents/last/12-months
    GET /incidents            (everything, optional ?limit=N)
    GET /docs                 (Swagger UI)
"""

from enum import Enum
from typing import Optional

from fastapi import FastAPI, Query
from psycopg2.extras import RealDictCursor
from fastapi.middleware.cors import CORSMiddleware

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173"],
#     allow_methods=["GET"],
#     allow_headers=["*"],
# )
from sync_incidents import TABLE, get_connection

app = FastAPI(title="Cambridge Incidents API (from Postgres)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

class Period(str, Enum):
    d7 = "7-days"
    d10 = "10-days"
    d15 = "15-days"
    d30 = "30-days"
    m2 = "2-months"
    m3 = "3-months"
    m6 = "6-months"
    m10 = "10-months"
    m12 = "12-months"


# Whitelist: the value is never taken from user input directly
INTERVALS = {
    Period.d7: "7 days",
    Period.d10: "10 days",
    Period.d15: "15 days",
    Period.d30: "30 days",
    Period.m2: "2 months",
    Period.m3: "3 months",
    Period.m6: "6 months",
    Period.m10: "10 months",
    Period.m12: "12 months",
}


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


@app.get("/incidents/last/{period}")
def incidents_last(period: Period):
    """Records whose date_time falls within the chosen window, newest first."""
    interval = INTERVALS[period]
    rows = run_query(
        f"""
        SELECT date_time, id, type, subtype, location
        FROM {TABLE}
        WHERE date_time >= NOW() - INTERVAL '{interval}'
        ORDER BY date_time DESC
        """
    )
    return {"period": period.value, "count": len(rows), "data": rows}


@app.get("/incidents")
def all_incidents(limit: Optional[int] = Query(None, ge=1)):
    """All records, newest first (optionally only the latest N)."""
    sql = f"SELECT date_time, id, type, subtype, location FROM {TABLE} ORDER BY date_time DESC NULLS LAST"
    params: tuple = ()
    if limit:
        sql += " LIMIT %s"
        params = (limit,)
    rows = run_query(sql, params)
    return {"count": len(rows), "data": rows}
