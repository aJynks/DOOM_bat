#!/usr/bin/env python3
"""
cleanpal - realtime Doom pal0 duplicate / similar colour cleaner (GUI)

Loads pal0 from a WAD (PLAYPAL), SLADE playpal.pal / pal0.pal, SLADE pal0.png,
DoomTools playpal.png or a COLORMAP image (line 0), and shows it as a SLADE
style 16x16 grid.

Matching runs in order:
  1. Remove exact   - exact RGB copies removed, first occurrence kept
  2. Remove similar - runs only on what stage 1 left. Transitive clusters,
                      lowest index kept. CIEDE2000 (default), CIE Lab
                      dE76 or weighted RGB.
  Align             - packs the kept colours toward index 0

Sort into ramps: reorders the palette (or a selection, gathered into one
block) with one of several methods - Curved ramps (default), Line ramps,
Shade families, Hue bands, Stepped hue, Gradient path, Single key, Reverse.
Preview / Apply / Cancel; Apply adds a history entry.
cleanpal --ramptest <palette> scores every method on a shuffled palette.

Ramp tool: fills selected cells (blank or filled) with a multi-node gradient
(OKLab / RGB / OKLCH, easing), with a popup colour picker (RGB sliders, HSL
sliders, HSL wheel, screen eyedropper) and a scratch palette of named sets.
Projects (.cleanpal) save every snapshot plus all settings.

Exports: DoomTools playpal.png (tinted), DoomTools blank playpal.png,
SLADE pal0.png, SLADE pal0.pal, SLADE playpal.pal (tinted), Analysis PNGs.
Removed / empty slots are transparent in PNGs and green (0,255,0) in .pal.
"""

import heapq
import json
import math
import os
import struct
import sys

VERSION = "1.9.1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "cleanpal")
SETTINGS_PATH = os.path.join(APP_DIR, "cleanpal_settings.json")
LEGACY_SETTINGS_PATH = os.path.join(SCRIPT_DIR, "cleanpal_settings.json")
PRESET_DIR = os.path.join(APP_DIR, "presets")
PRESET_MARKER = "cleanpal_preset"


# ============================================================ help (no deps)
def _ansi_ok():
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")  # enable VT processing on Win10+
    return True


def print_help():
    c = _ansi_ok()

    def k(code, s):
        return "\033[%sm%s\033[0m" % (code, s) if c else s

    def H(s):
        return k("1;33", s)

    def C(s):
        return k("36", s)

    def D(s):
        return k("90", s)

    out = [
        "",
        k("1;37", "cleanpal") + "  v%s   " % VERSION
        + D("realtime pal0 duplicate / similar colour cleaner"),
        "",
        H("USAGE"),
        "  " + C("cleanpal") + " [input]",
        "",
        "  Opens the GUI. With an input file it loads straight into the",
        "  viewer, otherwise use the Open button.",
        "",
        H("INPUTS") + D("  (pal0 = the first 256 colours)"),
        "  " + C(".wad") + "   WAD containing a PLAYPAL lump",
        "  " + C(".cleanpal") + "  cleanpal project (history + settings)",
        "  " + C(".pal") + "   SLADE playpal.pal (N x 768 bytes) or pal0.pal (768 bytes)",
        "  " + C(".png") + "   SLADE pal0.png         16x16 grid (128x128 or scaled square)",
        "         DoomTools playpal.png  256x14, row 0",
        "         COLORMAP image         256x34, line 0",
        "",
        H("MATCHING") + D("  (runs in order)"),
        "  " + C("1. Remove exact") + "     exact RGB copies removed, first occurrence kept",
        "  " + C("2. Remove similar") + "   works on what stage 1 left; transitive clusters,",
        "                      lowest index kept. CIEDE2000 (default 1.5),",
        "                      CIE Lab dE76 (2.0) or weighted RGB (1.1)",
        "  " + C("Align") + "              packs kept colours toward index 0",
        "",
        H("SORT INTO RAMPS") + D("  (GUI panel, Preview / Apply / Cancel)"),
        "  " + C("Curved ramps") + "     default - chains each colour to its nearest darker",
        "                   neighbour, allowing hue-shifted (bending) ramps",
        "  " + C("Line ramps") + "       repeatedly fits straight lines through RGB space",
        "  " + C("Shade families") + "   groups by R:G:B ratio (scaled toward black)",
        "  " + C("Hue bands") + "        greys, then hue groups by lightness",
        "  " + C("Stepped hue") + "      Zucconi hue x lightness buckets (smooth grid)",
        "  " + C("Gradient path") + "    one smooth nearest-colour chain",
        "  " + C("Single key") + "       plain sort by lightness, hue, R, G, B, ...",
        "  " + C("Reverse") + "          reverses the order",
        "  Whole palette, or Selected: the selection is sorted and gathered into",
        "  one block starting at the first selected slot.",
        "",
        H("RAMP TOOL / PICKER / SCRATCH") + D("  (GUI, top bar buttons)"),
        "  " + C("Ramp tool") + "        select cells (blank or filled), set start / end",
        "                   colours, add nodes, blend OKLab / RGB / OKLCH, ease",
        "                   in / out; one ramp step per selected cell",
        "  " + C("Colour picker") + "    popup: RGB sliders, HSL sliders, HSL wheel; hex,",
        "                   screen eyedropper, recent colours; live editing",
        "  " + C("Scratch palette") + "  named sets of temporary swatches; drag onto the",
        "                   grid, ramp nodes or the picker; import / export .gpl",
        "",
        H("PROJECTS"),
        "  " + C("Save project") + " writes a .cleanpal file: every snapshot, the",
        "  current entry, deleted marks, selection, all settings, ramp and scratch",
        "  sets. Open it like any palette:  " + C("cleanpal mywork.cleanpal"),
        "",
        H("RAMP TEST"),
        "  " + C("cleanpal --ramptest <palette> [folder]"),
        "  Shuffles the palette, runs every method, scores how many of the",
        "  palette's own ramps come back intact and writes a comparison PNG",
        "  (<name>_ramptest.png, current folder by default). No GUI.",
        "",
        H("EXPORTS"),
        "  " + C("DoomTools playpal.png") + "        256x14, Doom red / gold / green tints",
        "  " + C("DoomTools blank playpal.png") + "  256x14, pal0 in every row",
        "  " + C("SLADE pal0.png") + "               128x128 grid",
        "  " + C("SLADE pal0.pal") + "               768 bytes",
        "  " + C("SLADE playpal.pal") + "            14 x 768 bytes, tinted",
        "  " + C("Analysis PNGs") + "                -identical- / -simular- / -aligned- (+ split)",
        "  " + D("Removed / empty slots: transparent in PNGs, green (0,255,0) in .pal"),
        "",
        H("SETTINGS"),
        "  Saved on exit to %APPDATA%\\cleanpal\\cleanpal_settings.json.",
        "  Save / Load preset buttons store matching, sort + export setups as .json",
        "  (default folder %APPDATA%\\cleanpal\\presets).",
        "",
        H("EXAMPLES"),
        "  " + C("cleanpal") + "                       " + D("open empty, pick a file"),
        "  " + C("cleanpal PLAYPAL.png") + "           " + D("DoomTools playpal / SLADE pal0.png"),
        "  " + C("cleanpal doom2.wad") + "             " + D("pal0 from the PLAYPAL lump"),
        "  " + C("cleanpal --ramptest doom2.wad") + "  " + D("compare the sort methods"),
        "  " + C('cleanpal "D:\\Pal0\\playpal.pal"') + "  " + D("SLADE binary palette"),
        "",
    ]
    print("\n".join(out))


# ============================================================ dependency check
def _dep_check():
    missing = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter is missing - reinstall Python with the 'tcl/tk and IDLE' option.")
        sys.exit(1)
    if not missing:
        try:
            from PIL import ImageTk  # noqa: F401
        except ImportError:
            print("Pillow's ImageTk is missing - reinstall with: "
                  "pip install --force-reinstall Pillow")
            sys.exit(1)
    if missing:
        print("Missing dependencies: " + ", ".join(missing))
        print("Install with: pip install " + " ".join(missing))
        sys.exit(1)


# ============================================================ constants
ENTRIES = 256
GREEN = (0, 255, 0)
METRICS = ("de2000", "lab", "rgb")
METRIC_LABEL = {"de2000": "CIEDE2000", "lab": "CIE Lab dE76", "rgb": "Weighted RGB"}
METRIC_TOKEN = {"de2000": "DE2000", "lab": "CIE", "rgb": "RGB"}
METRIC_HOVER = {"de2000": "dE00", "lab": "dE", "rgb": "dRGB"}
DEFAULT_TOL = {"de2000": 1.5, "lab": 2.0, "rgb": 1.1}
TOL_RANGE = {"de2000": (10.0, 0.05), "lab": (10.0, 0.05), "rgb": (5.0, 0.05)}  # (max, step)
SETTINGS_VERSION = 2

# Doom dcolors.c palette shifts: (target, fraction) per palette, index 0 = none
TINTS = (
    [None]
    + [((255, 0, 0), i / 9.0) for i in range(1, 9)]        # 1-8  pain
    + [((215, 186, 69), i * 0.125) for i in range(1, 5)]   # 9-12 item pickup
    + [((0, 256, 0), 0.125)]                               # 13   radsuit
)

EXPORTS = [
    # label, name suffix, extension
    ("DoomTools playpal.png", "_playpal", ".png"),
    ("DoomTools blank playpal.png", "_playpal-blank", ".png"),
    ("SLADE pal0.png", "_pal0", ".png"),
    ("SLADE pal0.pal", "_pal0", ".pal"),
    ("SLADE playpal.pal", "_playpal", ".pal"),
    ("Analysis PNGs (identical / simular / aligned)", None, None),
]
EXPORT_LABELS = [e[0] for e in EXPORTS]


def fmt_tol(v):
    s = ("%.3f" % v).rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


# ============================================================ colour maths
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


def dist_lab(la, lb):
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(la, lb)))


def dist_rgb(ca, cb):
    dr, dg, db = (abs(p - q) for p, q in zip(ca, cb))
    return math.sqrt((0.299 * dr) ** 2 + (0.587 * dg) ** 2 + (0.114 * db) ** 2)


