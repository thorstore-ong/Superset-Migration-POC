"""Load raw readings CSV into readings_staging table"""

import csv
import os
import uuid   
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

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


if __name__ == "__main__":
    batch_id = str(uuid.uuid4())
    load_to_staging(batch_id)
    