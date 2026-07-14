"""
collectors/run_all.py — Orchestrates all data collectors in sequence.

Run manually:    python collectors/run_all.py
With dry-run:    python collectors/run_all.py --dry-run
"""

import argparse
import logging
import sys
import time
import pathlib
from datetime import datetime

# Make root importable from any working directory
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from database.db_setup import get_connection, create_tables
from database.models import log_scrape

# ── Logging setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("collector.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("run_all")


def run_collector(name: str, fn, dry_run: bool) -> dict:
    """Run a single collector function and return a status dict."""
    log.info(f"▶  Starting collector: {name}")
    start = time.time()
    result = {"source": name, "status": "success", "records": 0, "error": None}
    try:
        if dry_run:
            log.info(f"   [DRY RUN] Skipping actual scrape for {name}")
            result["records"] = 0
        else:
            records_written = fn()
            result["records"] = records_written or 0
        elapsed = round(time.time() - start, 2)
        log.info(f"✅ {name} completed in {elapsed}s — {result['records']} records written")
        log_scrape(name, "success", result["records"], duration_sec=elapsed)
    except Exception as exc:
        elapsed = round(time.time() - start, 2)
        result["status"] = "failed"
        result["error"] = str(exc)
        log.error(f"❌ {name} FAILED after {elapsed}s: {exc}")
        log_scrape(name, "failed", 0, error_msg=str(exc), duration_sec=elapsed)
    return result


def _execute_collectors(collectors: list, dry_run: bool) -> list:
    if not collectors:
        return []
    
    conn = get_connection()
    create_tables(conn)
    conn.close()

    results = []
    for name, fn in collectors:
        results.append(run_collector(name, fn, dry_run))
        time.sleep(1)
    
    return results

def run_real_estate(dry_run: bool = False):
    log.info("=== Starting Real Estate Daily Collection ===")
    from collectors.usahomelistings_scraper import run as mls_run
    
    collectors = [
        ("USA Home Listings (Pre-Mover Leads)", mls_run),
    ]
    return _execute_collectors(collectors, dry_run)

def run_self_storage(dry_run: bool = False):
    log.info("=== Starting Self-Storage Collection (Every 3 Days) ===")
    from collectors.google_maps_collector import run as google_maps_run
    from collectors.sparefoot_scraper import run as sparefoot_run
    from collectors.public_storage_scraper import run as ps_run
    from collectors.extra_space_scraper import run as es_run
    
    collectors = [
        ("Google Maps Discovery", google_maps_run),
        ("SpareFoot Aggregator", sparefoot_run),
        ("Public Storage Direct", ps_run),
        ("Extra Space Direct", es_run),
    ]
    return _execute_collectors(collectors, dry_run)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target", choices=["all", "real_estate", "storage"], default="all")
    args = parser.parse_args()
    
    if args.target in ("all", "real_estate"):
        run_real_estate(dry_run=args.dry_run)
    if args.target in ("all", "storage"):
        run_self_storage(dry_run=args.dry_run)
