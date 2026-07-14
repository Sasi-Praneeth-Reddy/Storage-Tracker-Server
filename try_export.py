"""
try_export.py
Tries to download the export CSV directly from the portal.
Waits for full Vue.js page rendering before interacting.
Run: venv\\Scripts\\python try_export.py
"""
import asyncio, sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD

IMPORT_DIR = pathlib.Path(__file__).parent / "data" / "imports"
IMPORT_DIR.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path("debug_screenshots")
OUT.mkdir(exist_ok=True)

async def main():
    from playwright.async_api import async_playwright, TimeoutError as PwTimeout

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
            downloads_path=str(IMPORT_DIR),
        )
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        # ── Login ───────────────────────────────────────────────────
        await page.goto("https://get.usahomelistings.com/login",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.fill('input[type="email"]', USAHOMELISTINGS_EMAIL)
        await page.click('button[type="submit"]')
        await page.wait_for_selector('input[type="password"]', timeout=12000)
        await page.fill('input[type="password"]', USAHOMELISTINGS_PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)
        print("Logged in:", page.url)

        # ── Go to listings, wait for full render ────────────────────
        await page.goto("https://get.usahomelistings.com/portal/page/listings_data",
                        wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(5000)  # extra wait for Vue to render
        print("Page loaded:", page.url)

        # Take a screenshot to confirm render
        await page.screenshot(path=str(OUT / "ready_state.png"), full_page=False)
        print("Screenshot: ready_state.png")

        # ── Inspect what's actually rendered now ─────────────────────
        print("\n=== PAGE BODY TEXT (first 1000 chars) ===")
        body_text = await page.evaluate("() => document.body.innerText")
        print(body_text[:1000])

        # ── Find filter elements ─────────────────────────────────────
        print("\n=== FILTER ELEMENT SEARCH ===")
        for sel in [
            '.filter__state-inner',
            '.custom__select-trigger',
            '.filter__wrapper',
            'div[class*="state"]',
            'div[class*="multiselect"]',
            '.vs__dropdown-toggle',        # vue-select
            '.choices__inner',             # choices.js
            '[data-v-app]',               # Vue 3 app root
        ]:
            try:
                els = await page.query_selector_all(sel)
                if els:
                    print("  {} -> {} found".format(sel, len(els)))
                    for el in els[:2]:
                        txt = (await el.inner_text()).strip()[:80]
                        cls = (await el.get_attribute("class") or "")[:80]
                        print("    text={!r}  class={!r}".format(txt, cls))
            except Exception as e:
                pass

        # ── Find Export button ───────────────────────────────────────
        print("\n=== EXPORT BUTTON SEARCH ===")
        export_btn = None
        for sel in [
            'button:has-text("Export to see Detailed Report")',
            'button:has-text("Export")',
            'a:has-text("Export to see Detailed Report")',
            'a:has-text("Export")',
            '.btn-success',
            'button.btn:has-text("Export")',
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    txt = (await el.inner_text()).strip()
                    cls = (await el.get_attribute("class") or "")
                    href = await el.get_attribute("href") or ""
                    print("  FOUND: {} | {!r} | class={} | href={}".format(
                        sel, txt[:60], cls[:60], href[:60]))
                    if export_btn is None:
                        export_btn = el
            except Exception as e:
                pass

        # ── Try to click Export & capture download ───────────────────
        if export_btn:
            print("\n=== ATTEMPTING EXPORT DOWNLOAD ===")
            try:
                async with context.expect_download(timeout=120000) as dl_info:
                    await export_btn.click()
                    print("  Export button clicked, waiting for download...")
                dl = await dl_info.value
                fname = dl.suggested_filename or "listings_export.csv"
                save_to = IMPORT_DIR / fname
                await dl.save_as(str(save_to))
                size = save_to.stat().st_size
                print("  Downloaded: {} ({:.1f} KB)".format(fname, size/1024))
                print("  Saved to: {}".format(save_to))
            except PwTimeout:
                print("  Download timed out (file may be too large for one export).")
                print("  => Need to filter by county before exporting.")
                await page.screenshot(path=str(OUT / "after_export_click.png"))
        else:
            print("\n  Export button NOT found - taking full screenshot to debug")
            await page.screenshot(path=str(OUT / "no_export_btn.png"), full_page=True)
            
            # Try JS to find any download links
            links = await page.evaluate("""() => {
                const anchors = document.querySelectorAll('a, button');
                return Array.from(anchors)
                    .filter(el => el.innerText && el.innerText.toLowerCase().includes('export'))
                    .map(el => ({tag: el.tagName, text: el.innerText.trim().substring(0,80),
                                 href: el.href || '', cls: el.className.substring(0,80)}));
            }""")
            print("\n  JS-found export elements:", links)

        # ── Get States dropdown options via JS ───────────────────────
        print("\n=== STATE DROPDOWN OPTIONS (via JS) ===")
        state_options = await page.evaluate("""() => {
            // Try to find any element with "States" text and check siblings
            const all = document.querySelectorAll('*');
            const results = [];
            for (const el of all) {
                if (el.children.length === 0 && el.innerText &&
                    el.innerText.trim() === 'States') {
                    const parent = el.closest('[class*="select"], [class*="dropdown"], [class*="filter"]');
                    if (parent) {
                        results.push({
                            elTag: el.tagName,
                            elClass: el.className,
                            parentTag: parent.tagName,
                            parentClass: parent.className.substring(0,80)
                        });
                    }
                }
            }
            return results.slice(0, 5);
        }""")
        print("  States element context:", state_options)

        await browser.close()

asyncio.run(main())
