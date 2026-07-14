"""
collectors/sparefoot_scraper.py

Scrapes self-storage facility listings and unit pricing from SpareFoot
(sparefoot.com) using Playwright (headless Chromium).

For each ZIP code in config.ALL_ZIP_CODES (up to MAX_ZIPS_PER_RUN per
execution), the scraper:
  1. Navigates to https://www.sparefoot.com/self-storage/search/{ZIP}/
  2. Collects every visible facility card on the results page.
  3. Extracts: facility name, address, ZIP, phone, website URL, unit sizes
     and advertised prices.
  4. Upserts facilities into the `facilities` table.
  5. Inserts pricing rows into the `pricing_snapshots` table.
  6. Logs the run result to the `scrape_log` table via log_scrape().

Run standalone:
    venv\\Scripts\\python collectors/sparefoot_scraper.py

Called by run_all.py via the synchronous run() function.
"""

import asyncio
import logging
import re
import sys
import time
import pathlib
from datetime import datetime

# ── Path bootstrap so this script is importable from any cwd ─────
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import ALL_ZIP_CODES, SCRAPE_DELAY_SECONDS
from database.db_setup import get_connection, create_tables
from database.models import log_scrape

# ── Module-level logger ──────────────────────────────────────────
log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

# ── Constants ────────────────────────────────────────────────────
SOURCE_NAME      = "sparefoot"
BASE_SEARCH_URL  = "https://www.sparefoot.com/self-storage/search/{}/"

# Only process this many ZIP codes per execution to avoid rate-limiting.
MAX_ZIPS_PER_RUN = 10

# Standard unit sizes the project tracks (from config.UNIT_SIZES).
TARGET_UNIT_SIZES = ["5x5", "5x10", "10x10", "10x15", "10x20"]

# User-agent string -- matches the one used elsewhere in the project.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Ordered CSS selector chains for graceful-degradation field extraction.
FACILITY_CARD_SELECTORS = [
    ".facility-card",
    "[data-testid='facility-card']",
    ".storage-facility",
    "[class*='facility']",
    "[class*='FacilityCard']",
    ".search-result",
    "[class*='result-item']",
    "[class*='ResultCard']",
]

NAME_SELECTORS = [
    "h2",
    ".facility-name",
    "[class*='name']",
    "[class*='Name']",
    "h3",
    "h1",
]

ADDRESS_SELECTORS = [
    ".address",
    "[class*='address']",
    "[class*='Address']",
    "[itemprop='streetAddress']",
    ".location",
    "[class*='location']",
]

PRICE_SELECTORS = [
    ".price",
    "[class*='price']",
    "[class*='Price']",
    ".from-price",
    "[class*='from-price']",
    "[class*='rate']",
    "[class*='Rate']",
]

UNIT_SIZE_SELECTORS = [
    ".unit-size",
    "[class*='size']",
    "[class*='Size']",
    ".unit-type",
    "[class*='unit-type']",
    "[class*='UnitSize']",
    "[class*='dimension']",
]

PHONE_SELECTORS = [
    "[href^='tel:']",
    ".phone",
    "[class*='phone']",
    "[class*='Phone']",
    "[itemprop='telephone']",
]

WEBSITE_SELECTORS = [
    "a[href*='http'][class*='website']",
    "a[class*='website']",
    ".website a",
    "a[rel='noopener']",
]


# ================================================================
# DATABASE HELPERS
# ================================================================

