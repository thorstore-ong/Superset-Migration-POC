"""Load raw readings CSV into readings_staging table"""

import csv
import os
import uuid   
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

from decimal import Decimal, InvalidOperation
from datetime import datetime

load_dotenv()
CSV_PATH = Path(__file__).parent.parent / "db" / "seed" / "output" / "readings.csv"

               
def load_to_staging(batch_id: str):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            cur.execute(
                """
                INSERT INTO readings_staging (batch_id, meter_id, reading_ts, kwh_value, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (batch_id, row["meter_id"], row["reading_ts"], row["kwh_value"], row["status"]),
            )
            count += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"Loaded {count} rows into readings_staging with batch {batch_id}")

def load_reference_data():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    sites_path = Path(__file__).parent.parent / "db" / "seed" / "output" / "sites.csv"
    with open(sites_path) as f:
        for row in csv.DictReader(f):
            cur.execute(
                """
                INSERT INTO sites (id, name, region)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (row["id"], row["name"], row["region"]),
            )

    meters_path = Path(__file__).parent.parent / "db" / "seed" / "output" / "meters.csv"
    with open(meters_path) as f:
        for row in csv.DictReader(f):
            cur.execute(
                """
                INSERT INTO meters (id, site_id, meter_type, install_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (row["id"], row["site_id"], row["meter_type"], row["install_date"]),
            )
    
    conn.commit()
    cur.close()
    conn.close()
    print("Loaded sites and meters")

def validate_and_load(batch_id: str):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    cur.execute(
        "SELECT id, meter_id, reading_ts, kwh_value, status FROM readings_staging WHERE batch_id = %s ORDER BY id",
        (batch_id,),
    )
    rows = cur.fetchall()

    accepted, rejected, updated = 0, 0, 0
    for staging_id, meter_id_raw, reading_ts_raw, kwh_raw, status in rows:
        reason = None

        try:
            reading_ts = datetime.fromisoformat(reading_ts_raw)
        except (ValueError, TypeError):
            reason = "bad_timestamp"

        kwh_value = None
        if reason is None:
            if kwh_raw == "" or kwh_raw is None:
                reason = "null_value"
            else:
                try:
                    kwh_value = Decimal(kwh_raw)
                    if kwh_value < 0:
                        reason = "negative_or_sentinel"
                except InvalidOperation:
                    reason = "unparseable_value"

        meter_id = int(meter_id_raw)

        if reason:
            cur.execute(
                """
                INSERT INTO readings_rejects (meter_id, reading_ts, raw_kwh_value, status, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (meter_id, reading_ts_raw if reason != "bad_timestamp" else None, kwh_raw, status, reason),
            )
            rejected += 1
        else:
            cur.execute(
                """
                INSERT INTO readings (meter_id, reading_ts, kwh_value, status, normalized_kwh)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (meter_id, reading_ts) 
                DO UPDATE SET kwh_value = EXCLUDED.kwh_value, 
                              normalized_kwh = EXCLUDED.normalized_kwh
                RETURNING (xmax = 0) AS inserted
                """,
                (meter_id, reading_ts, kwh_value, status, kwh_value / 1000),
            )
            was_inserted = cur.fetchone()[0]
            if was_inserted:
                accepted += 1
            else:
                updated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Accepted: {accepted}, Rejected: {rejected}, Updated: {updated}")


if __name__ == "__main__":
    batch_id = str(uuid.uuid4())
    load_reference_data()
    load_to_staging(batch_id)
    validate_and_load(batch_id)
    