"""
collectors/portal_exporter.py  (v2 - iframe-aware)

Automated CSV exporter for USA Home Listings portal.
The listings content is rendered inside an iframe - this version
correctly switches into the iframe before interacting with filters/buttons.

Run:
    # Export all (no filter = full ~10K export attempt):
    venv\\Scripts\\python collectors/portal_exporter.py

    # Export by state (smaller files, more reliable):
    venv\\Scripts\\python collectors/portal_exporter.py --by-state

    # Export a single state:
    venv\\Scripts\\python collectors/portal_exporter.py --state Virginia

    # Just import already-downloaded CSVs:
    venv\\Scripts\\python collectors/portal_exporter.py --import-only
"""

import asyncio
import sys
import re
import pathlib
import logging
import argparse
import time
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from config import USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

PORTAL_URL   = "https://get.usahomelistings.com"
LOGIN_URL    = PORTAL_URL + "/login"
LISTINGS_URL = PORTAL_URL + "/portal/page/listings_data"
import tempfile
IMPORT_DIR   = pathlib.Path(tempfile.gettempdir()) / "self_storage_imports"
DEBUG_DIR    = pathlib.Path(__file__).parent.parent / "debug_screenshots"

TARGET_STATES = ["Virginia", "Maryland", "West Virginia"]


# ── Login ─────────────────────────────────────────────────────────

