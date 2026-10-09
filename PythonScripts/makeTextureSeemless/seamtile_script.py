#!/usr/bin/env python3
"""
seamtile_script.py - Seamless tile maker with realtime preview

Methods:
  Radial mask  Keeps the centre of the original, builds the edges from a
               half-offset (wrapped) copy, joined through a radial mask with
               a noise-scattered boundary.
  Edge blend   Keeps the image in place; each edge band is cross-faded with
               the band from the opposite side. Tile shrinks by the overlap.
  Edge cut     Same overlap bands, but joined along the best-matching cut
               line instead of a fade. Every pixel is an original pixel.
               Tile shrinks by the overlap.
  Mirror       2x2 mirrored arrangement. Seamless by construction, symmetric,
               tile is double the cropped size.
  Offset only  Half-offset with nothing repaired, for fixing seams by hand.

Shared: crop, nudge (wrap-shift of the finished tile), views, saving.
No resampling, filtering or blurring is ever applied to the output.

Usage:  seamtile [image]
"""

import sys
import os
import json
import random
import argparse


# ---------------------------------------------------------------- deps check
def _dep_check():
    missing = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("pillow")
    tk_ok = True
    try:
        import tkinter  # noqa: F401
    except ImportError:
        tk_ok = False
    if missing or not tk_ok:
        print("seamtile: missing dependencies")
        if missing:
            print("  Install with:  pip install " + " ".join(missing))
        if not tk_ok:
            print("  tkinter not found - reinstall Python with the "
                  "'tcl/tk and IDLE' option enabled.")
        sys.exit(1)


_dep_check()

import numpy as np                                   # noqa: E402
from PIL import Image, ImageTk                       # noqa: E402
import tkinter as tk                                 # noqa: E402
from tkinter import ttk, filedialog, messagebox      # noqa: E402

RS = getattr(Image, "Resampling", Image)

APP_NAME = "seamtile"
GUARD_FRAC = 0.06          # radial: border band (fraction of half-size) where mask is forced to 0
CUT_MAX = 128              # edge cut: max overlap (memory/speed bound for the wrap-aware cut)

CURVES = {
    "smoothstep":   lambda t: t * t * (3.0 - 2.0 * t),
    "smootherstep": lambda t: t * t * t * (t * (t * 6.0 - 15.0) + 10.0),
    "cosine":       lambda t: 0.5 - 0.5 * np.cos(np.pi * t),
    "linear":       lambda t: t,
}

M_RADIAL, M_BLEND, M_CUT, M_MIRROR, M_OFFSET = (
    "Radial mask", "Edge blend", "Edge cut", "Mirror", "Offset only")
METHODS = [M_RADIAL, M_BLEND, M_CUT, M_MIRROR, M_OFFSET]
OVERLAY_METHODS = (M_RADIAL, M_BLEND, M_CUT)

DEFAULTS = {
    "method": M_CUT,
    "crop_top": 0, "crop_bottom": 0, "crop_left": 0, "crop_right": 0,
    # radial
    "inner": 0.35, "outer": 0.95,
    "scatter": 0.15, "detail": 6, "seed": 1234,
    "curve": "smoothstep", "hard": False,
    "center_x": 0, "center_y": 0,
    # edge blend
    "blend_overlap_x": 16, "blend_overlap_y": 16, "blend_curve": "smoothstep",
    # edge cut
    "cut_overlap_x": 24, "cut_overlap_y": 24,
    # shared
    "nudge_x": 0, "nudge_y": 0,
}
VIEW_DEFAULTS = {
    "view": "tiled", "tiles": 3, "seams": True, "overlay": False, "zoom": "100%",
}
ZOOMS = ["25%", "33%", "50%", "100%", "200%", "300%", "400%", "600%", "800%",
         "1200%", "1600%"]
VIEWS = ["tiled", "single", "original"]
MAX_DISPLAY = 12000        # max displayed image dimension in pixels
NO_CACHE_KEYS = ("nudge_x", "nudge_y")


# ---------------------------------------------------------------- radial mask
def smooth_noise(h, w, detail, seed):
    """Smooth value noise in [-1, 1], 3 octaves, deterministic per seed."""
    rng = np.random.default_rng(int(seed))
    total = np.zeros((h, w), np.float32)
    amp, norm = 1.0, 0.0
    longest = max(h, w)
    for octave in range(3):
        cells = max(1.0, float(detail) * (2 ** octave))
        gh = max(2, int(round(cells * h / longest)) + 1)
        gw = max(2, int(round(cells * w / longest)) + 1)
        grid = rng.uniform(-1.0, 1.0, (gh, gw)).astype(np.float32)
        up = Image.fromarray(grid).resize((w, h), RS.BICUBIC)
        total += amp * np.asarray(up, np.float32)
        norm += amp
        amp *= 0.5
    total /= norm
    peak = float(np.max(np.abs(total))) or 1.0
    return total / peak


