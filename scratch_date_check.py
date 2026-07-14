import asyncio
import logging
from playwright.async_api import async_playwright
from collectors.portal_exporter import login, get_listings_frame

logging.basicConfig(level=logging.INFO)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Logging in...")
        await login(page)
        
        print("Logged in. Getting frame...")
        frame, _ = await get_listings_frame(page)
        
        html = await frame.evaluate("() => document.body.innerHTML")
        with open("filters.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        print("Done!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
