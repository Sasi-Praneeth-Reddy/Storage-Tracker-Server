"""
collectors/sync_leads_to_scheduler.py

Bridges scraped USA Home Listings from the local SQLite database to the
ATM Scheduler backend (stored in Firebase SQL Connect) via POST /api/leads/ingest.
Sends in chunks and exits non-zero on failure so the GitHub Actions run is flagged.

Usage:
    python collectors/sync_leads_to_scheduler.py --backend-url http://localhost:8787
    python collectors/sync_leads_to_scheduler.py --backend-url https://atm-scheduler.web.app
"""

import sys
import os
import json
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

DEFAULT_BACKEND = "http://localhost:8787"
CHUNK = 200


def fetch_local_leads(limit=50000):
    """Retrieve pre_mover_leads from local SQLite database."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id, address, city, state, zip_code, county, status,
                list_price, bedrooms, bathrooms, sqft, is_vacant,
                listed_date, first_name, last_name, owner_full_name,
                email, phone, realtor_name, realtor_phone, realtor_email,
                broker_name
            FROM pre_mover_leads
            ORDER BY scraped_at DESC
            LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


def sync_to_scheduler(backend_url, leads, api_key=None):
    """Push leads to ATM Scheduler's /api/leads/ingest endpoint."""
    if not leads:
        log.info("No local leads found to sync.")
        return 0

    url = f"{backend_url.rstrip('/')}/api/leads/ingest"
    log.info(f"Syncing {len(leads)} leads to {url}...")

    # Normalize fields for the Scheduler leads schema
    payload_leads = []
    for l in leads:
        payload_leads.append({
            "address": l.get("address") or "",
            "city": l.get("city") or "",
            "state": l.get("state") or "",
            "zipCode": l.get("zip_code") or "",
            "county": l.get("county") or "",
            "status": l.get("status") or "for_sale",
            "listPrice": l.get("list_price"),
            "bedrooms": l.get("bedrooms"),
            "bathrooms": l.get("bathrooms"),
            "sqft": l.get("sqft"),
            "isVacant": bool(l.get("is_vacant")),
            "listedDate": l.get("listed_date"),
            "firstName": l.get("first_name") or "",
            "lastName": l.get("last_name") or "",
            "ownerFullName": l.get("owner_full_name") or "",
            "email": l.get("email") or "",
            "phone": l.get("phone") or "",
            "realtorName": l.get("realtor_name") or "",
            "realtorPhone": l.get("realtor_phone") or "",
            "realtorEmail": l.get("realtor_email") or "",
            "brokerName": l.get("broker_name") or "",
        })

    headers = {"Content-Type": "application/json"}
    key = api_key or os.environ.get("SCRAPER_API_KEY") or os.environ.get("SECRET_WEBHOOK_KEY")
    if not key:
        log.error("No API key (use --api-key or SCRAPER_API_KEY).")
        return None
    headers["x-api-key"] = key

    total = 0
    for i in range(0, len(payload_leads), CHUNK):
        data = json.dumps({"leads": payload_leads[i:i + CHUNK]}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                total += body.get("total", body.get("count", min(CHUNK, len(payload_leads) - i)))
                log.info(f"  chunk {i // CHUNK + 1}: {body}")
        except urllib.error.HTTPError as e:
            log.error(f"Sync failed with HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}")
            return None
        except Exception as e:
            log.error(f"Sync request failed: {e}")
            return None
    return total


def main():
    parser = argparse.ArgumentParser(description="Sync USA Home Listings to ATM Scheduler")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND, help="Base URL of ATM Scheduler backend")
    parser.add_argument("--api-key", default=None, help="Scraper API key (SCRAPER_API_KEY)")
    parser.add_argument("--limit", type=int, default=50000, help="Max leads to fetch from local SQLite")
    args = parser.parse_args()

    leads = fetch_local_leads(args.limit)
    log.info(f"Loaded {len(leads)} leads from local SQLite database.")
    synced = sync_to_scheduler(args.backend_url, leads, api_key=args.api_key)
    if synced is None:
        return 1
    log.info(f"Done. {synced} leads synced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
