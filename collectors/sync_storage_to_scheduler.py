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

CSV support (prices are public competitor data, so a dated CSV is safe to keep in the repo):
    --export-csv data/storage_prices   write today's facilities + prices to <dir>/storage_prices_<date>.csv
    --csv <file>                       upload a CSV in that same format instead of reading the SQLite database
                                       (use this to load prices you collected by hand)

Usage:
    python collectors/sync_storage_to_scheduler.py --backend-url https://<scheduler-host> --api-key <SCRAPER_API_KEY>
    python collectors/sync_storage_to_scheduler.py --export-csv data/storage_prices
    python collectors/sync_storage_to_scheduler.py --csv data/storage_prices/storage_prices_2026-10-28.csv --backend-url ...
    python collectors/sync_storage_to_scheduler.py --dry-run
"""

import sys
import os
import json
import time
import datetime
import logging
import argparse
import csv
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


CSV_COLUMNS = [
    "google_place_id", "name", "brand", "address", "city", "state", "zip_code", "lat", "lon", "phone", "website",
    "unit_size", "unit_type", "street_rate", "web_rate", "availability", "source", "scraped_at",
]


def export_csv(directory, facilities, pricing, day):
    """One row per facility + unit size. Facilities without a price are still listed (unit columns blank)."""
    by_id = {f["googlePlaceId"]: f for f in facilities}
    out = pathlib.Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"storage_prices_{day}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        priced = set()
        for p in pricing:
            f = by_id.get(p["facilityId"], {})
            priced.add(p["facilityId"])
            w.writerow({
                "google_place_id": p["facilityId"], "name": f.get("name"), "brand": f.get("brand"), "address": f.get("address"),
                "city": f.get("city"), "state": f.get("state"), "zip_code": f.get("zipCode"), "lat": f.get("lat"), "lon": f.get("lon"),
                "phone": f.get("phone"), "website": f.get("website"), "unit_size": p["unitSize"], "unit_type": p["unitType"],
                "street_rate": p["streetRate"], "web_rate": p["webRate"], "availability": p["availability"],
                "source": p["source"], "scraped_at": p["scrapedAt"],
            })
        for fid, f in by_id.items():
            if fid not in priced:
                w.writerow({"google_place_id": fid, "name": f.get("name"), "brand": f.get("brand"), "address": f.get("address"),
                            "city": f.get("city"), "state": f.get("state"), "zip_code": f.get("zipCode"), "lat": f.get("lat"),
                            "lon": f.get("lon"), "phone": f.get("phone"), "website": f.get("website")})
    return path


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def load_csv(path):
    """Read a CSV in the export format back into (facilities, pricing, day)."""
    facilities, pricing, seen, counts = [], [], set(), {}
    day = None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            fid = (r.get("google_place_id") or "").strip()
            if not fid:
                continue
            if fid not in seen:
                seen.add(fid)
                facilities.append({
                    "googlePlaceId": fid, "name": r.get("name"), "brand": r.get("brand"), "address": r.get("address"),
                    "city": r.get("city"), "state": r.get("state"), "zipCode": r.get("zip_code"), "lat": _num(r.get("lat")),
                    "lon": _num(r.get("lon")), "phone": r.get("phone"), "website": r.get("website"),
                })
            size = (r.get("unit_size") or "").strip()
            if not size:
                continue
            at = r.get("scraped_at") or datetime.date.today().isoformat()
            day = day or at[:10]
            n = counts.get((fid, size), 0)
            counts[(fid, size)] = n + 1
            pricing.append({
                "facilityId": fid, "unitSize": size, "unitType": r.get("unit_type"), "streetRate": _num(r.get("street_rate")),
                "webRate": _num(r.get("web_rate")), "availability": r.get("availability"), "source": r.get("source") or "csv",
                "scrapedAt": at, "snapshotKey": f"{size}_{n}_{at[:10]}",
            })
    return facilities, pricing, day


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
    ap.add_argument("--export-csv", metavar="DIR", help="Write facilities + prices to DIR/storage_prices_<date>.csv")
    ap.add_argument("--csv", metavar="FILE", help="Upload this CSV (export format) instead of reading the SQLite database")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be sent and exit")
    args = ap.parse_args()

    if args.csv:
        facilities, pricing, day = load_csv(args.csv)
    else:
        conn = get_connection()
        try:
            facilities = fetch_facilities(conn)
            pricing, day = fetch_pricing(conn, args.all_units)
        finally:
            conn.close()

    log.info(f"Loaded: {len(facilities)} facilities, {len(pricing)} pricing rows for {day}.")
    if not facilities or not pricing:
        log.error("Nothing to sync - the storage scrape produced no facilities/prices. Failing so the run is flagged.")
        return 1
    if args.export_csv:
        path = export_csv(args.export_csv, facilities, pricing, day)
        log.info(f"Wrote {path}")
        return 0  # exporting is its own step; run again without --export-csv to upload
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

    try:  # rebuild the Market tab's saved summary so page loads stay instant
        r = post(f"{args.backend_url.rstrip('/')}/api/storage/summary/refresh", {}, args.api_key)
        log.info(f"Summary refreshed: {r}")
    except Exception as e:
        log.warning(f"Summary refresh failed (the site will recompute on its next first load): {e}")

    log.info(f"Synced {f_ok} facilities and {p_ok} pricing rows ({p_skipped} skipped: unknown facility).")
    if p_ok == 0 or p_skipped > len(pricing) * 0.05:
        log.error("Too many pricing rows were rejected - check facility ids.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
