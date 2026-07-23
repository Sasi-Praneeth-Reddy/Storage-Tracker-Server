"""
collectors/google_maps_collector.py

Uses the Google Maps Places API (Text Search + Place Details) to discover
self-storage facilities near every ZIP code in config.ALL_ZIP_CODES.

For each ZIP code the module sends:
  1. A Text Search request:  "self storage near {ZIP_CODE}"
     -- pages through up to 3 result pages (~60 results) per ZIP.
  2. A Place Details request for each result to collect phone & website.

All discovered facilities are upserted into the `facilities` table in
storage_tracker.db via database.models.upsert_facility().

Run standalone:
    venv\\Scripts\\python collectors/google_maps_collector.py

Requires:
    pip install requests
"""

import logging
import re
import sys
import time
import pathlib
from datetime import datetime

# -- Allow running as a standalone script from any directory ------
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import (
    GOOGLE_MAPS_API_KEY,
    STORAGE_ZIP_CODES,
    TARGET_BRANDS as STORAGE_BRANDS,   # config exposes it as TARGET_BRANDS
    SCRAPE_DELAY_SECONDS,
)
from database.db_setup import get_connection, create_tables
from database.models import upsert_facility, log_scrape

# ================================================================
# LOGGING
# ================================================================

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ================================================================
# CONSTANTS
# ================================================================

TEXT_SEARCH_URL  = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACE_DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Place Details fields requested (each field adds quota cost)
DETAIL_FIELDS = "formatted_phone_number,website"

# Small pause between individual Place Details calls (seconds)
_DETAIL_DELAY = 0.25

# Placeholder value that signals the key has NOT been set
_API_KEY_PLACEHOLDER = "your_google_maps_api_key_here"


# ================================================================
# BRAND DETECTION
# ================================================================

def detect_brand(facility_name: str) -> str:
    """
    Match facility_name against every brand in STORAGE_BRANDS using a
    case-insensitive substring check.  Returns the matched brand string,
    or 'Independent' when no brand matches.
    """
    name_lower = facility_name.lower()
    for brand in STORAGE_BRANDS:
        if brand.lower() in name_lower:
            return brand
    return "Independent"


# ================================================================
# ADDRESS PARSING
# ================================================================

# Pattern for typical Google formatted_address:
#   "123 Main St, Springfield, VA 22150, USA"
_ADDR_RE = re.compile(
    r"^(?P<street>.+?),\s*"
    r"(?P<city>[^,]+),\s*"
    r"(?P<state>[A-Z]{2})\s+"
    r"(?P<zip>\d{5}(?:-\d{4})?)",
    re.IGNORECASE,
)


def parse_address(formatted_address: str) -> dict:
    """
    Split a Google formatted_address string into component parts.

    Returns a dict with keys: address, city, state, zip_code.
    Falls back to storing the full string in 'address' when the regex
    does not match (e.g., international or malformed addresses).
    """
    m = _ADDR_RE.match(formatted_address or "")
    if m:
        return {
            "address":  m.group("street").strip(),
            "city":     m.group("city").strip(),
            "state":    m.group("state").strip().upper(),
            "zip_code": m.group("zip")[:5],
        }
    return {
        "address":  (formatted_address or "").strip(),
        "city":     "",
        "state":    "",
        "zip_code": "",
    }


# ================================================================
# HTTP HELPER
# ================================================================

def _get(url: str, params: dict, label: str) -> dict | None:
    """
    Execute a single GET request against the Google Maps API.

    - On HTTP 429 (quota exceeded): logs a warning, waits 60 seconds,
      then retries once.
    - On any other non-200 status: logs a warning and returns None.
    - On network or JSON errors: logs a warning and returns None.

    Returns the parsed JSON dict on success, None on any failure.
    """
    try:
        import requests
    except ImportError:
        log.error(
            "The 'requests' library is required but not installed. "
            "Run:  pip install requests"
        )
        return None

    for attempt in (1, 2):
        try:
            resp = requests.get(url, params=params, timeout=15)
        except Exception as exc:
            log.warning("[%s] Network error (attempt %d): %s", label, attempt, exc)
            return None

        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception as exc:
                log.warning("[%s] JSON decode error: %s", label, exc)
                return None

        if resp.status_code == 429:
            if attempt == 1:
                log.warning(
                    "[%s] HTTP 429 -- Google Maps API quota exceeded. "
                    "Waiting 60 seconds before retry...",
                    label,
                )
                time.sleep(60)
                continue  # retry
            else:
                log.error(
                    "[%s] HTTP 429 on retry -- quota still exceeded. "
                    "Aborting this request.",
                    label,
                )
                return None

        # Any other non-200 status
        log.warning(
            "[%s] Unexpected HTTP %d: %s",
            label, resp.status_code, resp.text[:200],
        )
        return None

    return None


