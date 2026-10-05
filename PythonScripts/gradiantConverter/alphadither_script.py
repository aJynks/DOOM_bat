#!/usr/bin/env python3
"""
alphadither - draw (or load) a smooth alpha gradient and turn it into a pure
black/white dithered mask (0 = transparent, 255 = opaque) for Doom textures.

GUI:    alphadither [image.png | name.adgrad.json]
Batch:  alphadither <pngs/gradients/folders...> -p <preset> [options]
"""

import sys
import os
import re
import json
import math
import time
import argparse
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# dependency check
# ---------------------------------------------------------------------------
def _check_deps():
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
        print(f"alphadither: missing dependencies: {', '.join(missing)}")
        print(f"  install with:  python -m pip install {' '.join(missing)}")
        sys.exit(1)


_check_deps()

import numpy as np            # noqa: E402
from PIL import Image         # noqa: E402

PRESET_EXT = ".adpreset.json"
GRAD_EXT = ".adgrad.json"


def app_dir():
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "alphadither"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lib_dir(kind):
    p = app_dir() / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def lib_names(kind, ext):
    return sorted((f.name[:-len(ext)] for f in lib_dir(kind).glob("*" + ext)), key=str.lower)


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")


# ---------------------------------------------------------------------------
# dither settings
# ---------------------------------------------------------------------------
ALGORITHMS = [
    "Threshold",
    "Bayer 2x2", "Bayer 4x4", "Bayer 8x8",
    "Halftone 4x4", "Halftone 6x6", "Halftone 8x8",
    "Blue noise",
    "Random",
    "Floyd-Steinberg", "Jarvis-Judice-Ninke", "Stucki", "Burkes",
    "Sierra-3", "Sierra-2", "Sierra Lite", "Atkinson",
]

DEFAULTS = {
    "black": 0,
    "white": 255,
    "gamma": 1.0,
    "contrast": 0,
    "blur": 0.0,
    "invert": False,
    "protect_lo": 0,
    "protect_hi": 255,
    "algorithm": "Blue noise",
    "strength": 100,
    "serpentine": True,
    "scale": 1,
    "seed": 0,
    "seamless": True,
}

RANGES = {
    "black": (0, 254), "white": (1, 255), "gamma": (0.05, 10.0),
    "contrast": (-100, 99), "blur": (0.0, 32.0),
    "protect_lo": (-1, 254), "protect_hi": (1, 256),
    "strength": (0, 200), "scale": (1, 8), "seed": (0, 99999),
}

KERNELS = {
    "Floyd-Steinberg": ([(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)], 16),
    "Jarvis-Judice-Ninke": ([(1, 0, 7), (2, 0, 5),
                             (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
                             (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1)], 48),
    "Stucki": ([(1, 0, 8), (2, 0, 4),
                (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
                (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1)], 42),
    "Burkes": ([(1, 0, 8), (2, 0, 4),
                (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2)], 32),
    "Sierra-3": ([(1, 0, 5), (2, 0, 3),
                  (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2),
                  (-1, 2, 2), (0, 2, 3), (1, 2, 2)], 32),
    "Sierra-2": ([(1, 0, 4), (2, 0, 3),
                  (-2, 1, 1), (-1, 1, 2), (0, 1, 3), (1, 1, 2), (2, 1, 1)], 16),
    "Sierra Lite": ([(1, 0, 2), (-1, 1, 1), (0, 1, 1)], 4),
    "Atkinson": ([(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)], 8),
}


def sanitize_settings(raw):
    s = dict(DEFAULTS)
    for k, v in (raw or {}).items():
        if k not in DEFAULTS:
            continue
        d = DEFAULTS[k]
        try:
            if isinstance(d, bool):
                v = bool(v)
            elif isinstance(d, int):
                v = int(round(float(v)))
            elif isinstance(d, float):
                v = float(v)
            else:
                v = str(v)
        except (TypeError, ValueError):
            continue
        if k in RANGES:
            lo, hi = RANGES[k]
            v = type(d)(min(max(v, lo), hi))
        if k == "algorithm" and v not in ALGORITHMS:
            continue
        s[k] = v
    return s


def load_preset(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "settings" in data:
        data = data["settings"]
    return sanitize_settings(data)


def save_preset(path, settings):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"alphadither_preset": 2, "settings": settings}, f, indent=2)


BUILTIN_PREFIX = "\u2605 "   # star marks read-only built-in presets in the library list

# (name, description, overrides on DEFAULTS)
BUILTIN_PRESETS = [
    ("Smooth fade", "Blue noise, no shaping. The best all-round organic fade for a plain "
     "2-point gradient: even spacing, no grid, no streaks.",
     {"algorithm": "Blue noise"}),
    ("Smooth fade - clean ends", "Blue noise, with the faint and dense extremes snapped to "
     "empty/solid so no lone specks or pinholes sit at either end of the fade.",
     {"algorithm": "Blue noise", "protect_lo": 15, "protect_hi": 240}),
    ("Smooth fade - holds solid longer", "Blue noise, gamma 1.8: stays dense for most of the "
     "run and thins out late, near the end node.",
     {"algorithm": "Blue noise", "gamma": 1.8}),
    ("Smooth fade - thins out early", "Blue noise, gamma 0.55: breaks up quickly after the "
     "start node and spends longer as a light scatter.",
     {"algorithm": "Blue noise", "gamma": 0.55}),
    ("Short transition", "Blue noise, contrast 60: solid and empty regions with a narrow "
     "dithered band in the middle of the line.",
     {"algorithm": "Blue noise", "contrast": 60}),
    ("Chunky organic", "Blue noise at pattern scale 2. Bigger holes that read on large walls "
     "and hold up at distance.",
     {"algorithm": "Blue noise", "scale": 2}),
    ("Retro screen-door", "Bayer 4x4: the classic regular cross-hatch. Very stable on far "
     "walls; tiles on multiples of 4 px.",
     {"algorithm": "Bayer 4x4"}),
    ("Fine cross-hatch", "Bayer 8x8: smoother steps than 4x4 with a finer regular texture.",
     {"algorithm": "Bayer 8x8"}),
    ("Chunky screen-door", "Bayer 4x4 at pattern scale 2. Big regular blocks - the most "
     "distance-proof option for wide walls.",
     {"algorithm": "Bayer 4x4", "scale": 2}),
    ("Halftone dots", "Clustered dot 8x8: round dots growing into round holes, like print "
     "halftone. Good for grates, smoke, eaten metal.",
     {"algorithm": "Halftone 8x8"}),
    ("Small halftone dots", "Clustered dot 4x4: tighter, smaller dots on a 4 px grid.",
     {"algorithm": "Halftone 4x4"}),
    ("Organic grain", "Jarvis-Judice-Ninke error diffusion, serpentine. Accurate, slightly "
     "grainy, non-repeating. Best close up.",
     {"algorithm": "Jarvis-Judice-Ninke", "serpentine": True}),
    ("Fine grain", "Floyd-Steinberg, serpentine. The finest detail; can shimmer at distance.",
     {"algorithm": "Floyd-Steinberg", "serpentine": True}),
    ("Crisp diffusion", "Atkinson: high-contrast diffusion that washes the ends toward solid "
     "and empty - fewer stray pixels than other diffusers.",
     {"algorithm": "Atkinson", "serpentine": True}),
    ("Soft blurred source", "Blue noise with a light blur and clean ends. Mainly for PNG "
     "alphas that have banding or hard steps.",
     {"algorithm": "Blue noise", "blur": 1.5, "protect_lo": 8, "protect_hi": 247}),
    ("Gritty noise", "Random white noise. Clumpy and rough - for grime or deliberately messy "
     "edges. Try different seeds.",
     {"algorithm": "Random"}),
    ("Hard edge", "Threshold: no dithering, a straight cut where the fade crosses 50%.",
     {"algorithm": "Threshold"}),
]


def find_builtin(name):
    key = name.replace(BUILTIN_PREFIX.strip(), "").strip().lower()
    for n, desc, over in BUILTIN_PRESETS:
        if n.lower() == key:
            return n, desc, sanitize_settings(over)
    return None


def resolve_preset(arg):
    p = Path(arg)
    if p.is_file():
        return p
    lp = lib_dir("presets") / (safe_name(arg) + PRESET_EXT)
    if lp.is_file():
        return lp
    raise FileNotFoundError(f"preset not found as file, built-in or library name: {arg}")


def load_preset_arg(arg):
    """CLI: file path -> built-in name -> library name."""
    p = Path(arg)
    if p.is_file():
        return load_preset(p)
    b = find_builtin(arg)
    if b:
        return b[2]
    return load_preset(resolve_preset(arg))


# ---------------------------------------------------------------------------
# gradient model
#   start node: always 100% opaque, end node: always 100% transparent
#   mid nodes: {"t": 0..1 along the line, "tr": transparency 0..100 %}
# ---------------------------------------------------------------------------
def default_gradient(w=128, h=128):
    return {"width": w, "height": h, "start": [w / 2, 0.0], "end": [w / 2, float(h)], "nodes": []}


def sanitize_gradient(g):
    try:
        w = int(min(max(int(g.get("width", 128)), 1), 4096))
        h = int(min(max(int(g.get("height", 128)), 1), 4096))
        s = [float(v) for v in g["start"]][:2]
        e = [float(v) for v in g["end"]][:2]
        nodes = []
        for n in g.get("nodes", []):
            nodes.append({"t": min(max(float(n["t"]), 0.001), 0.999),
                          "tr": min(max(float(n["tr"]), 0.0), 100.0)})
        return {"width": w, "height": h, "start": s, "end": e, "nodes": nodes}
    except Exception:
        return default_gradient()


def load_gradient(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "gradient" in data:
        data = data["gradient"]
    return sanitize_gradient(data)


def save_gradient(path, g):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"alphadither_gradient": 1, "gradient": g}, f, indent=2)


def grad_profile_points(g):
    ns = sorted(g["nodes"], key=lambda n: n["t"])
    xp = [0.0] + [n["t"] for n in ns] + [1.0]
    fp = [1.0] + [1.0 - n["tr"] / 100.0 for n in ns] + [0.0]
    return xp, fp


def gradient_alpha(g):
    W, H = int(g["width"]), int(g["height"])
    sx, sy = g["start"]
    ex, ey = g["end"]
    dx, dy = ex - sx, ey - sy
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return np.ones((H, W))
    xs = np.arange(W) + 0.5
    ys = np.arange(H) + 0.5
    t = ((xs[None, :] - sx) * dx + (ys[:, None] - sy) * dy) / L2
    xp, fp = grad_profile_points(g)
    return np.interp(np.clip(t, 0.0, 1.0), xp, fp)


