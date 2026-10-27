#!/usr/bin/env python3
"""
png2endoom - convert images into a 4000-byte DOOM ENDOOM lump, with a
realtime preview GUI, stackable layers, project files and a headless CLI.

Moebius (https://blocktronics.github.io/moebius/) .ans / .bin / .xb files can
be opened as a finished screen, added as cell layers, and exported (flattened
screen plus one file per layer).

Layers: every layer is converted on its own (own placement, adjustments and
conversion settings) into its own 80x25 cells; the finished cells are then
stacked, top layer winning in each cell it covers.

Fonts embedded for the preview / solver:
  Hauge 8x18  - the font nyan-doom / dsda-doom use for ENDOOM.
                Copyright (C) 2026 Zokum, CC BY-SA 4.0
                https://creativecommons.org/licenses/by-sa/4.0/
  VGA 8x16    - the DOS font from the DOSBox project, as used by
                Chocolate Doom. Copyright (C) 2002-2004 The DOSBox Team, GPL.
"""

VERSION = "1.3.0"
TOOL = "png2endoom"

import os
import sys
import json
import math
import zlib
import time
import base64
import struct

# ---------------------------------------------------------------------------
# Help (works on a bare install: no numpy / Pillow / tkinter needed)
# ---------------------------------------------------------------------------

HELP = r"""
{B}png2endoom{R} {D}v{VER}{R} - images to DOOM ENDOOM lump, with layers and realtime preview

{C}USAGE{R}
  {G}png2endoom{R}                            open the GUI
  {G}png2endoom{R} image.png                  open the GUI with an image as the first layer
  {G}png2endoom{R} title.p2e                  open a saved layer project
  {G}png2endoom{R} ENDOOM                     view an existing lump (raw 4000 bytes or a WAD)
  {G}png2endoom{R} art.ans                    view a Moebius file (.ans / .bin / .xb) as the screen
  {G}png2endoom{R} image.png {G}-o{R} ENDOOM  [opts]  headless convert, single image
  {G}png2endoom{R} title.p2e {G}-o{R} ENDOOM  [opts]  headless convert, layer project
  {G}png2endoom{R} art.ans {G}-o{R} ENDOOM            headless: Moebius file straight to a lump

{C}GUI{R}
  {D}Every setting updates the preview live. Layers button: stack several PNGs
  (alpha respected), each with its own placement, adjustments and conversion
  settings. Drag the preview to move the selected layer, drag its outline's
  handles to scale it (edges = one direction, Shift = keep aspect ratio),
  wheel to scale it, Ctrl (or Shift when moving) to ignore cell snapping,
  Alt+click to pick the layer under the pointer. The Help button explains every control.{R}

{C}HEADLESS OPTIONS{R}
  {G}-o, --output{R} FILE      write the lump to FILE {Y}(this is what makes it headless){R}
  {G}-p, --preset{R} FILE      layer settings preset {D}(single image only){R}
  {G}--preview{R} FILE         also write a preview PNG at the port font's native size
  {G}--font{R} hauge|vga       port font {D}(default hauge = nyan/dsda; overrides a project's){R}
  {G}--moebius{R} FILE         also export for Moebius: FILE.bin or FILE.ans (flattened screen)
                         {D}plus FILE_<layer>.bin/.ans for every visible layer{R}
  {G}--no-layer-files{R}       with --moebius: write only the flattened file
  {G}-h, --help, -help{R}      this screen

{C}PROJECTS, SETTINGS & PRESETS{R}
  {D}A project (.p2e, JSON) stores the layers bottom to top: image paths
  (absolute, plus relative to the project file as a fallback), visibility,
  placement and every layer setting, plus the port font and screen colour.
  Presets hold one layer's adjustment + conversion settings (no placement).
  Last-used settings, window size and folders are saved on close to
  %APPDATA%\png2endoom\png2endoom_settings.json; presets default to
  %APPDATA%\png2endoom\presets.{R}

{C}MOEBIUS{R}
  {D}.bin (Binary Text) is exactly ENDOOM's cells plus a SAUCE record saying 80
  columns - lossless both ways. .ans is Moebius's own format. Moebius files
  can be layers: their cells go straight into the stack (no conversion),
  with one background colour (default black) treated as see-through.
  Loading: bigger than 80x25 shows the top-left (move the layer to show
  another part); iCE bright backgrounds become their dark versions; blink is
  kept; XBin custom fonts/palettes and 24-bit ANSI colours are ignored.{R}

{C}NOTES{R}
  {D}ENDOOM is 80x25 cells, 2 bytes each: CP437 character, then attribute
  (bits 0-3 foreground 0-15, bits 4-6 background 0-7, bit 7 blink).
  png2endoom never sets bit 7 - nyan/dsda really do blink those cells.
  Each cell is sampled as a 2x2 grid and solved from solid, top/bottom and
  left/right halves and the 25/50/75% shade characters. nyan/dsda draw
  ENDOOM with the Hauge 8x18 font (640x450 screen); Chocolate Doom and
  8x16-font viewers are 640x400 - pick the VGA font for those.
  Fonts: Hauge 8x18 (C) 2026 Zokum, CC BY-SA 4.0. VGA 8x16 from DOSBox
  (C) 2002-2004 The DOSBox Team, GPL.{R}

{C}EXAMPLES{R}
  {G}png2endoom{R} sky.png
  {G}png2endoom{R} title.p2e {G}-o{R} src\lumps\ENDOOM
  {G}png2endoom{R} title.png {G}-o{R} ENDOOM {G}-p{R} punchy.json {G}--preview{R} endoom_check.png
  {G}png2endoom{R} title.p2e {G}-o{R} ENDOOM {G}--moebius{R} edit\title.bin
  {G}png2endoom{R} mymod.wad
"""


def _enable_vt():
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


def _colour_ok():
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def print_help():
    if _colour_ok():
        _enable_vt()
        codes = dict(B="\033[1m", C="\033[1;36m", G="\033[92m", Y="\033[93m",
                     D="\033[90m", R="\033[0m")
    else:
        codes = dict(B="", C="", G="", Y="", D="", R="")
    try:
        print(HELP.format(VER=VERSION, **codes).rstrip() + "\n")
    except BrokenPipeError:
        pass


def check_dependencies(need_gui):
    missing = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("pillow")
    if missing:
        print(f"[{TOOL}] missing Python packages: {', '.join(missing)}")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)
    if need_gui:
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print(f"[{TOOL}] tkinter is missing - re-run the Python installer and tick "
                  "'tcl/tk and IDLE' (it is part of standard Python on Windows).")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Constants and settings model
# ---------------------------------------------------------------------------

DOS16 = [
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xAA), (0x00, 0xAA, 0x00), (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00), (0xAA, 0x00, 0xAA), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55), (0x55, 0x55, 0xFF), (0x55, 0xFF, 0x55), (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0x55), (0xFF, 0xFF, 0xFF),
]

COLS, ROWS = 80, 25
GRID_W, GRID_H = COLS * 2, ROWS * 2          # 2x2 samples per cell
WORK_MAX = 1600                              # loaded images are capped to this long side

SHADES = (176, 177, 178)
GLYPHSETS = {
    "halves":    ("Half-blocks only",             [32, 219, 223, 220]),
    "halves_lr": ("Half-blocks + left/right",     [32, 219, 223, 220, 221, 222]),
    "all":       ("Halves, left/right + shades",  [32, 219, 223, 220, 221, 222, 176, 177, 178]),
}
FONT_LABELS = {
    "hauge": "Hauge 8x18 (nyan / dsda)",
    "vga":   "VGA 8x16 (Chocolate / DOSBox)",
}
METRIC_LABELS = {
    "redmean": "Weighted RGB (redmean)",
    "rgb":     "Plain RGB",
}
KEY_LABELS = {
    "off": "Off (every cell solid)",
    "black": "Black", "blue": "Blue", "green": "Green", "cyan": "Cyan",
    "red": "Red", "magenta": "Magenta", "brown": "Brown", "grey": "Light grey",
}
KEY_INDEX = {"black": 0, "blue": 1, "green": 2, "cyan": 3, "red": 4, "magenta": 5, "brown": 6, "grey": 7}
TEXT_EXTS = {".ans", ".asc", ".diz", ".ice", ".nfo"}
MOEBIUS_EXTS = TEXT_EXTS | {".bin", ".xb"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tga", ".webp"}

VIEW_LABELS = {
    "endoom":    "ENDOOM",
    "original":  "Original (layers, true colour)",
    "split":     "Original | ENDOOM",
    "solo":      "Solo (selected layer's cells)",
    "target":    "Target (selected layer, adjusted)",
    "ownership": "Ownership (which layer won each cell)",
}

# key: (label, min, max, step[, spin increment])
SLIDERS = {
    "x":             ("X px",        -4000, 4000, 1),
    "y":             ("Y px",        -4000, 4000, 1),
    "scale_x":       ("Width %",       1, 5000, 0.01, 1),
    "scale_y":       ("Height %",      1, 5000, 0.01, 1),
    "brightness":    ("Brightness",  -100, 100, 1),
    "contrast":      ("Contrast",    -100, 100, 1),
    "saturation":    ("Saturation",  -100, 100, 1),
    "gamma":         ("Gamma",        0.2, 3.0, 0.05),
    "black_point":   ("Black point",    0, 128, 1),
    "shade_penalty": ("Shade penalty",  0, 100, 1),
    "dither":        ("Dither %",       0, 100, 1),
    "coverage":      ("Coverage %",     1, 100, 1),
    "col":           ("Column",     -2000, 2000, 1),
    "row":           ("Row",        -9999, 9999, 1),
}

CHOICES = {
    "font": FONT_LABELS,
    "glyphs": GLYPHSETS,
    "metric": METRIC_LABELS,
    "view": VIEW_LABELS,
    "key": KEY_LABELS,
}
BOOL_KEYS = {"save_preview", "snap", "alt_select", "show_outline", "edge_fill", "moebius_layers"}
COLOUR_KEYS = {"alpha_bg"}

DEFAULT_GLOBAL = {
    "font": "hauge",
    "alpha_bg": "#000000",
    "view": "endoom",
    "save_preview": True,
    "snap": True,
    "alt_select": True,
    "show_outline": True,
    "moebius_layers": True,
}

DEFAULT_LAYER = {
    "x": 0.0,
    "y": 0.0,
    "scale_x": 100.0,
    "scale_y": 100.0,
    "brightness": 0.0,
    "contrast": 0.0,
    "saturation": 0.0,
    "gamma": 1.0,
    "black_point": 12.0,
    "glyphs": "all",
    "shade_penalty": 40.0,
    "dither": 0.0,
    "metric": "redmean",
    "coverage": 50.0,
    "edge_fill": True,
    "col": 0.0,          # Moebius layers: position in cells
    "row": 0.0,
    "key": "black",      # Moebius layers: see-through background colour
}
PLACEMENT_KEYS = ("x", "y", "scale_x", "scale_y")
CONVERSION_KEYS = ("glyphs", "shade_penalty", "dither", "metric", "coverage", "edge_fill")
CELL_KEYS = ("col", "row", "key")
ADJUST_KEYS = ("brightness", "contrast", "saturation", "gamma", "black_point")
# What a preset carries: one layer's settings minus placement.
PRESET_KEYS = [k for k in DEFAULT_LAYER if k not in PLACEMENT_KEYS and k not in CELL_KEYS]
PRESET_MARKER = "png2endoom_preset"
PROJECT_MARKER = "png2endoom_project"
PROJECT_EXT = ".p2e"

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), TOOL)
SETTINGS_PATH = os.path.join(APP_DIR, f"{TOOL}_settings.json")
PRESET_DIR = os.path.join(APP_DIR, "presets")


def _is_hex_colour(v):
    if not isinstance(v, str) or len(v) != 7 or v[0] != "#":
        return False
    try:
        int(v[1:], 16)
        return True
    except ValueError:
        return False


def validate_settings(src, keys, strict=False):
    """Clean dict of the recognised keys in src. strict=True raises
    ValueError on a bad value; otherwise bad values are dropped."""
    out = {}
    if not isinstance(src, dict):
        if strict:
            raise ValueError("settings must be an object")
        return out
    for k in keys:
        if k not in src:
            continue
        v = src[k]
        ok = True
        if k in SLIDERS:
            lo, hi = SLIDERS[k][1], SLIDERS[k][2]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi):
                ok = False
            else:
                v = float(v)
        elif k in CHOICES:
            ok = v in CHOICES[k]
        elif k in COLOUR_KEYS:
            ok = _is_hex_colour(v)
        elif k in BOOL_KEYS:
            ok = isinstance(v, bool)
        if ok:
            out[k] = v
        elif strict:
            raise ValueError(f"bad value for '{k}': {v!r}")
    return out


def load_preset_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get(PRESET_MARKER) != 1 or not isinstance(data.get("settings"), dict):
        raise ValueError("not a png2endoom preset file")
    return validate_settings(data["settings"], PRESET_KEYS, strict=True)


def save_preset_file(path, layer_settings):
    data = {PRESET_MARKER: 1, "version": VERSION,
            "settings": {k: layer_settings[k] for k in PRESET_KEYS}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_project_file(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        return head.lstrip()[:1] == b"{" and PROJECT_MARKER.encode() in head
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Core (imported lazily so -h works without numpy / Pillow)
# ---------------------------------------------------------------------------

np = None
Image = None


def import_core():
    global np, Image
    import numpy as _np
    from PIL import Image as _Image
    np, Image = _np, _Image


_font_cache = {}


def get_font(key):
    """(bits[256, h, 8] bool, w, h)"""
    if key not in _font_cache:
        h = {"hauge": 18, "vga": 16}[key]
        raw = zlib.decompress(base64.b64decode({"hauge": FONT_HAUGE_B64, "vga": FONT_VGA_B64}[key]))
        arr = np.frombuffer(raw, np.uint8).reshape(256, h, 1)
        bits = np.unpackbits(arr, axis=2).astype(bool)
        _font_cache[key] = (bits, 8, h)
    return _font_cache[key]


def screen_size(font):
    _, fw, fh = get_font(font)
    return COLS * fw, ROWS * fh


_cov_cache = {}


def quad_coverage(font):
    """[256,4] fraction of each quadrant (TL,TR,BL,BR) a glyph's foreground covers."""
    if font not in _cov_cache:
        bits, fw, fh = get_font(font)
        hw, hh = fw // 2, fh // 2
        _cov_cache[font] = np.stack([bits[:, :hh, :hw].mean(axis=(1, 2)),
                                     bits[:, :hh, hw:].mean(axis=(1, 2)),
                                     bits[:, hh:, :hw].mean(axis=(1, 2)),
                                     bits[:, hh:, hw:].mean(axis=(1, 2))], axis=1).astype(np.float32)
    return _cov_cache[font]


def prepare_source(img):
    """Any PIL image -> RGBA working copy, long side capped to WORK_MAX."""
    img = img.convert("RGBA")
    w, h = img.size
    if max(w, h) > WORK_MAX:
        sc = WORK_MAX / max(w, h)
        img = img.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.Resampling.LANCZOS)
    return img


def hex_rgb(hx):
    return tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))


def nearest_bg(hx):
    """Nearest of the 8 background colours to a hex colour."""
    r, g, b = hex_rgb(hx)
    return min(range(8), key=lambda i: (DOS16[i][0] - r) ** 2 + (DOS16[i][1] - g) ** 2 + (DOS16[i][2] - b) ** 2)


