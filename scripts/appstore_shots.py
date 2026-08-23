import asyncio, os
from playwright.async_api import async_playwright

OUT = "/app/appstore_shots"
os.makedirs(OUT, exist_ok=True)
CHROME = "/usr/lib/chromium/chromium"
BASE = "https://quienva.me"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
        )
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            locale="es-ES",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        )
        # Force Spanish before any app code runs
        await ctx.add_init_script("try{localStorage.setItem('qv_lang','es');}catch(e){}")
        page = await ctx.new_page()

        async def shot(name, wait=4500, scroll=0):
            if scroll:
                await page.evaluate(f"window.scrollTo(0,{scroll})")
                await page.wait_for_timeout(1200)
            await page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
            print("SAVED", name)

        # 1) FEED
        await page.goto(f"{BASE}/feed", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        await shot("01_feed")
        await shot("02_feed_scroll", scroll=700)

        # capture first event id from a card link
        eid = None
        try:
            href = await page.get_attribute("a[href*='/event/']", "href")
            if href and "/event/" in href:
                eid = href.split("/event/")[1].split("/")[0].split("?")[0]
        except Exception as e:
            print("no event link", e)
        print("EVENT ID:", eid)

        # 2) EVENT DETAIL
        if eid:
            await page.goto(f"{BASE}/event/{eid}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)
            await shot("03_event_top")
            await shot("04_event_scroll", scroll=650)

        # 3) LOCALES
        await page.goto(f"{BASE}/locales", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        await shot("05_locales")

        # 4) MAPA
        await page.goto(f"{BASE}/mapa", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(6000)
        await shot("06_mapa")

        await browser.close()

asyncio.run(main())
