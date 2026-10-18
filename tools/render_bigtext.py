#!/usr/bin/env python3
"""Render a text file as big terminal text (quadrant block characters, 2x2
pixels per cell) for the end of the Termux boot intro.

usage: tools/render_bigtext.py TEXT.txt OUT.ans [--px 16] [--per-row 6]
  Each non-empty input line becomes one block in OUT.ans; blocks are separated
  by a line containing only "\f". Long lines are wrapped into rows of at most
  --per-row characters (6 x 16 px glyphs = 48 columns, fits the Redmi's ~50).
  Needs Pillow and a CJK font (macOS: PingFang / STHeiti).
"""
import argparse, math, os
from PIL import Image, ImageDraw, ImageFont

FONTS = ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/PingFang.ttc",
         "/System/Library/Fonts/Hiragino Sans GB.ttc"]
QUAD = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"   # index = TL + 2*TR + 4*BL + 8*BR

ap = argparse.ArgumentParser()
ap.add_argument("text"); ap.add_argument("out")
ap.add_argument("--px", type=int, default=16); ap.add_argument("--per-row", type=int, default=6)
a = ap.parse_args()
font = ImageFont.truetype(next(f for f in FONTS if os.path.exists(f)), a.px)

def render_row(s):
    w = a.px * len(s); h = a.px + (a.px % 2)
    img = Image.new("L", (w + (w % 2), h), 0)
    d = ImageDraw.Draw(img)
    for i, ch in enumerate(s):
        d.text((i * a.px + a.px / 2, h / 2), ch, font=font, fill=255, anchor="mm")
    px = img.load(); out = []
    for y in range(0, img.height, 2):
        line = ""
        for x in range(0, img.width, 2):
            on = lambda xx, yy: px[xx, yy] > 110
            line += QUAD[on(x, y) + 2 * on(x + 1, y) + 4 * on(x, y + 1) + 8 * on(x + 1, y + 1)]
        out.append(line.rstrip())
    return out

blocks = []
for raw in open(a.text, encoding="utf-8"):
    s = raw.strip()
    if not s:
        continue
    n = math.ceil(len(s) / a.per_row); k = math.ceil(len(s) / n)     # balanced rows
    rows = [s[i:i + k] for i in range(0, len(s), k)]
    blocks.append("\n".join(sum((render_row(r) for r in rows), [])))
open(a.out, "w", encoding="utf-8").write("\n\f\n".join(blocks) + "\n")
print(f"{len(blocks)} lines -> {a.out}")
