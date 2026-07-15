"""
collectors/usahomelistings_scraper.py

Logs into get.usahomelistings.com using Playwright and scrapes
daily home listing leads (new listings + under contract) by ZIP code.

These are pre-mover leads -- homeowners who just listed or are
under contract, meaning they'll need movers/storage soon.

Data stored in: mls_market_data and a new leads table.
Run: venv\\Scripts\\python collectors/usahomelistings_scraper.py
"""

import asyncio
import logging
import re
import sys
import time
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import (
    USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD,
    SCRAPE_DELAY_SECONDS, ALL_ZIP_CODES
)
from database.db_setup import get_connection, create_tables
from database.models import log_scrape

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

LOGIN_URL     = "https://get.usahomelistings.com/login"
PORTAL_BASE   = "https://get.usahomelistings.com/portal"
LISTINGS_URL  = PORTAL_BASE + "/page/listings_data"   # confirmed by user
API_SUB_URL   = PORTAL_BASE + "/api-subscription"


# ── Database helpers ─────────────────────────────────────────────

def ensure_leads_table():
    """Create the pre_mover_leads table if it doesn't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pre_mover_leads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            address       TEXT,
            city          TEXT,
            state         TEXT,
            zip_code      TEXT,
            status        TEXT,    -- 'for_sale', 'under_contract', 'pending'
            list_price    REAL,
            bedrooms      INTEGER,
            bathrooms     REAL,
            sqft          INTEGER,
            is_vacant     INTEGER DEFAULT 0,  -- Vacancy AI flag
            listed_date   TEXT,
            source_id     TEXT,   -- portal's internal ID
            scraped_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(source_id, scraped_at)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_zip_date
            ON pre_mover_leads(zip_code, scraped_at)
    """)
    conn.commit()
    conn.close()


