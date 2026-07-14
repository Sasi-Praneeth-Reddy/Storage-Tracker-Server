"""
debug_multi_county.py
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
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("Logging in...")
        await page.goto("https://get.usahomelistings.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[type="email"]', USAHOMELISTINGS_EMAIL)
        await page.click('button[type="submit"]')
        await page.wait_for_selector('input[type="password"]', timeout=12000)
        await page.fill('input[type="password"]', USAHOMELISTINGS_PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)

        print("Going to listings...")
        await page.goto("https://get.usahomelistings.com/portal/page/listings_data", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)

        frame = None
        for f in page.frames:
            if "portal.usahomelistings.com/listings" in f.url:
                frame = f
                break
        
        if not frame:
            print("No iframe found.")
            return

        # Let's try 2 counties: Alexandria County, then Arlington County
        for county_name in ["Alexandria County", "Arlington County"]:
            print(f"\\n--- Testing {county_name} ---")

            # 1. Open Counties dropdown
            multiselects = await frame.query_selector_all(".multiselect__tags")
            if len(multiselects) < 2:
                print("Counties multiselect not found")
                continue
            
            counties_input = multiselects[1]
            await counties_input.click()
            await frame.wait_for_timeout(1000)

            # 2. Select the county
            options = await frame.query_selector_all(".multiselect__option")
            clicked = False
            for opt in options:
                txt = (await opt.inner_text()).strip()
                if txt == county_name:
                    await opt.click()
                    clicked = True
                    print(f"Clicked option: {txt}")
                    break
            
            if not clicked:
                print("Option not found!")
                
            await frame.wait_for_timeout(1000)

            # Close dropdown just in case
            await page.keyboard.press("Escape")
            await frame.wait_for_timeout(1000)

            # 3. Update Results
            update_btn = await frame.query_selector('button:has-text("Update Results")')
            if update_btn:
                await update_btn.click(force=True)
                print("Update Results clicked")
            await frame.wait_for_timeout(5000)

            # 4. Check count
            count_el = await frame.query_selector_all("*")
            count_text = None
            for el in count_el:
                try:
                    txt = (await el.inner_text()).strip()
                    if "Listings Found" in txt and len(txt) < 40:
                        count_text = txt
                        break
                except Exception:
                    pass
            print(f"Count after Update: {count_text}")

            # 5. Deselect the county for the next loop
            # Look for the selected tag's remove icon
            print("Removing selected county...")
            remove_icons = await frame.query_selector_all(".multiselect__tag-icon")
            print(f"Found {len(remove_icons)} remove icons")
            for icon in remove_icons:
                try:
                    await icon.click(force=True)
                    print("Clicked remove icon")
                    await frame.wait_for_timeout(1000)
                except Exception as e:
                    print(f"Failed to click remove icon: {e}")
            
            # Click Update Results again to clear filter
            if update_btn:
                await update_btn.click(force=True)
                print("Update Results clicked to clear")
            await frame.wait_for_timeout(5000)

        await browser.close()

asyncio.run(main())