def _upsert_facility_sparefoot(data: dict) -> int:
    """
    Insert or update a SpareFoot facility using a name+address composite key
    (SpareFoot does not expose Google Place IDs).

    Returns the facility row ID.
    """
    conn = get_connection()
    now  = datetime.utcnow().isoformat()
    try:
        cur = conn.cursor()

        # Check whether we already have this facility by name + address.
        cur.execute(
            "SELECT id FROM facilities WHERE name = ? AND address = ?",
            (data["name"], data["address"]),
        )
        row = cur.fetchone()

        if row:
            # Update mutable fields on an existing record.
            cur.execute(
                """
                UPDATE facilities
                SET phone        = ?,
                    website      = ?,
                    zip_code     = ?,
                    last_updated = ?
                WHERE id = ?
                """,
                (
                    data.get("phone"),
                    data.get("website"),
                    data.get("zip_code"),
                    now,
                    row["id"],
                ),
            )
            conn.commit()
            return row["id"]

        # New facility -- insert with a NULL google_place_id.
        cur.execute(
            """
            INSERT INTO facilities
                (google_place_id, name, brand, address, city, state,
                 zip_code, lat, lon, phone, website,
                 google_rating, google_reviews, last_updated)
            VALUES
                (NULL, :name, :brand, :address, :city, :state,
                 :zip_code, :lat, :lon, :phone, :website,
                 NULL, NULL, :last_updated)
            """,
            {**data, "last_updated": now},
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _insert_pricing(
    facility_id: int,
    unit_size: str,
    web_rate,
    street_rate,
    unit_type,
    availability: str,
) -> None:
    """Insert one pricing_snapshots row."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO pricing_snapshots
                (facility_id, unit_size, unit_type, street_rate,
                 web_rate, availability, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                facility_id,
                unit_size,
                unit_type,
                street_rate,
                web_rate,
                availability,
                SOURCE_NAME,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ================================================================
# TEXT PARSING HELPERS
# ================================================================

def _extract_price(text: str):
    """
    Parse the first dollar-amount found in *text* and return it as a float.
    Handles patterns like '$79', '$1,250/mo', 'from $99/month', etc.
    Returns None when no price is found.
    """
    match = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_unit_size(text: str):
    """
    Find a storage unit dimension like '10x10', '5 x 5', '10 X 20' in *text*.
    Normalises the result to lowercase with no spaces (e.g. '10x10').
    Returns None when no match is found.
    """
    match = re.search(r"(\d+)\s*[xX]\s*(\d+)", text)
    if not match:
        return None
    return "{}x{}".format(match.group(1), match.group(2))


def _normalise_zip(text: str):
    """Extract the first 5-digit ZIP code from a string."""
    match = re.search(r"\b(\d{5})\b", text)
    return match.group(1) if match else None


def _normalise_phone(text: str):
    """Extract and normalise the first phone number from a string."""
    # Strip tel: prefix if present.
    text = re.sub(r"^tel:", "", text.strip(), flags=re.IGNORECASE)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10:
        return "({}) {}-{}".format(digits[:3], digits[3:6], digits[6:])
    if len(digits) == 11 and digits[0] == "1":
        return "({}) {}-{}".format(digits[1:4], digits[4:7], digits[7:])
    return text.strip() if text.strip() else None


# ================================================================
# PLAYWRIGHT PAGE-LEVEL HELPERS
# ================================================================

async def _safe_text(element, selectors: list) -> str:
    """
    Try each CSS selector against *element* in order.
    Returns the first non-empty inner_text, or an empty string.
    """
    for sel in selectors:
        try:
            child = await element.query_selector(sel)
            if child:
                txt = (await child.inner_text()).strip()
                if txt:
                    return txt
        except Exception:
            pass
    return ""


async def _safe_attr(element, selectors: list, attr: str) -> str:
    """
    Try each CSS selector against *element* in order, returning *attr*.
    Returns an empty string when nothing matches.
    """
    for sel in selectors:
        try:
            child = await element.query_selector(sel)
            if child:
                val = await child.get_attribute(attr)
                if val and val.strip():
                    return val.strip()
        except Exception:
            pass
    return ""


async def _take_debug_screenshot(page, tag: str) -> None:
    """Save a PNG for post-mortem debugging."""
    folder = pathlib.Path("debug_screenshots")
    folder.mkdir(exist_ok=True)
    fname = folder / "sparefoot_{}_{}.png".format(
        tag, datetime.now().strftime("%H%M%S")
    )
    try:
        await page.screenshot(path=str(fname), full_page=True)
        log.info("Debug screenshot saved: %s", fname)
    except Exception as exc:
        log.debug("Could not save screenshot '%s': %s", fname, exc)


# ================================================================
# FACILITY CARD PARSER
# ================================================================

async def _parse_facility_card(card, search_zip: str) -> dict:
    """
    Extract all available fields from a single facility card element.

    Returns a dict with keys:
        name, address, city, state, zip_code, phone, website, brand,
        lat, lon, units  (list of unit dicts)
    """
    result = {
        "name":     "",
        "address":  "",
        "city":     "",
        "state":    "",
        "zip_code": search_zip,
        "phone":    None,
        "website":  None,
        "brand":    None,
        "lat":      None,
        "lon":      None,
        "units":    [],
    }

    try:
        # ── Facility name ────────────────────────────────────────
        result["name"] = await _safe_text(card, NAME_SELECTORS)

        # ── Address ──────────────────────────────────────────────
        address_raw = await _safe_text(card, ADDRESS_SELECTORS)
        if address_raw:
            result["address"] = address_raw

            # Parse city / state / ZIP from address string.
            # Typical SpareFoot format: "123 Main St, Springfield, VA 22150"
            addr_match = re.search(
                r"(.+?),\s*([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})",
                address_raw,
            )
            if addr_match:
                result["city"]     = addr_match.group(2).strip()
                result["state"]    = addr_match.group(3).strip()
                result["zip_code"] = addr_match.group(4).strip()
            else:
                z = _normalise_zip(address_raw)
                if z:
                    result["zip_code"] = z

        # ── Phone ────────────────────────────────────────────────
        phone_href = await _safe_attr(card, ["[href^='tel:']"], "href")
        if phone_href:
            result["phone"] = _normalise_phone(phone_href)
        else:
            phone_text = await _safe_text(card, PHONE_SELECTORS)
            if phone_text:
                result["phone"] = _normalise_phone(phone_text)

        # ── Website ──────────────────────────────────────────────
        website = await _safe_attr(card, WEBSITE_SELECTORS, "href")
        if website and "sparefoot.com" not in website:
            result["website"] = website

        # ── Unit / pricing blocks ────────────────────────────────
        await _extract_unit_pricing(card, result)

    except Exception as exc:
        log.warning("Error parsing facility card: %s", exc)

    return result


async def _extract_unit_pricing(card, result: dict) -> None:
    """
    Scan *card* for unit size + price pairs.
    Populates result["units"] in-place.

    Strategy A: structured unit-row elements (preferred).
    Strategy B: full-card text regex scan (fallback).
    """
    found_units = {}   # size -> unit dict (deduplicates by size)

    # ── Strategy A: per-unit row elements ──────────────────────
    unit_row_selectors = [
        ".unit-row",
        "[class*='unit-row']",
        "[class*='UnitRow']",
        ".unit-listing",
        "[class*='unit-listing']",
        ".storage-unit",
        "[class*='storage-unit']",
        "[class*='StorageUnit']",
        "li[class*='unit']",
        "tr[class*='unit']",
    ]

    unit_rows = []
    for sel in unit_row_selectors:
        try:
            rows = await card.query_selector_all(sel)
            if rows:
                unit_rows = rows
                break
        except Exception:
            pass

    for row in unit_rows:
        try:
            row_text = await row.inner_text()
            size = _extract_unit_size(row_text)
            if not size or size not in TARGET_UNIT_SIZES:
                continue
            price = _extract_price(row_text)

            avail      = "available"
            text_lower = row_text.lower()
            if "call" in text_lower or "waitlist" in text_lower:
                avail = "waitlist"
            elif "limited" in text_lower or "hurry" in text_lower:
                avail = "limited"
            elif "unavailable" in text_lower or "sold out" in text_lower:
                avail = "unavailable"

            unit_type = None
            for kw, label in [
                ("climate", "Climate Controlled"),
                ("indoor",  "Indoor"),
                ("drive",   "Drive-Up"),
                ("outdoor", "Outdoor"),
                ("vehicle", "Vehicle"),
                ("boat",    "Boat/RV"),
            ]:
                if kw in text_lower:
                    unit_type = label
                    break

            if size not in found_units:
                found_units[size] = {
                    "size":         size,
                    "web_rate":     price,
                    "street_rate":  None,
                    "unit_type":    unit_type,
                    "availability": avail,
                }
        except Exception:
            pass

    # ── Strategy B: full-card text regex scan (fallback) ────────
    if not found_units:
        try:
            card_text = await card.inner_text()
            for m in re.finditer(r"(\d+)\s*[xX]\s*(\d+)", card_text):
                size = "{}x{}".format(m.group(1), m.group(2))
                if size not in TARGET_UNIT_SIZES or size in found_units:
                    continue

                # Search a 120-char window after the size mention for a price.
                window_end = min(len(card_text), m.end() + 120)
                excerpt    = card_text[m.start():window_end]
                price      = _extract_price(excerpt)

                avail      = "available"
                text_lower = excerpt.lower()
                if "call" in text_lower or "waitlist" in text_lower:
                    avail = "waitlist"
                elif "limited" in text_lower or "hurry" in text_lower:
                    avail = "limited"
                elif "unavailable" in text_lower or "sold out" in text_lower:
                    avail = "unavailable"

                unit_type = None
                for kw, label in [
                    ("climate", "Climate Controlled"),
                    ("indoor",  "Indoor"),
                    ("drive",   "Drive-Up"),
                    ("outdoor", "Outdoor"),
                ]:
                    if kw in text_lower:
                        unit_type = label
                        break

                found_units[size] = {
                    "size":         size,
                    "web_rate":     price,
                    "street_rate":  None,
                    "unit_type":    unit_type,
                    "availability": avail,
                }

        except Exception as exc:
            log.debug("Strategy B card text scan failed: %s", exc)

    result["units"] = list(found_units.values())


# ================================================================
# PER-ZIP SCRAPE FUNCTION
# ================================================================

async def scrape_zip(page, zip_code: str) -> list:
    """
    Scrape facility data for one ZIP code from SpareFoot.
    Returns a list of facility dicts (each with a 'units' list).
    """
    url = BASE_SEARCH_URL.format(zip_code)
    log.info("  Scraping ZIP %s -> %s", zip_code, url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        log.warning("  [%s] Page load failed: %s", zip_code, exc)
        return []

    # Allow JS-rendered content time to settle.
    await page.wait_for_timeout(3000)

    # ── Find facility card elements ──────────────────────────────
    cards = []
    for sel in FACILITY_CARD_SELECTORS:
        try:
            cards = await page.query_selector_all(sel)
            if cards:
                log.info(
                    "  [%s] Found %d cards using selector: %s",
                    zip_code, len(cards), sel,
                )
                break
        except Exception:
            pass

    if not cards:
        log.info(
            "  [%s] No facility cards found -- page may use different markup.",
            zip_code,
        )
        await _take_debug_screenshot(page, "no_cards_{}".format(zip_code))
        return []

    facilities = []
    for i, card in enumerate(cards, start=1):
        try:
            facility = await _parse_facility_card(card, zip_code)
            if not facility["name"]:
                log.debug("  [%s] Card %d has no name -- skipping.", zip_code, i)
                continue
            facilities.append(facility)
            log.debug(
                "  [%s] Card %d: %s (%d unit entries)",
                zip_code, i, facility["name"], len(facility["units"]),
            )
        except Exception as exc:
            log.warning("  [%s] Error parsing card %d: %s", zip_code, i, exc)

    return facilities


# ================================================================
# MAIN ASYNC ENTRY POINT
# ================================================================

async def run_async() -> int:
    """
    Iterate over up to MAX_ZIPS_PER_RUN ZIP codes, scrape SpareFoot for each,
    persist results to the database, and return total pricing rows written.
    """
    from playwright.async_api import async_playwright

    zip_codes = ALL_ZIP_CODES[:MAX_ZIPS_PER_RUN]
    log.info(
        "SpareFoot scraper starting. Processing %d of %d total ZIPs.",
        len(zip_codes), len(ALL_ZIP_CODES),
    )

    records_written = 0
    start_time      = time.time()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
            java_script_enabled=True,
            locale="en-US",
        )
        page = await context.new_page()

        # Block images and fonts to reduce bandwidth and speed up loads.
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font")
            else route.continue_(),
        )

        try:
            for idx, zip_code in enumerate(zip_codes, start=1):
                log.info(
                    "Processing ZIP %s (%d/%d)...",
                    zip_code, idx, len(zip_codes),
                )

                facilities = await scrape_zip(page, zip_code)
                log.info(
                    "  ZIP %s: %d facilities found.",
                    zip_code, len(facilities),
                )

                for fac in facilities:
                    if not fac.get("name"):
                        continue

                    try:
                        fac_id = _upsert_facility_sparefoot({
                            "name":     fac["name"],
                            "brand":    fac.get("brand"),
                            "address":  fac.get("address", ""),
                            "city":     fac.get("city", ""),
                            "state":    fac.get("state", ""),
                            "zip_code": fac.get("zip_code", zip_code),
                            "lat":      fac.get("lat"),
                            "lon":      fac.get("lon"),
                            "phone":    fac.get("phone"),
                            "website":  fac.get("website"),
                        })
                    except Exception as exc:
                        log.error(
                            "  Failed to upsert facility '%s': %s",
                            fac["name"], exc,
                        )
                        continue

                    for unit in fac.get("units", []):
                        try:
                            _insert_pricing(
                                facility_id=fac_id,
                                unit_size=unit["size"],
                                web_rate=unit.get("web_rate"),
                                street_rate=unit.get("street_rate"),
                                unit_type=unit.get("unit_type"),
                                availability=unit.get("availability", "available"),
                            )
                            records_written += 1
                        except Exception as exc:
                            log.error(
                                "  Failed to insert pricing for '%s' %s: %s",
                                fac["name"], unit["size"], exc,
                            )

                # Polite delay between ZIP requests.
                if idx < len(zip_codes):
                    log.debug(
                        "  Sleeping %ss before next ZIP...", SCRAPE_DELAY_SECONDS
                    )
                    await asyncio.sleep(SCRAPE_DELAY_SECONDS)

        except Exception as exc:
            log.error("Unexpected scraper error: %s", exc, exc_info=True)
            await _take_debug_screenshot(page, "fatal_error")
        finally:
            await browser.close()

    elapsed = round(time.time() - start_time, 2)
    log.info(
        "SpareFoot scraper done. %d pricing rows written in %ss.",
        records_written, elapsed,
    )
    return records_written


# ================================================================
# PUBLIC SYNC WRAPPER  (called by collectors/run_all.py)
# ================================================================

def run() -> int:
    """
    Synchronous wrapper called by collectors/run_all.py.
    Returns the number of pricing_snapshot rows written.
    """
    start   = time.time()
    records = 0
    try:
        records = asyncio.run(run_async())
        log_scrape(
            source=SOURCE_NAME,
            status="success",
            records_written=records,
            duration_sec=round(time.time() - start, 2),
        )
    except Exception as exc:
        log.error("SpareFoot run() failed: %s", exc, exc_info=True)
        log_scrape(
            source=SOURCE_NAME,
            status="failed",
            records_written=records,
            error_msg=str(exc),
            duration_sec=round(time.time() - start, 2),
        )
    return records


# ================================================================
# STANDALONE TEST  (python collectors/sparefoot_scraper.py)
# ================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  SpareFoot Self-Storage Scraper -- standalone test")
    print("  ZIPs to process this run: {}".format(MAX_ZIPS_PER_RUN))
    print("  Delay between ZIPs      : {}s".format(SCRAPE_DELAY_SECONDS))
    print("=" * 60)

    # Ensure DB schema exists before writing any records.
    _conn = get_connection()
    create_tables(_conn)
    _conn.close()

    count = run()

    print("-" * 60)
    print("Scraper complete.")
    print("Pricing rows written : {}".format(count))
    print("Results saved to     : storage_tracker.db")
    print("=" * 60)
