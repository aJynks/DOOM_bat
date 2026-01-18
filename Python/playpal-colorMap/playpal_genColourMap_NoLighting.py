#!/usr/bin/env python3

import sys
import os
from math import sqrt

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

PAL0_SIZE_BYTES = 768
PLAYPAL_SIZE_BYTES = 14 * 768

NUMLIGHTS = 32
TOTAL_ROWS = 34
GRAYCOLORMAP = 32
BLACKROW = 33

def is_png(path):
    try:
        with open(path, "rb") as f:
            return f.read(8) == PNG_SIGNATURE
    except:
        return False

def detect_type(path):
    if not os.path.isfile(path):
        return None

    if is_png(path):
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size

            if (w, h) == (256, 14):
                return "playpal14PNG"
            if (w, h) == (256, 1):
                return "playpal1PNG"
            if (w >= 16 and h >= 16) and (w % 16 == 0) and (h % 16 == 0):
                return "sladeStylePNG"
        return None

    size = os.path.getsize(path)

    if size == PLAYPAL_SIZE_BYTES:
        return "playpal.pal binary"
    if size == PAL0_SIZE_BYTES:
        return "pal0.pal Binary"

    return None

def extract_palette(path, kind):
    if kind in ("playpal14PNG", "playpal1PNG", "sladeStylePNG"):
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGBA")
            w, h = im.size

            if kind in ("playpal14PNG", "playpal1PNG"):
                pal = []
                for x in range(256):
                    r, g, b, _ = im.getpixel((x, 0))
                    pal.append((r, g, b))
                return pal

            if kind == "sladeStylePNG":
                cell_w = w // 16
                cell_h = h // 16
                pal = []
                for row in range(16):
                    for col in range(16):
                        cx = col * cell_w + cell_w // 2
                        cy = row * cell_h + cell_h // 2
                        r, g, b, _ = im.getpixel((cx, cy))
                        pal.append((r, g, b))
                return pal

    with open(path, "rb") as f:
        data = f.read()

    base = 0
    pal = []
    for i in range(256):
        off = base + i * 3
        pal.append((data[off], data[off+1], data[off+2]))

    return pal

def best_color(r, g, b, palette):
    best_dist = (r*r + g*g + b*b) * 2
    best_index = 0

    for i, (pr, pg, pb) in enumerate(palette):
        dr = r - pr
        dg = g - pg
        db = b - pb
        dist = dr*dr + dg*dg + db*db
        if dist < best_dist:
            if dist == 0:
                return i
            best_dist = dist
            best_index = i

    return best_index

def build_colormap_no_lighting(palette):
    colormap = []

    # Full brightness row (no darkening)
    full_bright_row = []
    for i in range(256):
        full_bright_row.append(i)
    
    # Repeat the full brightness row 32 times (rows 0-31)
    for l in range(NUMLIGHTS):
        colormap.append(full_bright_row[:])

    # Invulnerability row (row 32)
    invuln = []
    for r, g, b in palette:
        fr = r / 255.0
        fg = g / 255.0
        fb = b / 255.0
        gray = fr * 0.299 + fg * 0.587 + fb * 0.144
        gray = 1.0 - gray
        gv = int(gray * 255)
        idx = best_color(gv, gv, gv, palette)
        invuln.append(idx)

    colormap.append(invuln)

    # Pure black row (row 33)
    black_row = [best_color(0, 0, 0, palette)] * 256
    colormap.append(black_row)

    return colormap

def write_png(colormap, palette, outpath):
    from PIL import Image

    h = len(colormap)
    w = 256

    img = Image.new("RGB", (w, h))
    px = img.load()

    for y in range(h):
        for x in range(w):
            idx = colormap[y][x]
            px[x, y] = palette[idx]

    img.save(outpath)

def main():
    if len(sys.argv) != 3:
        print("Usage: py playpal_genColourMap_NoLighting.py inputpalette output.png")
        return 1

    inp = sys.argv[1]
    outp = sys.argv[2]

    kind = detect_type(inp)
    if not kind:
        print("ERROR: not a valid type")
        return 2

    palette = extract_palette(inp, kind)
    if len(palette) != 256:
        print("ERROR: palette extraction failed")
        return 3

    colormap = build_colormap_no_lighting(palette)
    write_png(colormap, palette, outp)

    print("Generated colormap PNG (no lighting):", outp)
    print("Rows:", len(colormap), "(32 full-bright + invulnerability + black)")

if __name__ == "__main__":
    main()