"""Load raw readings CSV into readings_staging table"""
import argparse
import csv
import logging
import os
import sys
import time
import uuid   
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone

load_dotenv()
CSV_PATH = Path(__file__).parent.parent / "db" / "seed" / "output" / "readings.csv"
SENTINEL_DAY = datetime(1970, 1, 1, tzinfo=timezone.utc)  # chunk for rows with unparseable timestamps

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill")

               
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

def chunk_key(meter_id_raw, reading_ts_raw):
    """A chunk is one meter for one UTC day. Must be derived from the upsert key 
    (meter_id, reading_ts) so duplicates of a reading always land in the same chunk."""
    try:
        ts = datetime.fromisoformat(reading_ts_raw)
        day = ts.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    except (ValueError, TypeError):
        day = SENTINEL_DAY
    return int(meter_id_raw), day, day + timedelta(days=1)



def process_row(cur, row):
    """Validate one staging row; reject it or upsert it. Returns 'accepted', 'updated' or 'rejected'."""
    staging_id, meter_id_raw, reading_ts_raw, kwh_raw, status = row
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
        return "rejected"
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
        return "accepted" if cur.fetchone()[0] else "updated"

def claim_chunk(conn, batch_id, meter_id, chunk_start, chunk_end):
    """Return the backfill_runs is to process, or None if the chunk already succeeded.
    Commits 'running' on its own so progress is visible while the chunk is processed."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO backfill_runs (batch_id, meter_id, chunk_start, chunk_end, status)
        VALUES(%s, %s, %s, %s, 'pending')
        ON CONFLICT ON CONSTRAINT uq_backfill_runs_meter_id DO NOTHING
        """,
        (batch_id, meter_id, chunk_start, chunk_end),
    )
    cur.execute(
        """
        SELECT id, status FROM backfill_runs
        WHERE meter_id = %s AND chunk_start = %s AND chunk_end = %s
        FOR UPDATE
        """,
        (meter_id, chunk_start, chunk_end),
    )
    run_id, status = cur.fetchone()

    if status == "succeeded":
        conn.commit()
        cur.close()
        return None

    
    cur.execute(
        """
        UPDATE backfill_runs
        SET status = 'running', batch_id = %s, started_at = now(),
            finished_at = NULL, error_message = NULL
        WHERE id = %s
        """,
        (batch_id, run_id),
    )
    conn.commit()
    cur.close()
    return run_id

def process_chunk(conn, run_id, rows):
    """Process a chunk's rows and mark it succeeded in ONE transaction: data and status
    commit together or not at all. Returns counts, or None if the chunk failed."""
    counts = {"accepted": 0, "updated": 0, "rejected": 0}
    cur = conn.cursor()
    try:
        for row in rows:
            counts[process_row(cur, row)] += 1
        cur.execute(
            """
            UPDATE backfill_runs
            SET status = 'succeeded', rows_read = %s, rows_upserted = %s, rows_rejected = %s, finished_at = now()
            WHERE id = %s
            """,
            (len(rows), counts["accepted"] + counts["updated"], counts["rejected"], run_id),
        )
        conn.commit()
        return counts
    except Exception as e:
        conn.rollback()
        cur = conn.cursor()
        cur.execute(
            "UPDATE backfill_runs SET status = 'failed', error_message = %s, finished_at = now() WHERE id = %s",
            (str(e), run_id),
        )
        conn.commit()
        return None

def run_backfill(batch_id: str) -> int:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        "SELECT id, meter_id, reading_ts, kwh_value, status FROM readings_staging WHERE batch_id = %s ORDER BY id",
        (batch_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.commit()

    if not rows:
        log.error("no staginf rows for batch_id=%s", batch_id)
        conn.close()
        return 1

    chunks = defaultdict(list)
    for row in rows:
        chunks[chunk_key(row[1], row[2])].append(row)

    totals = {"read": 0, "accepted": 0, "updated": 0, "rejected": 0, "skipped": 0, "failed": 0}
    for meter_id, chunk_start, chunk_end in sorted(chunks):
        chunk_rows = chunks[(meter_id, chunk_start, chunk_end)]
        day = chunk_start.date()

        run_id = claim_chunk(conn, batch_id, meter_id, chunk_start, chunk_end)
        if run_id is None:
            totals["skipped"] += 1
            continue

        t0 = time.perf_counter()
        counts = process_chunk(conn, run_id, chunk_rows)
        ms = round((time.perf_counter() - t0) * 1000)

        if counts is None:
            totals["failed"] += 1
            log.error("chunk meter=%s day=%s status=failed rows=%s ms=%s", meter_id, day, len(chunk_rows), ms)
            continue

        totals["read"] += len(chunk_rows)
        for k in ("accepted", "updated", "rejected"):
            totals[k] += counts[k]
        log.info(
            "chunk meter=%s day=%s status=succeeded read=%s accepted=%s updated=%s rejected=%s ms=%s",
            meter_id, day, len(chunk_rows), counts["accepted"], counts["updated"], counts["rejected"], ms,
        )
    conn.close()
    log.info(
            "done batch_id=%s chunks=%s skipped=%s failed=%s read=%s accepted=%s updated=%s rejected=%s",
             batch_id, len(chunks), totals["skipped"], totals["failed"], totals["read"],
             totals["accepted"], totals["updated"], totals["rejected"],
        )
    return 1 if totals["failed"] else 0 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", help="resume an existing staging batch instead of loading the CSV again")
    args = parser.parse_args()

    if args.batch_id:
        batch_id = args.batch_id
    else:
        batch_id = str(uuid.uuid4())
        load_reference_data()
        load_to_staging(batch_id)

    sys.exit(run_backfill(batch_id))