def save_lead(lead: dict) -> bool:
    """Insert a lead, skip if already exists for today. Returns True if new."""
    conn = get_connection()
    try:
        today = datetime.utcnow().date().isoformat()
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM pre_mover_leads
            WHERE source_id = ? AND date(scraped_at) = ?
        """, (lead.get("source_id", ""), today))
        if cur.fetchone():
            return False   # already have this lead today
        cur.execute("""
            INSERT OR IGNORE INTO pre_mover_leads
                (address, city, state, zip_code, status,
                 list_price, bedrooms, bathrooms, sqft,
                 is_vacant, listed_date, source_id)
            VALUES
                (:address, :city, :state, :zip_code, :status,
                 :list_price, :bedrooms, :bathrooms, :sqft,
                 :is_vacant, :listed_date, :source_id)
        """, lead)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def save_mls_summary(zip_code: str, for_sale: int, under_contract: int):
    """Save a market data summary row for this ZIP code."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO mls_market_data
                (zip_code, active_listings, new_listings_30d, source)
            VALUES (?, ?, ?, 'usahomelistings')
        """, (zip_code, for_sale, under_contract))
        conn.commit()
    finally:
        conn.close()


# ── Playwright scraper ───────────────────────────────────────────

async def login(page) -> bool:
    """
    Log into the USA Home Listings portal.
    Uses a two-step flow:
      Step 1 -- Enter email, click 'Sign In'
      Step 2 -- Password field appears, enter it, click submit
    Returns True on success.
    """
    log.info("Navigating to login page...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # ── Step 1: Fill email and click Sign In ─────────────────────
    email_sel = 'input[type="email"], input[name="email"], #email'
    await page.wait_for_selector(email_sel, timeout=10000)
    await page.fill(email_sel, USAHOMELISTINGS_EMAIL)
    log.info("Email entered. Clicking Sign In...")

    # Click the first Sign In button (email step)
    step1_btn = 'button[type="submit"], button:has-text("Sign in"), button:has-text("Sign In"), button:has-text("Next"), button:has-text("Continue")'
    await page.click(step1_btn)

    # ── Step 2: Wait for password field, then fill it ─────────────
    log.info("Waiting for password field...")
    pwd_sel = 'input[type="password"]'
    try:
        await page.wait_for_selector(pwd_sel, timeout=15000)
    except Exception:
        # Password field didn't appear -- take screenshot to debug
        await take_debug_screenshot(page, "after_email_step")
        log.error("Password field did not appear after clicking Sign In.")
        return False

    await page.fill(pwd_sel, USAHOMELISTINGS_PASSWORD)
    log.info("Password entered. Submitting...")

    # Click the final submit button
    submit_sel = 'button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Continue")'
    await page.click(submit_sel)
    await page.wait_for_timeout(4000)

    # ── Verify login success ──────────────────────────────────────
    current_url = page.url
    log.info("Post-login URL: %s", current_url)

    if "login" not in current_url and "signin" not in current_url:
        log.info("Login successful!")
        await take_debug_screenshot(page, "login_success")
        return True

    # Check for error message on page
    try:
        error = await page.inner_text('.error, .alert, [class*=error], [class*=alert]', timeout=3000)
        log.error("Login error message: %s", error.strip())
    except Exception:
        pass
    await take_debug_screenshot(page, "login_failed")
    log.error("Login failed. Still on: %s", current_url)
    return False


async def take_debug_screenshot(page, name: str):
    """Save a debug screenshot to help diagnose scraping issues."""
    path = pathlib.Path("debug_screenshots")
    path.mkdir(exist_ok=True)
    filename = path / "{}_{}.png".format(name, datetime.now().strftime("%H%M%S"))
    await page.screenshot(path=str(filename), full_page=True)
    log.info("Screenshot saved: %s", filename)


async def parse_listing_card(card) -> dict:
    """Extract data from a single listing card element."""
    lead = {
        "address": "",
        "city": "",
        "state": "VA",
        "zip_code": "",
        "status": "for_sale",
        "list_price": None,
        "bedrooms": None,
        "bathrooms": None,
        "sqft": None,
        "is_vacant": 0,
        "listed_date": None,
        "source_id": "",
    }

    try:
        # Address -- try common selectors
        for sel in ['.address', '[class*=address]', 'h3', 'h4', '.street']:
            try:
                el = await card.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text.strip():
                        lead["address"] = text.strip()
                        break
            except Exception:
                pass

        # ZIP code -- extract from address or dedicated field
        text_content = await card.inner_text()
        zip_match = re.search(r'\b(\d{5})\b', text_content)
        if zip_match:
            lead["zip_code"] = zip_match.group(1)

        # City
        city_match = re.search(r',\s*([A-Za-z\s]+),\s*[A-Z]{2}\s*\d{5}', text_content)
        if city_match:
            lead["city"] = city_match.group(1).strip()

        # Status -- look for keywords
        text_lower = text_content.lower()
        if "under contract" in text_lower or "pending" in text_lower:
            lead["status"] = "under_contract"
        elif "for sale" in text_lower or "active" in text_lower:
            lead["status"] = "for_sale"

        # Price -- look for $ amounts
        price_match = re.search(r'\$[\d,]+', text_content)
        if price_match:
            price_str = price_match.group(0).replace("$", "").replace(",", "")
            try:
                lead["list_price"] = float(price_str)
            except ValueError:
                pass

        # Bedrooms
        bed_match = re.search(r'(\d+)\s*(?:bd|bed|BR)', text_content, re.IGNORECASE)
        if bed_match:
            lead["bedrooms"] = int(bed_match.group(1))

        # Bathrooms
        bath_match = re.search(r'(\d+\.?\d*)\s*(?:ba|bath|BA)', text_content, re.IGNORECASE)
        if bath_match:
            lead["bathrooms"] = float(bath_match.group(1))

        # Sqft
        sqft_match = re.search(r'([\d,]+)\s*(?:sqft|sq\.?\s*ft)', text_content, re.IGNORECASE)
        if sqft_match:
            lead["sqft"] = int(sqft_match.group(1).replace(",", ""))

        # Vacancy AI flag
        if "vacant" in text_lower or "vacancy" in text_lower:
            lead["is_vacant"] = 1

        # Source ID -- use address as fallback unique key
        lead["source_id"] = lead["address"] or text_content[:80]

    except Exception as exc:
        log.warning("Error parsing card: %s", exc)

    return lead


async def check_api_subscription(page) -> dict:
    """
    Navigate to the API Subscription page in the portal.
    If an API key is available, return it so we can use the API directly
    instead of scraping the UI.
    """
    log.info("Checking API Subscription page...")
    for url in [API_SUB_URL, PORTAL_BASE + "/api", PORTAL_BASE + "/api-keys"]:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            if "not found" not in (await page.title()).lower():
                await take_debug_screenshot(page, "api_subscription_page")
                content = await page.inner_text("body")
                log.info("API Subscription page content (first 500 chars):\n%s", content[:500])
                return {"url": url, "content": content}
        except Exception as exc:
            log.debug("Could not load %s: %s", url, exc)

    # Try clicking the API Subscription sidebar link instead
    try:
        await page.goto(PORTAL_BASE + "/onboarding", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1000)
        # Click "API Subscription" in the sidebar
        api_link = await page.query_selector('a:has-text("API Subscription"), a:has-text("API")')
        if api_link:
            await api_link.click()
            await page.wait_for_timeout(2000)
            await take_debug_screenshot(page, "api_subscription_clicked")
            content = await page.inner_text("body")
            log.info("API page after sidebar click (first 500 chars):\n%s", content[:500])
            return {"url": page.url, "content": content}
    except Exception as exc:
        log.debug("Could not click API Subscription link: %s", exc)

    return {}


async def navigate_to_listings(page) -> bool:
    """
    From the portal dashboard, navigate to the actual listings page
    by clicking the sidebar 'Listings' link or 'GO TO MY LISTINGS' button.
    Returns True if successfully navigated.
    """
    log.info("Navigating to listings via portal sidebar...")
    try:
        await page.goto(PORTAL_BASE + "/onboarding", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
    except Exception as exc:
        log.warning("Could not load portal onboarding: %s", exc)

    # Try clicking 'GO TO MY LISTINGS' button first (visible on dashboard)
    for btn_text in ["GO TO MY LISTINGS", "My Listings", "Go to My Listings"]:
        try:
            btn = await page.query_selector('a:has-text("{}"), button:has-text("{}")'.format(btn_text, btn_text))
            if btn:
                await btn.click()
                await page.wait_for_timeout(3000)
                log.info("Clicked '%s' button. Now at: %s", btn_text, page.url)
                await take_debug_screenshot(page, "after_go_to_listings")
                return True
        except Exception:
            pass

    # Try clicking 'Listings' in the sidebar (it may expand a submenu)
    try:
        listings_link = await page.query_selector(
            'nav a:has-text("Listings"), .sidebar a:has-text("Listings"), '
            'a[href*="listing"], a[href*="service"]'
        )
        if listings_link:
            await listings_link.click()
            await page.wait_for_timeout(3000)
            log.info("Clicked Listings nav link. Now at: %s", page.url)
            await take_debug_screenshot(page, "after_listings_nav")
            return True
    except Exception as exc:
        log.warning("Could not click Listings nav: %s", exc)

    # Try direct portal sub-routes
    for path in ["/services", "/service-listings", "/my-listings",
                 "/leads", "/dashboard", "/home"]:
        try:
            url = PORTAL_BASE + path
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(1000)
            title = await page.title()
            if "not found" not in title.lower() and "404" not in title:
                log.info("Found listings at: %s (title: %s)", url, title)
                await take_debug_screenshot(page, "listings_found_" + path.strip("/"))
                return True
        except Exception:
            pass

    log.warning("Could not navigate to listings page.")
    return False


async def scrape_listings(page) -> list:
    """Navigate to the listings page and extract all property cards."""
    log.info("Starting scrape_listings...")
    leads = []

    # Ensure we are actually on the listings page
    success = await navigate_to_listings(page)
    if not success:
        log.warning("Could not reach listings page. Returning empty list.")
        return leads

    # ── Step 1: The listings page loads data inside a hidden iframe ──
    # We must switch into the iframe's content frame to access the data.
    content_frame = None
    try:
        # The iframe has hidden="" so we must use state='attached' not 'visible'
        await page.wait_for_selector("iframe[src*='portal']", state="attached", timeout=15000)
        iframe_el = await page.query_selector("iframe[src*='portal']")
        if iframe_el:
            content_frame = await iframe_el.content_frame()
            if content_frame:
                log.info("Switched into iframe: %s", content_frame.url)
                # Wait for the iframe's internal page to fully load
                await content_frame.wait_for_load_state("networkidle", timeout=30000)
                await take_debug_screenshot(page, "inside_iframe")
    except Exception as exc:
        log.warning("Could not switch into iframe: %s", exc)

    # Use the iframe frame if we found one, otherwise fall back to main page
    target = content_frame if content_frame else page

    # ── Step 2: Search for listing data inside the (iframe) page ──
    selectors = [
        'table tr',
        '.listing-card', '.property-card',
        '[class*="card"]', '[class*="listing"]',
        '[class*="property"]', '[class*="lead"]',
        '.row', '.item',
    ]
    selector_str = ", ".join(selectors)

    try:
        await target.wait_for_selector(selector_str, timeout=20000)
    except Exception:
        log.warning("No listing elements found inside iframe either.")
        try:
            html = await target.inner_html("body")
            log.warning("IFRAME HTML DUMP (first 3000 chars): %s", html[:3000])
        except Exception:
            log.warning("Could not dump iframe HTML.")
        await take_debug_screenshot(page, "no_cards_in_iframe")
        return leads

    # Extract all matching elements
    cards = await target.query_selector_all(selector_str)
    log.info("Found %d potential listing items.", len(cards))

    for card in cards:
        lead = await parse_listing_card(card)
        if lead and lead.get("address"):
            leads.append(lead)

    return leads


async def run_async() -> int:
    """Main async entry point. Returns number of records written."""
    from playwright.async_api import async_playwright

    if not USAHOMELISTINGS_EMAIL or not USAHOMELISTINGS_PASSWORD:
        log.error("USAHOMELISTINGS_EMAIL / USAHOMELISTINGS_PASSWORD not set in .env")
        return 0

    ensure_leads_table()
    records_written = 0
    start = time.time()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            # Step 1: Login
            logged_in = await login(page)
            if not logged_in:
                log.error("Could not log into USA Home Listings. Check credentials.")
                return 0

            # Step 2: Scrape listings
            leads = await scrape_listings(page)
            log.info("Total leads scraped: %d", len(leads))

            # Step 3: Save to DB
            zip_stats = {}   # zip_code -> {for_sale, under_contract}
            for lead in leads:
                is_new = save_lead(lead)
                if is_new:
                    records_written += 1
                z = lead.get("zip_code", "unknown")
                if z not in zip_stats:
                    zip_stats[z] = {"for_sale": 0, "under_contract": 0}
                if lead["status"] == "under_contract":
                    zip_stats[z]["under_contract"] += 1
                else:
                    zip_stats[z]["for_sale"] += 1

            # Step 4: Save ZIP-level summaries
            for z, stats in zip_stats.items():
                save_mls_summary(z, stats["for_sale"], stats["under_contract"])

            elapsed = round(time.time() - start, 2)
            log.info("Done. %d new leads saved in %ss", records_written, elapsed)
            log.info("ZIP breakdown:")
            for z, s in sorted(zip_stats.items()):
                log.info("  ZIP %s -- For Sale: %d | Under Contract: %d",
                         z, s["for_sale"], s["under_contract"])

        except Exception as exc:
            log.error("Scraper error: %s", exc, exc_info=True)
            await take_debug_screenshot(page, "error_state")
        finally:
            await browser.close()

    return records_written


def run() -> int:
    """Sync wrapper called by run_all.py."""
    return asyncio.run(run_async())


if __name__ == "__main__":
    conn = get_connection()
    create_tables(conn)
    conn.close()
    count = run()
    log.info("USA Home Listings scraper complete. Records: %d", count)