# ---------------------------------------------------------------------------
# threshold matrices
# ---------------------------------------------------------------------------
def bayer_matrix(n):
    m = np.array([[0, 2], [3, 1]], dtype=np.float64)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / m.size


def halftone_matrix(n):
    y, x = np.mgrid[0:n, 0:n]
    fx = (x + 0.5) / n
    fy = (y + 0.5) / n
    spot = np.cos(2 * np.pi * fx) + np.cos(2 * np.pi * fy)
    order = np.argsort(-spot.ravel(), kind="stable")
    rank = np.empty(n * n, dtype=np.float64)
    rank[order] = np.arange(n * n)
    return ((rank + 0.5) / (n * n)).reshape(n, n)


BLUE_N = 64
_BLUE = None


def blue_noise_ready():
    return _BLUE is not None


def blue_noise_matrix():
    global _BLUE
    if _BLUE is None:
        _BLUE = _void_and_cluster(BLUE_N, 1.5, 12345)
    return _BLUE


def _void_and_cluster(n, sigma, seed):
    rng = np.random.default_rng(seed)
    total = n * n
    d = np.minimum(np.arange(n), n - np.arange(n)).astype(np.float64)
    g = np.exp(-(d * d) / (2 * sigma * sigma))
    G = np.outer(g, g)

    def splat(e, idx, sign):
        y, x = divmod(int(idx), n)
        e += sign * np.roll(G, (y, x), axis=(0, 1))

    ones = max(1, total // 10)
    pat = np.zeros(total, dtype=bool)
    pat[rng.choice(total, ones, replace=False)] = True
    pat = pat.reshape(n, n)
    e = np.zeros((n, n))
    for idx in np.flatnonzero(pat):
        splat(e, idx, 1)
    for _ in range(total):
        c = int(np.argmax(np.where(pat, e, -np.inf)))
        pat.flat[c] = False
        splat(e, c, -1)
        v = int(np.argmin(np.where(pat, np.inf, e)))
        pat.flat[v] = True
        splat(e, v, 1)
        if v == c:
            break
    rank = np.zeros(total, dtype=np.int64)
    p, e1 = pat.copy(), e.copy()
    for r in range(ones - 1, -1, -1):
        c = int(np.argmax(np.where(p, e1, -np.inf)))
        p.flat[c] = False
        splat(e1, c, -1)
        rank[c] = r
    p, e2 = pat.copy(), e.copy()
    for r in range(ones, total):
        v = int(np.argmin(np.where(p, np.inf, e2)))
        p.flat[v] = True
        splat(e2, v, 1)
        rank[v] = r
    return (rank.reshape(n, n) + 0.5) / total


def pattern_period(s):
    n = {"Bayer 2x2": 2, "Bayer 4x4": 4, "Bayer 8x8": 8,
         "Halftone 4x4": 4, "Halftone 6x6": 6, "Halftone 8x8": 8,
         "Blue noise": BLUE_N}.get(s["algorithm"])
    sc = int(s["scale"])
    if n:
        return n * sc
    return sc if sc > 1 else None


# ---------------------------------------------------------------------------
# processing
# ---------------------------------------------------------------------------
def gauss_blur(a, sigma, wrap):
    r = int(math.ceil(sigma * 3))
    if r < 1:
        return a
    i = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-(i * i) / (2 * sigma * sigma))
    k /= k.sum()
    h, w = a.shape
    p = np.pad(a, r, mode="wrap" if wrap else "edge")
    tmp = np.zeros((p.shape[0], w))
    for j in range(2 * r + 1):
        tmp += k[j] * p[:, j:j + w]
    out = np.zeros((h, w))
    for j in range(2 * r + 1):
        out += k[j] * tmp[j:j + h, :]
    return out


def shape_alpha(src, s):
    a = src
    if s["blur"] > 0:
        a = gauss_blur(a, s["blur"], False)   # never wrap: a fade rarely matches at opposite edges
    b = s["black"] / 255.0
    w = s["white"] / 255.0
    if w <= b:
        w = b + 1 / 255.0
    a = np.clip((a - b) / (w - b), 0.0, 1.0)
    g = max(0.05, s["gamma"])
    if g != 1.0:
        a = a ** (1.0 / g)
    c = max(-100, min(99, s["contrast"]))
    if c:
        f = (1 + c / 100.0) / (1 - c / 100.0)
        a = np.clip((a - 0.5) * f + 0.5, 0.0, 1.0)
    return a


