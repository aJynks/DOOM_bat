import argparse
from pathlib import Path
from PIL import Image

COLORS = 256
GRID = 16  # 16x16 = 256 colors
MAX_PALS = 14  # pal0..pal13
DEFAULT_CELL = 8  # 16*8 = 128 px


def strip_to_slade_grid_row(strip, row, cell):
    """
    Convert one row of a 256xN strip into a SLADE-style 16x16 grid image.
    Output size = (16*cell) x (16*cell).
    """
    out_size = GRID * cell
    out = Image.new("RGB", (out_size, out_size))
    px = strip.load()

    for idx in range(COLORS):
        r, g, b = px[idx, row]
        gx = idx % GRID
        gy = idx // GRID
        x0 = gx * cell
        y0 = gy * cell

        for yy in range(y0, y0 + cell):
            for xx in range(x0, x0 + cell):
                out.putpixel((xx, yy), (r, g, b))

    return out


def main():
    ap = argparse.ArgumentParser(
        description="Convert a PLAYPAL strip PNG (256xN) into SLADE-style palette grid PNGs (<name>_pal0..pal13.png)."
    )
    ap.add_argument("input_strip_png", type=Path, help="Input strip PNG (MUST be 256xN, one palette per row).")
    ap.add_argument(
        "--cell",
        type=int,
        default=DEFAULT_CELL,
        help="Cell size in pixels for SLADE grid output (default: 8 -> 128x128).",
    )
    ap.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Output directory (default: same folder as input).",
    )
    args = ap.parse_args()

    in_path = args.input_strip_png
    cell = args.cell
    outdir = args.outdir if args.outdir is not None else in_path.parent

    if cell < 1:
        raise SystemExit("ERROR: --cell must be >= 1")

    if not in_path.is_file():
        raise SystemExit(f"ERROR: input file not found: {in_path}")

    try:
        img = Image.open(in_path).convert("RGB")
    except Exception as e:
        raise SystemExit(f"ERROR: failed to read PNG: {in_path}\n{e}")

    w, h = img.size
    if w != COLORS:
        raise SystemExit(f"ERROR: input must be exactly 256 pixels wide. Got {w}x{h}.")
    if h < 1:
        raise SystemExit("ERROR: input PNG has no rows (height < 1).")
    if h > MAX_PALS:
        raise SystemExit(f"ERROR: input has {h} rows; max supported is {MAX_PALS} (pal0..pal13).")

    stem = in_path.stem
    outdir.mkdir(parents=True, exist_ok=True)

    for p in range(h):
        out_img = strip_to_slade_grid_row(img, p, cell=cell)
        out_path = outdir / f"{stem}_pal{p}.png"
        out_img.save(out_path)
        print(f"Wrote {out_path} ({out_img.size[0]}x{out_img.size[1]})")

    print(f"Done. Converted {h} palette row(s) from {in_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
