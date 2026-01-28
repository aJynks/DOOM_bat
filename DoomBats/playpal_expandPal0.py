#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image

COLORS = 256
BYTES_PER_COLOR = 3
BYTES_PER_PALETTE = COLORS * BYTES_PER_COLOR  # 768
GRID = 16  # 16x16 = 256
OUTPUT_ROWS = 14  # Always output 14 rows


def pal_bytes_to_expanded_png(data: bytes, out_path: Path, scale: int = 1) -> None:
    if len(data) == 0:
        raise ValueError("Input .pal file is empty.")
    if len(data) % BYTES_PER_PALETTE != 0:
        raise ValueError(
            f"Invalid .pal size: {len(data)} bytes. "
            f"Expected multiple of {BYTES_PER_PALETTE} (256*3) for raw Doom palette data."
        )

    # Extract only the FIRST palette (pal0)
    # 256 colors × 3 bytes = 768 bytes
    first_palette = []
    for c in range(COLORS):
        i = c * 3
        r = data[i]
        g = data[i + 1]
        b = data[i + 2]
        first_palette.append((r, g, b))

    # Create 256 x 14 image with palette 0 repeated 14 times
    img = Image.new("RGB", (COLORS, OUTPUT_ROWS))
    px = img.load()

    for row in range(OUTPUT_ROWS):
        for col in range(COLORS):
            px[col, row] = first_palette[col]

    if scale > 1:
        img = img.resize((COLORS * scale, OUTPUT_ROWS * scale), Image.NEAREST)

    img.save(out_path)
    palettes_in_file = len(data) // BYTES_PER_PALETTE
    print(f"Read palette 0 from raw .pal ({len(data)} bytes, {palettes_in_file} palette(s) total)")
    print(f"Wrote {out_path} ({img.size[0]}x{img.size[1]}) - palette 0 repeated {OUTPUT_ROWS} times")


def _normalize_strip_png(img: Image.Image) -> Image.Image:
    """
    Accepts a palette strip PNG:
      - 256 x N
      - (256*scale) x (N*scale) (uniform integer scale)
    Returns:
      - 256 x N (unscaled)
    """
    w, h = img.size
    if w % COLORS != 0:
        raise ValueError(f"Strip PNG width must be 256 or a multiple of 256. Got width={w}.")

    scale = w // COLORS
    if scale < 1:
        scale = 1
    if h % scale != 0:
        raise ValueError(f"Strip PNG height must be a multiple of inferred scale={scale}. Got height={h}.")

    rows = h // scale
    if scale != 1:
        img = img.resize((COLORS, rows), Image.NEAREST)

    return img


def _grid16x16_to_strip(img: Image.Image) -> Image.Image:
    """
    Accepts a 16x16 grid palette PNG (commonly 128x128 or scaled).
    Samples the center pixel of each cell -> produces a 256x1 strip.
    """
    w, h = img.size
    if w % GRID != 0 or h % GRID != 0:
        raise ValueError(f"Grid PNG must be divisible by 16 in both dimensions. Got {w}x{h}.")

    cell_w = w // GRID
    cell_h = h // GRID

    out = Image.new("RGB", (COLORS, 1))
    out_px = out.load()
    px = img.load()

    idx = 0
    for gy in range(GRID):
        cy = gy * cell_h + cell_h // 2
        for gx in range(GRID):
            cx = gx * cell_w + cell_w // 2
            out_px[idx, 0] = px[cx, cy]
            idx += 1

    return out


def png_to_expanded_png(in_path: Path, out_path: Path, scale: int = 1) -> None:
    img = Image.open(in_path).convert("RGB")
    w, h = img.size

    # Heuristic:
    # - If width is exactly 256 => treat first row as palette 0 (any height)
    # - Else if width is multiple of 256 => treat as strip (256 x N or scaled)
    # - Else if divisible by 16 both ways => treat as 16x16 grid => 1 palette
    if w == COLORS:
        # Exact 256 width - just use first row as-is
        strip = img  # Don't normalize, just use first row directly
    elif w % COLORS == 0:
        strip = _normalize_strip_png(img)  # 256 x N (scaled)
    elif (w % GRID == 0) and (h % GRID == 0):
        strip = _grid16x16_to_strip(img)   # 256 x 1
    else:
        raise ValueError(
            f"Unrecognized palette PNG layout: {w}x{h}. "
            f"Expected width of 256, multiple of 256, or grid (dims divisible by 16)."
        )

    # Extract only the first row (palette 0)
    first_palette = []
    px = strip.load()
    for col in range(COLORS):
        first_palette.append(px[col, 0])

    # Create 256 x 14 image with palette 0 repeated 14 times
    out_img = Image.new("RGB", (COLORS, OUTPUT_ROWS))
    out_px = out_img.load()

    for row in range(OUTPUT_ROWS):
        for col in range(COLORS):
            out_px[col, row] = first_palette[col]

    if scale > 1:
        out_img = out_img.resize((out_img.size[0] * scale, out_img.size[1] * scale), Image.NEAREST)

    out_img.save(out_path)
    print(f"Read palette PNG: {in_path} ({w}x{h})")
    print(f"Wrote {out_path} ({out_img.size[0]}x{out_img.size[1]}) - palette 0 repeated {OUTPUT_ROWS} times")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate a 256x14 palette strip PNG by repeating palette 0 fourteen times."
    )
    ap.add_argument("input", type=Path, help="Input: playpal.pal / pal0.pal (raw) OR pal0.png (grid/strip)")
    ap.add_argument("output_png", type=Path, help="Output PNG (256x14, palette 0 repeated, optionally scaled)")
    ap.add_argument("--scale", type=int, default=1, help="Scale output up with nearest-neighbor (default: 1)")
    args = ap.parse_args()

    in_path = args.input
    out_path = args.output_png

    ext = in_path.suffix.lower()
    if ext == ".pal":
        pal_bytes_to_expanded_png(in_path.read_bytes(), out_path, scale=args.scale)
    elif ext == ".png":
        png_to_expanded_png(in_path, out_path, scale=args.scale)
    else:
        raise ValueError("Unsupported input type. Use a .pal or .png file.")


if __name__ == "__main__":
    main()