def crop_resample_pm(src_pm, box, size, resample):
    """Resample a float box of a premultiplied RGBa image; outside = transparent."""
    l, t, r, b = box
    W, H = src_pm.size
    L, T = math.floor(l), math.floor(t)
    R, B = math.ceil(r), math.ceil(b)
    if L >= 0 and T >= 0 and R <= W and B <= H:
        return src_pm.resize(size, resample, box=box)
    # Only the part of the box that overlaps the image matters; clamp the
    # padding canvas so a far-off or huge box can't allocate something silly.
    ix0, iy0 = max(L, 0), max(T, 0)
    ix1, iy1 = min(R, W), min(B, H)
    if ix1 <= ix0 or iy1 <= iy0:
        return Image.new("RGBa", size, (0, 0, 0, 0))
    # Padding wider than the resampling footprint, so output pixels left out
    # of the resampled slice below can only ever see transparency.
    fp = max((r - l) / size[0], (b - t) / size[1])
    pad = int(math.ceil(3 * fp)) + 2
    cl, ct = ix0 - pad, iy0 - pad
    canvas = Image.new("RGBa", (ix1 - ix0 + 2 * pad, iy1 - iy0 + 2 * pad), (0, 0, 0, 0))
    canvas.paste(src_pm.crop((ix0, iy0, ix1, iy1)), (pad, pad))
    sx = size[0] / (r - l)
    sy = size[1] / (b - t)
    ox0 = max(0, math.ceil((cl - l) * sx))
    oy0 = max(0, math.ceil((ct - t) * sy))
    ox1 = min(size[0], math.floor((cl + canvas.width - l) * sx))
    oy1 = min(size[1], math.floor((ct + canvas.height - t) * sy))
    out = Image.new("RGBa", size, (0, 0, 0, 0))
    if ox1 <= ox0 or oy1 <= oy0:
        return out
    sub_box = (max(0.0, l + ox0 / sx - cl), max(0.0, t + oy0 / sy - ct),
               min(float(canvas.width), l + ox1 / sx - cl), min(float(canvas.height), t + oy1 / sy - ct))
    out.paste(canvas.resize((ox1 - ox0, oy1 - oy0), resample, box=sub_box), (ox0, oy0))
    return out


def adjust(t, s):
    v = t.copy()
    if s["brightness"]:
        v += s["brightness"] * 1.28
    if s["contrast"]:
        f = ((100.0 + s["contrast"]) / 100.0) ** 2
        v = (v - 128.0) * f + 128.0
    if s["saturation"]:
        f = (100.0 + s["saturation"]) / 100.0
        luma = (v[..., 0] * 0.299 + v[..., 1] * 0.587 + v[..., 2] * 0.114)[..., None]
        v = luma + (v - luma) * f
    np.clip(v, 0, 255, out=v)
    if s["gamma"] != 1.0:
        v = 255.0 * (v / 255.0) ** (1.0 / s["gamma"])
    bp = s["black_point"]
    if bp:
        v = (v - bp) * (255.0 / (255.0 - bp))
    return np.clip(v, 0, 255).astype(np.float32)


_cand_cache = {}


def candidates(font, glyphs, metric, shade_penalty):
    """Every distinct thing a cell can look like for the font/glyphs.
    Returns (chars, fgs, bgs, rendered[N,4,3], penalty[N])."""
    key = (font, glyphs, metric, shade_penalty)
    if key in _cand_cache:
        return _cand_cache[key]
    cov = quad_coverage(font)
    pal = np.array(DOS16, np.float32)
    wsum = 9.0 if metric == "redmean" else 3.0
    pen_val = 4.0 * wsum * (shade_penalty * 0.5) ** 2
    chars, fgs, bgs, rends, pens = [], [], [], [], []
    seen = set()
    for ch in GLYPHSETS[glyphs][1]:
        c = cov[ch][:, None]
        for fg in range(16):
            for bg in range(8):
                rend = c * pal[fg] + (1.0 - c) * pal[bg]
                k = tuple(np.round(rend, 2).ravel().tolist())
                if k in seen:
                    continue
                seen.add(k)
                chars.append(ch); fgs.append(fg); bgs.append(bg); rends.append(rend)
                pens.append(pen_val if ch in SHADES else 0.0)
    res = (np.array(chars, np.uint8), np.array(fgs, np.uint8), np.array(bgs, np.uint8),
           np.array(rends, np.float32), np.array(pens, np.float32))
    if len(_cand_cache) > 24:
        _cand_cache.clear()
    _cand_cache[key] = res
    return res


def _costs(T, Wt, R, metric):
    """T[n,4,3] targets, Wt[n,4] quadrant weights, R[N,4,3] candidates -> cost[n,N]"""
    d = T[:, None, :, :] - R[None, :, :, :]
    if metric == "redmean":
        rbar = (T[:, None, :, 0] + R[None, :, :, 0]) * 0.5
        c = ((2.0 + rbar / 256.0) * d[..., 0] ** 2 + 4.0 * d[..., 1] ** 2
             + (2.0 + (255.0 - rbar) / 256.0) * d[..., 2] ** 2)
    else:
        c = (d * d).sum(-1)
    return (c * Wt[:, None, :]).sum(-1)


def to_cells(grid):
    """[50,160,C] -> [25,80,4,C] in TL,TR,BL,BR order"""
    c = grid.shape[2]
    return grid.reshape(ROWS, 2, COLS, 2, c).transpose(0, 2, 1, 3, 4).reshape(ROWS, COLS, 4, c)


def from_cells(cells):
    """[25,80,4,C] -> [50,160,C]"""
    c = cells.shape[3]
    return cells.reshape(ROWS, COLS, 2, 2, c).transpose(0, 2, 1, 3, 4).reshape(GRID_H, GRID_W, c)


