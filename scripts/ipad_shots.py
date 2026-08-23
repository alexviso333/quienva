import asyncio, base64, os
from playwright.async_api import async_playwright
from PIL import Image

CHROME = "/usr/lib/chromium/chromium"
SHOTS = "/app/appstore_shots"
OUTDIR = "/app/frontend/public/appstore"
TMP = "/tmp/ipad_market"
os.makedirs(TMP, exist_ok=True)
ICON = "/app/frontend/public/icons/icon-512.png"
icon_b64 = base64.b64encode(open(ICON, "rb").read()).decode()

SLIDES = [
    dict(src="01_feed.png",      label="DESCUBRE", head='Sabes <g>quién va</g> antes de salir',
         sub="Las fiestas de tu ciudad y qué amigos van a cada plan.", badge="👀 tus amigos ya van", crop=250),
    dict(src="03_event_top.png", label="ENTRADAS", head='Entrada, hora y <g>cómo llegar</g>',
         sub="Precio real y compra segura, todo en una pantalla.", badge="🎟️ desde 40€", crop=0),
    dict(src="04_event_mid.png", label="AMIGOS", head='Mira <g>quién va</g> y no salgas solo',
         sub="Tus amigos, en cada fiesta, antes de decidir.", badge="👀 5 van", crop=155),
    dict(src="05_locales.png",   label="LOCALES", head='Todas las <g>discotecas</g> de tu ciudad',
         sub="Días de apertura, mapa y sus próximas fiestas.", badge="📍 cerca de ti", crop=250),
    dict(src="06_mapa.png",      label="MAPA", head='La noche, <g>en el mapa</g>',
         sub="Encuentra locales y planes cerca de ti.", badge="🗺️ tu ciudad", crop=250),
]

def html_for(s):
    img_b64 = base64.b64encode(open(f"{SHOTS}/{s['src']}", "rb").read()).decode()
    head = s["head"].replace("<g>", '<span class="g">').replace("</g>", "</span>")
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<link href='https://fonts.googleapis.com/css2?family=Unbounded:wght@700;800;900&family=Outfit:wght@400;500;600&display=swap' rel='stylesheet'>
<style>
 *{{margin:0;padding:0;box-sizing:border-box}}
 html,body{{width:2048px;height:2732px;overflow:hidden}}
 .stage{{position:relative;width:2048px;height:2732px;
   background:radial-gradient(120% 70% at 15% 0%, #241226 0%, #0A0A0C 55%),
              radial-gradient(120% 70% at 100% 100%, #06202a 0%, rgba(10,10,12,0) 60%), #0A0A0C;
   font-family:'Outfit',sans-serif;color:#fff}}
 .top{{padding:170px 150px 0;text-align:center}}
 .brand{{display:flex;align-items:center;justify-content:center;gap:22px;margin-bottom:46px}}
 .brand img{{width:90px;height:90px;border-radius:22px}}
 .brand .name{{font-family:'Unbounded';font-weight:800;font-size:46px;letter-spacing:-1px}}
 .brand .dot{{color:#ff2d78}} .brand .label{{margin-left:16px;color:#22e3d6;font-weight:700;font-size:28px;letter-spacing:6px}}
 h1{{font-family:'Unbounded';font-weight:800;font-size:130px;line-height:1.03;letter-spacing:-3px}}
 h1 .g{{background:linear-gradient(90deg,#ff2d78,#a24bd6 55%,#22e3d6);-webkit-background-clip:text;background-clip:text;color:transparent}}
 .sub{{margin:40px auto 0;font-size:50px;line-height:1.35;color:#b9bec6;max-width:1400px}}
 .phonewrap{{position:absolute;left:50%;transform:translateX(-50%);bottom:-90px;width:760px}}
 .badge{{position:absolute;top:80px;right:-10px;z-index:5;background:#141418;border:1px solid rgba(255,255,255,.14);
   box-shadow:0 0 44px rgba(255,45,120,.45);border-radius:999px;padding:24px 38px;font-weight:700;font-size:38px;white-space:nowrap}}
 .phone{{position:relative;width:760px;border:16px solid #0e0e12;border-radius:70px;overflow:hidden;
   box-shadow:0 0 0 2px rgba(255,255,255,.06),0 50px 130px rgba(255,45,120,.30),0 20px 90px rgba(34,227,214,.22)}}
 .phone .notch{{position:absolute;top:18px;left:50%;transform:translateX(-50%);width:220px;height:40px;background:#0e0e12;border-radius:22px;z-index:3}}
 .phone img{{display:block;width:100%;margin-top:-{s['crop']}px}}
</style></head><body>
 <div class='stage'>
  <div class='top'>
   <div class='brand'><img src='data:image/png;base64,{icon_b64}'><span class='name'>¿quién va?<span class='dot'>.</span></span><span class='label'>{s['label']}</span></div>
   <h1>{head}</h1><div class='sub'>{s['sub']}</div>
  </div>
  <div class='phonewrap'><div class='badge'>{s['badge']}</div><div class='phone'><div class='notch'></div><img src='data:image/png;base64,{img_b64}'></div></div>
 </div>
</body></html>"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(viewport={"width":2048,"height":2732}, device_scale_factor=1)
        page = await ctx.new_page()
        for i, s in enumerate(SLIDES, 1):
            f = f"{TMP}/s{i}.html"; open(f,"w").write(html_for(s))
            await page.goto(f"file://{f}"); await page.wait_for_timeout(2500)
            try: await page.evaluate("document.fonts.ready"); await page.wait_for_timeout(600)
            except Exception: pass
            out = f"{OUTDIR}/ipad{i}.png"
            await page.screenshot(path=out, clip={"x":0,"y":0,"width":2048,"height":2732})
            print("SAVED", out, Image.open(out).size)
        await b.close()

asyncio.run(main())
