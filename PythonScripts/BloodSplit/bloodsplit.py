#!/usr/bin/env python3
"""
bloodsplit.py -- lift blood / gore pixels off Doom textures onto
transparent-background truecolour PNGs.

Detection modes:
  --doomMode [INDICES...]   exact match against the embedded Doom2 PLAYPAL.
                            Default: the red ramp (176-191). --wide and
                            --allred widen the set; explicit indices
                            override everything. The default mode.
  --paletteMode FILE IDX... exact match against user-chosen indices of a
                            supplied palette file.
  --colourMode [COLOURS...] hue-family matching for truecolour / large-
                            palette images. Hex values and/or colour names,
                            one or several; default blood red.

Scans a directory tree of images and writes each result as an RGBA PNG
into a mirrored directory structure under "_BloodSplit". Files with no
blood are not written.

Part of the aJynks Doom asset tool suite.
"""

import sys
import os

# ---------------------------------------------------------------- dep check
_missing = []
try:
    from PIL import Image
except ImportError:
    _missing.append("Pillow")
if _missing:
    print("Missing required package(s): " + ", ".join(_missing))
    print("Install with:  pip install " + " ".join(_missing))
    sys.exit(1)

import argparse
import base64
import colorsys
import struct
from collections import deque

VERSION = "2.4"

# ---------------------------------------------------------------- palette
# Authentic Doom/Doom2 PLAYPAL (palette 0, 768 bytes), embedded verbatim.
_DOOM_PLAYPAL_B64 = (
    "AAAAHxcLFw8HS0tL////GxsbExMTCwsLBwcHLzcfIysPFx8HDxcATzsrRzMjPysb/7e396ur86Oj"
    "65eX54+P34eH23t703Nzy2trx2Njv1tbu1dXs09Pr0dHpz8/ozs7mzMzly8vjysriyMjgx8ffxsbd"
    "xcXcxMTaw8PZwsLXwcHWwcHUwcHTwAARwAAQwAA/+vf/+PT/9vH/9O7/8+z/8en/7+b/7uT/7OD9"
    "6t776Nz55tr35Nj14tbz4NTy39Pv3tLs3NHq29Do2s/m2M7j183h1czf1Mvd08ra0cnX0MjUz8fS"
    "zcbPy8XMysTKyMP7+/v5+fn39/f29vb09PTy8vLx8fHv7+/t7e3s7Ozq6urp6enn5+fl5eXk5OTi"
    "4uLg4ODf39/d3d3b29va2trY2NjW1tbV1dXT09PR0dHQ0NDOzs7Nzc3Ly8vJycnIyMjd/9vb+9nZ"
    "99fX89XW79PU69HS58/Q5M3P4MvN3MrL2MjJ1MbH0MXFzMPEyMLCxcHv6ePt5+Hr5d/p493n4dvm"
    "39rk3tji3Nbg2tXe2NPd19Lb1dDZ1M/X0s3V0MzUz8vn4Njj3dTg2tLd18/Z1MzW0crTzsjQzMbe"
    "39jb3NXZ2tPW2NHU1c7R08zP0crNz8n//9z69tX17tDw5svr3sfm1sTh0MHcysA/////9vb/7u7/"
    "5ub/3t7/19f/z8//x8f/wAA7wAA4wAA1wAAywAAvwAAswAApwAAmwAAiwAAfwAAcwAAZwAAWwAAT"
    "wAAQwAA5+f/x8f/q6v/j4//c3P/U1P/Nzf/Gxv/AAD/AADjAADLAACzAACbAACDAABrAABT/////"
    "+vb/9e7/8eb/7N7/6Nb/487/38b83MX628P32cP118Ly1cHw08At0cAr0MA///////X//+z//+P/"
    "/9r//9H//8j//8Apz8AnzcAky8AhyMATzsnQy8bNyMTLxsLAABTAABHAAA7AAAvAAAjAAAXAAALA"
    "AAA/59D/+dL/3v//wD/zwDPnwCbbwBrp2tr"
)

DOOM_RED_RAMP = range(176, 192)

# --allred: fixed, user-curated list of every blood-relevant index in the
# Doom2 palette: pale flesh-reds + dried blood (16-47), pink highlights +
# red ramp (169-191), dark scorched oranges (232-235).
ALLRED_INDICES = sorted(set(range(16, 48)) |
                        set(range(169, 192)) |
                        set(range(232, 236)))

# --colourMode named colours (hue anchors -- matching is hue-family, so
# 'red' behaves identically to any red hex).
NAMED_COLOURS = {
    "red":     (0xFF, 0x00, 0x00),
    "green":   (0x00, 0xFF, 0x00),
    "blue":    (0x00, 0x00, 0xFF),
    "yellow":  (0xFF, 0xFF, 0x00),
    "orange":  (0xFF, 0x80, 0x00),
    "purple":  (0x80, 0x00, 0xFF),
    "violet":  (0xEE, 0x82, 0xEE),
    "magenta": (0xFF, 0x00, 0xFF),
    "pink":    (0xFF, 0x69, 0xB4),
    "cyan":    (0x00, 0xFF, 0xFF),
    "teal":    (0x00, 0x80, 0x80),
    "lime":    (0x80, 0xFF, 0x00),
    "brown":   (0x8B, 0x45, 0x13),
}


