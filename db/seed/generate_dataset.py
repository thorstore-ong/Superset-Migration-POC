import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 7, 1, tzinfo=timezone.utc)

SITES = [
    (1, "Midrand Depot", "Gauteng"),
    (2, "Durban Plant", "KwaZulu-Natal"),
    (3, "Cape Town Warehouse", "Western Cape"),
]

METERS = [
    {"id": 1, "site_id": 1, "meter_type": "energy_meter", "install_date":"2023-03-01", "capacity_kw": 120},
    {"id": 2, "site_id": 1, "meter_type": "generator", "install_date":"2023-03-15", "capacity_kw": 200},
    {"id": 3, "site_id": 2, "meter_type": "energy_meter", "install_date":"2022-11-10", "capacity_kw": 300},
    {"id": 4, "site_id": 2, "meter_type": "energy_meter", "install_date":"2022-11-15", "capacity_kw": 90},
    {"id": 5, "site_id": 3, "meter_type": "generator", "install_date":"2023-01-15", "capacity_kw": 250},
    {"id": 6, "site_id": 3, "meter_type": "energy_meter", "install_date":"2025-02-01", "capacity_kw": 150},
    {"id": 7, "site_id": 1, "meter_type": "energy_meter", "install_date":"2024-04-01", "capacity_kw": 60},
    {"id": 8, "site_id": 2, "meter_type": "generator", "install_date":"2025-05-01", "capacity_kw": 180},
]


# Each tuple contains (meter_id, gap_start_time, gap_duration_hours) - telemetry data will be missing for the specified duration starting from the gap_start_time
GAPS = [
    (1, datetime(2026, 3, 10, 6, tzinfo=timezone.utc), 48),
    (5, datetime(2026, 5, 2, 14, tzinfo=timezone.utc), 6)
]

def generator_run_hours(rng):
    """PICK THE HOURS A GENERATOR IS RUNNING: short bursts on ~35% of days (like loadshedding)"""
    running = set()
    day = START
    while day < END:
        if rng.random() < 0.35:
            start_hour = rng.randint(5,20)
            for h in range(rng.randint(2, 4)):
                running.add(day + timedelta(hours=start_hour + h))
                day += timedelta(days=1)
            return running


def build_readings(rng):
    rows = []
    for meter in METERS:
        running = generator_run_hours(rng) if meter["meter_type"] == "generator" else None
        ts = START
        while ts < END:
            if meter["meter_type"] == "generator":
                kwh = round(meter["capacity_kw"] * rng.uniform(0.6, 0.85), 3) if ts in running else 0.0
            else:
                daily = 0.55 + 0.45 * math.sin((ts.hour -6) / 24 * 2 * math.pi)  # peaks midday
                weekday = 1.0 if ts.weekday() < 5 else 0.7  # lower on weekends
                kwh = round(meter["capacity_kw"] * 0.6 * daily * weekday * rng.uniform(0.9, 1.1), 3)
            rows.append({"meter_id": meter["id"], "reading_ts": ts, "kwh_value": kwh, "status": "ok"})
            ts += timedelta(hours=1)
    return rows


def inject_messy_data(rows, rng):
    """Inject gaps and outliers into the readings"""
    manifest = {"gaps": [], "malformed": [], "exact_duplicates": [], "conflicting_duplicates": []}
    # Gaps
    for meter_id, gap_start, hours in GAPS:
        gap_end = gap_start + timedelta(hours=hours)
        rows = [r for r in rows if not (r["meter_id"] == meter_id and gap_start <= r["reading_ts"] < gap_end)]
        manifest["gaps"].append({"meter_id": meter_id, "from": gap_start.isoformat(), "hours": hours})

    # Malformed rows
    bad_idx = rng.sample(range(len(rows)), 8)
    print(f"DEBUG: Injecting {len(bad_idx)} malformed rows")
    modes = ["null", "negative", "sentinal", "bad_timestamp"]
    for n, i in enumerate(bad_idx):
        r, mode = rows[i], modes[n % 4]
        manifest["malformed"].append(
            {"meter_id": r["meter_id"], "original_ts": r["reading_ts"].isoformat(), "mode": mode }
            )
        if mode == "null":
            r["kwh_value"] = None
        elif mode == "negative":
            r["kwh_value"] = -round(rng.uniform(1, 20), 3)
        elif mode == "sentinal":
            r["kwh_value"] = -999
        else:
            r["reading_ts"] = "2026-13-45T99:00:00+00:00"  # invalid timestamp

        # Duplicates: appended at the END of the file to mimic late arrival
        clean_idx = [i for i in range(len(rows)) if i not in set(bad_idx)]
        late = []
        for n, i in enumerate(rng.sample(clean_idx, 15)):
            dup = dict(rows[i])
            key = {"meter_id": dup["meter_id"], "reading_ts": dup["reading_ts"].isoformat()}
            if n < 10:
                manifest["exact_duplicates"].append(key)
            else:
                manifest["conflicting_duplicates"].append(
                    {**key, "first_value": dup["kwh_value"], "later_value": round(dup["kwh_value"] * 1.1 + 1, 3)}
                )
                dup["kwh_value"] = round(dup["kwh_value"] * 1.1 + 1, 3)
            late.append(dup)

    return rows + late, manifest



def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            out = {k: r.get(k) for k in fieldnames}
            ts = out.get("reading_ts")
            if isinstance(ts, datetime):
                out["reading_ts"] = ts.isoformat()
            w.writerow(out) # None becomes an empty field, which Postgres COPY reads as NULL

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows, manifest = inject_messy_data(build_readings(rng), rng)
    manifest["seed"] = args.seed
    manifest["total_rows_written"] = len(rows)

    write_csv(OUTPUT_DIR / "sites.csv", ["id", "name", "region"],
              [dict(zip(["id", "name", "region"], s)) for s in SITES])
    write_csv(OUTPUT_DIR / "meters.csv", ["id", "site_id", "meter_type", "install_date"], METERS)
    write_csv(OUTPUT_DIR / "readings.csv", ["meter_id", "reading_ts", "kwh_value", "status"], rows)
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(rows)} readings. Seed={args.seed}")
              

if __name__ == "__main__":
    main()
            
        