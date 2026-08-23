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
            device_scale_factor=3, is_mobile=True, has_touch=True, locale="es-ES",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        )
        await ctx.add_init_script("try{localStorage.setItem('qv_lang','es');localStorage.setItem('qv_pwa_prompt_dismissed','1');}catch(e){}")
        page = await ctx.new_page()

        # FEED - dismiss install banner then shot
        await page.goto(f"{BASE}/feed", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        for label in ["Ahora no", "Ahora no", "Cerrar"]:
            try:
                b = page.get_by_text(label, exact=True)
                if await b.count() > 0:
                    await b.first.click(timeout=2500)
                    await page.wait_for_timeout(800)
            except Exception as e:
                pass
        # try close (x) on install card
        try:
            await page.evaluate("document.querySelectorAll('button').forEach(b=>{if(b.textContent.trim()==='Ahora no')b.click();})")
            await page.wait_for_timeout(800)
        except Exception:
            pass
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{OUT}/01_feed.png", full_page=False)
        print("SAVED 01_feed (clean)")

        # find first event card and click it
        eid = None
        try:
            eid = await page.evaluate("""() => {
                const cand = Array.from(document.querySelectorAll('[data-testid],[class*=card],[role=button],div'));
                for (const el of document.querySelectorAll('*')) {
                    const oc = el.getAttribute && el.getAttribute('href');
                }
                // look in react state via anchor fallback
                const a = document.querySelector("a[href*='/event/']");
                if (a) return a.getAttribute('href');
                return null;
            }""")
        except Exception as e:
            print("eval err", e)
        print("HREF:", eid)

        if not eid:
            # click first event image/card by text of a known party then read url
            try:
                card = page.get_by_text("ANOTR x FITZ", exact=False)
                if await card.count() > 0:
                    await card.first.click(timeout=4000)
                    await page.wait_for_timeout(4000)
                    print("URL after click:", page.url)
            except Exception as e:
                print("click err", e)
        else:
            path = eid.split("?")[0]
            await page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(4000)

        if "/event/" in page.url:
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{OUT}/03_event_top.png", full_page=False)
            print("SAVED 03_event_top", page.url)
            await page.evaluate("window.scrollTo(0,600)")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=f"{OUT}/04_event_mid.png", full_page=False)
            print("SAVED 04_event_mid")
        else:
            print("NOT on event page:", page.url)

        await browser.close()

asyncio.run(main())
