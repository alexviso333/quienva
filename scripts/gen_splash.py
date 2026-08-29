"""Build the iOS launch splash from the REAL logo artwork (icon.png) so the
letters are pixel-identical to the brand logo, on PURE BLACK (#000000) to match
the logo's own background exactly. Centered + prominent (Instagram-style).
"""
from PIL import Image

SRC = "/app/frontend/mobile/assets/icon.png"   # the exact "¿Quién va?" wordmark on black
SIZE = 2732
LOGO_FRAC = 0.72  # logo width as fraction of canvas -> big & centered

def main():
    logo = Image.open(SRC).convert("RGB")
    lw, lh = logo.size
    target_w = int(SIZE * LOGO_FRAC)
    target_h = int(lh * target_w / lw)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    canvas = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))  # pure black
    x = (SIZE - target_w) // 2
    y = (SIZE - target_h) // 2
    canvas.paste(logo, (x, y))

    for out in ("/app/frontend/assets/splash.png",
                "/app/frontend/mobile/assets/splash.png"):
        canvas.save(out)
        print("wrote", out)

if __name__ == "__main__":
    main()