def _ordered(a, M, seed):
    n = M.shape[0]
    off = seed % n
    if off:
        M = np.roll(M, (off, (off * 3) % n), axis=(0, 1))
    h, w = a.shape
    T = np.tile(M, (h // n + 1, w // n + 1))[:h, :w]
    return a > T


def _error_diffuse(a, name, serpentine, strength, seamless):
    kern, div = KERNELS[name]
    k = [(dx, dy, wt * strength / div) for dx, dy, wt in kern]
    h, w = a.shape
    warm = min(h, 16) if seamless else 0
    order = list(range(h - warm, h)) + list(range(h))
    n = len(order)
    buf = [a[r].astype(np.float64).tolist() for r in order]
    outrows = [[False] * w for _ in range(n)]
    fwd = range(w)
    rev = range(w - 1, -1, -1)
    for y in range(n):
        row = buf[y]
        orow = outrows[y]
        if serpentine and (y & 1):
            xs, sgn = rev, -1
        else:
            xs, sgn = fwd, 1
        for x in xs:
            old = row[x]
            if old >= 0.5:
                orow[x] = True
                err = old - 1.0
            else:
                err = old
            if err == 0.0:
                continue
            for dx, dy, wt in k:
                nx = x + dx * sgn
                ny = y + dy
                if nx < 0 or nx >= w:
                    if not seamless:
                        continue
                    nx %= w
                    if dy == 0:
                        ny += 1
                if ny >= n:
                    continue
                buf[ny][nx] += err * wt
    return np.array(outrows[warm:], dtype=bool)


def _dither_core(a, s):
    alg = s["algorithm"]
    if alg == "Threshold":
        return a >= 0.5
    if alg.startswith("Bayer"):
        return _ordered(a, bayer_matrix(int(alg[-1])), s["seed"])
    if alg.startswith("Halftone"):
        return _ordered(a, halftone_matrix(int(alg[-1])), s["seed"])
    if alg == "Blue noise":
        return _ordered(a, blue_noise_matrix(), s["seed"])
    if alg == "Random":
        rng = np.random.default_rng(s["seed"])
        return a > rng.random(a.shape)
    return _error_diffuse(a, alg, s["serpentine"], s["strength"] / 100.0, s["seamless"])


def dither(a, s):
    sc = int(s["scale"])
    h, w = a.shape
    if sc <= 1:
        return _dither_core(a, s)
    hh = -(-h // sc) * sc
    ww = -(-w // sc) * sc
    p = np.pad(a, ((0, hh - h), (0, ww - w)), mode="edge")
    small = p.reshape(hh // sc, sc, ww // sc, sc).mean(axis=(1, 3))
    o = _dither_core(small, s)
    return o.repeat(sc, 0).repeat(sc, 1)[:h, :w]


def process(alpha, s):
    """alpha 0..1 -> (mask uint8 0/255, smooth target 0..1)"""
    src = 1.0 - alpha if s["invert"] else alpha
    a = shape_alpha(src, s).copy()
    lo_m = src <= (s["protect_lo"] / 255.0) + 1e-9
    hi_m = src >= (s["protect_hi"] / 255.0) - 1e-9
    a[lo_m] = 0.0
    a[hi_m] = 1.0
    opaque = dither(a, s)
    opaque[lo_m] = False
    opaque[hi_m] = True
    return np.where(opaque, 255, 0).astype(np.uint8), a


def load_png_alpha(path):
    im = Image.open(path)
    im.load()
    has_alpha = im.mode in ("RGBA", "LA", "PA", "RGBa", "La") or "transparency" in im.info
    alpha = np.array(im.convert("RGBA"))[..., 3].astype(np.float64) / 255.0
    if not has_alpha or bool((alpha >= 1.0).all()):
        has_alpha = False
    return alpha, has_alpha


def write_mask(path, mask):
    vals = set(np.unique(mask).tolist())
    if not vals <= {0, 255}:
        raise ValueError(f"mask contains values other than 0/255 ({sorted(vals)[:8]}) - refusing to save")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(mask, dtype=np.uint8)).save(path)
    return path


# ---------------------------------------------------------------------------
# help text (GUI)
# ---------------------------------------------------------------------------
HELP = [
    ("h1", "alphadither"),
    ("p", "Doom's software renderers draw a texture pixel either fully or not at all, so a fade has "
          "to be faked with a pattern of holes. alphadither builds a smooth alpha gradient (or takes "
          "one from a PNG) and turns it into a pure black-and-white mask: white = opaque, "
          "black = transparent. Pick and tune the hole pattern while watching the result live."),
    ("p", "Pipeline:  source alpha  ->  alpha shaping  ->  protect  ->  dither  ->  mask.  Everything "
          "before the dither is smooth; the dither is the only step that makes the on/off "
          "decision, and the saved mask is checked to contain only 0 and 255."),

    ("h2", "Sliders"),
    ("p", "Every numeric setting has a slider and a spinner that stay in sync. Drag the slider or "
          "click anywhere on its track to jump there; the preview redraws live while you drag. "
          "Double-click a slider to reset that setting to its default. Type in the spinner for an "
          "exact value - some spinners accept a wider range than their slider shows (e.g. Blur up "
          "to 32), in which case the slider sits at its end. Gamma's slider is logarithmic, so 1.0 "
          "is in the middle. The mouse wheel over a slider scrolls the panel; over a spinner it "
          "steps the value."),

    ("h2", "Source"),
    ("i", "Gradient", "draw a linear fade on a blank canvas of the size you set."),
    ("i", "PNG", "use the alpha channel of a loaded PNG (Ctrl+O). Colour is ignored."),

    ("h2", "Gradient controls"),
    ("i", "Start node", "(filled black) is always 100% opaque. Drag it anywhere - even outside "
                        "the texture for a long, gentle fade."),
    ("i", "End node", "(white) is always 100% transparent. Drag it anywhere."),
    ("i", "Snapping", "hold Shift while dragging an end node to snap the line to 45 degree "
                      "steps; hold Ctrl to snap to whole pixels."),
    ("i", "Add a node", "click on the line (or on the ramp strip in the panel). It starts at "
                        "whatever transparency the gradient already had at that point."),
    ("i", "Move a node", "drag it - mid nodes only slide along the line."),
    ("i", "Node transparency", "mouse wheel over a node: 5% per notch, Shift = 1%. Wheel up = "
                               "more opaque. Or type it in the Transparency spinner."),
    ("i", "Delete a node", "right-click it, or select it and press Delete."),
    ("i", "Interpolation", "transparency is linear between neighbouring nodes. Before the start "
                           "node everything is solid; past the end node everything is empty."),
    ("i", "Direction buttons", "place start/end edge to edge: down, up, right, left. Nodes keep "
                               "their positions along the line."),
    ("i", "Size", "changing width/height rescales the start/end positions with the canvas."),

    ("h2", "Alpha shaping"),
    ("p", "Applied to the smooth alpha before dithering. With the defaults the gradient passes "
          "through untouched."),
    ("i", "Black / White point", "levels: alpha below the black point becomes 0, above the "
                                 "white point becomes 1, and the range between is stretched. "
                                 "Use it to shorten a fade or push it toward one end."),
    ("i", "Gamma", ">1 makes the whole fade more opaque (holes appear later), <1 more transparent. "
                   "Bends the fade without moving its ends."),
    ("i", "Contrast", "steepens (+) or flattens (-) the middle of the fade around 50%."),
    ("i", "Blur", "softens the source before dithering. Mostly for PNG sources with hard steps or "
                  "banding; a drawn gradient rarely needs it."),
    ("i", "Invert", "swaps opaque and transparent."),

    ("h2", "Protect"),
    ("p", "Compares the SOURCE alpha (0-255). Pixels at or past these limits are forced fully off "
          "or on after dithering, so solid areas never get stray holes and empty areas never get "
          "stray specks."),
    ("i", "Transparent <=", "default 0 (only exactly-empty pixels). Raise it, e.g. 10, to "
                               "clean lone dots out of the faint end of a fade. -1 disables."),
    ("i", "Opaque >=", "default 255. Lower it, e.g. 245, to remove lone holes from the solid "
                          "end. 256 disables."),

    ("h2", "Dither algorithms"),
    ("i", "Threshold", "no dithering - a hard cut at 50%. A baseline, or for a deliberate hard edge."),
    ("p", "ORDERED patterns compare each pixel against a fixed repeating grid of thresholds. They "
          "are stable, predictable, and tile perfectly when the texture size is a multiple of the "
          "grid. Because the pattern is regular they hold up well on far walls in Doom."),
    ("i", "Bayer 2x2", "only 5 opacity levels - coarse, visible steps. Strong checkerboard look."),
    ("i", "Bayer 4x4", "17 levels. The classic retro 'screen-door' cross-hatch; a good default "
                       "for regular, mechanical fades."),
    ("i", "Bayer 8x8", "65 levels - smooth steps, finer cross-hatch texture."),
    ("i", "Halftone 4x4 / 6x6 / 8x8", "clustered dot: grows round dots (and later round holes) "
                                      "from the cell corners, like print halftone. Fewer, bigger, "
                                      "clumped holes - reads as a chunky deliberate pattern. Good "
                                      "for grates, smoke, rust-eaten metal. Bigger cell = bigger dots."),
    ("i", "Blue noise", "an irregular but evenly-spaced pattern with no visible grid and no "
                        "streaks. Usually the most natural organic fade. Tiles every 64 px, so "
                        "use textures that are multiples of 64 (times the pattern scale)."),
    ("i", "Random", "plain white noise. Grainy and clumpy, mostly here for comparison. Seed "
                    "changes it."),
    ("p", "ERROR DIFFUSION visits pixels in order and pushes each pixel's rounding error onto "
          "neighbours not yet visited. It gives the most accurate average density and the finest "
          "detail, but the pattern never repeats, can form 'worm' streaks, and tends to shimmer on "
          "distant walls. Speed depends on texture size (tens of ms at Doom sizes)."),
    ("i", "Floyd-Steinberg", "4 neighbours. Fine grain, fast, some worms."),
    ("i", "Jarvis-Judice-Ninke", "12 neighbours over 2 rows. Smoother and coarser grain, "
                                 "fewer worms."),
    ("i", "Stucki", "like JJN with sharper weights - clean and slightly crisper."),
    ("i", "Burkes", "one-row version of Stucki; sits between Floyd-Steinberg and Stucki."),
    ("i", "Sierra-3 / Sierra-2 / Sierra Lite", "progressively lighter kernels. Sierra-3 is close "
                                               "to JJN; Sierra Lite is a rougher, cheap "
                                               "Floyd-Steinberg."),
    ("i", "Atkinson", "deliberately spreads only 3/4 of the error, so the faint and dense ends "
                      "of a fade wash toward empty/solid. Cleaner, higher-contrast fades with "
                      "fewer isolated pixels at the extremes."),

    ("h2", "Dither options"),
    ("i", "Strength %", "error diffusion only. 100 = correct. Lower keeps patterns "
                                  "cleaner but less accurate in density; above 100 gets noisy."),
    ("i", "Serpentine scan", "error diffusion only. Alternates scan direction each row to break "
                             "up diagonal worms. Usually on."),
    ("i", "Pattern scale", "dither at 1/n resolution and blow each result pixel up to an n x n "
                           "block. Chunkier holes that survive distance and big walls."),
    ("i", "Seed", "(New = random seed) the seed for Random; for Bayer, Halftone and Blue noise it "
                                  "shifts the pattern so neighbouring textures don't share "
                                  "identical holes. Ignored by error diffusion."),
    ("i", "Seamless", "treat the texture as wrapping, so the pattern continues across its edges "
                      "when tiled on a wall. Ordered patterns need the texture size to be a "
                      "multiple of the pattern period - the status bar warns when it isn't."),

    ("h2", "View"),
    ("i", "Dither (D)", "off shows the smooth target the dither is approximating (after shaping)."),
    ("i", "Mode", "Preview; Side by side (smooth | dithered); Mask (B/W) - exactly what gets "
                  "saved, white = opaque."),
    ("i", "Background", "Solid colour, Transparent (checkerboard) or Image (tiled behind the "
                        "mask - preview only, never saved)."),
    ("i", "Zoom", "nearest-neighbour; Ctrl+wheel over the image."),
    ("i", "Tile 3x3", "repeats the texture to check seams and pattern beat. Handles sit on the "
                      "centre tile."),
    ("i", "Distance + Sampling", "shrinks the preview as if the wall were further away. Point "
                                 "sampling is what dsda/nyan's software renderer does (one texel "
                                 "per screen pixel, no filtering) - it shows the aliasing and "
                                 "shimmer fine patterns get far away. Box shows the average your "
                                 "eye perceives. Handles are hidden while distance > 1."),

    ("h2", "Status bar"),
    ("p", "source = mean source alpha, target = mean after shaping/protect, mask = actual % of "
          "opaque pixels. Target and mask should be close; a big gap means the dither (e.g. "
          "Atkinson, low strength) is shifting the overall density."),

    ("h2", "Presets, gradients, session"),
    ("p", "Dither presets store shaping, protect and dither settings. Gradients store size, end "
          "positions and nodes. Both live in %APPDATA%\\alphadither and can be swapped "
          "independently, so one dither style can be paired with many gradients. Import/Export "
          "moves presets as files. Your last session (settings, view, gradient, source, "
          "background, window size) is restored on launch."),

    ("h2", "Built-in presets"),
    ("p", "Marked with a star in the Dither presets list. They can't be deleted or overwritten - "
          "pick one, tweak it, then Save as... to keep your version. All of them assume a plain "
          "2-point gradient unless noted."),
    ("BUILTINS",),

    ("h2", "Shortcuts"),
    ("i", "Ctrl+O", "load PNG"),
    ("i", "Ctrl+S", "save mask"),
    ("i", "D", "dither on/off"),
    ("i", "Delete", "delete selected node"),
    ("i", "F1", "this help"),
    ("i", "Drag empty space", "pan. Wheel / Shift+wheel scroll, Ctrl+wheel zoom."),

    ("h2", "Tips"),
    ("p", "Far, regular walls: Bayer 4x4 or Blue noise, pattern scale 1-2. Close-up organic fades: "
          "Blue noise or Jarvis-Judice-Ninke. Check any choice with Distance 3-4 + Point sampling "
          "before committing - fine error-diffusion patterns often turn to mush or shimmer there."),
]


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog
    from PIL import ImageTk
    TK_OK = True
except ImportError:
    TK_OK = False

VIEW_MODES = ["Preview", "Side by side", "Mask (B/W)"]
SAMPLING = ["Point (Doom software)", "Box (perceived average)"]
VIEW_DEFAULTS = {
    "bgmode": "Solid", "view": "Side by side", "zoom": 4, "tile": False,
    "distance": 1, "sampling": SAMPLING[0], "dither": True,
}
SIZES = (8, 16, 32, 48, 64, 96, 128, 160, 192, 256, 320, 384, 512, 768, 1024)


class SliderSpin:
    """label | slider (stretches) | spinner, all bound to one StringVar."""
    LABEL_W = 14
    THUMB = 8

    def __init__(self, app, parent, label, var, lo, hi, inc, fmt, default, srange=None, log=False):
        self.app, self.var = app, var
        self.lo, self.hi, self.inc, self.fmt, self.default = lo, hi, inc, fmt, default
        self.slo, self.shi = srange or (lo, hi)
        self.log = log
        self.enabled = True
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=self.LABEL_W).pack(side="left")
        kw = dict(from_=lo, to=hi, increment=inc, textvariable=var, width=7)
        if fmt:
            kw["format"] = fmt
        self.spin = ttk.Spinbox(row, **kw)
        self.spin.pack(side="right")
        self.scale = ttk.Scale(row, from_=0, to=1000, orient="horizontal", length=170)
        self.scale.pack(side="left", fill="x", expand=True, padx=(2, 6))
        self.scale.bind("<ButtonPress-1>", self._press)
        self.scale.bind("<B1-Motion>", self._motion)
        self.scale.bind("<ButtonRelease-1>", self._release)
        self.scale.bind("<Double-Button-1>", self._reset)
        var.trace_add("write", lambda *_: self._sync())
        self._sync()

    def _text(self, v):
        if self.fmt:
            return self.fmt % v
        return str(int(round(v)))

    def _sync(self):
        try:
            v = float(self.var.get())
        except ValueError:
            return
        v = min(max(v, self.slo), self.shi)
        if self.log:
            f = math.log(v / self.slo) / math.log(self.shi / self.slo)
        else:
            f = (v - self.slo) / (self.shi - self.slo) if self.shi != self.slo else 0.0
        self.scale.set(f * 1000)

    def _apply_x(self, x):
        w = self.scale.winfo_width()
        f = (x - self.THUMB) / max(1, w - 2 * self.THUMB)
        f = min(max(f, 0.0), 1.0)
        if self.log:
            v = self.slo * (self.shi / self.slo) ** f
        else:
            v = self.slo + f * (self.shi - self.slo)
        v = round(v / self.inc) * self.inc
        v = min(max(v, self.lo), self.hi)
        t = self._text(v)
        if t != self.var.get():
            self.var.set(t)

    def _press(self, e):
        if self.enabled:
            self.app._slider_active = True
            self._apply_x(e.x)
        return "break"

    def _motion(self, e):
        if self.enabled and self.app._slider_active:
            self._apply_x(e.x)
        return "break"

    def _release(self, e):
        self.app._slider_active = False
        return "break"

    def _reset(self, e):
        if self.enabled:
            self.var.set(self._text(self.default))
        return "break"

    def set_enabled(self, on):
        self.enabled = on
        st = ["!disabled"] if on else ["disabled"]
        self.spin.state(st)
        self.scale.state(st)


class App:
    PAD = 8
    RAMP_W = 270
    RAMP_PAD = 9
    RAMP_H = 24

    def __init__(self, root, initial=None):
        self.root = root
        root.title("alphadither")
        root.geometry("1320x880")
        root.minsize(800, 500)

        self.grad = default_gradient()
        self.png_path = None
        self.png_alpha = None
        self.png_has_alpha = True
        self.alpha = None
        self.has_alpha = True
        self.mask = None
        self.shaped = None
        self.proc_ms = 0.0
        self.sel = None
        self.drag = None
        self.handles_on = False
        self._origin = (0, 0)
        self._zoom = 1
        self._suppress = False
        self._need_proc = False
        self._job = None
        self._photo = None
        self._ramp_photo = None
        self.help_win = None
        self._slider_active = False
        self.bg_color = (74, 90, 106)
        self.bg_image = None
        self.bg_image_path = None
        self.last_save_dir = None

        self.s_vars = {}
        self.v_vars = {}
        self._good_s = dict(DEFAULTS)
        self._good_v = dict(VIEW_DEFAULTS)

        self._build()
        self._load_session()

        if initial:
            p = Path(initial)
            if p.name.lower().endswith(GRAD_EXT):
                try:
                    self.grad = load_gradient(p)
                    self.grad_name.set(p.name[:-len(GRAD_EXT)])
                except Exception as e:
                    messagebox.showerror("alphadither", f"Could not load gradient:\n{e}")
                self.source.set("Gradient")
            else:
                self._load_png(p)
                self.source.set("PNG")

        self._sync_size_panel()
        self._apply_source()

        root.bind_all("<MouseWheel>", self._on_wheel)
        root.bind("<Control-o>", lambda e: self.open_png())
        root.bind("<Control-s>", lambda e: self.save_mask())
        root.bind("<F1>", lambda e: self.show_help())
        root.bind("<KeyPress-d>", self._key_dither)
        root.bind("<KeyPress-D>", self._key_dither)
        root.bind("<Delete>", self._key_delete)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================= widget helpers =================
    @staticmethod
    def _fmt(v, kind):
        if kind == "float":
            return f"{float(v):.2f}"
        if kind == "int":
            return str(int(v))
        return v

    def _add_num(self, parent, store, key, label, lo, hi, inc, kind, default, reprocess,
                 srange=None, log=False):
        var = tk.StringVar(value=self._fmt(default, kind))
        store[key] = (var, kind, (lo, hi))
        var.trace_add("write", lambda *_: self.schedule(reprocess))
        fmt = "%.2f" if kind == "float" else None
        return SliderSpin(self, parent, label, var, lo, hi, inc, fmt, default, srange, log)

    def _add_seed(self, parent, store):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text="Seed", width=SliderSpin.LABEL_W).pack(side="left")
        var = tk.StringVar(value=str(DEFAULTS["seed"]))
        ttk.Button(row, text="New", width=5,
                   command=lambda: var.set(str(random.randint(1, 99999)))).pack(side="right")
        ttk.Spinbox(row, from_=0, to=99999, increment=1, textvariable=var,
                    width=7).pack(side="right", padx=(0, 4))
        store["seed"] = (var, "int", RANGES["seed"])
        var.trace_add("write", lambda *_: self.schedule(True))

    def _add_bool(self, parent, store, key, label, default, reprocess):
        var = tk.BooleanVar(value=default)
        ttk.Checkbutton(parent, text=label, variable=var).pack(anchor="w", pady=1)
        store[key] = (var, "bool", None)
        var.trace_add("write", lambda *_: self.schedule(reprocess))

    def _add_combo(self, parent, store, key, label, values, default, reprocess, kind="str", width=22):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=label).pack(side="left")
        var = tk.StringVar(value=str(default))
        ttk.Combobox(row, textvariable=var, values=values, state="readonly",
                     width=width).pack(side="right")
        store[key] = (var, kind, None)
        var.trace_add("write", lambda *_: self.schedule(reprocess))

    def _read(self, store, good):
        out = {}
        for key, (var, kind, rng) in store.items():
            try:
                raw = var.get()
                if kind == "int":
                    v = int(round(float(raw)))
                elif kind == "float":
                    v = float(raw)
                elif kind == "bool":
                    v = bool(raw)
                else:
                    v = str(raw)
                if rng:
                    v = min(max(v, rng[0]), rng[1])
            except (ValueError, tk.TclError):
                v = good[key]
            out[key] = v
        good.update(out)
        return out

    def get_settings(self):
        return sanitize_settings(self._read(self.s_vars, self._good_s))

    def get_view(self):
        return self._read(self.v_vars, self._good_v)

    def _set_store(self, store, values):
        for key, (var, kind, _) in store.items():
            if key in values:
                var.set(self._fmt(values[key], kind))

    def set_settings(self, s):
        self._set_store(self.s_vars, s)

    def _section(self, parent, title):
        f = ttk.LabelFrame(parent, text=title, padding=6)
        f.pack(fill="x", pady=(0, 6))
        return f

    @staticmethod
    def _btnrow(parent, buttons, pady=(4, 0)):
        r = ttk.Frame(parent)
        r.pack(fill="x", pady=pady)
        for text, cmd in buttons:
            ttk.Button(r, text=text, command=cmd).pack(side="left", expand=True, fill="x")
        return r

    # ================= layout =================
    def _build(self):
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        self.status = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status, anchor="w", relief="sunken",
                  padding=(6, 2)).pack(side="bottom", fill="x")

        self.bgc = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        self.pcanvas = tk.Canvas(main, width=420, highlightthickness=0, bg=self.bgc)
        psb = ttk.Scrollbar(main, orient="vertical", command=self.pcanvas.yview)
        self.pcanvas.configure(yscrollcommand=psb.set)
        psb.pack(side="right", fill="y")
        self.pcanvas.pack(side="right", fill="y")
        panel = ttk.Frame(self.pcanvas, padding=6)
        self.pcanvas.create_window(0, 0, anchor="nw", window=panel)
        panel.bind("<Configure>", lambda e: self.pcanvas.configure(
            scrollregion=self.pcanvas.bbox("all"), width=panel.winfo_reqwidth()))

        cf = ttk.Frame(main)
        cf.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(cf, bg="#1b1b1b", highlightthickness=0)
        hs = ttk.Scrollbar(cf, orient="horizontal", command=self.canvas.xview)
        vs = ttk.Scrollbar(cf, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        cf.rowconfigure(0, weight=1)
        cf.columnconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self._c_press)
        self.canvas.bind("<B1-Motion>", self._c_drag)
        self.canvas.bind("<ButtonRelease-1>", self._c_release)
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<ButtonPress-3>", self._c_right)

        S, V = self.s_vars, self.v_vars

        # --- file / help
        f = self._section(panel, "File")
        self._btnrow(f, [("Save mask... (Ctrl+S)", self.save_mask), ("Help (F1)", self.show_help)],
                     pady=0)

        # --- source
        self.src_frame = f = self._section(panel, "Source")
        self.source = tk.StringVar(value="Gradient")
        r = ttk.Frame(f)
        r.pack(fill="x")
        for m in ("Gradient", "PNG"):
            ttk.Radiobutton(r, text=m, value=m, variable=self.source).pack(side="left", padx=(0, 12))
        self.source.trace_add("write", lambda *_: self._apply_source())

        # --- gradient
        self.grad_frame = f = ttk.LabelFrame(panel, text="Gradient", padding=6)
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Label(r, text="W").pack(side="left")
        self.w_var = tk.StringVar(value="128")
        ttk.Spinbox(r, values=SIZES, textvariable=self.w_var, width=6).pack(side="left", padx=(2, 10))
        ttk.Label(r, text="H").pack(side="left")
        self.h_var = tk.StringVar(value="128")
        ttk.Spinbox(r, values=SIZES, textvariable=self.h_var, width=6).pack(side="left", padx=2)
        self.w_var.trace_add("write", lambda *_: self._size_changed())
        self.h_var.trace_add("write", lambda *_: self._size_changed())
        r = ttk.Frame(f)
        r.pack(fill="x", pady=(4, 0))
        ttk.Label(r, text="Direction").pack(side="left")
        for text, d in (("\u2193", "down"), ("\u2191", "up"), ("\u2192", "right"), ("\u2190", "left")):
            ttk.Button(r, text=text, width=3, command=lambda d=d: self._direction(d)).pack(side="left", padx=1)

        self.ramp = tk.Canvas(f, width=self.RAMP_W + 2 * self.RAMP_PAD, height=self.RAMP_H + 18,
                              bg=self.bgc, highlightthickness=0)
        self.ramp.pack(pady=(6, 2))
        self.ramp.bind("<ButtonPress-1>", self._ramp_press)
        self.ramp.bind("<B1-Motion>", self._ramp_drag)
        self.ramp.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.ramp.bind("<ButtonPress-3>", self._ramp_right)

        self.node_lbl = tk.StringVar(value="No node selected")
        ttk.Label(f, textvariable=self.node_lbl, foreground="#555").pack(anchor="w")
        self.pos_var = tk.StringVar()
        self.pos_ss = SliderSpin(self, f, "Position %", self.pos_var, 0.1, 99.9, 0.5, "%.1f", 50.0)
        self.tr_var = tk.StringVar()
        self.tr_ss = SliderSpin(self, f, "Transparency %", self.tr_var, 0, 100, 1, None, 50)
        self.pos_var.trace_add("write", lambda *_: self._node_edit())
        self.tr_var.trace_add("write", lambda *_: self._node_edit())

        r = ttk.Frame(f)
        r.pack(fill="x", pady=(6, 0))
        ttk.Label(r, text="Library").pack(side="left")
        self.grad_name = tk.StringVar()
        self.grad_combo = ttk.Combobox(r, textvariable=self.grad_name, state="readonly", width=24)
        self.grad_combo.pack(side="right")
        self.grad_combo.bind("<<ComboboxSelected>>", lambda e: self._grad_lib_load())
        self._btnrow(f, [("Save as...", self._grad_lib_save), ("Delete", self._grad_lib_delete),
                         ("Reset", self._grad_reset)])

        # --- png
        self.png_frame = f = ttk.LabelFrame(panel, text="PNG", padding=6)
        self._btnrow(f, [("Load PNG... (Ctrl+O)", self.open_png)], pady=0)
        self.png_name = tk.StringVar(value="(none loaded)")
        ttk.Label(f, textvariable=self.png_name, foreground="#555").pack(anchor="w", pady=(4, 0))

        # --- background
        self.bg_frame = f = self._section(panel, "Background")
        bgvar = tk.StringVar(value=VIEW_DEFAULTS["bgmode"])
        r = ttk.Frame(f)
        r.pack(fill="x")
        for m in ("Solid", "Transparent", "Image"):
            ttk.Radiobutton(r, text=m, value=m, variable=bgvar).pack(side="left", padx=(0, 8))
        V["bgmode"] = (bgvar, "str", None)
        bgvar.trace_add("write", lambda *_: self.schedule(False))
        r = ttk.Frame(f)
        r.pack(fill="x", pady=(4, 0))
        ttk.Button(r, text="Colour...", command=self.pick_colour).pack(side="left")
        self.swatch = tk.Label(r, width=4, relief="sunken", bg=self._hex(self.bg_color))
        self.swatch.pack(side="left", padx=6)
        ttk.Button(r, text="Image...", command=self.pick_bg_image).pack(side="left")
        self.bg_name = tk.StringVar(value="(no image)")
        ttk.Label(f, textvariable=self.bg_name, foreground="#555").pack(anchor="w")

        # --- view
        f = self._section(panel, "View")
        self._add_bool(f, V, "dither", "Dither  (D)", VIEW_DEFAULTS["dither"], False)
        self._add_combo(f, V, "view", "Mode", VIEW_MODES, VIEW_DEFAULTS["view"], False)
        self._add_num(f, V, "zoom", "Zoom", 1, 16, 1, "int", VIEW_DEFAULTS["zoom"], False)
        self._add_bool(f, V, "tile", "Tile 3x3 (check seams)", VIEW_DEFAULTS["tile"], False)
        self._add_num(f, V, "distance", "Distance (1/n)", 1, 8, 1, "int", VIEW_DEFAULTS["distance"], False)
        self._add_combo(f, V, "sampling", "Sampling", SAMPLING, VIEW_DEFAULTS["sampling"], False)

        # --- presets
        f = self._section(panel, "Dither presets")
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Label(r, text="Library").pack(side="left")
        self.preset_name = tk.StringVar()
        self.preset_combo = ttk.Combobox(r, textvariable=self.preset_name, state="readonly", width=24)
        self.preset_combo.pack(side="right")
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self._preset_lib_load())
        self.preset_desc = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.preset_desc, foreground="#555", wraplength=380,
                  justify="left").pack(anchor="w", pady=(2, 0))
        self._btnrow(f, [("Save as...", self._preset_lib_save), ("Delete", self._preset_lib_delete),
                         ("Reset", self._preset_reset)])
        self._btnrow(f, [("Import...", self._preset_import), ("Export...", self._preset_export)])

        # --- shaping
        f = self._section(panel, "Alpha shaping")
        self._add_num(f, S, "black", "Black point", 0, 254, 1, "int", DEFAULTS["black"], True)
        self._add_num(f, S, "white", "White point", 1, 255, 1, "int", DEFAULTS["white"], True)
        self._add_num(f, S, "gamma", "Gamma", 0.05, 10, 0.05, "float", DEFAULTS["gamma"], True,
                      srange=(0.1, 10.0), log=True)
        self._add_num(f, S, "contrast", "Contrast", -100, 99, 5, "int", DEFAULTS["contrast"], True)
        self._add_num(f, S, "blur", "Blur (sigma)", 0, 32, 0.25, "float", DEFAULTS["blur"], True,
                      srange=(0.0, 8.0))
        self._add_bool(f, S, "invert", "Invert", DEFAULTS["invert"], True)

        # --- protect
        f = self._section(panel, "Protect (source alpha; -1 / 256 = off)")
        self._add_num(f, S, "protect_lo", "Transparent <=", -1, 254, 1, "int", DEFAULTS["protect_lo"], True)
        self._add_num(f, S, "protect_hi", "Opaque >=", 1, 256, 1, "int", DEFAULTS["protect_hi"], True)

        # --- dither
        f = self._section(panel, "Dither")
        self._add_combo(f, S, "algorithm", "Algorithm", ALGORITHMS, DEFAULTS["algorithm"], True)
        self._add_num(f, S, "strength", "Strength %", 0, 200, 5, "int", DEFAULTS["strength"], True)
        self._add_bool(f, S, "serpentine", "Serpentine scan", DEFAULTS["serpentine"], True)
        self._add_combo(f, S, "scale", "Pattern scale", ["1", "2", "3", "4", "6", "8"],
                        DEFAULTS["scale"], True, kind="int", width=6)
        self._add_seed(f, S)
        self._add_bool(f, S, "seamless", "Seamless (texture tiles)", DEFAULTS["seamless"], True)

        self._refresh_libs()

    # ================= source =================
    def _apply_source(self):
        if self.source.get() == "Gradient":
            self.png_frame.pack_forget()
            self.grad_frame.pack(after=self.src_frame, fill="x", pady=(0, 6))
        else:
            self.grad_frame.pack_forget()
            self.png_frame.pack(after=self.src_frame, fill="x", pady=(0, 6))
        self._refresh_alpha()
        self._draw_ramp()
        self._sync_node_panel()

    def _refresh_alpha(self):
        if self.source.get() == "Gradient":
            self.alpha = gradient_alpha(self.grad)
            self.has_alpha = True
        else:
            self.alpha = self.png_alpha
            self.has_alpha = self.png_has_alpha
        self.mask = None
        self.schedule(True)

    def open_png(self):
        initial = str(self.png_path.parent) if self.png_path else None
        p = filedialog.askopenfilename(title="Load PNG", initialdir=initial,
                                       filetypes=[("PNG images", "*.png"), ("All files", "*.*")])
        if p and self._load_png(p):
            if self.source.get() != "PNG":
                self.source.set("PNG")
            else:
                self._refresh_alpha()

    def _load_png(self, path):
        try:
            alpha, has_alpha = load_png_alpha(path)
        except Exception as e:
            messagebox.showerror("alphadither", f"Could not load PNG:\n{e}")
            return False
        self.png_alpha, self.png_has_alpha = alpha, has_alpha
        self.png_path = Path(path)
        self.png_name.set(self.png_path.name)
        return True

    # ================= gradient editing =================
    def _sync_size_panel(self):
        self._suppress = True
        self.w_var.set(str(self.grad["width"]))
        self.h_var.set(str(self.grad["height"]))
        self._suppress = False

    def _size_changed(self):
        if self._suppress:
            return
        try:
            w = int(float(self.w_var.get()))
            h = int(float(self.h_var.get()))
        except ValueError:
            return
        w = min(max(w, 1), 4096)
        h = min(max(h, 1), 4096)
        ow, oh = self.grad["width"], self.grad["height"]
        if (w, h) == (ow, oh):
            return
        fx, fy = w / ow, h / oh
        for k in ("start", "end"):
            self.grad[k] = [self.grad[k][0] * fx, self.grad[k][1] * fy]
        self.grad["width"], self.grad["height"] = w, h
        self._grad_changed()

    def _direction(self, d):
        W, H = self.grad["width"], self.grad["height"]
        pts = {"down": ([W / 2, 0], [W / 2, H]), "up": ([W / 2, H], [W / 2, 0]),
               "right": ([0, H / 2], [W, H / 2]), "left": ([W, H / 2], [0, H / 2])}[d]
        self.grad["start"], self.grad["end"] = [float(v) for v in pts[0]], [float(v) for v in pts[1]]
        self._grad_changed()

    def _grad_reset(self):
        self.grad = default_gradient(self.grad["width"], self.grad["height"])
        self.sel = None
        self.grad_name.set("")
        self._grad_changed()

    def _grad_changed(self, fast=False, sync_panel=True):
        if self.source.get() == "Gradient":
            self.alpha = gradient_alpha(self.grad)
            self.has_alpha = True
            self._need_proc = True
        self._draw_ramp()
        if sync_panel:
            self._sync_node_panel()
        self.render_overlay()
        self.schedule(True, 25 if fast else 120)

    def _add_node(self, t):
        t = min(max(t, 0.001), 0.999)
        xp, fp = grad_profile_points(self.grad)
        a = float(np.interp(t, xp, fp))
        n = {"t": t, "tr": float(round((1 - a) * 100))}
        self.grad["nodes"].append(n)
        self.sel = n
        self.drag = n
        self._grad_changed()

    def _delete_node(self, node):
        self.grad["nodes"] = [n for n in self.grad["nodes"] if n is not node]
        if self.sel is node:
            self.sel = None
        if self.drag is node:
            self.drag = None
        self._grad_changed()

    def _nudge_node(self, node, notches, fine):
        step = 1 if fine else 5
        node["tr"] = min(max(round(node["tr"] - notches * step), 0), 100)
        self.sel = node
        self._grad_changed(fast=True)

    def _sync_node_panel(self):
        self._suppress = True
        sel = self.sel
        if isinstance(sel, dict):
            self.node_lbl.set("Mid node")
            self.pos_var.set(f"{sel['t'] * 100:.1f}")
            self.tr_var.set(f"{sel['tr']:.0f}")
            state = ["!disabled"]
        elif sel == "start":
            self.node_lbl.set("Start node - always 100% opaque")
            self.pos_var.set("0.0")
            self.tr_var.set("0")
            state = ["disabled"]
        elif sel == "end":
            self.node_lbl.set("End node - always 100% transparent")
            self.pos_var.set("100.0")
            self.tr_var.set("100")
            state = ["disabled"]
        else:
            self.node_lbl.set("No node selected - click the line to add one")
            self.pos_var.set("")
            self.tr_var.set("")
            state = ["disabled"]
        on = state == ["!disabled"]
        self.pos_ss.set_enabled(on)
        self.tr_ss.set_enabled(on)
        self._suppress = False

    def _node_edit(self):
        if self._suppress or not isinstance(self.sel, dict):
            return
        try:
            p = float(self.pos_var.get())
            tr = float(self.tr_var.get())
        except ValueError:
            return
        self.sel["t"] = min(max(p / 100.0, 0.001), 0.999)
        self.sel["tr"] = min(max(tr, 0.0), 100.0)
        self._grad_changed(fast=True, sync_panel=False)

    # ---------- ramp strip ----------
    def _draw_ramp(self):
        rc = self.ramp
        rc.delete("all")
        w, h, px = self.RAMP_W, self.RAMP_H, self.RAMP_PAD
        t = (np.arange(w) + 0.5) / w
        xp, fp = grad_profile_points(self.grad)
        a = np.interp(t, xp, fp)
        yy, xx = np.indices((h, w))
        chk = np.where(((yy // 6 + xx // 6) & 1) == 1, 205.0, 160.0)
        img = (chk * (1 - a[None, :]) + 0.5).astype(np.uint8)
        self._ramp_photo = ImageTk.PhotoImage(Image.fromarray(img))
        rc.create_image(px, 2, anchor="nw", image=self._ramp_photo)
        rc.create_rectangle(px - 1, 1, px + w, 2 + h, outline="#555")

        def tri(t, grey, selected):
            x = px + t * w
            rc.create_polygon(x, h + 4, x - 6, h + 15, x + 6, h + 15,
                              fill=self._hex((grey, grey, grey)),
                              outline="#ff9d00" if selected else "#333",
                              width=2 if selected else 1)

        tri(0.0, 0, self.sel == "start")
        tri(1.0, 255, self.sel == "end")
        for n in self.grad["nodes"]:
            g = int(255 * n["tr"] / 100)
            tri(n["t"], g, self.sel is n)

    def _ramp_hit(self, x):
        w, px = self.RAMP_W, self.RAMP_PAD
        best, bd = None, 7
        for n in self.grad["nodes"]:
            d = abs(px + n["t"] * w - x)
            if d < bd:
                best, bd = n, d
        if best is None:
            if abs(x - px) < 7:
                return "start"
            if abs(x - (px + w)) < 7:
                return "end"
        return best

    def _ramp_press(self, e):
        if self.source.get() != "Gradient":
            return
        hit = self._ramp_hit(e.x)
        if hit is not None:
            self.sel = hit
            self.drag = hit if isinstance(hit, dict) else None
            self._draw_ramp()
            self._sync_node_panel()
            self.render_overlay()
            return
        t = (e.x - self.RAMP_PAD) / self.RAMP_W
        if 0 < t < 1:
            self._add_node(t)

    def _ramp_drag(self, e):
        if isinstance(self.drag, dict):
            t = (e.x - self.RAMP_PAD) / self.RAMP_W
            self.drag["t"] = min(max(t, 0.001), 0.999)
            self._grad_changed(fast=True)

    def _ramp_right(self, e):
        hit = self._ramp_hit(e.x)
        if isinstance(hit, dict):
            self._delete_node(hit)

    # ---------- canvas handles ----------
    def _i2c(self, px, py):
        ox, oy = self._origin
        z = self._zoom
        return self.PAD + (ox + px) * z, self.PAD + (oy + py) * z

    def _c2i(self, cx, cy):
        ox, oy = self._origin
        z = self._zoom
        return (cx - self.PAD) / z - ox, (cy - self.PAD) / z - oy

    def _node_img_xy(self, n):
        (sx, sy), (ex, ey) = self.grad["start"], self.grad["end"]
        return sx + n["t"] * (ex - sx), sy + n["t"] * (ey - sy)

    def render_overlay(self):
        c = self.canvas
        c.delete("h")
        if not self.handles_on:
            return
        x0, y0 = self._i2c(*self.grad["start"])
        x1, y1 = self._i2c(*self.grad["end"])
        c.create_line(x0, y0, x1, y1, fill="#000000", width=3, tags="h")
        c.create_line(x0, y0, x1, y1, fill="#ffffff", width=1, tags="h")
        for key, fill, outline, r in (("start", "#000000", "#ffffff", 7), ("end", "#ffffff", "#000000", 7)):
            x, y = self._i2c(*self.grad[key])
            sel = self.sel == key
            c.create_oval(x - r, y - r, x + r, y + r, fill=fill,
                          outline="#ff9d00" if sel else outline, width=3 if sel else 2, tags="h")
        for n in self.grad["nodes"]:
            x, y = self._i2c(*self._node_img_xy(n))
            g = int(255 * n["tr"] / 100)
            sel = self.sel is n
            r = 6 if sel else 5
            c.create_oval(x - r, y - r, x + r, y + r, fill=self._hex((g, g, g)),
                          outline="#ff9d00" if sel else "#888888", width=2, tags="h")
            if sel:
                c.create_text(x + 11, y - 11, text=f"{n['tr']:.0f}%", anchor="w",
                              fill="#ff9d00", font=("Segoe UI", 10, "bold"), tags="h")

    def _canvas_hit(self, cx, cy):
        for n in reversed(self.grad["nodes"]):
            x, y = self._i2c(*self._node_img_xy(n))
            if math.hypot(cx - x, cy - y) <= 8:
                return n
        for key in ("start", "end"):
            x, y = self._i2c(*self.grad[key])
            if math.hypot(cx - x, cy - y) <= 10:
                return key
        return None

    def _line_project(self, cx, cy):
        px, py = self._c2i(cx, cy)
        (sx, sy), (ex, ey) = self.grad["start"], self.grad["end"]
        dx, dy = ex - sx, ey - sy
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            return None, float("inf")
        t = ((px - sx) * dx + (py - sy) * dy) / L2
        qx, qy = sx + t * dx, sy + t * dy
        return t, math.hypot(px - qx, py - qy) * self._zoom

    def _c_press(self, e):
        self.canvas.focus_set()
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        if self.handles_on:
            hit = self._canvas_hit(cx, cy)
            if hit is not None:
                self.sel = hit
                self.drag = hit
                self._draw_ramp()
                self._sync_node_panel()
                self.render_overlay()
                return
            t, dist = self._line_project(cx, cy)
            if t is not None and 0 < t < 1 and dist <= 6:
                self._add_node(t)
                return
        self.drag = None
        self.canvas.scan_mark(e.x, e.y)

    def _c_drag(self, e):
        if self.drag is None:
            self.canvas.scan_dragto(e.x, e.y, gain=1)
            return
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        if isinstance(self.drag, dict):
            t, _ = self._line_project(cx, cy)
            if t is not None:
                self.drag["t"] = min(max(t, 0.001), 0.999)
        else:
            px, py = self._c2i(cx, cy)
            if e.state & 0x1:  # shift: 45 degree snap
                ox, oy = self.grad["end" if self.drag == "start" else "start"]
                vx, vy = px - ox, py - oy
                L = math.hypot(vx, vy)
                ang = round(math.atan2(vy, vx) / (math.pi / 4)) * (math.pi / 4)
                px, py = ox + L * math.cos(ang), oy + L * math.sin(ang)
            if e.state & 0x4:  # ctrl: whole pixels
                px, py = round(px), round(py)
            self.grad[self.drag] = [px, py]
        self._grad_changed(fast=True)

    def _c_release(self, e):
        self.drag = None

    def _c_right(self, e):
        if not self.handles_on:
            return
        hit = self._canvas_hit(self.canvas.canvasx(e.x), self.canvas.canvasy(e.y))
        if isinstance(hit, dict):
            self._delete_node(hit)

    # ================= keys / wheel =================
    def _typing(self):
        w = self.root.focus_get()
        return w is not None and w.winfo_class() in ("TSpinbox", "TEntry", "Entry", "Spinbox",
                                                       "TCombobox", "Text")

    def _key_dither(self, e):
        if self._typing():
            return
        var = self.v_vars["dither"][0]
        var.set(not var.get())

    def _key_delete(self, e):
        if self._typing():
            return
        if isinstance(self.sel, dict):
            self._delete_node(self.sel)

    def _on_wheel(self, e):
        w = self.root.winfo_containing(e.x_root, e.y_root)
        if w is None:
            return
        notches = 1 if e.delta > 0 else -1
        fine = bool(e.state & 0x1)
        if w is self.ramp and self.source.get() == "Gradient":
            hit = self._ramp_hit(e.x_root - self.ramp.winfo_rootx())
            if isinstance(hit, dict):
                self._nudge_node(hit, notches, fine)
            return
        if str(w).startswith(str(self.pcanvas)):
            if w.winfo_class() in ("TSpinbox", "TCombobox"):
                return
            self.pcanvas.yview_scroll(-notches, "units")
            return
        if w is self.canvas:
            cx = self.canvas.canvasx(e.x_root - self.canvas.winfo_rootx())
            cy = self.canvas.canvasy(e.y_root - self.canvas.winfo_rooty())
            if self.handles_on:
                hit = self._canvas_hit(cx, cy)
                if isinstance(hit, dict):
                    self._nudge_node(hit, notches, fine)
                    return
            if e.state & 0x4:
                var = self.v_vars["zoom"][0]
                var.set(str(min(max(self.get_view()["zoom"] + notches, 1), 16)))
            elif e.state & 0x1:
                self.canvas.xview_scroll(-notches * 3, "units")
            else:
                self.canvas.yview_scroll(-notches * 3, "units")

    # ================= processing / render =================
    def schedule(self, reprocess, delay=120):
        if self._slider_active:
            delay = min(delay, 25)
        self._need_proc = self._need_proc or reprocess
        if self._job:
            self.root.after_cancel(self._job)
        self._job = self.root.after(delay, self._update)

    def _update(self):
        self._job = None
        if self.alpha is None:
            self.mask = None
            self._placeholder()
            return
        if self._need_proc or self.mask is None:
            s = self.get_settings()
            if s["algorithm"] == "Blue noise" and not blue_noise_ready():
                self.status.set("Generating blue-noise matrix (one-off)...")
                self.root.update_idletasks()
            t = time.perf_counter()
            self.mask, self.shaped = process(self.alpha, s)
            self.proc_ms = (time.perf_counter() - t) * 1000
            self._need_proc = False
        self.render()

    def flush(self):
        if self._job:
            self.root.after_cancel(self._job)
            self._job = None
            self._update()

    @staticmethod
    def _hex(c):
        return "#%02x%02x%02x" % tuple(int(x) for x in c)

    def _make_bg(self, H, W, mode):
        if mode == "Image" and self.bg_image is not None:
            bh, bw = self.bg_image.shape[:2]
            return np.tile(self.bg_image, (H // bh + 1, W // bw + 1, 1))[:H, :W].astype(np.float32)
        if mode == "Transparent":
            y, x = np.indices((H, W))
            c = ((y // 8 + x // 8) & 1).astype(bool)[..., None]
            return np.where(c, np.float32(205), np.float32(160)) * np.ones(3, np.float32)
        return np.full((H, W, 3), self.bg_color, np.float32)

    @staticmethod
    def _distance(img, d, sampling):
        if d <= 1:
            return img
        if sampling.startswith("Point"):
            return np.ascontiguousarray(img[::d, ::d])
        h, w = img.shape[:2]
        hh, ww = h // d * d, w // d * d
        if hh == 0 or ww == 0:
            return img
        return (img[:hh, :ww].reshape(hh // d, d, ww // d, d, 3).mean(axis=(1, 3)) + 0.5).astype(np.uint8)

    def render(self):
        if self.mask is None:
            return
        v = self.get_view()
        s = self._good_s
        tiles = 3 if v["tile"] else 1
        H, W = self.mask.shape
        TH, TW = H * tiles, W * tiles
        dith = self.mask.astype(np.float32) / 255.0
        smooth = self.shaped.astype(np.float32)
        show = dith if v["dither"] else smooth
        bg = self._make_bg(TH, TW, v["bgmode"])

        def comp(a01):
            a = np.tile(a01, (tiles, tiles))[..., None]
            return (bg * (1 - a) + 0.5).astype(np.uint8)   # opaque pixels are black

        ox = W if tiles == 3 else 0
        oy = H if tiles == 3 else 0
        mode = v["view"]
        if mode == "Side by side":
            panels = [comp(smooth), comp(show)]
            ox += TW + 4
        elif mode == "Mask (B/W)":
            m = (np.tile(show, (tiles, tiles)) * 255 + 0.5).astype(np.uint8)
            panels = [np.dstack([m, m, m])]
        else:
            panels = [comp(show)]

        panels = [self._distance(p, v["distance"], v["sampling"]) for p in panels]
        if len(panels) == 2:
            gap = np.full((panels[0].shape[0], 4, 3), 20, np.uint8)
            img = np.hstack([panels[0], gap, panels[1]])
        else:
            img = panels[0]

        pil = Image.fromarray(np.ascontiguousarray(img))
        z = v["zoom"]
        if z > 1:
            pil = pil.resize((pil.width * z, pil.height * z), Image.NEAREST)
        self._photo = ImageTk.PhotoImage(pil)
        self.canvas.delete("all")
        self.canvas.create_image(self.PAD, self.PAD, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, pil.width + 2 * self.PAD, pil.height + 2 * self.PAD))

        self._origin = (ox, oy)
        self._zoom = z
        self.handles_on = self.source.get() == "Gradient" and v["distance"] == 1
        self.render_overlay()

        parts = [f"{W}x{H}",
                 f"source {self.alpha.mean() * 100:.1f}%",
                 f"target {self.shaped.mean() * 100:.1f}%",
                 f"mask {(self.mask > 0).mean() * 100:.1f}% opaque",
                 s["algorithm"] + ("" if v["dither"] else "  [DITHER OFF]"),
                 f"{self.proc_ms:.0f} ms"]
        per = pattern_period(s)
        if s["seamless"] and per and (W % per or H % per):
            parts.append(f"note: {W}x{H} not a multiple of {per} - pattern won't tile cleanly")
        if not self.has_alpha:
            parts.insert(0, "NO ALPHA - PNG is fully opaque")
        self.status.set("   |   ".join(parts))

    def _placeholder(self):
        self.canvas.delete("all")
        self.handles_on = False
        self.canvas.create_text(20, 20, anchor="nw", fill="#888", font=("Segoe UI", 14),
                                text="Load a PNG (Ctrl+O) or switch Source to Gradient")
        self.status.set("")

    # ================= background =================
    def pick_colour(self):
        res = colorchooser.askcolor(color=self._hex(self.bg_color), title="Background colour")
        if res and res[0]:
            self.bg_color = tuple(int(c) for c in res[0])
            self.swatch.configure(bg=self._hex(self.bg_color))
            self.v_vars["bgmode"][0].set("Solid")
            self.schedule(False)

    def pick_bg_image(self):
        p = filedialog.askopenfilename(title="Background image",
                                       filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"),
                                                  ("All files", "*.*")])
        if p and self._load_bg_image(p):
            self.v_vars["bgmode"][0].set("Image")
            self.schedule(False)

    def _load_bg_image(self, p):
        try:
            self.bg_image = np.array(Image.open(p).convert("RGB"))
        except Exception as e:
            messagebox.showerror("alphadither", f"Could not load background:\n{e}")
            return False
        self.bg_image_path = str(p)
        self.bg_name.set(Path(p).name)
        return True

    # ================= saving =================
    def save_mask(self):
        if self.alpha is None:
            messagebox.showinfo("alphadither", "Nothing to save yet.")
            return
        self.flush()
        if self.source.get() == "PNG" and self.png_path:
            initdir = str(self.png_path.parent)
            name = self.png_path.stem + "-mask.png"
        else:
            initdir = self.last_save_dir
            name = (self.grad_name.get() or "gradient") + "-mask.png"
        p = filedialog.asksaveasfilename(title="Save mask", initialdir=initdir, initialfile=name,
                                         defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not p:
            return
        try:
            write_mask(p, self.mask)
        except Exception as e:
            messagebox.showerror("alphadither", f"Save failed:\n{e}")
            return
        self.last_save_dir = str(Path(p).parent)
        self.status.set(f"Saved {p}")

    # ================= libraries =================
    def _refresh_libs(self):
        self.preset_combo["values"] = ([BUILTIN_PREFIX + n for n, _, _ in BUILTIN_PRESETS]
                                       + lib_names("presets", PRESET_EXT))
        self.grad_combo["values"] = lib_names("gradients", GRAD_EXT)

    def _ask_name(self, title, initial):
        name = simpledialog.askstring(title, "Name:", initialvalue=initial or "", parent=self.root)
        if not name:
            return None
        name = safe_name(name)
        return name or None

    def _preset_lib_load(self):
        name = self.preset_name.get()
        if not name:
            return
        if name.startswith(BUILTIN_PREFIX):
            b = find_builtin(name)
            if b:
                self.set_settings(b[2])
                self.preset_desc.set(b[1])
            return
        try:
            self.set_settings(load_preset(lib_dir("presets") / (name + PRESET_EXT)))
            self.preset_desc.set("Your preset.")
        except Exception as e:
            messagebox.showerror("alphadither", f"Could not load preset:\n{e}")

    def _preset_reset(self):
        self.set_settings(DEFAULTS)
        self.preset_name.set("")
        self.preset_desc.set("")

    def _plain_name(self):
        n = self.preset_name.get()
        return n[len(BUILTIN_PREFIX):] if n.startswith(BUILTIN_PREFIX) else n

    def _preset_lib_save(self):
        initial = self._plain_name()
        if self.preset_name.get().startswith(BUILTIN_PREFIX):
            initial += " (mine)"
        name = self._ask_name("Save dither preset", initial)
        if name:
            name = name.lstrip(BUILTIN_PREFIX.strip()).strip()
        if not name:
            return
        p = lib_dir("presets") / (name + PRESET_EXT)
        if p.exists() and not messagebox.askyesno("alphadither", f"Overwrite preset '{name}'?"):
            return
        save_preset(p, self.get_settings())
        self._refresh_libs()
        self.preset_name.set(name)
        self.preset_desc.set("Your preset.")

    def _preset_lib_delete(self):
        name = self.preset_name.get()
        if not name:
            return
        if name.startswith(BUILTIN_PREFIX):
            messagebox.showinfo("alphadither", "Built-in presets can't be deleted.")
            return
        if not messagebox.askyesno("alphadither", f"Delete preset '{name}'?"):
            return
        try:
            (lib_dir("presets") / (name + PRESET_EXT)).unlink()
        except OSError:
            pass
        self.preset_name.set("")
        self.preset_desc.set("")
        self._refresh_libs()

    def _preset_import(self):
        p = filedialog.askopenfilename(title="Import preset",
                                       filetypes=[("alphadither preset", "*" + PRESET_EXT),
                                                  ("JSON", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            s = load_preset(p)
        except Exception as e:
            messagebox.showerror("alphadither", f"Could not load preset:\n{e}")
            return
        self.set_settings(s)
        stem = Path(p).name
        stem = stem[:-len(PRESET_EXT)] if stem.lower().endswith(PRESET_EXT) else Path(p).stem
        name = safe_name(stem)
        dest = lib_dir("presets") / (name + PRESET_EXT)
        if not dest.exists() or messagebox.askyesno("alphadither", f"Add to library as '{name}' (overwrite)?"):
            save_preset(dest, s)
            self._refresh_libs()
            self.preset_name.set(name)

    def _preset_export(self):
        initial = safe_name(self._plain_name() or "preset") + PRESET_EXT
        p = filedialog.asksaveasfilename(title="Export preset", initialfile=initial,
                                         defaultextension=PRESET_EXT,
                                         filetypes=[("alphadither preset", "*" + PRESET_EXT)])
        if p:
            save_preset(p, self.get_settings())

    def _grad_lib_load(self):
        name = self.grad_name.get()
        if not name:
            return
        try:
            self.grad = load_gradient(lib_dir("gradients") / (name + GRAD_EXT))
        except Exception as e:
            messagebox.showerror("alphadither", f"Could not load gradient:\n{e}")
            return
        self.sel = None
        self._sync_size_panel()
        self._grad_changed()

    def _grad_lib_save(self):
        name = self._ask_name("Save gradient", self.grad_name.get())
        if not name:
            return
        p = lib_dir("gradients") / (name + GRAD_EXT)
        if p.exists() and not messagebox.askyesno("alphadither", f"Overwrite gradient '{name}'?"):
            return
        save_gradient(p, self.grad)
        self._refresh_libs()
        self.grad_name.set(name)

    def _grad_lib_delete(self):
        name = self.grad_name.get()
        if not name or not messagebox.askyesno("alphadither", f"Delete gradient '{name}'?"):
            return
        try:
            (lib_dir("gradients") / (name + GRAD_EXT)).unlink()
        except OSError:
            pass
        self.grad_name.set("")
        self._refresh_libs()

    # ================= session =================
    def _session_path(self):
        return app_dir() / "session.json"

    def _load_session(self):
        try:
            with open(self._session_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        try:
            self.set_settings(sanitize_settings(d.get("settings", {})))
            view = dict(VIEW_DEFAULTS)
            view.update({k: v for k, v in d.get("view", {}).items() if k in VIEW_DEFAULTS})
            self._set_store(self.v_vars, view)
            self.grad = sanitize_gradient(d.get("gradient", {}))
            self.grad_name.set(d.get("grad_name", ""))
            self.preset_name.set(d.get("preset_name", ""))
            pn = self.preset_name.get()
            b = find_builtin(pn) if pn.startswith(BUILTIN_PREFIX) else None
            self.preset_desc.set(b[1] if b else ("Your preset." if pn else ""))
            if d.get("bg_color"):
                self.bg_color = tuple(int(c) for c in d["bg_color"])[:3]
                self.swatch.configure(bg=self._hex(self.bg_color))
            if d.get("bg_image") and Path(d["bg_image"]).is_file():
                self._load_bg_image(d["bg_image"])
            if d.get("png") and Path(d["png"]).is_file():
                self._load_png(d["png"])
            self.last_save_dir = d.get("last_save_dir")
            if d.get("source") in ("Gradient", "PNG"):
                self.source.set(d["source"])
            if d.get("geometry"):
                self.root.geometry(d["geometry"])
        except Exception:
            pass

    def _on_close(self):
        try:
            d = {
                "settings": self.get_settings(),
                "view": self.get_view(),
                "gradient": self.grad,
                "grad_name": self.grad_name.get(),
                "preset_name": self.preset_name.get(),
                "source": self.source.get(),
                "png": str(self.png_path) if self.png_path else None,
                "bg_color": list(self.bg_color),
                "bg_image": self.bg_image_path,
                "last_save_dir": self.last_save_dir,
                "geometry": self.root.geometry(),
            }
            with open(self._session_path(), "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
        except Exception:
            pass
        self.root.destroy()

    # ================= help =================
    def show_help(self):
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.lift()
            self.help_win.focus_set()
            return
        w = tk.Toplevel(self.root)
        w.title("alphadither - help")
        w.geometry("780x760")
        self.help_win = w
        txt = tk.Text(w, wrap="word", padx=16, pady=10, relief="flat", font=("Segoe UI", 10))
        sb = ttk.Scrollbar(w, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.tag_configure("h1", font=("Segoe UI", 16, "bold"), spacing3=6)
        txt.tag_configure("h2", font=("Segoe UI", 12, "bold"), foreground="#1f5f9f",
                          spacing1=14, spacing3=4)
        txt.tag_configure("p", spacing1=2, spacing3=6)
        txt.tag_configure("i", lmargin1=14, lmargin2=28, spacing3=3)
        txt.tag_configure("term", font=("Segoe UI", 10, "bold"))
        for item in HELP:
            kind = item[0]
            if kind == "BUILTINS":
                for n, desc, _ in BUILTIN_PRESETS:
                    txt.insert("end", n, ("i", "term"))
                    txt.insert("end", "  -  " + desc + "\n", "i")
                continue
            if kind == "i":
                txt.insert("end", item[1], ("i", "term"))
                txt.insert("end", "  -  " + item[2] + "\n", "i")
            else:
                txt.insert("end", item[1] + "\n", kind)
        txt.configure(state="disabled")
        w.bind("<Escape>", lambda e: w.destroy())


def run_gui(initial=None):
    if not TK_OK:
        print("alphadither: tkinter / Pillow ImageTk not available.\n"
              "  Re-run the python.org installer with 'tcl/tk and IDLE' ticked, then:\n"
              "  python -m pip install --force-reinstall pillow")
        sys.exit(1)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root, initial)
    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
C = {"h": "\033[1;36m", "o": "\033[33m", "e": "\033[32m", "d": "\033[90m",
     "b": "\033[1m", "r": "\033[31m", "x": "\033[0m"}


def help_text():
    h, o, e, d, b, x = C["h"], C["o"], C["e"], C["d"], C["b"], C["x"]
    return f"""
{b}alphadither{x}  {d}-{x}  smooth alpha gradient -> black/white dithered mask for Doom

{h}USAGE{x}
  {o}alphadither{x}                                 open the GUI (last session restored)
  {o}alphadither{x} <image.png>                     GUI, dithering that PNG's alpha
  {o}alphadither{x} <name{GRAD_EXT}>              GUI, editing that gradient
  {o}alphadither{x} <inputs...> -p <preset>         batch mode (no GUI)

{h}DESCRIPTION{x}
  Doom's software renderers only draw a pixel fully or not at all. alphadither
  turns a smooth alpha (a gradient drawn in the GUI, or a PNG's alpha channel)
  into a mask of pure black and white pixels: white = opaque, black = transparent.
  Full explanation of every option: the Help button (F1) in the GUI.

{h}OUTPUT{x}
  {o}<name>-mask.png{x}        8-bit greyscale, values 0 and 255 only

{h}BATCH{x}  {d}(inputs: .png files, {GRAD_EXT} files, or folders of either){x}
  {o}-p, --preset{x} NAME|FILE  dither preset: built-in name, library name, or {PRESET_EXT} file
  {o}-o, --outdir{x} DIR        write masks here instead of beside each input
  {o}-r, --recursive{x}         recurse into folders
  {o}    --overwrite{x}         replace existing masks {d}(default: skip){x}
  {o}    --list{x}              list built-in and library presets
  {o}-h, --help{x}              this screen

{h}FILES{x}
  {d}%APPDATA%\\alphadither\\presets\\{x}     dither preset library
  {d}%APPDATA%\\alphadither\\gradients\\{x}   gradient library
  {d}%APPDATA%\\alphadither\\session.json{x}  last GUI session

{h}EXAMPLES{x}
  {e}alphadither{x}
  {e}alphadither grate01.png{x}
  {e}alphadither --list{x}
  {e}alphadither fade_down{GRAD_EXT} -p "Smooth fade - clean ends"{x}
  {e}alphadither masks\\src -p bayer4 -r -o masks\\out --overwrite{x}
"""


def collect_inputs(inputs, recursive):
    files = []
    for i in inputs:
        p = Path(i)
        if p.is_dir():
            pats = ("*.png", "*" + GRAD_EXT)
            for pat in pats:
                it = p.rglob(pat) if recursive else p.glob(pat)
                for f in sorted(it):
                    if f.stem.endswith("-mask"):
                        continue
                    files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            print(f"{C['r']}not found:{C['x']} {i}")
    return files


def run_batch(args):
    try:
        s = load_preset_arg(args.preset)
    except Exception as e:
        print(f"{C['r']}could not load preset:{C['x']} {e}")
        return 1
    files = collect_inputs(args.inputs, args.recursive)
    if not files:
        print("nothing to do")
        return 1
    print(f"{C['h']}alphadither{C['x']}  {s['algorithm']}  ({len(files)} input(s))")
    done = skipped = failed = 0
    for f in files:
        is_grad = f.name.lower().endswith(GRAD_EXT)
        stem = f.name[:-len(GRAD_EXT)] if is_grad else f.stem
        out = (Path(args.outdir) if args.outdir else f.parent) / f"{stem}-mask.png"
        if out.exists() and not args.overwrite:
            print(f"  {C['d']}skip (exists){C['x']}  {f}")
            skipped += 1
            continue
        try:
            if is_grad:
                alpha = gradient_alpha(load_gradient(f))
            else:
                alpha, has_alpha = load_png_alpha(f)
                if not has_alpha:
                    print(f"  {C['r']}no alpha{C['x']}       {f}")
                    skipped += 1
                    continue
            t = time.perf_counter()
            mask, shaped = process(alpha, s)
            ms = (time.perf_counter() - t) * 1000
            write_mask(out, mask)
            print(f"  {C['e']}ok{C['x']}  {f}  {C['d']}target {shaped.mean() * 100:.1f}% "
                  f"-> mask {(mask > 0).mean() * 100:.1f}%  {ms:.0f} ms{C['x']}")
            done += 1
        except Exception as e:
            print(f"  {C['r']}fail{C['x']}  {f}: {e}")
            failed += 1
    print(f"done: {done}  skipped: {skipped}  failed: {failed}")
    return 1 if failed else 0


def main():
    if os.name == "nt":
        os.system("")
    ap = argparse.ArgumentParser(prog="alphadither", add_help=False)
    ap.add_argument("inputs", nargs="*")
    ap.add_argument("-p", "--preset")
    ap.add_argument("-o", "--outdir")
    ap.add_argument("-r", "--recursive", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()

    if args.help:
        print(help_text())
        return 0
    if args.list:
        print(f"{C['h']}BUILT-IN PRESETS{C['x']}")
        for n, desc, _ in BUILTIN_PRESETS:
            print(f"  {C['o']}{n}{C['x']}")
            print(f"      {C['d']}{desc}{C['x']}")
        user = lib_names("presets", PRESET_EXT)
        print(f"\n{C['h']}LIBRARY PRESETS{C['x']}  {C['d']}{lib_dir('presets')}{C['x']}")
        for n in user:
            print(f"  {C['o']}{n}{C['x']}")
        if not user:
            print(f"  {C['d']}(none yet){C['x']}")
        return 0
    if args.preset:
        return run_batch(args)
    if len(args.inputs) > 1 or (args.inputs and Path(args.inputs[0]).is_dir()):
        print(f"{C['r']}batch mode needs a preset:{C['x']} -p <name|file>   (see -h)")
        return 1
    run_gui(args.inputs[0] if args.inputs else None)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