# ================================================================
# GOOGLE MAPS API WRAPPERS
# ================================================================

def text_search(query: str) -> list:
    """
    Call the Places Text Search API for the given query string.

    Pages through results automatically (up to 3 pages / ~60 results).
    Google requires a 2-second pause before requesting the next page token.

    Returns a flat list of raw Google place dicts.
    """
    params   = {"query": query, "key": GOOGLE_MAPS_API_KEY}
    all_results = []
    page_num = 1

    while True:
        data = _get(TEXT_SEARCH_URL, params, "TextSearch")
        if not data:
            break

        status = data.get("status", "UNKNOWN")
        if status == "ZERO_RESULTS":
            log.debug("TextSearch: zero results for '%s'", query)
            break
        if status not in ("OK",):
            log.warning(
                "TextSearch API returned status '%s' for query '%s'",
                status, query,
            )
            break

        batch = data.get("results", [])
        all_results.extend(batch)
        log.debug(
            "TextSearch page %d: %d result(s) (running total: %d)",
            page_num, len(batch), len(all_results),
        )

        next_token = data.get("next_page_token")
        if not next_token:
            break

        # Google mandates a short delay before using next_page_token
        time.sleep(2)
        params   = {"pagetoken": next_token, "key": GOOGLE_MAPS_API_KEY}
        page_num += 1

    return all_results


def fetch_place_details(place_id: str) -> dict:
    """
    Call the Place Details API to retrieve phone number and website for
    a single place_id.

    Returns a dict with keys 'phone' and 'website'.
    Both default to an empty string if the API call fails or the field
    is absent from the response.
    """
    params = {
        "place_id": place_id,
        "fields":   DETAIL_FIELDS,
        "key":      GOOGLE_MAPS_API_KEY,
    }
    data = _get(PLACE_DETAIL_URL, params, "PlaceDetails")
    if not data or data.get("status") != "OK":
        return {"phone": "", "website": ""}

    result = data.get("result", {})
    return {
        "phone":   result.get("formatted_phone_number", ""),
        "website": result.get("website", ""),
    }


# ================================================================
# DATABASE HELPER
# ================================================================

