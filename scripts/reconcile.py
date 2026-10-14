"""Compare the database end state against the generator's manifest. Exit 1 on any mismatch."""

import json
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import psycopg2
from dotenv  import load_dotenv

load_dotenv()
MANIFEST_PATH = Path(__file__).parent.parent / "db" / "seed" / "output" / "manifest.json"

MODE_TO_REASON = {
    "null" : "null_value",
    "negative" : "negative_or_sentinel",
    "sentinal": "negative_or_sentinel",
    "bad_timestamp": "bad_timestamp",
}

def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text())
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    failures = []

    def check(name, expected, actual):
        ok = expected == actual
        print(f"{'ok' if ok else 'MISMATCH' :8} {name} expected={expected} actual={actual}")
        if not ok:
            failures.append(name)

    total = manifest["total_rows_written"]
    malformed = len(manifest["malformed"])
    dupes = len(manifest["exact_duplicates"]) + len(manifest["conflicting_duplicates"])

    cur.execute(
        "SELECT count(*) FILTER (WHERE status <> 'succeeded'), "
        "COALESCE(sum(rows_read), 0), COALESCE(sum(rows_upserted), 0) FROM backfill_runs"
    )
    unfinished, rows_read, rows_upserted = cur.fetchone()
    check("unfinished chunks", 0, unfinished)
    check("rows read", total, rows_read)
    check("rows upserted", total - malformed, rows_upserted)

    expected_reasons = Counter(MODE_TO_REASON[m["mode"]] for m in manifest["malformed"])
    cur.execute("SELECT reason, count(*) FROM readings_rejects GROUP BY reason")
    check("rejects by reason", dict(expected_reasons), dict(cur.fetchall()))

    cur.execute("SELECT count(*) FROM readings")
    check("distinct readings", total - malformed - dupes, cur.fetchone()[0])

    for d in manifest["conflicting_duplicates"]:
        cur.execute(
            "SELECT kwh_value FROM readings WHERE meter_id = %s AND reading_ts = %s",
            (d["meter_id"], d["reading_ts"]),
        )
        row = cur.fetchone()
        actual = Decimal(str(row[0])) if row else None
        check(f"last one wins meter={d['meter_id']} ts={d['reading_ts']}", Decimal(str(d["later_value"])), actual)

    conn.close()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("All checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())