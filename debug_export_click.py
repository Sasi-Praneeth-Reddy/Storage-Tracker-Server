"""
debug_export_click.py
Takes a screenshot AFTER clicking the Export button to see what happens.
Run: venv\\Scripts\\python debug_export_click.py
"""
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD

OUT = pathlib.Path("debug_screenshots")
OUT.mkdir(exist_ok=True)

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        # Track new pages/popups
        new_pages = []
        context.on("page", lambda p: new_pages.append(p))

        # Login
        await page.goto("https://get.usahomelistings.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[type="email"]', USAHOMELISTINGS_EMAIL)
        await page.click('button[type="submit"]')
        await page.wait_for_selector('input[type="password"]', timeout=12000)
        await page.fill('input[type="password"]', USAHOMELISTINGS_PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)

        # Load listings page, find iframe
        await page.goto("https://get.usahomelistings.com/portal/page/listings_data",
                        wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)

        frame = None
        for f in page.frames:
            if "portal.usahomelistings.com/listings" in f.url:
                frame = f
                break

        if not frame:
            print("ERROR: Could not find listings iframe")
            await browser.close()
            return

        print("Iframe found:", frame.url[:80])

        # Select a small county filter: Alexandria (smallest county in VA)
        print("\nSelecting Alexandria County for a small test export...")

        # Select state Virginia
        state_el = await frame.evaluate("""() => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            let node;
            while ((node = walker.nextNode())) {
                if (node.textContent.trim() === 'States') {
                    const el = node.parentElement;
                    const sel = 'div[class*="select"], div[class*="dropdown"], div[class*="filter"], div[class*="multiselect"], button';
                    const c = el.closest(sel);
                    if (c) { c.click(); return c.className; }
                    el.click(); return el.className;
                }
            }
            return null;
        }""")
        print("States clicked:", state_el)
        await frame.wait_for_timeout(1000)

        # Select Virginia
        clicked = await frame.evaluate("""() => {
            const items = document.querySelectorAll('li, [class*="option"], [class*="item"]');
            for (const el of items) {
                if (el.textContent.trim() === 'Virginia') { el.click(); return true; }
            }
            return false;
        }""")
        print("Virginia selected:", clicked)
        await frame.wait_for_timeout(1000)

        # Select county Alexandria
        county_el = await frame.evaluate("""() => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            let node;
            while ((node = walker.nextNode())) {
                if (node.textContent.trim() === 'Counties') {
                    const el = node.parentElement;
                    const sel = 'div[class*="select"], div[class*="dropdown"], div[class*="filter"], div[class*="multiselect"], button';
                    const c = el.closest(sel);
                    if (c) { c.click(); return c.className; }
                    el.click(); return el.className;
                }
            }
            return null;
        }""")
        print("Counties clicked:", county_el)
        await frame.wait_for_timeout(1000)

        # Get list of counties
        counties = await frame.evaluate("""() => {
            const items = document.querySelectorAll('li, [class*="option"], [class*="item"]');
            return Array.from(items).map(el => el.textContent.trim()).filter(t => t && t.length < 40).slice(0, 30);
        }""")
        print("Available county options:", counties[:15])

        # Click Alexandria City or Alexandria County (first Alexandria)
        clicked_county = await frame.evaluate("""() => {
            const items = document.querySelectorAll('li, [class*="option"], [class*="item"]');
            for (const el of items) {
                const t = el.textContent.trim();
                if (t.includes('Alexandria') || t.includes('Arlington')) {
                    el.click(); return t;
                }
            }
            return null;
        }""")
        print("County selected:", clicked_county)
        await frame.wait_for_timeout(800)

        # Click Update Results
        update_btn = await frame.query_selector('button:has-text("Update Results")')
        if update_btn:
            await update_btn.click()
            print("Update Results clicked")
            await frame.wait_for_timeout(5000)

        # Screenshot before Export click
        await page.screenshot(path=str(OUT / "before_export.png"))
        print("Screenshot saved: before_export.png")

        # Find export button
        export_btn = await frame.query_selector('button:has-text("Export to see Detailed Report")')
        if not export_btn:
            export_btn = await frame.query_selector('button:has-text("Export")')

        if not export_btn:
            print("ERROR: Export button not found")
            await browser.close()
            return

        print("Export button found. Clicking now...")

        # Try to capture download, new page, OR dialog
        try:
            async with page.expect_download(timeout=30000) as dl_info:
                await export_btn.click()
                print("Export button clicked")
                await page.wait_for_timeout(5000)

                # Screenshot immediately after click
                await page.screenshot(path=str(OUT / "after_export_click.png"))
                print("Screenshot after click saved")

                # Check for new pages
                await page.wait_for_timeout(3000)
                if new_pages:
                    print("New pages opened:", len(new_pages))
                    for np in new_pages:
                        print("  New page URL:", np.url)
                        await np.screenshot(path=str(OUT / "new_page.png"))

                # Check for dialogs/modals
                modals = await page.query_selector_all('[class*="modal"], [role="dialog"], [class*="popup"]')
                print("Modals found:", len(modals))
                for m in modals[:3]:
                    txt = (await m.inner_text()).strip()[:200]
                    print("  Modal text:", txt)

            dl = await dl_info.value
            fname = dl.suggested_filename or "export.csv"
            save_path = pathlib.Path("data/imports") / fname
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await dl.save_as(str(save_path))
            print(f"SUCCESS! Downloaded: {fname} ({save_path.stat().st_size/1024:.1f} KB)")

        except Exception as exc:
            print(f"Download not triggered in 30s: {exc}")
            await page.screenshot(path=str(OUT / "timeout_state.png"))
            print("Timeout screenshot saved: timeout_state.png")

            # Check what happened on the page
            body_text = await page.evaluate("() => document.body.innerText")
            print("\nPage text after click (first 500 chars):")
            print(body_text[:500])

            # Check iframe content after click
            if frame:
                iframe_text = await frame.evaluate("() => document.body.innerText")
                print("\nIframe text after click (first 500 chars):")
                print(iframe_text[:500])

        await browser.close()

asyncio.run(main())
