#!/usr/bin/env python3
"""Draw the repo banner. Pure PIL, no generated imagery — RyanAI Lab house style.

Concept: a production model swap on a two-node GB10 cluster — one engine replaces
another but keeps the old name as an alias, so no client changes. Left = wordmark.
Right = two stacked engine slabs (OLD / NEW) joined by a single orange arrow that
re-uses the outgoing name: the alias that makes the cutover zero-client-change.

Repro:
  pip install Pillow      # any reasonably recent Pillow (e.g. >=9) provides the
                          # Image/ImageDraw/ImageFont API used here.
  python3 docs/make_banner.py

Fonts: the layout hard-codes two macOS system fonts (Helvetica Neue .ttc index 7
for the wordmark, Menlo for mono). On a host without those exact paths, font()
falls back to ImageFont.load_default() (a small built-in bitmap font) — the banner
still renders, but text metrics will differ from the committed docs/assets/banner.png.
For pixel-identical output, run on macOS, or supply .ttc files at the same paths.
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
BG = (10, 10, 10)
WHITE = (245, 245, 245)
GREY = (140, 140, 140)
DIM = (70, 70, 70)
ORANGE = (255, 122, 26)
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs/assets/banner.png"

HN = "/System/Library/Fonts/HelveticaNeue.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"

def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        # Fallback when the platform font is missing — see the Repro note above.
        return ImageFont.load_default()

f_title = font(HN, 88, 7)     # Light
f_tag = font(HN, 30, 7)
f_mono = font(MENLO, 17)
f_label = font(MENLO, 15)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# crosshair corners
for cx, cy in ((40, 40), (W - 40, H - 40)):
    d.line([(cx - 11, cy), (cx + 11, cy)], fill=DIM, width=1)
    d.line([(cx, cy - 11), (cx, cy + 11)], fill=DIM, width=1)

# 5x3 dot lattices
for ox, oy in ((72, 78), (1150, 536)):
    for r in range(3):
        for c in range(5):
            x, y = ox + c * 15, oy + r * 12
            d.ellipse([x, y, x + 1.6, y + 1.6], fill=DIM)

# wordmark
d.text((80, 196), "MODEL SWAP", font=f_title, fill=WHITE)
d.text((80, 288), "ZERO CHANGE", font=f_title, fill=WHITE)
d.text((82, 414), "Production model swap on two Dell Pro Max with GB10.", font=f_tag, fill=WHITE)
d.text((82, 462), "vLLM · SERVED-NAME ALIAS · ONE-COMMAND ROLLBACK · 1M YaRN", font=f_mono, fill=GREY)

# right: two engine slabs (isometric-ish parallelograms), stacked
SX, SY = 860, 180
tiers = [("OLD  DSV4F", "01"), ("NEW  Qwen3.8-Flash-Next 1M", "02")]
slab_w, slab_h, skew, gap = 280, 58, 42, 120
boxes = []
for i, (name, num) in enumerate(tiers):
    y = SY + i * (slab_h + gap)
    poly = [(SX + skew, y), (SX + skew + slab_w, y), (SX + slab_w, y + slab_h), (SX, y + slab_h)]
    d.polygon(poly, outline=(96, 96, 96), width=1)
    d.text((SX + skew + 14, y + 18), name, font=f_label, fill=GREY)
    d.text((SX + skew + slab_w + 16, y + 20), num, font=f_label, fill=DIM)
    boxes.append(y)

# the single orange alias arrow: NEW keeps the OLD name as a served-name alias
rx = SX + skew + slab_w - 30
top, bot = boxes[0] + slab_h + 6, boxes[1] - 6
d.line([(rx, bot), (rx, top)], fill=ORANGE, width=2)
d.polygon([(rx, top - 2), (rx - 6, top + 10), (rx + 6, top + 10)], fill=ORANGE)
d.ellipse([rx - 5, bot - 5, rx + 5, bot + 5], fill=ORANGE)
d.text((rx + 14, (top + bot) // 2 - 8), "ALIAS", font=f_label, fill=ORANGE)

# footer rule + labels
d.line([(80, 560), (W - 80, 560)], fill=(40, 40, 40), width=1)
d.text((80, 576), "RYANAI LAB", font=f_label, fill=GREY)
d.text((W - 80 - 250, 576), "DELL PRO MAX WITH GB10", font=f_label, fill=GREY)

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
print("wrote", OUT)
