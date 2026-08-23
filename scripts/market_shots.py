import asyncio, base64, os
from playwright.async_api import async_playwright
from PIL import Image

CHROME = "/usr/lib/chromium/chromium"
SHOTS = "/app/appstore_shots"
OUTDIR = "/app/frontend/public/appstore"
TMP = "/tmp/asc_market"
os.makedirs(TMP, exist_ok=True)

ICON = "/app/frontend/public/icons/icon-512.png"
icon_b64 = base64.b64encode(open(ICON, "rb").read()).decode()

# each: source screenshot, headline html (use <g> for gradient word), subtitle, badge, crop-top(px in 1242-space to skip app's own header)
SLIDES = [
    dict(src="01_feed.png",      label="DESCUBRE",
         head='Sabes <g>quién va</g> antes de salir',
         sub="Las fiestas de tu ciudad y qué amigos van a cada plan.",
         badge="👀 tus amigos ya van", crop=250),
    dict(src="03_event_top.png", label="ENTRADAS",
         head='Entrada, hora y <g>cómo llegar</g>',
         sub="Precio real y compra segura, todo en una pantalla.",
         badge="🎟️ desde 40€", crop=0),
    dict(src="04_event_mid.png", label="AMIGOS",
         head='Mira <g>quién va</g> y no salgas solo',
         sub="Tus amigos, en cada fiesta, antes de decidir.",
         badge="👀 5 van", crop=155),
    dict(src="05_locales.png",   label="LOCALES",
         head='Todas las <g>discotecas</g> de tu ciudad',
         sub="Días de apertura, mapa y sus próximas fiestas.",
         badge="📍 cerca de ti", crop=250),
    dict(src="06_mapa.png",      label="MAPA",
         head='La noche, <g>en el mapa</g>',
         sub="Encuentra locales y planes cerca de ti.",
         badge="🗺️ tu ciudad", crop=250),
]

def html_for(slide):
    img_b64 = base64.b64encode(open(f"{SHOTS}/{slide['src']}", "rb").read()).decode()
    head = slide["head"].replace("<g>", '<span class="g">').replace("</g>", "</span>")
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=Unbounded:wght@700;800;900&family=Outfit:wght@400;500;600&display=swap' rel='stylesheet'>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:1242px;height:2688px;overflow:hidden}}
  .stage{{position:relative;width:1242px;height:2688px;
    background:radial-gradient(120% 80% at 15% 0%, #241226 0%, #0A0A0C 55%),
               radial-gradient(120% 80% at 100% 100%, #06202a 0%, rgba(10,10,12,0) 60%),
               #0A0A0C;
    font-family:'Outfit',sans-serif;color:#fff}}
  .top{{padding:120px 90px 0}}
  .brand{{display:flex;align-items:center;gap:20px;margin-bottom:40px}}
  .brand img{{width:78px;height:78px;border-radius:20px}}
  .brand .name{{font-family:'Unbounded';font-weight:800;font-size:40px;letter-spacing:-1px}}
  .brand .dot{{color:#ff2d78}}
  .brand .label{{margin-left:14px;color:#22e3d6;font-weight:700;font-size:26px;letter-spacing:5px}}
  h1{{font-family:'Unbounded';font-weight:800;font-size:118px;line-height:1.02;letter-spacing:-3px}}
  h1 .g{{background:linear-gradient(90deg,#ff2d78,#a24bd6 55%,#22e3d6);-webkit-background-clip:text;background-clip:text;color:transparent}}
  .sub{{margin-top:34px;font-size:44px;line-height:1.35;color:#b9bec6;font-weight:400;max-width:1000px}}
  .phonewrap{{position:absolute;left:50%;transform:translateX(-50%);bottom:-70px;width:820px}}
  .badge{{position:absolute;top:70px;right:-6px;z-index:5;background:#141418;border:1px solid rgba(255,255,255,.14);
    box-shadow:0 0 40px rgba(255,45,120,.45);border-radius:999px;padding:22px 34px;font-weight:700;font-size:34px;white-space:nowrap}}
  .phone{{position:relative;width:820px;border:16px solid #0e0e12;border-radius:70px;overflow:hidden;
    box-shadow:0 0 0 2px rgba(255,255,255,.06), 0 40px 120px rgba(255,45,120,.28), 0 20px 80px rgba(34,227,214,.20);}}
  .phone .notch{{position:absolute;top:18px;left:50%;transform:translateX(-50%);width:230px;height:40px;background:#0e0e12;border-radius:22px;z-index:3}}
  .phone img{{display:block;width:100%;margin-top:-{slide['crop']}px}}
</style></head>
<body>
  <div class='stage'>
    <div class='top'>
      <div class='brand'>
        <img src='data:image/png;base64,{icon_b64}'>
        <span class='name'>¿quién va?<span class='dot'>.</span></span>
        <span class='label'>{slide['label']}</span>
      </div>
      <h1>{head}</h1>
      <div class='sub'>{slide['sub']}</div>
    </div>
    <div class='phonewrap'>
      <div class='badge'>{slide['badge']}</div>
      <div class='phone'><div class='notch'></div><img src='data:image/png;base64,{img_b64}'></div>
    </div>
  </div>
</body></html>"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width":1242,"height":2688}, device_scale_factor=2)
        page = await ctx.new_page()
        for i, s in enumerate(SLIDES, 1):
            f = f"{TMP}/slide{i}.html"
            open(f,"w").write(html_for(s))
            await page.goto(f"file://{f}")
            await page.wait_for_timeout(2500)  # let fonts load
            try:
                await page.evaluate("document.fonts.ready")
                await page.wait_for_timeout(800)
            except Exception: pass
            big = f"{TMP}/m{i}.png"
            await page.screenshot(path=big, clip={"x":0,"y":0,"width":1242,"height":2688})
            # downscale 2x supersample -> crisp 1242x2688
            img = Image.open(big).convert("RGB").resize((1242,2688), Image.LANCZOS)
            out = f"{OUTDIR}/m{i}.png"
            img.save(out)
            print("SAVED", out, img.size)
        await browser.close()

asyncio.run(main())
