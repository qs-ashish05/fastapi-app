"""
Loads Cambridge incidents into the Postgres table "A_crimesRecord".

- Creates the table if it doesn't exist (id is the PRIMARY KEY).
- Safe to re-run: rows whose id already exists are skipped.

Usage:
    export DB_PASSWORD="your-password"
    python sync_incidents.py
"""

import os
import sys

import psycopg2
import requests
from psycopg2.extras import execute_values

SOCRATA_URL = "https://data.cambridgema.gov/resource/3gki-wyrb.json"
PAGE_SIZE = 1000  # Socrata returns at most 1000 rows per request
FIELDS = "date_time,id,type,subtype,location"

# Quoted so Postgres keeps the exact case (otherwise it becomes a_crimesrecord)
TABLE = '"A_crimesRecord"'

DB_CONFIG = {
    "host": "aws-0-ap-south-1.pooler.supabase.com",
    "port":  6543,
    "dbname": "postgres",
    "user": "postgres.jrcnplryqsgwflsytxyc",
    "password": "Ash@qwerty@8080",
    "sslmode": "require",
}


def get_connection():
    if not DB_CONFIG["password"]:
        sys.exit("Set the DB_PASSWORD environment variable first.")
    return psycopg2.connect(**DB_CONFIG)


def create_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id        TEXT PRIMARY KEY,
                date_time TIMESTAMP,
                type      TEXT,
                subtype   TEXT,
                location  TEXT
            )
            """
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_a_crimesrecord_date_time '
            f"ON {TABLE} (date_time DESC)"
        )
    conn.commit()


def fetch_pages():
    """Yield the dataset one page (list of dicts) at a time."""
    offset = 0
    with requests.Session() as session:
        while True:
            params = {
                "$select": FIELDS,
                # id as tie-breaker keeps paging stable
                "$order": "date_time DESC, id",
                "$limit": PAGE_SIZE,
                "$offset": offset,
            }
            resp = session.get(SOCRATA_URL, params=params, timeout=60)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            yield batch
            if len(batch) < PAGE_SIZE:
                break
            offset += PAGE_SIZE


def insert_batch(conn, batch: list[dict]) -> int:
    """Insert a page; rows with an existing id are ignored. Returns rows inserted."""
    values = [
        (
            str(r["id"]),
            r.get("date_time"),
            r.get("type"),
            r.get("subtype"),
            r.get("location"),
        )
        for r in batch
        if r.get("id") is not None
    ]
    if not values:
        return 0

    with conn.cursor() as cur:
        inserted = execute_values(
            cur,
            f"""
            INSERT INTO {TABLE} (id, date_time, type, subtype, location)
            VALUES %s
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            values,
            page_size=PAGE_SIZE,
            fetch=True,
        )
    conn.commit()
    return len(inserted)


def main() -> None:
    conn = get_connection()
    try:
        create_table(conn)

        fetched = inserted = 0
        for batch in fetch_pages():
            fetched += len(batch)
            inserted += insert_batch(conn, batch)
            print(f"Fetched {fetched} | newly inserted {inserted}", flush=True)

        print(f"\nDone. Fetched {fetched} rows, inserted {inserted} new, "
              f"skipped {fetched - inserted} existing.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
