"""
collectors/sync_storage_to_scheduler.py

Pushes the self-storage facilities and the latest pricing snapshot from the local SQLite database
(filled by the StorageCafe ETL earlier in the same run) to the ATM Scheduler backend, which keeps
them in Firebase SQL Connect (Postgres):

    POST /api/storage/facilities/bulk
    POST /api/storage/pricing/bulk

Why this exists: the GitHub Actions runner is wiped after every run, so without this step the
prices the ETL collected were thrown away and the Scheduler's Market tab never updated.

Facilities are matched by google_place_id (the ETL's "sc_<zip>_<name>_<address>" id), which is the
Scheduler's facility id. Re-running the same day is safe: every snapshot carries a stable key, so it
overwrites instead of duplicating.

By default only the CHEAPEST rate per facility + unit size is sent (that is all the Market tab uses),
which keeps the database small as history accumulates daily. Use --all-units to send every unit row.

Usage:
    python collectors/sync_storage_to_scheduler.py --backend-url https://<scheduler-host> --api-key <SCRAPER_API_KEY>
    python collectors/sync_storage_to_scheduler.py --dry-run
"""

import sys
import os
import json
import time
import logging
import argparse
import pathlib
import urllib.request
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from database.db_setup import get_connection

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

CHUNK = 400


def fetch_facilities(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT google_place_id, name, brand, address, city, state, zip_code, lat, lon, phone, website
        FROM facilities
        WHERE google_place_id IS NOT NULL AND google_place_id != ''
    """)
    return [
        {
            "googlePlaceId": r["google_place_id"], "name": r["name"], "brand": r["brand"], "address": r["address"],
            "city": r["city"], "state": r["state"], "zipCode": r["zip_code"], "lat": r["lat"], "lon": r["lon"],
            "phone": r["phone"], "website": r["website"],
        }
        for r in cur.fetchall()
    ]


def fetch_pricing(conn, all_units=False):
    """Latest scrape day's pricing, one row per facility + unit size (cheapest web rate) unless all_units."""
    cur = conn.cursor()
    cur.execute("SELECT MAX(date(scraped_at)) AS d FROM pricing_snapshots")
    row = cur.fetchone()
    day = row["d"] if row else None
    if not day:
        return [], None
    cur.execute("""
        SELECT f.google_place_id AS place_id, p.unit_size, p.unit_type, p.street_rate, p.web_rate,
               p.availability, p.source, p.scraped_at
        FROM pricing_snapshots p
        JOIN facilities f ON f.id = p.facility_id
        WHERE date(p.scraped_at) = ? AND f.google_place_id IS NOT NULL AND f.google_place_id != ''
        ORDER BY f.google_place_id, p.unit_size, COALESCE(p.web_rate, p.street_rate)
    """, (day,))
    out = []
    seen = {}
    for r in cur.fetchall():
        k = (r["place_id"], r["unit_size"])
        n = seen.get(k, 0)
        if n and not all_units:
            continue  # rows are ordered cheapest first; keep only the first
        seen[k] = n + 1
        out.append({
            "facilityId": r["place_id"],
            "unitSize": r["unit_size"],
            "unitType": r["unit_type"],
            "streetRate": r["street_rate"],
            "webRate": r["web_rate"],
            "availability": r["availability"],
            "source": r["source"],
            "scrapedAt": r["scraped_at"],
            "snapshotKey": f"{r['unit_size']}_{n}_{day}",
        })
    return out, day


def post(url, payload, key, retries=3):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "x-api-key": key}
    last = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            last = f"HTTP {e.code}: {body}"
            if e.code in (400, 401, 403, 404):
                break  # retrying will not help
        except Exception as e:  # timeouts, connection resets
            last = str(e)
        time.sleep(3 * attempt)
    raise RuntimeError(f"POST {url} failed: {last}")


def push(base, path, field, rows, key):
    url = f"{base.rstrip('/')}{path}"
    total = skipped = 0
    for i in range(0, len(rows), CHUNK):
        res = post(url, {field: rows[i:i + CHUNK]}, key)
        total += res.get("count", 0)
        skipped += res.get("skipped", 0)
        log.info(f"  {field}: {min(i + CHUNK, len(rows))}/{len(rows)}")
    return total, skipped


def main():
    ap = argparse.ArgumentParser(description="Sync storage facilities + pricing to the ATM Scheduler")
    ap.add_argument("--backend-url", default=os.environ.get("ATM_SCHEDULER_URL"), help="Base URL of the ATM Scheduler")
    ap.add_argument("--api-key", default=os.environ.get("SCRAPER_API_KEY"), help="Scraper API key (SCRAPER_API_KEY)")
    ap.add_argument("--all-units", action="store_true", help="Send every unit row, not just the cheapest per size")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be sent and exit")
    args = ap.parse_args()

    conn = get_connection()
    try:
        facilities = fetch_facilities(conn)
        pricing, day = fetch_pricing(conn, args.all_units)
    finally:
        conn.close()

    log.info(f"Local SQLite: {len(facilities)} facilities, {len(pricing)} pricing rows for {day}.")
    if not facilities or not pricing:
        log.error("Nothing to sync - the storage scrape produced no facilities/prices. Failing so the run is flagged.")
        return 1
    if args.dry_run:
        log.info("Dry run - nothing sent.")
        return 0
    if not args.backend_url or not args.api_key:
        log.error("Missing --backend-url / --api-key (ATM_SCHEDULER_URL / SCRAPER_API_KEY).")
        return 1

    try:
        f_ok, _ = push(args.backend_url, "/api/storage/facilities/bulk", "facilities", facilities, args.api_key)
        p_ok, p_skipped = push(args.backend_url, "/api/storage/pricing/bulk", "snapshots", pricing, args.api_key)
    except Exception as e:
        log.error(str(e))
        return 1

    log.info(f"Synced {f_ok} facilities and {p_ok} pricing rows ({p_skipped} skipped: unknown facility).")
    if p_ok == 0 or p_skipped > len(pricing) * 0.05:
        log.error("Too many pricing rows were rejected - check facility ids.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
