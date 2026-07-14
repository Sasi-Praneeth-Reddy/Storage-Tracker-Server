"""
Quick script to screenshot the USA Home Listings portal
listings page and inspect available filters/export options.
"""
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        # Login
        await page.goto("https://get.usahomelistings.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[type="email"]', USAHOMELISTINGS_EMAIL)
        await page.click('button[type="submit"]')
        await page.wait_for_selector('input[type="password"]', timeout=10000)
        await page.fill('input[type="password"]', USAHOMELISTINGS_PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(4000)
        print("Logged in. URL:", page.url)

        # Go to listings
        await page.goto("https://get.usahomelistings.com/portal/page/listings_data",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        out = pathlib.Path("debug_screenshots")
        out.mkdir(exist_ok=True)

        # Full page screenshot
        await page.screenshot(path=str(out / "listings_full.png"), full_page=True)
        print("Screenshot 1 saved: listings_full.png")

        # Save page HTML for analysis
        html = await page.content()
        (out / "listings_page.html").write_text(html[:50000], encoding="utf-8")
        print("HTML saved (first 50KB): listings_page.html")

        # Check for filter elements
        filters = await page.query_selector_all('select, [class*=filter], [class*=Filter], button:has-text("Export"), button:has-text("Download"), button:has-text("CSV")')
        print("Filter/export elements found:", len(filters))
        for f in filters[:10]:
            tag  = await f.evaluate("el => el.tagName")
            text = await f.inner_text()
            cls  = await f.get_attribute("class") or ""
            print("  {} | text: {!r:.60} | class: {:.60}".format(tag, text.strip(), cls))

        await browser.close()

asyncio.run(main())
