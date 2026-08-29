"""Generate a clean, professional splash image for the native iOS app.

The old splash.png had the wordmark inside a pure-black (#000) square on a
#0A0A0C canvas, so on the launch screen it looked small, off-center and a
different colour from the background. This regenerates a single, edge-to-edge
#0A0A0C canvas with the "¿Quién va?" wordmark centred and nicely sized so the
launch screen looks like a polished app.
"""
from PIL import Image, ImageDraw, ImageFont

FONT = "/app/backend/assets/fonts/Unbounded.ttf"
BG = (10, 10, 12)          # #0A0A0C  (exact app background)
WHITE = (255, 255, 255)
PINK = (255, 0, 85)        # #FF0055  (qv-primary)

SIZE = 2732                # high-res square; capacitor-assets downscales


def line_size(font, text):
    box = font.getbbox(text)
    return box[2] - box[0], box[3] - box[1], box[0], box[1]


def main():
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)

    # Two-line wordmark. Size the font so the widest line ~= 46% of the canvas
    # (comfortable margins, reads well cropped on tall iPhones).
    target_w = int(SIZE * 0.46)
    fs = 100
    font = ImageFont.truetype(FONT, fs)
    w1, _, _, _ = line_size(font, "¿Quién")
    fs = int(fs * target_w / w1)
    font = ImageFont.truetype(FONT, fs)

    l1, l2 = "¿Quién", "va?"
    w1, h1, ox1, oy1 = line_size(font, l1)
    w2, h2, ox2, oy2 = line_size(font, l2)

    gap = int(fs * 0.14)
    total_h = h1 + gap + h2
    top = (SIZE - total_h) // 2

    # Line 1 (white)
    x1 = (SIZE - w1) // 2 - ox1
    d.text((x1, top - oy1), l1, font=font, fill=WHITE)
    # Line 2 (pink)
    x2 = (SIZE - w2) // 2 - ox2
    d.text((x2, top + h1 + gap - oy2), l2, font=font, fill=PINK)

    for out in ("/app/frontend/assets/splash.png",
                "/app/frontend/mobile/assets/splash.png"):
        img.save(out)
        print("wrote", out)


if __name__ == "__main__":
    main()
