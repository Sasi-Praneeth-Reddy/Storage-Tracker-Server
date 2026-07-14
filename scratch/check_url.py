import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        page = await context.new_page()
        res = await page.goto('https://www.sparefoot.com/self-storage/search/20002/', wait_until='domcontentloaded')
        print('Status:', res.status if res else 'None')
        print('URL:', page.url)
        print('Title:', await page.title())
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
