#!/usr/bin/env python3
"""
cleanpal0 - Doom pal0 duplicate/similarity cleaner (CLI)

Reads one of:
  * SLADE palette PNG export      (128x128, 16x16 grid of 8x8 blocks)
  * DoomTools blank playpal PNG   (256 wide, any height; row 0 = pal0)
  * Raw palette file (.pal)       (768-byte RGB triples; first 768 = pal0)
  * WAD file (.wad)               (finds the PLAYPAL lump, first 768 bytes)

Finds IDENTICAL (exact RGB) and SIMILAR (perceptual, transitive clusters)
palette entries. The lowest-index entry of each set/cluster is KEPT; the
rest are CLEARED.

Outputs (next to the input file):
  inputname-identical-(TYPE-tol).png  cleared identical pixels, original
                                      positions, transparent background
  inputname-simular-(TYPE-tol).png    cleared similar pixels, same treatment
  inputname-aligned-(TYPE-tol).png    kept colours packed from slot 0 in
                                      original order, tail transparent

Options:
  --rgb            use weighted RGB metric (default tolerance 1.1)
                   instead of CIE Lab dE76 (default tolerance 2.0)
  --tolerance N    override the active metric's default tolerance
  --split          also write one PNG per identical set / similar cluster
                   (like the Photoshop script's layers):
                   inputname-identical-(TYPE-tol)-keepNNN.png

Output geometry follows the input:
  SLADE PNG      -> 128x128, entries painted as 8x8 blocks
  DoomTools PNG  -> 256xN, entries painted as full-height 1px columns
  .pal / .wad    -> 256x1, one pixel per entry
"""

import argparse
import math
import os
import struct
import sys


# -------------------- dependency check --------------------
def _dep_check():
    missing = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    if missing:
        print("Missing dependencies: " + ", ".join(missing))
        print("Install with: pip install " + " ".join(missing))
        sys.exit(1)


_dep_check()
from PIL import Image  # noqa: E402


ENTRIES = 256
SLADE_SIZE = 128
SLADE_GRID = 16
SLADE_CELL = 8
DEFAULT_TOL_LAB = "2.0"
DEFAULT_TOL_RGB = "1.1"


# -------------------- colour maths --------------------
def srgb_to_lab(r, g, b):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    rl, gl, bl = lin(r), lin(g), lin(b)
    x = rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375
    y = rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750
    z = rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041
    xn, yn, zn = 0.95047, 1.00000, 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def dist_lab(a, b):
    dl = a["lab"][0] - b["lab"][0]
    da = a["lab"][1] - b["lab"][1]
    db = a["lab"][2] - b["lab"][2]
    return math.sqrt(dl * dl + da * da + db * db)


def dist_rgb_weighted(a, b):
    dr = abs(a["r"] - b["r"])
    dg = abs(a["g"] - b["g"])
    db = abs(a["b"] - b["b"])
    return math.sqrt(
        (0.299 * dr) ** 2 + (0.587 * dg) ** 2 + (0.114 * db) ** 2
    )