async def login(page):
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    await page.fill('input[type="email"]', USAHOMELISTINGS_EMAIL)
    await page.click('button[type="submit"]')
    await page.wait_for_selector('input[type="password"]', timeout=12000)
    await page.fill('input[type="password"]', USAHOMELISTINGS_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(5000)
    log.info("Logged in: %s", page.url)


# ── Get the listings iframe ───────────────────────────────────────

async def get_listings_frame(page):
    """
    Load the listings page and return the frame containing the actual
    listings content (filter dropdowns + export button).
    The content is inside https://portal.usahomelistings.com/listings/ iframe.
    Returns (frame, is_iframe).
    """
    await page.goto(LISTINGS_URL, wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(4000)

    frames = page.frames
    log.info("Total frames on page: %d", len(frames))
    for f in frames:
        log.info("  Frame: %s", f.url[:100])

    # 1. Prefer frame at portal.usahomelistings.com (confirmed iframe host)
    for frame in frames:
        if "portal.usahomelistings.com/listings" in frame.url:
            log.info("Listings iframe found directly: %s", frame.url[:80])
            return frame, True

    # 2. Fall back: find frame containing the Export button
    for frame in frames:
        try:
            btn = await frame.query_selector(
                'button:has-text("Export"), a:has-text("Export")'
            )
            if btn:
                log.info("Export button found in frame: %s", frame.url[:80])
                return frame, True
        except Exception:
            pass

    # 3. Main page fallback
    log.warning("Listings iframe not found — using main page.")
    return page, False


# ── Dropdown helpers (iframe-aware) ──────────────────────────────

async def click_dropdown_by_index(frame, index: int) -> bool:
    """Click a filter dropdown by its index (0=States, 1=Counties, etc)."""
    multiselects = await frame.query_selector_all('.multiselect__tags')
    if len(multiselects) > index:
        await multiselects[index].click()
        log.info("  Clicked dropdown index %d", index)
        await frame.wait_for_timeout(1000)
        return True
    log.warning("  Could not find dropdown at index %d", index)
    return False


async def select_option(frame, option_text: str) -> bool:
    """Select an option from an open dropdown."""
    result = await frame.evaluate("""(text) => {
        const activeSelect = document.querySelector('.multiselect--active');
        if (!activeSelect) return false;
        
        const options = activeSelect.querySelectorAll('.multiselect__option');
        for (const opt of options) {
            const t = opt.textContent.trim();
            if (t === text || t.startsWith(text)) {
                opt.click();
                return true;
            }
        }
        return false;
    }""", option_text)

    if result:
        log.info("  Selected option '%s'", option_text)
        await frame.wait_for_timeout(600)
        return True

    log.warning("  Could not select option: %s", option_text)
    return False

async def clear_county_selection(frame):
    """Click all 'remove' icons only on the Counties dropdown to reset it."""
    await frame.evaluate("""() => {
        const selects = document.querySelectorAll('.multiselect');
        if (selects.length > 1) {
            const countySelect = selects[1];
            const icons = countySelect.querySelectorAll('.multiselect__tag-icon');
            icons.forEach(icon => icon.click());
        }
    }""")
    await frame.wait_for_timeout(500)



async def get_options(page, frame, dropdown_index: int = 1) -> list[str]:
    """Open a dropdown by index and return all visible options."""
    await click_dropdown_by_index(frame, dropdown_index)
    await frame.wait_for_timeout(1000)

    options = await frame.evaluate("""() => {
        const candidates = document.querySelectorAll('.multiselect__option, li, [class*="option"], [class*="item"]');
        const opts = [];
        for (const el of candidates) {
            const t = el.textContent.trim();
            if (t && t.length < 60 && !opts.includes(t)) opts.push(t);
        }
        return opts.slice(0, 150);
    }""")

    # Close dropdown using page.keyboard (Frame doesn't have keyboard)
    await page.keyboard.press("Escape")
    await frame.wait_for_timeout(400)
    return options


async def click_update_results(frame) -> int:
    """Click Update Results and return the listing count."""
    btns = [
        'button:has-text("Update Results")',
        'button:has-text("Update")',
        'button:has-text("Search")',
        'button:has-text("Apply")',
    ]
    for sel in btns:
        try:
            btn = await frame.query_selector(sel)
            if btn:
                await btn.click(force=True)
                # Wait for the loading overlay to disappear
                try:
                    await frame.wait_for_selector('.loading-overlay', state='hidden', timeout=15000)
                except Exception:
                    pass
                await frame.wait_for_timeout(4000)
                break
        except Exception:
            pass

    # Read count
    count_text = await frame.evaluate("""() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const t = el.textContent.trim();
            if (/^[\\d,]+\\s+Listings Found$/.test(t) ||
                /^[\\d,]+\\s+Listing/.test(t)) {
                return t;
            }
        }
        return null;
    }""")

    if count_text:
        nums = re.findall(r'[\d,]+', count_text)
        if nums:
            return int(nums[0].replace(",", ""))
    return -1


# ── Export + download ─────────────────────────────────────────────

async def do_export(page, frame, context, save_path: pathlib.Path,
                    timeout_ms: int = 120000) -> bool:
    """Click the Export button and capture the file download."""
    save_path.parent.mkdir(parents=True, exist_ok=True)

    export_sel = [
        'button:has-text("Export to see Detailed Report")',
        'button:has-text("Export")',
        'a:has-text("Export to see Detailed Report")',
        'a:has-text("Export")',
        '.btn-success',
        'button[class*="success"]',
    ]

    btn = None
    for sel in export_sel:
        try:
            btn = await frame.query_selector(sel)
            if btn:
                log.info("  Found export button via: %s", sel)
                break
        except Exception:
            pass

    if not btn:
        log.warning("  Export button not found in frame.")
        return False

    try:
        # expect_download is on page, not context
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            await btn.click(force=True)
            log.info("  Waiting for download (up to %ds)...", timeout_ms // 1000)
        dl = await dl_info.value
        fname = dl.suggested_filename or save_path.name
        await dl.save_as(str(save_path))
        size_kb = save_path.stat().st_size / 1024
        log.info("  Downloaded: %s  (%.1f KB)", fname, size_kb)
        return True
    except Exception as exc:
        log.error("  Download failed: %s", exc)
        return False


# ── High-level export flows ───────────────────────────────────────

async def export_all(page, frame, context) -> bool:
    """Try exporting all listings at once (no state filter)."""
    log.info("Attempting full export (all states)...")
    count = await click_update_results(frame)
    log.info("Total listings: %s", count if count > 0 else "unknown")
    save_path = IMPORT_DIR / "all_listings.csv"
    return await do_export(page, frame, context, save_path, timeout_ms=180000)


async def export_by_state(page, frame, context, state_name: str) -> bool:
    """Filter by state then export."""
    log.info("Exporting state: %s", state_name)

    # Reload to clear filters
    await frame.evaluate("() => window.location.reload()")
    await frame.wait_for_timeout(5000)

    opened = await click_dropdown_by_index(frame, 0)
    if not opened:
        log.warning("  Could not open States dropdown for %s", state_name)
        return False

    await frame.wait_for_timeout(800)
    selected = await select_option(frame, state_name)
    if not selected:
        log.warning("  Could not select state: %s", state_name)
        return False

    count = await click_update_results(frame)
    log.info("  %s: %d listings", state_name, count)

    if count == 0:
        log.warning("  No listings found for %s, skipping.", state_name)
        return False

    safe = state_name.replace(" ", "_")
    save_path = IMPORT_DIR / "{}_listings.csv".format(safe)
    return await do_export(page, frame, context, save_path, timeout_ms=120000)

async def export_by_state_chunked(page, frame, context, state_name: str) -> int:
    """Filter by state and break the last 30 days into 5-day chunks to prevent timeouts."""
    log.info("Exporting state (chunked): %s", state_name)
    
    # Reload to clear filters
    await frame.evaluate("() => window.location.reload()")
    await frame.wait_for_timeout(5000)

    opened = await click_dropdown_by_index(frame, 0)
    if not opened:
        log.warning("  Could not open States dropdown for %s", state_name)
        return 0

    await frame.wait_for_timeout(800)
    selected = await select_option(frame, state_name)
    if not selected:
        log.warning("  Could not select state: %s", state_name)
        return 0

    exported = 0
    today = datetime.now()
    
    # We want 30 days back from today, in 5-day chunks
    for i in range(7):
        end_date = today - timedelta(days=i*5)
        start_date = today - timedelta(days=(i+1)*5 - 1)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        log.info("  Processing chunk %d: %s to %s", i+1, start_str, end_str)
        
        safe_state = state_name.replace(" ", "_")
        save_path = IMPORT_DIR / safe_state / "{}_{}_to_{}.csv".format(safe_state, start_str, end_str)
        
        if save_path.exists() and save_path.stat().st_size > 0:
            log.info("    Already downloaded %s, skipping.", save_path.name)
            continue
            
        # Inject the dates via Vue app
        script = f"""() => {{
            if (typeof app !== 'undefined' && app.selectedDates) {{
                app.selectedDates.start = '{start_str} 00:00';
                app.selectedDates.end = '{end_str} 23:59:59';
                app.search();
            }}
        }}"""
        await frame.evaluate(script)
        await frame.wait_for_timeout(1000)
        
        count = await click_update_results(frame)
        log.info("    %s (%s - %s): %d listings", state_name, start_str, end_str, count)
        
        if count == 0:
            log.info("    No listings in this chunk, skipping.")
            continue
            
        ok = await do_export(page, frame, context, save_path, timeout_ms=120000)
        if ok:
            exported += 1
            log.info("    Saved: %s", save_path.name)
        else:
            log.warning("    Export failed for chunk %s to %s", start_str, end_str)
            
        await asyncio.sleep(2)
        
    return exported



async def export_by_county(page, frame, context, state_name: str) -> int:
    """
    Get all counties and export each as a separate CSV.
    Reloads the iframe between counties to ensure clean filter state.
    """
    log.info("Getting county list from portal...")

    counties = await get_options(page, frame, 1)
    log.info("  Total county options: %d  First 10: %s", len(counties), counties[:10])

    if not counties:
        log.warning("  No county options found.")
        return 0

    exported = 0
    
    skip_list = [
        "District Of Columbia", "Maryland", "Virginia", "West Virginia", 
        "No elements found. Consider changing the search query."
    ]

    # Apply state filter ONCE before looping over counties
    if state_name:
        opened = await click_dropdown_by_index(frame, 0)
        if opened:
            await frame.wait_for_timeout(600)
            await select_option(frame, state_name)
            await frame.wait_for_timeout(600)

    for county in counties:
        if county in skip_list:
            continue
            
        log.info("  Processing county: %s", county)

        safe_state  = state_name.replace(" ", "_") if state_name else "All"
        safe_county = county.replace(" ", "_").replace("/", "-").replace("\\", "-")
        save_path   = IMPORT_DIR / safe_state / "{}.csv".format(safe_county)
        
        # Skip if we already downloaded this county
        if save_path.exists() and save_path.stat().st_size > 0:
            log.info("    Already downloaded %s, skipping.", save_path.name)
            continue

        # Select the county
        opened = await click_dropdown_by_index(frame, 1)
        if not opened:
            log.warning("    Could not open Counties dropdown")
            continue
        await frame.wait_for_timeout(600)
        selected = await select_option(frame, county)
        if not selected:
            log.warning("    Could not select: %s", county)
            continue

        # Click Update Results
        count = await click_update_results(frame)
        log.info("    %s: %d listings", county, count)
        if count == 0:
            log.info("    No listings, skipping.")
            await clear_county_selection(frame)
            continue

        ok = await do_export(page, frame, context, save_path, timeout_ms=120000)
        if ok:
            exported += 1
            log.info("    Saved: %s", save_path.name)
        else:
            log.warning("    Export failed for %s", county)

        # Clear just the county selection for the next iteration
        await clear_county_selection(frame)

        await asyncio.sleep(2)

    return exported



# ── Main ──────────────────────────────────────────────────────────

async def run_async(args) -> int:
    from playwright.async_api import async_playwright

    import tempfile
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    total_files = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        await login(page)

        # Get the correct frame (iframe or main page)
        frame, is_iframe = await get_listings_frame(page)
        log.info("Using %s for interactions.", "iframe" if is_iframe else "main page")

        # Debug screenshot
        await page.screenshot(
            path=str(DEBUG_DIR / "frame_detected.png"), full_page=False
        )

        if args.import_only:
            log.info("--import-only: skipping export step.")
        elif args.county and args.state:
            ok = await export_by_county(page, frame, context, args.state)
            total_files += ok
        elif args.state:
            if args.county:
                ok = await export_by_county(page, frame, context, args.state)
                total_files += ok
            else:
                total_files += await export_by_state_chunked(page, frame, context, args.state)
        elif args.by_state:
            for state in TARGET_STATES:
                total_files += await export_by_state_chunked(page, frame, context, state)
                await asyncio.sleep(3)
        else:
            ok = await export_all(page, frame, context)
            if ok:
                total_files += 1
            else:
                log.info("Full export failed. Trying state-by-state...")
                for state in TARGET_STATES:
                    ok = await export_by_state(page, frame, context, state)
                    if ok:
                        total_files += 1
                    await asyncio.sleep(3)

        await browser.close()

    log.info("Export done. %d file(s) in %s", total_files, IMPORT_DIR)
    return total_files


def run(args=None):
    if args is None:
        args = argparse.Namespace(
            state=None, county=False, by_state=True, import_only=False
        )

    if not args.import_only:
        total = asyncio.run(run_async(args))
        log.info("Downloaded %d CSV file(s).", total)

    # Auto-import
    from collectors.csv_importer import run as import_run
    imported = import_run()
    log.info("Import complete. %d records in DB.", imported)
    return imported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="USA Home Listings — Portal CSV Exporter")
    parser.add_argument("--state",       default=None,
                        help="Export specific state (e.g. 'Virginia')")
    parser.add_argument("--county",      action="store_true",
                        help="Export county-by-county (use with --state)")
    parser.add_argument("--by-state",    action="store_true",
                        help="Export each target state as a separate CSV")
    parser.add_argument("--import-only", action="store_true",
                        help="Skip export, import existing CSVs from data/imports/")
    args = parser.parse_args()
    run(args)