def build_mask(h, w, inner, outer, scatter, detail, seed, curve, hard):
    """1.0 = keep original, 0.0 = use offset copy. Always 0 on the border."""
    ys = (np.arange(h, dtype=np.float32) + 0.5 - h / 2.0) / (h / 2.0)
    xs = (np.arange(w, dtype=np.float32) + 0.5 - w / 2.0) / (w / 2.0)
    dy, dx = np.meshgrid(ys, xs, indexing="ij")
    r = np.sqrt(dx * dx + dy * dy)
    if scatter > 0:
        r = r + float(scatter) * smooth_noise(h, w, detail, seed)
    if outer <= inner:
        outer = inner + 1e-3
    t = np.clip((r - inner) / (outer - inner), 0.0, 1.0)
    m = 1.0 - CURVES.get(curve, CURVES["smoothstep"])(t)

    # border guard: exact 0 on the outermost pixels, eased in over a small band
    yy = np.arange(h)
    xx = np.arange(w)
    ey = np.minimum(yy, h - 1 - yy)[:, None]
    ex = np.minimum(xx, w - 1 - xx)[None, :]
    e = np.minimum(ey, ex).astype(np.float32)
    guard_px = max(2.0, GUARD_FRAC * min(h, w) / 2.0)
    g = np.clip(e / guard_px, 0.0, 1.0)
    g = g * g * (3.0 - 2.0 * g)
    m = m * g

    if hard:
        m = (m >= 0.5).astype(np.float32)
    return m.astype(np.float32)