def _decode_embedded_palette():
    raw = base64.b64decode(_DOOM_PLAYPAL_B64)
    if len(raw) != 768:
        print("Internal error: embedded palette corrupt.")
        sys.exit(1)
    return [tuple(raw[i * 3:i * 3 + 3]) for i in range(256)]


# ---------------------------------------------------------------- helpers
def _strip_quotes(s):
    # survive the cmd.exe quoting bug: -i "C:\foo\" leaves a literal "
    return s.replace('"', '') if s else s


def load_palette(path):
    """Load a 256-colour palette from: WAD (PLAYPAL), JASC .pal, raw
    .pal/PLAYPAL lump, DoomTools playpal PNG (256 wide, row 0), SLADE
    pal0.png (16x16 swatch grid), or any 256-pixel image."""
    path = _strip_quotes(path)
    if not os.path.isfile(path):
        raise ValueError("palette file not found: %s" % path)
    with open(path, "rb") as f:
        data = f.read()

    # WAD?
    if len(data) >= 12 and data[0:4] in (b"IWAD", b"PWAD"):
        numlumps, diroff = struct.unpack("<ii", data[4:12])
        for i in range(numlumps):
            e = diroff + i * 16
            if e + 16 > len(data):
                break
            ofs, size = struct.unpack("<ii", data[e:e + 8])
            name = data[e + 8:e + 16].rstrip(b"\x00").decode("ascii", "replace")
            if name.upper() == "PLAYPAL":
                if size < 768:
                    raise ValueError("PLAYPAL lump in WAD is too small.")
                raw = data[ofs:ofs + 768]
                return [tuple(raw[j * 3:j * 3 + 3]) for j in range(256)]
        raise ValueError("no PLAYPAL lump found in WAD: %s" % path)

    # JASC .pal?
    if data[:8] == b"JASC-PAL":
        lines = data.decode("ascii", "replace").splitlines()
        cols = []
        for ln in lines[3:]:
            parts = ln.split()
            if len(parts) >= 3:
                cols.append(tuple(int(p) for p in parts[:3]))
        if len(cols) < 256:
            raise ValueError("JASC palette has fewer than 256 entries.")
        return cols[:256]

    # image?
    try:
        img = Image.open(path)
        img.load()
    except Exception:
        img = None
    if img is not None:
        img = img.convert("RGB")
        w, h = img.size
        px = img.load()
        if w == 256:  # DoomTools playpal PNG -- row 0 is the base palette
            return [px[x, 0] for x in range(256)]
        if w == h and w % 16 == 0 and w >= 16:  # SLADE pal0.png swatch grid
            cell = w // 16
            out = []
            for gy in range(16):
                for gx in range(16):
                    out.append(px[gx * cell + cell // 2, gy * cell + cell // 2])
            return out
        if w * h == 256:  # plain 256-pixel image, row-major
            return [px[i % w, i // w] for i in range(256)]
        raise ValueError(
            "image palette must be 256 wide (DoomTools), a 16x16 swatch "
            "grid (SLADE), or contain exactly 256 pixels: %s" % path)

    # raw PLAYPAL / .pal lump
    if len(data) >= 768 and len(data) % 3 == 0:
        return [tuple(data[i * 3:i * 3 + 3]) for i in range(256)]

    raise ValueError("unrecognised palette format: %s" % path)


def parse_index_specs(tokens):
    """Parse index specs like: 124-138, 15, 10, 20-30 (commas and/or
    spaces, trailing commas fine). Returns a sorted, deduped list."""
    items = []
    for tok in tokens:
        for part in tok.replace(",", " ").split():
            items.append(part)
    if not items:
        raise ValueError("no palette indices given.")
    out = set()
    for it in items:
        if "-" in it[1:]:
            a, _, b = it.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                raise ValueError("bad index range: '%s'" % it)
            if lo > hi:
                lo, hi = hi, lo
            if lo < 0 or hi > 255:
                raise ValueError("index range out of 0-255: '%s'" % it)
            out.update(range(lo, hi + 1))
        else:
            try:
                v = int(it)
            except ValueError:
                raise ValueError("bad index: '%s'" % it)
            if not (0 <= v <= 255):
                raise ValueError("index out of 0-255: '%s'" % it)
            out.add(v)
    return sorted(out)


def parse_hex_colour(s):
    """Parse a hex colour like 8B0000 / f00 (leading # tolerated)."""
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError("bad colour: '%s' (want RRGGBB or a colour name: %s)"
                         % (s, ", ".join(sorted(NAMED_COLOURS))))
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError("bad colour: '%s' (want RRGGBB or a colour name: %s)"
                         % (s, ", ".join(sorted(NAMED_COLOURS))))


def parse_colour_tokens(tokens):
    """Parse --colourMode inputs: hex values and/or colour names, comma
    and/or space separated. Returns a list of (r, g, b)."""
    items = []
    for tok in tokens:
        for part in tok.replace(",", " ").split():
            items.append(part)
    if not items:
        items = ["FF0000"]  # default blood red
    out = []
    for it in items:
        named = NAMED_COLOURS.get(it.lower())
        out.append(named if named else parse_hex_colour(it))
    return out


# ---------------------------------------------------------------- blood sets
def is_blood_colour_wide(rgb, sat_min=0.55, hue_tol=14.0):
    """Wide predicate used by --doomMode --wide: saturated red-family
    colour (dried blood, bright blood highlights)."""
    return hue_family_score(rgb, [0.0], hue_tol, sat_min) >= 1.0


def hue_family_score(rgb, base_hues, hue_tol, sat_min):
    """Continuous score for 'same colour family as any base hue, any
    shade'. >= 1.0 is a hard pass; just below 1.0 is the --softAlpha
    feather band."""
    r, g, b = rgb
    if max(r, g, b) < 30:  # near-black: shade of nothing
        return 0.0
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue = h * 360.0
    best_hue_ratio = 0.0
    for bh in base_hues:
        d = abs(hue - bh)
        if d > 180.0:
            d = 360.0 - d
        ratio = hue_tol / d if d > 0 else 9.0
        if ratio > best_hue_ratio:
            best_hue_ratio = ratio
    sat_ratio = (s / sat_min) if sat_min > 0 else 9.0
    return min(best_hue_ratio, sat_ratio, 9.0)


def build_doom_blood_set(palette, wide, sat_min, hue_tol):
    """doomMode --wide blood set: the red ramp plus every
    predicate-passing palette entry."""
    blood = set(palette[i] for i in DOOM_RED_RAMP)
    if wide:
        for c in palette:
            if c != (0, 0, 0) and is_blood_colour_wide(c, sat_min, hue_tol):
                blood.add(c)
    blood.discard((0, 0, 0))
    return blood


# ---------------------------------------------------------------- processing
def despeckle(alpha, w, h, min_blob):
    """Drop 8-connected blobs (alpha > 0) smaller than min_blob pixels.
    Returns surviving pixel count with alpha >= 128."""
    if min_blob <= 1:
        return sum(1 for a in alpha if a >= 128)
    seen = bytearray(w * h)
    strong = 0
    for start in range(w * h):
        if alpha[start] == 0 or seen[start]:
            continue
        blob = [start]
        seen[start] = 1
        q = deque((start,))
        while q:
            idx = q.popleft()
            x, y = idx % w, idx // w
            for dy in (-1, 0, 1):
                ny = y + dy
                if ny < 0 or ny >= h:
                    continue
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx = x + dx
                    if nx < 0 or nx >= w:
                        continue
                    nidx = ny * w + nx
                    if alpha[nidx] > 0 and not seen[nidx]:
                        seen[nidx] = 1
                        blob.append(nidx)
                        q.append(nidx)
        if len(blob) < min_blob:
            for idx in blob:
                alpha[idx] = 0
        else:
            strong += sum(1 for idx in blob if alpha[idx] >= 128)
    return strong


def process_image(img, opts, blood_set):
    """Return (blood_img_or_None, strong_pixel_count, palette_clean_bool,
    composite_img_or_None). None blood image means: no blood worth
    writing. The composite (only built with --saveCompositeFile, and only when
    blood was found) is the original image with the blood alpha
    subtracted -- layering composite over blood reconstructs the
    original exactly."""
    img = img.convert("RGBA")
    w, h = img.size
    buf = img.tobytes()  # RGBA, 4 bytes per pixel
    n = w * h
    alpha = bytearray(n)

    soft = max(0, min(100, opts.softalpha)) / 100.0

    if opts.mode == "colour":
        band = soft
        for i in range(n):
            j = i * 4
            if buf[j + 3] == 0:
                continue
            score = hue_family_score(buf[j:j + 3], opts.base_hues,
                                     opts.hue_tol, opts.sat_min)
            if score >= 1.0:
                alpha[i] = 255
            elif band > 0 and score > (1.0 - band):
                alpha[i] = int(255 * (score - (1.0 - band)) / band)
    else:  # doom / palette: exact colour match
        for i in range(n):
            j = i * 4
            if buf[j + 3] == 0:
                continue
            if (buf[j], buf[j + 1], buf[j + 2]) in blood_set:
                alpha[i] = 255
        if soft > 0:
            # feather exact-mode edges: blood pixels touching non-blood
            # neighbours lose alpha in proportion to --softAlpha.
            base = bytes(alpha)
            for i in range(n):
                if base[i] == 0:
                    continue
                x, y = i % w, i // w
                nonblood = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            if base[ny * w + nx] == 0:
                                nonblood += 1
                        # out-of-bounds counts as blood (image edge)
                if nonblood:
                    alpha[i] = max(0, 255 - int(255 * soft * nonblood / 8.0))

    strong = despeckle(alpha, w, h, opts.min_blob)
    if strong < opts.min_pixels:
        # palette-clean check (only bothered with when nothing was found,
        # to power the --colourMode suggestion in exact modes)
        clean = True
        if opts.mode != "colour" and strong == 0:
            clean = _looks_palette_clean(buf, n, opts.full_palette)
        return None, strong, clean, None

    out = bytearray(n * 4)
    for i in range(n):
        oa = alpha[i]
        if oa == 0:
            continue
        j = i * 4
        sa = buf[j + 3]
        out[j] = buf[j]
        out[j + 1] = buf[j + 1]
        out[j + 2] = buf[j + 2]
        out[j + 3] = oa if oa < sa else sa
    res = Image.frombytes("RGBA", (w, h), bytes(out))

    comp = None
    if opts.saveall:
        # complement: source alpha minus what the blood copy took, so
        # composite-over-blood rebuilds the original pixel-perfectly
        cbuf = bytearray(n * 4)
        for i in range(n):
            j = i * 4
            sa = buf[j + 3]
            taken = alpha[i] if alpha[i] < sa else sa
            ca = sa - taken
            if ca == 0:
                continue
            cbuf[j] = buf[j]
            cbuf[j + 1] = buf[j + 1]
            cbuf[j + 2] = buf[j + 2]
            cbuf[j + 3] = ca
        comp = Image.frombytes("RGBA", (w, h), bytes(cbuf))
    return res, strong, True, comp


def _looks_palette_clean(buf, n, palette):
    """Sample opaque pixels; True if >= 90% are exact palette colours."""
    pal = set(palette)
    total = hits = 0
    step = max(1, n // 4096)
    for i in range(0, n, step):
        j = i * 4
        if buf[j + 3] == 0:
            continue
        total += 1
        if (buf[j], buf[j + 1], buf[j + 2]) in pal:
            hits += 1
    if total == 0:
        return True
    return hits / total >= 0.90


# ---------------------------------------------------------------- console
def _colour_enabled():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            hh = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(hh, ctypes.byref(mode)):
                k.SetConsoleMode(hh, mode.value | 0x0004)
        except Exception:
            return False
    return True


class C:
    def __init__(self, on):
        self.BOLD = "\x1b[1m" if on else ""
        self.CYAN = "\x1b[1;36m" if on else ""
        self.GREEN = "\x1b[92m" if on else ""
        self.YELLOW = "\x1b[93m" if on else ""
        self.RED = "\x1b[91m" if on else ""
        self.DIM = "\x1b[90m" if on else ""
        self.OFF = "\x1b[0m" if on else ""


def print_help():
    c = C(_colour_enabled())

    def flag(name, arg, *desc):
        head = "  %s%s%s" % (c.GREEN, name, c.OFF)
        if arg:
            head += " " + arg
        print(head)
        for d in desc:
            print("      %s%s%s" % (c.DIM, d, c.OFF))

    def ex(cmd, *desc):
        print("  %s%s%s" % (c.BOLD, cmd, c.OFF))
        for d in desc:
            print("      %s%s%s" % (c.DIM, d, c.OFF))

    print("%sBLOODSPLIT v%s%s" % (c.BOLD, VERSION, c.OFF))
    print("Lift blood / gore pixels off Doom textures onto transparent")
    print("truecolour PNGs. Scans a directory tree; writes results into a")
    print("mirrored structure under %s_BloodSplit%s, same filenames, always"
          % (c.BOLD, c.OFF))
    print("RGBA PNG. Files with no blood are not written at all.")
    print()
    print("%sMODES%s  (pick one; --doomMode is the default)" % (c.CYAN, c.OFF))
    flag("--doomMode", "[INDICES...]",
         "exact match against the embedded Doom2 PLAYPAL -- no palette",
         "file ever needed. Default set: the red ramp (176-191), which",
         "is pure blood only. Widen with --wide or --allred, or take",
         "full control by listing indices yourself (same syntax as",
         "--paletteMode; overrides --wide/--allred):",
         "    bloodsplit --doomMode 16-47, 176-191, 66")
    flag("-w, --wide", "",
         "doomMode: add dried-blood/flesh reds and bright blood",
         "highlights (indices 28-47, 173-175). ~39 colours.")
    flag("-allred, --allred", "",
         "doomMode: every blood-relevant colour in the Doom2 palette --",
         "indices 16-47, 169-191, 232-235 (59 indices). Adds the pale",
         "flesh-reds, pink highlights and dark scorched oranges that",
         "--wide leaves behind. Catches the most gore; expect false",
         "hits on flesh, fire and torch pixels. Supersedes --wide.")
    flag("--paletteMode", "FILE INDICES...",
         "exact match against the palette entries YOU list, from a",
         "supplied palette file. Indices are singles and/or ranges,",
         "comma or space separated: 124-138, 15, 10, 20-30",
         "Duplicates and overlapping ranges are simply combined.",
         "FILE formats: WAD (PLAYPAL found inside), raw .pal/lump,",
         "JASC .pal, DoomTools playpal PNG (256 wide), SLADE pal0.png.")
    flag("--colourMode", "[COLOURS...]",
         "hue-family matching, no palette involved -- for truecolour",
         "images or big-palette games (Hexen etc). Lifts every shade",
         "of each base colour, bright to dark, ignoring other hues.",
         "COLOURS: hex (no # needed) and/or names, one or several,",
         "comma or space separated. A pixel matching ANY base is",
         "lifted. Default: blood red.",
         "Names: " + ", ".join(sorted(NAMED_COLOURS)))
    print()
    print("%sINPUT / OUTPUT%s" % (c.CYAN, c.OFF))
    flag("-i, --input", "DIR",
         "directory to scan (recursive). Default: current directory.")
    flag("-o, --output", "DIR",
         "where the _BloodSplit dir is created. Default: current directory.")
    flag("--ext", "png,bmp,...",
         "image extensions to process. Default: png,bmp,gif,tga,jpg,jpeg.")
    print()
    print("%sTUNING%s" % (c.CYAN, c.OFF))
    flag("--tolerance", "N",
         "colourMode master knob 0-100, default 25. Higher = wider hue",
         "window and looser saturation floor, applied to every base",
         "colour. Start here before touching the two overrides below.")
    flag("--hue-tol", "X",
         "colourMode override: hue window in degrees either side of each",
         "base colour. (Default derives from --tolerance; 25 -> 14.)")
    flag("--sat-min", "X",
         "colourMode override: minimum saturation 0-1.",
         "(Default derives from --tolerance; 25 -> 0.55.)")
    flag("--softAlpha", "N",
         "0-100 feather amount, default 0 (hard mask).",
         "colourMode: borderline pixels fade in over an N%-wide band.",
         "doom/paletteMode: blob edges are feathered by neighbourhood.")
    flag("--saveCompositeFile", "",
         "for every blood file written, also save NAME--composite.png:",
         "the original image with the blood punched out to transparency.",
         "With --softAlpha the composite gets the exact alpha complement,",
         "so layering composite over blood rebuilds the original.",
         "Saved next to the blood file, easy to eyeball-check.")
    flag("--saveCompositeFileMoved", "",
         "same, but composites go straight into",
         "_BloodSplit\\__CompositeFiles\\... instead of next to the blood",
         "files -- identical layout to running --moveComposite afterwards.")
    flag("--moveComposite", "",
         "standalone tidy-up, no image processing: move every file ending",
         "--composite.png found under -i (subdirs included, _BloodSplit",
         "trees included) into __CompositeFiles at -o, mirroring the",
         "directory structure. Never looks inside __CompositeFiles, so",
         "re-runs are safe; existing destination files are not overwritten.")
    flag("--min-blob", "N",
         "drop connected blood blobs smaller than N pixels. Default 3.")
    flag("--min-pixels", "N",
         "skip the file entirely if fewer than N blood pixels survive.",
         "Default 8.")
    print()
    print("%sNOTES%s" % (c.CYAN, c.OFF))
    print("      %s- Mode and option names are matched case-insensitively.%s"
          % (c.DIM, c.OFF))
    print("      %s- Existing transparency is preserved; transparent pixels"
          " are never blood.%s" % (c.DIM, c.OFF))
    print("      %s- _BloodSplit directories are never scanned, so re-runs"
          " are safe.%s" % (c.DIM, c.OFF))
    print("      %s- In doom/paletteMode, bloodless files that don't look"
          " palette-clean%s" % (c.DIM, c.OFF))
    print("      %s  trigger an end-of-run note suggesting --colourMode.%s"
          % (c.DIM, c.OFF))
    print()
    print("%sEXAMPLES%s" % (c.CYAN, c.OFF))
    ex("bloodsplit",
       "scan current dir, doomMode red ramp, output to .\\_BloodSplit")
    ex("bloodsplit --allred",
       "the widest doomMode net -- all 59 blood-relevant Doom2 indices")
    ex("bloodsplit -i D:\\tex\\walls -o D:\\out --wide",
       "doomMode middle tier, output to D:\\out\\_BloodSplit")
    ex("bloodsplit --doomMode 16-47, 169-191",
       "explicit indices against the embedded Doom2 palette --",
       "(--allred minus the 232-235 oranges, for example)")
    ex("bloodsplit --paletteMode mypal.wad 124-138, 15, 10, 20-30",
       "lift exactly those palette indices, palette pulled from the WAD")
    ex("bloodsplit --colourMode",
       "hue matching, default blood red -- for truecolour/Hexen images")
    ex("bloodsplit --colourMode FF3700, FF000B, FF0058",
       "several base colours at once; a pixel matching any is lifted")
    ex("bloodsplit --colourMode green --tolerance 40",
       "every shade of green (nukage?) with a looser match")
    ex("bloodsplit --allred --saveCompositeFile",
       "widest net, plus a --composite copy of each hit with the blood",
       "punched out, saved next to the blood file")
    ex("bloodsplit --allred --saveCompositeFileMoved",
       "same, but composites land in _BloodSplit\\__CompositeFiles\\...")
    ex("cd _BloodSplit && bloodsplit --moveComposite",
       "after eyeball-checking: sweep the --composite.png files out of",
       "the tree into _BloodSplit\\__CompositeFiles, structure mirrored")
    ex("bloodsplit --colourMode red 00FF88 --softAlpha 30",
       "names and hex mix freely; soft edges")


# ---------------------------------------------------------------- main
OUTPUT_DIR_NAME = "_BloodSplit"
COMPOSITE_DIR_NAME = "__CompositeFiles"
COMPOSITE_SUFFIX = "--composite.png"
DEFAULT_EXTS = "png,bmp,gif,tga,jpg,jpeg"


def do_move_composites(in_dir, out_parent, c):
    """--moveComposite: move every *--composite.png under in_dir into
    out_parent/__CompositeFiles, mirroring the directory structure.
    Unlike normal scans this DOES look inside _BloodSplit trees (that's
    where composites live) but never inside __CompositeFiles ones."""
    import shutil
    comp_root = os.path.join(out_parent, COMPOSITE_DIR_NAME)
    print("%sBLOODSPLIT%s  operation: moveComposite" % (c.BOLD, c.OFF))
    print("scan:  %s" % in_dir)
    print("dest:  %s" % comp_root)
    print()
    moved = skipped = 0
    for root, dirs, files in os.walk(in_dir):
        dirs[:] = [d for d in dirs if d != COMPOSITE_DIR_NAME]
        for name in sorted(files):
            if not name.lower().endswith(COMPOSITE_SUFFIX):
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(root, in_dir)
            dest_dir = (os.path.join(comp_root, rel) if rel != "."
                        else comp_root)
            dest = os.path.join(dest_dir, name)
            if os.path.exists(dest):
                print("%swarn%s   %s  (already exists at destination, "
                      "not moved)" % (c.YELLOW, c.OFF,
                                      os.path.relpath(src, in_dir)))
                skipped += 1
                continue
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, dest)
            moved += 1
            print("%smoved%s  %s" % (c.GREEN, c.OFF,
                                     os.path.relpath(src, in_dir)))
    print()
    print("%sDONE%s  moved %d, skipped %d" % (c.BOLD, c.OFF, moved, skipped))
    return 0

_CANONICAL_FLAGS = [
    "--doomMode", "--paletteMode", "--colourMode",
    "--input", "--output", "--ext", "--wide", "--allred", "-allred",
    "--tolerance", "--hue-tol", "--sat-min", "--softAlpha",
    "--saveCompositeFile", "--saveCompositeFileMoved", "--moveComposite",
    "--min-blob", "--min-pixels", "--help",
]


def _normalise_argv(argv):
    """Case-insensitive long-option matching: --COLOURMODE, --softalpha,
    -ALLRED all work."""
    lut = {f.lower(): f for f in _CANONICAL_FLAGS}
    out = []
    for a in argv:
        if a.startswith("-") and len(a) > 2:
            name, eq, val = a.partition("=")
            canon = lut.get(name.lower())
            if canon:
                a = canon + eq + val
        out.append(a)
    return out


def main():
    argv = _normalise_argv(sys.argv[1:])
    if any(a in ("-h", "--help", "-help") for a in argv):
        print_help()
        return 0

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--doomMode", dest="doommode", nargs="*",
                    default=None, metavar="IDX")
    ap.add_argument("--paletteMode", dest="palettemode", nargs="+",
                    metavar="X", default=None)
    ap.add_argument("--colourMode", dest="colourmode", nargs="*",
                    default=None, metavar="COLOUR")
    ap.add_argument("-w", "--wide", action="store_true")
    ap.add_argument("-allred", "--allred", dest="allred", action="store_true")
    ap.add_argument("-i", "--input", default=".")
    ap.add_argument("-o", "--output", default=".")
    ap.add_argument("--ext", default=DEFAULT_EXTS)
    ap.add_argument("--tolerance", type=float, default=25.0)
    ap.add_argument("--hue-tol", dest="hue_tol", type=float, default=None)
    ap.add_argument("--sat-min", dest="sat_min", type=float, default=None)
    ap.add_argument("--softAlpha", dest="softalpha", type=int, default=0)
    ap.add_argument("--saveCompositeFile", dest="saveall", action="store_true")
    ap.add_argument("--saveCompositeFileMoved", dest="saveallmoved",
                    action="store_true")
    ap.add_argument("--moveComposite", dest="movecomposite",
                    action="store_true")
    ap.add_argument("--min-blob", dest="min_blob", type=int, default=3)
    ap.add_argument("--min-pixels", dest="min_pixels", type=int, default=8)
    opts = ap.parse_args(argv)

    c = C(_colour_enabled())

    picked = [n for n, v in (("--doomMode", opts.doommode is not None),
                             ("--paletteMode", opts.palettemode is not None),
                             ("--colourMode", opts.colourmode is not None))
              if v]
    if opts.movecomposite:
        if picked or opts.saveall or opts.saveallmoved:
            print("%sERROR:%s --moveComposite is a standalone operation -- "
                  "no detection mode or composite flags with it."
                  % (c.RED, c.OFF))
            return 1
        in_dir = os.path.abspath(_strip_quotes(opts.input))
        out_parent = os.path.abspath(_strip_quotes(opts.output))
        if not os.path.isdir(in_dir):
            print("%sERROR:%s input directory not found: %s"
                  % (c.RED, c.OFF, in_dir))
            return 1
        return do_move_composites(in_dir, out_parent, c)
    if opts.saveallmoved:
        if opts.saveall:
            print("%swarn%s   --saveCompositeFileMoved supersedes "
                  "--saveCompositeFile." % (c.YELLOW, c.OFF))
        opts.saveall = True
    if len(picked) > 1:
        print("%sERROR:%s pick one mode only (got %s)."
              % (c.RED, c.OFF, ", ".join(picked)))
        return 1
    if opts.palettemode is not None:
        opts.mode = "palette"
    elif opts.colourmode is not None:
        opts.mode = "colour"
    else:
        opts.mode = "doom"

    in_dir = os.path.abspath(_strip_quotes(opts.input))
    out_parent = os.path.abspath(_strip_quotes(opts.output))
    out_dir = os.path.join(out_parent, OUTPUT_DIR_NAME)

    if not os.path.isdir(in_dir):
        print("%sERROR:%s input directory not found: %s" % (c.RED, c.OFF, in_dir))
        return 1
    if not (0 <= opts.softalpha <= 100):
        print("%sERROR:%s --softAlpha must be 0-100." % (c.RED, c.OFF))
        return 1
    if not (0 <= opts.tolerance <= 100):
        print("%sERROR:%s --tolerance must be 0-100." % (c.RED, c.OFF))
        return 1
    if (opts.wide or opts.allred) and opts.mode != "doom":
        print("%swarn%s   --wide/--allred only apply to --doomMode; ignored."
              % (c.YELLOW, c.OFF))

    # tolerance -> derived colourMode thresholds (25 reproduces the
    # classic 14 degrees / 0.55 saturation floor)
    if opts.hue_tol is None:
        opts.hue_tol = 6.0 + opts.tolerance * 0.32
    if opts.sat_min is None:
        opts.sat_min = max(0.05, 0.75 - opts.tolerance * 0.008)

    exts = {"." + e.strip().lstrip(".").lower()
            for e in opts.ext.split(",") if e.strip()}

    # ---- build the blood set / base colours per mode
    blood_set = None
    opts.base_hues = [0.0]
    if opts.mode == "doom":
        palette = _decode_embedded_palette()
        opts.full_palette = palette
        explicit = opts.doommode if opts.doommode else []
        if explicit:
            if opts.wide or opts.allred:
                print("%swarn%s   explicit doomMode indices override "
                      "--wide/--allred; ignored." % (c.YELLOW, c.OFF))
            try:
                indices = parse_index_specs(explicit)
            except ValueError as e:
                print("%sERROR:%s %s" % (c.RED, c.OFF, e))
                return 1
            blood_set = set(palette[i] for i in indices)
            blood_set.discard((0, 0, 0))
            if not blood_set:
                print("%sERROR:%s the chosen indices contain no usable "
                      "colours (all black?)." % (c.RED, c.OFF))
                return 1
            tier = "%d explicit indices" % len(indices)
        elif opts.allred:
            if opts.wide:
                print("%swarn%s   --allred supersedes --wide."
                      % (c.YELLOW, c.OFF))
            blood_set = set(palette[i] for i in ALLRED_INDICES)
            blood_set.discard((0, 0, 0))
            tier = "allred (%d indices)" % len(ALLRED_INDICES)
        elif opts.wide:
            blood_set = build_doom_blood_set(palette, True, 0.55, 14.0)
            tier = "wide"
        else:
            blood_set = build_doom_blood_set(palette, False, 0.55, 14.0)
            tier = "red ramp"
        mode_desc = "doomMode [embedded Doom2 PLAYPAL], %s -> %d colours" % (
            tier, len(blood_set))
    elif opts.mode == "palette":
        if len(opts.palettemode) < 2:
            print("%sERROR:%s --paletteMode needs a palette file AND at "
                  "least one index/range." % (c.RED, c.OFF))
            return 1
        pal_file = opts.palettemode[0]
        try:
            palette = load_palette(pal_file)
            indices = parse_index_specs(opts.palettemode[1:])
        except ValueError as e:
            print("%sERROR:%s %s" % (c.RED, c.OFF, e))
            return 1
        opts.full_palette = palette
        blood_set = set(palette[i] for i in indices)
        blood_set.discard((0, 0, 0))
        mode_desc = "paletteMode [%s], %d indices -> %d colours" % (
            os.path.basename(_strip_quotes(pal_file)), len(indices),
            len(blood_set))
        if not blood_set:
            print("%sERROR:%s the chosen indices contain no usable colours "
                  "(all black?)." % (c.RED, c.OFF))
            return 1
    else:  # colour
        try:
            bases = parse_colour_tokens(opts.colourmode)
        except ValueError as e:
            print("%sERROR:%s %s" % (c.RED, c.OFF, e))
            return 1
        opts.base_hues = []
        names = []
        for rgb in bases:
            h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0,
                                          rgb[2] / 255.0)
            if s < 0.2:
                print("%sERROR:%s base colour %02X%02X%02X is too grey -- "
                      "hue matching needs a saturated colour."
                      % ((c.RED, c.OFF) + rgb))
                return 1
            opts.base_hues.append(h * 360.0)
            names.append("#%02X%02X%02X" % rgb)
        opts.full_palette = []
        mode_desc = ("colourMode base %s, hue +/-%.0f deg, sat >= %.2f"
                     % (" ".join(names), opts.hue_tol, opts.sat_min))

    print("%sBLOODSPLIT%s  mode: %s" % (c.BOLD, c.OFF, mode_desc))
    print("scan:  %s" % in_dir)
    print("out:   %s" % out_dir)
    print()

    scanned = written = bloodless = errors = 0
    composites = 0
    not_clean = 0
    written_paths = set()

    for root, dirs, files in os.walk(in_dir):
        # never descend into any _BloodSplit or __CompositeFiles tree
        # (this run's or a previous run's), nor the current output dir
        dirs[:] = [d for d in dirs
                   if d != OUTPUT_DIR_NAME
                   and d != COMPOSITE_DIR_NAME
                   and os.path.abspath(os.path.join(root, d)) != out_dir]
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in exts:
                continue
            src = os.path.join(root, name)
            scanned += 1
            try:
                with Image.open(src) as img:
                    result, count, clean, comp = process_image(img, opts,
                                                               blood_set)
            except Exception as e:
                errors += 1
                print("%serror%s  %s  (%s)" % (c.RED, c.OFF,
                                               os.path.relpath(src, in_dir), e))
                continue
            if result is None:
                bloodless += 1
                if not clean:
                    not_clean += 1
                continue
            rel = os.path.relpath(root, in_dir)
            dest_dir = os.path.join(out_dir, rel) if rel != "." else out_dir
            stem = os.path.splitext(name)[0]
            dest = os.path.join(dest_dir, stem + ".png")
            key = os.path.normcase(dest)
            if key in written_paths:
                print("%swarn%s   %s  (name collision, skipped)"
                      % (c.YELLOW, c.OFF, os.path.relpath(src, in_dir)))
                errors += 1
                continue
            os.makedirs(dest_dir, exist_ok=True)
            result.save(dest, "PNG")
            written_paths.add(key)
            written += 1
            print("%sblood%s  %s  (%d px)"
                  % (c.GREEN, c.OFF, os.path.relpath(dest, out_dir), count))
            if comp is not None:
                if opts.saveallmoved:
                    cdir = os.path.join(out_dir, COMPOSITE_DIR_NAME)
                    cdir = os.path.join(cdir, rel) if rel != "." else cdir
                else:
                    cdir = dest_dir
                cdest = os.path.join(cdir, stem + "--composite.png")
                ckey = os.path.normcase(cdest)
                if ckey in written_paths:
                    print("%swarn%s   %s  (composite name collision, skipped)"
                          % (c.YELLOW, c.OFF, os.path.relpath(src, in_dir)))
                    errors += 1
                else:
                    os.makedirs(cdir, exist_ok=True)
                    comp.save(cdest, "PNG")
                    written_paths.add(ckey)
                    composites += 1
                    print("%scomp%s   %s"
                          % (c.CYAN, c.OFF, os.path.relpath(cdest, out_dir)))

    print()
    summary = ("%sDONE%s  scanned %d, written %d, bloodless %d, errors %d"
               % (c.BOLD, c.OFF, scanned, written, bloodless, errors))
    if opts.saveall:
        summary += ", composites %d" % composites
    print(summary)
    if written == 0 and scanned > 0 and bloodless == scanned:
        print("No blood found in any file.")
    if opts.mode != "colour" and not_clean > 0:
        print("%sNOTE:%s %d bloodless file(s) do not look palette-clean --"
              " if they should contain blood, try %s--colourMode%s."
              % (c.YELLOW, c.OFF, not_clean, c.BOLD, c.OFF))
    return 0


if __name__ == "__main__":
    sys.exit(main())