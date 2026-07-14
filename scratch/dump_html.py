import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # User agent is important for avoiding bot detection
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=user_agent)
        page = await context.new_page()
        print("Navigating...")
        await page.goto('https://www.sparefoot.com/self-storage/search/20002/', wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        
        # Save screenshot
        await page.screenshot(path="sparefoot_debug.png")
        
        html = await page.content()
        with open('sparefoot.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print('Length:', len(html))
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