def solve_cells(target, weight, claim, font, s):
    """target[25,80,4,3], weight[25,80,4], claim[25,80] bool -> chars, fg, bg [25,80]
    (only claimed cells are solved; the rest are left as zeros)."""
    chars, fgs, bgs, R, pen = candidates(font, s["glyphs"], s["metric"], s["shade_penalty"])
    metric = s["metric"]
    strength = s["dither"] / 100.0
    idx = np.zeros((ROWS, COLS), np.int64)
    ys, xs = np.nonzero(claim)
    if len(ys) == 0:
        return np.zeros((ROWS, COLS), np.uint8), np.zeros((ROWS, COLS), np.uint8), np.zeros((ROWS, COLS), np.uint8)
    if strength <= 0:
        T = target[ys, xs]
        Wt = weight[ys, xs]
        out = np.empty(len(T), np.int64)
        step = 80
        for i in range(0, len(T), step):
            out[i:i + step] = np.argmin(_costs(T[i:i + step], Wt[i:i + step], R, metric) + pen, axis=1)
        idx[ys, xs] = out
    else:
        # Error diffusion between claimed cells, using what each cell will
        # really render as. The 2x2 error block is pushed whole to neighbours.
        work = target.astype(np.float32).copy()
        for cy, cx in zip(ys.tolist(), xs.tolist()):
            t = np.clip(work[cy, cx], 0, 255)
            k = int(np.argmin(_costs(t[None], weight[cy, cx][None], R, metric)[0] + pen))
            idx[cy, cx] = k
            err = (t - R[k]) * strength * weight[cy, cx][:, None]
            for dy, dx, f in ((0, 1, 7 / 16), (1, -1, 3 / 16), (1, 0, 5 / 16), (1, 1, 1 / 16)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < ROWS and 0 <= nx < COLS and claim[ny, nx]:
                    work[ny, nx] += err * f
    return chars[idx], fgs[idx], bgs[idx]


def render(chars, fg, bg, font):
    """Draw cells with a port font -> PIL RGB image (640 x 25*fh)."""
    bits, fw, fh = get_font(font)
    pal = np.array(DOS16, np.uint8)
    mask = bits[chars]                                   # [25,80,fh,8]
    img = np.where(mask[..., None], pal[fg][:, :, None, None, :], pal[bg][:, :, None, None, :])
    img = img.transpose(0, 2, 1, 3, 4).reshape(ROWS * fh, COLS * fw, 3)
    return Image.fromarray(np.ascontiguousarray(img), "RGB")


def quad_colours(chars, fg, bg, font):
    """[25,80,4,3] colour each cell quadrant shows (glyph coverage mix)."""
    cov = quad_coverage(font)[chars][..., None]          # [25,80,4,1]
    pal = np.array(DOS16, np.float32)
    return cov * pal[fg][:, :, None, :] + (1.0 - cov) * pal[bg][:, :, None, :]


def build_lump(chars, fg, bg, blink=None):
    out = np.empty((ROWS, COLS, 2), np.uint8)
    out[..., 0] = chars
    out[..., 1] = (bg.astype(np.uint8) << 4) | fg.astype(np.uint8)
    if blink is not None:
        out[..., 1] |= (blink.astype(np.uint8) & 1) << 7
    data = out.tobytes()
    assert len(data) == 4000
    return data


def parse_lump(data):
    a = np.frombuffer(data, np.uint8).reshape(ROWS, COLS, 2)
    attr = a[..., 1]
    return a[..., 0].copy(), (attr & 15).copy(), ((attr >> 4) & 7).copy(), int((attr & 0x80).astype(bool).sum())


ENDOOM_NAMES = ["ENDOOM", "ENDBOOM", "ENDTEXT", "ENDSTRF"]


def read_endoom_file(path):
    """Raw 4000-byte lump or a WAD -> (bytes, description). Raises ValueError."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] in (b"IWAD", b"PWAD") and len(data) >= 12:
        n, off = struct.unpack_from("<ii", data, 4)
        found = {}
        for i in range(n):
            lp, ls, nm = struct.unpack_from("<ii8s", data, off + i * 16)
            name = nm.split(b"\0")[0].decode("ascii", "replace").upper()
            if name in ENDOOM_NAMES and ls == 4000:
                found[name] = data[lp:lp + ls]          # later entries win, like the engine
        for name in ENDOOM_NAMES:
            if name in found:
                return found[name], f"{os.path.basename(path)} : {name}"
        raise ValueError("no 4000-byte ENDOOM / ENDBOOM / ENDTEXT / ENDSTRF lump in that WAD")
    if len(data) == 4000:
        return data, os.path.basename(path)
    raise ValueError("not an image, a project, a 4000-byte ENDOOM lump, or a WAD")


def glyph_stats(chars):
    c = chars.ravel()
    solid = int(np.isin(c, (0, 32, 219, 255)).sum())
    tb = int(np.isin(c, (220, 223)).sum())
    lr = int(np.isin(c, (221, 222)).sum())
    sh = int(np.isin(c, SHADES).sum())
    other = c.size - solid - tb - lr - sh
    txt = f"solid {solid}  |  top/bottom {tb}  |  left/right {lr}  |  shades {sh}"
    if other:
        txt += f"  |  other {other}"
    return txt



# ---- Moebius / textmode formats ----

class TextDoc:
    """A grid of cells of any size: chars/fg(0-15)/bg(0-7)/blink [rows, cols]."""

    def __init__(self, chars, fg, bg, blink, warnings=None):
        self.chars, self.fg, self.bg, self.blink = chars, fg, bg, blink
        self.rows, self.columns = chars.shape
        self.warnings = warnings or []


def _doc_from_attrs(chars, attrs, ice, warns):
    fg = (attrs & 15).astype(np.uint8)
    bgr = (attrs >> 4).astype(np.uint8)
    bright = bgr >= 8
    if ice:
        n = int(bright.sum())
        if n:
            warns.append(f"{n} cell(s) used iCE bright backgrounds - changed to the dark version "
                         "(ENDOOM backgrounds are 0-7)")
        blink = np.zeros(chars.shape, bool)
    else:
        blink = bright
    return TextDoc(chars.astype(np.uint8), fg, (bgr & 7).astype(np.uint8), blink, warns)


def _parse_sauce(data):
    """-> (info dict or None, body bytes without SAUCE/comments/EOF)"""
    if len(data) >= 128 and data[-128:-123] == b"SAUCE" and data[-123:-121] == b"00":
        sb = data[-128:]
        filesize = int.from_bytes(sb[90:94], "little")
        datatype, filetype = sb[94], sb[95]
        t1, t2 = sb[96] | (sb[97] << 8), sb[98] | (sb[99] << 8)
        ncom, flags = sb[104], sb[105]
        end = len(data) - 128 - (ncom * 64 + 5 if ncom else 0)
        if end > 0 and data[end - 1] == 0x1A:
            end -= 1
        if filesize == 0 or filesize > end:
            filesize = max(end, 0)
        if datatype == 5:
            cols, rows = filetype * 2, None
        else:
            cols, rows = (t1 or None), (t2 or None)
        return {"columns": cols, "rows": rows, "ice": bool(flags & 1), "datatype": datatype}, data[:filesize]
    return None, data


def _read_bin(body, sauce, warns):
    if sauce and sauce["columns"]:
        cols = sauce["columns"]
    else:
        cols = 80 if len(body) == 4000 else 160      # Moebius assumes 160 without SAUCE
    if cols <= 0 or len(body) % (cols * 2):
        raise ValueError(f"Binary Text size {len(body)} doesn't fit {cols} columns")
    a = np.frombuffer(body, np.uint8).reshape(-1, cols, 2)
    return _doc_from_attrs(a[..., 0], a[..., 1], bool(sauce and sauce["ice"]), warns)


def _read_xbin(data, warns):
    if data[:5] != b"XBIN\x1a" or len(data) < 11:
        raise ValueError("not an XBin file")
    w, h = struct.unpack_from("<HH", data, 5)
    fontsize, flags = data[9], data[10]
    p = 11
    if flags & 1:
        pal = data[p:p + 48]
        p += 48
        std = all(abs(pal[i * 3 + c] * 4 - DOS16[i][c]) <= 8 for i in range(16) for c in range(3))
        if not std:
            warns.append("XBin custom palette ignored - standard 16 colours used")
    if flags & 2:
        p += fontsize * (512 if flags & 16 else 256)
        warns.append("XBin custom font ignored - CP437 characters used")
    n = w * h
    out = bytearray()
    if flags & 4:
        while len(out) < n * 2 and p < len(data):
            b = data[p]; p += 1
            kind, count = b >> 6, (b & 63) + 1
            if kind == 0:
                out += data[p:p + count * 2]; p += count * 2
            elif kind == 1:
                ch = data[p]; p += 1
                for k in range(count):
                    out += bytes((ch, data[p + k]))
                p += count
            elif kind == 2:
                at = data[p]; p += 1
                for k in range(count):
                    out += bytes((data[p + k], at))
                p += count
            else:
                out += bytes((data[p], data[p + 1])) * count; p += 2
    else:
        out = bytearray(data[p:p + n * 2])
    if len(out) < n * 2:
        raise ValueError("XBin image data is truncated")
    a = np.frombuffer(bytes(out[:n * 2]), np.uint8).reshape(h, w, 2)
    return _doc_from_attrs(a[..., 0], a[..., 1], bool(flags & 8), warns)


_ANSI_TO_DOS = [0, 4, 2, 6, 1, 5, 3, 7]


def _read_ansi(body, sauce, warns):
    cols = (sauce["columns"] if sauce and sauce["columns"] else 80)
    rows_c, rows_a = [], []

    def ensure(y):
        while len(rows_c) <= y:
            rows_c.append(bytearray(b" " * cols))
            rows_a.append(bytearray(b"\x07" * cols))

    x = y = 0
    fg, bg = 7, 0
    bold = blink = inverse = False
    saved = (0, 0)
    truecolour = False
    i, n = 0, len(body)
    while i < n:
        b = body[i]
        if b == 0x1A:
            break
        if b == 0x1B and i + 1 < n and body[i + 1] == 0x5B:
            j = i + 2
            while j < n and not (0x40 <= body[j] <= 0x7E):
                j += 1
            if j >= n:
                break
            params = body[i + 2:j].decode("ascii", "replace").lstrip("?=")
            final = chr(body[j])
            vals = [int(v) if v.isdigit() else None for v in params.split(";")] if params else []
            v0 = vals[0] if vals and vals[0] is not None else None
            if final == "m":
                for v in (vals or [0]):
                    v = 0 if v is None else v
                    if 30 <= v <= 37:
                        fg = _ANSI_TO_DOS[v - 30]
                    elif 40 <= v <= 47:
                        bg = _ANSI_TO_DOS[v - 40]
                    elif v == 0:
                        fg, bg, bold, blink, inverse = 7, 0, False, False, False
                    elif v == 1:
                        bold = True
                    elif v == 5:
                        blink = True
                    elif v == 7:
                        inverse = True
                    elif v == 22:
                        bold = False
                    elif v in (21, 25):
                        blink = False
                    elif v == 27:
                        inverse = False
                    elif v == 39:
                        fg = 7
                    elif v == 49:
                        bg = 0
            elif final in "Hf":
                r = vals[0] if len(vals) > 0 and vals[0] else 1
                c = vals[1] if len(vals) > 1 and vals[1] else 1
                y, x = max(0, r - 1), min(max(0, c - 1), cols - 1)
            elif final == "A":
                y = max(0, y - (v0 or 1))
            elif final == "B":
                y += v0 or 1
            elif final == "C":
                x = min(cols - 1, x + (v0 or 1))
            elif final == "D":
                x = max(0, x - (v0 or 1))
            elif final == "s":
                saved = (x, y)
            elif final == "u":
                x, y = saved
            elif final == "t":
                truecolour = True
            i = j + 1
            continue
        if b == 10:
            x, y = 0, y + 1
        elif b == 13:
            pass
        else:
            if inverse:
                fv, bv = bg + (8 if blink else 0), fg + (8 if bold else 0)
            else:
                fv, bv = fg + (8 if bold else 0), bg + (8 if blink else 0)
            ensure(y)
            rows_c[y][x] = b
            rows_a[y][x] = ((bv & 15) << 4) | (fv & 15)
            x += 1
            if x == cols:
                x, y = 0, y + 1
        i += 1
    if truecolour:
        warns.append("24-bit ANSI colours ignored - the 16-colour attributes were used")
    want = sauce["rows"] if sauce and sauce["rows"] else max(len(rows_c), 1)
    ensure(want - 1)
    chars = np.array([list(r) for r in rows_c[:want]], np.uint8).reshape(want, cols)
    attrs = np.array([list(r) for r in rows_a[:want]], np.uint8).reshape(want, cols)
    return _doc_from_attrs(chars, attrs, bool(sauce and sauce["ice"]), warns)


def doc_from_lump(data, warns=None):
    a = np.frombuffer(data, np.uint8).reshape(ROWS, COLS, 2)
    return _doc_from_attrs(a[..., 0], a[..., 1], False, warns or [])


def load_textmode(path):
    """Moebius .ans/.bin/.xb, a raw ENDOOM lump or a WAD -> TextDoc. Raises ValueError."""
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    warns = []
    if ext == ".xb" or data[:5] == b"XBIN\x1a":
        return _read_xbin(data, warns)
    sauce, body = _parse_sauce(data)
    if ext in TEXT_EXTS:
        return _read_ansi(body, sauce, warns)
    if ext == ".bin":
        return _read_bin(body, sauce, warns)
    if data[:4] in (b"IWAD", b"PWAD") or len(data) == 4000:
        lump, _ = read_endoom_file(path)
        return doc_from_lump(lump, warns)
    if sauce and sauce["datatype"] == 5:
        return _read_bin(body, sauce, warns)
    if sauce and sauce["datatype"] == 1:
        return _read_ansi(body, sauce, warns)
    raise ValueError("not an image, a Moebius file (.ans/.bin/.xb), an ENDOOM lump or a WAD")


def doc_to_screen(doc):
    """Top-left 80x25 of a TextDoc -> (chars, fg, bg, blink) screen arrays, blank-padded."""
    c = np.full((ROWS, COLS), 32, np.uint8)
    f = np.full((ROWS, COLS), 7, np.uint8)
    b = np.zeros((ROWS, COLS), np.uint8)
    k = np.zeros((ROWS, COLS), bool)
    h, w = min(doc.rows, ROWS), min(doc.columns, COLS)
    c[:h, :w], f[:h, :w], b[:h, :w], k[:h, :w] = doc.chars[:h, :w], doc.fg[:h, :w], doc.bg[:h, :w], doc.blink[:h, :w]
    return c, f, b, k


def _sauce_record(datatype, filetype, cols, rows, title):
    r = bytearray(128)
    r[0:7] = b"SAUCE00"
    r[7:42] = title.encode("ascii", "replace")[:35].ljust(35)
    r[42:62] = b" " * 20
    r[62:82] = b" " * 20
    r[82:90] = time.strftime("%Y%m%d").encode()
    r[94] = datatype
    if datatype == 5:
        r[95] = cols // 2
    else:
        r[95] = filetype
        r[96:98] = struct.pack("<H", cols)
        r[98:100] = struct.pack("<H", rows)
    r[105] = (1 << 1) | (1 << 4)                 # 8px letter spacing, legacy aspect
    r[106:113] = b"IBM VGA"
    return r


def encode_moebius(lump_bytes, ext, title=""):
    """4000-byte ENDOOM cells -> Moebius .bin or .ans bytes (with SAUCE)."""
    if ext == ".ans":
        out = bytearray(b"\x1b[0m")
        cur_fg, cur_bg, cur_bold, cur_blink = 7, 0, False, False
        for i in range(0, 4000, 2):
            code, attr = lump_bytes[i], lump_bytes[i + 1]
            fg, bg = attr & 15, attr >> 4
            code = {10: 9, 13: 14, 26: 16, 27: 17}.get(code, code)   # as Moebius does
            bold, blink = fg > 7, bg > 7
            fg, bg = fg & 7, bg & 7
            at = []
            if (cur_bold and not bold) or (cur_blink and not blink):
                at.append("0")
                cur_fg, cur_bg, cur_bold, cur_blink = 7, 0, False, False
            if bold and not cur_bold:
                at.append("1"); cur_bold = True
            if blink and not cur_blink:
                at.append("5"); cur_blink = True
            if fg != cur_fg:
                at.append(str(30 + _ANSI_TO_DOS[fg])); cur_fg = fg
            if bg != cur_bg:
                at.append(str(40 + _ANSI_TO_DOS[bg])); cur_bg = bg
            if at:
                out += b"\x1b[" + ";".join(at).encode() + b"m"
            out.append(code)
        rec = _sauce_record(1, 1, COLS, ROWS, title)
    else:
        out = bytearray(lump_bytes)
        rec = _sauce_record(5, 0, COLS, ROWS, title)
    rec[90:94] = struct.pack("<I", len(out))
    return bytes(out) + b"\x1a" + bytes(rec)


def _safe_part(name):
    import re
    stem = os.path.splitext(name)[0]
    return re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")


def moebius_export(path, lump_bytes, layers, res, with_layers, title=""):
    """Write the flattened screen and (optionally) one file per visible layer.
    -> list of written paths."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".bin", ".ans"):
        path, ext = path + ".bin", ".bin"
    written = []
    with open(path, "wb") as f:
        f.write(encode_moebius(lump_bytes, ext, title))
    written.append(path)
    if with_layers and res is not None:
        base = os.path.splitext(path)[0]
        used = set()
        for i, L in enumerate(layers):
            if i not in res["solo"]:
                continue
            claim, c, fg, bg, k = res["solo"][i]
            key = KEY_INDEX.get(L.s["key"], 0) if L.kind == "cells" else 0
            data = build_lump(np.where(claim, c, 32), np.where(claim, fg, 7),
                              np.where(claim, bg, key), np.where(claim, k, False))
            part = _safe_part(L.name) or f"layer{i + 1}"
            name, n = part, 2
            while name.lower() in used:
                name, n = f"{part}_{n}", n + 1
            used.add(name.lower())
            lp = f"{base}_{name}{ext}"
            with open(lp, "wb") as f:
                f.write(encode_moebius(data, ext, f"{title} {L.name}".strip()))
            written.append(lp)
    return written


class Layer:
    """One image, its placement and settings, converted on its own."""
    _next_id = 0
    kind = "image"

    def __init__(self, img=None, path=None, name=None, settings=None):
        Layer._next_id += 1
        self.id = Layer._next_id
        self.path = path
        self.name = name or (os.path.basename(path) if path else f"layer {self.id}")
        self.s = dict(DEFAULT_LAYER)
        if settings:
            self.s.update(settings)
        self.visible = True
        self._grid = self._adj = self._res = self._native = (None, None)
        if img is not None:
            self.orig_w, self.orig_h = img.size
            self.src = prepare_source(img)
            self.src_pm = self.src.convert("RGBa")
            self.work_ratio = self.src.width / self.orig_w

    def clone(self):
        c = Layer()
        for a in ("orig_w", "orig_h", "src", "src_pm", "work_ratio", "path", "visible"):
            setattr(c, a, getattr(self, a))
        c.name = self.name + " copy"
        c.s = dict(self.s)
        return c

    # placement: x, y = screen px of the image's top-left; scale_x / scale_y =
    # % of original image pixels (100 = one image pixel per screen pixel)
    def screen_scale(self):
        return self.s["scale_x"] / 100.0, self.s["scale_y"] / 100.0

    def _pkey(self):
        return (self.s["x"], self.s["y"], self.s["scale_x"], self.s["scale_y"])

    def bounds(self, font=None):
        sx, sy = self.screen_scale()
        return (self.s["x"], self.s["y"], self.s["x"] + self.orig_w * sx, self.s["y"] + self.orig_h * sy)

    def fit(self, mode, font, snap):
        SW, SH = screen_size(font)
        _, fw, fh = get_font(font)
        if mode == "cover":
            sc = math.ceil(max(SW / self.orig_w, SH / self.orig_h) * 1000) / 1000
        elif mode == "contain":
            sc = math.floor(min(SW / self.orig_w, SH / self.orig_h) * 1000) / 1000
        else:
            sc = 1.0
        lo, hi = SLIDERS["scale_x"][1], SLIDERS["scale_x"][2]
        v = min(hi, max(lo, round(sc * 100, 2)))
        self.s["scale_x"] = self.s["scale_y"] = v
        sc = v / 100.0
        x = (SW - self.orig_w * sc) / 2
        y = (SH - self.orig_h * sc) / 2
        if snap and mode != "cover":            # snapping a cover fit could open a gap
            x, y = round(x / fw) * fw, round(y / fh) * fh
        self.s["x"], self.s["y"] = float(round(x)), float(round(y))

    def _box(self, font):
        SW, SH = screen_size(font)
        sx, sy = self.screen_scale()
        sx, sy = sx / self.work_ratio, sy / self.work_ratio   # screen px per working-image px
        x, y = self.s["x"], self.s["y"]
        # working-image coords of the screen rectangle
        return ((0 - x) / sx, (0 - y) / sy, (SW - x) / sx, (SH - y) / sy)

    def grid(self, font):
        """(colour[50,160,3] straight float, alpha[50,160] 0..1) on the screen grid"""
        key = (self.id,) + self._pkey() + (font,)
        if self._grid[0] != key:
            im = crop_resample_pm(self.src_pm, self._box(font), (GRID_W, GRID_H), Image.Resampling.BOX)
            a = np.asarray(im, dtype=np.float32)
            alpha = a[..., 3] / 255.0
            with np.errstate(divide="ignore", invalid="ignore"):
                col = np.where(alpha[..., None] > 0, a[..., :3] / np.maximum(alpha[..., None], 1e-6), 0.0)
            self._grid = (key, (np.clip(col, 0, 255).astype(np.float32), alpha))
        return self._grid[1]

    def adjusted(self, font):
        col, alpha = self.grid(font)
        key = (self._grid[0],) + tuple(self.s[k] for k in ADJUST_KEYS)
        if self._adj[0] != key:
            self._adj = (key, adjust(col, self.s))
        return self._adj[1], alpha

    def native(self, font):
        """premultiplied RGBa image at screen size, for the true-colour views"""
        key = (self.id,) + self._pkey() + (font,)
        if self._native[0] != key:
            self._native = (key, crop_resample_pm(self.src_pm, self._box(font), screen_size(font),
                                                  Image.Resampling.LANCZOS))
        return self._native[1]

    def solve(self, font, below_q):
        """-> (claim[25,80], chars, fg, bg). below_q[25,80,4,3]: what the
        stack below shows, used as the target for transparent parts of this
        layer's cells when Edge fill is on."""
        adj, alpha = self.adjusted(font)
        conv = tuple(self.s[k] for k in ("glyphs", "metric", "shade_penalty", "dither", "coverage", "edge_fill"))
        bkey = hash(below_q.tobytes()) if self.s["edge_fill"] else None
        key = (self._adj[0], font, conv, bkey)
        if self._res[0] != key:
            cc = to_cells(adj)
            ca = to_cells(alpha[..., None])[..., 0]           # [25,80,4]
            cov = ca.mean(-1)
            claim = (cov > 0) & (cov * 100.0 >= self.s["coverage"] - 1e-6)
            if self.s["edge_fill"]:
                target = cc * ca[..., None] + below_q * (1.0 - ca[..., None])
                weight = np.ones_like(ca)
            else:
                target = cc
                weight = ca
            chars, fg, bg = solve_cells(target.astype(np.float32), weight.astype(np.float32), claim, font, self.s)
            self._res = (key, (claim, chars, fg, bg, np.zeros((ROWS, COLS), bool)))
        return self._res[1]

    def opaque_at(self, font, sx, sy):
        """Is the layer's pixel at screen point (sx, sy) non-transparent?"""
        x0, y0, x1, y1 = self.bounds()
        if not (x0 <= sx < x1 and y0 <= sy < y1):
            return False
        kx, ky = self.screen_scale()
        px = int((sx - self.s["x"]) / (kx / self.work_ratio))
        py = int((sy - self.s["y"]) / (ky / self.work_ratio))
        px = min(max(px, 0), self.src.width - 1)
        py = min(max(py, 0), self.src.height - 1)
        return self.src.getpixel((px, py))[3] > 0


class CellLayer:
    """A Moebius file (or ENDOOM lump) used as a layer: its cells go straight
    into the stack. One background colour (setting 'key') is see-through."""
    kind = "cells"

    def __init__(self, doc=None, path=None, name=None, settings=None):
        Layer._next_id += 1
        self.id = Layer._next_id
        self.doc = doc
        self.path = path
        self.name = name or (os.path.basename(path) if path else f"cells {self.id}")
        self.s = dict(DEFAULT_LAYER)
        if settings:
            self.s.update(settings)
        self.visible = True
        self._res = self._native = (None, None)

    def clone(self):
        c = CellLayer(self.doc, self.path, self.name + " copy", dict(self.s))
        c.visible = self.visible
        return c

    def bounds(self, font):
        _, fw, fh = get_font(font)
        c, r = self.s["col"], self.s["row"]
        return (c * fw, r * fh, (c + self.doc.columns) * fw, (r + self.doc.rows) * fh)

    def fit(self, mode, font, snap):
        self.s["col"] = float((COLS - self.doc.columns) // 2) if self.doc.columns < COLS else 0.0
        self.s["row"] = float((ROWS - self.doc.rows) // 2) if self.doc.rows < ROWS else 0.0

    def solve(self, font, below_q):
        key = (int(self.s["col"]), int(self.s["row"]), self.s["key"])
        if self._res[0] != key:
            col, row = key[0], key[1]
            d = self.doc
            chars = np.full((ROWS, COLS), 32, np.uint8)
            fg = np.full((ROWS, COLS), 7, np.uint8)
            bg = np.zeros((ROWS, COLS), np.uint8)
            blink = np.zeros((ROWS, COLS), bool)
            claim = np.zeros((ROWS, COLS), bool)
            sy0, sx0 = max(0, -row), max(0, -col)
            dy0, dx0 = max(0, row), max(0, col)
            h = min(d.rows - sy0, ROWS - dy0)
            w = min(d.columns - sx0, COLS - dx0)
            if h > 0 and w > 0:
                src = (slice(sy0, sy0 + h), slice(sx0, sx0 + w))
                dst = (slice(dy0, dy0 + h), slice(dx0, dx0 + w))
                chars[dst], fg[dst], bg[dst], blink[dst] = d.chars[src], d.fg[src], d.bg[src], d.blink[src]
                claim[dst] = True
            if self.s["key"] != "off":
                ki = KEY_INDEX[self.s["key"]]
                see = (np.isin(chars, (0, 32, 255)) & (bg == ki)) | ((chars == 219) & (fg == ki))
                claim &= ~see
            self._res = (key, (claim, chars, fg, bg, blink))
        return self._res[1]

    def native(self, font):
        claim, c, f, b, _ = self.solve(font, None)
        key = (self._res[0], font)
        if self._native[0] != key:
            _, fw, fh = get_font(font)
            img = render(c, f, b, font).convert("RGBA")
            a = (claim.astype(np.uint8) * 255).repeat(fh, 0).repeat(fw, 1)
            img.putalpha(Image.fromarray(a, "L"))
            self._native = (key, img.convert("RGBa"))
        return self._native[1]

    def opaque_at(self, font, sx, sy):
        _, fw, fh = get_font(font)
        cx, cy = int(sx // fw), int(sy // fh)
        if not (0 <= cx < COLS and 0 <= cy < ROWS):
            return False
        return bool(self.solve(font, None)[0][cy, cx])


def load_layer_file(path, settings=None, name=None):
    """Image -> Layer, anything textmode -> CellLayer. Raises ValueError/OSError."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in MOEBIUS_EXTS:
        try:
            img = Image.open(path)
            img.load()
            return Layer(img, path, name, settings)
        except (OSError, ValueError, Image.UnidentifiedImageError):
            if ext in IMAGE_EXTS:
                raise ValueError("can't read that image")
    return CellLayer(load_textmode(path), path, name, settings)


def compose(layers, g):
    """Convert every visible layer and stack the cells, bottom to top.
    -> dict(chars, fg, bg, owner[25,80] (-1 = empty), solo{layer index: result})"""
    font = g["font"]
    empty_bg = nearest_bg(g["alpha_bg"])
    chars = np.full((ROWS, COLS), 32, np.uint8)
    fg = np.full((ROWS, COLS), 7, np.uint8)
    bg = np.full((ROWS, COLS), empty_bg, np.uint8)
    blink = np.zeros((ROWS, COLS), bool)
    owner = np.full((ROWS, COLS), -1, np.int32)
    solo = {}
    for i, L in enumerate(layers):
        if not L.visible:
            continue
        below = quad_colours(chars, fg, bg, font)
        claim, c, f, b, k = L.solve(font, below)
        solo[i] = (claim, c, f, b, k)
        chars = np.where(claim, c, chars)
        fg = np.where(claim, f, fg)
        bg = np.where(claim, b, bg)
        blink = np.where(claim, k, blink)
        owner[claim] = i
    return {"chars": chars, "fg": fg, "bg": bg, "blink": blink, "owner": owner, "solo": solo,
            "empty_bg": empty_bg}


def composite_original(layers, g):
    """True-colour composite of the visible layers over the screen colour."""
    size = screen_size(g["font"])
    base = Image.new("RGBA", size, g["alpha_bg"])
    for L in layers:
        if L.visible:
            base.alpha_composite(L.native(g["font"]).convert("RGBA"))
    return base.convert("RGB")


OWNER_TINTS = [(255, 70, 70), (70, 180, 255), (90, 255, 90), (255, 220, 50),
               (220, 100, 255), (255, 150, 40), (40, 255, 220), (255, 120, 190)]


def ownership_view(endoom_img, owner, font):
    _, fw, fh = get_font(font)
    img = np.asarray(endoom_img, np.float32)
    tint = np.zeros((ROWS, COLS, 3), np.float32)
    amt = np.zeros((ROWS, COLS, 1), np.float32)
    for i in np.unique(owner):
        m = owner == i
        if i < 0:
            amt[m] = -1
        else:
            tint[m] = OWNER_TINTS[i % len(OWNER_TINTS)]
            amt[m] = 0.5
    tint = tint.repeat(fh, 0).repeat(fw, 1)
    amt = amt.repeat(fh, 0).repeat(fw, 1)
    out = np.where(amt < 0, img * 0.25, img * (1 - amt) + tint * amt)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


# ---- projects ----

def save_project(path, layers, g):
    pdir = os.path.dirname(os.path.abspath(path))
    out = {PROJECT_MARKER: 1, "version": VERSION, "note": "layers are listed bottom to top",
           "global": {k: g[k] for k in ("font", "alpha_bg")}, "layers": []}
    for L in layers:
        entry = {"name": L.name, "type": "moebius" if L.kind == "cells" else "image",
                 "visible": L.visible, "settings": dict(L.s)}
        if L.path:
            ap = os.path.abspath(L.path)
            entry["path"] = ap
            try:
                entry["relpath"] = os.path.relpath(ap, pdir)
            except ValueError:                       # different drive on Windows
                pass
        out["layers"].append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


def load_project(path):
    """-> (global settings dict, [Layer], [warnings]). Raises ValueError."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get(PROJECT_MARKER) != 1 or not isinstance(data.get("layers"), list):
        raise ValueError("not a png2endoom project file")
    g = validate_settings(data.get("global", {}), ("font", "alpha_bg"))
    pdir = os.path.dirname(os.path.abspath(path))
    layers, warns = [], []
    for n, e in enumerate(data["layers"], 1):
        if not isinstance(e, dict):
            continue
        cands = []
        if isinstance(e.get("path"), str):
            cands.append(e["path"])
        if isinstance(e.get("relpath"), str):
            cands.append(os.path.join(pdir, e["relpath"]))
        name = e.get("name") if isinstance(e.get("name"), str) else None
        raw = dict(e.get("settings", {})) if isinstance(e.get("settings"), dict) else {}
        old = raw.get("scale")
        if isinstance(old, (int, float)) and not isinstance(old, bool):      # pre-1.3 projects
            raw.setdefault("scale_x", old)
            raw.setdefault("scale_y", old)
        settings = validate_settings(raw, DEFAULT_LAYER.keys())
        L, err = None, "not found"
        for c in cands:
            if os.path.isfile(c):
                try:
                    L = load_layer_file(c, settings, name)
                    break
                except Exception as ex:
                    err = str(ex)
        if L is None:
            warns.append(f"layer {n} ({name or '?'}): {err}: {cands[0] if cands else '(no path)'}")
            continue
        if L.kind == "cells":
            warns += [f"layer {n} ({L.name}): {w}" for w in L.doc.warnings]
        L.visible = e.get("visible", True) is not False
        layers.append(L)
    return g, layers, warns


# ---------------------------------------------------------------------------
# Headless CLI
# ---------------------------------------------------------------------------

def run_headless(opts):
    g = dict(DEFAULT_GLOBAL)
    src = opts["input"]
    if is_project_file(src):
        if opts.get("preset"):
            print(f"[{TOOL}] -p/--preset only applies to a single image; a project keeps its own layer settings")
            return 2
        try:
            pg, layers, warns = load_project(src)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[{TOOL}] project error: {e}")
            return 1
        for w in warns:
            print(f"[{TOOL}] warning: {w}")
        if not layers:
            print(f"[{TOOL}] project has no usable layers")
            return 1
        g.update(pg)
        if opts.get("font"):
            g["font"] = opts["font"]
    else:
        settings = {}
        if opts.get("preset"):
            try:
                settings = load_preset_file(opts["preset"])
            except (OSError, ValueError, json.JSONDecodeError) as e:
                print(f"[{TOOL}] preset error: {e}")
                return 1
        if opts.get("font"):
            g["font"] = opts["font"]
        try:
            L = load_layer_file(src, settings)
        except Exception as e:
            print(f"[{TOOL}] can't read '{src}': {e}")
            return 1
        if L.kind == "cells":
            L.s["key"] = "off"                 # a whole file converts as-is
            for w in L.doc.warnings:
                print(f"[{TOOL}] note: {w}")
        else:
            L.fit("cover", g["font"], False)
        layers = [L]
    t0 = time.perf_counter()
    res = compose(layers, g)
    data = build_lump(res["chars"], res["fg"], res["bg"], res["blink"])
    moeb = []
    try:
        if opts.get("output"):
            with open(opts["output"], "wb") as f:
                f.write(data)
        if opts.get("preview"):
            render(res["chars"], res["fg"], res["bg"], g["font"]).save(opts["preview"])
        if opts.get("moebius"):
            title = os.path.splitext(os.path.basename(src))[0]
            moeb = moebius_export(opts["moebius"], data, layers, res, not opts.get("no_layer_files"), title)
    except OSError as e:
        print(f"[{TOOL}] write failed: {e}")
        return 1
    ms = (time.perf_counter() - t0) * 1000
    nvis = sum(1 for L in layers if L.visible)
    if opts.get("output"):
        print(f"[{TOOL}] {os.path.basename(src)} -> {opts['output']} (4000 bytes, {nvis} layer(s), {ms:.0f} ms)")
    nb = int(res["blink"].sum())
    print(f"[{TOOL}] {glyph_stats(res['chars'])}" + (f"  |  {nb} blink cells" if nb else ""))
    if opts.get("preview"):
        print(f"[{TOOL}] preview -> {opts['preview']}")
    for m in moeb:
        print(f"[{TOOL}] moebius -> {m}")
    return 0


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

GUI_HELP = """png2endoom - controls

LAYERS
  The Layers button shows/hides the layer list. Each layer is one image
  (PNG alpha respected), converted ON ITS OWN with its own placement,
  adjustments and conversion settings into its own 80x25 cells. The finished
  cells are then stacked: in every cell, the topmost visible layer that
  covers it wins, using its character and colours as they are.
  Click a layer to select it - the Layer sections on the left show and edit
  that layer's settings, and they stay with the layer when you switch.
  Add... (several files at once is fine), Replace with file... (swap the
  selected layer's source, keeping its place and position), Remove, Up,
  Down, Duplicate.
  Untick a layer to hide it. Double-click a name to rename it.
  The first layer added fits with Cover; later ones at 1:1 if they fit on
  the screen, otherwise Contain.

PREVIEW (mouse)
  Drag inside the outline: move the selected layer (snaps to whole cells if
  Snap is ticked; hold Shift or Ctrl to ignore snapping).
  Drag a handle on the outline (image layers): an edge handle scales only
  that direction, the opposite edge stays put; a corner handle scales both
  directions freely, the opposite corner stays put. Shift keeps the aspect
  ratio you started with (on an edge handle the other direction follows,
  centred). With Snap ticked the dragged edge lands on a cell boundary;
  Ctrl ignores snapping. Handles show with "Show layer outline".
  Wheel: scale the selected layer around the pointer (width and height
  together, keeping their proportion).
  Alt+click: select the topmost layer with an opaque pixel under the
  pointer (if "Alt+click selects" is ticked).
  Arrow keys (click the preview first): nudge the selected layer one cell,
  or one pixel with Shift.

SCREEN (shared by every layer)
  Port font: draws the preview AND measures each glyph's real coverage for
  the solver. Hauge 8x18 = nyan / dsda (640x450 screen). VGA 8x16 =
  Chocolate Doom, DOSBox and most viewers (640x400). Layer positions are in
  screen pixels, so switching font keeps them but the screen gets taller or
  shorter - use the Fit buttons to refit.
  View: ENDOOM; Original (the layers composited in true colour);
  Original | ENDOOM; Solo (only the selected layer's own cells); Target (the
  selected layer's adjusted samples the solver aims at, each block one
  quarter of a cell); Ownership (tints each cell by the layer that won it,
  dims empty cells).
  Screen colour: behind everything. Cells no layer covers become a space on
  the nearest of the 8 background colours.
  Snap to cells / Alt+click selects / Show layer outline: each can be off.

LAYER: PLACEMENT
  Cover: fill the screen. Contain: whole image visible. 1:1: one image pixel
  per screen pixel (for art made at 640x450). Centre: centre without
  rescaling. X / Y: screen pixel of the image's top-left. Width % / Height
  %: scale as % of the image's own pixels - different values stretch it.
  Reset scale: back to 100% / 100% (true proportions, one image pixel per
  screen pixel), keeping the layer's centre where it is.
  Every section has its own Reset button; double-clicking a slider's name
  resets just that one.

LAYER: ADJUST  (before solving)
  Brightness, Contrast, Saturation: the 16-colour palette rewards punchy
  images - contrast and saturation are usually the first to raise.
  Gamma: above 1 lifts mid-tones, below 1 darkens them.
  Black point: darker than this becomes black, the rest is stretched.
  Keeps dark areas from turning into noisy dark grey / blue cells. 0 = off.

LAYER: CONVERSION
  Glyphs: which CP437 characters this layer may use - solid, top/bottom
  halves, left/right halves, and shades (25/50/75% fg/bg mixes).
  Shade penalty: extra cost for a shade, so solids win when the fit is about
  equal. Higher = cleaner and blockier, 0 = off.
  Dither %: error diffusion between this layer's cells. 0 = off (default).
  Metric: Weighted RGB (redmean) matches browns/skin better than plain RGB.
  Coverage %: how much of a cell must be opaque in this layer's image for
  the layer to claim that cell. 1 = any cell it touches, 100 = only fully
  covered cells.
  Edge fill: in this layer's edge cells, the transparent parts aim for what
  the layers below show there - so a moon's round edge becomes a clean
  half-block against the sky instead of a dark ring. Off = strict stamping
  (transparent parts are ignored by the solver).

MOEBIUS
  Add... and Replace with file... take Moebius files (.ans .bin .xb) and
  ENDOOM lumps as well as images. These become CELL layers: their cells go
  straight into the stack with no adjustment or conversion. Placement is in
  whole cells (Column / Row, drag and arrow keys move a cell at a time, no
  scaling; Centre works). Transparent: cells that show only that background
  colour (a blank on it, or a full block in it) are see-through. Default
  Black; Off makes every cell solid. Bigger than 80x25: move it to show
  another part.
  Export for Moebius...: writes the flattened screen as .bin (Binary Text,
  lossless, with a SAUCE record so Moebius knows it is 80 columns) or .ans,
  plus - if "also write each layer" is ticked - one file per visible layer
  named <file>_<layer>, holding only that layer's cells with the rest blank
  in its transparent colour (black for image layers). Re-add or Replace a
  layer with its edited file and it stacks exactly as before.
  On load: iCE bright backgrounds become the dark version; blink is kept
  (and counted in the status bar - nyan/dsda really blink it); XBin custom
  fonts/palettes and 24-bit ANSI colours are ignored.

FILES
  Open... (Ctrl+O): an image (replace the project, or add it as a layer),
  a project (.p2e), a Moebius file, a raw ENDOOM lump, or a WAD. Moebius
  files, lumps and WADs opened this way are only viewed as the finished
  screen - settings don't apply; Export writes them out as is.
  Save project... (Ctrl+S): layers, image paths, placement, all settings.
  Export... (Ctrl+E): the 4000-byte lump, plus <name>_preview.png at the
  font's native size if that box is ticked.
  Presets: one layer's adjust + conversion settings (no placement), applied
  to the selected layer. New layers start with the layer settings that were
  selected when you last closed the window.

OPTIONS PANEL
  The mouse wheel scrolls the panel anywhere over it; dropdowns, spinboxes
  and sliders don't change on the wheel. Double-click a slider's name to
  reset it.

LIMITS
  Background colours are 0-7 only and bit 7 (blink) is never set - nyan and
  dsda really do blink those cells.
"""


def run_gui(initial_path=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
    from PIL import ImageTk

    class SliderRow:
        def __init__(self, app, parent, row, key, kind):
            spec = SLIDERS[key]
            label, lo, hi, step = spec[:4]
            inc = spec[4] if len(spec) > 4 else step
            self.app, self.key, self.kind, self.lo, self.hi, self.step = app, key, kind, lo, hi, step
            self.fmt = "%.2f" if step < 0.1 else ("%.1f" if step < 1 else "%.0f")
            lab = ttk.Label(parent, text=label)
            lab.grid(row=row, column=0, sticky="w", pady=1)
            self.lab = lab
            dflt = (DEFAULT_GLOBAL if kind == "g" else DEFAULT_LAYER)[key]
            lab.bind("<Double-Button-1>", lambda e: self.set(dflt, notify=True))
            v = app.store(kind)[key]
            self.var = tk.DoubleVar(value=v)
            self.scale = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal",
                                   variable=self.var, command=self._from_scale)
            self.scale.grid(row=row, column=1, sticky="ew", padx=4)
            self.txt = tk.StringVar(value=self.fmt % v)
            self.spin = ttk.Spinbox(parent, from_=lo, to=hi, increment=inc, width=7,
                                    textvariable=self.txt, command=self._from_spin)
            self.spin.grid(row=row, column=2, sticky="e")
            self.spin.bind("<Return>", self._from_spin)
            self.spin.bind("<FocusOut>", self._from_spin)

        def _snap(self, v):
            v = round(v / self.step) * self.step
            return round(min(self.hi, max(self.lo, v)), 4)

        def _commit(self, v):
            d = self.app.store(self.kind)
            if v != d[self.key]:
                d[self.key] = v
                self.app.changed()

        def _from_scale(self, _=None):
            v = self._snap(self.var.get())
            self.txt.set(self.fmt % v)
            self._commit(v)

        def _from_spin(self, _=None):
            try:
                v = self._snap(float(self.txt.get()))
            except ValueError:
                v = self.app.store(self.kind)[self.key]
            self.var.set(v)
            self.txt.set(self.fmt % v)
            self._commit(v)

        def set(self, v, notify=False):
            v = self._snap(v)
            self.var.set(v)
            self.txt.set(self.fmt % v)
            self.app.store(self.kind)[self.key] = v
            if notify:
                self.app.changed()

        def sync(self):
            v = self.app.store(self.kind)[self.key]
            self.var.set(v)
            self.txt.set(self.fmt % v)

        def show(self, on):
            for w in (self.lab, self.scale, self.spin):
                w.grid() if on else w.grid_remove()

    class ChoiceRow:
        def __init__(self, app, parent, row, key, label, kind):
            self.app, self.key, self.kind = app, key, kind
            self.labels = {k: (v[0] if isinstance(v, tuple) else v) for k, v in CHOICES[key].items()}
            self.rev = {v: k for k, v in self.labels.items()}
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=1)
            self.var = tk.StringVar(value=self.labels[app.store(kind)[key]])
            cb = ttk.Combobox(parent, textvariable=self.var, state="readonly",
                              values=list(self.labels.values()), width=30)
            cb.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(4, 0))
            cb.bind("<<ComboboxSelected>>", self._picked)

        def _picked(self, _=None):
            v = self.rev[self.var.get()]
            d = self.app.store(self.kind)
            if v != d[self.key]:
                d[self.key] = v
                self.app.changed(choice=self.key)

        def sync(self):
            self.var.set(self.labels[self.app.store(self.kind)[self.key]])

    class CheckRow:
        def __init__(self, app, parent, key, label, kind, **grid):
            self.app, self.key, self.kind = app, key, kind
            self.var = tk.BooleanVar(value=app.store(kind)[key])
            ttk.Checkbutton(parent, text=label, variable=self.var, command=self._toggled).grid(**grid)

        def _toggled(self):
            self.app.store(self.kind)[self.key] = self.var.get()
            self.app.changed()

        def sync(self):
            self.var.set(self.app.store(self.kind)[self.key])

    class App:
        def __init__(self, root):
            self.root = root
            self.g = dict(DEFAULT_GLOBAL)
            self.layer_defaults = dict(DEFAULT_LAYER)
            self.meta = {}
            self.load_settings()
            self.layers = []            # bottom -> top
            self.sel = None
            self.mode = "project"       # project | lump
            self.lump = None
            self.lump_name = ""
            self.project_path = None
            self.preset_name = None
            self.native = None
            self.native_layout = None   # (pane width, pane height, panes)
            self.photo = None
            self._pending = None
            self._redisplay_pending = None
            self._drag = None
            self.disp = (1.0, 0, 0)     # scale, image left, image top (canvas px)
            self.result = None
            self.build_ui()
            self.update_title()
            geo = self.meta.get("geometry")
            try:
                root.geometry(geo if isinstance(geo, str) else "1400x860")
            except tk.TclError:
                pass
            if self.meta.get("zoomed"):
                try:
                    root.state("zoomed")
                except tk.TclError:
                    pass
            if self.meta.get("layers_open", True):
                self.toggle_layers(force=True)
            root.protocol("WM_DELETE_WINDOW", self.on_close)
            root.bind("<Control-o>", lambda e: self.open_file())
            root.bind("<Control-e>", lambda e: self.export())
            root.bind("<Control-s>", lambda e: self.save_project_dialog())

        # ---- data access ----
        def store(self, kind):
            if kind == "g":
                return self.g
            return self.layers[self.sel].s if self.sel is not None else self.layer_defaults

        def cur(self):
            return self.layers[self.sel] if self.sel is not None else None

        # ---- settings persistence ----
        def load_settings(self):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.g.update(validate_settings(data.get("global", {}), DEFAULT_GLOBAL.keys()))
                    ld = validate_settings(data.get("layer_defaults", {}), PRESET_KEYS)
                    self.layer_defaults.update(ld)
                    m = data.get("meta", {})
                    self.meta = m if isinstance(m, dict) else {}
            except (OSError, ValueError):
                pass

        def save_settings(self):
            try:
                self.meta["zoomed"] = self.root.state() == "zoomed"
                if not self.meta["zoomed"]:
                    self.meta["geometry"] = self.root.geometry()
                self.meta["layers_open"] = self.layers_open
                ld = self.cur().s if self.cur() else self.layer_defaults
                os.makedirs(APP_DIR, exist_ok=True)
                with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                    json.dump({"version": VERSION, "global": self.g,
                               "layer_defaults": {k: ld[k] for k in PRESET_KEYS},
                               "meta": self.meta}, f, indent=2)
                return None
            except OSError as e:
                return str(e)

        def on_close(self):
            err = self.save_settings()
            if err:
                messagebox.showwarning(TOOL, f"Couldn't save settings to\n{SETTINGS_PATH}\n\n{err}")
            self.root.destroy()

        # ---- UI ----
        def build_ui(self):
            root = self.root
            root.minsize(1000, 450)
            outer = ttk.Frame(root)
            outer.pack(fill="both", expand=True)
            self.outer = outer

            # options panel in a scrolling canvas (scrollbar only when needed)
            side = ttk.Frame(outer)
            side.pack(side="left", fill="y")
            panel_bg = ttk.Style().lookup("TFrame", "background") or root.cget("bg")
            self.pcanvas = tk.Canvas(side, highlightthickness=0, borderwidth=0, bg=panel_bg,
                                     yscrollincrement=20)
            self.pscroll = ttk.Scrollbar(side, orient="vertical", command=self.pcanvas.yview)
            self.pcanvas.configure(yscrollcommand=self.pscroll.set)
            self.pcanvas.pack(side="left", fill="y")
            panel = ttk.Frame(self.pcanvas, padding=(8, 6))
            self.panel = panel
            self.pcanvas.create_window(0, 0, window=panel, anchor="nw")
            panel.bind("<Configure>", lambda e: self.panel_layout())
            self.pcanvas.bind("<Configure>", lambda e: self.panel_layout())

            # layers dock (toggled)
            self.dock = ttk.Frame(outer, padding=(4, 6))
            self.layers_open = False
            self.build_dock()

            right = ttk.Frame(outer)
            right.pack(side="left", fill="both", expand=True)
            self.right = right

            r1 = ttk.Frame(panel)
            r1.pack(fill="x", pady=(0, 3))
            ttk.Button(r1, text="Open...", command=self.open_file).pack(side="left")
            ttk.Button(r1, text="Save project...", command=self.save_project_dialog).pack(side="left", padx=4)
            ttk.Button(r1, text="Export...", command=self.export).pack(side="left")
            r2 = ttk.Frame(panel)
            r2.pack(fill="x", pady=(0, 3))
            self.layers_btn = ttk.Button(r2, text="Layers >>", command=self.toggle_layers)
            self.layers_btn.pack(side="left")
            ttk.Button(r2, text="Export for Moebius...", command=self.export_moebius).pack(side="left", padx=4)
            ttk.Button(r2, text="Help", command=self.show_help).pack(side="right")
            self.prev_var = tk.BooleanVar(value=self.g["save_preview"])
            ttk.Checkbutton(panel, text="Export: also save preview PNG", variable=self.prev_var,
                            command=lambda: self.g.__setitem__("save_preview", self.prev_var.get())
                            ).pack(anchor="w")
            self.mlay_var = tk.BooleanVar(value=self.g["moebius_layers"])
            ttk.Checkbutton(panel, text="Moebius export: also write each layer", variable=self.mlay_var,
                            command=lambda: self.g.__setitem__("moebius_layers", self.mlay_var.get())
                            ).pack(anchor="w", pady=(0, 4))

            self.rows = []

            def section(title):
                lf = ttk.LabelFrame(panel, text=title, padding=(6, 3))
                lf.pack(fill="x", pady=3)
                lf.columnconfigure(0, minsize=100)
                lf.columnconfigure(1, weight=1, minsize=150)
                return lf

            f = section("Screen")
            self.rows.append(ChoiceRow(self, f, 0, "font", "Port font", "g"))
            self.rows.append(ChoiceRow(self, f, 1, "view", "View", "g"))
            ttk.Label(f, text="Screen colour").grid(row=2, column=0, sticky="w", pady=1)
            self.alpha_btn = tk.Button(f, width=6, relief="groove", command=self.pick_alpha,
                                       bg=self.g["alpha_bg"], activebackground=self.g["alpha_bg"])
            self.alpha_btn.grid(row=2, column=1, sticky="w", padx=4)
            self.rows.append(CheckRow(self, f, "snap", "Snap to cells", "g", row=3, column=0, columnspan=2, sticky="w"))
            self.rows.append(CheckRow(self, f, "alt_select", "Alt+click selects", "g", row=3, column=1, columnspan=2, sticky="e"))
            self.rows.append(CheckRow(self, f, "show_outline", "Show layer outline", "g", row=4, column=0, columnspan=2, sticky="w"))

            self.place_frame = f = section("Layer: placement")
            fb = ttk.Frame(f)
            fb.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 2))
            self.fit_btns = {}
            for txt, mode in (("Cover", "cover"), ("Contain", "contain"), ("1:1", "1:1"), ("Centre", "centre")):
                b = ttk.Button(fb, text=txt, width=8, command=lambda m=mode: self.fit_layer(m))
                b.pack(side="left", padx=(0, 3))
                self.fit_btns[mode] = b
            self.sliders = {}
            for i, k in enumerate(PLACEMENT_KEYS + ("col", "row"), 1):
                self.sliders[k] = SliderRow(self, f, i, k, "l")
                self.rows.append(self.sliders[k])
            self.reset_scale_btn = ttk.Button(f, text="Reset scale", command=self.reset_scale)
            self.reset_scale_btn.grid(row=10, column=0, columnspan=3, sticky="e", pady=(2, 0))

            self.moeb_frame = f = section("Layer: Moebius cells")
            self.rows.append(ChoiceRow(self, f, 0, "key", "Transparent", "l"))
            ttk.Button(f, text="Reset transparency", command=self.reset_key).grid(
                row=2, column=0, columnspan=3, sticky="e", pady=(2, 0))
            self.moeb_info = tk.StringVar(value="")
            ttk.Label(f, textvariable=self.moeb_info, foreground="#555555", wraplength=330,
                      justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

            self.adj_frame = f = section("Layer: adjust")
            for i, k in enumerate(ADJUST_KEYS):
                self.sliders[k] = SliderRow(self, f, i, k, "l")
                self.rows.append(self.sliders[k])
            ttk.Button(f, text="Reset adjustments", command=self.reset_adjust).grid(
                row=5, column=0, columnspan=3, sticky="e", pady=(2, 0))

            self.conv_frame = f = section("Layer: conversion")
            self.rows.append(ChoiceRow(self, f, 0, "glyphs", "Glyphs", "l"))
            for i, k in enumerate(("shade_penalty", "dither"), 1):
                self.sliders[k] = SliderRow(self, f, i, k, "l")
                self.rows.append(self.sliders[k])
            self.rows.append(ChoiceRow(self, f, 3, "metric", "Metric", "l"))
            self.sliders["coverage"] = SliderRow(self, f, 4, "coverage", "l")
            self.rows.append(self.sliders["coverage"])
            self.rows.append(CheckRow(self, f, "edge_fill", "Edge fill (transparent parts aim for the layers below)",
                                      "l", row=5, column=0, columnspan=3, sticky="w"))
            ttk.Button(f, text="Reset conversion", command=self.reset_conversion).grid(
                row=6, column=0, columnspan=3, sticky="e", pady=(2, 0))

            self.preset_frame = pf = ttk.Frame(panel)
            pf.pack(fill="x", pady=(6, 0))
            self.layer_frames = [self.place_frame, self.moeb_frame, self.adj_frame, self.conv_frame, pf]
            ttk.Button(pf, text="Load preset...", command=self.load_preset).pack(side="left")
            ttk.Button(pf, text="Save preset...", command=self.save_preset).pack(side="left", padx=4)
            ttk.Label(pf, text="(selected layer)").pack(side="left")

            self.canvas = tk.Canvas(right, bg="#202020", highlightthickness=0, cursor="fleur", takefocus=1)
            self.canvas.pack(fill="both", expand=True)
            self.status = tk.StringVar(value="Open an image (Ctrl+O) or add layers to start.")
            ttk.Label(right, textvariable=self.status, anchor="w", padding=(6, 3)).pack(fill="x")

            c = self.canvas
            c.bind("<Configure>", lambda e: self.schedule_redisplay())
            c.bind("<ButtonPress-1>", self.drag_start)
            c.bind("<B1-Motion>", self.drag_move)
            c.bind("<ButtonRelease-1>", lambda e: (setattr(self, "_drag", None), self.hover(e)))
            c.bind("<Motion>", self.hover)
            c.bind("<Alt-Button-1>", self.alt_click)
            for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
                c.bind(f"<{key}>", lambda e, dx=dx, dy=dy: self.nudge(dx, dy, False))
                c.bind(f"<Shift-{key}>", lambda e, dx=dx, dy=dy: self.nudge(dx, dy, True))

            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                root.bind_all(seq, self.wheel_router)
                for cls in ("TCombobox", "TSpinbox", "TScale"):
                    root.bind_class(cls, seq, self.wheel_router)
            self.update_layer_titles()
            self.apply_layer_kind()

        def build_dock(self):
            d = self.dock
            ttk.Label(d, text="Layers  (top first)", font=("Segoe UI", 9, "bold")).pack(anchor="w")
            btns = ttk.Frame(d)
            btns.pack(fill="x", pady=(3, 3))
            for txt, cmd in (("Add...", self.add_layers_dialog), ("Replace with file...", self.replace_layer_dialog),
                             ("Remove", self.remove_layer),
                             ("Up", lambda: self.move_layer(1)), ("Down", lambda: self.move_layer(-1)),
                             ("Duplicate", self.duplicate_layer)):
                ttk.Button(btns, text=txt, width=16, command=cmd).pack(fill="x", pady=1)
            self.list_frame = tk.Frame(d, bg="#ffffff", relief="sunken", bd=1)
            self.list_frame.pack(fill="both", expand=True, pady=(4, 0))

        def rebuild_layer_list(self):
            lf = self.list_frame
            for w in lf.winfo_children():
                w.destroy()
            if not self.layers:
                tk.Label(lf, text="(no layers)", bg="#ffffff", fg="#888888").pack(anchor="w", padx=4, pady=4)
                return
            for i in reversed(range(len(self.layers))):
                L = self.layers[i]
                sel = i == self.sel
                bg = "#cce4ff" if sel else "#ffffff"
                row = tk.Frame(lf, bg=bg)
                row.pack(fill="x")
                var = tk.BooleanVar(value=L.visible)
                cb = tk.Checkbutton(row, variable=var, bg=bg, activebackground=bg,
                                    command=lambda L=L, v=var: self.set_visible(L, v.get()))
                cb.pack(side="left")
                cb._var = var
                tint = OWNER_TINTS[i % len(OWNER_TINTS)]
                tk.Label(row, text="  ", bg="#%02x%02x%02x" % tint).pack(side="left", padx=(0, 4))
                name = L.name if len(L.name) <= 24 else L.name[:22] + "..."
                lab = tk.Label(row, text=name, bg=bg, anchor="w", width=20,
                               font=("Segoe UI", 9, "bold" if sel else "normal"))
                lab.pack(side="left", fill="x", expand=True)
                for w in (row, lab):
                    w.bind("<Button-1>", lambda e, i=i: self.select(i))
                    w.bind("<Double-Button-1>", lambda e, i=i: self.rename_layer(i))

        def panel_layout(self):
            pw, ph = self.panel.winfo_reqwidth(), self.panel.winfo_reqheight()
            self.pcanvas.configure(width=pw, scrollregion=(0, 0, pw, ph))
            if ph > self.pcanvas.winfo_height():
                if not self.pscroll.winfo_ismapped():
                    self.pscroll.pack(side="left", fill="y")
            else:
                if self.pscroll.winfo_ismapped():
                    self.pscroll.pack_forget()
                self.pcanvas.yview_moveto(0)

        @staticmethod
        def _inside(widget, container):
            p, c = str(widget), str(container)
            return p == c or p.startswith(c + ".")

        def wheel_router(self, e):
            w = self.root.winfo_containing(e.x_root, e.y_root)
            if w is None:
                return None
            if e.num == 4:
                d, steps = 1, 1
            elif e.num == 5:
                d, steps = -1, 1
            else:
                if not e.delta:
                    return "break"
                d = 1 if e.delta > 0 else -1
                steps = max(1, abs(e.delta) // 120)
            if self._inside(w, self.pcanvas):
                if self.pscroll.winfo_ismapped():
                    self.pcanvas.yview_scroll(-d * steps * 3, "units")
                return "break"
            if self._inside(w, self.canvas):
                cx = e.x_root - self.canvas.winfo_rootx()
                cy = e.y_root - self.canvas.winfo_rooty()
                self.wheel_scale(d, cx, cy)
                return "break"
            return None

        def toggle_layers(self, force=False):
            if self.layers_open and not force:
                self.dock.pack_forget()
                self.layers_open = False
                self.layers_btn.configure(text="Layers >>")
            else:
                self.dock.pack(side="left", fill="y", before=self.right)
                self.layers_open = True
                self.layers_btn.configure(text="<< Layers")
                self.rebuild_layer_list()

        def update_title(self):
            t = f"{TOOL} {VERSION}"
            if self.mode == "lump":
                t += f" - {self.lump_name}"
            elif self.project_path:
                t += f" - {os.path.basename(self.project_path)}"
            elif self.layers:
                t += f" - {self.layers[0].name}"
            if self.preset_name:
                t += f" [preset: {self.preset_name}]"
            self.root.title(t)

        def update_layer_titles(self):
            L = self.cur()
            nm = f" ({L.name})" if L else " (no layer - editing new-layer defaults)"
            if L is not None and L.kind == "cells":
                nm = " - cells" + nm
            nm = nm if len(nm) < 40 else nm[:37] + "...)"
            self.place_frame.configure(text="Layer: placement" + nm)
            self.adj_frame.configure(text="Layer: adjust")
            self.conv_frame.configure(text="Layer: conversion")

        def sync_widgets(self):
            for r in self.rows:
                r.sync()
            self.alpha_btn.configure(bg=self.g["alpha_bg"], activebackground=self.g["alpha_bg"])
            self.prev_var.set(self.g["save_preview"])
            self.mlay_var.set(self.g["moebius_layers"])
            self.update_layer_titles()
            self.apply_layer_kind()

        def apply_layer_kind(self):
            """Show the sections that apply to the selected layer's type."""
            L = self.cur()
            cells = L is not None and L.kind == "cells"
            for k in PLACEMENT_KEYS:
                self.sliders[k].show(not cells)
            for k in ("col", "row"):
                self.sliders[k].show(cells)
            for m in ("cover", "contain", "1:1"):
                self.fit_btns[m].state(["disabled"] if cells else ["!disabled"])
            self.reset_scale_btn.state(["disabled"] if cells else ["!disabled"])
            for fr in self.layer_frames:
                fr.pack_forget()
            want = [self.place_frame, self.moeb_frame] if cells else \
                   [self.place_frame, self.adj_frame, self.conv_frame, self.preset_frame]
            for fr in want:
                fr.pack(fill="x", pady=(6, 0) if fr is self.preset_frame else 3)
            if cells:
                d = L.doc
                note = f"{d.columns} x {d.rows} cells from the file. No adjustment or conversion - " \
                       "the cells are used as they are."
                if d.columns > COLS or d.rows > ROWS:
                    note += " Bigger than the screen: move it to show another part."
                if d.warnings:
                    note += "\nOn load: " + "; ".join(d.warnings)
                self.moeb_info.set(note)

        # ---- changes ----
        def changed(self, choice=None):
            if self._pending:
                self.root.after_cancel(self._pending)
            self._pending = self.root.after(30, self.refresh)

        def reset_adjust(self):
            for k in ADJUST_KEYS:
                self.sliders[k].set(DEFAULT_LAYER[k])
            self.changed()

        def reset_conversion(self):
            d = self.store("l")
            for k in CONVERSION_KEYS:
                d[k] = DEFAULT_LAYER[k]
            for r in self.rows:
                if getattr(r, "kind", None) == "l" and r.key in CONVERSION_KEYS:
                    r.sync()
            self.changed()

        def reset_key(self):
            self.store("l")["key"] = DEFAULT_LAYER["key"]
            for r in self.rows:
                if getattr(r, "key", None) == "key":
                    r.sync()
            self.changed()

        def reset_scale(self):
            L = self.cur()
            if L is None or L.kind == "cells":
                return
            x0, y0, x1, y1 = L.bounds()
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            self.sliders["scale_x"].set(100.0)
            self.sliders["scale_y"].set(100.0)
            self.sliders["x"].set(round(cx - L.orig_w / 2))
            self.sliders["y"].set(round(cy - L.orig_h / 2))
            self.changed()

        def pick_alpha(self):
            rgb, hx = colorchooser.askcolor(color=self.g["alpha_bg"], title="Screen colour")
            if hx:
                self.g["alpha_bg"] = hx.lower()
                self.alpha_btn.configure(bg=hx, activebackground=hx)
                self.changed()

        # ---- layers ----
        def select(self, i):
            self.sel = i if (i is not None and 0 <= i < len(self.layers)) else None
            self.sync_widgets()
            self.rebuild_layer_list()
            self.changed()

        def new_layer(self, path):
            L = load_layer_file(path, {k: self.layer_defaults[k] for k in PRESET_KEYS})
            if L.kind == "cells":
                return L
            font, snap = self.g["font"], self.g["snap"]
            if not self.layers:
                L.fit("cover", font, False)
            else:
                SW, SH = screen_size(font)
                L.fit("1:1" if (L.orig_w <= SW and L.orig_h <= SH) else "contain", font, snap)
            return L

        def add_image_paths(self, paths):
            errs, warns = [], []
            for p in paths:
                try:
                    L = self.new_layer(p)
                except Exception as e:
                    errs.append(f"{os.path.basename(p)}: {e}")
                    continue
                self.layers.append(L)
                if L.kind == "cells":
                    warns += [f"{L.name}: {w}" for w in L.doc.warnings]
            if errs:
                messagebox.showerror(TOOL, "Couldn't load:\n" + "\n".join(errs))
            if warns:
                messagebox.showwarning(TOOL, "Loaded with changes:\n\n" + "\n".join(warns))
            if self.layers:
                self.mode = "project"
                self.select(len(self.layers) - 1)
            self.update_title()

        def add_layers_dialog(self):
            paths = filedialog.askopenfilenames(
                title="Add image layer(s)", initialdir=self._dir("last_dir"),
                filetypes=[("Images and Moebius files",
                            "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp *.ans *.asc *.bin *.xb *.diz"),
                           ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp"),
                           ("Moebius / ANSI", "*.ans *.asc *.bin *.xb *.diz"), ("All files", "*")])
            if paths:
                self.meta["last_dir"] = os.path.dirname(os.path.abspath(paths[0]))
                if self.mode == "lump":
                    self.mode = "project"
                self.add_image_paths(list(paths))

        def replace_layer_dialog(self):
            old = self.cur()
            if old is None:
                messagebox.showinfo(TOOL, "Select a layer to replace first.")
                return
            path = filedialog.askopenfilename(
                title=f"Replace '{old.name}' with", initialdir=self._dir("last_dir"),
                filetypes=[("Images and Moebius files",
                            "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp *.ans *.asc *.bin *.xb *.diz"),
                           ("All files", "*")])
            if not path:
                return
            self.meta["last_dir"] = os.path.dirname(os.path.abspath(path))
            try:
                new = load_layer_file(path, dict(old.s))
            except Exception as e:
                messagebox.showerror(TOOL, f"Can't load {os.path.basename(path)}:\n{e}")
                return
            _, fw, fh = get_font(self.g["font"])
            if old.kind == "image" and new.kind == "cells":
                new.s["col"], new.s["row"] = float(round(old.s["x"] / fw)), float(round(old.s["y"] / fh))
            elif old.kind == "cells" and new.kind == "image":
                new.s["x"], new.s["y"] = old.s["col"] * fw, old.s["row"] * fh
                new.s["scale_x"] = new.s["scale_y"] = 100.0
            new.visible = old.visible
            self.layers[self.sel] = new
            if new.kind == "cells" and new.doc.warnings:
                messagebox.showwarning(TOOL, "Loaded with changes:\n\n" + "\n".join(new.doc.warnings))
            self.select(self.sel)

        def remove_layer(self):
            if self.sel is None:
                return
            del self.layers[self.sel]
            self.select(min(self.sel, len(self.layers) - 1) if self.layers else None)

        def move_layer(self, d):
            i = self.sel
            if i is None or not (0 <= i + d < len(self.layers)):
                return
            self.layers[i], self.layers[i + d] = self.layers[i + d], self.layers[i]
            self.select(i + d)

        def duplicate_layer(self):
            if self.sel is None:
                return
            self.layers.insert(self.sel + 1, self.layers[self.sel].clone())
            self.select(self.sel + 1)

        def set_visible(self, L, v):
            L.visible = v
            self.changed()

        def rename_layer(self, i):
            L = self.layers[i]
            nm = simpledialog.askstring(TOOL, "Layer name:", initialvalue=L.name, parent=self.root)
            if nm and nm.strip():
                L.name = nm.strip()
                self.rebuild_layer_list()
                self.update_layer_titles()

        def fit_layer(self, mode):
            L = self.cur()
            if not L:
                return
            if L.kind == "cells":
                L.fit("centre", self.g["font"], True)
                for k in ("col", "row"):
                    self.sliders[k].sync()
                self.changed()
                return
            if mode == "centre":
                SW, SH = screen_size(self.g["font"])
                _, fw, fh = get_font(self.g["font"])
                x0, y0, x1, y1 = L.bounds(self.g["font"])
                x, y = (SW - (x1 - x0)) / 2, (SH - (y1 - y0)) / 2
                if self.g["snap"]:
                    x, y = round(x / fw) * fw, round(y / fh) * fh
                L.s["x"], L.s["y"] = float(round(x)), float(round(y))
            else:
                L.fit(mode, self.g["font"], self.g["snap"])
            for k in PLACEMENT_KEYS:
                self.sliders[k].sync()
            self.changed()

        # ---- files ----
        def _dir(self, key):
            d = self.meta.get(key)
            return d if isinstance(d, str) and os.path.isdir(d) else None

        def open_file(self, path=None):
            if not path:
                path = filedialog.askopenfilename(
                    title="Open image, project, ENDOOM lump or WAD", initialdir=self._dir("last_dir"),
                    filetypes=[("All supported", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp *.p2e *.wad *.lmp "
                                                 "*.ans *.asc *.bin *.xb *.diz *"),
                               ("png2endoom project", "*.p2e"), ("Moebius / ANSI", "*.ans *.asc *.bin *.xb *.diz"),
                               ("All files", "*")])
                if not path:
                    return
            self.meta["last_dir"] = os.path.dirname(os.path.abspath(path))
            if is_project_file(path):
                self.open_project(path)
                return
            try:
                img = Image.open(path)
                img.load()
            except Exception:
                img = None
            if img is not None and os.path.splitext(path)[1].lower() not in MOEBIUS_EXTS:
                if self.mode == "project" and self.layers:
                    ans = messagebox.askyesnocancel(
                        TOOL, f"Replace the current layers with {os.path.basename(path)}?\n\n"
                              "Yes = replace (new project)\nNo = add it as a new layer on top")
                    if ans is None:
                        return
                    if ans:
                        self.layers, self.project_path = [], None
                else:
                    self.layers, self.project_path = [], None
                self.mode = "project"
                self.lump = None
                try:
                    self.layers.append(self.new_layer(path))
                except Exception as e:
                    messagebox.showerror(TOOL, f"Can't open {os.path.basename(path)}:\n{e}")
                    return
                self.select(len(self.layers) - 1)
                self.update_title()
                return
            try:
                doc = load_textmode(path)
            except (OSError, ValueError) as e:
                messagebox.showerror(TOOL, f"Can't open {os.path.basename(path)}:\n{e}")
                return
            warns = list(doc.warnings)
            if doc.columns > COLS or doc.rows > ROWS:
                warns.append(f"file is {doc.columns} x {doc.rows} cells - showing the top-left 80 x 25 "
                             "(add it as a layer to show another part)")
            if warns:
                messagebox.showwarning(TOOL, "Opened with changes:\n\n" + "\n".join(warns))
            self.mode = "lump"
            self.lump = build_lump(*doc_to_screen(doc))
            ext = os.path.splitext(path)[1].lower()
            self.lump_name = os.path.basename(path) if ext in MOEBIUS_EXTS else \
                (read_endoom_file(path)[1] if (os.path.getsize(path) == 4000 or ext == ".wad") else os.path.basename(path))
            self.update_title()
            self.refresh()

        def open_project(self, path):
            try:
                pg, layers, warns = load_project(path)
            except (OSError, ValueError, json.JSONDecodeError) as e:
                messagebox.showerror(TOOL, f"Can't open project:\n{e}")
                return
            if warns:
                messagebox.showwarning(TOOL, "Some layers couldn't be loaded:\n\n" + "\n".join(warns))
            self.g.update(pg)
            self.layers = layers
            self.project_path = path
            self.mode = "project"
            self.lump = None
            self.sel = len(layers) - 1 if layers else None
            self.sync_widgets()
            self.rebuild_layer_list()
            self.update_title()
            self.refresh()

        def save_project_dialog(self):
            if not self.layers:
                messagebox.showinfo(TOOL, "No layers to save yet.")
                return
            path = filedialog.asksaveasfilename(
                title="Save project", initialdir=self._dir("project_dir") or self._dir("last_dir"),
                initialfile=os.path.basename(self.project_path) if self.project_path else "endoom" + PROJECT_EXT,
                defaultextension=PROJECT_EXT, filetypes=[("png2endoom project", "*" + PROJECT_EXT)])
            if not path:
                return
            self.meta["project_dir"] = os.path.dirname(os.path.abspath(path))
            try:
                save_project(path, self.layers, self.g)
                self.project_path = path
                self.update_title()
                self.status.set(f"Saved project {os.path.basename(path)}")
            except OSError as e:
                messagebox.showerror(TOOL, f"Couldn't save project:\n{e}")

        def export(self):
            if self.mode == "project" and not self.layers:
                messagebox.showinfo(TOOL, "Nothing to export yet - open an image or add layers first.")
                return
            path = filedialog.asksaveasfilename(
                title="Export ENDOOM lump", initialdir=self._dir("export_dir") or self._dir("last_dir"),
                initialfile="ENDOOM", filetypes=[("Raw lump", "*"), ("Lump", "*.lmp")])
            if not path:
                return
            self.meta["export_dir"] = os.path.dirname(os.path.abspath(path))
            chars, fg, bg, data = self.current_cells()
            try:
                with open(path, "wb") as f:
                    f.write(data)
                msg = f"Wrote {os.path.basename(path)} (4000 bytes)"
                if self.g["save_preview"]:
                    pp = os.path.splitext(path)[0] + "_preview.png"
                    render(chars, fg, bg, self.g["font"]).save(pp)
                    msg += f" + {os.path.basename(pp)}"
                self.status.set(msg)
            except OSError as e:
                messagebox.showerror(TOOL, f"Export failed:\n{e}")

        def export_moebius(self):
            if self.mode == "project" and not self.layers:
                messagebox.showinfo(TOOL, "Nothing to export yet - open an image or add layers first.")
                return
            stem = os.path.splitext(os.path.basename(self.project_path))[0] if self.project_path else "endoom"
            path = filedialog.asksaveasfilename(
                title="Export for Moebius", initialdir=self._dir("moebius_dir") or self._dir("export_dir"),
                initialfile=stem + ".bin", defaultextension=".bin",
                filetypes=[("Moebius Binary Text (lossless)", "*.bin"), ("Moebius ANSI", "*.ans")])
            if not path:
                return
            self.meta["moebius_dir"] = os.path.dirname(os.path.abspath(path))
            chars, fg, bg, data = self.current_cells()
            res = self.result if self.mode == "project" else None
            title = os.path.splitext(os.path.basename(path))[0]
            try:
                written = moebius_export(path, data, self.layers if res else [], res,
                                         self.g["moebius_layers"], title)
            except OSError as e:
                messagebox.showerror(TOOL, f"Moebius export failed:\n{e}")
                return
            extra = f" + {len(written) - 1} layer file(s)" if len(written) > 1 else ""
            self.status.set(f"Wrote {os.path.basename(written[0])}{extra}")

        def save_preset(self):
            os.makedirs(PRESET_DIR, exist_ok=True)
            path = filedialog.asksaveasfilename(
                title="Save preset (selected layer)", initialdir=self._dir("preset_dir") or PRESET_DIR,
                defaultextension=".json", filetypes=[("png2endoom preset", "*.json")])
            if not path:
                return
            self.meta["preset_dir"] = os.path.dirname(os.path.abspath(path))
            try:
                save_preset_file(path, self.store("l"))
                self.preset_name = os.path.splitext(os.path.basename(path))[0]
                self.update_title()
            except OSError as e:
                messagebox.showerror(TOOL, f"Couldn't save preset:\n{e}")

        def load_preset(self):
            os.makedirs(PRESET_DIR, exist_ok=True)
            path = filedialog.askopenfilename(
                title="Load preset into selected layer", initialdir=self._dir("preset_dir") or PRESET_DIR,
                filetypes=[("png2endoom preset", "*.json"), ("All files", "*")])
            if not path:
                return
            self.meta["preset_dir"] = os.path.dirname(os.path.abspath(path))
            try:
                vals = load_preset_file(path)
            except (OSError, ValueError, json.JSONDecodeError) as e:
                messagebox.showerror(TOOL, f"Can't load preset:\n{e}")
                return
            self.store("l").update(vals)
            self.sync_widgets()
            self.preset_name = os.path.splitext(os.path.basename(path))[0]
            self.update_title()
            self.refresh()

        def show_help(self):
            top = tk.Toplevel(self.root)
            top.title(f"{TOOL} help")
            top.geometry("760x680")
            txt = tk.Text(top, wrap="word", font=("Consolas", 10), padx=10, pady=8)
            sb = ttk.Scrollbar(top, command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", GUI_HELP)
            txt.configure(state="disabled")

        # ---- conversion / display ----
        def current_cells(self):
            if self.mode == "lump":
                chars, fg, bg, _ = parse_lump(self.lump)
                return chars, fg, bg, self.lump
            res = compose(self.layers, self.g)
            self.result = res
            return res["chars"], res["fg"], res["bg"], build_lump(res["chars"], res["fg"], res["bg"], res["blink"])

        def refresh(self):
            self._pending = None
            font = self.g["font"]
            t0 = time.perf_counter()
            try:
                if self.mode == "lump":
                    chars, fg, bg, blink = parse_lump(self.lump)
                    self.native = render(chars, fg, bg, font)
                    self.native_layout = (self.native.width, self.native.height, 1)
                    note = f"  |  {blink} blink cells" if blink else ""
                    stat = f"Viewing lump (settings don't apply){note}  |  {glyph_stats(chars)}"
                elif not self.layers:
                    self.native = None
                    self.redisplay()
                    self.status.set("Open an image (Ctrl+O) or add layers to start.")
                    return
                else:
                    g = self.g
                    res = compose(self.layers, g)
                    self.result = res
                    endoom = render(res["chars"], res["fg"], res["bg"], font)
                    SW, SH = endoom.size
                    view = g["view"]
                    L = self.cur()
                    panes = 1
                    if view == "endoom":
                        self.native = endoom
                    elif view == "original":
                        self.native = composite_original(self.layers, g)
                    elif view == "split":
                        orig = composite_original(self.layers, g)
                        both = Image.new("RGB", (SW * 2 + 8, SH), (32, 32, 32))
                        both.paste(orig, (0, 0))
                        both.paste(endoom, (SW + 8, 0))
                        self.native = both
                        panes = 2
                    elif view == "solo":
                        e = res["empty_bg"]
                        c = np.full((ROWS, COLS), 32, np.uint8)
                        f = np.full((ROWS, COLS), 7, np.uint8)
                        b = np.full((ROWS, COLS), e, np.uint8)
                        if self.sel is not None and self.sel in res["solo"]:
                            claim, sc, sf, sb, _ = res["solo"][self.sel]
                            c, f, b = np.where(claim, sc, c), np.where(claim, sf, f), np.where(claim, sb, b)
                        self.native = render(c, f, b, font)
                    elif view == "target":
                        if L is not None and L.kind == "cells":
                            self.native = composite_original([L], g)
                        elif L is not None:
                            adj, alpha = L.adjusted(font)
                            bgc = np.array(hex_rgb(g["alpha_bg"]), np.float32)
                            t = adj * alpha[..., None] + bgc * (1 - alpha[..., None])
                            self.native = Image.fromarray(t.round().astype(np.uint8), "RGB").resize(
                                (SW, SH), Image.Resampling.NEAREST)
                        else:
                            self.native = Image.new("RGB", (SW, SH), g["alpha_bg"])
                    else:
                        self.native = ownership_view(endoom, res["owner"], font)
                    self.native_layout = (SW, SH, panes)
                    stat = glyph_stats(res["chars"])
                    nb = int(res["blink"].sum())
                    if nb:
                        stat += f"  |  {nb} blink cells"
                    if L is not None:
                        hidden = "" if L.visible else " (hidden)"
                        stat += f"  |  layer: {L.name}{hidden}"
            except Exception as e:  # keep the GUI alive on unexpected input
                self.native = None
                self.status.set(f"Error: {e}")
                self.redisplay()
                return
            ms = (time.perf_counter() - t0) * 1000
            self.status.set(f"{stat}  |  {ms:.0f} ms")
            self.redisplay()

        def schedule_redisplay(self):
            if self._redisplay_pending:
                self.root.after_cancel(self._redisplay_pending)
            self._redisplay_pending = self.root.after(30, self.redisplay)

        def redisplay(self):
            self._redisplay_pending = None
            c = self.canvas
            c.delete("all")
            cw, ch = max(1, c.winfo_width()), max(1, c.winfo_height())
            if self.native is None:
                c.create_text(cw // 2, ch // 2, fill="#888888", font=("Segoe UI", 12),
                              text="Open an image, project, ENDOOM lump or WAD  (Ctrl+O)")
                return
            iw, ih = self.native.size
            sc = max(min((cw - 16) / iw, (ch - 16) / ih), 0.05)
            dw, dh = max(1, round(iw * sc)), max(1, round(ih * sc))
            rs = Image.Resampling.NEAREST if sc >= 1 else Image.Resampling.BOX
            self.photo = ImageTk.PhotoImage(self.native.resize((dw, dh), rs))
            left, top = cw // 2 - dw // 2, ch // 2 - dh // 2
            c.create_image(left, top, image=self.photo, anchor="nw")
            self.disp = (sc, left, top)
            L = self.cur()
            if (self.mode == "project" and L is not None and self.g["show_outline"]
                    and self.native_layout):
                SW, SH, panes = self.native_layout
                x0, y0, x1, y1 = L.bounds(self.g["font"])
                for p in range(panes):
                    ox = left + p * (SW + 8) * sc
                    c.create_rectangle(ox + x0 * sc, top + y0 * sc, ox + x1 * sc, top + y1 * sc,
                                       outline="#ffd400", dash=(4, 3))
                    if L.kind == "image":
                        for hx, hy in self.handle_points(L).values():
                            px, py = ox + hx * sc, top + hy * sc
                            c.create_rectangle(px - 4, py - 4, px + 4, py + 4, fill="#ffd400", outline="#000000")

        def canvas_to_screen(self, cx, cy):
            sc, left, top = self.disp
            x = (cx - left) / sc
            y = (cy - top) / sc
            if self.native_layout and self.native_layout[2] == 2:
                SW = self.native_layout[0]
                if x >= SW + 8:
                    x -= SW + 8
            return x, y

        HANDLE_CURSORS = {"nw": "top_left_corner", "ne": "top_right_corner",
                          "sw": "bottom_left_corner", "se": "bottom_right_corner",
                          "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                          "e": "sb_h_double_arrow", "w": "sb_h_double_arrow"}

        def handle_points(self, L):
            x0, y0, x1, y1 = L.bounds()
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            return {"nw": (x0, y0), "n": (mx, y0), "ne": (x1, y0), "e": (x1, my),
                    "se": (x1, y1), "s": (mx, y1), "sw": (x0, y1), "w": (x0, my)}

        def handle_at(self, cx, cy):
            L = self.cur()
            if (self.mode != "project" or L is None or L.kind != "image" or not self.g["show_outline"]
                    or self.native is None):
                return None
            sx, sy = self.canvas_to_screen(cx, cy)
            tol = 7 / self.disp[0]
            best = None
            for name, (hx, hy) in self.handle_points(L).items():
                d = max(abs(sx - hx), abs(sy - hy))
                if d <= tol and (best is None or d < best[0]):
                    best = (d, name)
            return best[1] if best else None

        def hover(self, e):
            if self._drag is not None:
                return
            h = self.handle_at(e.x, e.y)
            want = self.HANDLE_CURSORS[h] if h else "fleur"
            if self.canvas.cget("cursor") != want:
                self.canvas.configure(cursor=want)

        def drag_start(self, e):
            self.canvas.focus_set()
            L = self.cur()
            if self.mode != "project" or L is None:
                self._drag = None
                return
            h = self.handle_at(e.x, e.y)
            if h:
                self._drag = ("resize", h, L.bounds(), self.canvas_to_screen(e.x, e.y))
                return
            if L.kind == "cells":
                self._drag = (e.x, e.y, L.s["col"], L.s["row"])
            else:
                self._drag = (e.x, e.y, L.s["x"], L.s["y"])

        def drag_move(self, e):
            L = self.cur()
            if self._drag is None or L is None:
                return
            if self._drag[0] == "resize":
                self.resize_move(L, e)
                return
            sx, sy, x0, y0 = self._drag
            sc = self.disp[0]
            if L.kind == "cells":
                _, fw, fh = get_font(self.g["font"])
                self.sliders["col"].set(round(x0 + (e.x - sx) / sc / fw))
                self.sliders["row"].set(round(y0 + (e.y - sy) / sc / fh))
                self.changed()
                return
            x = x0 + (e.x - sx) / sc
            y = y0 + (e.y - sy) / sc
            if self.g["snap"] and not (e.state & 0x0005):     # Shift or Ctrl: free
                _, fw, fh = get_font(self.g["font"])
                x, y = round(x / fw) * fw, round(y / fh) * fh
            self.sliders["x"].set(round(x))
            self.sliders["y"].set(round(y))
            self.changed()

        def resize_move(self, L, e):
            _, h, (x0, y0, x1, y1), _start = self._drag
            px, py = self.canvas_to_screen(e.x, e.y)
            W0, H0 = x1 - x0, y1 - y0
            nx0, ny0, nx1, ny1 = x0, y0, x1, y1
            if "w" in h:
                nx0 = px
            if "e" in h:
                nx1 = px
            if "n" in h:
                ny0 = py
            if "s" in h:
                ny1 = py
            if self.g["snap"] and not (e.state & 0x0004):            # Ctrl: free
                _, fw, fh = get_font(self.g["font"])
                if "w" in h:
                    nx0 = round(nx0 / fw) * fw
                if "e" in h:
                    nx1 = round(nx1 / fw) * fw
                if "n" in h:
                    ny0 = round(ny0 / fh) * fh
                if "s" in h:
                    ny1 = round(ny1 / fh) * fh
            minw = L.orig_w * SLIDERS["scale_x"][1] / 100.0
            minh = L.orig_h * SLIDERS["scale_y"][1] / 100.0
            if "w" in h:
                nx0 = min(nx0, nx1 - minw)
            if "e" in h:
                nx1 = max(nx1, nx0 + minw)
            if "n" in h:
                ny0 = min(ny0, ny1 - minh)
            if "s" in h:
                ny1 = max(ny1, ny0 + minh)
            if e.state & 0x0001:                                     # Shift: keep aspect ratio
                w, hh = nx1 - nx0, ny1 - ny0
                if len(h) == 2:
                    f = max(w / W0, hh / H0)
                    w, hh = W0 * f, H0 * f
                    if "w" in h:
                        nx0 = nx1 - w
                    else:
                        nx1 = nx0 + w
                    if "n" in h:
                        ny0 = ny1 - hh
                    else:
                        ny1 = ny0 + hh
                elif h in ("e", "w"):
                    f = w / W0
                    cy = (y0 + y1) / 2
                    ny0, ny1 = cy - H0 * f / 2, cy + H0 * f / 2
                else:
                    f = hh / H0
                    cx = (x0 + x1) / 2
                    nx0, nx1 = cx - W0 * f / 2, cx + W0 * f / 2
            self.sliders["scale_x"].set((nx1 - nx0) / L.orig_w * 100.0)
            self.sliders["scale_y"].set((ny1 - ny0) / L.orig_h * 100.0)
            # keep the anchored side exactly where it was
            sx, sy = L.screen_scale()
            nx = nx1 - L.orig_w * sx if "w" in h else nx0
            ny = ny1 - L.orig_h * sy if "n" in h else ny0
            self.sliders["x"].set(round(nx))
            self.sliders["y"].set(round(ny))
            self.changed()

        def alt_click(self, e):
            self.canvas.focus_set()
            if not self.g["alt_select"] or self.mode != "project":
                return "break"
            sx, sy = self.canvas_to_screen(e.x, e.y)
            for i in reversed(range(len(self.layers))):
                L = self.layers[i]
                if L.visible and L.opaque_at(self.g["font"], sx, sy):
                    self.select(i)
                    break
            return "break"

        def nudge(self, dx, dy, fine):
            L = self.cur()
            if self.mode != "project" or L is None:
                return "break"
            if L.kind == "cells":
                self.sliders["col"].set(L.s["col"] + dx)
                self.sliders["row"].set(L.s["row"] + dy)
                self.changed()
                return "break"
            _, fw, fh = get_font(self.g["font"])
            if fine or not self.g["snap"]:
                stepx, stepy = 1, 1
            else:
                stepx, stepy = fw, fh
            self.sliders["x"].set(L.s["x"] + dx * stepx)
            self.sliders["y"].set(L.s["y"] + dy * stepy)
            self.changed()
            return "break"

        def wheel_scale(self, d, cx, cy):
            L = self.cur()
            if self.mode != "project" or L is None or L.kind == "cells":
                return
            px, py = self.canvas_to_screen(cx, cy)
            ox, oy = L.s["scale_x"], L.s["scale_y"]
            f = 1.1 if d > 0 else 1 / 1.1
            self.sliders["scale_x"].set(ox * f)
            self.sliders["scale_y"].set(oy * f)
            kx, ky = L.s["scale_x"] / ox, L.s["scale_y"] / oy
            x = px - (px - L.s["x"]) * kx
            y = py - (py - L.s["y"]) * ky
            if self.g["snap"]:
                _, fw, fh = get_font(self.g["font"])
                x, y = round(x / fw) * fw, round(y / fh) * fh
            self.sliders["x"].set(round(x))
            self.sliders["y"].set(round(y))
            self.changed()

    root = tk.Tk()
    app = App(root)
    root.update_idletasks()
    if initial_path:
        root.after(50, lambda: app.open_file(initial_path))
    else:
        root.after(50, app.refresh)
    root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args(argv):
    """Hand-rolled so -h always works and flags accept - or --."""
    opts = {"input": None, "output": None, "preset": None, "preview": None, "font": None,
            "moebius": None, "no_layer_files": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        flag = a.lstrip("-").lower() if a.startswith("-") and a != "-" else None

        def val():
            if i + 1 >= len(argv):
                raise ValueError(f"{a} needs a value")
            return argv[i + 1]
        if flag in ("o", "output"):
            opts["output"] = val(); i += 2
        elif flag in ("p", "preset"):
            opts["preset"] = val(); i += 2
        elif flag == "preview":
            opts["preview"] = val(); i += 2
        elif flag == "moebius":
            opts["moebius"] = val(); i += 2
        elif flag in ("no-layer-files", "nolayerfiles"):
            opts["no_layer_files"] = True; i += 1
        elif flag == "font":
            v = val().lower()
            if v not in FONT_LABELS:
                raise ValueError("--font must be hauge or vga")
            opts["font"] = v; i += 2
        elif flag is not None:
            raise ValueError(f"unknown option {a}")
        else:
            if opts["input"]:
                raise ValueError(f"unexpected extra argument {a}")
            opts["input"] = a; i += 1
    return opts


def main():
    argv = sys.argv[1:]
    if any(a.lower() in ("-h", "--help", "-help", "/?") for a in argv):
        print_help()
        return 0
    try:
        opts = parse_args(argv)
    except ValueError as e:
        print(f"[{TOOL}] {e}  (see {TOOL} -h)")
        return 2
    headless = opts["output"] is not None or opts["moebius"] is not None
    if not headless and (any(opts[k] is not None for k in ("preset", "preview", "font")) or opts["no_layer_files"]):
        print(f"[{TOOL}] -p/--preview/--font/--no-layer-files only apply with -o or --moebius (headless)")
        return 2
    if headless and not opts["input"]:
        print(f"[{TOOL}] headless mode needs an input image, Moebius file or project")
        return 2
    if opts["input"] and not os.path.isfile(opts["input"]):
        print(f"[{TOOL}] file not found: {opts['input']}")
        return 2
    check_dependencies(need_gui=not headless)
    import_core()
    if headless:
        return run_headless(opts)
    run_gui(opts["input"])
    return 0


# Embedded font data (zlib + base64, 1 bit per pixel, MSB = leftmost)
FONT_HAUGE_B64 = "eNqFWM1qI0cQnmVg5MNgEbIsDRqkQ4LPswjaBg0tax0cAr4uJCYJWhqkg4UkMFgCi+nn8CvkHfbkB8h1wSTk5ouJ97gHg1PV3TX9M2tSMmLmU/10/XR1tZOkTWIyeT+ZTH77aTIRFlHqQiklN0qJho0DooQo9hpkrwBGD2BVdX9/zxirHFI/P9c+YvmYfXw2dH97e28fDV7N3r2bVT7P7c3Hjze3xLNd/3zWH2rqkwRSxRiYM8ju7GyXI+13OwapZ7Nas11tDlO7FnZzXt1X5zck9SrtdAdjNR50O+krjRxP19tdrerddj09JrcYUt34MSOCJ2vr7u7u70+GTFBlVnAJxItSiiADGNkk1lyHCBIt2ZIzj2ipShZozTOV5WGq0zRVAfCaK/7ae98rCiGUCtYGOfeS3iZIJyQUl2dXiHH4PubiYInrL+ODkCdpKqZAUpBnJ3J9xPL9jvxg3gsQKJYjzPLSuJTvZ5HekuWWWGn9ZqUl5tyHanqGovKXrUuFtbxhhR+0+usuO7HjKZjJbKnoNUOKLy50ni1z0W8yZvfX5RQXB2LShlpICERhomH9Oqr48K1CN7Y2E5C9dOzzFBkiWFOEKNCD60Eizfirz6NfatRT9mOPPMcaxIbD+JlmEN5pGB4XI/Or4SRbU8ipVxxo/RpplAqqOQyZ0ks0yBgrSOj9NKbdfZJqOqGuMBBXdsvxgfV9dpq96b/JstOZipAs63p6rsHQvP7VINqsMW6tV80Go7a1tfXkus0czPK+4LCGuUG6maXGOrZPdeFrlvOVUteXHmIS42fH+J55a254Lq5FuXY8HL9XDU+aFRD6Rk9dn0deyJat5p3TBjd2gNSGE7Lh0AAE39CaqdE6zUq+LRnW849Uz1VFu7KqqK+mWZYXsDenU+KhfWp44DjZyMnLfUafDc0uD6lfCtclkg4Er6/DM/MarZBYQOT7EdrlKHS59HmkcjwFP4As+LlAWppzR5S6GNAWX2pbc7dxiiDyZWnsmRoiKSghqCCSKlpVh3SoMBkUeaQRHTT+mr2cejzCLft3WjM1k2S0nEV+wQEF0SU9e5C7sc7g4sjxGDVDL2JUQAGCi/bWAyVUQC+XsRR0oXJA54zErkH1s0XDHW1+G516Tc/u4uNaA8aL5egrlWG6iyTFiZhTJ5mLgu2jT7Ff+twIKgGUYI3pIrO+yyRCIHgRUmBUQilXh6AarWvNYdXJuA615pBnlkQ1xqpZhGipAJEmGK7TwgIjBEYIappNH9N1uFjUvV7vymZnBxtHKdw7ly4+YR3KuDLJC4fk/WEUec0T1pgMqqWPgIj6mEzizgYe2wPjBDuV3cq2Rc/H1McqnADqpqIGYHXw3fAarZtaXX9idkxgvX2jOc8opX61hLkAntBTjYR+YbH6exne8XgITofq4GAXTiAw5VYhkucJjridNOgAZlhIgyETT3zberMOpJfDqkYfYPk7D5ld/vJk2fSZzcx059QseK/HF75ieAXQPP/wTfz543382fwVf9iLNBjErw5ZWFqt6MnNrAHSllqtpk6qTVZJzANSbjQm0CFuhXEPirwA+vIlkAKim49/3rWlwg5oz8RITyzipGjNDw+BXw8P+dNTYPrpKY94Hh+TaIXw+vgY63FSxOOkSI+TIscjHqC2LeeXA+O8OS+c74GeIBrO2ViP00whbeeinWWn+blFnieWui363KK2OPUO6MW9ke0keA/+tjfEtjGks9QcMWEL0PcvzjnxwDjG8KogvT6PTR5o3yHNKNFo+vfaTDJWAi6odiKsvRuQUt5UYI7gDRrf2Ls5jho7I+dZhzvznd/d/kHkz5psb/Fio2djmgr8Ado5Sn/eXabGfws4CM1jU1b+PRLBBlnDvf2lruRHCNTWSXCN1GMIzSL6Cpv83yWSEHr4bIfFQ84rM33xqMXhUYD3rNPwgloTvTBD/wcJdCU+"
FONT_VGA_B64 = "eNp9V09r40YU12JQchD2obAMWMhQQs8Cg2qwUMIGcuq10EMPCgMypSExBNqAjUTopV8hH6CXfoUSWBDsqbDXFJUe60vY3VPJwez0vfn7Zjbtc4L903sz7/+bURSF1N7+cnt7f3d722osBiH6nRCtkSg6oCo9NPgwrShkZbnb7RgrLW5hscNKhKlfQtKuRwVI8mHZvHrVlI7f393f3/Waf7P+5qtsDpRFWhioZKBA4f3v+wRoPDlQ+OObj2+A/t6tRlo5G8pdOWj5F6ODyaybTQ5GLyQ+qdc32257s65PrPmMsdYYHDWK4FvvPwzDXw9IElY8TgvOizTnFYkqhizYr6UYyZgnySmER3mXM7JZEndxQnM2Go06Ao8a0Rw5eJimVdV1xJaqSl2+AoLclGiMtgdcPfIFiqIr5L+ytuKno6quz3llPDjlOUtifq5QWhTp5RLydalsT5LY2w5kJbFcO8dyScx52JSibKiJLtvkGVkQdc/4ZVec1GifzjfUT98PQ9/rgotYmukMRDqhSpx3FtdlXdcmvfmiLOYdGHyjVUMyjgk/jQFzII07WK98NvsBi/Dxdwvr88yznDissXFXmgdRq10Lyz9Dkocydv+c5Fc+2Gw2y1FlqgXKt0ODFD6GCqiw4o9NvE7Bw9GpidesUA1RzLR/zdnL7GV81nQejuMJWb/hvPlWYdQk1Wl9pW4AMy9uZDW4fl+BqiwDpSuFJ7Ekqw8nCaQTSO+/uuo2125/GWsSb+lf7OzT/O83Vb62fPRxZflxmtd2vRjuPHt5sH+vqDH9LNEwCDM/JIthFVp+U5L9RH+OyfupFzo+iSYzT2GCjdOFnVdlrqk02Yz+iwS2I/v0eZZXtl+jgzjOZIrdOKs4FIDxbwGairmTl/zO8dPii3hC4gt0ieLzKpcphf2Ly8bFF+oypfGs62hdS2pkyYG8KgAtnwb1giUiBiSLl3pkO/tIfiy/siYa+0xLLy8bz36c8Xa8HybJMabjYmH5cjmJh5d/hbEAHAYmFIDFqn7aOjctNcd5qut7Da6O0d+1Oy8icn4gD2XYWDuzDNMrO9xsp/sZ2jmvpUdz336cwzSfsNivj7lfLzBtPJwWqS+PGiGFoM4UqF8v3K8f3M/jN5FXHxA4D6M8xdwNNGMOxTgWuyaG3DfuzPjhz4d2unynwBaKu8N4XEfOXlI/3K8nZa/DSTb34ol8rz44yXeGsPLmB4/8eQLnUg/56s0JaNtrdeyKScBH82F8VWfNP1Dfb1X5PDB5fAJNxzoAND+Yby++wKf+IPbsh/oi/QXIDlyV7KLY0tMIrwMRvRnBOZjg8UqvS3iGjujtCdvfXHVOObbD9R91/uRwc/3dVomobihL0m8XxbS4INsBKqbq58+f+59fv/Y/v73zP+x5mgXI4gtFV/rbWNF5OJS/qq18SDocPv+qtrWrn3TkWiTtCUbALLD/yZNnTIQnRSjPvDtrJML1gfRTEI9Hz/7HZO9p2yc+/30kgnPrfbD+0YuPcPJ6vZXX3okgXuH+IvQvSMPe8/fJxU/S0yfx2QfrhW8PC+Mb5svuJwKK6GsU0CSgDwH5y8x5vJxOp0vdz/huNZ1D+87NfRVPe9qQeP1HMpDDTHPnE94/p0jjiL4xwYQdWXVebFpWqjc4OyHkeIYxYSFHdT/q+yBcZ7fync/pg8PejZjXNeC3rVG3SGIc73GyiIILIHlZ6Ogrg369MEHS12c7xPR12+D1w8MzA4H6D5u19P6OQ9KeynIe/s/LinlgfnyQd7svi6Jc6FlGUoHH/zSJP/PLp1L07BXwX3/b09U="

if __name__ == "__main__":
    sys.exit(main())
