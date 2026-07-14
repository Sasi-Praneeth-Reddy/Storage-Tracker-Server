import asyncio
from playwright.async_api import async_playwright
from collectors.portal_exporter import login, get_listings_frame

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        await login(page)
        frame, _ = await get_listings_frame(page)
        
        result = await frame.evaluate("""() => {
            return typeof app !== 'undefined' ? (app.selectedDates || 'app defined but no dates') : 'app not defined';
        }""")
        print(f"Result: {result}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
