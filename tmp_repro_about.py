import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        for url in ['about:support', 'about:blank', 'about:config']:
            try:
                print('trying', url)
                await page.goto(url, wait_until='commit', timeout=20000)
                print('ok', url)
                await page.screenshot(path=f'd:/temp/{url.replace(":", "_").replace("/", "_")}.png')
            except Exception as e:
                print('failed', url, type(e).__name__, e)
        await context.close()
        await browser.close()

asyncio.run(main())