def _facility_exists(place_id: str) -> bool:
    """
    Return True if a row with this google_place_id already exists in the
    facilities table (i.e., the facility is not new to us).
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM facilities WHERE google_place_id = ?",
            (place_id,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


# ================================================================
# PER-ZIP COLLECTION
# ================================================================

def collect_for_zip(zip_code: str) -> int:
    """
    Search for self-storage facilities near zip_code, fetch details for
    each result, and upsert them into the facilities table.

    Returns the count of facilities that were NEWLY inserted (not
    previously present in the database).
    """
    query = "self storage near {}".format(zip_code)
    log.info("  Searching: '%s'", query)

    places = text_search(query)
    if not places:
        log.debug("  ZIP %s: no results.", zip_code)
        return 0

    log.info("  ZIP %s: %d candidate(s) returned.", zip_code, len(places))
    new_count = 0

    for place in places:
        place_id = place.get("place_id", "")
        if not place_id:
            continue

        # Check existence BEFORE upsert so we can report new vs updated
        is_new = not _facility_exists(place_id)

        # -- Core fields from Text Search response --------------------
        name           = (place.get("name") or "").strip()
        formatted_addr = place.get("formatted_address", "")
        addr_parts     = parse_address(formatted_addr)
        geometry       = place.get("geometry", {}).get("location", {})
        lat            = geometry.get("lat")
        lng            = geometry.get("lng")
        rating         = place.get("rating")
        review_count   = place.get("user_ratings_total")

        # -- Fetch phone & website from Place Details -----------------
        time.sleep(_DETAIL_DELAY)
        details = fetch_place_details(place_id)

        # -- Brand detection ------------------------------------------
        brand = detect_brand(name)

        # -- Build payload matching database.models.upsert_facility() -
        # Note: the facilities schema column is `lon` (not `lng`)
        facility_data = {
            "google_place_id": place_id,
            "name":            name,
            "brand":           brand,
            "address":         addr_parts["address"],
            "city":            addr_parts["city"],
            "state":           addr_parts["state"],
            "zip_code":        addr_parts["zip_code"] or zip_code,
            "lat":             lat,
            "lon":             lng,
            "phone":           details["phone"],
            "website":         details["website"],
            "google_rating":   rating,
            "google_reviews":  review_count,
        }

        try:
            upsert_facility(facility_data)
        except Exception as exc:
            log.warning("  Could not save '%s' (place_id=%s): %s", name, place_id, exc)
            continue

        if is_new:
            new_count += 1
            log.info(
                "  [NEW]  %-45s | %-20s | %s",
                name[:45], addr_parts.get("city", "")[:20], brand,
            )
        else:
            log.debug(
                "  [UPD]  %-45s | %s",
                name[:45], addr_parts.get("city", ""),
            )

    return new_count


# ================================================================
# PUBLIC ENTRY POINT
# ================================================================

def run() -> int:
    """
    Main synchronous entry point called by collectors/run_all.py.

    Iterates all ZIP codes in config.ALL_ZIP_CODES, searches Google Maps
    for 'self storage near {ZIP}', fetches place details, and persists
    everything to the facilities table.

    Returns the total count of NEW facilities inserted this run
    (updated/unchanged facilities do NOT count).
    """
    # -- Guard: skip gracefully when the API key is missing ---------
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY == _API_KEY_PLACEHOLDER:
        log.warning(
            "GOOGLE_MAPS_API_KEY is not configured (empty or placeholder). "
            "Add it to your .env file and re-run. Skipping collection."
        )
        return 0

    start       = time.time()
    total_new   = 0
    total_zips  = len(STORAGE_ZIP_CODES)

    log.info("=" * 60)
    log.info("Google Maps collector starting.")
    log.info("ZIP codes to search : %d", total_zips)
    log.info("Delay between ZIPs  : %ss", SCRAPE_DELAY_SECONDS)
    log.info("=" * 60)

    for idx, zip_code in enumerate(STORAGE_ZIP_CODES, start=1):
        log.info("-- [%d/%d] ZIP %s", idx, total_zips, zip_code)
        try:
            new_count  = collect_for_zip(zip_code)
            total_new += new_count
            log.info("     New facilities this ZIP: %d", new_count)
        except Exception as exc:
            log.error(
                "Unhandled error for ZIP %s: %s",
                zip_code, exc, exc_info=True,
            )

        # Polite rate-limit delay between ZIP-level requests
        if idx < total_zips:
            time.sleep(SCRAPE_DELAY_SECONDS)

    elapsed = round(time.time() - start, 2)
    log.info("=" * 60)
    log.info(
        "Google Maps collection complete. "
        "New facilities: %d | ZIPs searched: %d | Elapsed: %ss",
        total_new, total_zips, elapsed,
    )
    log.info("=" * 60)
    return total_new


# ================================================================
# STANDALONE TEST
# ================================================================

if __name__ == "__main__":
    # Ensure all DB tables exist before the first run
    _conn = get_connection()
    create_tables(_conn)
    _conn.close()

    _start = time.time()
    try:
        _count   = run()
        _elapsed = round(time.time() - _start, 2)
        log_scrape(
            source          = "google_maps_collector",
            status          = "success",
            records_written = _count,
            duration_sec    = _elapsed,
        )
        log.info("Standalone run finished. New facilities saved: %d", _count)
    except Exception as _exc:
        _elapsed = round(time.time() - _start, 2)
        log.error("Standalone run failed: %s", _exc, exc_info=True)
        log_scrape(
            source          = "google_maps_collector",
            status          = "failed",
            records_written = 0,
            error_msg       = str(_exc),
            duration_sec    = _elapsed,
        )
        sys.exit(1)