# -------------------- union-find --------------------
class UF:
    def __init__(self, n):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            self.p[ra] = rb
        elif self.r[ra] > self.r[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.r[ra] += 1


# -------------------- input loaders --------------------
def load_wad_pal0(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        raise ValueError("Not a valid WAD file (bad header).")
    numlumps, infotableofs = struct.unpack_from("<ii", data, 4)
    for i in range(numlumps):
        off = infotableofs + i * 16
        if off + 16 > len(data):
            break
        filepos, size = struct.unpack_from("<ii", data, off)
        name = data[off + 8 : off + 16].rstrip(b"\x00").decode("ascii", "replace")
        if name.upper() == "PLAYPAL":
            if size < 768:
                raise ValueError("PLAYPAL lump is smaller than 768 bytes.")
            return data[filepos : filepos + 768]
    raise ValueError("No PLAYPAL lump found in WAD.")


def load_pal_pal0(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 768 or len(data) % 768 != 0:
        raise ValueError(
            "PAL file size (%d) is not a multiple of 768 bytes." % len(data)
        )
    return data[:768]


def load_input(path):
    """Returns (colors, mode). colors = list of 256 entry dicts.
    mode = dict with canvas size + paint geometry for output images."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".png":
        im = Image.open(path).convert("RGB")
        w, h = im.size
        px = im.load()
        if w == SLADE_SIZE and h == SLADE_SIZE:
            mode = {
                "label": "SLADE (128x128, 8x8 cells)",
                "canvas": (SLADE_SIZE, SLADE_SIZE),
                "paint_wh": (SLADE_CELL, SLADE_CELL),
                "paint_xy": lambda s: (
                    (s % SLADE_GRID) * SLADE_CELL,
                    (s // SLADE_GRID) * SLADE_CELL,
                ),
            }
            rgbs = []
            for idx in range(ENTRIES):
                gx, gy = idx % SLADE_GRID, idx // SLADE_GRID
                sx = gx * SLADE_CELL + SLADE_CELL // 2
                sy = gy * SLADE_CELL + SLADE_CELL // 2
                rgbs.append(px[sx, sy])
        elif w == ENTRIES and h >= 1:
            mode = {
                "label": "DoomTools playpal (256x%d, row 0 = pal0)" % h,
                "canvas": (ENTRIES, h),
                "paint_wh": (1, h),
                "paint_xy": lambda s: (s, 0),
            }
            rgbs = [px[idx, 0] for idx in range(ENTRIES)]
        else:
            raise ValueError(
                "Unexpected PNG size %dx%d. Expected 128x128 (SLADE) or 256xN (DoomTools)."
                % (w, h)
            )
    elif ext in (".pal", ".wad"):
        raw = load_wad_pal0(path) if ext == ".wad" else load_pal_pal0(path)
        mode = {
            "label": "raw pal0 (%s)" % ("WAD PLAYPAL" if ext == ".wad" else "PAL file"),
            "canvas": (ENTRIES, 1),
            "paint_wh": (1, 1),
            "paint_xy": lambda s: (s, 0),
        }
        rgbs = [
            (raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i in range(ENTRIES)
        ]
    else:
        raise ValueError("Unsupported input type: %s (use .png, .pal, or .wad)" % ext)

    colors = []
    for idx, (r, g, b) in enumerate(rgbs):
        colors.append(
            {
                "idx": idx,
                "r": r,
                "g": g,
                "b": b,
                "key": (r, g, b),
                "lab": srgb_to_lab(r, g, b),
            }
        )
    return colors, mode


# -------------------- painting --------------------
def new_canvas(mode):
    return Image.new("RGBA", mode["canvas"], (0, 0, 0, 0))


def paint_entry(img, mode, slot, rgb):
    x0, y0 = mode["paint_xy"](slot)
    pw, ph = mode["paint_wh"]
    px = img.load()
    for dy in range(ph):
        for dx in range(pw):
            px[x0 + dx, y0 + dy] = (rgb[0], rgb[1], rgb[2], 255)


# -------------------- main --------------------
def main():
    ap = argparse.ArgumentParser(
        prog="cleanpal0",
        description="Find duplicate/similar Doom pal0 entries and output "
        "identical / simular / aligned PNGs.",
    )
    ap.add_argument("input", help="input file (.png, .pal, or .wad)")
    ap.add_argument(
        "--rgb",
        action="store_true",
        help="use weighted RGB metric (default tolerance 1.1) instead of CIE Lab dE76",
    )
    ap.add_argument(
        "--tolerance",
        metavar="N",
        default=None,
        help="tolerance level (default: 2.0 for CIE Lab, 1.1 for RGB)",
    )
    ap.add_argument(
        "--split",
        action="store_true",
        help="also write one PNG per identical set / similar cluster",
    )
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print("Input file not found: %s" % args.input)
        sys.exit(1)

    use_lab = not args.rgb
    tol_str = args.tolerance if args.tolerance is not None else (
        DEFAULT_TOL_LAB if use_lab else DEFAULT_TOL_RGB
    )
    try:
        tol = float(tol_str)
        if tol < 0:
            raise ValueError
    except ValueError:
        print("Invalid tolerance value: %s" % tol_str)
        sys.exit(1)

    mtype = "CIE" if use_lab else "RGB"
    token = "(%s-%s)" % (mtype, tol_str)
    dist = dist_lab if use_lab else dist_rgb_weighted

    try:
        colors, mode = load_input(args.input)
    except (ValueError, OSError) as e:
        print("Error reading input: %s" % e)
        sys.exit(1)

    base = os.path.splitext(args.input)[0]

    # ---- IDENTICAL (exact RGB) ----
    exact_map = {}
    for c in colors:
        exact_map.setdefault(c["key"], []).append(c["idx"])
    identical_groups = [
        sorted(v) for v in exact_map.values() if len(v) >= 2
    ]
    identical_groups.sort(key=lambda g: g[0])

    # ---- SIMILAR (transitive clustering, exact pairs excluded) ----
    uf = UF(ENTRIES)
    for a in range(ENTRIES):
        for b in range(a + 1, ENTRIES):
            if colors[a]["key"] == colors[b]["key"]:
                continue  # exact dupes are IDENTICAL's job
            if dist(colors[a], colors[b]) <= tol:
                uf.union(a, b)
    clusters = {}
    for i in range(ENTRIES):
        clusters.setdefault(uf.find(i), []).append(i)
    similar_groups = [
        sorted(v) for v in clusters.values() if len(v) >= 2
    ]
    similar_groups.sort(key=lambda g: g[0])

    # ---- cleared set (keep lowest index of every group) ----
    cleared = set()
    for grp in identical_groups:
        cleared.update(grp[1:])
    for grp in similar_groups:
        cleared.update(grp[1:])
    kept = [i for i in range(ENTRIES) if i not in cleared]

    written = []

    # ---- identical image ----
    img = new_canvas(mode)
    for grp in identical_groups:
        for idx in grp[1:]:
            paint_entry(img, mode, idx, colors[idx]["key"])
    p = "%s-identical-%s.png" % (base, token)
    img.save(p)
    written.append(p)

    # ---- simular image ----
    img = new_canvas(mode)
    for grp in similar_groups:
        for idx in grp[1:]:
            paint_entry(img, mode, idx, colors[idx]["key"])
    p = "%s-simular-%s.png" % (base, token)
    img.save(p)
    written.append(p)

    # ---- aligned image (packed, transparent tail) ----
    img = new_canvas(mode)
    for slot, idx in enumerate(kept):
        paint_entry(img, mode, slot, colors[idx]["key"])
    p = "%s-aligned-%s.png" % (base, token)
    img.save(p)
    written.append(p)

    # ---- split files ----
    if args.split:
        for grp in identical_groups:
            img = new_canvas(mode)
            for idx in grp[1:]:
                paint_entry(img, mode, idx, colors[idx]["key"])
            p = "%s-identical-%s-keep%03d.png" % (base, token, grp[0])
            img.save(p)
            written.append(p)
        for grp in similar_groups:
            img = new_canvas(mode)
            for idx in grp[1:]:
                paint_entry(img, mode, idx, colors[idx]["key"])
            p = "%s-simular-%s-keep%03d.png" % (base, token, grp[0])
            img.save(p)
            written.append(p)

    # ---- summary ----
    print("Input : %s  [%s]" % (args.input, mode["label"]))
    print(
        "Metric: %s, tolerance <= %s"
        % ("CIE Lab dE76" if use_lab else "Weighted RGB", tol_str)
    )
    print(
        "IDENTICAL sets: %d   SIMILAR clusters: %d"
        % (len(identical_groups), len(similar_groups))
    )
    print("Kept: %d   Cleared: %d" % (len(kept), len(cleared)))
    print("Wrote %d file(s):" % len(written))
    for p in written:
        print("  " + p)


if __name__ == "__main__":
    main()