def method_radial(O, s):
    h, w = O.shape[:2]
    cx = max(-(w // 2), min(w // 2, int(s["center_x"])))
    cy = max(-(h // 2), min(h // 2, int(s["center_y"])))
    if cx or cy:
        O = np.roll(O, (-cy, -cx), axis=(0, 1))
    S = np.roll(O, (h // 2, w // 2), axis=(0, 1))
    m = build_mask(h, w, float(s["inner"]), float(s["outer"]), float(s["scatter"]),
                   int(s["detail"]), int(s["seed"]), s["curve"], bool(s["hard"]))
    if s["hard"]:
        out = np.where(m[..., None] >= 0.5, O, S)
    else:
        mf = m[..., None]
        out = (O.astype(np.float32) * mf +
               S.astype(np.float32) * (1.0 - mf) + 0.5).astype(np.uint8)
    return out, m


# ---------------------------------------------------------------- edge blend
def _blend_pass(A, k, curve):
    """Horizontal pass: cross-fade left band with right band. Width -> w-k.
    Returns (image, per-column weight of 'own side' for the first w-k columns)."""
    h, w = A.shape[:2]
    t = (np.arange(k, dtype=np.float32) + 0.5) / k
    wl = CURVES.get(curve, CURVES["smoothstep"])(t).astype(np.float32)
    L = A[:, :k].astype(np.float32)
    R = A[:, w - k:].astype(np.float32)
    band = L * wl[None, :, None] + R * (1.0 - wl)[None, :, None]
    out = np.concatenate([np.clip(band + 0.5, 0, 255).astype(np.uint8), A[:, k:w - k]], axis=1)
    col_w = np.ones(w - k, np.float32)
    col_w[:k] = wl
    return out, col_w


def method_edge_blend(O, s):
    h, w = O.shape[:2]
    kx = max(0, min(int(s["blend_overlap_x"]), (w - 1) // 2))
    ky = max(0, min(int(s["blend_overlap_y"]), (h - 1) // 2))
    A = O
    cw = np.ones(w, np.float32)
    rw = np.ones(h, np.float32)
    if kx > 0:
        A, cw = _blend_pass(A, kx, s["blend_curve"])
    if ky > 0:
        At, rw = _blend_pass(A.transpose(1, 0, 2), ky, s["blend_curve"])
        A = At.transpose(1, 0, 2)
    m = np.minimum(rw[:A.shape[0], None], cw[None, :A.shape[1]])
    return np.ascontiguousarray(A), m


# ---------------------------------------------------------------- edge cut
def _dp_path(cost, wrap):
    """Min-cost path through cost (n steps x k states), moving at most 1 state
    per step. With wrap=True the path must end on the state it started on."""
    n, k = cost.shape
    cost = cost.astype(np.float64)
    if not wrap:
        acc = cost[0].copy()
        back = np.zeros((n, k), np.int8)
        idx = np.arange(k)
        for i in range(1, n):
            left = np.full(k, np.inf)
            left[1:] = acc[:-1]
            right = np.full(k, np.inf)
            right[:-1] = acc[1:]
            st = np.stack((left, acc, right))
            a = np.argmin(st, axis=0)
            acc = st[a, idx] + cost[i]
            back[i] = a - 1
        p = np.empty(n, np.int64)
        p[-1] = int(np.argmin(acc))
        for i in range(n - 1, 0, -1):
            p[i - 1] = p[i] + back[i, p[i]]
        return p

    idx = np.arange(k)
    acc = np.full((k, k), np.inf)          # [start state, current state]
    acc[idx, idx] = cost[0]
    back = np.zeros((n, k, k), np.int8)
    for i in range(1, n):
        left = np.full((k, k), np.inf)
        left[:, 1:] = acc[:, :-1]
        right = np.full((k, k), np.inf)
        right[:, :-1] = acc[:, 1:]
        st = np.stack((left, acc, right))
        a = np.argmin(st, axis=0)
        acc = np.take_along_axis(st, a[None], axis=0)[0] + cost[i][None, :]
        back[i] = a - 1
    start = int(np.argmin(acc[idx, idx]))
    p = np.empty(n, np.int64)
    p[-1] = start
    for i in range(n - 1, 0, -1):
        p[i - 1] = p[i] + back[i, start, p[i]]
    return p


def _cut_pass(A, k, wrap):
    """Horizontal pass: join right band (continuing from the tile end) to the
    left band along the best-matching vertical cut. Width -> w-k.
    Returns (image, bool h x k: True where the pixel came from the right band)."""
    h, w = A.shape[:2]
    L = A[:, :k]
    R = A[:, w - k:]
    d = ((L.astype(np.float32) - R.astype(np.float32)) ** 2).sum(axis=-1)
    cost = d[:, 1:] + d[:, :-1]                # boundary between col p-1 (R) and p (L)
    p = _dp_path(cost, wrap) + 1               # p in 1..k-1: col 0 always R, col k-1 always L
    from_r = np.arange(k)[None, :] < p[:, None]
    band = np.where(from_r[..., None], R, L)
    out = np.concatenate([band, A[:, k:w - k]], axis=1)
    return out, from_r


def method_edge_cut(O, s):
    h, w = O.shape[:2]
    kx = max(0, min(int(s["cut_overlap_x"]), (w - 1) // 2, CUT_MAX))
    ky = max(0, min(int(s["cut_overlap_y"]), (h - 1) // 2, CUT_MAX))
    A = O
    m = np.ones((h, w), np.float32)
    if kx >= 2:
        A, from_r = _cut_pass(A, kx, wrap=False)
        m = np.ones(A.shape[:2], np.float32)
        m[:, :kx][from_r] = 0.0
    if ky >= 2:
        hh = A.shape[0]
        At, from_b = _cut_pass(A.transpose(1, 0, 2), ky, wrap=True)
        from_b = from_b.T                       # ky x width: True = from bottom band
        top = np.where(from_b, 0.0, m[:ky]).astype(np.float32)
        m = np.concatenate([top, m[ky:hh - ky]], axis=0)
        A = At.transpose(1, 0, 2)
    return np.ascontiguousarray(A), m


# ---------------------------------------------------------------- simple methods
def method_mirror(O, s):
    top = np.concatenate([O, O[:, ::-1]], axis=1)
    out = np.concatenate([top, top[::-1]], axis=0)
    return np.ascontiguousarray(out), np.ones(out.shape[:2], np.float32)


def method_offset(O, s):
    h, w = O.shape[:2]
    out = np.roll(O, (h // 2, w // 2), axis=(0, 1))
    return out, np.ones((h, w), np.float32)


METHOD_FUNCS = {
    M_RADIAL: method_radial,
    M_BLEND: method_edge_blend,
    M_CUT: method_edge_cut,
    M_MIRROR: method_mirror,
    M_OFFSET: method_offset,
}


class Engine:
    """Runs crop + method, caches the pre-nudge result."""

    def __init__(self):
        self._key = None
        self._res = None

    def process(self, src, token, s):
        """Returns (tile uint8 HxWxC, overlay map float HxW: 1 = own pixels)."""
        key = (token,) + tuple(sorted((k, v) for k, v in s.items()
                                      if k in DEFAULTS and k not in NO_CACHE_KEYS))
        if key != self._key:
            H, W = src.shape[:2]
            t = max(0, int(s["crop_top"]))
            b = max(0, int(s["crop_bottom"]))
            l = max(0, int(s["crop_left"]))
            r = max(0, int(s["crop_right"]))
            if t + b > H - 4 or l + r > W - 4:
                raise ValueError("Crop leaves less than 4 pixels")
            O = src[t:H - b, l:W - r]
            func = METHOD_FUNCS.get(s["method"], method_radial)
            self._res = func(O, s)
            self._key = key
        out, m = self._res
        nx, ny = int(s["nudge_x"]), int(s["nudge_y"])
        if nx or ny:
            out = np.roll(out, (ny, nx), axis=(0, 1))
            m = np.roll(m, (ny, nx), axis=(0, 1))
        return np.ascontiguousarray(out), m


# ---------------------------------------------------------------- image helpers
def load_image(path):
    img = Image.open(path)
    img.load()
    has_alpha = ("A" in img.getbands()) or ("transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")
    return np.array(img, dtype=np.uint8)


def to_display_rgb(arr):
    """RGBA -> RGB over a checkerboard; RGB passes through."""
    if arr.shape[2] == 3:
        return arr
    h, w = arr.shape[:2]
    yy, xx = np.indices((h, w))
    chk = (((yy // 8) + (xx // 8)) % 2).astype(np.float32) * 40.0 + 100.0
    a = arr[..., 3:4].astype(np.float32) / 255.0
    rgb = arr[..., :3].astype(np.float32) * a + chk[..., None] * (1.0 - a)
    return (rgb + 0.5).astype(np.uint8)


def apply_overlay(rgb, m):
    """Tint the pixels that came from the other copy / opposite side."""
    a = ((1.0 - m) * 0.45)[..., None]
    tint = np.array([255.0, 40.0, 40.0], np.float32)
    out = rgb.astype(np.float32) * (1.0 - a) + tint * a
    return (out + 0.5).astype(np.uint8)


# ---------------------------------------------------------------- help text
HELP_TEXT = [
    ("h1", "seamtile"),
    ("", "Turns an image into a tile that repeats without visible seams. "
         "Everything updates live as you change settings."),
    ("h1", "Workflow"),
    ("", "1. Open an image (Ctrl+O, or drag it onto seamtile.bat).\n"
         "2. Crop away any bad edges, vignetting or borders.\n"
         "3. Pick a method and adjust its options while watching the Tiled view.\n"
         "4. Nudge the tile so the part you care about sits where you want it.\n"
         "5. Save (Ctrl+S)."),
    ("h1", "Methods"),
    ("h2", "Edge cut (default)"),
    ("", "Keeps the image where it is. A band along each edge is overlapped with the band "
         "from the opposite side, and the two are joined along the line where they match best. "
         "No pixels are mixed, so nothing gets blurred or ghosted. Best for busy textures: "
         "rock, brick, gravel, foliage. The tile gets smaller by the overlap."),
    ("", "Overlap X / Y - width of the edge bands in pixels (2-128). Wider gives the cut more "
         "room to find a good path; narrower keeps more of the image. Below 2 leaves that axis "
         "alone (it will not tile in that direction)."),
    ("h2", "Edge blend"),
    ("", "Like Edge cut, but the edge bands are faded into each other instead of cut. Smooth "
         "joins, but features in the band can look doubled. Best for soft textures: sand, "
         "plaster, cloth, cloud. The tile gets smaller by the overlap."),
    ("", "Overlap X / Y - width of the fade in pixels. 0 leaves that axis alone.\n"
         "Curve - shape of the fade (smoothstep is a good default)."),
    ("h2", "Radial mask"),
    ("", "Keeps the centre of the original and builds the edges from a half-shifted copy, "
         "joined through a soft circular mask with a wobbly edge. Tile stays the cropped size."),
    ("", "Inner radius - where the fade starts. Inside it is 100% original. Measured from the "
         "centre: 1.0 = middle of an edge, about 1.41 = corner.\n"
         "Outer radius - where the fade ends. Beyond it is 100% shifted copy. A wide gap between "
         "inner and outer gives a long, gentle fade.\n"
         "Scatter - how much the circle's edge wobbles, so it does not show as a ring.\n"
         "Scatter detail - size of the wobbles: low = big lumps, high = fine fringing.\n"
         "Seed / Re-roll - which random wobble pattern is used.\n"
         "Curve - shape of the fade.\n"
         "Hard edge - no fading; each pixel comes wholly from one copy or the other.\n"
         "Mask centre X / Y - which part of the source is kept untouched in the middle. "
         "Keep it modest; large values can pull the source's own edge seam into view."),
    ("h2", "Mirror"),
    ("", "Flips the image into a 2x2 mirrored tile. Always seamless, but obviously symmetric, "
         "and double the size. No options."),
    ("h2", "Offset only"),
    ("", "Shifts the image by half its size and repairs nothing. The seams end up as a cross "
         "through the middle, ready to fix by hand in a paint program. No options."),
    ("h1", "Shared settings"),
    ("", "Crop - pixels removed from each side before anything else happens. Shown as a dashed "
         "box in the Original view.\n"
         "Nudge X / Y - slides the finished tile around with wraparound, to re-centre it. "
         "It can never break the tiling. Arrow keys nudge 1 px, Shift+arrows 8 px.\n"
         "Reset positions - zeroes nudge and mask centre."),
    ("h1", "View"),
    ("", "Tiled / Single / Original - toggle with the button or V, or press 1 / 2 / 3.\n"
         "Tiles - 2x2, 3x3 or 4x4 in the Tiled view.\n"
         "Seam markers - dashed lines on the tile boundaries (Tiled view) or the crop box "
         "(Original view).\n"
         "Overlay - tints in red the pixels that came from the other copy or opposite side, "
         "so you can see exactly what each method changed.\n"
         "Zoom - mouse wheel zooms at the cursor. Fit picks the largest zoom that fits."),
    ("h1", "Files"),
    ("", "Save writes three files next to the source image:\n"
         "  name_tile.png - the finished tile\n"
         "  name_3x3.png - a 3x3 tiled example\n"
         "  name_tile.json - every setting, reloaded automatically when you open that image again\n"
         "Save as - choose a different name or folder; the json is still written alongside.\n"
         "Save settings / Load settings - store or apply all settings on their own. "
         "Any of the json files above can be loaded.\n"
         "Reload (Ctrl+R) - re-reads the source from disk, keeping your settings.\n"
         "Reset settings - back to defaults, keeping the current method and seed."),
    ("h1", "Keys and mouse"),
    ("", "Ctrl+O open    Ctrl+R reload    Ctrl+S save    F1 help\n"
         "1 / 2 / 3 views    V toggle view\n"
         "Arrows nudge 1 px    Shift+arrows nudge 8 px\n"
         "Wheel zoom at cursor    Left or middle drag pan\n"
         "Ctrl+wheel scroll    Shift+wheel scroll sideways"),
]


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self, path=None):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1320x900")
        self.minsize(900, 600)

        self.engine = Engine()
        self.src = None
        self.src_token = 0
        self.src_path = None
        self.tile = None
        self.tile_mask = None
        self._photo = None
        self._pending = None
        self._geom = None          # (ox, oy, zoom, region_w, region_h) of last render
        self._last = dict(DEFAULTS, **VIEW_DEFAULTS)
        self._help_win = None

        self.v = {}
        for k, d in list(DEFAULTS.items()) + list(VIEW_DEFAULTS.items()):
            if isinstance(d, bool):
                var = tk.BooleanVar(value=d)
            elif isinstance(d, int):
                var = tk.IntVar(value=d)
            elif isinstance(d, float):
                var = tk.DoubleVar(value=d)
            else:
                var = tk.StringVar(value=d)
            var.trace_add("write", lambda *_: self.schedule())
            self.v[k] = var
        self.v["seed"].set(random.randint(0, 99999))

        self._build_ui()
        self.v["method"].trace_add("write", lambda *_: self._update_method_ui())
        self._update_method_ui()
        self._bind_keys()

        if path:
            self.after(50, lambda: self.open_path(path))
        else:
            self.schedule()

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass

        panel = ttk.Frame(self, padding=6)
        panel.pack(side="left", fill="y")
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True)

        # --- file
        f = ttk.LabelFrame(panel, text="File", padding=4)
        f.pack(fill="x", pady=(0, 6))
        ttk.Button(f, text="Open... (Ctrl+O)", command=self.open_dialog).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Reload (Ctrl+R)", command=self.reload).grid(row=0, column=1, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Save (Ctrl+S)", command=self.save).grid(row=1, column=0, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Save as...", command=self.save_as).grid(row=1, column=1, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Load settings...", command=self.load_settings_dialog).grid(row=2, column=0, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Save settings...", command=self.save_settings_dialog).grid(row=2, column=1, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Reset settings", command=self.reset_settings).grid(row=3, column=0, sticky="ew", padx=1, pady=1)
        ttk.Button(f, text="Help (F1)", command=self.show_help).grid(row=3, column=1, sticky="ew", padx=1, pady=1)
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        # --- crop
        f = ttk.LabelFrame(panel, text="Crop (pixels)", padding=4)
        f.pack(fill="x", pady=(0, 6))
        self._spin(f, 0, 0, "Top", "crop_top", 0, 8192, 1)
        self._spin(f, 0, 2, "Bottom", "crop_bottom", 0, 8192, 1)
        self._spin(f, 1, 0, "Left", "crop_left", 0, 8192, 1)
        self._spin(f, 1, 2, "Right", "crop_right", 0, 8192, 1)

        # --- method
        f = ttk.LabelFrame(panel, text="Method", padding=4)
        f.pack(fill="x", pady=(0, 6))
        ttk.Combobox(f, textvariable=self.v["method"], values=METHODS,
                     state="readonly", width=18).pack(anchor="w", fill="x")
        self.method_box = ttk.Frame(f)
        self.method_box.pack(fill="x", pady=(4, 0))
        self.mframes = {}

        # radial
        fr = ttk.Frame(self.method_box)
        self.mframes[M_RADIAL] = fr
        self._spin(fr, 0, 0, "Inner radius", "inner", 0.0, 1.5, 0.01, fmt="%.2f")
        self._spin(fr, 1, 0, "Outer radius", "outer", 0.0, 1.6, 0.01, fmt="%.2f")
        self._spin(fr, 2, 0, "Scatter", "scatter", 0.0, 0.6, 0.01, fmt="%.2f")
        self._spin(fr, 3, 0, "Scatter detail", "detail", 1, 64, 1)
        self._spin(fr, 4, 0, "Seed", "seed", 0, 99999, 1)
        ttk.Button(fr, text="Re-roll", width=8,
                   command=lambda: self.v["seed"].set(random.randint(0, 99999))
                   ).grid(row=4, column=2, padx=(4, 0), sticky="w")
        ttk.Label(fr, text="Curve").grid(row=5, column=0, sticky="w", padx=(2, 6), pady=1)
        ttk.Combobox(fr, textvariable=self.v["curve"], values=list(CURVES.keys()),
                     state="readonly", width=12).grid(row=5, column=1, columnspan=2, sticky="w", pady=1)
        ttk.Checkbutton(fr, text="Hard edge (no pixel mixing)",
                        variable=self.v["hard"]).grid(row=6, column=0, columnspan=3, sticky="w", pady=(3, 0))
        ttk.Label(fr, text="Mask centre (which part of the source is kept)",
                  foreground="#666").grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))
        sub = ttk.Frame(fr)
        sub.grid(row=8, column=0, columnspan=3, sticky="w")
        self._spin(sub, 0, 0, "X", "center_x", -4096, 4096, 1)
        self._spin(sub, 0, 2, "Y", "center_y", -4096, 4096, 1)

        # edge blend
        fb = ttk.Frame(self.method_box)
        self.mframes[M_BLEND] = fb
        self._spin(fb, 0, 0, "Overlap X", "blend_overlap_x", 0, 2048, 1)
        self._spin(fb, 1, 0, "Overlap Y", "blend_overlap_y", 0, 2048, 1)
        ttk.Label(fb, text="Curve").grid(row=2, column=0, sticky="w", padx=(2, 6), pady=1)
        ttk.Combobox(fb, textvariable=self.v["blend_curve"], values=list(CURVES.keys()),
                     state="readonly", width=12).grid(row=2, column=1, sticky="w", pady=1)
        ttk.Label(fb, foreground="#666", wraplength=230, justify="left",
                  text="Edge bands are faded into the opposite side. "
                       "Tile shrinks by the overlap. 0 = leave that axis alone."
                  ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # edge cut
        fc = ttk.Frame(self.method_box)
        self.mframes[M_CUT] = fc
        self._spin(fc, 0, 0, "Overlap X", "cut_overlap_x", 0, CUT_MAX, 1)
        self._spin(fc, 1, 0, "Overlap Y", "cut_overlap_y", 0, CUT_MAX, 1)
        ttk.Label(fc, foreground="#666", wraplength=230, justify="left",
                  text=f"Edge bands are joined along the best-matching cut line. "
                       f"No pixel mixing. Tile shrinks by the overlap. "
                       f"2-{CUT_MAX} px; below 2 leaves that axis alone."
                  ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # mirror / offset
        fm = ttk.Frame(self.method_box)
        self.mframes[M_MIRROR] = fm
        ttk.Label(fm, foreground="#666", wraplength=230, justify="left",
                  text="No options. The image is flipped into a 2x2 mirrored "
                       "tile - seamless, but symmetric, and double the size."
                  ).pack(anchor="w")
        fo = ttk.Frame(self.method_box)
        self.mframes[M_OFFSET] = fo
        ttk.Label(fo, foreground="#666", wraplength=230, justify="left",
                  text="No options. Half-offset only: the seams end up as a cross "
                       "through the middle, ready to fix by hand."
                  ).pack(anchor="w")

        # --- position
        f = ttk.LabelFrame(panel, text="Nudge (wrap-shift the tile; arrow keys)", padding=4)
        f.pack(fill="x", pady=(0, 6))
        self._spin(f, 0, 0, "X", "nudge_x", -8192, 8192, 1)
        self._spin(f, 0, 2, "Y", "nudge_y", -8192, 8192, 1)
        ttk.Button(f, text="Reset positions", command=self.reset_positions
                   ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        # --- view
        f = ttk.LabelFrame(panel, text="View", padding=4)
        f.pack(fill="x", pady=(0, 6))
        ttk.Button(f, text="Toggle view (V)", command=self.cycle_view
                   ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        for i, (lbl, val) in enumerate((("Tiled (1)", "tiled"), ("Single (2)", "single"),
                                        ("Original (3)", "original"))):
            ttk.Radiobutton(f, text=lbl, value=val, variable=self.v["view"]
                            ).grid(row=1, column=i, sticky="w")
        ttk.Label(f, text="Tiles").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Combobox(f, textvariable=self.v["tiles"], values=[2, 3, 4],
                     state="readonly", width=5).grid(row=2, column=1, sticky="w")
        ttk.Label(f, text="Zoom").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Combobox(f, textvariable=self.v["zoom"], values=ZOOMS,
                     state="readonly", width=7).grid(row=3, column=1, sticky="w")
        ttk.Button(f, text="Fit", width=6, command=self.zoom_fit).grid(row=3, column=2, sticky="w")
        ttk.Checkbutton(f, text="Seam markers", variable=self.v["seams"]
                        ).grid(row=4, column=0, columnspan=3, sticky="w")
        self.overlay_cb = ttk.Checkbutton(f, variable=self.v["overlay"])
        self.overlay_cb.grid(row=5, column=0, columnspan=3, sticky="w")

        ttk.Label(panel, foreground="#666", justify="left",
                  text="Arrows: nudge 1px  (Shift: 8px)\n"
                       "Wheel: zoom at cursor   Drag: pan\n"
                       "Ctrl+Wheel: scroll   Shift+Wheel: scroll sideways"
                  ).pack(anchor="w", pady=(4, 0))

        # --- canvas
        cf = ttk.Frame(right)
        cf.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(cf, bg="#2b2b2b", highlightthickness=0)
        xs = ttk.Scrollbar(cf, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(cf, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        cf.rowconfigure(0, weight=1)
        cf.columnconfigure(0, weight=1)

        self.status = tk.StringVar(value="Open an image to begin (Ctrl+O)")
        ttk.Label(right, textvariable=self.status, anchor="w", padding=(6, 3)
                  ).pack(fill="x", side="bottom")

        c = self.canvas
        c.bind("<ButtonPress-1>", lambda e: (c.focus_set(), c.scan_mark(e.x, e.y)))
        c.bind("<B1-Motion>", lambda e: c.scan_dragto(e.x, e.y, gain=1))
        c.bind("<ButtonPress-2>", lambda e: (c.focus_set(), c.scan_mark(e.x, e.y)))
        c.bind("<B2-Motion>", lambda e: c.scan_dragto(e.x, e.y, gain=1))
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Shift-MouseWheel>", lambda e: c.xview_scroll(-int(e.delta / 120), "units"))
        c.bind("<Control-MouseWheel>", lambda e: c.yview_scroll(-int(e.delta / 120), "units"))
        c.bind("<Configure>", lambda e: self.schedule())

    def _spin(self, parent, row, col, label, name, frm, to, inc, fmt=None):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(2, 6), pady=1)
        kw = dict(from_=frm, to=to, increment=inc, textvariable=self.v[name], width=7)
        if fmt:
            kw["format"] = fmt
        sb = ttk.Spinbox(parent, **kw)
        sb.grid(row=row, column=col + 1, sticky="w", pady=1, padx=(0, 6))
        return sb

    def _update_method_ui(self):
        method = self.g("method")
        if method not in METHODS:
            method = M_RADIAL
        for fr in self.mframes.values():
            fr.pack_forget()
        self.mframes[method].pack(fill="x")
        if method in OVERLAY_METHODS:
            text = {M_RADIAL: "Mask overlay (red = offset copy)",
                    M_BLEND: "Overlay (red = faded from opposite side)",
                    M_CUT: "Overlay (red = taken from opposite side)"}[method]
            self.overlay_cb.configure(text=text)
            self.overlay_cb.grid()
        else:
            self.overlay_cb.grid_remove()

    def _bind_keys(self):
        self.bind("<Control-o>", lambda e: self.open_dialog())
        self.bind("<Control-r>", lambda e: self.reload())
        self.bind("<Control-s>", lambda e: self.save())
        self.bind("<F1>", lambda e: self.show_help())
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            self.bind(f"<{key}>", lambda e, a=dx, b=dy: self._key_nudge(e, a, b, 1))
            self.bind(f"<Shift-{key}>", lambda e, a=dx, b=dy: self._key_nudge(e, a, b, 8))
        self.bind("<Key-1>", lambda e: self._key_view(e, "tiled"))
        self.bind("<Key-2>", lambda e: self._key_view(e, "single"))
        self.bind("<Key-3>", lambda e: self._key_view(e, "original"))
        self.bind("<Key-v>", lambda e: None if self._typing() else self.cycle_view())

    def _typing(self):
        w = self.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry, tk.Spinbox))

    def _key_nudge(self, e, dx, dy, step):
        if self._typing():
            return
        self.v["nudge_x"].set(self.g("nudge_x") + dx * step)
        self.v["nudge_y"].set(self.g("nudge_y") + dy * step)
        return "break"

    def _key_view(self, e, view):
        if not self._typing():
            self.v["view"].set(view)

    def _on_wheel(self, e):
        """Zoom in/out one step, keeping the image point under the cursor fixed."""
        if self.src is None or e.delta == 0:
            return
        z = self.g("zoom")
        i = ZOOMS.index(z) if z in ZOOMS else ZOOMS.index("100%")
        ni = min(len(ZOOMS) - 1, i + 1) if e.delta > 0 else max(0, i - 1)
        if ni == i:
            return
        c = self.canvas
        anchor = None
        if self._geom:
            ox, oy, zoom, _, _ = self._geom
            anchor = ((c.canvasx(e.x) - ox) / zoom, (c.canvasy(e.y) - oy) / zoom)
        self.v["zoom"].set(ZOOMS[ni])
        self.update_now()
        if anchor and self._geom:
            ox, oy, zoom, rw, rh = self._geom
            left = ox + anchor[0] * zoom - e.x
            top = oy + anchor[1] * zoom - e.y
            if rw > 0:
                c.xview_moveto(max(0.0, left / rw))
            if rh > 0:
                c.yview_moveto(max(0.0, top / rh))
        return "break"

    # ------------------------------------------------------------ help
    def show_help(self):
        if self._help_win is not None and self._help_win.winfo_exists():
            self._help_win.deiconify()
            self._help_win.lift()
            self._help_win.focus_set()
            return
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} - Help")
        win.geometry("640x720")
        self._help_win = win
        frame = ttk.Frame(win, padding=6)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="word", padx=10, pady=8, relief="flat",
                      font=("Segoe UI", 10), spacing1=2, spacing3=2)
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        txt.tag_configure("h1", font=("Segoe UI", 13, "bold"), spacing1=10, spacing3=4)
        txt.tag_configure("h2", font=("Segoe UI", 10, "bold"), spacing1=8)
        for tag, line in HELP_TEXT:
            txt.insert("end", line + "\n", tag)
        txt.configure(state="disabled")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))
        win.bind("<Escape>", lambda e: win.destroy())

    # ------------------------------------------------------------ settings
    def g(self, name):
        """Safe variable read; falls back to last good value on bad input."""
        try:
            val = self.v[name].get()
            if isinstance(self._last[name], int) and not isinstance(self._last[name], bool):
                val = int(val)
            self._last[name] = val
            return val
        except (tk.TclError, ValueError):
            return self._last[name]

    def settings(self):
        """Every panel setting (method, all method options, view). Never the image."""
        return {k: self.g(k) for k in list(DEFAULTS) + list(VIEW_DEFAULTS)}

    def apply_settings(self, data):
        for k in list(DEFAULTS) + list(VIEW_DEFAULTS):
            if k in data:
                try:
                    self.v[k].set(data[k])
                except tk.TclError:
                    pass
        # older files have no method; unknown methods fall back too
        if data.get("method") not in METHODS:
            self.v["method"].set(M_RADIAL)

    def reset_settings(self):
        seed, method = self.g("seed"), self.g("method")
        self.apply_settings(DEFAULTS)
        self.v["seed"].set(seed)
        self.v["method"].set(method)

    def reset_positions(self):
        for k in ("center_x", "center_y", "nudge_x", "nudge_y"):
            self.v[k].set(0)

    def cycle_view(self):
        cur = self.g("view")
        i = VIEWS.index(cur) if cur in VIEWS else 0
        self.v["view"].set(VIEWS[(i + 1) % len(VIEWS)])

    def zoom_fit(self):
        if self.src is None:
            return
        self.update_idletasks()
        cw = max(50, self.canvas.winfo_width() - 8)
        ch = max(50, self.canvas.winfo_height() - 8)
        w, h = self._view_base_size()
        best = ZOOMS[0]
        for z in ZOOMS:
            f = self._zoom_factor(z)
            if w * f <= cw and h * f <= ch:
                best = z
        self.v["zoom"].set(best)

    @staticmethod
    def _zoom_factor(z):
        try:
            return {"33%": 1 / 3}.get(z, float(z.rstrip("%")) / 100.0)
        except ValueError:
            return 1.0

    def _view_base_size(self):
        view = self.g("view")
        if view == "original" or self.tile is None:
            return self.src.shape[1], self.src.shape[0]
        h, w = self.tile.shape[:2]
        if view == "single":
            return w, h
        n = int(self.g("tiles"))
        return w * n, h * n

    # ------------------------------------------------------------ file ops
    def open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp *.tif *.tiff"),
                       ("All files", "*.*")])
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            self.src = load_image(path)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not open image:\n{ex}")
            return
        self.src_token += 1
        self.src_path = os.path.abspath(path)
        self.title(f"{APP_NAME} - {os.path.basename(path)}")
        side = self._sidecar_path(self.src_path)
        if os.path.isfile(side):
            try:
                with open(side, "r", encoding="utf-8") as fh:
                    self.apply_settings(json.load(fh).get("settings", {}))
                self.status.set(f"Loaded settings from {os.path.basename(side)}")
            except Exception:
                pass
        self.schedule()
        self.after(80, self.zoom_fit)

    def reload(self):
        if not self.src_path:
            return
        try:
            self.src = load_image(self.src_path)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not reload image:\n{ex}")
            return
        self.src_token += 1
        self.update_now()
        self.status.set("Reloaded source")

    @staticmethod
    def _stem(path):
        return os.path.splitext(path)[0]

    def _sidecar_path(self, src_path):
        return self._stem(src_path) + "_tile.json"

    def _settings_doc(self):
        return {"app": APP_NAME, "version": 2,
                "source": os.path.basename(self.src_path) if self.src_path else None,
                "settings": self.settings()}

    def save(self):
        if self.src_path is None:
            return
        self._save_to(self._stem(self.src_path))

    def save_as(self):
        if self.src_path is None:
            return
        base = os.path.basename(self._stem(self.src_path))
        path = filedialog.asksaveasfilename(
            title="Save tile as", initialdir=os.path.dirname(self.src_path),
            initialfile=base + "_tile.png", defaultextension=".png",
            filetypes=[("PNG", "*.png")])
        if not path:
            return
        stem = self._stem(path)
        if stem.endswith("_tile"):
            stem = stem[:-5]
        self._save_to(stem, confirm=False)

    def _save_to(self, stem, confirm=True):
        self.update_now()
        if self.tile is None:
            return
        p_tile, p_3x3, p_json = stem + "_tile.png", stem + "_3x3.png", stem + "_tile.json"
        existing = [p for p in (p_tile, p_3x3, p_json) if os.path.exists(p)]
        if confirm and existing:
            names = "\n".join(os.path.basename(p) for p in existing)
            if not messagebox.askyesno(APP_NAME, f"Overwrite?\n\n{names}"):
                return
        try:
            Image.fromarray(self.tile).save(p_tile)
            Image.fromarray(np.tile(self.tile, (3, 3, 1))).save(p_3x3)
            with open(p_json, "w", encoding="utf-8") as fh:
                json.dump(self._settings_doc(), fh, indent=2)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Save failed:\n{ex}")
            return
        self.status.set(f"Saved {os.path.basename(p_tile)}, {os.path.basename(p_3x3)}, "
                        f"{os.path.basename(p_json)}")

    def save_settings_dialog(self):
        init_dir = os.path.dirname(self.src_path) if self.src_path else os.getcwd()
        init_name = (os.path.basename(self._stem(self.src_path)) + "_settings.json"
                     if self.src_path else "seamtile_settings.json")
        path = filedialog.asksaveasfilename(
            title="Save settings", initialdir=init_dir, initialfile=init_name,
            defaultextension=".json", filetypes=[("Settings", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._settings_doc(), fh, indent=2)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not save settings:\n{ex}")
            return
        self.status.set(f"Saved settings to {os.path.basename(path)}")

    def load_settings_dialog(self):
        path = filedialog.askopenfilename(title="Load settings",
                                          filetypes=[("Settings", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self.apply_settings(json.load(fh).get("settings", {}))
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not load settings:\n{ex}")
            return
        self.status.set(f"Loaded settings from {os.path.basename(path)}")

    # ------------------------------------------------------------ render
    def schedule(self):
        if self._pending is not None:
            self.after_cancel(self._pending)
        self._pending = self.after(25, self.update_now)

    def update_now(self):
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except tk.TclError:
                pass
        self._pending = None
        c = self.canvas
        c.delete("all")
        self._geom = None
        if self.src is None:
            return

        s = self.settings()
        try:
            self.tile, self.tile_mask = self.engine.process(self.src, self.src_token, s)
        except ValueError as ex:
            self.tile = None
            self.status.set(str(ex))
            return

        method = s["method"]
        view = s["view"]
        n = int(s["tiles"])
        th, tw = self.tile.shape[:2]

        if view == "original":
            arr = to_display_rgb(self.src)
        else:
            arr = to_display_rgb(self.tile)
            if s["overlay"] and method in OVERLAY_METHODS:
                arr = apply_overlay(arr, self.tile_mask)
            if view == "tiled":
                arr = np.tile(arr, (n, n, 1))

        h, w = arr.shape[:2]
        zoom = self._zoom_factor(s["zoom"])
        note = ""
        if max(w, h) * zoom > MAX_DISPLAY:
            zoom = MAX_DISPLAY / max(w, h)
            note = "  (zoom capped)"
        iw, ih = max(1, int(round(w * zoom))), max(1, int(round(h * zoom)))
        img = Image.fromarray(arr)
        if (iw, ih) != (w, h):
            img = img.resize((iw, ih), RS.NEAREST if zoom >= 1 else RS.BOX)
        self._photo = ImageTk.PhotoImage(img)

        cw, ch = c.winfo_width(), c.winfo_height()
        ox, oy = max(0, (cw - iw) // 2), max(0, (ch - ih) // 2)
        c.create_image(ox, oy, anchor="nw", image=self._photo)
        c.configure(scrollregion=(0, 0, max(cw, iw), max(ch, ih)))
        self._geom = (ox, oy, zoom, max(cw, iw), max(ch, ih))

        if s["seams"]:
            if view == "tiled":
                for k in range(1, n):
                    x = ox + k * tw * zoom
                    y = oy + k * th * zoom
                    c.create_line(x, oy, x, oy + ih, fill="#00e5ff", dash=(4, 4))
                    c.create_line(ox, y, ox + iw, y, fill="#00e5ff", dash=(4, 4))
            elif view == "original":
                H, W = self.src.shape[:2]
                c.create_rectangle(ox + s["crop_left"] * zoom, oy + s["crop_top"] * zoom,
                                   ox + (W - s["crop_right"]) * zoom,
                                   oy + (H - s["crop_bottom"]) * zoom,
                                   outline="#00e5ff", dash=(4, 4))

        extra = ""
        if method == M_RADIAL:
            extra = "   Blend: " + ("hard" if s["hard"] else "soft")
        self.status.set(f"Source {self.src.shape[1]}x{self.src.shape[0]}   "
                        f"Tile {tw}x{th}   Method: {method}{extra}   View: {view}   "
                        f"Zoom {s['zoom']}{note}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        prog="seamtile",
        description="Seamless tile maker with realtime preview "
                    "(radial mask, edge blend, edge cut, mirror, offset).",
        epilog="EXAMPLES:\n  seamtile\n  seamtile rock.png",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="image to open")
    args = ap.parse_args()

    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    App(args.image).mainloop()


if __name__ == "__main__":
    main()
