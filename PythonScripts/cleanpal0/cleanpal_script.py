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

Exports: DoomTools playpal.png (tinted), DoomTools blank playpal.png,
SLADE pal0.png, SLADE pal0.pal, SLADE playpal.pal (tinted), Analysis PNGs.
Removed / empty slots are transparent in PNGs and green (0,255,0) in .pal.
"""

import json
import math
import os
import struct
import sys

VERSION = "1.7.1"
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
        "  Save / Load preset buttons store matching + export setups as .json",
        "  (default folder %APPDATA%\\cleanpal\\presets).",
        "",
        H("EXAMPLES"),
        "  " + C("cleanpal") + "                       " + D("open empty, pick a file"),
        "  " + C("cleanpal PLAYPAL.png") + "           " + D("DoomTools playpal / SLADE pal0.png"),
        "  " + C("cleanpal doom2.wad") + "             " + D("pal0 from the PLAYPAL lump"),
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


# ============================================================ presets
PRESET_KEYS = ("exact", "similar", "metric", "tol_de2000", "tol_lab", "tol_rgb",
               "align", "split", "export")


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
    if not out:
        raise ValueError("Preset contains no settings.")
    return out


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
  A snapshot taken after stepping back discards the later entries.
  History is for this session only. Closing with snapshots that have not
  been exported asks first. Loading a palette starts a fresh history.
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
  each metric's tolerance, Align, export format, split, window size /
  position and the last folder. Stored in
  %%APPDATA%%\\cleanpal\\cleanpal_settings.json. You are told if saving fails.

PRESETS
  Save preset...  writes the matching + export setup to a .json file:
                  tick boxes, metric, every metric's tolerance, Align,
                  export format and split (no window size or folders).
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
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=(8, 8, 8, 0))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(top, text="Open...", command=self.open_dialog).pack(side="left")
        ttk.Button(top, text="Palettised preview...",
                   command=self.open_preview).pack(side="right")
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
            filetypes=[("Palette sources", "*.wad *.pal *.png"),
                       ("WAD", "*.wad"), ("Palette", "*.pal"),
                       ("PNG", "*.png"), ("All files", "*.*")])
        if p:
            self.load(p)

    def load(self, path):
        from tkinter import messagebox

        try:
            rgbs, label = load_palette(path)
        except (ValueError, OSError) as e:
            messagebox.showerror("cleanpal", "Could not load:\n%s\n\n%s" % (path, e))
            return
        if self.move_var.get():
            self._exit_move(record=False)
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
                if ent and ent[1] != "empty" and ent[0] in self.selection:
                    x, y, C = self._cell_xy(slot)
                    w = max(2, min(5, round(C / 10)))
                    # black under, bright cyan over: readable on any colour
                    cv.create_rectangle(x + w, y + w, x + C - w, y + C - w,
                                        outline="#000000", width=w + 3)
                    cv.create_rectangle(x + w, y + w, x + C - w, y + C - w,
                                        outline="#00ffff", width=w)
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
        return self.res is not None and \
            self.res["status"][idx] in ("kept", "similar", "deleted")

    @staticmethod
    def _alt_down(ev):
        return bool(ev.state & (0x20000 if os.name == "nt" else 0x0008))

    def _on_b1_press(self, ev):
        if self.res is None:
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
        self.recompute()

    @staticmethod
    def _typing(ev):
        return ev.widget.winfo_class() in ("TEntry", "Entry", "TSpinbox", "Spinbox",
                                           "Text", "TCombobox")

    def _on_select_all(self, ev):
        if self._typing(ev) or self.res is None:
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
        if self._typing(ev) or self.rgbs is None:
            return
        self.move_var.set(not self.move_var.get())
        self._on_move_toggle()

    def _on_move_button(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
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
        if self.selection:
            self.selection = set()
            self.recompute()

    # ---------------------------------------------------------- snapshots
    def _load_entry(self, i):
        h = self.history[i]
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
        if not self.history or not 0 <= i < len(self.history) or self.move_var.get():
            return
        self._load_entry(i)
        self.status_var.set("Loaded #%d." % i)

    def step_back(self):
        if self.hist_pos > 0:
            self.jump_to(self.hist_pos - 1)

    def remove_snapshot(self):
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
        if self.move_var.get():
            self._undo_move()
        else:
            self.step_back()

    def _on_hist_select(self, _ev):
        if self.move_var.get():
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
        moving = self.move_var.get()
        on = ["!disabled"] if self.hist_pos > 0 and not moving else ["disabled"]
        self.back_btn.state(on)
        self.remove_btn.state(on)
        self.snap_btn.state(["disabled"] if moving else ["!disabled"])
        lb.configure(state="disabled" if moving else "normal")

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
        if self.src_path:
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
        return d

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
        self._update_states()
        self._sync_tol_widgets()
        self.recompute()
        self.s["preset_dir"] = os.path.dirname(p)
        self.preset_name = os.path.splitext(os.path.basename(p))[0]
        self._update_title()
        self.status_var.set("Loaded preset %s" % p)

    def on_close(self):
        if self.move_var.get():
            self._exit_move()
        if self.preview is not None:
            self.preview.store_state()
        if len(self.history) > 1 and not self.exported:
            from tkinter import messagebox
            if not messagebox.askyesno(
                    "cleanpal", "You have snapshots that haven't been exported.\n\n"
                                "Close without exporting?"):
                return
        self.s.update({
            "exact": self.exact_var.get(), "similar": self.similar_var.get(),
            "metric": self.metric_var.get(),
            "tol_de2000": self.tol["de2000"],
            "tol_lab": self.tol["lab"], "tol_rgb": self.tol["rgb"],
            "align": self.align_var.get(), "split": self.split_var.get(),
            "export": self.export_var.get(),
        })
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


# ============================================================ main
def main():
    args = sys.argv[1:]
    if any(a.lower() in ("-h", "--help", "-help", "/?") for a in args):
        print_help()
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
