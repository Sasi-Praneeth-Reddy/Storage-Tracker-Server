"""
inspect_dropdowns.py
Inspects the filter dropdowns on the listings page to find exact selectors.
Run: venv\\Scripts\\python inspect_dropdowns.py
"""
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import USAHOMELISTINGS_EMAIL, USAHOMELISTINGS_PASSWORD

async def main():
    from playwright.async_api import async_playwright
    out = pathlib.Path("debug_screenshots")
    out.mkdir(exist_ok=True)

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
        await page.wait_for_timeout(5000)

        await page.goto("https://get.usahomelistings.com/portal/page/listings_data",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # 1. Find all filter-like elements
        print("\n=== FILTER ELEMENTS ===")
        for sel in ['.filter__wrapper', '.filter__input', '[class*=filter]',
                    '.multiselect', '[class*=multiselect]', 'v-select',
                    '[class*=dropdown]', '[class*=select]']:
            els = await page.query_selector_all(sel)
            if els:
                print("  Selector: {} -> {} elements".format(sel, len(els)))
                for el in els[:3]:
                    text = (await el.inner_text()).strip()[:60]
                    cls = (await el.get_attribute("class") or "")[:60]
                    print("    text={!r} class={!r}".format(text, cls))

        # 2. Screenshot before click
        await page.screenshot(path=str(out / "before_dropdown.png"))
        print("\nScreenshot: before_dropdown.png")

        # 3. Try clicking States dropdown using various methods
        print("\n=== TRYING TO OPEN STATES DROPDOWN ===")
        clicked = False
        
        # Method A: click element containing "States" text
        for sel in [
            'div.multiselect:first-of-type',
            '.filter__input:first-child',
            'div:has-text("States"):not(script)',
            '[placeholder="States"]',
            'span:has-text("States")',
            '.multiselect__placeholder:has-text("States")',
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    print("  Found via: {}".format(sel))
                    await el.click()
                    await page.wait_for_timeout(1500)
                    await page.screenshot(path=str(out / "dropdown_open.png"))
                    print("  Screenshot: dropdown_open.png")
                    clicked = True
                    break
            except Exception as exc:
                print("  {} -> {}".format(sel, str(exc)[:50]))

        if clicked:
            # 4. Find the options in the opened dropdown
            print("\n=== DROPDOWN OPTIONS ===")
            for sel in [
                '.multiselect__element',
                '.multiselect__option',
                'li.multiselect__element',
                '[class*=option]',
                '[class*=item]',
                'ul li',
            ]:
                els = await page.query_selector_all(sel)
                if els:
                    print("  Options selector: {} -> {} items".format(sel, len(els)))
                    for el in els[:5]:
                        text = (await el.inner_text()).strip()[:50]
                        print("    {!r}".format(text))
                    break

        # 5. Inspect Export button
        print("\n=== EXPORT BUTTON ===")
        for sel in [
            'button:has-text("Export")',
            'a:has-text("Export")',
            '[class*=export]',
            'button.btn-success',
            'button.btn-primary',
        ]:
            els = await page.query_selector_all(sel)
            if els:
                for el in els:
                    text = (await el.inner_text()).strip()[:80]
                    tag  = await el.evaluate("e => e.tagName")
                    cls  = (await el.get_attribute("class") or "")[:60]
                    href = await el.get_attribute("href") or ""
                    print("  {} text={!r} class={!r} href={!r}".format(
                        tag, text, cls, href[:80]))

        # 6. Save full HTML for analysis
        html = await page.content()
        # Find filter section
        start = html.find("filter")
        if start > 0:
            snippet = html[max(0, start-200):start+2000]
            (out / "filter_html_snippet.txt").write_text(snippet, encoding="utf-8")
            print("\nFilter HTML snippet saved.")

        await browser.close()

asyncio.run(main())