def dist_de2000(l1, l2):
    """CIEDE2000 colour difference (Sharma et al. 2005), kL = kC = kH = 1."""
    L1, a1, b1 = l1
    L2, a2, b2 = l2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    cb7 = ((C1 + C2) / 2.0) ** 7
    G = 0.5 * (1 - math.sqrt(cb7 / (cb7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(b, ap):
        if b == 0 and ap == 0:
            return 0.0
        return math.degrees(math.atan2(b, ap)) % 360.0

    h1p, h2p = hue(b1, a1p), hue(b2, a2p)
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

    Lbp = (L1 + L2) / 2.0
    Cbp = (C1p + C2p) / 2.0
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2.0
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2.0
    else:
        hbp = (h1p + h2p - 360) / 2.0

    T = (1 - 0.17 * math.cos(math.radians(hbp - 30))
         + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6))
         - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-((hbp - 275) / 25.0) ** 2)
    cbp7 = Cbp ** 7
    Rc = 2 * math.sqrt(cbp7 / (cbp7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    tl, tc, th = dLp / Sl, dCp / Sc, dHp / Sh
    return math.sqrt(max(tl * tl + tc * tc + th * th + Rt * tc * th, 0.0))


def metric_dist(metric, rgb_a, rgb_b, lab_a, lab_b):
    if metric == "de2000":
        return dist_de2000(lab_a, lab_b)
    if metric == "lab":
        return dist_lab(lab_a, lab_b)
    return dist_rgb(rgb_a, rgb_b)


def tint(c, spec):
    if spec is None or c is None:
        return c
    target, f = spec
    return tuple(max(0, min(255, int(v + (t - v) * f))) for v, t in zip(c, target))


# ============================================================ union-find
class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # lower index becomes root (cosmetic; groups are sorted anyway)
            if ra < rb:
                self.p[rb] = ra
            else:
                self.p[ra] = rb


# ============================================================ loaders
def _wad_playpal(path):
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
        name = data[off + 8: off + 16].split(b"\x00")[0].decode("ascii", "replace")
        if name.upper() == "PLAYPAL":
            if size < 768:
                raise ValueError("PLAYPAL lump is smaller than 768 bytes.")
            return data[filepos: filepos + size]
    raise ValueError("No PLAYPAL lump found in WAD.")


def _triples(raw):
    return [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i in range(ENTRIES)]


def _looks_like_grid(px, w):
    """True if a square image is made of uniform 16x16 cells (SLADE style)."""
    cell = w // 16
    if cell < 2:
        return True
    uniform = 0
    for idx in range(ENTRIES):
        gx, gy = idx % 16, idx // 16
        y = gy * cell + cell // 2
        x0 = gx * cell
        row = [px[x0 + dx, y] for dx in range(1, cell - 1)] or [px[x0, y]]
        if all(p == row[0] for p in row):
            uniform += 1
    return uniform >= ENTRIES * 0.9


def load_palette(path):
    """Returns (list of 256 RGB tuples, source label)."""
    from PIL import Image

    ext = os.path.splitext(path)[1].lower()

    if ext == ".wad":
        raw = _wad_playpal(path)
        return _triples(raw), "WAD PLAYPAL (%d palettes)" % (len(raw) // 768)

    if ext == ".pal":
        with open(path, "rb") as fh:
            raw = fh.read()
        if len(raw) < 768 or len(raw) % 768:
            raise ValueError("PAL size (%d bytes) is not a multiple of 768." % len(raw))
        n = len(raw) // 768
        label = "SLADE pal0.pal (single palette)" if n == 1 \
            else "SLADE playpal.pal (%d palettes)" % n
        return _triples(raw), label

    if ext == ".png":
        im = Image.open(path).convert("RGB")
        w, h = im.size
        px = im.load()
        is_grid = (w == h and w % 16 == 0 and w >= 16
                   and (w != 256 or _looks_like_grid(px, w)))
        if is_grid:
            cell = w // 16
            rgbs = [px[(i % 16) * cell + cell // 2, (i // 16) * cell + cell // 2]
                    for i in range(ENTRIES)]
            return rgbs, "SLADE pal0.png (%dx%d grid, %dpx cells)" % (w, h, cell)
        if w == 256:
            rgbs = [px[i, 0] for i in range(ENTRIES)]
            if h == 14:
                label = "DoomTools playpal.png (14 palettes)"
            elif h in (32, 33, 34):
                label = "COLORMAP image (256x%d, line 0)" % h
            elif h == 1:
                label = "256x1 palette strip"
            else:
                label = "256x%d palette image (row 0)" % h
            return rgbs, label
        raise ValueError("Unexpected PNG size %dx%d. Expected a 16x16 grid "
                         "(SLADE) or 256 wide (DoomTools / COLORMAP)." % (w, h))

    raise ValueError("Unsupported input: %s (use .wad, .pal or .png)" % ext)


def build_pairs(rgbs):
    """Sorted (distance, a, b) lists for every metric, exact pairs excluded."""
    labs = [srgb_to_lab(*c) if c is not None else None for c in rgbs]
    out = {m: [] for m in METRICS}
    for a in range(ENTRIES):
        if rgbs[a] is None:
            continue
        for b in range(a + 1, ENTRIES):
            if rgbs[b] is None or rgbs[a] == rgbs[b]:
                continue
            out["de2000"].append((dist_de2000(labs[a], labs[b]), a, b))
            out["lab"].append((dist_lab(labs[a], labs[b]), a, b))
            out["rgb"].append((dist_rgb(rgbs[a], rgbs[b]), a, b))
    for v in out.values():
        v.sort()
    return labs, out


# ============================================================ analysis
def analyse(rgbs, pairs, do_exact, do_similar, tol, selection=None, deleted=None):
    """rgbs may contain None (empty slots). selection: None = similar matching
    works on the whole palette; a set = only those colours (they can only
    merge with each other; an empty set culls nothing)."""
    status = ["kept" if c is not None else "empty" for c in rgbs]
    for i in deleted or ():
        if status[i] == "kept":
            status[i] = "deleted"  # manual delete: out of all matching
    owner = list(range(ENTRIES))
    identical, similar = [], []

    if do_exact:
        first = {}
        groups = {}
        for i, c in enumerate(rgbs):
            if status[i] != "kept":
                continue
            if c in first:
                status[i] = "exact"
                owner[i] = first[c]
                groups[first[c]].append(i)
            else:
                first[c] = i
                groups[i] = [i]
        identical = sorted(g for g in groups.values() if len(g) > 1)

        if do_similar:
            alive = [status[i] == "kept" and (selection is None or i in selection)
                     for i in range(ENTRIES)]
            uf = UF(ENTRIES)
            for d, a, b in pairs:
                if d > tol:
                    break
                if alive[a] and alive[b]:
                    uf.union(a, b)
            clusters = {}
            for i in range(ENTRIES):
                if alive[i]:
                    clusters.setdefault(uf.find(i), []).append(i)
            for g in clusters.values():
                if len(g) > 1:
                    similar.append(g)
                    for i in g[1:]:
                        status[i] = "similar"
                        owner[i] = g[0]
            similar.sort()

    kept = [i for i in range(ENTRIES) if status[i] == "kept"]
    return {"status": status, "owner": owner, "identical": identical,
            "similar": similar, "kept": kept,
            "exact_all": identical, "similar_all": similar}


def result_entries(rgbs, res, align):
    if align:
        out = [rgbs[i] for i in res["kept"]]
        return out + [None] * (ENTRIES - len(out))
    return [rgbs[i] if res["status"][i] == "kept" else None for i in range(ENTRIES)]


# ============================================================ ramp sorting
def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklab(rgb):
    r, g, b = (_lin(float(v)) for v in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1.0 / 3.0), v) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


GREY_CHROMA = 0.025          # OKLab chroma below this = grey
JOIN_DIST = 0.10             # OKLab distance limit for joining an outlier
HUE_CUT = 10.0               # OKLab hue where the wheel starts (just below red)


def _hsv(rgb):
    r, g, b = (v / 255.0 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0, (d / mx if mx else 0.0), mx


class _Col:
    __slots__ = ("rgb", "L", "a", "b", "C", "h", "hsv")

    def __init__(self, rgb):
        self.rgb = rgb
        self.L, self.a, self.b = oklab(rgb)
        self.C = math.hypot(self.a, self.b)
        self.h = math.degrees(math.atan2(self.b, self.a)) % 360.0
        self.hsv = _hsv(rgb)


SORT_KEYS = {
    "Lightness (OKLab)": lambda c: c.L,
    "Hue": lambda c: (c.h - HUE_CUT) % 360.0,
    "Saturation": lambda c: c.hsv[1],
    "Chroma (OKLab)": lambda c: c.C,
    "Red": lambda c: c.rgb[0],
    "Green": lambda c: c.rgb[1],
    "Blue": lambda c: c.rgb[2],
    "R+G+B": lambda c: sum(c.rgb),
    "R\u00b2+G\u00b2+B\u00b2": lambda c: sum(v * v for v in c.rgb),
}
SORT_KEY_NAMES = list(SORT_KEYS)

RAMP_ORDERS = ["Greys first, then hue", "Original position", "Largest first",
               "By key (ramp's highest value)"]
OUTLIER_MODES = ["Join nearest ramp", "Collect at end", "Leave single"]

# method: (label, kind, [(param, label, default, lo, hi, step), ...])
SORT_METHODS = [
    ("Curved ramps", "ramps", [
        ("max_step", "Max step (OKLab x100)", 25.0, 1.0, 40.0, 0.5),
        ("bend", "Max bend (degrees)", 110.0, 5.0, 180.0, 5.0),
        ("hue_weight", "Hue/chroma weight", 3.0, 0.5, 8.0, 0.5),
    ]),
    ("Line ramps", "ramps", [
        ("tol", "Line tolerance (RGB)", 4.0, 1.0, 64.0, 1.0),
        ("gap", "Max gap (RGB)", 48.0, 4.0, 255.0, 4.0),
    ]),
    ("Shade families", "ramps", [
        ("tol", "Ratio tolerance (x100)", 2.0, 0.5, 40.0, 0.5),
    ]),
    ("Hue bands", "ramps", [
        ("width", "Max band width (degrees)", 35.0, 5.0, 180.0, 5.0),
    ]),
    ("Stepped hue", "plain", [
        ("steps", "Buckets", 8.0, 2.0, 32.0, 1.0),
    ]),
    ("Gradient path", "plain", []),
    ("Single key", "plain", []),
    ("Reverse", "plain", []),
]
SORT_METHOD_NAMES = [m[0] for m in SORT_METHODS]
SORT_METHOD_INFO = {m[0]: m for m in SORT_METHODS}


def default_sort_params():
    return {m: {p[0]: p[2] for p in spec} for m, _k, spec in SORT_METHODS}


# ------------------------------------------------------------ helpers
def _d2(p, q):
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


def _lab_d(c1, c2):
    return math.sqrt((c1.L - c2.L) ** 2 + (c1.a - c2.a) ** 2 + (c1.b - c2.b) ** 2)


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _groups(uf, n):
    g = {}
    for i in range(n):
        g.setdefault(uf.find(i), []).append(i)
    return list(g.values())


# ------------------------------------------------------------ curved ramps
def _ramps_curved(cols, p):
    """Greedy minimum path cover: every colour links to at most one darker
    and one lighter neighbour, cheapest links first, with a bend limit."""
    n = len(cols)
    step = p["max_step"] / 100.0
    w = p["hue_weight"]
    cosmax = math.cos(math.radians(p["bend"]))
    vec = [(c.L, c.a * w, c.b * w) for c in cols]
    rank = sorted(range(n), key=lambda i: (-cols[i].L, i))
    pos = [0] * n
    for k, i in enumerate(rank):
        pos[i] = k
    edges = []
    for i in range(n):
        for j in range(n):
            if pos[j] > pos[i]:              # j is darker
                d = math.sqrt(_d2(vec[i], vec[j]))
                if 1e-9 < d <= step:
                    edges.append((d, i, j))
    edges.sort()
    nxt = [-1] * n
    prv = [-1] * n

    def bend_ok(a, b, c):
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - b[k] for k in range(3)]
        nu = math.sqrt(sum(x * x for x in u))
        nv = math.sqrt(sum(x * x for x in v))
        if nu < 1e-9 or nv < 1e-9:
            return True
        return sum(u[k] * v[k] for k in range(3)) / (nu * nv) >= cosmax

    for d, i, j in edges:
        if nxt[i] != -1 or prv[j] != -1:
            continue
        if prv[i] != -1 and not bend_ok(vec[prv[i]], vec[i], vec[j]):
            continue
        if nxt[j] != -1 and not bend_ok(vec[i], vec[j], vec[nxt[j]]):
            continue
        nxt[i] = j
        prv[j] = i
    ramps = []
    for i in range(n):
        if prv[i] == -1:
            r = [i]
            while nxt[r[-1]] != -1:
                r.append(nxt[r[-1]])
            ramps.append(r)
    return ramps


# ------------------------------------------------------------ line ramps
def _fit_line(pts):
    n = len(pts)
    cx = sum(q[0] for q in pts) / n
    cy = sum(q[1] for q in pts) / n
    cz = sum(q[2] for q in pts) / n
    xx = xy = xz = yy = yz = zz = 0.0
    for x, y, z in pts:
        x -= cx; y -= cy; z -= cz
        xx += x * x; xy += x * y; xz += x * z
        yy += y * y; yz += y * z; zz += z * z
    v = (1.0, 1.0, 1.0)
    for _ in range(30):                      # power iteration
        v = (xx * v[0] + xy * v[1] + xz * v[2],
             xy * v[0] + yy * v[1] + yz * v[2],
             xz * v[0] + yz * v[1] + zz * v[2])
        nv = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        if nv < 1e-12:
            return (cx, cy, cz), None
        v = (v[0] / nv, v[1] / nv, v[2] / nv)
    return (cx, cy, cz), v


def _line_run(pts, idxs, origin, d, tol2, gap, must=None):
    """Points of idxs within tol of the line, split at gaps; returns the
    longest run (or the run containing `must`)."""
    ox, oy, oz = origin
    dx, dy, dz = d
    hits = []
    for i in idxs:
        x, y, z = pts[i]
        vx, vy, vz = x - ox, y - oy, z - oz
        t = vx * dx + vy * dy + vz * dz
        if vx * vx + vy * vy + vz * vz - t * t <= tol2:
            hits.append((t, i))
    if not hits:
        return []
    hits.sort()
    runs, cur = [], [hits[0]]
    for h in hits[1:]:
        if h[0] - cur[-1][0] > gap:
            runs.append(cur)
            cur = [h]
        else:
            cur.append(h)
    runs.append(cur)
    if must is not None:
        for r in runs:
            if any(i == must for _t, i in r):
                return [i for _t, i in r]
        return []
    best = max(runs, key=len)
    return [i for _t, i in best]


def _ramps_line(cols, p, min_size):
    """Sequential line fitting in RGB: take the longest gap-free run of
    colours lying on one line, remove it, repeat."""
    n = len(cols)
    pts = [tuple(float(v) for v in c.rgb) for c in cols]
    tol2 = p["tol"] ** 2
    gap = p["gap"]
    alive = set(range(n))
    seeds = set()
    k = 8
    for i in range(n):
        near = sorted((_d2(pts[i], pts[j]), j) for j in range(n) if j != i)
        for dd, j in near[:k]:
            if dd > 0:
                seeds.add((min(i, j), max(i, j)))
    # precompute each seed's refined line
    cands = []
    for a, b in seeds:
        pa, pb = pts[a], pts[b]
        L = math.sqrt(_d2(pa, pb))
        d = ((pb[0] - pa[0]) / L, (pb[1] - pa[1]) / L, (pb[2] - pa[2]) / L)
        run = _line_run(pts, alive, pa, d, tol2, gap, must=a)
        if len(run) >= 3:
            o, d2 = _fit_line([pts[i] for i in run])
            if d2 is not None:
                run2 = _line_run(pts, alive, o, d2, tol2, gap, must=a)
                if len(run2) >= len(run):
                    run, pa, d = run2, o, d2
        cands.append((pa, d, a))
    heap = []
    for ci, (o, d, a) in enumerate(cands):
        r = _line_run(pts, alive, o, d, tol2, gap)
        heapq.heappush(heap, (-len(r), ci))
    ramps = []
    while heap and alive:
        negsz, ci = heapq.heappop(heap)
        o, d, a = cands[ci]
        r = _line_run(pts, alive, o, d, tol2, gap)
        if len(r) != -negsz:                 # stale - re-queue
            if r:
                heapq.heappush(heap, (-len(r), ci))
            continue
        if len(r) < max(2, min_size):
            break
        if len(r) >= 3:                      # one refit on what's left
            o2, d2 = _fit_line([pts[i] for i in r])
            if d2 is not None:
                r2 = _line_run(pts, alive, o2, d2, tol2, gap)
                if len(r2) > len(r):
                    r = r2
        ramps.append(r)
        alive -= set(r)
    ramps.extend([i] for i in sorted(alive))
    return ramps


# ------------------------------------------------------------ shade families
def _ramps_shade(cols, p):
    """Colours with the same R:G:B ratio (scaled toward black) group up."""
    n = len(cols)
    tol = p["tol"] / 100.0
    pts = []
    for c in cols:
        s = float(sum(c.rgb))
        pts.append((c.rgb[0] / s, c.rgb[1] / s) if s > 0 else None)
    uf = _UF(n)
    for i in range(n):
        if pts[i] is None or max(cols[i].rgb) < 24:
            continue                          # too dark to have a stable ratio
        for j in range(i + 1, n):
            if pts[j] is None or max(cols[j].rgb) < 24:
                continue
            if (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2 <= tol * tol:
                uf.union(i, j)
    return _groups(uf, n)


# ------------------------------------------------------------ hue bands
def _ramps_hue(cols, p):
    n = len(cols)
    greys = [i for i in range(n) if cols[i].C < GREY_CHROMA]
    rest = sorted((i for i in range(n) if cols[i].C >= GREY_CHROMA),
                  key=lambda i: (cols[i].h - HUE_CUT) % 360.0)
    ramps = [greys] if greys else []
    if not rest:
        return ramps
    hs = [(cols[i].h - HUE_CUT) % 360.0 for i in rest]
    gaps = sorted(((hs[k + 1] - hs[k], k) for k in range(len(rest) - 1)), reverse=True)
    cuts = set()
    width = p["width"]

    def split(lo, hi):                       # inclusive index range of rest
        if hs[hi] - hs[lo] <= width or hi == lo:
            return
        k = max(range(lo, hi), key=lambda k: hs[k + 1] - hs[k])
        cuts.add(k)
        split(lo, k)
        split(k + 1, hi)

    # natural gaps (> 8 degrees) first, then widen-split
    nat = sorted(k for g, k in gaps if g > 8.0)
    bounds = [-1] + nat + [len(rest) - 1]
    for a, b in zip(bounds, bounds[1:]):
        cuts.add(b)
        split(a + 1, b)
    cur = []
    for k, i in enumerate(rest):
        cur.append(i)
        if k in cuts:
            ramps.append(cur)
            cur = []
    if cur:
        ramps.append(cur)
    return ramps


# ------------------------------------------------------------ plain orders
def _order_stepped(cols, p, lightest_first):
    reps = int(p["steps"])

    def key(i):
        c = cols[i]
        h, s, v = c.hsv
        r, g, b = c.rgb
        lum = math.sqrt(.241 * r * r + .691 * g * g + .068 * b * b) / 255.0
        h2 = int(((h - 10.0) % 360.0) / 360.0 * reps)
        l2 = int(lum * reps)
        v2 = int(v * reps)
        if c.C < GREY_CHROMA:
            h2 = -1
        if (h2 % 2 == 1) == lightest_first:
            l2, v2 = -l2, -v2
        return (h2, l2, v2, lum if not lightest_first else -lum)
    return sorted(range(len(cols)), key=key)


def _order_path(cols, lightest_first):
    n = len(cols)
    if n < 3:
        return sorted(range(n), key=lambda i: -cols[i].L if lightest_first else cols[i].L)
    D = [[_lab_d(cols[i], cols[j]) for j in range(n)] for i in range(n)]
    start = max(range(n), key=lambda i: cols[i].L if lightest_first else -cols[i].L)
    path = [start]
    left = set(range(n)) - {start}
    while left:
        last = path[-1]
        nx = min(left, key=lambda j: D[last][j])
        path.append(nx)
        left.discard(nx)
    # 2-opt (open path, first element fixed)
    for _ in range(12):
        improved = False
        for i in range(1, n - 1):
            a, b = path[i - 1], path[i]
            for j in range(i + 1, n):
                c = path[j]
                d = path[j + 1] if j + 1 < n else None
                old = D[a][b] + (D[c][d] if d is not None else 0.0)
                new = D[a][c] + (D[b][d] if d is not None else 0.0)
                if new < old - 1e-12:
                    path[i:j + 1] = reversed(path[i:j + 1])
                    a, b = path[i - 1], path[i]
                    improved = True
        if not improved:
            break
    return path


# ------------------------------------------------------------ shared finish
def _finish(cols, ramps, min_size, key, high_first, ramp_order, outliers, orig_pos):
    real = [r for r in ramps if len(r) >= min_size]
    loose = [i for r in ramps if len(r) < min_size for i in r]
    if not real:
        real, loose = [loose], []
    tail = []
    if outliers == "Join nearest ramp":
        adds = []
        for i in loose:
            best, br = None, 0
            for k, r in enumerate(real):
                d = min(_lab_d(cols[i], cols[j]) for j in r)
                if best is None or d < best:
                    best, br = d, k
            if best <= JOIN_DIST:
                adds.append((br, i))
            else:
                real.append([i])              # nothing close: stays single
        for br, i in adds:
            real[br].append(i)
    elif outliers == "Collect at end":
        tail = loose
    else:
        real.extend([i] for i in loose)
    kf = SORT_KEYS[key]
    for r in real:
        r.sort(key=lambda i: (kf(cols[i]), -i), reverse=high_first)

    def grey(r):
        return sum(cols[i].C for i in r) / len(r) < GREY_CHROMA

    def mean_hue(r):
        x = sum(cols[i].a for i in r)
        y = sum(cols[i].b for i in r)
        return (math.degrees(math.atan2(y, x)) - HUE_CUT) % 360.0

    if ramp_order == "Greys first, then hue":
        real.sort(key=lambda r: (0, -max(cols[i].L for i in r)) if grey(r)
                  else (1, mean_hue(r), -max(cols[i].L for i in r)))
    elif ramp_order == "Original position":
        real.sort(key=lambda r: sum(orig_pos[i] for i in r) / len(r))
    elif ramp_order == "Largest first":
        real.sort(key=lambda r: (-len(r), mean_hue(r)))
    else:
        real.sort(key=lambda r: max(kf(cols[i]) for i in r), reverse=high_first)
    if tail:
        tail.sort(key=lambda i: kf(cols[i]), reverse=high_first)
        real.append(tail)
    return real


def ramp_sort(rgbs, method, params=None, key="Lightness (OKLab)", high_first=True,
              ramp_order="Greys first, then hue", outliers="Join nearest ramp",
              min_size=3):
    """rgbs: list of RGB tuples. Returns (order, n_ramps): order[k] = which
    input goes to position k. n_ramps is 0 for plain orderings."""
    n = len(rgbs)
    if n == 0:
        return [], 0
    cols = [_Col(tuple(c)) for c in rgbs]
    allp = default_sort_params()
    p = dict(allp.get(method, {}))
    if params:
        p.update(params)
    kind = SORT_METHOD_INFO[method][1]
    if kind == "plain":
        if method == "Reverse":
            return list(range(n - 1, -1, -1)), 0
        if method == "Single key":
            kf = SORT_KEYS[key]
            return sorted(range(n), key=lambda i: (kf(cols[i]), -i), reverse=high_first), 0
        if method == "Stepped hue":
            return _order_stepped(cols, p, high_first), 0
        if method == "Gradient path":
            return _order_path(cols, high_first), 0
    min_size = max(1, int(min_size))
    if method == "Curved ramps":
        ramps = _ramps_curved(cols, p)
    elif method == "Line ramps":
        ramps = _ramps_line(cols, p, min_size)
    elif method == "Shade families":
        ramps = _ramps_shade(cols, p)
    else:
        ramps = _ramps_hue(cols, p)
    real = _finish(cols, ramps, min_size, key, high_first, ramp_order, outliers,
                   list(range(n)))
    order = [i for r in real for i in r]
    return order, len(real)


# ============================================================ colour tools maths
def _unlin(c):
    c = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return min(max(c, 0.0), 1.0) * 255.0


def oklab_to_rgbf(L, a, b):
    """OKLab -> sRGB floats 0..255 (clipped)."""
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return _unlin(r), _unlin(g), _unlin(bb)


def rgb_round(c):
    return tuple(int(min(max(round(v), 0), 255)) for v in c)


def rgb_to_hsl(r, g, b):
    """0..255 floats -> (h 0..360, s 0..100, l 0..100)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    d = mx - mn
    if d < 1e-12:
        return 0.0, 0.0, l * 100.0
    s = d / (1.0 - abs(2.0 * l - 1.0)) if 0.0 < l < 1.0 else 0.0
    if mx == r:
        h = ((g - b) / d) % 6.0
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return (h * 60.0) % 360.0, min(s, 1.0) * 100.0, l * 100.0


def hsl_to_rgb(h, s, l):
    """(h 0..360, s 0..100, l 0..100) -> 0..255 floats."""
    s, l = s / 100.0, l / 100.0
    c = (1.0 - abs(2.0 * l - 1.0)) * s
    hp = (h % 360.0) / 60.0
    x = c * (1.0 - abs(hp % 2.0 - 1.0))
    r, g, b = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))[int(hp) % 6]
    m = l - c / 2.0
    return (r + m) * 255.0, (g + m) * 255.0, (b + m) * 255.0


def hex_of(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


def parse_colour(text):
    """'#EBEBEB', 'ebebeb', '#ebe', 'ebe', '235,235,235', '235 235 235'
    -> (r, g, b) or None."""
    t = text.strip().strip(";")
    if not t:
        return None
    parts = [p for p in t.replace(",", " ").replace("(", " ").replace(")", " ").split()]
    if parts and parts[0].lower() == "rgb":
        parts = parts[1:]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        v = [int(p) for p in parts]
        return tuple(v) if all(0 <= x <= 255 for x in v) else None
    h = t.lstrip("#").strip()
    if h.lower().startswith("0x"):
        h = h[2:]
    if len(h) in (3, 6) and all(ch in "0123456789abcdefABCDEF" for ch in h):
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return None


def parse_colour_list(text):
    out = []
    for line in text.splitlines():
        c = parse_colour(line)
        if c is not None:
            out.append(c)
            continue
        for tok in line.replace(",", " ").split():
            c = parse_colour(tok)
            if c is not None and (tok.startswith("#") or len(tok.lstrip("#")) in (3, 6)) \
                    and not tok.isdigit():
                out.append(c)
    return out


# ------------------------------------------------------------ ramp maker
RAMP_SPACES = ["OKLab", "RGB", "OKLCH (hue path)"]
RAMP_EASES = ["Linear", "Ease in", "Ease out", "Ease in-out"]
RAMP_EASE_SCOPES = ["Whole ramp", "Each segment"]


def default_ramp_state():
    return {"nodes": [{"pos": 0.0, "rgb": [255, 183, 183], "hsl": None},
                      {"pos": 1.0, "rgb": [167, 0, 0], "hsl": None}],
            "space": RAMP_SPACES[0], "ease": RAMP_EASES[0], "strength": 2.0,
            "ease_scope": RAMP_EASE_SCOPES[0]}


def clean_ramp_state(src):
    """Validated ramp state; raises ValueError on garbage."""
    if not isinstance(src, dict):
        raise ValueError("Bad ramp data.")
    st = default_ramp_state()
    nodes = src.get("nodes")
    if isinstance(nodes, list) and len(nodes) >= 2:
        out = []
        for n in nodes:
            if not isinstance(n, dict):
                raise ValueError("Bad ramp node.")
            rgb = n.get("rgb")
            pos = n.get("pos")
            if not (isinstance(rgb, (list, tuple)) and len(rgb) == 3
                    and all(isinstance(v, int) and 0 <= v <= 255 for v in rgb)):
                raise ValueError("Bad ramp node colour.")
            if isinstance(pos, bool) or not isinstance(pos, (int, float)):
                raise ValueError("Bad ramp node position.")
            hsl = n.get("hsl")
            if not (isinstance(hsl, (list, tuple)) and len(hsl) == 3
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                            for v in hsl)):
                hsl = None
            out.append({"pos": min(max(float(pos), 0.0), 1.0), "rgb": list(rgb),
                        "hsl": list(hsl) if hsl else None})
        out.sort(key=lambda n: n["pos"])
        out[0]["pos"], out[-1]["pos"] = 0.0, 1.0
        st["nodes"] = out
    for k, choices in (("space", RAMP_SPACES), ("ease", RAMP_EASES),
                       ("ease_scope", RAMP_EASE_SCOPES)):
        if src.get(k) in choices:
            st[k] = src[k]
    v = src.get("strength")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        st["strength"] = min(max(float(v), 1.0), 6.0)
    return st


def _ease(u, kind, p):
    if kind == "Ease in":
        return u ** p
    if kind == "Ease out":
        return 1.0 - (1.0 - u) ** p
    if kind == "Ease in-out":
        return 0.5 * (2.0 * u) ** p if u < 0.5 else 1.0 - 0.5 * (2.0 - 2.0 * u) ** p
    return u


def _mix(c1, c2, u, space):
    if space == "RGB":
        return tuple(c1[k] + (c2[k] - c1[k]) * u for k in range(3))
    l1, l2 = oklab(c1), oklab(c2)
    if space.startswith("OKLCH"):
        C1, C2 = math.hypot(l1[1], l1[2]), math.hypot(l2[1], l2[2])
        h1, h2 = math.atan2(l1[2], l1[1]), math.atan2(l2[2], l2[1])
        if C1 < 1e-4:
            h1 = h2
        if C2 < 1e-4:
            h2 = h1
        dh = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi     # shortest way round
        L = l1[0] + (l2[0] - l1[0]) * u
        C = C1 + (C2 - C1) * u
        h = h1 + dh * u
        return oklab_to_rgbf(L, C * math.cos(h), C * math.sin(h))
    return oklab_to_rgbf(*(l1[k] + (l2[k] - l1[k]) * u for k in range(3)))


def ramp_colour_at(state, t):
    """Float RGB at t (0..1) along the ramp."""
    nodes = state["nodes"]
    ease, p = state["ease"], state["strength"]
    per_seg = state["ease_scope"] == "Each segment"
    t = min(max(t, 0.0), 1.0)
    if not per_seg:
        t = _ease(t, ease, p)
    k = 0
    while k < len(nodes) - 2 and t > nodes[k + 1]["pos"]:
        k += 1
    a, b = nodes[k], nodes[k + 1]
    span = b["pos"] - a["pos"]
    u = 0.0 if span <= 1e-9 else (t - a["pos"]) / span
    u = min(max(u, 0.0), 1.0)
    if per_seg:
        u = _ease(u, ease, p)
    return _mix(tuple(a["rgb"]), tuple(b["rgb"]), u, state["space"])


def ramp_colours(state, n):
    if n <= 0:
        return []
    if n == 1:
        return [tuple(state["nodes"][0]["rgb"])]
    return [rgb_round(ramp_colour_at(state, k / (n - 1.0))) for k in range(n)]


# ------------------------------------------------------------ incremental pairs
def update_pairs(rgbs, labs, pairs, changed):
    """New (labs, pairs) after the colours at `changed` indices changed.
    Much faster than build_pairs when few entries change."""
    changed = set(changed)
    labs = list(labs)
    for i in changed:
        labs[i] = srgb_to_lab(*rgbs[i]) if rgbs[i] is not None else None
    out = {}
    for m in METRICS:
        keep = [t for t in pairs[m] if t[1] not in changed and t[2] not in changed]
        new = []
        for a in changed:
            if rgbs[a] is None:
                continue
            for b in range(ENTRIES):
                if b == a or rgbs[b] is None or rgbs[a] == rgbs[b]:
                    continue
                if b in changed and b < a:
                    continue                  # pair already done from b's side
                if m == "de2000":
                    d = dist_de2000(labs[a], labs[b])
                elif m == "lab":
                    d = dist_lab(labs[a], labs[b])
                else:
                    d = dist_rgb(rgbs[a], rgbs[b])
                new.append((d, min(a, b), max(a, b)))
        new.sort()
        out[m] = list(heapq.merge(keep, new))
    return labs, out


# ============================================================ writers
def rows_image(rows, force_rgba=False):
    from PIL import Image

    rgba = force_rgba or any(e is None for r in rows for e in r)
    im = Image.new("RGBA" if rgba else "RGB", (ENTRIES, len(rows)),
                   (0, 0, 0, 0) if rgba else (0, 0, 0))
    px = im.load()
    for y, row in enumerate(rows):
        for x, e in enumerate(row):
            if e is not None:
                px[x, y] = (e + (255,)) if rgba else e
    return im


def slade_image(entries, force_rgba=False, cell=8):
    from PIL import Image, ImageDraw

    rgba = force_rgba or any(e is None for e in entries)
    size = cell * 16
    im = Image.new("RGBA" if rgba else "RGB", (size, size),
                   (0, 0, 0, 0) if rgba else (0, 0, 0))
    dr = ImageDraw.Draw(im)
    for i, e in enumerate(entries):
        if e is None:
            continue
        x0, y0 = (i % 16) * cell, (i // 16) * cell
        dr.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1],
                     fill=(e + (255,)) if rgba else e)
    return im


def palette_rows(entries, tinted):
    return [[tint(e, spec) if tinted else e for e in entries] for spec in TINTS]


def pal_bytes(rows):
    out = bytearray()
    for row in rows:
        for e in row:
            out += bytes(e if e is not None else GREEN)
    return bytes(out)


def write_export(label, path, entries):
    if label == "DoomTools playpal.png":
        rows_image(palette_rows(entries, True)).save(path)
    elif label == "DoomTools blank playpal.png":
        rows_image(palette_rows(entries, False)).save(path)
    elif label == "SLADE pal0.png":
        slade_image(entries).save(path)
    elif label == "SLADE pal0.pal":
        with open(path, "wb") as fh:
            fh.write(pal_bytes([entries]))
    elif label == "SLADE playpal.pal":
        with open(path, "wb") as fh:
            fh.write(pal_bytes(palette_rows(entries, True)))
    else:
        raise ValueError("Unknown export: %s" % label)


def write_analysis(outdir, stem, token, rgbs, res, exact_on, similar_on, split):
    written = []

    def ents(idxs):
        e = [None] * ENTRIES
        for i in idxs:
            e[i] = rgbs[i]
        return e

    def save(entries, name):
        p = os.path.join(outdir, name)
        slade_image(entries, force_rgba=True).save(p)
        written.append(p)

    exact_on = exact_on or bool(res["exact_all"])        # include snapshot removals
    similar_on = similar_on or bool(res["similar_all"])
    if exact_on:
        save(ents(i for g in res["exact_all"] for i in g[1:]),
             "%s-identical-%s.png" % (stem, token))
    if similar_on:
        save(ents(i for g in res["similar_all"] for i in g[1:]),
             "%s-simular-%s.png" % (stem, token))
    packed = [rgbs[i] for i in res["kept"]]
    save(packed + [None] * (ENTRIES - len(packed)),
         "%s-aligned-%s.png" % (stem, token))

    if split:
        if exact_on:
            for g in res["exact_all"]:
                save(ents(g[1:]), "%s-identical-%s-keep%03d.png" % (stem, token, g[0]))
        if similar_on:
            for g in res["similar_all"]:
                save(ents(g[1:]), "%s-simular-%s-keep%03d.png" % (stem, token, g[0]))
    return written


# ============================================================ palettise preview
def _pil_const(group, name):
    from PIL import Image
    return getattr(getattr(Image, group, Image), name)


def palettise(src_rgba, colours, dither):
    """Map an RGBA image to the given colours (nearest RGB, Pillow in C).
    Pixels with alpha < 128 become transparent. Source is not modified."""
    from PIL import Image

    if not colours:
        return src_rgba
    cols = list(colours)[:256]
    flat = []
    for c in cols:
        flat.extend(c)
    flat.extend(list(cols[0]) * (256 - len(cols)))  # pad with a real colour
    palimg = Image.new("P", (1, 1))
    palimg.putpalette(flat)
    mode = _pil_const("Dither", "FLOYDSTEINBERG" if dither else "NONE")
    out = src_rgba.convert("RGB").quantize(palette=palimg, dither=mode).convert("RGBA")
    out.putalpha(src_rgba.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    return out


# ============================================================ settings
def load_settings():
    s = {"exact": True, "similar": False, "metric": "de2000",
         "tol_de2000": DEFAULT_TOL["de2000"],
         "tol_lab": DEFAULT_TOL["lab"], "tol_rgb": DEFAULT_TOL["rgb"],
         "align": False, "split": False, "export": EXPORT_LABELS[0],
         "last_dir": "", "geometry": "", "zoomed": False}
    s.update(default_sort_settings())
    for path in (SETTINGS_PATH, LEGACY_SETTINGS_PATH):  # legacy = old location
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                s.update(data)
                break
        except (OSError, ValueError):
            continue
    if s.get("settings_version", 1) < SETTINGS_VERSION:
        s["metric"] = "de2000"  # one-time switch to the new default
    s["settings_version"] = SETTINGS_VERSION
    if s["metric"] not in METRICS:
        s["metric"] = "de2000"
    if s["export"] not in EXPORT_LABELS:
        s["export"] = EXPORT_LABELS[0]
    try:
        s.update(clean_sort_settings(s))
    except ValueError:
        s.update(default_sort_settings())
    rec = s.get("recent_colours")
    s["recent_colours"] = [x for x in rec if isinstance(x, str) and parse_colour(x)][:16] \
        if isinstance(rec, list) else []
    sets = s.get("scratch_sets")
    clean = {}
    if isinstance(sets, dict):
        for k, v in sets.items():
            if isinstance(k, str) and isinstance(v, list):
                clean[k] = [x for x in v if isinstance(x, str) and parse_colour(x)]
    s["scratch_sets"] = clean or {"Scratch": []}
    if s.get("scratch_current") not in s["scratch_sets"]:
        s["scratch_current"] = next(iter(s["scratch_sets"]))
    return s


def save_settings(s):
    """Returns None on success, or an error message."""
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2)
        os.replace(tmp, SETTINGS_PATH)
        return None
    except OSError as e:
        return "%s\n\n%s" % (SETTINGS_PATH, e)


# ============================================================ sort settings
SORT_SETTING_KEYS = ("sort_method", "sort_params", "sort_key", "sort_high",
                     "sort_ramp_order", "sort_outliers", "sort_min")


def default_sort_settings():
    return {"sort_method": SORT_METHOD_NAMES[0], "sort_params": default_sort_params(),
            "sort_key": SORT_KEY_NAMES[0], "sort_high": True,
            "sort_ramp_order": RAMP_ORDERS[0], "sort_outliers": OUTLIER_MODES[0],
            "sort_min": 3}


def clean_sort_settings(src, strict=False):
    """Validated sort settings from src (unknown / bad values fall back to
    defaults, or raise ValueError when strict)."""
    out = {}

    def bad(k):
        if strict:
            raise ValueError("Bad value for '%s'." % k)

    for k, choices in (("sort_method", SORT_METHOD_NAMES), ("sort_key", SORT_KEY_NAMES),
                       ("sort_ramp_order", RAMP_ORDERS), ("sort_outliers", OUTLIER_MODES)):
        if k in src:
            if src[k] in choices:
                out[k] = src[k]
            else:
                bad(k)
    if "sort_high" in src:
        if isinstance(src["sort_high"], bool):
            out["sort_high"] = src["sort_high"]
        else:
            bad("sort_high")
    if "sort_min" in src:
        v = src["sort_min"]
        if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= ENTRIES:
            out["sort_min"] = v
        else:
            bad("sort_min")
    if "sort_params" in src:
        given = src["sort_params"]
        if not isinstance(given, dict):
            bad("sort_params")
            given = {}
        params = default_sort_params()
        for m, _kind, spec in SORT_METHODS:
            g = given.get(m)
            if not isinstance(g, dict):
                continue
            for name, _label, _dflt, lo, hi, _step in spec:
                v = g.get(name)
                if v is None:
                    continue
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    bad("sort_params")
                    continue
                params[m][name] = float(min(max(v, lo), hi))
        out["sort_params"] = params
    return out


# ============================================================ presets
PRESET_KEYS = ("exact", "similar", "metric", "tol_de2000", "tol_lab", "tol_rgb",
               "align", "split", "export") + SORT_SETTING_KEYS


def validate_preset(data):
    """Returns a clean settings dict or raises ValueError."""
    if not isinstance(data, dict) or data.get(PRESET_MARKER) != 1 \
            or not isinstance(data.get("settings"), dict):
        raise ValueError("Not a cleanpal preset file.")
    src = data["settings"]
    out = {}
    for k in ("exact", "similar", "align", "split"):
        if k in src:
            if not isinstance(src[k], bool):
                raise ValueError("Bad value for '%s'." % k)
            out[k] = src[k]
    if "metric" in src:
        if src["metric"] not in METRICS:
            raise ValueError("Unknown metric '%s'." % src["metric"])
        out["metric"] = src["metric"]
    for m in METRICS:
        k = "tol_" + m
        if k in src:
            v = src[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ValueError("Bad value for '%s'." % k)
            out[k] = float(v)
    if "export" in src:
        if src["export"] not in EXPORT_LABELS:
            raise ValueError("Unknown export format '%s'." % src["export"])
        out["export"] = src["export"]
    out.update(clean_sort_settings(src, strict=True))
    if not out:
        raise ValueError("Preset contains no settings.")
    return out


# ============================================================ projects
PROJECT_EXT = ".cleanpal"
PROJECT_MARKER = "cleanpal_project"
PROJECT_FORMAT = 1


def validate_project(data):
    """Clean project dict or ValueError."""
    if not isinstance(data, dict) or PROJECT_MARKER not in data:
        raise ValueError("Not a cleanpal project file.")
    if not isinstance(data[PROJECT_MARKER], int) or data[PROJECT_MARKER] > PROJECT_FORMAT:
        raise ValueError("Project was saved by a newer cleanpal (format %s) - "
                         "update cleanpal to open it." % data[PROJECT_MARKER])
    hist = data.get("history")
    if not isinstance(hist, list) or not hist:
        raise ValueError("Project has no history.")
    out_h = []
    for h in hist:
        if not isinstance(h, dict) or not isinstance(h.get("palette"), list) \
                or len(h["palette"]) != ENTRIES:
            raise ValueError("Bad history entry.")
        pal = []
        for e in h["palette"]:
            if e is None:
                pal.append(None)
                continue
            c = parse_colour(e) if isinstance(e, str) else None
            if c is None:
                raise ValueError("Bad colour in history: %r" % (e,))
            pal.append(c)
        out_h.append({"text": str(h.get("text") or "Entry"), "palette": pal})
    pos = data.get("hist_pos", len(out_h) - 1)
    if not isinstance(pos, int) or not 0 <= pos < len(out_h):
        pos = len(out_h) - 1

    def idx_list(k):
        v = data.get(k) or []
        if not isinstance(v, list):
            return []
        return [i for i in v if isinstance(i, int) and 0 <= i < ENTRIES]

    settings = {}
    if isinstance(data.get("settings"), dict):
        try:
            settings = validate_preset({PRESET_MARKER: 1, "settings": data["settings"]})
        except ValueError:
            settings = {}
    ramp = None
    if data.get("ramp") is not None:
        try:
            ramp = clean_ramp_state(data["ramp"])
        except ValueError:
            ramp = None
    sets = {}
    if isinstance(data.get("scratch_sets"), dict):
        for name, lst in data["scratch_sets"].items():
            if isinstance(name, str) and isinstance(lst, list):
                sets[name] = [hex_of(c) for c in (parse_colour(x) if isinstance(x, str)
                                                  else None for x in lst) if c]
    recent = [hex_of(c) for c in (parse_colour(x) if isinstance(x, str) else None
                                  for x in (data.get("recent_colours") or [])
                                  if isinstance(data.get("recent_colours"), list)) if c]
    mode = data.get("picker_mode") if data.get("picker_mode") in PICKER_MODES else None
    src = data.get("source") if isinstance(data.get("source"), str) else ""
    return {"history": out_h, "hist_pos": pos, "deleted": idx_list("deleted"),
            "selection": idx_list("selection"), "settings": settings, "ramp": ramp,
            "scratch_sets": sets, "scratch_current": data.get("scratch_current"),
            "recent_colours": recent, "picker_mode": mode, "source": src}


# ============================================================ GUI
HELP_TEXT = """\
cleanpal v%s - pal0 duplicate / similar colour cleaner

LOADING
  Open a WAD (PLAYPAL lump), SLADE playpal.pal / pal0.pal, SLADE pal0.png,
  DoomTools playpal.png or a COLORMAP image. pal0 (the first 256 colours,
  or row / line 0 of an image) is shown as a SLADE style 16x16 grid,
  index 0 top-left.

MATCHING - runs in order
  1. Remove exact colours
     Entries with exactly the same RGB value. The first occurrence (lowest
     index) is kept, later copies are removed.            Marker: X

  2. Remove similar colours  (needs stage 1)
     Only looks at what stage 1 left. Pairs within the tolerance are
     joined into clusters, and clustering is TRANSITIVE: if A~B and B~C,
     then A, B and C are one cluster even if A and C are further apart.
     The lowest index of each cluster is kept.           Marker: O

     CIEDE2000      (default) modern perceptual distance, built for judging
                    small differences. Corrects dE76's over-reaction to
                    saturated colours and its blue-purple distortion.
                    ~1 is just noticeable. Default 1.5.
     CIE Lab dE76   older perceptual distance. Cautious with vivid
                    colours. Default 2.0.
     Weighted RGB   channel-weighted RGB distance (0.299/0.587/0.114).
                    Blue barely counts. Default 1.1.

  Tolerance
     Drag the slider, click anywhere on its bar to jump there, use the
     mouse wheel over it (+/-0.05), or type in the box (applies as you
     type).
     In the box: Up/Down = +/-0.05, Shift+Up/Down = +/-0.5,
     mouse wheel = +/-0.05. Values above the slider range can be typed.

  Align
     Removes the removed entries and packs the kept colours toward index 0
     in their original order. The empty tail shows as a checkerboard.

TEXT FIELDS
  Every text / number box has a right-click menu: Cut, Copy, Paste,
  Delete, Select all. Ctrl+A selects the whole box while typing.

VIEW
  Mouse wheel      zoom toward the cursor
  Middle drag      pan
  Fit / F / double middle-click   reset to auto-fit
  The grid auto-fits as the window resizes until you zoom or pan.

SELECTION
  Click             select one colour
  Click-drag        box-select every colour inside
  Shift + click/drag   add to the selection
  Ctrl + click/drag    toggle colours in / out
  Ctrl+A            select all
  Esc / Clear       clear the selection
  Cull scope (under Remove similar):
    Whole palette          similar matching works on every colour
    Selected colours only  only the selection is culled; colours can only
                           merge with each other, unselected colours are
                           never touched. Nothing selected = nothing culled.
  Selecting on the grid switches the scope to Selected colours only.
  Selecting is easiest with Align off - the grid reflows as culling changes.

SORT INTO RAMPS
  Reorders the working palette. Pick a method, set its options, then:
    Preview   shows the result live on the grid (button turns blue). Changing
              any sort option re-sorts at once. While it is open, selecting,
              deleting, Move mode and snapshots are paused.
    Apply     keeps it and adds a "Sort ..." history entry - Back / Ctrl+Z
              undoes it. Works with or without Preview.
    Cancel    (or Esc, or the Preview button again) restores the palette.

  Apply to:
    Whole palette        every colour is sorted; empty slots go to the end.
    Selected (gathered)  the selected colours are sorted and pulled together
                         into ONE block that starts at the first selected
                         slot. The other colours keep their order and shift
                         along to close the gaps. Select all the reds anywhere
                         in the palette and they end up as one red section.
                         The selection stays on the moved block afterwards.
    Selecting on the grid switches this to Selected; clearing the selection
    switches it back to Whole palette.

  Methods that find ramps:
    Curved ramps    (default, best on Doom's PLAYPAL) every colour links to
                    its nearest darker neighbour, cheapest links first, each
                    colour taking at most one lighter and one darker link.
                    Max step   longest allowed link (OKLab distance x100)
                    Max bend   how sharply a ramp may change direction - keep
                               it high for white -> colour -> black ramps
                    Hue/chroma weight  how much more a hue / colourfulness
                               change costs than a lightness change
    Line ramps      repeatedly takes the longest gap-free run of colours lying
                    on one straight line in RGB (ramps made by linear RGB
                    blending), removes it and repeats.
                    Line tolerance  distance from the line (RGB units)
                    Max gap         largest gap between neighbours on a line
    Shade families  colours with the same R:G:B ratio, i.e. one colour scaled
                    toward black. Ratio tolerance x100.
    Hue bands       greys first, then groups split at gaps in hue. Simple
                    baseline. Max band width in degrees.
  Shared options for those four:
    Order colours by   order inside each ramp (default OKLab lightness)
    Lightest / Darkest first
    Ramp order         Greys first then hue / Original position /
                       Largest first / By key (each ramp's highest value)
    Outliers           colours in ramps smaller than Min ramp size:
                       Join nearest ramp (if one is close, else left single),
                       Collect at end, or Leave single
    Min ramp size      smaller groups count as outliers

  Plain orderings (no ramps):
    Stepped hue     Alan Zucconi's hue x lightness buckets, alternating
                    direction. Smooth looking grid, not strict ramps.
    Gradient path   one nearest-colour chain through everything (OKLab),
                    tidied with 2-opt. Good on a selection.
    Single key      plain sort by the Order colours by key.
    Reverse         reverses the palette or the selection.

  No sort is perfect - try a few and compare. Sorting a selection (one
  colour family at a time) gives the most control.
  Method, options and direction are saved with the settings and presets.

  Ramp test (command line, no GUI):
    cleanpal --ramptest <palette> [folder]
  Shuffles the palette three times, runs every method with its defaults and
  reports how many of the palette's own ramps (runs of close colours in its
  current order) come back as neighbours. Writes <name>_ramptest.png with
  every result side by side.

RAMP TOOL  (Ramp tool... button, top right)
  Select the cells to fill in the main grid - blank (empty) cells,
  exact-removed cells and normal colours can all be selected. The ramp
  fills them in INDEX ORDER, one step per cell; scattered cells work too.
  Align is switched off while the Ramp tool is open (slots must equal
  indices) and restored when it closes.

  Gradient bar
    Start and end nodes are fixed at the ends.
    Click the bar        add a node there (it takes the colour shown, so the
                         ramp doesn't jump)
    Drag a node          move it            Right-click / Del   remove it
    Double-click a node  open the colour picker on it
    Node row: swatch (click = picker), hex box, position %%, Delete node.
    Right-click the swatch or hex box to copy / paste the node colour.
  Blend
    OKLab            (default) even-looking steps, no muddy middle
    RGB              plain RGB mixing, like most paint programs / Doom's ramps
    OKLCH (hue path) goes round the hue wheel - the most vivid in-betweens
  Ease     Linear / Ease in / Ease out / Ease in-out, Strength 1 - 6
  Ease applies to: Whole ramp, or Each segment (every node-to-node stretch
           eases on its own). With whole-ramp easing the nodes are drawn
           where their colour actually lands on the bar.
  Reverse              flips the ramp
  Use selection ends   start / end take the first / last selected cells'
                       colours (extend or smooth an existing ramp)
  Steps strip          the actual colours that will be written, with hover
                       info. Dot = same RGB as an earlier step; corner
                       triangle = already in the palette elsewhere (Remove
                       exact would flag it).
  Preview / Apply / Cancel work like the sort: Apply adds a "Ramp ..."
  history entry (Back undoes it). Esc cancels a preview.
  Load ramp... / Save ramp... store nodes, blend and easing as .json.
  The ramp is remembered between sessions and saved in projects.

COLOUR PICKER  (popup - Picker... / double-click a node / swatch)
  Non-modal: edits apply live to the node, the steps and the grid preview.
  Clicking another ramp node switches the picker to that node.
  Modes (dropdown) - all edit the same colour, switching never changes it:
    RGB Sliders        R / G / B sliders + full spectrum box (hue across,
                       white - colour - black down)
    HSL Sliders        H / S / L sliders + hue x lightness box drawn at the
                       current saturation
    HSL Colour Wheel   hue ring + saturation / lightness triangle
  Hue and saturation are remembered through greys, black and white, so
  dropping saturation to 0 and back keeps your hue.
  Fields: R G B (0-255), H (0-360) S L (0-100), R# G# B#, and # hex.
  The # box takes EBEBEB, #EBEBEB, #ebe or 235,235,235; Ctrl+C / Ctrl+V.
  Right-click any field or the swatch: Cut / Copy / Paste / Select all, plus
  Copy colour as hex, Copy colour as R,G,B and Paste colour (applies a
  copied colour in any of those forms to the whole colour).
  Precision:  Shift + drag = fine (quarter speed)   Ctrl + drag = lock to
              one axis   arrow keys nudge the last-used control by 1
              (Shift = 10)   mouse wheel on sliders / fields = 1 (Shift 10)
  Swatch: left = new, right = colour when the node was picked - click the
  right half to revert.
  Eyedropper: click anywhere on screen (any program); a magnifier shows the
  exact pixel. Esc / right-click cancels.
  Recent: last 16 colours used. On top keeps the window above others.

SCRATCH PALETTE  (Scratch palette... button)
  Temporary swatches in named sets (New / Rename / Delete).
  Add:   + Picker (current picker colour), + Selected (selected grid
         cells), Eyedropper, Ctrl+V (hex lines), or drag cells from the
         main grid onto it (a selected group drags as a group).
  Use:   click a swatch          -> picker / active ramp node
         drag onto a grid cell   -> writes it into the palette
         drag onto the ramp bar  -> recolours that node (or adds one)
         drag onto the picker    -> sets the picker
         Fill selected           -> writes it into every selected cell
         Palette writes become "Set colour ..." history entries.
  Manage: drag to reorder, Shift / Ctrl click to multi-select, Del
         removes, Ctrl+C copies as hex. Right-click a swatch: Copy hex,
         Copy R,G,B, Paste colour(s) here, Send to picker, Remove. A dot marks swatches whose
         colour is already in the palette; hover shows where.
  Import: hex text, GIMP .gpl, JASC .pal or raw .pal (as a new set).
  Export: .gpl or hex .txt. Sets are kept between sessions and in projects.

MANUAL DELETE
  Delete / Backspace / the "Delete / restore selected" button
                    marks the selected colours as deleted   Marker: bar -
                    Do it again on deleted colours to restore them.
  Deleted colours are left out of exact / similar matching completely, are
  baked by Snapshot and are left out of exports. In the Align view they
  vanish, so switch Align off to reach them again.

MOVE MODE  (button or M key)
  Select first, then drag: dragging a SELECTED colour moves the
  selection; dragging from an unselected colour (or outside the grid)
  draws a selection box as usual (Shift adds, Ctrl toggles). To move one
  colour: click it, then drag it.
  A dropped colour lands on the slot and the colours in between shift
  along. Alt + drag swaps two single colours instead. A multi-colour
  selection moves as a block, in order, with its gaps closed up.
  Align is switched off while moving. Ctrl+Z undoes moves one at a time.
  Leaving Move mode with changes adds a "Moved colours" history entry.

PALETTISED PREVIEW
  Opens a separate window. Open folder... loads the PNGs in a folder;
  Open WAD... lists the raw graphics stored in a WAD: patches, sprites,
  flats, other Doom-format graphics and PNG lumps (TEXTURE1/2 and PNAMES
  are not used). Doom-format graphics are decoded with the WAD's PLAYPAL (or the
  loaded palette if the WAD has none). Type / name filters narrow the list.
  Up / Down (or PgUp / PgDn, or the arrow buttons) cycles through them.
  The image is shown converted to the CURRENT result palette (the colours
  an export would write right now) and updates live as you edit.
  Space flips Palettised / Original. Wheel zoom, middle-drag pan, F fit.
  Single / Grid: Grid shows columns x rows images per page (default 4x4,
  1-16 each). All images share one pixel scale so relative sizes are true;
  each cell is the size of the page's largest image. Up / Down moves a
  page and refits; zoom and pan freely in between. Names show on the
  cells when large enough (Names tick box or N key hides them); hover
  shows details; double-click an image to open it in Single view.
  Dither: Floyd-Steinberg on / off. Matching is nearest RGB.
  Source images and WADs are only read, never modified.

SNAPSHOTS - work like export + reload
  Snapshot   takes the current result exactly as an export would (live
             culling applied, packed toward 0 if Align is ticked) and makes
             it the working palette. Everything after that works on the new
             palette as if you had exported it and loaded it again.
  History    every entry is a complete palette. Click one to load it.
             Back / Ctrl+Z loads the previous entry.
  Remove     deletes the current entry and loads the one before it.
             #0 Original can't be removed.
  Collapse   keeps only the current entry and makes it the new #0 (asks
             first - the other entries are gone for good).
  A snapshot taken after stepping back discards the later entries.
  History lives in the session unless you save a project. Closing with
  changes that are neither exported nor saved as a project asks first.
  Loading a palette starts a fresh history.

PROJECTS
  Save project / Save project as...  write a .cleanpal file (JSON):
    every history entry and which one is loaded, deleted marks, the
    selection, matching / sort / export settings, the ramp, scratch sets,
    recent colours and picker mode. Palettes are stored inside, so the
    project still opens if the source WAD / PNG moves.
  Open...  (or cleanpal mywork.cleanpal) restores it exactly. Its scratch
    sets are merged into yours (same name = project's version wins).
  A project save counts as saved for the close warning.
  Hover info and analysis PNGs refer to the working palette's indices.

HOVER
  Shows index, RGB and Lab. Hovering a removed entry outlines the colour
  it collapses into; hovering a kept entry outlines what it absorbed.

EXPORT - writes what the viewer currently shows
  DoomTools playpal.png        256x14, Doom pain / item / radsuit tints
  DoomTools blank playpal.png  256x14, pal0 copied to every row
  SLADE pal0.png               128x128 grid, 8x8 cells
  SLADE pal0.pal               768 byte raw palette
  SLADE playpal.pal            14 x 768 bytes, tinted
  Analysis PNGs                original cleanpal0 outputs, into a folder:
     -identical-  stage 1 removals at their original slots
     -simular-    stage 2 removals at their original slots
     -aligned-    kept colours packed from slot 0
     Split        also one -keepNNN file per set / cluster

  Removed / empty slots are TRANSPARENT in PNGs and GREEN (0,255,0) in
  .pal files. Green stays untinted in every palette so it reads as a
  placeholder. You are warned if a kept colour is exactly (0,255,0).

  Filename token: (DE2000-1.5) / (CIE-2.0) / (RGB-1.1) with similar on,
  (EXACT) for
  exact only, (NONE) with no matching.

SETTINGS
  Everything is remembered when you close: matching tick boxes, metric,
  each metric's tolerance, Align, sort method and options, export format,
  split, window size /
  position and the last folder. Stored in
  %%APPDATA%%\\cleanpal\\cleanpal_settings.json. You are told if saving fails.

PRESETS
  Save preset...  writes the matching, sort + export setup to a .json file:
                  tick boxes, metric, every metric's tolerance, Align,
                  sort method and options, export format and split (no
                  window size or folders).
  Load preset...  applies one immediately. The preset's name shows in
                  the title bar.
  Default folder: %%APPDATA%%\\cleanpal\\presets
""" % VERSION


class App:
    CELL = 30          # world units per cell
    GAP = 2            # world units between cells
    PAD = 10           # screen px margin when fitting
    ZOOM_MIN = 0.25    # relative to fit scale
    ZOOM_MAX = 16.0
    ZOOM_STEP = 1.2
    MARKER_MIN_PX = 10

    def __init__(self, root, path=None):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.s = load_settings()

        self.rgbs = None
        self.labs = None
        self.pairs = {m: [] for m in METRICS}
        self.res = None
        self.src_path = None
        self.preset_name = None
        self.hover_slot = None
        self.selection = set()
        self.deleted = set()
        self.preview = None
        self._move_undo = []
        self._move_start = None
        self._align_before_move = False
        self.history = []
        self.hist_pos = 0
        self.exported = True
        self._drag = None
        self._scale_lock = False
        self.view_scale = 1.0
        self.off_x = 0.0
        self.off_y = 0.0
        self.auto_fit = True
        self._pan_start = None

        self.exact_var = tk.BooleanVar(value=bool(self.s["exact"]))
        self.similar_var = tk.BooleanVar(value=bool(self.s["similar"]))
        self.metric_var = tk.StringVar(value=self.s["metric"])
        self.align_var = tk.BooleanVar(value=bool(self.s["align"]))
        self.split_var = tk.BooleanVar(value=bool(self.s["split"]))
        self.export_var = tk.StringVar(value=self.s["export"])
        self.scope_var = tk.StringVar(value="all")
        self.move_var = tk.BooleanVar(value=False)
        self.tol = {m: float(self.s.get("tol_" + m, DEFAULT_TOL[m])) for m in METRICS}
        self.tol_text = tk.StringVar()
        self._text_lock = False
        self.sort_method_var = tk.StringVar(value=self.s["sort_method"])
        self.sort_scope_var = tk.StringVar(value="all")
        self.sort_key_var = tk.StringVar(value=self.s["sort_key"])
        self.sort_high_var = tk.BooleanVar(value=bool(self.s["sort_high"]))
        self.sort_order_var = tk.StringVar(value=self.s["sort_ramp_order"])
        self.sort_outlier_var = tk.StringVar(value=self.s["sort_outliers"])
        self.sort_min_text = tk.StringVar(value=str(self.s["sort_min"]))
        self.sort_min = int(self.s["sort_min"])
        self.sort_params = self.s["sort_params"]
        self._sort_backup = None      # state before the sort preview
        self._sort_block = set()      # indices placed by the sort (preview outline)
        self._sort_nramps = 0
        self._sort_after = None
        self._sort_param_vars = {}
        self.ramp = None              # RampTool window
        self.picker = None            # ColourPicker window
        self.scratch = None           # ScratchPalette window
        self._ramp_backup = None      # state before the ramp preview
        self._ramp_targets = []
        self._ramp_align_saved = False
        self.project_path = None
        self.file_var = tk.StringVar(value="No palette loaded")
        self.stats_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self._build_ui()
        if self.s.get("geometry"):
            try:
                root.geometry(self.s["geometry"])
            except tk.TclError:
                pass
        if self.s.get("zoomed") and os.name == "nt":
            try:
                root.state("zoomed")
            except tk.TclError:
                pass
        self._sync_tol_widgets()
        self._update_states()
        self._update_sort_btn()
        self._refresh_history()
        self.recompute()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if path:
            self.load(path)

    # ---------------------------------------------------------- UI
    def _build_ui(self):
        tk = self.tk
        from tkinter import ttk

        self.root.title("cleanpal v%s" % VERSION)
        self.root.resizable(True, True)
        self._colour_ctx = {}
        for cls in ("TEntry", "TSpinbox", "Entry", "Spinbox"):
            self.root.bind_class(cls, "<Button-3>", self._entry_menu, add="+")
            self.root.bind_class(cls, "<Control-a>", self._entry_select_all)
            self.root.bind_class(cls, "<Control-A>", self._entry_select_all)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=(8, 8, 8, 0))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(top, text="Open...", command=self.open_dialog).pack(side="left")
        ttk.Button(top, text="Save project",
                   command=self.save_project).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Save project as...",
                   command=lambda: self.save_project(ask=True)).pack(side="left", padx=(4, 0))
        ttk.Button(top, text="Palettised preview...",
                   command=self.open_preview).pack(side="right")
        ttk.Button(top, text="Scratch palette...",
                   command=self.open_scratch).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Ramp tool...",
                   command=self.open_ramp).pack(side="right", padx=(0, 6))
        ttk.Label(top, textvariable=self.file_var).pack(side="left", padx=8)

        size = self.PAD * 2 + self._grid_world()
        self.canvas = tk.Canvas(self.root, width=size, height=size, bg="#262626",
                                highlightthickness=3, highlightbackground="#262626",
                                highlightcolor="#262626")
        self.canvas.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        cv = self.canvas
        cv.bind("<Motion>", self._on_motion)
        cv.bind("<Leave>", self._on_leave)
        cv.bind("<Configure>", self._on_canvas_resize)
        cv.bind("<MouseWheel>", self._on_wheel)                       # Windows / macOS
        cv.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, self.ZOOM_STEP))  # X11
        cv.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / self.ZOOM_STEP))
        cv.bind("<ButtonPress-2>", self._on_pan_start)
        cv.bind("<B2-Motion>", self._on_pan_move)
        cv.bind("<ButtonRelease-2>", self._on_pan_end)
        cv.bind("<Double-Button-2>", lambda e: self.fit_view())
        cv.bind("<ButtonPress-1>", self._on_b1_press)
        cv.bind("<B1-Motion>", self._on_b1_move)
        cv.bind("<ButtonRelease-1>", self._on_b1_release)
        self.root.bind("<Escape>", lambda e: self.clear_selection())
        self.root.bind("<Control-z>", self._on_undo_key)
        self.root.bind("<Control-Z>", self._on_undo_key)
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<BackSpace>", self._on_delete_key)
        self.root.bind("<Control-a>", self._on_select_all)
        self.root.bind("<Control-A>", self._on_select_all)
        self.root.bind("<Key-m>", self._on_move_key)
        self.root.bind("<Key-M>", self._on_move_key)
        self.root.bind("<Key-f>", self._on_fit_key)
        self.root.bind("<Key-F>", self._on_fit_key)

        # side panel lives in a scrollable canvas so it fits small screens
        wrap = ttk.Frame(self.root)
        wrap.grid(row=1, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        bg = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        self.side_cv = tk.Canvas(wrap, highlightthickness=0, bg=bg, yscrollincrement=20)
        self.side_cv.grid(row=0, column=0, sticky="ns")
        self.side_sb = ttk.Scrollbar(wrap, orient="vertical", command=self.side_cv.yview)
        self.side_cv.configure(yscrollcommand=self.side_sb.set)
        side = ttk.Frame(self.side_cv, padding=(0, 8, 8, 8))
        self.side_cv.create_window(0, 0, window=side, anchor="nw")
        self.side = side
        side.bind("<Configure>", lambda e: self._side_layout())
        self.side_cv.bind("<Configure>", lambda e: self._side_layout())

        # matching
        mf = ttk.LabelFrame(side, text="Matching (runs in order)", padding=8)
        mf.pack(fill="x")
        ttk.Checkbutton(mf, text="1. Remove exact colours", variable=self.exact_var,
                        command=self._on_toggle).pack(anchor="w")
        self.sim_chk = ttk.Checkbutton(mf, text="2. Remove similar colours",
                                       variable=self.similar_var,
                                       command=self._on_toggle)
        self.sim_chk.pack(anchor="w", pady=(4, 0))

        sub = ttk.Frame(mf, padding=(18, 4, 0, 0))
        sub.pack(fill="x")
        sub.columnconfigure(0, weight=1)
        self.metric_rbs = []
        for row, m in enumerate(METRICS):
            text = METRIC_LABEL[m] + ("  (default)" if m == "de2000" else "")
            rb = ttk.Radiobutton(sub, text=text, value=m,
                                 variable=self.metric_var, command=self._on_metric)
            rb.grid(row=row, column=0, sticky="w")
            self.metric_rbs.append(rb)
        r0 = len(METRICS)
        self.range_var = tk.StringVar()
        hdr = ttk.Frame(sub)
        hdr.grid(row=r0, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(hdr, text="Tolerance").pack(side="left")
        ttk.Label(hdr, textvariable=self.range_var, foreground="#888").pack(side="right")
        try:
            ui = max(1.0, self.root.winfo_fpixels("1i") / 96.0)  # monitor scale factor
            self.ui = ui
        except tk.TclError:
            ui = 1.0
            self.ui = ui
        self.scale = tk.Scale(sub, from_=0, to=10, resolution=0.05, orient="horizontal",
                              showvalue=0, length=120,
                              sliderlength=int(36 * ui), width=int(22 * ui),
                              command=self._on_scale)
        self.scale.grid(row=r0 + 1, column=0, sticky="ew")
        self.scale.bind("<Button-1>", self._on_scale_click)
        self.scale.bind("<MouseWheel>", lambda e: self._step_tol(1 if e.delta > 0 else -1))
        self.scale.bind("<Button-4>", lambda e: self._step_tol(1))
        self.scale.bind("<Button-5>", lambda e: self._step_tol(-1))
        self.tol_spin = ttk.Spinbox(sub, textvariable=self.tol_text, from_=0, to=1000,
                                    increment=0.05, width=9, command=self._on_spin_arrow)
        self.tol_spin.grid(row=r0 + 2, column=0, sticky="w", pady=(4, 0))
        scf = ttk.Frame(sub)
        scf.grid(row=r0 + 3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(scf, text="Cull:").pack(side="left")
        self.scope_rbs = [
            ttk.Radiobutton(scf, text="Whole palette", value="all",
                            variable=self.scope_var, command=self.recompute),
            ttk.Radiobutton(scf, text="Selected only", value="selected",
                            variable=self.scope_var, command=self.recompute),
        ]
        self.scope_rbs[0].pack(side="left", padx=(6, 0))
        self.scope_rbs[1].pack(side="left", padx=(6, 0))
        sp = self.tol_spin
        sp.bind("<Up>", lambda e: self._step_tol(1))
        sp.bind("<Down>", lambda e: self._step_tol(-1))
        sp.bind("<Shift-Up>", lambda e: self._step_tol(10))
        sp.bind("<Shift-Down>", lambda e: self._step_tol(-10))
        sp.bind("<MouseWheel>", lambda e: self._step_tol(1 if e.delta > 0 else -1))
        sp.bind("<Button-4>", lambda e: self._step_tol(1))
        sp.bind("<Button-5>", lambda e: self._step_tol(-1))
        sp.bind("<Return>", self._on_tol_commit)
        sp.bind("<FocusOut>", self._on_tol_commit)
        self.tol_text.trace_add("write", self._on_tol_typed)

        self._build_sort_panel(side)

        # view
        vf = ttk.LabelFrame(side, text="View", padding=8)
        vf.pack(fill="x", pady=(8, 0))
        self.align_chk = ttk.Checkbutton(vf, text="Align (pack kept toward index 0)",
                                         variable=self.align_var, command=self._on_toggle)
        self.align_chk.pack(anchor="w")
        ttk.Label(vf, text="X = exact removed   O = similar removed\n"
                           "checker = empty slot\n"
                           "wheel = zoom   middle drag = pan",
                  foreground="#666").pack(anchor="w", pady=(6, 0))
        ttk.Button(vf, text="Fit", command=self.fit_view).pack(anchor="e", pady=(6, 0))

        # snapshots
        sf = ttk.LabelFrame(side, text="Selection & snapshots", padding=8)
        sf.pack(fill="x", pady=(8, 0))
        ttk.Label(sf, text="click / drag = select   shift = add   ctrl = toggle\n"
                           "Del / Backspace = delete / restore   Ctrl+A = all\n"
                           "M = move mode",
                  foreground="#666").pack(anchor="w")
        mrow = ttk.Frame(sf)
        mrow.pack(fill="x", pady=(6, 0))
        self.move_btn = tk.Button(mrow, text="Move mode: OFF", width=16, relief="raised",
                                  command=self._on_move_button)
        self._move_btn_bg = self.move_btn.cget("background")
        self.move_btn.pack(side="left")
        ttk.Button(mrow, text="Delete / restore selected",
                   command=self.delete_selected).pack(side="left", padx=(6, 0))
        sbf = ttk.Frame(sf)
        sbf.pack(fill="x", pady=(6, 0))
        self.snap_btn = ttk.Button(sbf, text="Snapshot", command=self.take_snapshot)
        self.snap_btn.pack(side="left")
        self.back_btn = ttk.Button(sbf, text="Back", command=self.step_back)
        self.back_btn.pack(side="left", padx=(6, 0))
        self.remove_btn = ttk.Button(sbf, text="Remove", command=self.remove_snapshot)
        self.remove_btn.pack(side="left", padx=(6, 0))
        self.collapse_btn = ttk.Button(sbf, text="Collapse", command=self.collapse_history)
        self.collapse_btn.pack(side="left", padx=(6, 0))
        ttk.Button(sbf, text="Clear selection",
                   command=self.clear_selection).pack(side="right")
        lf = ttk.Frame(sf)
        lf.pack(fill="x", pady=(6, 0))
        self.hist_list = tk.Listbox(lf, height=5, activestyle="none",
                                    exportselection=False, font=("Consolas", 9))
        hsb = ttk.Scrollbar(lf, orient="vertical", command=self.hist_list.yview)
        self.hist_list.configure(yscrollcommand=hsb.set)
        self.hist_list.pack(side="left", fill="x", expand=True)
        hsb.pack(side="right", fill="y")
        self.hist_list.bind("<<ListboxSelect>>", self._on_hist_select)

        # export
        ef = ttk.LabelFrame(side, text="Export", padding=8)
        ef.pack(fill="x", pady=(8, 0))
        ttk.Combobox(ef, textvariable=self.export_var, values=EXPORT_LABELS,
                     state="readonly", width=40).pack(fill="x")
        ttk.Checkbutton(ef, text="Split per set / cluster (analysis PNGs)",
                        variable=self.split_var).pack(anchor="w", pady=(6, 0))
        ttk.Button(ef, text="Export...", command=self.do_export).pack(anchor="e", pady=(6, 0))

        bf = ttk.Frame(side)
        bf.pack(fill="x", pady=(8, 0))
        ttk.Button(bf, text="Help", command=self.show_help).pack(side="right")
        ttk.Button(bf, text="Load preset...", command=self.load_preset).pack(side="left")
        ttk.Button(bf, text="Save preset...",
                   command=self.save_preset).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(bottom, textvariable=self.stats_var,
                  font=("Consolas", 10, "bold")).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.info_var,
                  font=("Consolas", 10)).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.status_var,
                  foreground="#2a6").pack(anchor="w")

        # wheel over the panel scrolls it (sliders / spinbox / lists keep theirs)
        def bind_tree(w):
            if w.winfo_class() not in ("Scale", "TSpinbox", "Spinbox", "TCombobox",
                                       "Listbox", "TScrollbar"):
                w.bind("<MouseWheel>", self._side_wheel, add="+")
                w.bind("<Button-4>", lambda e: self._side_scroll(-1), add="+")
                w.bind("<Button-5>", lambda e: self._side_scroll(1), add="+")
            for ch in w.winfo_children():
                bind_tree(ch)
        bind_tree(side)
        self.side_cv.bind("<MouseWheel>", self._side_wheel)

        # minimum size: panel width + a usable preview; height no longer
        # depends on the panel (it scrolls)
        self.root.update_idletasks()
        self._side_layout()
        min_w = side.winfo_reqwidth() + 30 + 260
        min_h = top.winfo_reqheight() + bottom.winfo_reqheight() + 320
        self.root.minsize(min_w, min_h)

    def _build_sort_panel(self, side):
        tk = self.tk
        from tkinter import ttk

        sf = ttk.LabelFrame(side, text="Sort into ramps", padding=8)
        sf.pack(fill="x", pady=(8, 0))
        sf.columnconfigure(1, weight=1)
        ttk.Label(sf, text="Method").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(sf, textvariable=self.sort_method_var, values=SORT_METHOD_NAMES,
                          state="readonly", width=22)
        cb.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_sort_method())
        scf = ttk.Frame(sf)
        scf.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(scf, text="Apply to:").pack(side="left")
        self.sort_scope_rbs = [
            ttk.Radiobutton(scf, text="Whole palette", value="all",
                            variable=self.sort_scope_var, command=self._on_sort_option),
            ttk.Radiobutton(scf, text="Selected (gathered)", value="selected",
                            variable=self.sort_scope_var, command=self._on_sort_option),
        ]
        for rb in self.sort_scope_rbs:
            rb.pack(side="left", padx=(6, 0))

        # per-method options, rebuilt when the method changes
        self.sort_opt_frame = ttk.Frame(sf)
        self.sort_opt_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.sort_opt_frame.columnconfigure(0, weight=1)

        # shared ordering options
        shf = ttk.Frame(sf)
        shf.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        shf.columnconfigure(1, weight=1)
        self.sort_shared = {}
        ttk.Label(shf, text="Order colours by").grid(row=0, column=0, sticky="w")
        w = ttk.Combobox(shf, textvariable=self.sort_key_var, values=SORT_KEY_NAMES,
                         state="readonly", width=18)
        w.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_sort_option())
        self.sort_shared["key"] = [w]
        dirf = ttk.Frame(shf)
        dirf.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.sort_shared["dir"] = [
            ttk.Radiobutton(dirf, text="Lightest / highest first", value=True,
                            variable=self.sort_high_var, command=self._on_sort_option),
            ttk.Radiobutton(dirf, text="Darkest / lowest first", value=False,
                            variable=self.sort_high_var, command=self._on_sort_option)]
        for rb in self.sort_shared["dir"]:
            rb.pack(side="left", padx=(0, 8))
        ttk.Label(shf, text="Ramp order").grid(row=2, column=0, sticky="w", pady=(4, 0))
        w = ttk.Combobox(shf, textvariable=self.sort_order_var, values=RAMP_ORDERS,
                         state="readonly", width=18)
        w.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_sort_option())
        self.sort_shared["ramps"] = [w]
        ttk.Label(shf, text="Outliers").grid(row=3, column=0, sticky="w", pady=(4, 0))
        w = ttk.Combobox(shf, textvariable=self.sort_outlier_var, values=OUTLIER_MODES,
                         state="readonly", width=18)
        w.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_sort_option())
        self.sort_shared["ramps"].append(w)
        ttk.Label(shf, text="Min ramp size").grid(row=4, column=0, sticky="w", pady=(4, 0))
        w = ttk.Spinbox(shf, textvariable=self.sort_min_text, from_=1, to=64,
                        increment=1, width=6, command=self._on_sort_min)
        w.grid(row=4, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        w.bind("<Return>", lambda e: self._on_sort_min())
        w.bind("<FocusOut>", lambda e: self._on_sort_min())
        self.sort_shared["ramps"].append(w)

        bf = ttk.Frame(sf)
        bf.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.sort_prev_btn = tk.Button(bf, text="Preview: OFF", width=12, relief="raised",
                                       command=self._on_sort_preview)
        self._sort_btn_bg = self.sort_prev_btn.cget("background")
        self.sort_prev_btn.pack(side="left")
        ttk.Button(bf, text="Apply", command=self.sort_apply).pack(side="left", padx=(6, 0))
        self.sort_cancel_btn = ttk.Button(bf, text="Cancel", command=self.sort_cancel)
        self.sort_cancel_btn.pack(side="left", padx=(6, 0))
        self._build_sort_options()

    def _build_sort_options(self):
        """(Re)build the option boxes for the current method."""
        from tkinter import ttk

        f = self.sort_opt_frame
        for ch in f.winfo_children():
            ch.destroy()
        m = self.sort_method_var.get()
        _name, kind, spec = SORT_METHOD_INFO[m]
        self._sort_param_vars = {}
        vals = self.sort_params.setdefault(m, {})
        for row, (name, label, dflt, lo, hi, step) in enumerate(spec):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=(0, 2))
            v = self.tk.StringVar(value=fmt_tol(vals.get(name, dflt)))
            sp = ttk.Spinbox(f, textvariable=v, from_=lo, to=hi, increment=step, width=7,
                             command=lambda n=name: self._on_sort_param(n))
            sp.grid(row=row, column=1, sticky="e", padx=(6, 0), pady=(0, 2))
            sp.bind("<Return>", lambda e, n=name: self._on_sort_param(n, tidy=True))
            sp.bind("<FocusOut>", lambda e, n=name: self._on_sort_param(n, tidy=True))
            v.trace_add("write", lambda *_a, n=name: self._on_sort_param(n))
            self._sort_param_vars[name] = (v, lo, hi)
        for ch in f.winfo_children():
            if ch.winfo_class() not in ("TSpinbox", "Spinbox"):
                ch.bind("<MouseWheel>", self._side_wheel, add="+")
        if not spec:
            hint = {"Gradient path": "One smooth nearest-colour chain (OKLab).",
                    "Single key": "Plain sort by 'Order colours by'.",
                    "Reverse": "Reverses the order."}.get(m, "")
            ttk.Label(f, text=hint, foreground="#666").grid(row=0, column=0, sticky="w")
        # shared options only where they mean something
        states = {"key": kind == "ramps" or m == "Single key",
                  "dir": m != "Reverse",
                  "ramps": kind == "ramps"}
        for grp, on in states.items():
            for w in self.sort_shared.get(grp, []):
                w.state(["!disabled"] if on else ["disabled"])
        if hasattr(self, "side_cv"):
            self.root.update_idletasks()
            self._side_layout()

    def _on_sort_method(self):
        self._build_sort_options()
        self._on_sort_option()

    def _on_sort_param(self, name, tidy=False):
        if name not in self._sort_param_vars:
            return
        v, lo, hi = self._sort_param_vars[name]
        m = self.sort_method_var.get()
        try:
            x = float(v.get())
        except ValueError:
            x = None
        if x is not None and x == x:
            x = min(max(x, lo), hi)
            if self.sort_params[m].get(name) != x:
                self.sort_params[m][name] = x
                self._on_sort_option()
        if tidy:
            v.set(fmt_tol(self.sort_params[m].get(name, lo)))

    def _on_sort_min(self):
        try:
            x = int(float(self.sort_min_text.get()))
        except ValueError:
            x = self.sort_min
        x = min(max(x, 1), 64)
        self.sort_min_text.set(str(x))
        if x != self.sort_min:
            self.sort_min = x
            self._on_sort_option()

    def _on_sort_option(self):
        """Any sort setting changed: re-sort the preview (debounced)."""
        if self._sort_backup is None:
            return
        if self._sort_after is not None:
            self.root.after_cancel(self._sort_after)
        self._sort_after = self.root.after(120, self._sort_refresh)

    # ---------------------------------------------------------- sorting
    def _permute(self, perm):
        """Reorder the working palette: perm[new_slot] = old_slot. Deleted
        marks and the selection follow their colours."""
        newpos = [0] * ENTRIES
        for new, old in enumerate(perm):
            newpos[old] = new
        self.rgbs = [self.rgbs[o] for o in perm]
        self.labs = [self.labs[o] for o in perm]
        self.pairs = {m: [(d, newpos[a], newpos[b]) for d, a, b in v]
                      for m, v in self.pairs.items()}
        self.deleted = {newpos[i] for i in self.deleted}
        self.selection = {newpos[i] for i in self.selection}
        return newpos

    def _sort_perm(self):
        """(perm, n_ramps, n_sorted) for the current settings, or a message."""
        rgbs = self.rgbs
        if self.sort_scope_var.get() == "selected":
            idxs = sorted(i for i in self.selection if rgbs[i] is not None)
            if len(idxs) < 2:
                return "Select at least two colours, or set Apply to: Whole palette."
        else:
            idxs = [i for i in range(ENTRIES) if rgbs[i] is not None]
            if len(idxs) < 2:
                return "Nothing to sort."
        order, nr = ramp_sort(
            [rgbs[i] for i in idxs], self.sort_method_var.get(),
            self.sort_params.get(self.sort_method_var.get()),
            key=self.sort_key_var.get(), high_first=self.sort_high_var.get(),
            ramp_order=self.sort_order_var.get(), outliers=self.sort_outlier_var.get(),
            min_size=self.sort_min)
        block = [idxs[k] for k in order]
        if self.sort_scope_var.get() == "selected":
            bs = set(block)
            rest = [i for i in range(ENTRIES) if i not in bs]
            pos = idxs[0]                  # block starts at the first selected slot
            perm = rest[:pos] + block + rest[pos:]
        else:
            perm = block + [i for i in range(ENTRIES) if rgbs[i] is None]
        return perm, nr, block

    def _busy(self, on):
        try:
            self.root.configure(cursor="watch" if on else "")
            self.canvas.configure(cursor="watch" if on else "")
            if on:
                self.root.update_idletasks()
        except self.tk.TclError:
            pass

    def _sort_refresh(self):
        """Preview: re-sort from the pre-preview state."""
        self._sort_after = None
        if self._sort_backup is None:
            return
        b = self._sort_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.selection = set(b[3]), set(b[4])
        self._busy(True)
        try:
            r = self._sort_perm()
        finally:
            self._busy(False)
        if isinstance(r, str):
            self._sort_block = set()
            self._sort_nramps = 0
            self.status_var.set(r)
        else:
            perm, nr, block = r
            n = len(block)
            newpos = self._permute(perm)
            self._sort_block = {newpos[o] for o in block}
            self._sort_nramps = nr
            self.status_var.set("Sort preview: %s - %d colours%s. Apply keeps it, "
                                "Cancel restores." % (
                                    self.sort_method_var.get(), n,
                                    (", %d ramps" % nr) if nr else ""))
        self.recompute()

    def _update_sort_btn(self):
        on = self._sort_backup is not None
        self.sort_prev_btn.configure(
            text="Preview: ON" if on else "Preview: OFF",
            relief="sunken" if on else "raised",
            background="#7fd4ff" if on else self._sort_btn_bg,
            activebackground="#a8e2ff" if on else self._sort_btn_bg)
        self.sort_cancel_btn.state(["!disabled"] if on else ["disabled"])

    def _sort_begin(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return False
        if self._ramp_backup is not None:
            self.status_var.set("Ramp preview is open - Apply or Cancel it first.")
            return False
        if self.move_var.get():
            self._exit_move()
        self._sort_backup = (self.rgbs, self.labs, self.pairs,
                             set(self.deleted), set(self.selection))
        self._update_sort_btn()
        self._refresh_history()
        return True

    def _sort_end(self):
        if self._sort_after is not None:
            self.root.after_cancel(self._sort_after)
            self._sort_after = None
        self._sort_backup = None
        self._sort_block = set()
        self._sort_nramps = 0
        self._update_sort_btn()
        self._refresh_history()

    def _on_sort_preview(self):
        if self._sort_backup is not None:
            self.sort_cancel()
            return
        if self._sort_begin():
            self._sort_refresh()

    def sort_cancel(self):
        if self._sort_backup is None:
            return
        b = self._sort_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.selection = set(b[3]), set(b[4])
        self._sort_end()
        self.status_var.set("Sort cancelled.")
        self.recompute()

    def sort_apply(self):
        """Commit the sort (previewed or not) as a history entry."""
        if self._sort_backup is None:
            if not self._sort_begin():
                return
        if self._sort_after is not None or not self._sort_block:
            if self._sort_after is not None:
                self.root.after_cancel(self._sort_after)
                self._sort_after = None
            self._sort_refresh()           # options changed since / never shown
        before = self._sort_backup[0]
        scope = self.sort_scope_var.get()
        n_sel = len([i for i in self._sort_backup[4] if before[i] is not None])
        nr = self._sort_nramps
        ok = bool(self._sort_block)
        self._sort_end()
        if not ok:
            self.recompute()
            return
        if self.rgbs == before:
            self.status_var.set("Already in that order - nothing changed.")
            self.recompute()
            return
        text = "Sort %s%s%s - %d colours" % (
            self.sort_method_var.get(), (" (%d ramps)" % nr) if nr else "",
            (" on %d selected" % n_sel) if scope == "selected" else "",
            sum(1 for e in self.rgbs if e is not None))
        self.history = self.history[:self.hist_pos + 1]
        self.history.append({"text": text, "palette": self.rgbs,
                             "labs": self.labs, "pairs": self.pairs})
        self.hist_pos = len(self.history) - 1
        self.exported = False
        self._refresh_history()
        self.status_var.set("Sorted - recorded as #%d (Back undoes it)." % self.hist_pos)
        self.recompute()

    def _previewing(self):
        return self._sort_backup is not None or self._ramp_backup is not None

    def _sort_busy_msg(self):
        """True (with a status message) while a sort or ramp preview is open."""
        if self._sort_backup is not None:
            self.status_var.set("Sort preview is open - Apply or Cancel it first.")
            return True
        if self._ramp_backup is not None:
            self.status_var.set("Ramp preview is open - Apply or Cancel it first.")
            return True
        return False

    def _cancel_previews(self):
        if self._sort_backup is not None:
            self.sort_cancel()
        if self._ramp_backup is not None:
            self.ramp_cancel()

    def _update_states(self):
        exact = self.exact_var.get()
        if not exact:
            self.similar_var.set(False)
            self.selection.clear()  # selecting needs exact removal
        self.sim_chk.state(["!disabled"] if exact else ["disabled"])
        sim_on = exact and self.similar_var.get()
        for w in self.metric_rbs + [self.tol_spin] + self.scope_rbs:
            w.state(["!disabled"] if sim_on else ["disabled"])
        self.scale.configure(state="normal" if sim_on else "disabled")

    # ---------------------------------------------------------- tolerance
    def _scale_value(self, t):
        hi, res = TOL_RANGE[self.metric_var.get()]
        return round(min(max(t, 0.0), hi) / res) * res

    def _set_tol_text(self, v):
        self._text_lock = True
        self.tol_text.set(fmt_tol(v))
        self._text_lock = False

    def _sync_scale(self):
        m = self.metric_var.get()
        hi, res = TOL_RANGE[m]
        self._scale_lock = True
        state = str(self.scale.cget("state"))
        self.scale.configure(state="normal", from_=0, to=hi, resolution=res)
        self.scale.set(self._scale_value(self.tol[m]))
        self.scale.configure(state=state)
        # Scale fires its command at idle time; release the lock after that
        self.root.after_idle(self._release_scale_lock)

    def _sync_tol_widgets(self):
        m = self.metric_var.get()
        hi, res = TOL_RANGE[m]
        self.range_var.set("0 - %s   (default %s)" % (fmt_tol(hi), fmt_tol(DEFAULT_TOL[m])))
        self.tol_spin.configure(increment=res)
        self._sync_scale()
        self._set_tol_text(self.tol[m])

    def _on_scale_click(self, ev):
        """Click on the bar: jump the handle there, then let Tk start the drag."""
        if str(self.scale.cget("state")) == "disabled":
            return "break"
        if self.scale.identify(ev.x, ev.y) in ("trough1", "trough2"):
            v = float(self.scale.tk.call(self.scale._w, "get", ev.x, ev.y))
            self.scale.set(v)  # handle is now under the cursor
        # fall through to the class binding, which begins dragging the handle

    def _release_scale_lock(self):
        self._scale_lock = False

    def _on_scale(self, val):
        if self._scale_lock:
            return
        m = self.metric_var.get()
        v = float(val)
        _, res = TOL_RANGE[m]
        if abs(v - self._scale_value(self.tol[m])) < res / 2:
            return  # programmatic set or no change
        self.tol[m] = v
        self._set_tol_text(v)
        self.recompute()

    def _apply_tol(self, v, update_text):
        m = self.metric_var.get()
        v = max(0.0, v)
        if abs(v - self.tol[m]) < 1e-12:
            if update_text:
                self._set_tol_text(v)
            return
        self.tol[m] = v
        self._sync_scale()
        if update_text:
            self._set_tol_text(v)
        self.recompute()

    def _on_tol_typed(self, *_):
        """Live: apply whenever the box holds a valid number."""
        if self._text_lock:
            return
        try:
            v = float(self.tol_text.get())
        except ValueError:
            return  # partial input like "" or "1." - wait for more
        if v < 0 or v != v:
            return
        self._apply_tol(v, update_text=False)

    def _on_tol_commit(self, *_):
        """Enter / focus out: tidy the box to the value actually in use."""
        self._set_tol_text(self.tol[self.metric_var.get()])

    def _step_tol(self, n):
        if self.tol_spin.instate(["disabled"]):
            return "break"
        m = self.metric_var.get()
        _, res = TOL_RANGE[m]
        v = round((self.tol[m] + n * res) / res) * res
        self._apply_tol(round(v, 6), update_text=True)
        return "break"

    def _on_spin_arrow(self):
        """Spinbox arrow buttons: snap to the step grid and apply."""
        m = self.metric_var.get()
        _, res = TOL_RANGE[m]
        try:
            v = float(self.tol_text.get())
        except ValueError:
            v = self.tol[m]
        self._apply_tol(round(round(v / res) * res, 6), update_text=True)

    def _on_metric(self):
        self._sync_tol_widgets()
        self.recompute()

    def _on_toggle(self):
        self._update_states()
        self.recompute()

    # ---------------------------------------------------------- loading
    def open_dialog(self):
        from tkinter import filedialog

        p = filedialog.askopenfilename(
            title="Open palette",
            initialdir=self.s.get("last_dir") or None,
            filetypes=[("Palette sources / projects", "*.wad *.pal *.png *" + PROJECT_EXT),
                       ("cleanpal project", "*" + PROJECT_EXT),
                       ("WAD", "*.wad"), ("Palette", "*.pal"),
                       ("PNG", "*.png"), ("All files", "*.*")])
        if p:
            self.load(p)

    def load(self, path):
        from tkinter import messagebox

        if path.lower().endswith(PROJECT_EXT):
            self.load_project(path)
            return
        try:
            rgbs, label = load_palette(path)
        except (ValueError, OSError) as e:
            messagebox.showerror("cleanpal", "Could not load:\n%s\n\n%s" % (path, e))
            return
        if self.move_var.get():
            self._exit_move(record=False)
        if self._sort_backup is not None:
            self._sort_end()
        if self._ramp_backup is not None:
            self._ramp_end()
        self.project_path = None
        self.rgbs = list(rgbs)
        self.labs, self.pairs = build_pairs(self.rgbs)
        self.selection = set()
        self.deleted = set()
        self.history = [{"text": "Original - %d colours" % ENTRIES,
                         "palette": self.rgbs, "labs": self.labs, "pairs": self.pairs}]
        self.hist_pos = 0
        self.exported = True
        self._refresh_history()
        self.src_path = os.path.abspath(path)
        self.s["last_dir"] = os.path.dirname(self.src_path)
        self.file_var.set("%s   [%s]" % (os.path.basename(path), label))
        self._update_title()
        self.status_var.set("")
        self.recompute()

    # ---------------------------------------------------------- analysis
    def recompute(self):
        if self.rgbs is None:
            self.res = None
            self.stats_var.set("Open a palette to begin.")
        else:
            m = self.metric_var.get()
            self.res = analyse(self.rgbs, self.pairs[m], self.exact_var.get(),
                               self.similar_var.get(), self.tol[m],
                               self.selection if self.scope_var.get() == "selected" else None,
                               self.deleted)
            r = self.res
            n_ex = sum(len(g) - 1 for g in r["exact_all"])
            n_si = sum(len(g) - 1 for g in r["similar_all"])
            pre = ("Snapshot #%d  |  " % self.hist_pos) if self.hist_pos else ""
            if self.move_var.get():
                pre = "MOVE MODE  |  " + pre
            if self._sort_backup is not None:
                pre = ("SORT PREVIEW%s  |  " % ((" (%d ramps)" % self._sort_nramps)
                                              if self._sort_nramps else "")) + pre
            if self._ramp_backup is not None:
                pre = "RAMP PREVIEW (%d cells)  |  " % len(self._ramp_targets) + pre
            n_del = r["status"].count("deleted")
            if n_del:
                pre += "Deleted: %d  |  " % n_del
            post = ("  |  Selected: %d" % len(self.selection)) if self.selection else ""
            self.stats_var.set(
                pre + "Exact: %d removed (%d sets)  |  Similar: %d removed (%d clusters)"
                "  |  Kept: %d  |  Empty: %d"
                % (n_ex, len(r["exact_all"]), n_si, len(r["similar_all"]),
                   len(r["kept"]), ENTRIES - len(r["kept"])) + post
                + ("  |  Cull: selected only" if self.similar_var.get()
                   and self.scope_var.get() == "selected" else ""))
        self._update_move_btn()
        self.redraw()
        if self.preview is not None:
            self.preview.schedule()
        self._tools_refresh()

    def token(self):
        if not self.exact_var.get():
            return "(NONE)"
        if not self.similar_var.get():
            return "(EXACT)"
        m = self.metric_var.get()
        return "(%s-%s)" % (METRIC_TOKEN[m], fmt_tol(self.tol[m]))

    # ---------------------------------------------------------- drawing
    def _grid_world(self):
        return 16 * self.CELL + 15 * self.GAP

    def _cell_xy(self, slot):
        """Screen top-left of a cell plus its screen size."""
        step = self.CELL + self.GAP
        sc = self.view_scale
        x = self.off_x + (slot % 16) * step * sc
        y = self.off_y + (slot // 16) * step * sc
        return x, y, self.CELL * sc

    # ---------------------------------------------------------- view transform
    def _fit_scale(self):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        g = self._grid_world()
        return max(min((cw - 2 * self.PAD) / g, (ch - 2 * self.PAD) / g), 0.05)

    def fit_view(self):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        g = self._grid_world()
        self.view_scale = self._fit_scale()
        self.off_x = (cw - g * self.view_scale) / 2
        self.off_y = (ch - g * self.view_scale) / 2
        self.auto_fit = True
        self.redraw()

    def _on_canvas_resize(self, _ev):
        if self.auto_fit:
            self.fit_view()
        else:
            self.redraw()

    def _zoom_at(self, x, y, factor):
        fit = self._fit_scale()
        new = min(max(self.view_scale * factor, fit * self.ZOOM_MIN), fit * self.ZOOM_MAX)
        if new == self.view_scale:
            return
        wx = (x - self.off_x) / self.view_scale
        wy = (y - self.off_y) / self.view_scale
        self.view_scale = new
        self.off_x = x - wx * new
        self.off_y = y - wy * new
        self.auto_fit = False
        self.redraw()

    def _on_wheel(self, ev):
        if ev.delta:
            self._zoom_at(ev.x, ev.y, self.ZOOM_STEP ** (ev.delta / 120.0))

    def _on_pan_start(self, ev):
        self._pan_start = (ev.x, ev.y, self.off_x, self.off_y)
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, ev):
        if self._pan_start is None:
            return
        x0, y0, ox, oy = self._pan_start
        self.off_x = ox + (ev.x - x0)
        self.off_y = oy + (ev.y - y0)
        self.auto_fit = False
        self.redraw()

    def _on_pan_end(self, _ev):
        self._pan_start = None
        self.canvas.configure(cursor="")

    def _on_fit_key(self, ev):
        if ev.widget.winfo_class() in ("TEntry", "Entry", "TCombobox", "Text"):
            return
        self.fit_view()

    # ---------------------------------------------------------- drawing
    def _view_entry(self, slot):
        """(index, status) shown at slot, or None for empty."""
        if self.res is None:
            return None
        if self.align_var.get():
            kept = self.res["kept"]
            return (kept[slot], "kept") if slot < len(kept) else None
        return slot, self.res["status"][slot]

    @staticmethod
    def _hex(c):
        return "#%02x%02x%02x" % c

    @staticmethod
    def _contrast(c):
        return "#000000" if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 140 else "#ffffff"

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        cw = cv.winfo_width()
        ch = cv.winfo_height()
        for slot in range(ENTRIES):
            x, y, C = self._cell_xy(slot)
            if x > cw or y > ch or x + C < 0 or y + C < 0:
                continue  # off-screen
            ent = self._view_entry(slot)
            if ent is None or ent[1] == "empty":
                h = C / 2
                cv.create_rectangle(x, y, x + C, y + C, fill="#5a5a5a", outline="")
                cv.create_rectangle(x, y, x + h, y + h, fill="#7a7a7a", outline="")
                cv.create_rectangle(x + h, y + h, x + C, y + C, fill="#7a7a7a", outline="")
                continue
            idx, st = ent
            rgb = self.rgbs[idx]
            cv.create_rectangle(x, y, x + C, y + C, fill=self._hex(rgb), outline="")
            if C < self.MARKER_MIN_PX or st == "kept":
                continue
            fg = self._contrast(rgb)
            w = max(1, min(6, round(C / 14)))
            if st == "exact":
                i = C * 0.23
                cv.create_line(x + i, y + i, x + C - i, y + C - i, fill=fg, width=w)
                cv.create_line(x + C - i, y + i, x + i, y + C - i, fill=fg, width=w)
            elif st == "similar":
                i = C * 0.27
                cv.create_oval(x + i, y + i, x + C - i, y + C - i, outline=fg, width=w)
            elif st == "deleted":
                i = C * 0.16
                bw = max(2, round(C / 7))
                cv.create_line(x + i, y + C / 2, x + C - i, y + C / 2, fill=fg, width=bw)
        if self.selection and self.res is not None:
            for slot in range(ENTRIES):
                ent = self._view_entry(slot)
                if ent and ent[0] in self.selection:
                    x, y, C = self._cell_xy(slot)
                    w = max(2, min(5, round(C / 10)))
                    # black under, bright cyan over: readable on any colour
                    cv.create_rectangle(x + w, y + w, x + C - w, y + C - w,
                                        outline="#000000", width=w + 3)
                    cv.create_rectangle(x + w, y + w, x + C - w, y + C - w,
                                        outline="#00ffff", width=w)
        if self._ramp_backup is not None and self.res is not None:
            tg = set(self._ramp_targets)
            for slot in range(ENTRIES):
                ent = self._view_entry(slot)
                if ent and ent[0] in tg:
                    x, y, C = self._cell_xy(slot)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#000000", width=3)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#ffb36b", width=2, dash=(4, 2))
        if self._sort_backup is not None and self._sort_block and self.res is not None \
                and self.sort_scope_var.get() == "selected":
            for slot in range(ENTRIES):
                ent = self._view_entry(slot)
                if ent and ent[1] != "empty" and ent[0] in self._sort_block:
                    x, y, C = self._cell_xy(slot)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#000000", width=3)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#7fd4ff", width=2, dash=(4, 2))
        self._draw_hover()

    def _outline(self, slot, colour, dash=None):
        x, y, C = self._cell_xy(slot)
        self.canvas.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                     outline=colour, width=2, dash=dash, tags="hover")

    def _draw_hover(self):
        self.canvas.delete("hover")
        slot = self.hover_slot
        if slot is None or self.res is None:
            self.info_var.set("")
            return
        ent = self._view_entry(slot)
        self._outline(slot, "#ffcc00")
        if ent is None or ent[1] == "empty":
            self.info_var.set("Slot %3d   empty" % slot)
            return

        idx, st = ent
        r = self.res
        rgb = self.rgbs[idx]
        lab = self.labs[idx]
        where = ("Slot %3d <- Index %3d" % (slot, idx)) if self.align_var.get() \
            else ("Index %3d" % idx)
        base = "%s   RGB(%3d,%3d,%3d)   Lab(%.1f, %.1f, %.1f)" % (
            (where,) + tuple(rgb) + tuple(lab))

        if not self.align_var.get():
            own = r["owner"][idx]
            group = [j for j in range(ENTRIES) if r["owner"][j] == own]
            for j in group:
                if j != slot:
                    self._outline(j, "#ffcc00", dash=(3, 2))
            if st == "deleted":
                tail = "deleted (manual) - Del again to restore"
            elif st == "exact":
                tail = "removed - exact copy of %d" % own
            elif st == "similar":
                m = self.metric_var.get()
                d = "%s %.2f" % (METRIC_HOVER[m], metric_dist(
                    m, rgb, self.rgbs[own], lab, self.labs[own]))
                tail = "removed - similar to %d (%s)" % (own, d)
            else:
                others = [j for j in group if j != idx]
                if others:
                    shown = ", ".join(str(j) for j in others[:8])
                    if len(others) > 8:
                        shown += ", ..."
                    tail = "kept - absorbs %d: %s" % (len(others), shown)
                else:
                    tail = "kept"
        else:
            tail = "kept"
        self.info_var.set(base + "   " + tail)

    def _slot_at(self, x, y):
        step = self.CELL + self.GAP
        wx = (x - self.off_x) / self.view_scale
        wy = (y - self.off_y) / self.view_scale
        gx, gy = math.floor(wx / step), math.floor(wy / step)
        if 0 <= gx < 16 and 0 <= gy < 16:
            return int(gy * 16 + gx)
        return None

    def _on_motion(self, ev):
        slot = self._slot_at(ev.x, ev.y)
        if slot != self.hover_slot:
            self.hover_slot = slot
            self._draw_hover()

    def _on_leave(self, _ev):
        self.hover_slot = None
        self._draw_hover()

    # ---------------------------------------------------------- selection
    # ---------------------------------------------------------- side panel
    def _side_layout(self):
        cv = self.side_cv
        rw, rh = self.side.winfo_reqwidth(), self.side.winfo_reqheight()
        if int(cv.cget("width")) != rw:
            cv.configure(width=rw)
        cv.configure(scrollregion=(0, 0, rw, rh))
        if rh > cv.winfo_height() > 1:
            if not self.side_sb.winfo_ismapped():
                self.side_sb.grid(row=0, column=1, sticky="ns")
        else:
            if self.side_sb.winfo_ismapped():
                self.side_sb.grid_remove()
            cv.yview_moveto(0)

    def _side_scroll(self, units):
        if self.side.winfo_reqheight() > self.side_cv.winfo_height():
            self.side_cv.yview_scroll(units, "units")

    def _side_wheel(self, ev):
        if ev.delta:
            self._side_scroll(-1 if ev.delta > 0 else 1)
        return "break"

    def _selectable(self, idx):
        # any slot - blank and exact-removed cells too (ramp targets)
        return self.res is not None and 0 <= idx < ENTRIES

    @staticmethod
    def _alt_down(ev):
        return bool(ev.state & (0x20000 if os.name == "nt" else 0x0008))

    def _on_b1_press(self, ev):
        if self.res is None or self._sort_busy_msg():
            self._drag = None
            return
        if ev.state & 0x0004:
            mode = "toggle"
        elif ev.state & 0x0001:
            mode = "add"
        else:
            mode = "replace"
        d = {"x0": ev.x, "y0": ev.y, "mode": mode, "moved": False, "move": False}
        if self.move_var.get():
            # drag from a SELECTED colour = move the selection;
            # drag from anything else = selection box
            slot = self._slot_at(ev.x, ev.y)
            if slot is not None and slot in self.selection and mode == "replace":
                blk = sorted(self.selection) if len(self.selection) > 1 else [slot]
                d.update(move=True, slot=slot, block=blk, swap=self._alt_down(ev))
        self._drag = d

    def _on_b1_move(self, ev):
        d = self._drag
        if not d:
            return
        if abs(ev.x - d["x0"]) + abs(ev.y - d["y0"]) > 4:
            d["moved"] = True
        if not d["moved"]:
            return
        cv = self.canvas
        if d["move"]:
            cv.delete("moveind")
            swap = d["swap"] or self._alt_down(ev)
            for b in d["block"]:
                x, y, C = self._cell_xy(b)
                cv.create_rectangle(x, y, x + C, y + C, outline="#ffffff", width=2,
                                    dash=(4, 3), tags="moveind")
            t = self._slot_at(ev.x, ev.y)
            if t is not None:
                x, y, C = self._cell_xy(t)
                w = max(3, round(4 * getattr(self, "ui", 1.0)))
                cv.create_rectangle(x, y, x + C, y + C, outline="#000000", width=w + 3,
                                    tags="moveind")
                cv.create_rectangle(x, y, x + C, y + C,
                                    outline="#ff40ff" if swap else "#ffff00",
                                    width=w, tags="moveind")
            return
        cv.delete("marquee")
        w = max(2, round(3 * getattr(self, "ui", 1.0)))
        cv.create_rectangle(d["x0"], d["y0"], ev.x, ev.y, outline="#000000",
                            width=w + 3, tags="marquee")
        cv.create_rectangle(d["x0"], d["y0"], ev.x, ev.y, outline="#00ffff",
                            width=w, tags="marquee")

    def _on_b1_release(self, ev):
        d = self._drag
        self._drag = None
        if not d:
            return
        self.canvas.delete("marquee")
        self.canvas.delete("moveind")
        if d["moved"] and self.scratch is not None and \
                self.root.winfo_containing(ev.x_root, ev.y_root) is self.scratch.cv:
            slot = self._slot_at(d["x0"], d["y0"])
            ent = self._view_entry(slot) if slot is not None else None
            if ent and self.rgbs[ent[0]] is not None:
                i = ent[0]
                if i in self.selection and len(self.selection) > 1:
                    cols = [self.rgbs[j] for j in sorted(self.selection)
                            if self.rgbs[j] is not None]
                else:
                    cols = [self.rgbs[i]]
                self.scratch.add_colours(cols)
            return
        if d["move"] and d["moved"]:
            t = self._slot_at(ev.x, ev.y)
            if t is not None and t != d["slot"]:
                self._do_move(d["block"], d["slot"], t, d["swap"] or self._alt_down(ev))
            return
        hits = []
        if d["moved"]:
            x0, x1 = sorted((d["x0"], ev.x))
            y0, y1 = sorted((d["y0"], ev.y))
            for slot in range(ENTRIES):
                x, y, C = self._cell_xy(slot)
                if x < x1 and x + C > x0 and y < y1 and y + C > y0:
                    ent = self._view_entry(slot)
                    if ent and self._selectable(ent[0]):
                        hits.append(ent[0])
        else:
            slot = self._slot_at(ev.x, ev.y)
            ent = self._view_entry(slot) if slot is not None else None
            if ent and self._selectable(ent[0]):
                hits.append(ent[0])
        self._apply_selection(hits, d["mode"])

    def _apply_selection(self, hits, mode):
        if hits or mode == "replace":
            self.scope_var.set("selected")
        if mode == "replace":
            self.selection = set(hits)
        elif mode == "add":
            self.selection |= set(hits)
        else:
            self.selection ^= set(hits)
        self.sort_scope_var.set("selected" if self.selection else "all")
        self.recompute()

    @staticmethod
    def _typing(ev):
        return ev.widget.winfo_class() in ("TEntry", "Entry", "TSpinbox", "Spinbox",
                                           "Text", "TCombobox")

    def _on_select_all(self, ev):
        if self._typing(ev) or self.res is None or self._sort_busy_msg():
            return
        self._apply_selection([i for i in range(ENTRIES) if self._selectable(i)], "replace")
        return "break"

    def _on_delete_key(self, ev):
        if self._typing(ev):
            return
        self.delete_selected()
        return "break"

    def delete_selected(self):
        """Del / Backspace / button: delete the selection, or restore it if
        every selected colour is already deleted."""
        if self._sort_busy_msg():
            return
        if self.res is None:
            return
        sel = {i for i in self.selection if self.rgbs[i] is not None}
        if not sel:
            self.status_var.set("Select colours first, then press Delete.")
            return
        if sel <= self.deleted:
            self.deleted -= sel
            self.status_var.set("Restored %d colour(s)." % len(sel))
        else:
            n = len(sel - self.deleted)
            self.deleted |= sel
            self.status_var.set("Deleted %d colour(s) - Delete again to restore." % n)
        self.recompute()

    # ---------------------------------------------------------- move mode
    def _on_move_key(self, ev):
        if self._typing(ev) or self.rgbs is None or self._sort_busy_msg():
            return
        self.move_var.set(not self.move_var.get())
        self._on_move_toggle()

    def _on_move_button(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return
        if self._sort_busy_msg():
            return
        self.move_var.set(not self.move_var.get())
        self._on_move_toggle()

    def _update_move_btn(self):
        on = self.move_var.get()
        self.move_btn.configure(
            text="Move mode: ON" if on else "Move mode: OFF",
            relief="sunken" if on else "raised",
            background="#ffd24a" if on else self._move_btn_bg,
            activebackground="#ffe07a" if on else self._move_btn_bg)
        col = "#ffd24a" if on else "#262626"
        self.canvas.configure(highlightbackground=col, highlightcolor=col)

    def _on_move_toggle(self):
        if self.move_var.get():
            if self.rgbs is None:
                self.move_var.set(False)
                self._update_move_btn()
                return
            self._move_start = self.rgbs
            self._move_undo = []
            self._align_before_move = self.align_var.get()
            self.align_var.set(False)
            self.align_chk.state(["disabled"])
            self._refresh_history()
            self.status_var.set("Move mode: click to select, then drag a selected colour "
                                "to move it. Drag elsewhere = selection box. Alt+drag "
                                "swaps. Ctrl+Z undoes a move.")
            self.recompute()
        else:
            self._exit_move()

    def _exit_move(self, record=True):
        if self._move_start is None:
            self.move_var.set(False)
            self._update_move_btn()
            return
        self.move_var.set(False)
        changed = self.rgbs != self._move_start
        if self.ramp is None:
            self.align_chk.state(["!disabled"])
            self.align_var.set(self._align_before_move)
        self._move_start = None
        self._move_undo = []
        if record and changed:
            self.history = self.history[:self.hist_pos + 1]
            self.history.append({
                "text": "Moved colours - %d colours" % sum(1 for e in self.rgbs if e),
                "palette": self.rgbs, "labs": self.labs, "pairs": self.pairs})
            self.hist_pos = len(self.history) - 1
            self.exported = False
            self.status_var.set("Moves recorded as #%d." % self.hist_pos)
        self._refresh_history()
        self.recompute()

    def _do_move(self, block, src, target, swap):
        n = ENTRIES
        if swap and len(block) == 1:
            perm = list(range(n))           # perm[new_slot] = old_slot
            perm[src], perm[target] = target, src
        else:
            bs = set(block)
            rest = [i for i in range(n) if i not in bs]
            pos = min(target, n - len(block))
            perm = rest[:pos] + list(block) + rest[pos:]
        if perm == list(range(n)):
            return
        self._move_undo.append((self.rgbs, self.labs, self.pairs,
                                set(self.deleted), set(self.selection)))
        newpos = [0] * n
        for new, old in enumerate(perm):
            newpos[old] = new
        self.rgbs = [self.rgbs[o] for o in perm]
        self.labs = [self.labs[o] for o in perm]
        self.pairs = {m: [(d, newpos[a], newpos[b]) for d, a, b in v]
                      for m, v in self.pairs.items()}
        self.deleted = {newpos[i] for i in self.deleted}
        self.selection = {newpos[i] for i in self.selection}
        self.recompute()

    def _undo_move(self):
        if not self._move_undo:
            self.status_var.set("No moves to undo.")
            return
        self.rgbs, self.labs, self.pairs, self.deleted, self.selection = self._move_undo.pop()
        self.recompute()

    def clear_selection(self):
        if self._previewing():
            self._cancel_previews()        # Esc also closes a sort / ramp preview
            return
        if self.selection:
            self.selection = set()
            self.recompute()

    # ---------------------------------------------------------- snapshots
    def _load_entry(self, i):
        h = self.history[i]
        if h.get("labs") is None or h.get("pairs") is None:
            h["labs"], h["pairs"] = build_pairs(h["palette"])
        self.hist_pos = i
        self.rgbs = h["palette"]
        self.labs = h["labs"]
        self.pairs = h["pairs"]
        self.selection = set()
        self.deleted = set()
        self._refresh_history()
        self.recompute()

    def take_snapshot(self):
        """Export + reload: the current result becomes the working palette."""
        if self._sort_busy_msg():
            return
        if self.res is None or self.move_var.get():
            return
        r = self.res
        new = result_entries(self.rgbs, r, self.align_var.get())
        if new == self.rgbs:
            self.status_var.set("Nothing would change - no snapshot taken.")
            return
        n_ex = sum(1 for st in r["status"] if st == "exact")
        n_si = sum(1 for st in r["status"] if st == "similar")
        parts = []
        n_del = r["status"].count("deleted")
        if n_del:
            parts.append("Deleted -%d" % n_del)
        if n_ex:
            parts.append("Exact -%d" % n_ex)
        if n_si:
            m = self.metric_var.get()
            scope = ("on %d selected" % len(self.selection)) \
                if self.scope_var.get() == "selected" else "on all"
            parts.append("Similar %s %s %s -%d" % (METRIC_TOKEN[m], fmt_tol(self.tol[m]),
                                                  scope, n_si))
        if self.align_var.get():
            parts.append("packed")
        kept = sum(1 for e in new if e is not None)
        labs, pairs = build_pairs(new)
        self.history = self.history[:self.hist_pos + 1]
        self.history.append({"text": "%s - %d colours" % (", ".join(parts), kept),
                             "palette": new, "labs": labs, "pairs": pairs})
        self.exported = False
        self._load_entry(len(self.history) - 1)
        self.status_var.set("Snapshot #%d taken - now working on it." % self.hist_pos)

    def jump_to(self, i):
        if self._sort_busy_msg():
            return
        if not self.history or not 0 <= i < len(self.history) or self.move_var.get():
            return
        self._load_entry(i)
        self.status_var.set("Loaded #%d." % i)

    def step_back(self):
        if self.hist_pos > 0:
            self.jump_to(self.hist_pos - 1)

    def remove_snapshot(self):
        if self._sort_busy_msg():
            return
        if self.move_var.get():
            return
        if self.hist_pos == 0:
            self.status_var.set("#0 Original can't be removed.")
            return
        gone = self.hist_pos
        del self.history[gone]
        self._load_entry(gone - 1)
        self.status_var.set("Removed snapshot #%d - loaded #%d." % (gone, self.hist_pos))

    def _on_undo_key(self, ev):
        if self._typing(ev):
            return
        if self._previewing():
            self._cancel_previews()
        elif self.move_var.get():
            self._undo_move()
        else:
            self.step_back()

    def _on_hist_select(self, _ev):
        if self.move_var.get() or self._previewing():
            return
        sel = self.hist_list.curselection()
        if sel and sel[0] != self.hist_pos:
            self.jump_to(sel[0])

    def _refresh_history(self):
        lb = self.hist_list
        lb.delete(0, "end")
        for k, h in enumerate(self.history):
            lb.insert("end", "%s#%d  %s" % ("> " if k == self.hist_pos else "  ", k, h["text"]))
        if self.history:
            lb.selection_clear(0, "end")
            lb.selection_set(self.hist_pos)
            lb.see(self.hist_pos)
        moving = self.move_var.get() or self._previewing()
        on = ["!disabled"] if self.hist_pos > 0 and not moving else ["disabled"]
        self.back_btn.state(on)
        self.remove_btn.state(on)
        self.collapse_btn.state(["!disabled"] if len(self.history) > 1 and not moving
                                else ["disabled"])
        self.snap_btn.state(["disabled"] if moving else ["!disabled"])
        lb.configure(state="disabled" if moving else "normal")

    # ---------------------------------------------------------- context menus
    def register_colour_widget(self, w, getter, setter):
        """Give a widget's right-click menu colour items. getter() -> rgb or
        None; setter(rgb) applies a pasted colour."""
        self._colour_ctx[str(w)] = (getter, setter)
        w.bind("<Destroy>", lambda e, k=str(w): self._colour_ctx.pop(k, None), add="+")

    def _clip_text(self, w):
        try:
            return w.clipboard_get()
        except self.tk.TclError:
            return ""

    def _copy_text(self, w, text, what):
        w.clipboard_clear()
        w.clipboard_append(text)
        self.status_var.set("Copied %s: %s" % (what, text))

    def _add_colour_items(self, menu, w, getter, setter):
        rgb = getter()
        st = "normal" if rgb is not None else "disabled"
        menu.add_command(label="Copy colour as hex", state=st,
                         command=lambda: self._copy_text(w, hex_of(rgb), "hex"))
        menu.add_command(label="Copy colour as R,G,B", state=st,
                         command=lambda: self._copy_text(w, "%d,%d,%d" % tuple(rgb),
                                                         "R,G,B"))
        clip = parse_colour(self._clip_text(w))
        menu.add_command(label="Paste colour" + (" (%s)" % hex_of(clip) if clip else ""),
                         state="normal" if clip and setter else "disabled",
                         command=lambda: setter(clip))

    def _popup(self, menu, ev):
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def colour_menu(self, ev, getter, setter):
        """Right-click menu for a colour swatch."""
        menu = self.tk.Menu(ev.widget, tearoff=0)
        self._add_colour_items(menu, ev.widget, getter, setter)
        self._popup(menu, ev)
        return "break"

    def _entry_menu(self, ev):
        w = ev.widget
        try:
            w.focus_set()
        except self.tk.TclError:
            pass
        try:
            has_sel = bool(w.tk.call(w._w, "selection", "present"))
        except self.tk.TclError:
            has_sel = False
        try:
            disabled = w.instate(["disabled"])
        except (AttributeError, self.tk.TclError):
            disabled = str(w.cget("state")) == "disabled"
        try:
            ro = w.instate(["readonly"])
        except (AttributeError, self.tk.TclError):
            ro = False
        editable = not disabled and not ro
        clip = self._clip_text(w)
        menu = self.tk.Menu(w, tearoff=0)

        def ev_(name):
            return lambda: w.event_generate(name)

        def delete():
            try:
                w.delete("sel.first", "sel.last")
            except self.tk.TclError:
                pass

        def select_all():
            try:
                w.selection_range(0, "end")
                w.icursor("end")
            except (AttributeError, self.tk.TclError):
                w.tk.call(w._w, "selection", "range", 0, "end")

        menu.add_command(label="Cut", accelerator="Ctrl+X", command=ev_("<<Cut>>"),
                         state="normal" if has_sel and editable else "disabled")
        menu.add_command(label="Copy", accelerator="Ctrl+C", command=ev_("<<Copy>>"),
                         state="normal" if has_sel else "disabled")
        menu.add_command(label="Paste", accelerator="Ctrl+V", command=ev_("<<Paste>>"),
                         state="normal" if clip and editable else "disabled")
        menu.add_command(label="Delete", command=delete,
                         state="normal" if has_sel and editable else "disabled")
        menu.add_separator()
        menu.add_command(label="Select all", accelerator="Ctrl+A", command=select_all)
        ctx = self._colour_ctx.get(str(w))
        if ctx:
            menu.add_separator()
            self._add_colour_items(menu, w, ctx[0], ctx[1])
        self._popup(menu, ev)
        return "break"

    def _entry_select_all(self, ev):
        w = ev.widget
        try:
            w.selection_range(0, "end")
            w.icursor("end")
        except (AttributeError, self.tk.TclError):
            pass
        return "break"

    # ---------------------------------------------------------- tool windows
    def open_ramp(self):
        if self.ramp is not None:
            self.ramp.win.deiconify()
            self.ramp.win.lift()
            return self.ramp
        if self.move_var.get():
            self._exit_move()
        self.ramp = RampTool(self)
        return self.ramp

    def open_picker(self):
        if self.picker is not None:
            self.picker.win.deiconify()
            self.picker.win.lift()
            return self.picker
        self.picker = ColourPicker(self)
        self.picker.owner = None
        self.picker.set_target(None, (128, 128, 128), None, "")
        return self.picker

    def open_scratch(self):
        if self.scratch is not None:
            self.scratch.win.deiconify()
            self.scratch.win.lift()
            return self.scratch
        self.scratch = ScratchPalette(self)
        return self.scratch

    def add_recent(self, rgb):
        hx = hex_of(rgb)
        rec = [x for x in self.s.get("recent_colours", []) if isinstance(x, str) and x != hx]
        self.s["recent_colours"] = [hx] + rec[:15]

    def _tools_refresh(self):
        """Palette changed: let the open tool windows redraw their markers."""
        if self.ramp is not None:
            self.ramp.draw_strip()
        if self.scratch is not None:
            self.scratch.draw()

    # ---------------------------------------------------------- ramp preview
    def ramp_preview_start(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return False
        if self._sort_backup is not None:
            self.status_var.set("Sort preview is open - Apply or Cancel it first.")
            return False
        if self._ramp_backup is not None:
            return True
        tg = sorted(self.selection)
        if not tg:
            self.status_var.set("Select the cells to fill (blank or filled) first.")
            return False
        if self.move_var.get():
            self._exit_move()
        self._ramp_backup = (self.rgbs, self.labs, self.pairs,
                             set(self.deleted), set(self.selection))
        self._ramp_targets = tg
        self._refresh_history()
        return True

    def ramp_preview_set(self, colours):
        if self._ramp_backup is None:
            return
        b = self._ramp_backup
        tg = self._ramp_targets
        new = list(b[0])
        for i, c in zip(tg, colours):
            new[i] = tuple(c)
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, b[1], b[2], tg)
        self.deleted = set(b[3]) - set(tg)
        self.selection = set(b[4])
        self.status_var.set("Ramp preview: %d cells. Apply keeps it, Cancel restores."
                            % len(tg))
        self.recompute()

    def _ramp_end(self):
        self._ramp_backup = None
        self._ramp_targets = []
        if self.ramp is not None:
            self.ramp.update_buttons()
        self._refresh_history()

    def ramp_cancel(self):
        if self._ramp_backup is None:
            return
        b = self._ramp_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.selection = set(b[3]), set(b[4])
        self._ramp_end()
        self.status_var.set("Ramp cancelled.")
        self.recompute()

    def ramp_apply(self, colours, node_rgbs):
        if self._ramp_backup is None:
            return
        before = self._ramp_backup[0]
        n = len(self._ramp_targets)
        self._ramp_end()
        if self.rgbs == before:
            self.status_var.set("The cells already hold that ramp - nothing changed.")
            self.recompute()
            return
        text = "Ramp %d cells %s - %d colours" % (
            n, " > ".join(hex_of(c) for c in node_rgbs),
            sum(1 for e in self.rgbs if e is not None))
        self._push_history(text)
        self.status_var.set("Ramp applied - recorded as #%d (Back undoes it)."
                            % self.hist_pos)
        self.recompute()

    def _push_history(self, text):
        self.history = self.history[:self.hist_pos + 1]
        self.history.append({"text": text, "palette": self.rgbs,
                             "labs": self.labs, "pairs": self.pairs})
        self.hist_pos = len(self.history) - 1
        self.exported = False
        self._refresh_history()

    # ---------------------------------------------------------- direct colour writes
    def set_cells_colour(self, indices, rgb, what="Set colour"):
        """Write one colour into palette cells (blank or filled)."""
        if self.rgbs is None or self._sort_busy_msg():
            return
        indices = sorted(set(indices))
        if not indices:
            return
        if self.move_var.get():
            self._exit_move()
        rgb = tuple(rgb)
        new = list(self.rgbs)
        for i in indices:
            new[i] = rgb
        if new == self.rgbs:
            self.status_var.set("Those cells already hold %s." % hex_of(rgb))
            return
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, indices)
        self.deleted -= set(indices)
        self._push_history("%s %s - %d cell%s" % (what, hex_of(rgb), len(indices),
                                                  "" if len(indices) == 1 else "s"))
        self.status_var.set("Set %d cell(s) to %s - recorded as #%d."
                            % (len(indices), hex_of(rgb), self.hist_pos))
        self.recompute()

    def drop_colour_on_grid(self, x_root, y_root, rgb):
        if self.rgbs is None:
            return
        slot = self._slot_at(x_root - self.canvas.winfo_rootx(),
                             y_root - self.canvas.winfo_rooty())
        ent = self._view_entry(slot) if slot is not None else None
        if ent is None:
            self.status_var.set("Drop onto a palette cell (switch Align off to reach "
                                "empty slots).")
            return
        self.set_cells_colour([ent[0]], rgb)

    # ---------------------------------------------------------- history collapse
    def collapse_history(self):
        from tkinter import messagebox

        if self._sort_busy_msg() or self.move_var.get() or len(self.history) < 2:
            return
        if not messagebox.askyesno(
                "cleanpal", "Collapse the history to the current entry (#%d)?\n\n"
                            "All other entries are discarded - this can't be undone."
                            % self.hist_pos):
            return
        h = self.history[self.hist_pos]
        kept = sum(1 for e in h["palette"] if e is not None)
        self.history = [{"text": "Collapsed - %d colours" % kept, "palette": h["palette"],
                         "labs": h["labs"], "pairs": h["pairs"]}]
        self.hist_pos = 0
        self.exported = False
        self._refresh_history()
        self.status_var.set("History collapsed to a single entry.")
        self.recompute()

    # ---------------------------------------------------------- projects
    def save_project(self, ask=False):
        from tkinter import filedialog, messagebox

        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return
        if self._sort_busy_msg():
            return
        if self.move_var.get():
            self._exit_move()
        p = self.project_path
        if ask or not p:
            if self.project_path:
                d0, f0 = os.path.split(self.project_path)
            else:
                d0 = self.s.get("project_dir") or (os.path.dirname(self.src_path)
                                                   if self.src_path else None)
                f0 = (os.path.splitext(os.path.basename(self.src_path))[0]
                      if self.src_path else "palette") + PROJECT_EXT
            p = filedialog.asksaveasfilename(
                title="Save project", initialdir=d0 or None, initialfile=f0,
                defaultextension=PROJECT_EXT,
                filetypes=[("cleanpal project", "*" + PROJECT_EXT)])
            if not p:
                return
        data = self.project_data()
        try:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, p)
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not save project:\n%s" % e)
            return
        self.project_path = os.path.abspath(p)
        self.s["project_dir"] = os.path.dirname(self.project_path)
        self.exported = True
        self._update_title()
        self.status_var.set("Saved project %s" % self.project_path)

    def project_data(self):
        def pal(entries):
            return [hex_of(c) if c is not None else None for c in entries]

        ramp = self.ramp.st if self.ramp is not None else self.s.get("ramp")
        settings = self.current_preset()
        if self.ramp is not None:
            settings["align"] = bool(self._ramp_align_saved)
        return {
            PROJECT_MARKER: 1, "version": VERSION,
            "source": self.src_path or "",
            "history": [{"text": h["text"], "palette": pal(h["palette"])}
                        for h in self.history],
            "hist_pos": self.hist_pos,
            "deleted": sorted(self.deleted), "selection": sorted(self.selection),
            "settings": settings,
            "ramp": json.loads(json.dumps(ramp)) if ramp else None,
            "scratch_sets": self.s.get("scratch_sets") or {},
            "scratch_current": self.s.get("scratch_current"),
            "recent_colours": self.s.get("recent_colours", []),
            "picker_mode": self.s.get("picker_mode", PICKER_MODES[0]),
        }

    def load_project(self, path):
        from tkinter import messagebox

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            proj = validate_project(data)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not open project:\n%s\n\n%s"
                                 % (path, e))
            return
        if self.move_var.get():
            self._exit_move(record=False)
        if self._sort_backup is not None:
            self._sort_end()
        if self._ramp_backup is not None:
            self._ramp_end()
        if proj["settings"]:
            self.apply_settings(proj["settings"])
        if proj["ramp"] is not None:
            self.s["ramp"] = proj["ramp"]
            if self.ramp is not None:
                self.ramp.set_state(clean_ramp_state(proj["ramp"]))
        if proj["scratch_sets"]:
            sets = self.s.get("scratch_sets")
            if not isinstance(sets, dict):
                sets = {}
            sets.update(proj["scratch_sets"])
            self.s["scratch_sets"] = sets
            if proj["scratch_current"] in sets:
                self.s["scratch_current"] = proj["scratch_current"]
            if self.scratch is not None:
                self.scratch._refresh_sets()
        if proj["recent_colours"]:
            self.s["recent_colours"] = proj["recent_colours"][:16]
        if proj["picker_mode"]:
            self.s["picker_mode"] = proj["picker_mode"]
        self.history = [{"text": h["text"], "palette": h["palette"],
                         "labs": None, "pairs": None} for h in proj["history"]]
        self.src_path = proj["source"] or os.path.abspath(path)
        self.project_path = os.path.abspath(path)
        self.s["project_dir"] = os.path.dirname(self.project_path)
        self.s["last_dir"] = os.path.dirname(self.project_path)
        self._load_entry(proj["hist_pos"])
        self.deleted = {i for i in proj["deleted"] if self.rgbs[i] is not None}
        self.selection = set(proj["selection"])
        self.exported = True
        self.file_var.set("%s   [cleanpal project, %d entries]"
                          % (os.path.basename(path), len(self.history)))
        self._update_title()
        self.status_var.set("Opened project %s" % path)
        self.recompute()

    # ---------------------------------------------------------- preview
    def open_preview(self):
        if self.preview is not None:
            self.preview.win.deiconify()
            self.preview.win.lift()
            self.preview.win.focus_set()
            return
        self.preview = PreviewWindow(self)

    def preview_palette(self):
        """Colours an export would write right now (unique, in order)."""
        if self.res is None:
            return None
        entries = result_entries(self.rgbs, self.res, False)
        return list(dict.fromkeys(e for e in entries if e is not None))

    # ---------------------------------------------------------- export
    def do_export(self):
        from tkinter import filedialog, messagebox

        if self.res is None:
            messagebox.showinfo("cleanpal", "Open a palette first.")
            return
        label = self.export_var.get()
        stem = os.path.splitext(os.path.basename(self.src_path))[0]
        outdir = self.s.get("last_dir") or os.path.dirname(self.src_path)
        token = self.token()
        suffix, ext = next((e[1], e[2]) for e in EXPORTS if e[0] == label)

        try:
            if suffix is None:
                d = filedialog.askdirectory(title="Folder for analysis PNGs",
                                            initialdir=outdir)
                if not d:
                    return
                files = write_analysis(d, stem, token, self.rgbs, self.res,
                                       self.exact_var.get(), self.similar_var.get(),
                                       self.split_var.get())
                self.status_var.set("Wrote %d file(s) to %s" % (len(files), d))
                self.exported = True
                return

            ftypes = [("PNG image", "*.png")] if ext == ".png" else [("Palette", "*.pal")]
            p = filedialog.asksaveasfilename(
                title="Export " + label, initialdir=outdir,
                initialfile="%s%s-%s%s" % (stem, suffix, token, ext),
                defaultextension=ext, filetypes=ftypes)
            if not p:
                return
            entries = result_entries(self.rgbs, self.res, self.align_var.get())
            write_export(label, p, entries)
            self.s["last_dir"] = os.path.dirname(p)
            self.status_var.set("Wrote %s" % p)
            self.exported = True
            if ext == ".pal" and any(e == GREEN for e in entries):
                messagebox.showwarning(
                    "cleanpal",
                    "A kept colour is exactly (0,255,0) - in the .pal it can't be "
                    "told apart from the green empty-slot fill.")
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Export failed:\n%s" % e)

    # ---------------------------------------------------------- misc
    def show_help(self):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title("cleanpal help")
        txt = tk.Text(win, width=78, height=40, wrap="none", font=("Consolas", 10))
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)

    def _update_title(self):
        t = "cleanpal v%s" % VERSION
        if self.project_path:
            t += " - %s" % os.path.basename(self.project_path)
        elif self.src_path:
            t += " - %s" % os.path.basename(self.src_path)
        if self.preset_name:
            t += "  [preset: %s]" % self.preset_name
        self.root.title(t)

    def current_preset(self):
        d = {"exact": self.exact_var.get(), "similar": self.similar_var.get(),
             "metric": self.metric_var.get(),
             "align": self.align_var.get(), "split": self.split_var.get(),
             "export": self.export_var.get()}
        for m in METRICS:
            d["tol_" + m] = self.tol[m]
        d.update(self.current_sort_settings())
        return d

    def current_sort_settings(self):
        return {"sort_method": self.sort_method_var.get(),
                "sort_params": json.loads(json.dumps(self.sort_params)),
                "sort_key": self.sort_key_var.get(), "sort_high": self.sort_high_var.get(),
                "sort_ramp_order": self.sort_order_var.get(),
                "sort_outliers": self.sort_outlier_var.get(), "sort_min": self.sort_min}

    def save_preset(self):
        from tkinter import filedialog, messagebox

        initdir = self.s.get("preset_dir") or PRESET_DIR
        try:
            os.makedirs(initdir, exist_ok=True)
        except OSError:
            initdir = None
        p = filedialog.asksaveasfilename(
            title="Save preset", initialdir=initdir,
            initialfile=(self.preset_name or "cleanpal-preset") + ".json",
            defaultextension=".json", filetypes=[("cleanpal preset", "*.json")])
        if not p:
            return
        data = {PRESET_MARKER: 1, "version": VERSION, "settings": self.current_preset()}
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not save preset:\n%s" % e)
            return
        self.s["preset_dir"] = os.path.dirname(p)
        self.preset_name = os.path.splitext(os.path.basename(p))[0]
        self._update_title()
        self.status_var.set("Saved preset %s" % p)

    def load_preset(self):
        from tkinter import filedialog, messagebox

        initdir = self.s.get("preset_dir") or PRESET_DIR
        if not os.path.isdir(initdir):
            initdir = None
        p = filedialog.askopenfilename(
            title="Load preset", initialdir=initdir,
            filetypes=[("cleanpal preset", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                d = validate_preset(json.load(fh))
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not load preset:\n%s\n\n%s" % (p, e))
            return
        self.apply_settings(d)
        self.s["preset_dir"] = os.path.dirname(p)
        self.preset_name = os.path.splitext(os.path.basename(p))[0]
        self._update_title()
        self.status_var.set("Loaded preset %s" % p)

    def apply_settings(self, d):
        """Apply a validated preset-style settings dict."""
        if self.ramp is not None and "align" in d:
            self._ramp_align_saved = d["align"]
            d = dict(d)
            del d["align"]
        for k, var in (("exact", self.exact_var), ("similar", self.similar_var),
                       ("align", self.align_var), ("split", self.split_var),
                       ("metric", self.metric_var), ("export", self.export_var)):
            if k in d:
                var.set(d[k])
        for m in METRICS:
            if "tol_" + m in d:
                self.tol[m] = d["tol_" + m]
        if self.similar_var.get() and not self.exact_var.get():
            self.similar_var.set(False)  # similar needs exact
        for k, var in (("sort_method", self.sort_method_var), ("sort_key", self.sort_key_var),
                       ("sort_high", self.sort_high_var),
                       ("sort_ramp_order", self.sort_order_var),
                       ("sort_outliers", self.sort_outlier_var)):
            if k in d:
                var.set(d[k])
        if "sort_min" in d:
            self.sort_min = d["sort_min"]
            self.sort_min_text.set(str(self.sort_min))
        if "sort_params" in d:
            self.sort_params = d["sort_params"]
        self._build_sort_options()
        self._on_sort_option()
        self._update_states()
        self._sync_tol_widgets()
        self.recompute()

    def on_close(self):
        if len(self.history) > 1 and not self.exported:
            from tkinter import messagebox
            if not messagebox.askyesno(
                    "cleanpal", "You have changes that haven't been exported or saved "
                                "as a project.\n\nClose anyway?"):
                return
        self._cancel_previews()
        if self.move_var.get():
            self._exit_move()
        if self.preview is not None:
            self.preview.store_state()
        for w in (self.ramp, self.picker, self.scratch):
            if w is not None:
                w.close()
        self.s.update({
            "exact": self.exact_var.get(), "similar": self.similar_var.get(),
            "metric": self.metric_var.get(),
            "tol_de2000": self.tol["de2000"],
            "tol_lab": self.tol["lab"], "tol_rgb": self.tol["rgb"],
            "align": self.align_var.get(), "split": self.split_var.get(),
            "export": self.export_var.get(),
        })
        self.s.update(self.current_sort_settings())
        try:
            zoomed = self.root.state() == "zoomed"
            self.s["zoomed"] = zoomed
            if not zoomed:
                self.s["geometry"] = self.root.geometry()
        except Exception:
            pass
        err = save_settings(self.s)
        if err:
            from tkinter import messagebox
            messagebox.showwarning("cleanpal", "Settings could not be saved:\n" + err)
        self.root.destroy()


# ============================================================ WAD graphics
PNG_SIG = b"\x89PNG\r\n\x1a\n"
NON_GFX = {"PLAYPAL", "COLORMAP", "TEXTURE1", "TEXTURE2", "PNAMES", "ENDOOM", "GENMIDI",
           "DMXGUS", "DMXGUSC", "ANIMATED", "SWITCHES", "THINGS", "LINEDEFS", "SIDEDEFS",
           "VERTEXES", "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP",
           "BEHAVIOR", "TEXTMAP", "ZNODES", "DIALOGUE", "ENDMAP", "SCRIPTS", "DEHACKED",
           "MAPINFO", "UMAPINFO", "DECORATE", "ZMAPINFO", "SNDINFO", "LANGUAGE",
           "TEXTURES", "SNDSEQ", "GAMEINFO", "DMAPINFO", "SBARINFO", "MENUDEF"}
REGION_START = {"S_START": "sprite", "SS_START": "sprite", "F_START": "flat",
                "FF_START": "flat", "P_START": "patch", "PP_START": "patch"}
REGION_END = {"S_END", "SS_END", "F_END", "FF_END", "P_END", "PP_END"}
KIND_LABEL = {"flat": "Flats", "sprite": "Sprites", "patch": "Patches",
              "graphic": "Graphics"}


def is_doom_picture(d):
    """Strict structural check for the Doom picture (patch) format."""
    n = len(d)
    if n < 12:
        return False
    w, h = struct.unpack_from("<HH", d, 0)
    if not (1 <= w <= 4096 and 1 <= h <= 4096) or n < 8 + 4 * w:
        return False
    lo = 8 + 4 * w
    for x in range(w):
        off = struct.unpack_from("<I", d, 8 + 4 * x)[0]
        if not lo <= off < n:
            return False
        p = off
        for _ in range(1024):
            if p >= n:
                return False
            top = d[p]
            if top == 0xFF:
                break
            if p + 1 >= n:
                return False
            ln = d[p + 1]
            p += 4 + ln
            if p > n:
                return False
        else:
            return False
    return True


def decode_doom_picture(d, pal):
    from PIL import Image

    w, h = struct.unpack_from("<HH", d, 0)
    buf = bytearray(w * h * 4)
    for x in range(w):
        p = struct.unpack_from("<I", d, 8 + 4 * x)[0]
        prev = -1
        while p < len(d) and d[p] != 0xFF:
            top = d[p]
            ln = d[p + 1]
            if top <= prev:          # DeePsea tall patches
                top += prev
            prev = top
            src = p + 3
            for k in range(ln):
                y = top + k
                if 0 <= y < h and src + k < len(d):
                    r, g, b = pal[d[src + k]]
                    i = (y * w + x) * 4
                    buf[i:i + 4] = bytes((r, g, b, 255))
            p += 4 + ln
    return Image.frombytes("RGBA", (w, h), bytes(buf))


def decode_flat(d, pal):
    from PIL import Image

    h = len(d) // 64
    return Image.frombytes("RGB", (64, h), bytes(c for i in d[:64 * h] for c in pal[i])
                           ).convert("RGBA")


def decode_png(d):
    import io
    from PIL import Image

    with Image.open(io.BytesIO(d)) as im:
        im.load()
        return im.convert("RGBA")


class WadSource:
    """Read-only index of the graphics in a WAD. Images decode on demand."""

    def __init__(self, path, fallback_pal):
        with open(path, "rb") as fh:
            data = fh.read()
        if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
            raise ValueError("Not a valid WAD file (bad header).")
        num, ofs = struct.unpack_from("<ii", data, 4)
        lumps = []
        for i in range(num):
            o = ofs + i * 16
            if o + 16 > len(data):
                break
            pos, size = struct.unpack_from("<ii", data, o)
            name = data[o + 8:o + 16].split(b"\x00")[0].decode("ascii", "replace").upper()
            lumps.append((name, pos, size))
        self.data = data
        self.path = path
        self.lumps = lumps

        self.pal = fallback_pal
        self.pal_src = "loaded palette"
        for name, pos, size in lumps:
            if name == "PLAYPAL" and size >= 768:
                raw = data[pos:pos + 768]
                self.pal = [tuple(raw[i * 3:i * 3 + 3]) for i in range(256)]
                self.pal_src = "WAD PLAYPAL"
                break

        items = []
        region = None
        for i, (name, pos, size) in enumerate(lumps):
            if name in REGION_START:
                region = REGION_START[name]
                continue
            if name in REGION_END:
                region = None
                continue
            if size <= 0:
                continue
            d = data[pos:pos + size]
            if d[:8] == PNG_SIG:
                items.append({"name": name, "kind": region or "graphic", "lump": i,
                              "fmt": "png"})
            elif region == "flat":
                if size in (4096, 8192):
                    items.append({"name": name, "kind": "flat", "lump": i, "fmt": "flat"})
            elif region in ("sprite", "patch"):
                if is_doom_picture(d):
                    items.append({"name": name, "kind": region, "lump": i, "fmt": "doom"})
            elif name not in NON_GFX and not name.startswith(("D_", "DS", "DP", "DEMO")) \
                    and is_doom_picture(d):
                items.append({"name": name, "kind": "graphic", "lump": i, "fmt": "doom"})
        for it in items:
            it["key"] = (path, it["kind"], it["name"], it.get("lump"))
        self.items = items

    def _lump(self, i):
        name, pos, size = self.lumps[i]
        return self.data[pos:pos + size]

    def image(self, it):
        f = it["fmt"]
        d = self._lump(it["lump"])
        if f == "png":
            return decode_png(d)
        if f == "flat":
            return decode_flat(d, self.pal)
        return decode_doom_picture(d, self.pal)


# ============================================================ preview window
class PreviewWindow:
    PAD = 10
    ZOOM_STEP = 1.2
    GAP = 8                 # page pixels between grid cells
    MAX_CACHE = 400
    TYPES = ["All", "Patches", "Sprites", "Flats", "Graphics"]

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Palettised preview")
        self.win.minsize(480, 340)
        try:
            self.win.geometry(app.s.get("preview_geometry") or "820x700")
        except tk.TclError:
            pass
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(2, weight=1)

        self.mode = None          # "folder" / "wad"
        self.folder = None
        self.wad = None
        self.items = []
        self.view = []
        self.idx = 0
        self.orig_cache = {}
        self.conv_cache = {}
        self.conv_cache_key = None
        self.errors = {}
        self.content = None
        self.content_key = None
        self.cells = []           # grid: (view index, x, y, w, h) in page pixels
        self._used = 0
        self._native_checkers = {}
        self.view_scale = 1.0
        self.off_x = self.off_y = 0.0
        self.auto_fit = True
        self._pan = None
        self._after = None
        self._tkimg = None
        self._checker = (None, None)

        s = app.s
        self.view_var = tk.StringVar(value="pal")
        self.dither_var = tk.BooleanVar(value=bool(s.get("preview_dither", False)))
        self.type_var = tk.StringVar(value=s.get("preview_type", "All"))
        if self.type_var.get() not in self.TYPES:
            self.type_var.set("All")
        self.filter_var = tk.StringVar(value=s.get("preview_filter", ""))
        self.layout_var = tk.StringVar(value=s.get("preview_layout", "single"))
        if self.layout_var.get() not in ("single", "grid"):
            self.layout_var.set("single")
        self.cols = self._clamp(s.get("preview_cols", 4))
        self.rows = self._clamp(s.get("preview_rows", 4))
        self.names_var = tk.BooleanVar(value=bool(s.get("preview_names", True)))
        self.cols_var = tk.StringVar(value=str(self.cols))
        self.rows_var = tk.StringVar(value=str(self.rows))
        self.name_var = tk.StringVar(value="Open a folder of PNGs or a WAD")
        self.info_var = tk.StringVar(value="")
        self.hover_var = tk.StringVar(value="")

        # row 1: sources + navigation
        top = ttk.Frame(self.win, padding=(8, 8, 8, 2))
        top.grid(row=0, column=0, sticky="ew")
        ttk.Button(top, text="Open folder...", command=self.open_folder_dialog).pack(side="left")
        ttk.Button(top, text="Open WAD...", command=self.open_wad_dialog).pack(
            side="left", padx=(6, 0))
        ttk.Button(top, text="\u25b2", width=3, command=lambda: self.step(-1)).pack(
            side="left", padx=(10, 0))
        ttk.Button(top, text="\u25bc", width=3, command=lambda: self.step(1)).pack(
            side="left", padx=(2, 0))
        ttk.Label(top, textvariable=self.name_var).pack(side="left", padx=8)

        # row 2: filters, layout, view
        row2 = ttk.Frame(self.win, padding=(8, 2, 8, 4))
        row2.grid(row=1, column=0, sticky="ew")
        ttk.Label(row2, text="Type").pack(side="left")
        self.type_cb = ttk.Combobox(row2, textvariable=self.type_var, values=self.TYPES,
                                    state="readonly", width=9)
        self.type_cb.pack(side="left", padx=(4, 8))
        self.type_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        ttk.Label(row2, text="Name").pack(side="left")
        self.filter_entry = ttk.Entry(row2, textvariable=self.filter_var, width=11)
        self.filter_entry.pack(side="left", padx=(4, 10))
        self.filter_var.trace_add("write", lambda *a: self.apply_filter())

        ttk.Radiobutton(row2, text="Single", value="single", variable=self.layout_var,
                        command=self._on_layout).pack(side="left")
        ttk.Radiobutton(row2, text="Grid", value="grid", variable=self.layout_var,
                        command=self._on_layout).pack(side="left", padx=(4, 4))
        self.cols_sb = ttk.Spinbox(row2, from_=1, to=16, width=3, textvariable=self.cols_var)
        self.cols_sb.pack(side="left")
        ttk.Label(row2, text="x").pack(side="left", padx=2)
        self.rows_sb = ttk.Spinbox(row2, from_=1, to=16, width=3, textvariable=self.rows_var)
        self.rows_sb.pack(side="left")
        ttk.Checkbutton(row2, text="Names", variable=self.names_var,
                        command=self.redraw).pack(side="left", padx=(8, 0))
        for sb, var in ((self.cols_sb, self.cols_var), (self.rows_sb, self.rows_var)):
            sb.bind("<Up>", lambda e, v=var: self._spin(v, 1))
            sb.bind("<Down>", lambda e, v=var: self._spin(v, -1))
            sb.bind("<MouseWheel>", lambda e, v=var: self._spin(v, 1 if e.delta > 0 else -1))
            var.trace_add("write", lambda *a: self._on_grid_size())

        ttk.Checkbutton(row2, text="Dither", variable=self.dither_var,
                        command=self.schedule).pack(side="right")
        ttk.Radiobutton(row2, text="Original", value="orig", variable=self.view_var,
                        command=self.redraw).pack(side="right", padx=(0, 8))
        ttk.Radiobutton(row2, text="Palettised", value="pal", variable=self.view_var,
                        command=self.redraw).pack(side="right", padx=(0, 4))

        self.canvas = tk.Canvas(self.win, bg="#262626", highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=8)
        cv = self.canvas
        cv.bind("<Configure>", lambda e: self.redraw())
        cv.bind("<MouseWheel>", self._on_wheel)
        cv.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, self.ZOOM_STEP))
        cv.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / self.ZOOM_STEP))
        cv.bind("<ButtonPress-2>", self._pan_start)
        cv.bind("<B2-Motion>", self._pan_move)
        cv.bind("<ButtonRelease-2>", self._pan_end)
        cv.bind("<Double-Button-2>", lambda e: self.fit())
        cv.bind("<Button-1>", lambda e: cv.focus_set())
        cv.bind("<Double-Button-1>", self._on_double_click)
        cv.bind("<Motion>", self._on_motion)
        cv.bind("<Leave>", lambda e: self.hover_var.set(""))

        bottom = ttk.Frame(self.win, padding=(8, 4, 8, 8))
        bottom.grid(row=3, column=0, sticky="ew")
        ttk.Label(bottom, textvariable=self.info_var, font=("Consolas", 10)).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.hover_var, font=("Consolas", 10)).pack(anchor="w")

        w = self.win
        w.bind("<Up>", lambda e: self.step(-1))
        w.bind("<Down>", lambda e: self.step(1))
        w.bind("<Prior>", lambda e: self.step(-1))
        w.bind("<Next>", lambda e: self.step(1))
        w.bind("<space>", self._key_flip)
        w.bind("<Key-f>", self._key_fit)
        w.bind("<Key-F>", self._key_fit)
        w.bind("<Key-n>", self._key_names)
        w.bind("<Key-N>", self._key_names)
        w.protocol("WM_DELETE_WINDOW", self.close)
        w.focus_set()

        st = s.get("preview_mode")
        sel = s.get("preview_item")
        if st == "wad" and s.get("preview_wad") and os.path.isfile(s["preview_wad"]):
            self.open_wad(s["preview_wad"], sel)
        elif s.get("preview_dir") and os.path.isdir(s["preview_dir"]):
            self.open_folder(s["preview_dir"], sel)
        else:
            self.redraw()

    # ---------------- helpers
    @staticmethod
    def _clamp(v):
        try:
            return max(1, min(16, int(v)))
        except (TypeError, ValueError):
            return 4

    @staticmethod
    def _typing(ev):
        return ev.widget.winfo_class() in ("TEntry", "Entry", "TCombobox", "TSpinbox")

    def _key_flip(self, ev):
        if self._typing(ev):
            return
        return self.flip()

    def _key_fit(self, ev):
        if self._typing(ev):
            return
        return self.fit()

    def _key_names(self, ev):
        if self._typing(ev):
            return
        self.names_var.set(not self.names_var.get())
        self.redraw()
        return "break"

    def _grid(self):
        return self.layout_var.get() == "grid"

    def _per_page(self):
        return self.cols * self.rows

    # ---------------- layout controls
    def _spin(self, var, n):
        var.set(str(self._clamp(self._clamp(var.get()) + n)))
        return "break"

    def _on_grid_size(self):
        try:
            c, r = int(self.cols_var.get()), int(self.rows_var.get())
        except ValueError:
            return                      # partial typing - wait
        if not (1 <= c <= 16 and 1 <= r <= 16):
            return
        if (c, r) != (self.cols, self.rows):
            self.cols, self.rows = c, r
            if self._grid():
                self.show(refit=True)

    def _on_layout(self):
        self.show(refit=True)

    # ---------------- sources
    def open_folder_dialog(self):
        from tkinter import filedialog

        d = filedialog.askdirectory(parent=self.win, title="Folder of PNGs",
                                    initialdir=self.folder or self.app.s.get("preview_dir")
                                    or None)
        if d:
            self.open_folder(d)

    def open_wad_dialog(self):
        from tkinter import filedialog

        last = self.app.s.get("preview_wad")
        p = filedialog.askopenfilename(
            parent=self.win, title="Open WAD",
            initialdir=os.path.dirname(last) if last else None,
            filetypes=[("WAD", "*.wad"), ("All files", "*.*")])
        if p:
            self.open_wad(p)

    def _reset_caches(self):
        self.orig_cache.clear()
        self.conv_cache.clear()
        self.errors.clear()
        self.content_key = None

    def open_folder(self, folder, select=None):
        try:
            names = sorted((f for f in os.listdir(folder) if f.lower().endswith(".png")),
                           key=str.lower)
        except OSError as e:
            self.name_var.set("Can't read folder: %s" % e)
            return
        self.mode, self.folder, self.wad = "folder", folder, None
        self.items = [{"name": n, "kind": "png", "fmt": "file",
                       "path": os.path.join(folder, n),
                       "key": ("file", os.path.join(folder, n))} for n in names]
        self._reset_caches()
        self.app.s.update(preview_mode="folder", preview_dir=folder)
        self.type_cb.state(["disabled"])
        self.apply_filter(select)

    def open_wad(self, path, select=None):
        from tkinter import messagebox

        fallback = None
        if self.app.history:
            fallback = [c if c is not None else (0, 0, 0)
                        for c in self.app.history[0]["palette"]]
        if fallback is None:
            fallback = [(i, i, i) for i in range(256)]
        try:
            wad = WadSource(path, fallback)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not open WAD:\n%s\n\n%s" % (path, e),
                                 parent=self.win)
            return
        self.mode, self.wad, self.folder = "wad", wad, None
        self.items = wad.items
        self._reset_caches()
        self.app.s.update(preview_mode="wad", preview_wad=path)
        self.type_cb.state(["!disabled"])
        self.apply_filter(select)

    def apply_filter(self, select=None):
        if select is None and self.view and 0 <= self.idx < len(self.view):
            select = self.view[self.idx]["name"]
        kind = self.type_var.get()
        text = self.filter_var.get().strip().upper()
        self.app.s.update(preview_type=kind, preview_filter=self.filter_var.get())
        self.view = [it for it in self.items
                     if not (self.mode == "wad" and kind != "All"
                             and KIND_LABEL.get(it["kind"]) != kind)
                     and (not text or text in it["name"].upper())]
        names = [it["name"] for it in self.view]
        self.idx = names.index(select) if select in names else 0
        self.show(refit=True)

    # ---------------- images
    def _orig(self, it):
        from PIL import Image

        k = it["key"]
        if k in self.orig_cache:
            return self.orig_cache[k]
        if len(self.orig_cache) > self.MAX_CACHE:
            self.orig_cache.clear()
        try:
            if it["fmt"] == "file":
                with Image.open(it["path"]) as im:   # read only
                    im.load()
                    img = im.convert("RGBA")
            else:
                img = self.wad.image(it)
        except Exception as e:      # bad data: report, keep browsing
            img = None
            self.errors[k] = str(e)
        self.orig_cache[k] = img
        return img

    def _conv(self, it, img, pal):
        ck = (tuple(pal), self.dither_var.get())
        if ck != self.conv_cache_key:
            self.conv_cache.clear()
            self.conv_cache_key = ck
        k = it["key"]
        if k not in self.conv_cache:
            if len(self.conv_cache) > self.MAX_CACHE:
                self.conv_cache.clear()
            self.conv_cache[k] = palettise(img, pal, self.dither_var.get())
        return self.conv_cache[k]

    def _native_checker(self, size):
        from PIL import Image

        if size in self._native_checkers:
            return self._native_checkers[size]
        w, h = size
        cell = 4
        img = Image.new("RGBA", size)
        img.putdata([(90, 90, 90, 255) if ((x // cell) + (y // cell)) % 2
                     else (122, 122, 122, 255) for y in range(h) for x in range(w)])
        if len(self._native_checkers) > 64:
            self._native_checkers.clear()
        self._native_checkers[size] = img
        return img

    def _page_range(self):
        per = self._per_page()
        start = (self.idx // per) * per
        return start, min(start + per, len(self.view))

    def _content(self):
        """The image to display (single image or a whole grid page)."""
        from PIL import Image

        if not self.view:
            return None
        pal = self.app.preview_palette()
        pal_on = self.view_var.get() == "pal" and bool(pal)
        palkey = (tuple(pal), self.dither_var.get()) if pal_on else None
        if self._grid():
            a, b = self._page_range()
            key = ("grid", tuple(it["key"] for it in self.view[a:b]), self.cols, palkey)
        else:
            key = ("single", self.view[self.idx]["key"], palkey)
        if key == self.content_key:
            return self.content

        used = set()

        def get(it):
            img = self._orig(it)
            if img is not None and pal_on:
                img = self._conv(it, img, pal)
                cols = img.getcolors(1 << 16)
                if cols:
                    used.update(c[:3] for _, c in cols if c[3])
            return img

        self.cells = []
        if not self._grid():
            img = get(self.view[self.idx])
        else:
            a, b = self._page_range()
            ims = [(i, get(self.view[i])) for i in range(a, b)]
            sizes = [im.size for _, im in ims if im is not None] or [(64, 64)]
            cw = max(s[0] for s in sizes)
            ch = max(s[1] for s in sizes)
            G = self.GAP
            nrows = -(-len(ims) // self.cols)
            W = self.cols * cw + (self.cols + 1) * G
            H = nrows * ch + (nrows + 1) * G
            img = Image.new("RGBA", (W, H), (30, 30, 30, 255))
            for k, (i, im) in enumerate(ims):
                cx = G + (k % self.cols) * (cw + G)
                cy = G + (k // self.cols) * (ch + G)
                self.cells.append((i, cx, cy, cw, ch))
                if im is None:
                    continue
                ox, oy = cx + (cw - im.size[0]) // 2, cy + (ch - im.size[1]) // 2
                img.paste(self._native_checker(im.size), (ox, oy))
                img.alpha_composite(im, (ox, oy))
        self._used = len(used)
        self.content = img
        self.content_key = key
        return img

    # ---------------- navigation
    def show(self, refit=False):
        prev = self.content.size if self.content is not None else None
        self.content_key = None
        if not self.view:
            self.content = None
            what = "PNGs" if self.mode == "folder" else "matching graphics"
            self.name_var.set("No %s" % what if self.mode else
                              "Open a folder of PNGs or a WAD")
            self.info_var.set("")
            self.redraw()
            return
        img = self._content()
        if self._grid():
            per = self._per_page()
            a, b = self._page_range()
            pages = -(-len(self.view) // per)
            self.name_var.set("Page %d/%d  (%d-%d of %d)" % (
                a // per + 1, pages, a + 1, b, len(self.view)))
            refit = True                       # every page change refits
        else:
            it = self.view[self.idx]
            self.app.s["preview_item"] = it["name"]
            if img is None:
                self.name_var.set("%d/%d  %s  (can't decode: %s)" % (
                    self.idx + 1, len(self.view), it["name"],
                    self.errors.get(it["key"], "?")))
            else:
                kind = "" if it["fmt"] == "file" else "%s " % it["kind"]
                self.name_var.set("%d/%d  %s  [%s%dx%d]" % (
                    self.idx + 1, len(self.view), it["name"], kind,
                    img.size[0], img.size[1]))
            if img is not None and prev != img.size:
                refit = True
        if refit:
            self.auto_fit = True
        self.redraw()

    def step(self, n):
        if self.view:
            if self._grid():
                per = self._per_page()
                pages = -(-len(self.view) // per)
                page = (self.idx // per + n) % pages
                self.idx = page * per
            else:
                self.idx = (self.idx + n) % len(self.view)
            self.show()
        return "break"

    def flip(self):
        self.view_var.set("orig" if self.view_var.get() == "pal" else "pal")
        self.redraw()
        return "break"

    def _cell_at(self, x, y):
        if not self._grid() or self.content is None:
            return None
        px = (x - self.off_x) / self.view_scale
        py = (y - self.off_y) / self.view_scale
        for c in self.cells:
            i, cx, cy, cw, ch = c
            if cx <= px < cx + cw and cy <= py < cy + ch:
                return c
        return None

    def _on_motion(self, ev):
        c = self._cell_at(ev.x, ev.y)
        if c is None:
            self.hover_var.set("")
            return
        it = self.view[c[0]]
        im = self.orig_cache.get(it["key"])
        size = ("%dx%d" % im.size) if im is not None else "can't decode"
        kind = "" if it["fmt"] == "file" else "%s " % it["kind"]
        self.hover_var.set("%s  [%s%s]   double-click = open single" % (it["name"], kind, size))

    def _on_double_click(self, ev):
        c = self._cell_at(ev.x, ev.y)
        if c is None:
            return
        self.idx = c[0]
        self.layout_var.set("single")
        self.show(refit=True)

    # ---------------- conversion
    def schedule(self):
        if self._after is not None:
            self.win.after_cancel(self._after)
        self._after = self.win.after(100, self._refresh)

    def _refresh(self):
        self._after = None
        self.redraw()

    # ---------------- view transform
    def _fit_scale(self, size):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        return max(min((cw - 2 * self.PAD) / size[0], (ch - 2 * self.PAD) / size[1]), 0.01)

    def fit(self):
        self.auto_fit = True
        self.redraw()
        return "break"

    def _zoom_at(self, x, y, factor):
        if self.content is None:
            return
        fit = self._fit_scale(self.content.size)
        new = min(max(self.view_scale * factor, fit * 0.25), max(fit * 8, 32.0))
        if new == self.view_scale:
            return
        wx = (x - self.off_x) / self.view_scale
        wy = (y - self.off_y) / self.view_scale
        self.view_scale = new
        self.off_x = x - wx * new
        self.off_y = y - wy * new
        self.auto_fit = False
        self.redraw()

    def _on_wheel(self, ev):
        if ev.delta:
            self._zoom_at(ev.x, ev.y, self.ZOOM_STEP ** (ev.delta / 120.0))

    def _pan_start(self, ev):
        self._pan = (ev.x, ev.y, self.off_x, self.off_y)
        self.canvas.configure(cursor="fleur")

    def _pan_move(self, ev):
        if self._pan is None:
            return
        x0, y0, ox, oy = self._pan
        self.off_x = ox + ev.x - x0
        self.off_y = oy + ev.y - y0
        self.auto_fit = False
        self.redraw()

    def _pan_end(self, _ev):
        self._pan = None
        self.canvas.configure(cursor="")

    # ---------------- drawing
    def _checker_img(self, size):
        from PIL import Image

        if self._checker[0] == size:
            return self._checker[1]
        cell = 8
        cw, ch = -(-size[0] // cell), -(-size[1] // cell)
        small = Image.new("RGBA", (cw, ch))
        small.putdata([(90, 90, 90, 255) if (x + y) % 2 else (122, 122, 122, 255)
                       for y in range(ch) for x in range(cw)])
        big = small.resize((cw * cell, ch * cell), _pil_const("Resampling", "NEAREST"))
        img = big.crop((0, 0, size[0], size[1]))
        self._checker = (size, img)
        return img

    def redraw(self):
        from PIL import ImageTk

        cv = self.canvas
        cv.delete("all")
        im = self._content()
        if im is None:
            msg = "Open a folder of PNGs or a WAD" if not self.mode else "Nothing to show"
            cv.create_text(cv.winfo_width() / 2, cv.winfo_height() / 2, text=msg,
                           fill="#888")
            return
        cw, ch = cv.winfo_width(), cv.winfo_height()
        w, h = im.size
        if self.auto_fit:
            self.view_scale = self._fit_scale(im.size)
            self.off_x = (cw - w * self.view_scale) / 2
            self.off_y = (ch - h * self.view_scale) / 2
        sc = self.view_scale
        sx0 = max(0, math.floor(-self.off_x / sc))
        sy0 = max(0, math.floor(-self.off_y / sc))
        sx1 = min(w, math.ceil((cw - self.off_x) / sc))
        sy1 = min(h, math.ceil((ch - self.off_y) / sc))
        if sx1 > sx0 and sy1 > sy0:
            dw = max(1, round((sx1 - sx0) * sc))
            dh = max(1, round((sy1 - sy0) * sc))
            disp = im.crop((sx0, sy0, sx1, sy1)).resize(
                (dw, dh), _pil_const("Resampling", "NEAREST"))
            out = self._checker_img((dw, dh)).copy()
            out.alpha_composite(disp)
            self._tkimg = ImageTk.PhotoImage(out)
            cv.create_image(round(self.off_x + sx0 * sc), round(self.off_y + sy0 * sc),
                            image=self._tkimg, anchor="nw")
        # names on grid cells when big enough to read
        for i, cx, cy, cwid, chei in (self.cells if self.names_var.get() else ()):
            if cwid * sc < 70:
                break
            x = self.off_x + cx * sc
            y = self.off_y + cy * sc
            if x > cw or y > ch or x + cwid * sc < 0 or y + chei * sc < 0:
                continue
            t = cv.create_text(x + 4, y + 3, text=self.view[i]["name"], anchor="nw",
                               fill="#ffffff", font=("Consolas", 9))
            bx = cv.bbox(t)
            r = cv.create_rectangle(bx[0] - 2, bx[1] - 1, bx[2] + 2, bx[3] + 1,
                                    fill="#000000", outline="")
            cv.tag_lower(r, t)

        src = ("   source pal: %s" % self.wad.pal_src) if self.mode == "wad" else ""
        pal = self.app.preview_palette() or []
        if self.view_var.get() == "pal" and pal:
            self.info_var.set("PALETTISED   palette: %d colours   used: %d   dither: %s   "
                              "zoom %.0f%%%s   (Space = original)" % (
                                  len(pal), self._used,
                                  "on" if self.dither_var.get() else "off", sc * 100, src))
        else:
            self.info_var.set("ORIGINAL   zoom %.0f%%%s   (Space = palettised)" % (
                sc * 100, src))

    # ---------------- close
    def store_state(self):
        try:
            self.app.s["preview_geometry"] = self.win.geometry()
        except Exception:
            pass
        self.app.s.update(preview_dither=self.dither_var.get(),
                          preview_layout=self.layout_var.get(),
                          preview_names=self.names_var.get(),
                          preview_cols=self.cols, preview_rows=self.rows)

    def close(self):
        self.store_state()
        if self._after is not None:
            self.win.after_cancel(self._after)
        self.app.preview = None
        self.win.destroy()


# ============================================================ eyedropper
class EyeDropper:
    """Full-screen screenshot overlay: click a pixel to pick it, with a
    magnifier loupe. Esc / right-click cancels."""
    LOUPE_SRC = 15
    LOUPE_PX = 9

    def __init__(self, app, callback):
        from PIL import Image, ImageGrab, ImageTk

        tk = app.tk
        self.app = app
        self.cb = callback
        x0 = y0 = 0
        try:
            if os.name == "nt":
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                x0, y0 = gm(76), gm(77)
                shot = ImageGrab.grab(all_screens=True)
            else:
                shot = ImageGrab.grab()
        except Exception as e:  # noqa: BLE001 - any grab failure
            from tkinter import messagebox
            messagebox.showerror("cleanpal", "Screen capture failed:\n%s" % e)
            self.win = None
            return
        self.shot = shot.convert("RGB")
        self.px = self.shot.load()
        w, h = self.shot.size
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.geometry("%dx%d%+d%+d" % (w, h, x0, y0))
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self.win, width=w, height=h, highlightthickness=0,
                            cursor="crosshair")
        self.cv.pack()
        self._img = ImageTk.PhotoImage(self.shot)
        self.cv.create_image(0, 0, anchor="nw", image=self._img)
        self._loupe = None
        self._Image = Image
        self._ImageTk = ImageTk
        self.cv.bind("<Motion>", self._motion)
        self.cv.bind("<ButtonPress-1>", self._pick)
        self.cv.bind("<ButtonPress-3>", lambda e: self.close())
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()
        self.win.grab_set()

    def _motion(self, ev):
        cv = self.cv
        cv.delete("loupe")
        x, y = ev.x, ev.y
        w, h = self.shot.size
        if not (0 <= x < w and 0 <= y < h):
            return
        n = self.LOUPE_SRC
        half = n // 2
        crop = self.shot.crop((x - half, y - half, x - half + n, y - half + n))
        size = n * self.LOUPE_PX
        big = crop.resize((size, size), self._Image.NEAREST)
        self._loupe = self._ImageTk.PhotoImage(big)
        lx = x + 24 if x + 24 + size < w else x - 24 - size
        ly = y + 24 if y + 24 + size + 22 < h else y - 24 - size - 22
        cv.create_rectangle(lx - 2, ly - 2, lx + size + 2, ly + size + 24,
                            fill="#202020", outline="#ffffff", tags="loupe")
        cv.create_image(lx, ly, anchor="nw", image=self._loupe, tags="loupe")
        c0 = lx + half * self.LOUPE_PX
        r0 = ly + half * self.LOUPE_PX
        cv.create_rectangle(c0, r0, c0 + self.LOUPE_PX, r0 + self.LOUPE_PX,
                            outline="#000000", width=3, tags="loupe")
        cv.create_rectangle(c0, r0, c0 + self.LOUPE_PX, r0 + self.LOUPE_PX,
                            outline="#ffffff", width=1, tags="loupe")
        rgb = self.px[x, y]
        cv.create_text(lx + 4, ly + size + 11, anchor="w", fill="#ffffff",
                       font=("Consolas", 10),
                       text="%s  %d,%d,%d" % ((hex_of(rgb),) + tuple(rgb)), tags="loupe")

    def _pick(self, ev):
        w, h = self.shot.size
        if 0 <= ev.x < w and 0 <= ev.y < h:
            rgb = tuple(self.px[ev.x, ev.y])
            self.close()
            self.cb(rgb)
        else:
            self.close()

    def close(self):
        if self.win is not None:
            try:
                self.win.grab_release()
            except self.app.tk.TclError:
                pass
            self.win.destroy()
            self.win = None


# ============================================================ colour picker
_PICKER_CACHE = {}


def _full_box_image():
    """Hue (x) x lightness (y, 100 top -> 0 bottom) at full saturation."""
    if "box" not in _PICKER_CACHE:
        from PIL import Image
        W, H = 360, 200
        im = Image.new("RGB", (W, H))
        px = im.load()
        for x in range(W):
            for y in range(H):
                px[x, y] = rgb_round(hsl_to_rgb(x * 360.0 / W, 100.0,
                                                100.0 - y * 100.0 / (H - 1)))
        grey = Image.new("RGB", (W, H))
        gp = grey.load()
        for y in range(H):
            v = int(round(255 * (1.0 - y / (H - 1.0))))
            for x in range(W):
                gp[x, y] = (v, v, v)
        _PICKER_CACHE["box"] = im
        _PICKER_CACHE["grey"] = grey
    return _PICKER_CACHE["box"], _PICKER_CACHE["grey"]


def _ring_image():
    """Hue ring (RGBA) at base size; hue runs clockwise from red at 3 o'clock."""
    if "ring" not in _PICKER_CACHE:
        from PIL import Image
        S = 320
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        px = im.load()
        c = (S - 1) / 2.0
        ro, ri = S / 2.0 - 1, S / 2.0 * 0.80
        for y in range(S):
            for x in range(S):
                dx, dy = x - c, y - c
                r = math.hypot(dx, dy)
                if ri - 1 <= r <= ro + 1:
                    a = 255
                    if r > ro:
                        a = int(255 * max(0.0, 1.0 - (r - ro)))
                    elif r < ri:
                        a = int(255 * max(0.0, 1.0 - (ri - r)))
                    h = math.degrees(math.atan2(dy, dx)) % 360.0
                    px[x, y] = rgb_round(hsl_to_rgb(h, 100.0, 50.0)) + (a,)
        _PICKER_CACHE["ring"] = im
    return _PICKER_CACHE["ring"]


def _tri_vertices(cx, cy, r):
    """tip (pure hue, right), black (top-left), white (bottom-left)."""
    return ((cx + r, cy),
            (cx + r * math.cos(math.radians(240)), cy + r * math.sin(math.radians(240))),
            (cx + r * math.cos(math.radians(120)), cy + r * math.sin(math.radians(120))))


def _bary(p, a, b, c):
    """Barycentric weights of p in triangle abc."""
    (x, y), (x1, y1), (x2, y2), (x3, y3) = p, a, b, c
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    w1 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / det
    w2 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / det
    return w1, w2, 1.0 - w1 - w2


def _tri_masks():
    """Tip weight, white weight and inside mask for the triangle at base size."""
    if "tri" not in _PICKER_CACHE:
        from PIL import Image
        S = 256
        c = (S - 1) / 2.0
        A, B, C = _tri_vertices(c, c, S / 2.0 - 1)
        tip = Image.new("L", (S, S))
        wht = Image.new("L", (S, S))
        msk = Image.new("L", (S, S))
        tp, wp, mp = tip.load(), wht.load(), msk.load()
        for y in range(S):
            for x in range(S):
                wt, wk, ww = _bary((x, y), A, B, C)
                inside = min(wt, wk, ww) >= -0.004
                wt, ww = max(wt, 0.0), max(ww, 0.0)
                tp[x, y] = int(round(min(wt, 1.0) * 255))
                wp[x, y] = int(round(min(ww, 1.0) * 255))
                mp[x, y] = 255 if inside else 0
        _PICKER_CACHE["tri"] = (tip, wht, msk)
    return _PICKER_CACHE["tri"]


PICKER_MODES = ["RGB Sliders", "HSL Sliders", "HSL Colour Wheel"]


class ColourPicker:
    """Non-modal picker. One colour (kept as HSL floats + RGB floats), shown
    by three interchangeable modes. Hue / saturation survive greys."""
    FINE = 0.25

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        s = app.s
        self.win = tk.Toplevel(app.root)
        self.win.title("Colour picker")
        self.win.minsize(560, 380)
        try:
            self.win.geometry(s.get("picker_geometry") or "760x470")
        except tk.TclError:
            pass
        self.pin_var = tk.BooleanVar(value=bool(s.get("picker_pin", True)))
        self._apply_pin()
        self.mode_var = tk.StringVar(value=s.get("picker_mode", PICKER_MODES[0]))
        if self.mode_var.get() not in PICKER_MODES:
            self.mode_var.set(PICKER_MODES[0])
        self.h, self.s, self.l = 0.0, 0.0, 50.0
        self.rgbf = (127.5, 127.5, 127.5)
        self.old = (128, 128, 128)
        self.target = None             # callable(rgb, hsl) or None
        self.target_label = ""
        self._drag = None
        self.active = None             # control taking arrow keys
        self._lock = False
        self._imgs = {}
        self._dropper = None
        ui = getattr(app, "ui", 1.0)
        self.ui = ui

        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        self.left = ttk.Frame(self.win, padding=8)
        self.left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(self.win, padding=(0, 8, 8, 8))
        right.grid(row=0, column=1, sticky="ns")

        top = ttk.Frame(right)
        top.pack(fill="x")
        cb = ttk.Combobox(top, textvariable=self.mode_var, values=PICKER_MODES,
                          state="readonly", width=18)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._build_mode())
        self.sw = tk.Canvas(top, width=int(76 * ui), height=int(30 * ui),
                            highlightthickness=1, highlightbackground="#888")
        self.sw.pack(side="left", padx=(8, 0))
        self.sw.bind("<Button-1>", self._on_swatch)
        self.target_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.target_var, foreground="#666").pack(anchor="w",
                                                                               pady=(4, 0))

        ff = ttk.Frame(right)
        ff.pack(fill="x", pady=(8, 0))
        self.fvars = {}
        self.fwidgets = {}
        for row, (k, hi) in enumerate((("R", 255), ("G", 255), ("B", 255))):
            self._field(ff, k, hi, row, 0)
        for row, (k, hi) in enumerate((("H", 360), ("S", 100), ("L", 100))):
            self._field(ff, k, hi, row, 2)
        hf = ttk.Frame(right)
        hf.pack(fill="x", pady=(10, 0))
        self.hvars = {}
        for row, k in enumerate(("R#", "G#", "B#")):
            ttk.Label(hf, text=k).grid(row=row, column=0, sticky="e", pady=1)
            v = tk.StringVar()
            e = ttk.Entry(hf, textvariable=v, width=5)
            e.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)
            e.bind("<Return>", lambda ev, kk=k: self._on_hexpart(kk))
            e.bind("<FocusOut>", lambda ev, kk=k: self._on_hexpart(kk))
            self.hvars[k] = v
        ttk.Label(hf, text="#").grid(row=3, column=0, sticky="e", pady=(4, 1))
        self.hex_var = tk.StringVar()
        self.hex_entry = ttk.Entry(hf, textvariable=self.hex_var, width=12)
        self.hex_entry.grid(row=3, column=1, columnspan=2, sticky="w", padx=(4, 0),
                            pady=(4, 1))
        self.hex_entry.bind("<Return>", lambda e: self._on_hex())
        self.hex_entry.bind("<FocusOut>", lambda e: self._on_hex(quiet=True))
        self.hex_entry.bind("<<Paste>>", lambda e: self.win.after(1, self._on_hex))
        self.hex_var.trace_add("write", lambda *a: self._on_hex(live=True))

        ef = ttk.Frame(right)
        ef.pack(fill="x", pady=(10, 0))
        ttk.Button(ef, text="Eyedropper", command=self.eyedropper).pack(side="left")
        self.last_cv = tk.Canvas(ef, width=int(22 * ui), height=int(22 * ui),
                                 highlightthickness=1, highlightbackground="#888")
        self.last_cv.pack(side="left", padx=(6, 0))
        self.last_cv.bind("<Button-1>", lambda e: self._use_last())
        self._last_pick = None
        ttk.Label(right, text="Recent").pack(anchor="w", pady=(10, 0))
        self.recent_cv = tk.Canvas(right, height=int(40 * ui), width=int(200 * ui),
                                   highlightthickness=0)
        self.recent_cv.pack(fill="x")
        self.recent_cv.bind("<Button-1>", self._on_recent)
        bf = ttk.Frame(right)
        bf.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Checkbutton(bf, text="On top", variable=self.pin_var,
                        command=self._apply_pin).pack(side="left")
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")

        get = self.rgb

        def put(rgb):
            self.set_rgb(rgb)
            self._commit()
        for w in list(self.fwidgets.values()) + [self.hex_entry]:
            app.register_colour_widget(w, get, put)
        for w in hf.winfo_children():
            if w.winfo_class() == "TEntry":
                app.register_colour_widget(w, get, put)
        self.sw.bind("<Button-3>", lambda e: app.colour_menu(e, get, put))

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        for k in ("Left", "Right", "Up", "Down"):
            self.win.bind("<%s>" % k, lambda e, kk=k: self._on_arrow(e, kk, 1))
            self.win.bind("<Shift-%s>" % k, lambda e, kk=k: self._on_arrow(e, kk, 10))
        self._build_mode()
        self._draw_recent()

    # ---------------------------------------------------------- setup helpers
    def _apply_pin(self):
        try:
            self.win.attributes("-topmost", bool(self.pin_var.get()))
        except self.app.tk.TclError:
            pass

    def _field(self, parent, k, hi, row, col):
        from tkinter import ttk
        ttk.Label(parent, text=k + ":").grid(row=row, column=col, sticky="e", pady=1,
                                             padx=(8 if col else 0, 0))
        v = self.app.tk.StringVar()
        sp = ttk.Spinbox(parent, textvariable=v, from_=0, to=hi, increment=1, width=5,
                         command=lambda kk=k: self._on_field(kk))
        sp.grid(row=row, column=col + 1, sticky="w", padx=(4, 0), pady=1)
        v.trace_add("write", lambda *a, kk=k: self._on_field(kk))
        sp.bind("<Return>", lambda e: self.refresh())
        sp.bind("<FocusOut>", lambda e: (self.refresh(), self._commit()))
        sp.bind("<MouseWheel>", lambda e, kk=k: self._wheel_field(kk, e))
        sp.bind("<Shift-MouseWheel>", lambda e, kk=k: self._wheel_field(kk, e, 10))
        self.fvars[k] = v
        self.fwidgets[k] = sp

    def _build_mode(self):
        from tkinter import ttk

        for ch in self.left.winfo_children():
            ch.destroy()
        self.sliders = {}
        self.box = None
        self.wheel = None
        mode = self.mode_var.get()
        L = self.left
        L.columnconfigure(1, weight=1)
        if mode == "HSL Colour Wheel":
            L.rowconfigure(0, weight=1)
            for r in range(1, 4):
                L.rowconfigure(r, weight=0)
            self.wheel = self.app.tk.Canvas(L, highlightthickness=0, cursor="crosshair")
            self.wheel.grid(row=0, column=0, columnspan=3, sticky="nsew")
            self._bind_drag(self.wheel, "wheel")
            self.wheel.bind("<Configure>", lambda e: self._draw_wheel(full=True))
        else:
            keys = "RGB" if mode == "RGB Sliders" else "HSL"
            for r, k in enumerate(keys):
                L.rowconfigure(r, weight=0)
                ttk.Label(L, text=k + ":").grid(row=r, column=0, sticky="w")
                c = self.app.tk.Canvas(L, height=int(26 * self.ui), highlightthickness=0,
                                       cursor="hand2")
                c.grid(row=r, column=1, sticky="ew", padx=(6, 0), pady=3)
                c.bind("<Configure>", lambda e, kk=k: self._draw_slider(kk))
                self._bind_drag(c, k)
                c.bind("<MouseWheel>", lambda e, kk=k: self._wheel_slider(kk, e, 1))
                c.bind("<Shift-MouseWheel>", lambda e, kk=k: self._wheel_slider(kk, e, 10))
                self.sliders[k] = c
            L.rowconfigure(3, weight=1)
            self.box = self.app.tk.Canvas(L, highlightthickness=1,
                                          highlightbackground="#555", cursor="crosshair")
            self.box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
            self.box.bind("<Configure>", lambda e: self._draw_box(full=True))
            self._bind_drag(self.box, "box")
        self.s_app_mode()
        self.refresh()

    def s_app_mode(self):
        self.app.s["picker_mode"] = self.mode_var.get()

    # ---------------------------------------------------------- state
    def rgb(self):
        return rgb_round(self.rgbf)

    def hsl(self):
        return [self.h, self.s, self.l]

    def _set_hsl(self, h, s, l, emit=True):
        self.h = h % 360.0
        self.s = min(max(s, 0.0), 100.0)
        self.l = min(max(l, 0.0), 100.0)
        self.rgbf = hsl_to_rgb(self.h, self.s, self.l)
        self.refresh()
        if emit:
            self._emit()

    def set_rgb(self, rgb, emit=True, keep_hue=False):
        """New colour from RGB. Hue (and saturation for black / white) are
        kept when the colour can't define them."""
        r, g, b = (float(v) for v in rgb)
        h, s, l = rgb_to_hsl(r, g, b)
        if max(r, g, b) - min(r, g, b) < 1e-9 or keep_hue:
            h = self.h
        if l <= 1e-9 or l >= 100.0 - 1e-9:
            s = self.s
        self.h, self.s, self.l = h, s, l
        self.rgbf = (r, g, b)
        self.refresh()
        if emit:
            self._emit()

    def set_target(self, cb, rgb, hsl=None, label=""):
        """Edit another colour (a ramp node etc.) - no change is sent."""
        self.target = cb
        self.target_label = label
        self.target_var.set(("Editing: " + label) if label else "No target - pick freely")
        rgb = tuple(rgb)
        self.old = rgb
        if hsl and rgb_round(hsl_to_rgb(*hsl)) == rgb:
            self.h, self.s, self.l = hsl[0] % 360.0, hsl[1], hsl[2]
            self.rgbf = hsl_to_rgb(*hsl)
        else:
            self.set_rgb(rgb, emit=False)
        self.refresh()

    def _emit(self):
        if self.target is not None:
            self.target(self.rgb(), self.hsl())

    def _commit(self):
        """End of a gesture: remember the colour in Recent."""
        self.app.add_recent(self.rgb())
        self._draw_recent()

    # ---------------------------------------------------------- drawing
    def refresh(self):
        self._lock = True
        try:
            r, g, b = self.rgb()
            vals = {"R": r, "G": g, "B": b, "H": int(round(self.h)) % 360,
                    "S": int(round(self.s)), "L": int(round(self.l))}
            for k, v in vals.items():
                w = self.fwidgets[k]
                if self.win.focus_get() is not w or not self._typed_ok(k):
                    self.fvars[k].set(str(v))
            for k, v in (("R#", r), ("G#", g), ("B#", b)):
                self.hvars[k].set("%02X" % v)
            if self.win.focus_get() is not self.hex_entry \
                    or parse_colour(self.hex_var.get()) != self.rgb():
                self.hex_var.set(hex_of(self.rgb())[1:])
        finally:
            self._lock = False
        sw = self.sw
        sw.delete("all")
        W, H = int(sw.cget("width")), int(sw.cget("height"))
        sw.create_rectangle(0, 0, W // 2, H, fill=hex_of(self.rgb()), outline="")
        sw.create_rectangle(W // 2, 0, W, H, fill=hex_of(self.old), outline="")
        for k in self.sliders:
            self._draw_slider(k)
        if self.box is not None:
            self._draw_box(full=self.mode_var.get() == "HSL Sliders")
        if self.wheel is not None:
            self._draw_wheel()

    def _typed_ok(self, k):
        try:
            return int(float(self.fvars[k].get())) == int(round(
                {"R": self.rgbf[0], "G": self.rgbf[1], "B": self.rgbf[2],
                 "H": self.h, "S": self.s, "L": self.l}[k]))
        except ValueError:
            return False

    def _track(self, k):
        """(function t -> rgb float, value 0..1) for slider k."""
        r, g, b = self.rgbf
        h, s, l = self.h, self.s, self.l
        if k == "R":
            return (lambda t: (t * 255, g, b)), r / 255.0
        if k == "G":
            return (lambda t: (r, t * 255, b)), g / 255.0
        if k == "B":
            return (lambda t: (r, g, t * 255)), b / 255.0
        if k == "H":
            return (lambda t: hsl_to_rgb(t * 360, 100, 50)), h / 360.0
        if k == "S":
            return (lambda t: hsl_to_rgb(h, t * 100, l)), s / 100.0
        return (lambda t: hsl_to_rgb(h, s, t * 100)), l / 100.0

    def _slider_geom(self, c):
        W, H = max(c.winfo_width(), 20), max(c.winfo_height(), 10)
        pad = H // 2
        return pad, W - pad, H

    def _draw_slider(self, k):
        from PIL import Image, ImageTk

        c = self.sliders.get(k)
        if c is None:
            return
        x0, x1, H = self._slider_geom(c)
        if x1 - x0 < 4:
            return
        f, v = self._track(k)
        strip = Image.new("RGB", (128, 1))
        strip.putdata([rgb_round(f(i / 127.0)) for i in range(128)])
        th = max(6, H // 3)
        img = strip.resize((int(x1 - x0), th), Image.BILINEAR)
        tki = ImageTk.PhotoImage(img)
        self._imgs["sl" + k] = tki
        c.delete("all")
        c.create_image(x0, (H - th) // 2, anchor="nw", image=tki)
        x = x0 + v * (x1 - x0)
        rad = H / 2.0 - 2
        c.create_oval(x - rad, H / 2 - rad, x + rad, H / 2 + rad, outline="#000000",
                      width=3)
        c.create_oval(x - rad, H / 2 - rad, x + rad, H / 2 + rad, outline="#ffffff",
                      width=2, fill=hex_of(self.rgb()))

    def _draw_box(self, full=False):
        from PIL import Image, ImageTk

        c = self.box
        W, H = c.winfo_width(), c.winfo_height()
        if W < 10 or H < 10:
            return
        hsl_mode = self.mode_var.get() == "HSL Sliders"
        key = ("box", W, H, round(self.s, 1) if hsl_mode else None)
        if full or self._imgs.get("boxkey") != key:
            fb, grey = _full_box_image()
            base = Image.blend(grey, fb, self.s / 100.0) if hsl_mode else fb
            self._imgs["box"] = ImageTk.PhotoImage(base.resize((W, H), Image.BILINEAR))
            self._imgs["boxkey"] = key
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._imgs["box"])
        x = self.h / 360.0 * (W - 1)
        y = (1.0 - self.l / 100.0) * (H - 1)
        self._crosshair(c, x, y)

    def _crosshair(self, c, x, y):
        g, n = 4, 10
        for col, w in (("#000000", 3), ("#ffffff", 1)):
            c.create_line(x - g - n, y, x - g, y, fill=col, width=w)
            c.create_line(x + g, y, x + g + n, y, fill=col, width=w)
            c.create_line(x, y - g - n, x, y - g, fill=col, width=w)
            c.create_line(x, y + g, x, y + g + n, fill=col, width=w)

    def _wheel_geom(self):
        c = self.wheel
        W, H = c.winfo_width(), c.winfo_height()
        S = max(min(W, H) - 8, 40)
        cx, cy = W / 2.0, H / 2.0
        ro = S / 2.0
        ri = ro * 0.80
        rt = ri * 0.96
        return cx, cy, ro, ri, rt, S

    def _draw_wheel(self, full=False):
        from PIL import Image, ImageChops, ImageTk

        c = self.wheel
        if c is None or c.winfo_width() < 50:
            return
        cx, cy, ro, ri, rt, S = self._wheel_geom()
        key = ("ring", S)
        if full or self._imgs.get("ringkey") != key:
            self._imgs["ring"] = ImageTk.PhotoImage(
                _ring_image().resize((int(S), int(S)), Image.BILINEAR))
            self._imgs["ringkey"] = key
        tkey = ("tri", int(2 * rt), round(self.h, 1))
        if full or self._imgs.get("trikey") != tkey:
            tip, wht, msk = _tri_masks()
            pr, pg, pb = hsl_to_rgb(self.h, 100, 50)
            bands = [ImageChops.add(tip.point(lambda v, p=p: v * p / 255.0), wht)
                     for p in (pr, pg, pb)]
            im = Image.merge("RGB", bands)
            im.putalpha(msk)
            sz = max(int(2 * rt), 8)
            self._imgs["tri"] = ImageTk.PhotoImage(im.resize((sz, sz), Image.BILINEAR))
            self._imgs["trikey"] = tkey
        c.delete("all")
        c.create_image(cx, cy, image=self._imgs["ring"])
        c.create_image(cx, cy, image=self._imgs["tri"])
        # ring marker
        a = math.radians(self.h)
        rm = (ro + ri) / 2.0
        mx, my = cx + rm * math.cos(a), cy + rm * math.sin(a)
        rr = (ro - ri) / 2.0 - 1
        c.create_oval(mx - rr, my - rr, mx + rr, my + rr, outline="#000000", width=3)
        c.create_oval(mx - rr, my - rr, mx + rr, my + rr, outline="#ffffff", width=2)
        # triangle marker
        px, py = self._tri_point()
        self._crosshair(c, px, py)
        c.create_text(8, c.winfo_height() - 8, anchor="sw", fill="#888",
                      font=("Consolas", 10),
                      text="H: %d\nS: %d\nL: %d" % (round(self.h) % 360, round(self.s),
                                                    round(self.l)))

    def _tri_weights(self):
        r, g, b = self.rgbf
        mx, mn = max(r, g, b), min(r, g, b)
        wc = (mx - mn) / 255.0
        ww = mn / 255.0
        return wc, ww, max(0.0, 1.0 - wc - ww)

    def _tri_point(self):
        cx, cy, ro, ri, rt, S = self._wheel_geom()
        A, B, C = _tri_vertices(cx, cy, rt)
        wc, ww, wk = self._tri_weights()
        return (wc * A[0] + wk * B[0] + ww * C[0], wc * A[1] + wk * B[1] + ww * C[1])

    # ---------------------------------------------------------- dragging
    def _bind_drag(self, c, ctl):
        c.bind("<ButtonPress-1>", lambda e: self._press(e, ctl))
        c.bind("<B1-Motion>", lambda e: self._motion(e, ctl))
        c.bind("<ButtonRelease-1>", lambda e: self._release(e, ctl))

    def _press(self, ev, ctl):
        self.win.focus_set()
        if ctl == "wheel":
            cx, cy, ro, ri, rt, S = self._wheel_geom()
            r = math.hypot(ev.x - cx, ev.y - cy)
            ctl = "ring" if r >= ri - 2 else "tri"
        self.active = ctl
        self._drag = {"ctl": ctl, "vx": float(ev.x), "vy": float(ev.y),
                      "lx": ev.x, "ly": ev.y, "ax": float(ev.x), "ay": float(ev.y),
                      "axis": None}
        self._apply_point(ctl, ev.x, ev.y, ev.widget)

    def _motion(self, ev, ctl):
        d = self._drag
        if not d:
            return
        f = self.FINE if ev.state & 0x0001 else 1.0
        d["vx"] += (ev.x - d["lx"]) * f
        d["vy"] += (ev.y - d["ly"]) * f
        d["lx"], d["ly"] = ev.x, ev.y
        x, y = d["vx"], d["vy"]
        if ev.state & 0x0004:                      # Ctrl: lock to one axis
            if d["axis"] is None and abs(x - d["ax"]) + abs(y - d["ay"]) > 3:
                d["axis"] = "x" if abs(x - d["ax"]) >= abs(y - d["ay"]) else "y"
            if d["axis"] == "x":
                y = d["ay"]
            elif d["axis"] == "y":
                x = d["ax"]
        else:
            d["axis"] = None
            d["ax"], d["ay"] = x, y
        self._apply_point(d["ctl"], x, y, ev.widget)

    def _release(self, _ev, _ctl):
        if self._drag:
            self._drag = None
            self._commit()

    def _apply_point(self, ctl, x, y, widget):
        if ctl in ("R", "G", "B", "H", "S", "L"):
            x0, x1, _H = self._slider_geom(widget)
            t = min(max((x - x0) / max(x1 - x0, 1), 0.0), 1.0)
            self._set_channel(ctl, t)
        elif ctl == "box":
            W, H = widget.winfo_width(), widget.winfo_height()
            hh = min(max(x / max(W - 1, 1), 0.0), 1.0) * 360.0
            ll = (1.0 - min(max(y / max(H - 1, 1), 0.0), 1.0)) * 100.0
            if hh >= 360.0:
                hh = 359.999
            if self.mode_var.get() == "RGB Sliders":
                self._set_hsl(hh, 100.0, ll)
            else:
                self._set_hsl(hh, self.s, ll)
        elif ctl == "ring":
            cx, cy, ro, ri, rt, S = self._wheel_geom()
            hh = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
            wc, ww, wk = self._tri_weights()
            pr = hsl_to_rgb(hh, 100, 50)
            self.h = hh
            self.set_rgb(tuple(wc * p + ww * 255.0 for p in pr), keep_hue=True)
        elif ctl == "tri":
            cx, cy, ro, ri, rt, S = self._wheel_geom()
            A, B, C = _tri_vertices(cx, cy, rt)
            wc, wk, ww = _bary((x, y), A, B, C)
            wc, wk, ww = max(wc, 0.0), max(wk, 0.0), max(ww, 0.0)
            tot = wc + wk + ww or 1.0
            wc, ww = wc / tot, ww / tot
            pr = hsl_to_rgb(self.h, 100, 50)
            self.set_rgb(tuple(min(255.0, wc * p + ww * 255.0) for p in pr), keep_hue=True)

    def _set_channel(self, k, t):
        if k in "RGB":
            v = list(self.rgbf)
            v["RGB".index(k)] = t * 255.0
            self.set_rgb(v)
        elif k == "H":
            self._set_hsl(min(t, 0.99999) * 360.0, self.s, self.l)
        elif k == "S":
            self._set_hsl(self.h, t * 100.0, self.l)
        else:
            self._set_hsl(self.h, self.s, t * 100.0)

    def _channel_value(self, k):
        return {"R": self.rgbf[0], "G": self.rgbf[1], "B": self.rgbf[2],
                "H": self.h, "S": self.s, "L": self.l}[k]

    def _step_channel(self, k, n):
        hi = {"R": 255.0, "G": 255.0, "B": 255.0, "H": 360.0, "S": 100.0, "L": 100.0}[k]
        v = round(self._channel_value(k)) + n
        if k == "H":
            v %= 360
        v = min(max(v, 0.0), hi)
        self._set_channel(k, v / hi if k != "H" else (v % 360) / 360.0)

    def _wheel_slider(self, k, ev, n):
        self.active = k
        self._step_channel(k, n if ev.delta > 0 else -n)
        self._commit()
        return "break"

    def _on_arrow(self, ev, key, n):
        cls = ev.widget.winfo_class() if hasattr(ev.widget, "winfo_class") else ""
        if cls in ("TEntry", "Entry", "TSpinbox", "Spinbox", "TCombobox"):
            return
        ctl = self.active
        if ctl is None:
            return
        sign = 1 if key in ("Right", "Up") else -1
        if ctl in ("R", "G", "B", "H", "S", "L"):
            self._step_channel(ctl, sign * n)
        elif ctl in ("box", "tri"):
            if key in ("Left", "Right"):
                if ctl == "box":
                    self._step_channel("H", sign * n)
                else:
                    self._step_channel("S", sign * n)
            else:
                self._step_channel("L", sign * n)
        elif ctl == "ring":
            self._step_channel("H", sign * n)
        self._commit()
        return "break"

    # ---------------------------------------------------------- fields
    def _on_field(self, k):
        if self._lock:
            return
        try:
            v = float(self.fvars[k].get())
        except ValueError:
            return
        hi = {"R": 255, "G": 255, "B": 255, "H": 360, "S": 100, "L": 100}[k]
        if not 0 <= v <= hi or abs(v - round(self._channel_value(k))) < 1e-9:
            return
        if k == "H":
            self._set_hsl(v % 360.0, self.s, self.l)
        else:
            self._set_channel(k, v / hi)

    def _wheel_field(self, k, ev, n=1):
        self._step_channel(k, n if ev.delta > 0 else -n)
        self._commit()
        return "break"

    def _on_hexpart(self, k):
        try:
            v = int(self.hvars[k].get().strip().lstrip("#"), 16)
        except ValueError:
            self.refresh()
            return
        if 0 <= v <= 255:
            rgb = list(self.rgb())
            rgb[("R#", "G#", "B#").index(k)] = v
            self.set_rgb(rgb)
            self._commit()
        else:
            self.refresh()

    def _on_hex(self, live=False, quiet=False):
        if self._lock:
            return
        txt = self.hex_var.get().strip()
        if live and not (len(txt.lstrip("#")) == 6 or "," in txt):
            return                                 # wait for a full value
        c = parse_colour(txt)
        if c is None:
            if not live and not quiet:
                self.refresh()
            return
        if c != self.rgb():
            self.set_rgb(c)
        if not live:
            self._commit()

    # ---------------------------------------------------------- swatches
    def _on_swatch(self, ev):
        W = int(self.sw.cget("width"))
        if ev.x >= W // 2:                         # old half: revert
            self.set_rgb(self.old)
            self._commit()

    def _draw_recent(self):
        c = self.recent_cv
        c.delete("all")
        sz = int(18 * self.ui)
        for k, hx in enumerate(self.app.s.get("recent_colours", [])[:16]):
            x = (k % 8) * (sz + 3)
            y = (k // 8) * (sz + 3)
            c.create_rectangle(x, y, x + sz, y + sz, fill=hx, outline="#777")

    def _on_recent(self, ev):
        sz = int(18 * self.ui) + 3
        k = (ev.y // sz) * 8 + ev.x // sz
        rec = self.app.s.get("recent_colours", [])
        if ev.x // sz < 8 and 0 <= k < len(rec):
            c = parse_colour(rec[k])
            if c:
                self.set_rgb(c)

    def eyedropper(self):
        self._dropper = EyeDropper(self.app, self._picked)

    def _picked(self, rgb):
        self._last_pick = rgb
        self.last_cv.configure(background=hex_of(rgb))
        self.set_rgb(rgb)
        self._commit()

    def _use_last(self):
        if self._last_pick:
            self.set_rgb(self._last_pick)
            self._commit()

    def close(self):
        try:
            self.app.s["picker_geometry"] = self.win.geometry()
        except self.app.tk.TclError:
            pass
        self.app.s["picker_pin"] = bool(self.pin_var.get())
        self.app.s["picker_mode"] = self.mode_var.get()
        self.app.picker = None
        self.win.destroy()


# ============================================================ ramp tool
class RampTool:
    """Gradient editor: nodes on a bar, blend space + easing. Fills the
    selected palette cells (blank or filled) in index order."""

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        s = app.s
        ui = getattr(app, "ui", 1.0)
        self.ui = ui
        try:
            self.st = clean_ramp_state(s.get("ramp") or {})
        except ValueError:
            self.st = default_ramp_state()
        self.active = self.st["nodes"][0]
        self._drag = None
        self._img = None
        self._strip_cells = []
        self._after = None

        self.win = tk.Toplevel(app.root)
        self.win.title("Ramp tool")
        self.win.transient(app.root)
        self.win.minsize(560, 420)
        try:
            self.win.geometry(s.get("ramp_geometry") or "680x500")
        except tk.TclError:
            pass
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(4, weight=1)

        self.bar = tk.Canvas(self.win, height=int(70 * ui), highlightthickness=0,
                             bg="#2a2a2a", cursor="hand2")
        self.bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        self.bar.bind("<Configure>", lambda e: self.draw_bar())
        self.bar.bind("<ButtonPress-1>", self._bar_press)
        self.bar.bind("<B1-Motion>", self._bar_motion)
        self.bar.bind("<ButtonRelease-1>", self._bar_release)
        self.bar.bind("<Double-Button-1>", self._bar_double)
        self.bar.bind("<ButtonPress-3>", self._bar_right)

        nf = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        nf.grid(row=1, column=0, sticky="ew")
        self.node_var = tk.StringVar()
        ttk.Label(nf, textvariable=self.node_var, width=12).pack(side="left")
        self.node_sw = tk.Canvas(nf, width=int(44 * ui), height=int(22 * ui),
                                 highlightthickness=1, highlightbackground="#888",
                                 cursor="hand2")
        self.node_sw.pack(side="left")
        self.node_sw.bind("<Button-1>", lambda e: self.open_picker())
        ttk.Label(nf, text="#").pack(side="left", padx=(8, 0))
        self.hex_var = tk.StringVar()
        he = ttk.Entry(nf, textvariable=self.hex_var, width=9)
        he.pack(side="left")
        he.bind("<Return>", lambda e: self._on_hex())
        he.bind("<FocusOut>", lambda e: self._on_hex())
        ttk.Label(nf, text="Pos %").pack(side="left", padx=(8, 0))
        self.pos_var = tk.StringVar()
        self.pos_sp = ttk.Spinbox(nf, textvariable=self.pos_var, from_=0, to=100,
                                  increment=1, width=6, command=self._on_pos)
        self.pos_sp.pack(side="left", padx=(4, 0))
        self.pos_sp.bind("<Return>", lambda e: self._on_pos())
        self.pos_sp.bind("<FocusOut>", lambda e: self._on_pos())
        ttk.Button(nf, text="Picker...", command=self.open_picker).pack(side="left",
                                                                        padx=(8, 0))
        self.del_btn = ttk.Button(nf, text="Delete node", command=self.delete_active)
        self.del_btn.pack(side="left", padx=(6, 0))

        of = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        of.grid(row=2, column=0, sticky="ew")
        self.space_var = tk.StringVar(value=self.st["space"])
        self.ease_var = tk.StringVar(value=self.st["ease"])
        self.str_var = tk.StringVar(value=fmt_tol(self.st["strength"]))
        self.scope_var = tk.StringVar(value=self.st["ease_scope"])
        ttk.Label(of, text="Blend").pack(side="left")
        w = ttk.Combobox(of, textvariable=self.space_var, values=RAMP_SPACES,
                         state="readonly", width=16)
        w.pack(side="left", padx=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_opts())
        ttk.Label(of, text="Ease").pack(side="left", padx=(10, 0))
        w = ttk.Combobox(of, textvariable=self.ease_var, values=RAMP_EASES,
                         state="readonly", width=11)
        w.pack(side="left", padx=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_opts())
        ttk.Label(of, text="Strength").pack(side="left", padx=(10, 0))
        self.str_sp = ttk.Spinbox(of, textvariable=self.str_var, from_=1, to=6,
                                  increment=0.25, width=5, command=self._on_opts)
        self.str_sp.pack(side="left", padx=(4, 0))
        self.str_sp.bind("<Return>", lambda e: self._on_opts())
        self.str_sp.bind("<FocusOut>", lambda e: self._on_opts())
        of2 = ttk.Frame(self.win, padding=(8, 4, 8, 0))
        of2.grid(row=3, column=0, sticky="ew")
        ttk.Label(of2, text="Ease applies to:").pack(side="left")
        self.scope_rbs = []
        for v in RAMP_EASE_SCOPES:
            rb = ttk.Radiobutton(of2, text=v, value=v, variable=self.scope_var,
                                 command=self._on_opts)
            rb.pack(side="left", padx=(6, 0))
            self.scope_rbs.append(rb)
        ttk.Button(of2, text="Reverse", command=self.reverse).pack(side="right")
        ttk.Button(of2, text="Use selection ends",
                   command=self.use_selection_ends).pack(side="right", padx=(0, 6))

        sf = ttk.LabelFrame(self.win, text="Steps (one per selected cell, index order)",
                            padding=6)
        sf.grid(row=4, column=0, sticky="nsew", padx=8, pady=(8, 0))
        sf.columnconfigure(0, weight=1)
        sf.rowconfigure(0, weight=1)
        self.strip = tk.Canvas(sf, height=int(60 * ui), highlightthickness=0, bg="#2a2a2a")
        self.strip.grid(row=0, column=0, sticky="nsew")
        self.strip.bind("<Configure>", lambda e: self.draw_strip())
        self.strip.bind("<Motion>", self._strip_hover)
        self.strip.bind("<Leave>", lambda e: self.info_var.set(""))
        self.info_var = tk.StringVar()
        ttk.Label(sf, textvariable=self.info_var, font=("Consolas", 9)).grid(
            row=1, column=0, sticky="w", pady=(4, 0))

        ff = ttk.Frame(self.win, padding=(8, 8, 8, 0))
        ff.grid(row=5, column=0, sticky="ew")
        ttk.Button(ff, text="Load ramp...", command=self.load_ramp).pack(side="left")
        ttk.Button(ff, text="Save ramp...", command=self.save_ramp).pack(side="left",
                                                                         padx=(6, 0))
        ttk.Button(ff, text="Scratch palette...",
                   command=app.open_scratch).pack(side="right")
        bf = ttk.Frame(self.win, padding=8)
        bf.grid(row=6, column=0, sticky="ew")
        self.prev_btn = tk.Button(bf, text="Preview: OFF", width=12, relief="raised",
                                  command=self.toggle_preview)
        self._btn_bg = self.prev_btn.cget("background")
        self.prev_btn.pack(side="left")
        ttk.Button(bf, text="Apply", command=self.apply).pack(side="left", padx=(6, 0))
        self.cancel_btn = ttk.Button(bf, text="Cancel", command=self.cancel)
        self.cancel_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")

        def get():
            return tuple(self.active["rgb"])

        def put(rgb):
            self.set_node_colour(self.active, rgb)
            p = app.picker
            if p is not None and getattr(p, "owner", None) is self:
                self._target_picker(p)
        app.register_colour_widget(he, get, put)
        app.register_colour_widget(self.pos_sp, get, put)
        self.node_sw.bind("<Button-3>", lambda e: app.colour_menu(e, get, put))

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Delete>", self._on_del_key)
        self.win.bind("<Escape>", lambda e: self.cancel() if app._ramp_backup else None)

        app._ramp_align_saved = app.align_var.get()
        app.align_var.set(False)
        app.align_chk.state(["disabled"])
        self.update_buttons()
        self.changed(store=False)
        app.recompute()

    # ---------------------------------------------------------- helpers
    def nodes(self):
        return self.st["nodes"]

    def idx(self, node):
        for k, n in enumerate(self.nodes()):
            if n is node:
                return k
        return 0

    def _bar_geom(self):
        W = max(self.bar.winfo_width(), 40)
        H = max(self.bar.winfo_height(), 40)
        m = int(12 * self.ui)
        return m, W - m, 4, H - int(24 * self.ui), H

    def _x(self, t):
        x0, x1, _y0, _y1, _H = self._bar_geom()
        return x0 + t * (x1 - x0)

    def _t(self, x):
        x0, x1, _y0, _y1, _H = self._bar_geom()
        return min(max((x - x0) / max(x1 - x0, 1), 0.0), 1.0)

    # node positions live in eased space when easing applies to the whole
    # ramp; the bar shows them where their colour actually appears
    def _whole(self):
        return self.st["ease_scope"] == "Whole ramp" and self.st["ease"] != "Linear"

    def _to_pos(self, t):
        return _ease(t, self.st["ease"], self.st["strength"]) if self._whole() else t

    def _to_bar(self, pos):
        if not self._whole():
            return pos
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2.0
            if _ease(mid, self.st["ease"], self.st["strength"]) < pos:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    def targets(self):
        a = self.app
        if a._ramp_backup is not None:
            return list(a._ramp_targets)
        return sorted(a.selection)

    def colours(self, n=None):
        return ramp_colours(self.st, len(self.targets()) if n is None else n)

    # ---------------------------------------------------------- drawing
    def draw_bar(self):
        from PIL import Image, ImageTk

        c = self.bar
        x0, x1, y0, y1, H = self._bar_geom()
        c.delete("all")
        w = int(x1 - x0)
        if w < 4:
            return
        strip = Image.new("RGB", (200, 1))
        strip.putdata([rgb_round(ramp_colour_at(self.st, i / 199.0)) for i in range(200)])
        self._img = ImageTk.PhotoImage(strip.resize((w, int(y1 - y0)), Image.BILINEAR))
        c.create_image(x0, y0, anchor="nw", image=self._img)
        c.create_rectangle(x0 - 1, y0 - 1, x1, y1, outline="#000000")
        sz = 9 * self.ui
        for n in self.nodes():
            x = self._x(self._to_bar(n["pos"]))
            act = n is self.active
            c.create_line(x, y0, x, y1, fill="#000000" if act else "", width=1)
            pts = (x, y1 + 2, x - sz, y1 + 2 + sz * 1.6, x + sz, y1 + 2 + sz * 1.6)
            c.create_polygon(*pts, fill=hex_of(n["rgb"]), outline="#000000",
                             width=3 if act else 1)
            if act:
                c.create_polygon(*pts, fill="", outline="#ffffff", width=1)

    def draw_strip(self):
        c = self.strip
        c.delete("all")
        tg = self.targets()
        n = len(tg)
        self._strip_cells = []
        W = max(c.winfo_width(), 40)
        if n == 0:
            c.create_text(10, 20, anchor="w", fill="#bbbbbb",
                          text="Select cells in the main grid (blank or filled) - "
                               "one ramp step per cell.")
            return
        cols = min(n, 32)
        cell = min(40 * self.ui, (W - 8) / cols)
        rows = (n + cols - 1) // cols
        need = int(rows * cell + 8)
        if int(c.cget("height")) < need:
            c.configure(height=need)
        cs = self.colours()
        base = self.app._ramp_backup[0] if self.app._ramp_backup else self.app.rgbs
        deleted = self.app._ramp_backup[3] if self.app._ramp_backup else self.app.deleted
        tset = set(tg)
        where = {}
        if base is not None:
            for i, col in enumerate(base):
                if col is not None and i not in tset and i not in deleted:
                    where.setdefault(tuple(col), i)
        seen = {}
        for k, col in enumerate(cs):
            x = 4 + (k % cols) * cell
            y = 4 + (k // cols) * cell
            c.create_rectangle(x, y, x + cell - 2, y + cell - 2, fill=hex_of(col),
                               outline="")
            fg = "#000000" if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] > 140 \
                else "#ffffff"
            dup = seen.get(col)
            ex = where.get(col)
            if dup is not None:
                r = max(2, cell / 9)
                c.create_oval(x + 3, y + 3, x + 3 + 2 * r, y + 3 + 2 * r, fill=fg,
                              outline="")
            if ex is not None:
                q = cell / 4
                c.create_polygon(x + cell - 2, y + cell - 2, x + cell - 2 - q, y + cell - 2,
                                 x + cell - 2, y + cell - 2 - q, fill=fg, outline="")
            seen.setdefault(col, k)
            self._strip_cells.append((x, y, cell, k, col, dup, ex, tg[k]))

    def _strip_hover(self, ev):
        for x, y, cell, k, col, dup, ex, slot in self._strip_cells:
            if x <= ev.x < x + cell and y <= ev.y < y + cell:
                t = "Step %d -> index %d   %s   %d,%d,%d" % ((k + 1, slot, hex_of(col))
                                                           + tuple(col))
                if dup is not None:
                    t += "   same as step %d" % (dup + 1)
                if ex is not None:
                    t += "   already in palette at %d" % ex
                self.info_var.set(t)
                return
        self.info_var.set("")

    def refresh_node_row(self):
        n = self.active
        k = self.idx(n)
        last = len(self.nodes()) - 1
        self.node_var.set("Node %d of %d" % (k + 1, last + 1) + (
            " (start)" if k == 0 else " (end)" if k == last else ""))
        self.node_sw.configure(background=hex_of(n["rgb"]))
        self.hex_var.set(hex_of(n["rgb"])[1:])
        self.pos_var.set(fmt_tol(round(self._to_bar(n["pos"]) * 100.0, 2)))
        end = k in (0, last)
        self.pos_sp.state(["disabled"] if end else ["!disabled"])
        self.del_btn.state(["disabled"] if end else ["!disabled"])

    def changed(self, store=True):
        self.draw_bar()
        self.refresh_node_row()
        self.draw_strip()
        if store:
            self.app.s["ramp"] = json.loads(json.dumps(self.st))
        if self.app._ramp_backup is not None:
            if self._after is not None:
                self.win.after_cancel(self._after)
            self._after = self.win.after(50, self._push_preview)

    def _push_preview(self):
        self._after = None
        if self.app._ramp_backup is not None:
            self.app.ramp_preview_set(self.colours())

    # ---------------------------------------------------------- nodes
    def set_active(self, node):
        self.active = node
        self.changed(store=False)
        p = self.app.picker
        if p is not None and getattr(p, "owner", None) is self:
            self._target_picker(p)

    def _target_picker(self, p):
        node = self.active
        k = self.idx(node)
        p.owner = self
        p.set_target(lambda rgb, hsl, nd=node: self.set_node_colour(nd, rgb, hsl),
                     tuple(node["rgb"]), node.get("hsl"),
                     "ramp node %d of %d" % (k + 1, len(self.nodes())))

    def open_picker(self):
        p = self.app.open_picker()
        self._target_picker(p)

    def set_node_colour(self, node, rgb, hsl=None):
        if not any(n is node for n in self.nodes()):
            return
        node["rgb"] = list(rgb)
        node["hsl"] = list(hsl) if hsl else None
        self.changed()

    def _hit(self, x, y):
        x0, x1, y0, y1, H = self._bar_geom()
        best, bd = None, 10 * self.ui
        for n in self.nodes():
            d = abs(self._x(self._to_bar(n["pos"])) - x)
            if d <= bd and (y >= y1 - 2 or d <= 4 * self.ui):
                best, bd = n, d
        return best

    def _bar_press(self, ev):
        n = self._hit(ev.x, ev.y)
        if n is None:
            t = self._t(ev.x)
            col = rgb_round(ramp_colour_at(self.st, t))   # the colour shown there
            n = {"pos": min(max(self._to_pos(t), 0.001), 0.999), "rgb": list(col),
                 "hsl": None}
            nodes = self.nodes()
            nodes.append(n)
            nodes.sort(key=lambda q: q["pos"])
            self.set_active(n)
            self.changed()
        else:
            self.set_active(n)
        k = self.idx(n)
        if 0 < k < len(self.nodes()) - 1:
            self._drag = n

    def _bar_motion(self, ev):
        n = self._drag
        if n is None:
            return
        n["pos"] = min(max(self._to_pos(self._t(ev.x)), 0.001), 0.999)
        self.nodes().sort(key=lambda q: q["pos"])
        self.changed(store=False)

    def _bar_release(self, _ev):
        if self._drag is not None:
            self._drag = None
            self.changed()

    def _bar_double(self, ev):
        n = self._hit(ev.x, ev.y)
        if n is not None:
            self.set_active(n)
            self.open_picker()

    def _bar_right(self, ev):
        n = self._hit(ev.x, ev.y)
        if n is not None:
            self.delete_node(n)

    def delete_node(self, n):
        nodes = self.nodes()
        k = self.idx(n)
        if k in (0, len(nodes) - 1):
            return
        del nodes[k]
        if self.active is n:
            self.set_active(nodes[min(k, len(nodes) - 1)])
        self.changed()

    def delete_active(self):
        self.delete_node(self.active)

    def _on_del_key(self, ev):
        if ev.widget.winfo_class() in ("TEntry", "Entry", "TSpinbox", "Spinbox"):
            return
        self.delete_active()

    def _on_hex(self):
        c = parse_colour(self.hex_var.get())
        if c is None:
            self.refresh_node_row()
            return
        if tuple(self.active["rgb"]) != c:
            self.set_node_colour(self.active, c)
            p = self.app.picker
            if p is not None and getattr(p, "owner", None) is self:
                self._target_picker(p)

    def _on_pos(self):
        k = self.idx(self.active)
        if k in (0, len(self.nodes()) - 1):
            return
        try:
            v = float(self.pos_var.get())
        except ValueError:
            self.refresh_node_row()
            return
        self.active["pos"] = min(max(self._to_pos(min(max(v / 100.0, 0.0), 1.0)),
                                     0.001), 0.999)
        self.nodes().sort(key=lambda q: q["pos"])
        self.changed()

    def _on_opts(self):
        self.st["space"] = self.space_var.get()
        self.st["ease"] = self.ease_var.get()
        self.st["ease_scope"] = self.scope_var.get()
        try:
            v = float(self.str_var.get())
            self.st["strength"] = min(max(v, 1.0), 6.0)
        except ValueError:
            pass
        self.str_var.set(fmt_tol(self.st["strength"]))
        self.changed()

    def reverse(self):
        nodes = self.nodes()
        for n in nodes:
            n["pos"] = 1.0 - n["pos"]
        nodes.reverse()
        nodes[0]["pos"], nodes[-1]["pos"] = 0.0, 1.0
        self.set_active(self.active)
        self.changed()

    def use_selection_ends(self):
        a = self.app
        base = a._ramp_backup[0] if a._ramp_backup else a.rgbs
        tg = self.targets()
        if base is None or len(tg) < 2:
            a.status_var.set("Select at least two cells first.")
            return
        first, last = base[tg[0]], base[tg[-1]]
        if first is None or last is None:
            a.status_var.set("The first and last selected cells must hold colours.")
            return
        nodes = self.nodes()
        nodes[0]["rgb"], nodes[0]["hsl"] = list(first), None
        nodes[-1]["rgb"], nodes[-1]["hsl"] = list(last), None
        self.set_active(nodes[0])
        self.changed()

    def drop_colour(self, x_root, rgb):
        """A swatch dropped on the bar: recolour the node there, or add one."""
        x = x_root - self.bar.winfo_rootx()
        n = self._hit(x, 10 ** 6)
        if n is None:
            t = min(max(self._to_pos(self._t(x)), 0.001), 0.999)
            n = {"pos": t, "rgb": list(rgb), "hsl": None}
            self.nodes().append(n)
            self.nodes().sort(key=lambda q: q["pos"])
        else:
            n["rgb"], n["hsl"] = list(rgb), None
        self.set_active(n)
        self.changed()

    # ---------------------------------------------------------- preview / apply
    def update_buttons(self):
        on = self.app._ramp_backup is not None
        self.prev_btn.configure(text="Preview: ON" if on else "Preview: OFF",
                                relief="sunken" if on else "raised",
                                background="#ffb36b" if on else self._btn_bg,
                                activebackground="#ffcb94" if on else self._btn_bg)
        self.cancel_btn.state(["!disabled"] if on else ["disabled"])

    def toggle_preview(self):
        if self.app._ramp_backup is not None:
            self.cancel()
        elif self.app.ramp_preview_start():
            self.app.ramp_preview_set(self.colours())
        self.update_buttons()
        self.draw_strip()

    def apply(self):
        a = self.app
        if a._ramp_backup is None:
            if not a.ramp_preview_start():
                self.update_buttons()
                return
        if self._after is not None:
            self.win.after_cancel(self._after)
            self._after = None
        cs = self.colours()
        a.ramp_preview_set(cs)
        a.ramp_apply(cs, [n["rgb"] for n in self.nodes()])
        self.update_buttons()
        self.draw_strip()

    def cancel(self):
        if self.app._ramp_backup is not None:
            self.app.ramp_cancel()
        self.update_buttons()
        self.draw_strip()

    def save_ramp(self):
        from tkinter import filedialog, messagebox

        initdir = self.app.s.get("ramp_dir") or PRESET_DIR
        try:
            os.makedirs(initdir, exist_ok=True)
        except OSError:
            initdir = None
        p = filedialog.asksaveasfilename(
            parent=self.win, title="Save ramp", initialdir=initdir,
            initialfile="ramp.json", defaultextension=".json",
            filetypes=[("cleanpal ramp", "*.json")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"cleanpal_ramp": 1, "version": VERSION, "ramp": self.st}, fh,
                          indent=2)
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not save ramp:\n%s" % e, parent=self.win)
            return
        self.app.s["ramp_dir"] = os.path.dirname(p)
        self.app.status_var.set("Saved ramp %s" % p)

    def load_ramp(self):
        from tkinter import filedialog, messagebox

        initdir = self.app.s.get("ramp_dir") or PRESET_DIR
        if not os.path.isdir(initdir):
            initdir = None
        p = filedialog.askopenfilename(
            parent=self.win, title="Load ramp", initialdir=initdir,
            filetypes=[("cleanpal ramp", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or data.get("cleanpal_ramp") != 1:
                raise ValueError("Not a cleanpal ramp file.")
            st = clean_ramp_state(data.get("ramp"))
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not load ramp:\n%s\n\n%s" % (p, e),
                                 parent=self.win)
            return
        self.app.s["ramp_dir"] = os.path.dirname(p)
        self.set_state(st)

    def set_state(self, st):
        self.st = st
        self.space_var.set(st["space"])
        self.ease_var.set(st["ease"])
        self.str_var.set(fmt_tol(st["strength"]))
        self.scope_var.set(st["ease_scope"])
        self.set_active(self.st["nodes"][0])
        self.changed()

    def close(self):
        a = self.app
        if a._ramp_backup is not None:
            a.ramp_cancel()
        if self._after is not None:
            self.win.after_cancel(self._after)
        try:
            a.s["ramp_geometry"] = self.win.geometry()
        except a.tk.TclError:
            pass
        a.s["ramp"] = json.loads(json.dumps(self.st))
        p = a.picker
        if p is not None and getattr(p, "owner", None) is self:
            p.owner = None
            p.set_target(None, p.rgb(), p.hsl(), "")
        a.ramp = None
        if not a.move_var.get():
            a.align_chk.state(["!disabled"])
            a.align_var.set(getattr(a, "_ramp_align_saved", False))
        self.win.destroy()
        a.recompute()


# ============================================================ scratch palette
class ScratchPalette:
    """Temporary swatches in named sets. Click = send to the picker; drag
    onto the grid / a ramp node / the picker; drag to reorder."""

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        s = app.s
        ui = getattr(app, "ui", 1.0)
        self.ui = ui
        sets = s.get("scratch_sets")
        if not isinstance(sets, dict) or not sets:
            sets = {"Scratch": []}
        s["scratch_sets"] = sets
        if s.get("scratch_current") not in sets:
            s["scratch_current"] = next(iter(sets))
        self.sel = set()
        self._anchor = None
        self._drag = None
        self._cells = []

        self.win = tk.Toplevel(app.root)
        self.win.title("Scratch palette")
        self.win.minsize(330, 240)
        try:
            self.win.geometry(s.get("scratch_geometry") or "420x320")
        except tk.TclError:
            pass
        self.pin_var = tk.BooleanVar(value=bool(s.get("scratch_pin", True)))
        self._apply_pin()
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(2, weight=1)

        tf = ttk.Frame(self.win, padding=(8, 8, 8, 0))
        tf.grid(row=0, column=0, sticky="ew")
        self.set_var = tk.StringVar(value=s["scratch_current"])
        self.set_cb = ttk.Combobox(tf, textvariable=self.set_var, state="readonly",
                                   width=18, values=list(sets))
        self.set_cb.pack(side="left")
        self.set_cb.bind("<<ComboboxSelected>>", lambda e: self._on_set())
        ttk.Button(tf, text="New", width=6, command=self.new_set).pack(side="left",
                                                                      padx=(6, 0))
        ttk.Button(tf, text="Rename", width=7, command=self.rename_set).pack(side="left",
                                                                            padx=(4, 0))
        ttk.Button(tf, text="Delete", width=7, command=self.delete_set).pack(side="left",
                                                                            padx=(4, 0))
        bf = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        bf.grid(row=1, column=0, sticky="ew")
        ttk.Button(bf, text="+ Picker", command=self.add_picker).pack(side="left")
        ttk.Button(bf, text="+ Selected", command=self.add_selected).pack(side="left",
                                                                         padx=(4, 0))
        ttk.Button(bf, text="Eyedropper", command=self.eyedropper).pack(side="left",
                                                                       padx=(4, 0))
        ttk.Button(bf, text="Fill selected", command=self.fill_selected).pack(
            side="left", padx=(4, 0))
        self.cv = tk.Canvas(self.win, highlightthickness=1, highlightbackground="#888",
                            bg="#2a2a2a")
        self.cv.grid(row=2, column=0, sticky="nsew", padx=8, pady=(6, 0))
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<ButtonPress-3>", self._right)
        self.cv.bind("<Motion>", self._hover)
        self.info_var = tk.StringVar(value="")
        ttk.Label(self.win, textvariable=self.info_var, font=("Consolas", 9)).grid(
            row=3, column=0, sticky="w", padx=8)
        ff = ttk.Frame(self.win, padding=8)
        ff.grid(row=4, column=0, sticky="ew")
        ttk.Button(ff, text="Import...", command=self.import_file).pack(side="left")
        ttk.Button(ff, text="Export...", command=self.export_file).pack(side="left",
                                                                       padx=(4, 0))
        ttk.Checkbutton(ff, text="On top", variable=self.pin_var,
                        command=self._apply_pin).pack(side="left", padx=(8, 0))
        ttk.Button(ff, text="Close", command=self.close).pack(side="right")

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Delete>", lambda e: self.delete_selected())
        self.win.bind("<BackSpace>", lambda e: self.delete_selected())
        self.win.bind("<Control-c>", lambda e: self.copy())
        self.win.bind("<Control-C>", lambda e: self.copy())
        self.win.bind("<Control-v>", lambda e: self.paste())
        self.win.bind("<Control-V>", lambda e: self.paste())
        self.win.bind("<Control-a>", lambda e: self._select_all())
        self.win.bind("<Escape>", lambda e: self.close())

    # ---------------------------------------------------------- data
    def _apply_pin(self):
        try:
            self.win.attributes("-topmost", bool(self.pin_var.get()))
        except self.app.tk.TclError:
            pass

    def swatches(self):
        return self.app.s["scratch_sets"][self.app.s["scratch_current"]]

    def colours(self):
        out = []
        for hx in self.swatches():
            c = parse_colour(hx)
            out.append(c if c else (0, 0, 0))
        return out

    def add_colours(self, cols):
        sw = self.swatches()
        for c in cols:
            sw.append(hex_of(c))
        self.sel = set(range(len(sw) - len(cols), len(sw)))
        self.draw()
        self.app.status_var.set("Scratch: added %d colour(s)." % len(cols))

    # ---------------------------------------------------------- sets
    def _sets(self):
        return self.app.s["scratch_sets"]

    def _refresh_sets(self):
        self.set_cb.configure(values=list(self._sets()))
        self.set_var.set(self.app.s["scratch_current"])
        self.sel = set()
        self.draw()

    def _on_set(self):
        self.app.s["scratch_current"] = self.set_var.get()
        self._refresh_sets()

    def _ask_name(self, title, initial=""):
        from tkinter import simpledialog
        name = simpledialog.askstring("cleanpal", title, initialvalue=initial,
                                      parent=self.win)
        if name is None:
            return None
        name = name.strip()
        return name or None

    def _unique(self, name):
        base, k = name, 2
        while name in self._sets():
            name = "%s %d" % (base, k)
            k += 1
        return name

    def new_set(self):
        name = self._ask_name("Name for the new set:")
        if not name:
            return
        name = self._unique(name)
        self._sets()[name] = []
        self.app.s["scratch_current"] = name
        self._refresh_sets()

    def rename_set(self):
        old = self.app.s["scratch_current"]
        name = self._ask_name("Rename set:", old)
        if not name or name == old:
            return
        name = self._unique(name)
        sets = self._sets()
        self.app.s["scratch_sets"] = {(name if k == old else k): v for k, v in sets.items()}
        self.app.s["scratch_current"] = name
        self._refresh_sets()

    def delete_set(self):
        from tkinter import messagebox
        cur = self.app.s["scratch_current"]
        if not messagebox.askyesno("cleanpal", "Delete the set '%s'?" % cur,
                                   parent=self.win):
            return
        sets = self._sets()
        del sets[cur]
        if not sets:
            sets["Scratch"] = []
        self.app.s["scratch_current"] = next(iter(sets))
        self._refresh_sets()

    # ---------------------------------------------------------- drawing
    def _cell(self):
        return int(26 * self.ui), 3

    def draw(self):
        c = self.cv
        c.delete("all")
        sz, gap = self._cell()
        W = max(c.winfo_width(), sz + 10)
        cols = max(1, (W - 6) // (sz + gap))
        pal = set()
        if self.app.rgbs is not None:
            pal = {tuple(x) for x in self.app.rgbs if x is not None}
        self._cells = []
        cs = self.colours()
        for k, col in enumerate(cs):
            x = 4 + (k % cols) * (sz + gap)
            y = 4 + (k // cols) * (sz + gap)
            c.create_rectangle(x, y, x + sz, y + sz, fill=hex_of(col), outline="#000000")
            fg = "#000000" if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] > 140 \
                else "#ffffff"
            if col in pal:
                r = max(2, sz // 8)
                c.create_oval(x + sz - 3 - 2 * r, y + 3, x + sz - 3, y + 3 + 2 * r,
                              fill=fg, outline="")
            if k in self.sel:
                c.create_rectangle(x - 1, y - 1, x + sz + 1, y + sz + 1, outline="#00ffff",
                                   width=2)
            self._cells.append((x, y, sz, k))
        if not cs:
            c.create_text(10, 16, anchor="w", fill="#bbbbbb",
                          text="Empty - + Picker, + Selected, Eyedropper, Ctrl+V,\n"
                               "or drag cells here from the main grid.")
        self._cols = cols

    def _at(self, x, y):
        for cx, cy, sz, k in self._cells:
            if cx <= x < cx + sz and cy <= y < cy + sz:
                return k
        return None

    def _insert_at(self, x, y):
        sz, gap = self._cell()
        col = int(max(0, x - 4 + (sz + gap) / 2) // (sz + gap))
        row = int(max(0, y - 4) // (sz + gap))
        return min(row * self._cols + min(col, self._cols), len(self.swatches()))

    # ---------------------------------------------------------- mouse
    def _hover(self, ev):
        k = self._at(ev.x, ev.y)
        if k is None:
            self.info_var.set("")
            return
        col = self.colours()[k]
        t = "%s   %d,%d,%d" % ((hex_of(col),) + tuple(col))
        if self.app.rgbs is not None:
            hits = [i for i, x in enumerate(self.app.rgbs) if x is not None
                    and tuple(x) == col]
            if hits:
                t += "   in palette at %s" % ", ".join(str(i) for i in hits[:6])
        self.info_var.set(t)

    def _press(self, ev):
        self.win.focus_set()
        k = self._at(ev.x, ev.y)
        shift, ctrl = ev.state & 0x0001, ev.state & 0x0004
        if k is None:
            if not (shift or ctrl):
                self.sel = set()
                self.draw()
            self._drag = None
            return
        if shift and self._anchor is not None:
            a, b = sorted((self._anchor, k))
            self.sel |= set(range(a, b + 1))
        elif ctrl:
            self.sel ^= {k}
            self._anchor = k
        elif k not in self.sel:
            self.sel = {k}
            self._anchor = k
        self._drag = {"k": k, "x": ev.x, "y": ev.y, "moved": False,
                      "plain": not (shift or ctrl)}
        self.draw()

    def _motion(self, ev):
        d = self._drag
        if d and abs(ev.x - d["x"]) + abs(ev.y - d["y"]) > 4:
            d["moved"] = True
            self.cv.configure(cursor="fleur")

    def _release(self, ev):
        d = self._drag
        self._drag = None
        self.cv.configure(cursor="")
        if not d:
            return
        cols = self.colours()
        rgb = cols[d["k"]]
        if not d["moved"]:
            if d["plain"]:
                self.sel = {d["k"]}
                self._anchor = d["k"]
                self.draw()
                self.send_to_picker(rgb)
            return
        w = self.win.winfo_containing(ev.x_root, ev.y_root)
        a = self.app
        if w is self.cv:
            self._reorder(self._insert_at(ev.x, ev.y))
        elif w is a.canvas:
            a.drop_colour_on_grid(ev.x_root, ev.y_root, rgb)
            self.draw()
        elif a.ramp is not None and w is a.ramp.bar:
            a.ramp.drop_colour(ev.x_root, rgb)
        elif a.picker is not None and w is not None and \
                str(w).startswith(str(a.picker.win)):
            a.picker.set_rgb(rgb)
            a.picker._commit()

    def _reorder(self, pos):
        sw = self.swatches()
        moving = sorted(self.sel) if self.sel else []
        if not moving:
            return
        items = [sw[k] for k in moving]
        before = sum(1 for k in moving if k < pos)
        rest = [x for k, x in enumerate(sw) if k not in self.sel]
        pos -= before
        sw[:] = rest[:pos] + items + rest[pos:]
        self.sel = set(range(pos, pos + len(items)))
        self.draw()

    def _right(self, ev):
        a = self.app
        k = self._at(ev.x, ev.y)
        menu = a.tk.Menu(self.cv, tearoff=0)
        clip = parse_colour_list(a._clip_text(self.win))
        if k is not None:
            if k not in self.sel:
                self.sel = {k}
                self._anchor = k
                self.draw()
            col = self.colours()[k]
            menu.add_command(label="Copy hex  (%s)" % hex_of(col),
                             command=lambda: a._copy_text(self.win, hex_of(col), "hex"))
            menu.add_command(label="Copy R,G,B",
                             command=lambda: a._copy_text(self.win, "%d,%d,%d" % col,
                                                          "R,G,B"))
            if len(self.sel) > 1:
                menu.add_command(label="Copy %d selected as hex" % len(self.sel),
                                 command=self.copy)
            menu.add_separator()
        menu.add_command(
            label=("Paste %d colour(s) here" % len(clip)) if clip else "Paste colour(s)",
            state="normal" if clip else "disabled",
            command=lambda: self._paste_at(clip, k + 1 if k is not None else None))
        if k is not None:
            menu.add_command(label="Send to picker", command=lambda: self.send_to_picker(
                self.colours()[k]))
            menu.add_separator()
            n = len(self.sel)
            menu.add_command(label="Remove" if n <= 1 else "Remove %d selected" % n,
                             command=self.delete_selected)
        a._popup(menu, ev)

    def _paste_at(self, cols, pos):
        if not cols:
            return
        sw = self.swatches()
        if pos is None:
            pos = len(sw)
        sw[pos:pos] = [hex_of(c) for c in cols]
        self.sel = set(range(pos, pos + len(cols)))
        self.draw()
        self.app.status_var.set("Scratch: pasted %d colour(s)." % len(cols))

    def _select_all(self):
        self.sel = set(range(len(self.swatches())))
        self.draw()

    def delete_selected(self):
        if not self.sel:
            return
        sw = self.swatches()
        sw[:] = [x for k, x in enumerate(sw) if k not in self.sel]
        self.sel = set()
        self.draw()

    # ---------------------------------------------------------- actions
    def send_to_picker(self, rgb):
        a = self.app
        p = a.picker
        if p is None:
            if a.ramp is not None:
                a.ramp.open_picker()
            else:
                a.open_picker()
            p = a.picker
        p.set_rgb(rgb)
        p._commit()

    def add_picker(self):
        if self.app.picker is None:
            self.app.status_var.set("Open the colour picker first (Picker... in the "
                                    "Ramp tool, or click a swatch).")
            return
        self.add_colours([self.app.picker.rgb()])

    def add_selected(self):
        a = self.app
        if a.rgbs is None:
            return
        cols = [a.rgbs[i] for i in sorted(a.selection) if a.rgbs[i] is not None]
        if not cols:
            a.status_var.set("Select coloured cells in the main grid first.")
            return
        self.add_colours(cols)

    def eyedropper(self):
        EyeDropper(self.app, lambda rgb: self.add_colours([rgb]))

    def fill_selected(self):
        a = self.app
        if not self.sel:
            a.status_var.set("Pick a scratch swatch first.")
            return
        rgb = self.colours()[min(self.sel)]
        if not a.selection:
            a.status_var.set("Select the palette cells to fill first.")
            return
        a.set_cells_colour(sorted(a.selection), rgb)
        self.draw()

    def copy(self):
        cols = self.colours()
        pick = sorted(self.sel) if self.sel else range(len(cols))
        txt = "\n".join(hex_of(cols[k]) for k in pick)
        if txt:
            self.win.clipboard_clear()
            self.win.clipboard_append(txt)
            self.app.status_var.set("Copied %d colour(s)." % len(list(pick)))

    def paste(self):
        try:
            txt = self.win.clipboard_get()
        except self.app.tk.TclError:
            return
        cols = parse_colour_list(txt)
        if cols:
            self.add_colours(cols)

    def import_file(self):
        from tkinter import filedialog, messagebox

        p = filedialog.askopenfilename(
            parent=self.win, title="Import colours",
            initialdir=self.app.s.get("scratch_dir") or None,
            filetypes=[("Colour lists", "*.txt *.hex *.gpl *.pal"),
                       ("Hex text", "*.txt *.hex"), ("GIMP palette", "*.gpl"),
                       ("Palette", "*.pal"), ("All files", "*.*")])
        if not p:
            return
        try:
            cols = read_colour_file(p)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not import:\n%s\n\n%s" % (p, e),
                                 parent=self.win)
            return
        name = self._unique(os.path.splitext(os.path.basename(p))[0] or "Imported")
        self._sets()[name] = [hex_of(c) for c in cols]
        self.app.s["scratch_current"] = name
        self.app.s["scratch_dir"] = os.path.dirname(p)
        self._refresh_sets()
        self.app.status_var.set("Imported %d colours as set '%s'." % (len(cols), name))

    def export_file(self):
        from tkinter import filedialog, messagebox

        p = filedialog.asksaveasfilename(
            parent=self.win, title="Export set",
            initialdir=self.app.s.get("scratch_dir") or None,
            initialfile=self.app.s["scratch_current"] + ".gpl",
            defaultextension=".gpl",
            filetypes=[("GIMP palette", "*.gpl"), ("Hex text", "*.txt")])
        if not p:
            return
        cols = self.colours()
        try:
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                if p.lower().endswith(".gpl"):
                    fh.write("GIMP Palette\nName: %s\nColumns: 16\n#\n"
                             % self.app.s["scratch_current"])
                    for c in cols:
                        fh.write("%3d %3d %3d\t%s\n" % (c + (hex_of(c),)))
                else:
                    fh.write("\n".join(hex_of(c) for c in cols) + "\n")
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not export:\n%s" % e, parent=self.win)
            return
        self.app.s["scratch_dir"] = os.path.dirname(p)
        self.app.status_var.set("Exported %d colours to %s" % (len(cols), p))

    def close(self):
        try:
            self.app.s["scratch_geometry"] = self.win.geometry()
        except self.app.tk.TclError:
            pass
        self.app.s["scratch_pin"] = bool(self.pin_var.get())
        self.app.scratch = None
        self.win.destroy()


def read_colour_file(path):
    """Colours from hex text, GIMP .gpl, JASC .pal or raw .pal (pal0)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    ext = os.path.splitext(path)[1].lower()
    head = raw[:16]
    if ext == ".pal" and not head.startswith(b"JASC-PAL"):
        if len(raw) < 3 or len(raw) % 3:
            raise ValueError("Raw .pal size is not a multiple of 3 bytes.")
        n = min(len(raw) // 3, ENTRIES)
        return [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i in range(n)]
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    cols = []
    if head.startswith(b"GIMP Palette") or ext == ".gpl":
        for ln in lines[1:]:
            t = ln.strip()
            if not t or t.startswith("#") or t.split(":")[0] in ("Name", "Columns"):
                continue
            parts = t.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                v = tuple(int(p) for p in parts[:3])
                if all(0 <= x <= 255 for x in v):
                    cols.append(v)
    elif head.startswith(b"JASC-PAL"):
        for ln in lines[3:]:
            parts = ln.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                cols.append(tuple(min(int(p), 255) for p in parts[:3]))
    else:
        cols = parse_colour_list(text)
    if not cols:
        raise ValueError("No colours found.")
    return cols


# ============================================================ ramp test (CLI)
def _ramp_segments(rgbs):
    """Ramps implied by a palette's own order: runs of close neighbours that
    keep stepping the same way in lightness (works for light->dark and
    dark->light layouts)."""
    labs = [oklab(c) for c in rgbs]
    steps = [labs[i + 1][0] - labs[i][0] for i in range(len(rgbs) - 1)]
    down = sum(1 for d in steps if d < 0) >= sum(1 for d in steps if d > 0)
    segs, cur = [], [0]
    for i in range(len(rgbs) - 1):
        a, b = labs[i], labs[i + 1]
        dist = math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))
        same_way = (b[0] <= a[0] + 0.005) if down else (b[0] >= a[0] - 0.005)
        if dist <= 0.12 and same_way:
            cur.append(i + 1)
        else:
            segs.append(cur)
            cur = [i + 1]
    segs.append(cur)
    return [s for s in segs if len(s) >= 3]


def _ramp_score(rgbs, segs, out):
    pos = {}
    for k, c in enumerate(out):
        pos.setdefault(c, []).append(k)
    hit = tot = intact = 0
    for s in segs:
        h = 0
        for a, b in zip(s, s[1:]):
            ca, cb = rgbs[a], rgbs[b]
            if ca == cb or any(abs(x - y) == 1 for x in pos[ca] for y in pos[cb]):
                h += 1
        hit += h
        tot += len(s) - 1
        intact += h >= 0.9 * (len(s) - 1)
    return (hit / tot if tot else 0.0), intact


def ramp_test(path, outdir=None):
    import random
    import time
    from PIL import Image, ImageDraw

    rgbs, label = load_palette(path)
    rgbs = [tuple(c) for c in rgbs]
    segs = _ramp_segments(rgbs)
    print("")
    print("cleanpal ramptest  -  %s  [%s]" % (os.path.basename(path), label))
    print("Ramps found in the palette's own order: %d (%d colours). Each method"
          % (len(segs), sum(len(s) for s in segs)))
    print("sorts 3 shuffled copies with its default settings and is scored on")
    print("how many of those ramp links come back as neighbours.")
    print("")
    print("  %-16s %10s %12s %7s %8s" % ("method", "links kept", "ramps intact",
                                         "ramps", "time"))
    results = []
    for name in SORT_METHOD_NAMES:
        if name == "Reverse":
            continue
        tot_l = tot_i = 0.0
        t_all = 0.0
        nr = 0
        first = None
        for seed in (1, 2, 3):
            sh = rgbs[:]
            random.Random(seed).shuffle(sh)
            t = time.time()
            order, nr = ramp_sort(sh, name)
            t_all += time.time() - t
            out = [sh[i] for i in order]
            lk, it = _ramp_score(rgbs, segs, out)
            tot_l += lk
            tot_i += it
            if first is None:
                first = out
        results.append((name, tot_l / 3, tot_i / 3, nr, t_all / 3, first))
        print("  %-16s %9.1f%% %8.1f / %-3d %7s %7.2fs" % (
            name, 100 * tot_l / 3, tot_i / 3, len(segs), nr if nr else "-", t_all / 3))
    best = max(results, key=lambda r: (r[1], r[2]))
    print("")
    print("Best here: %s" % best[0])

    cell, gap, pad, head = 10, 1, 12, 16
    gw = 16 * (cell + gap)
    panels = [("original", rgbs)] + [(r[0], r[5]) for r in results]
    cols = 3
    rows = (len(panels) + cols - 1) // cols
    im = Image.new("RGB", (pad + cols * (gw + pad), pad + rows * (gw + head + pad)),
                   (38, 38, 38))
    dr = ImageDraw.Draw(im)
    for k, (name, cs) in enumerate(panels):
        ox = pad + (k % cols) * (gw + pad)
        oy = pad + (k // cols) * (gw + head + pad)
        dr.text((ox, oy), name, fill=(255, 255, 255))
        for j, c in enumerate(cs):
            x = ox + (j % 16) * (cell + gap)
            y = oy + head + (j // 16) * (cell + gap)
            dr.rectangle([x, y, x + cell - 1, y + cell - 1], fill=c)
    outdir = outdir or os.getcwd()
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0]
                       + "_ramptest.png")
    im.save(out)
    print("Comparison image: %s" % out)
    print("")


def _dep_check_pil():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Missing dependencies: Pillow")
        print("Install with: pip install Pillow")
        sys.exit(1)


# ============================================================ main
def main():
    args = sys.argv[1:]
    if any(a.lower() in ("-h", "--help", "-help", "/?") for a in args):
        print_help()
        return
    if args and args[0].lower() == "--ramptest":
        if len(args) not in (2, 3):
            print("Usage: cleanpal --ramptest <palette> [output folder]")
            sys.exit(1)
        if not os.path.isfile(args[1]):
            print("Input file not found: %s" % args[1])
            sys.exit(1)
        _dep_check_pil()
        try:
            ramp_test(args[1], args[2] if len(args) == 3 else None)
        except (ValueError, OSError) as e:
            print("ramptest failed: %s" % e)
            sys.exit(1)
        return
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("Usage: cleanpal [input]   (cleanpal --help for details)")
        sys.exit(1)
    path = args[0] if args else None
    if path and not os.path.isfile(path):
        print("Input file not found: %s" % path)
        sys.exit(1)

    _dep_check()
    import tkinter as tk

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    App(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
