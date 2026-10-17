"""Paint-tool colour filters (pure maths, no GUI).

apply_filter(name, params, colours, ctx) -> new colours. colours is a list of
(r, g, b) ints (the selected, non-empty palette cells in index order); the
result has the same length. ctx = {"ramp": ramp state or None,
"fill": (r, g, b) or None}.

Everything runs in float and is rounded / clamped once at the end.
Perceptual modes use OKLab / OKLCH with gamut mapping (chroma is reduced,
lightness and hue kept, when a colour falls outside sRGB).
"""

import math

from .colour import hsl_to_rgb, oklab, rgb_to_hsl
from .ramps import ramp_colour_at

PERC = "Perceptual (OKLab)"
CLASSIC = "Classic (RGB)"

# param specs: (key, label, "num", lo, hi, step, default)
#              (key, label, "choice", [options], default)
#              (key, label, "bool", default)
FILTERS = {
    "Levels": {
        "desc": "Remap input black / white points with a gamma curve, then squeeze "
                "into the output range. RGB together or one channel.",
        "params": [
            ("channel", "Channel", "choice", ["RGB", "Red", "Green", "Blue"], "RGB"),
            ("in_black", "Input black", "num", 0, 254, 1, 0),
            ("gamma", "Gamma", "num", 0.1, 9.99, 0.01, 1.0),
            ("in_white", "Input white", "num", 1, 255, 1, 255),
            ("out_black", "Output black", "num", 0, 255, 1, 0),
            ("out_white", "Output white", "num", 0, 255, 1, 255),
        ]},
    "Brightness / Contrast": {
        "desc": "Brightness shifts everything lighter / darker; contrast spreads "
                "colours away from (or toward) the pivot. Perceptual keeps hues steadier.",
        "params": [
            ("mode", "Mode", "choice", [PERC, CLASSIC], PERC),
            ("brightness", "Brightness", "num", -100, 100, 1, 0),
            ("contrast", "Contrast", "num", -100, 100, 1, 0),
            ("pivot", "Contrast pivot", "choice", ["Mid grey", "Selection average"],
             "Mid grey"),
        ]},
    "Hue / Saturation / Lightness": {
        "desc": "Rotate hue, scale saturation, push lightness. OKLCH avoids yellows "
                "going muddy; HSL behaves like classic paint programs.",
        "params": [
            ("space", "Space", "choice", ["Perceptual (OKLCH)", "Classic (HSL)"],
             "Perceptual (OKLCH)"),
            ("hue", "Hue shift", "num", -180, 180, 1, 0),
            ("sat", "Saturation %", "num", -100, 100, 1, 0),
            ("light", "Lightness %", "num", -100, 100, 1, 0),
        ]},
    "Colorise": {
        "desc": "One hue for everything, keeping each colour's lightness (like "
                "Photoshop's Colorize). Can take the hue from the Paint fill colour.",
        "params": [
            ("source", "Colour from", "choice", ["Hue / saturation below",
                                                 "Paint fill colour"],
             "Hue / saturation below"),
            ("space", "Space", "choice", [PERC, "Classic (HSL)"], PERC),
            ("hue", "Hue", "num", 0, 360, 1, 30),
            ("sat", "Saturation", "num", 0, 100, 1, 50),
            ("light", "Lightness", "num", -100, 100, 1, 0),
            ("amount", "Strength %", "num", 0, 100, 1, 100),
        ]},
    "Black & white": {
        "desc": "Convert to grey. Doom / Rec.601 matches the classic luma weights; "
                "Custom is a channel mixer (weights in %).",
        "params": [
            ("weights", "Weights", "choice", ["Doom / Rec.601", "Rec.709",
                                              "Perceptual (OKLab L)", "Custom"],
             "Doom / Rec.601"),
            ("red", "Red % (custom)", "num", -200, 300, 1, 30),
            ("green", "Green % (custom)", "num", -200, 300, 1, 59),
            ("blue", "Blue % (custom)", "num", -200, 300, 1, 11),
            ("amount", "Amount %", "num", 0, 100, 1, 100),
        ]},
    "Invert": {
        "desc": "RGB inverts everything; Lightness only flips light and dark but "
                "keeps the hue (dark reds become light reds).",
        "params": [
            ("mode", "Mode", "choice", ["RGB", "Lightness only (keep hue)"], "RGB"),
            ("amount", "Amount %", "num", 0, 100, 1, 100),
        ]},
    "Gradient map": {
        "desc": "Map each colour's lightness onto the Paint window's current ramp - "
                "recolour a family while keeping its shading.",
        "params": [
            ("light_from", "Lightness from", "choice", ["Perceptual (OKLab L)",
                                                        "Doom / Rec.601"],
             "Perceptual (OKLab L)"),
            ("stretch", "Stretch selection to the whole ramp", "bool", True),
            ("direction", "Ramp direction", "choice", ["Auto (match lightness)",
                                                       "Start = lightest",
                                                       "Start = darkest"],
             "Auto (match lightness)"),
            ("amount", "Amount %", "num", 0, 100, 1, 100),
        ]},
    "Even out ramp": {
        "desc": "Space the selection's lightness evenly, keeping hue and chroma - "
                "fixes lumpy ramps. Lightness order keeps every colour in its slot.",
        "params": [
            ("order", "Order", "choice", ["Lightness order (keep positions)",
                                          "Index order"],
             "Lightness order (keep positions)"),
            ("range", "Range", "choice", ["Keep selection's lightest / darkest",
                                          "Custom"],
             "Keep selection's lightest / darkest"),
            ("lightest", "Lightest % (custom)", "num", 0, 100, 1, 95),
            ("darkest", "Darkest % (custom)", "num", 0, 100, 1, 10),
            ("curve", "Curve (gamma)", "num", 0.2, 5.0, 0.05, 1.0),
        ]},
    "Temperature / Tint": {
        "desc": "Warm / cool and green / magenta shifts for quick mood changes.",
        "params": [
            ("mode", "Mode", "choice", [PERC, CLASSIC], PERC),
            ("temp", "Temperature (+ warm)", "num", -100, 100, 1, 0),
            ("tint", "Tint (+ magenta)", "num", -100, 100, 1, 0),
        ]},
    "Posterise": {
        "desc": "Reduce to a few levels for a crunchy retro look.",
        "params": [
            ("levels", "Levels", "num", 2, 32, 1, 4),
            ("space", "Space", "choice", ["RGB channels", "Lightness only (OKLab)"],
             "RGB channels"),
        ]},
}
FILTER_NAMES = list(FILTERS)


def defaults(name):
    out = {}
    for p in FILTERS[name]["params"]:
        out[p[0]] = p[-1]
    return out


def clean_params(name, src):
    """Defaults overlaid with valid values from src (settings may be stale)."""
    out = defaults(name)
    if not isinstance(src, dict):
        return out
    for p in FILTERS[name]["params"]:
        key, kind = p[0], p[2]
        if key not in src:
            continue
        v = src[key]
        if kind == "num":
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v == v:
                out[key] = min(max(v, p[3]), p[4])
        elif kind == "choice":
            if v in p[3]:
                out[key] = v
        elif kind == "bool":
            out[key] = bool(v)
    return out


# ============================================================ helpers
def _clamp01(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _oklab_to_lin(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def _enc(c):
    c = _clamp01(c)
    c = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return c * 255.0


def _in_gamut(lin, eps=1e-4):
    return all(-eps <= v <= 1.0 + eps for v in lin)


def from_oklab(L, a, b):
    """OKLab -> sRGB floats 0..255, gamut-mapped by reducing chroma."""
    L = _clamp01(L)
    lin = _oklab_to_lin(L, a, b)
    if not _in_gamut(lin):
        lo, hi = 0.0, 1.0
        for _ in range(18):
            mid = (lo + hi) / 2.0
            if _in_gamut(_oklab_to_lin(L, a * mid, b * mid)):
                lo = mid
            else:
                hi = mid
        lin = _oklab_to_lin(L, a * lo, b * lo)
    return tuple(_enc(v) for v in lin)


def to_lch(rgb):
    L, a, b = oklab(rgb)
    return L, math.hypot(a, b), math.atan2(b, a)


def from_lch(L, C, h):
    return from_oklab(L, C * math.cos(h), C * math.sin(h))


def _luma601(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _push(v, amt, top):
    """Push v (0..top) toward top (amt > 0) or 0 (amt < 0); amt in -1..1."""
    return v + (top - v) * amt if amt >= 0 else v * (1.0 + amt)


def _round(c):
    return tuple(int(min(max(round(v), 0), 255)) for v in c)


# ============================================================ filters
def _levels(p, cols, ctx):
    ib, iw = p["in_black"], max(p["in_white"], p["in_black"] + 1)
    g = max(p["gamma"], 0.01)
    ob, ow = p["out_black"], p["out_white"]
    ch = {"RGB": (0, 1, 2), "Red": (0,), "Green": (1,), "Blue": (2,)}[p["channel"]]

    def f(v):
        t = _clamp01((v - ib) / (iw - ib)) ** (1.0 / g)
        return ob + t * (ow - ob)

    return [tuple(f(c[k]) if k in ch else float(c[k]) for k in range(3)) for c in cols]


def _contrast_k(c):
    c = c / 100.0
    return 1.0 + c if c <= 0 else 1.0 / max(1.0 - c * 0.98, 0.02)


def _bc(p, cols, ctx):
    k = _contrast_k(p["contrast"])
    bright = p["brightness"] / 100.0
    if p["mode"] == CLASSIC:
        if p["pivot"] == "Selection average" and cols:
            piv = sum(sum(c) for c in cols) / (3.0 * len(cols))
        else:
            piv = 127.5
        return [tuple((v - piv) * k + piv + bright * 127.5 for v in c) for c in cols]
    labs = [oklab(c) for c in cols]
    if p["pivot"] == "Selection average" and labs:
        piv = sum(L for L, _, _ in labs) / len(labs)
    else:
        piv = 0.5
    out = []
    for L, a, b in labs:
        L2 = (L - piv) * k + piv + bright * 0.5
        out.append(from_oklab(L2, a, b))
    return out


def _hsl(p, cols, ctx):
    dh, ds, dl = p["hue"], p["sat"] / 100.0, p["light"] / 100.0
    out = []
    if p["space"].startswith("Classic"):
        for c in cols:
            h, s, l = rgb_to_hsl(*c)
            s = min(max(s * (1.0 + ds), 0.0), 100.0)
            l = _push(l, dl, 100.0)
            out.append(hsl_to_rgb(h + dh, s, l))
        return out
    for c in cols:
        L, C, h = to_lch(c)
        out.append(from_lch(_push(L, dl, 1.0), max(C * (1.0 + ds), 0.0),
                            h + math.radians(dh)))
    return out


def _colorise(p, cols, ctx):
    amt = p["amount"] / 100.0
    dl = p["light"] / 100.0
    fill = ctx.get("fill") if p["source"] == "Paint fill colour" else None
    out = []
    if p["space"].startswith("Classic"):
        if fill is not None:
            hue, sat, _ = rgb_to_hsl(*fill)
        else:
            hue, sat = p["hue"], p["sat"]
        for c in cols:
            _, _, l = rgb_to_hsl(*c)
            new = hsl_to_rgb(hue, sat, _push(l, dl, 100.0))
            out.append(_mix(c, new, amt))
        return out
    if fill is not None:
        _, C, h = to_lch(fill)
    else:
        h, C = math.radians(p["hue"]), p["sat"] / 100.0 * 0.25
    for c in cols:
        L, a0, b0 = oklab(c)
        L2 = _push(L, dl, 1.0)
        a, b = C * math.cos(h), C * math.sin(h)
        out.append(from_oklab(L + (L2 - L) * amt, a0 + (a - a0) * amt, b0 + (b - b0) * amt))
    return out


def _bw(p, cols, ctx):
    amt = p["amount"] / 100.0
    w = p["weights"]
    out = []
    for c in cols:
        if w == "Perceptual (OKLab L)":
            g = from_oklab(oklab(c)[0], 0.0, 0.0)[0]
        else:
            if w == "Doom / Rec.601":
                kr, kg, kb = 0.299, 0.587, 0.114
            elif w == "Rec.709":
                kr, kg, kb = 0.2126, 0.7152, 0.0722
            else:
                kr, kg, kb = p["red"] / 100.0, p["green"] / 100.0, p["blue"] / 100.0
            g = kr * c[0] + kg * c[1] + kb * c[2]
        out.append(_mix(c, (g, g, g), amt))
    return out


def _invert(p, cols, ctx):
    amt = p["amount"] / 100.0
    out = []
    for c in cols:
        if p["mode"] == "RGB":
            new = tuple(255.0 - v for v in c)
        else:
            L, a, b = oklab(c)
            new = from_oklab(1.0 - L, a, b)
        out.append(_mix(c, new, amt))
    return out


def _lightness(c, how):
    return oklab(c)[0] if how.startswith("Perceptual") else _luma601(c) / 255.0


def _gradmap(p, cols, ctx):
    st = ctx.get("ramp")
    if not st or not cols:
        return [tuple(map(float, c)) for c in cols]
    amt = p["amount"] / 100.0
    ls = [_lightness(c, p["light_from"]) for c in cols]
    lo, hi = (min(ls), max(ls)) if p["stretch"] else (0.0, 1.0)
    span = hi - lo
    d = p["direction"]
    if d.startswith("Auto"):
        a = _lightness(_round(ramp_colour_at(st, 0.0)), p["light_from"])
        b = _lightness(_round(ramp_colour_at(st, 1.0)), p["light_from"])
        start_light = a >= b
    else:
        start_light = d == "Start = lightest"
    out = []
    for c, l in zip(cols, ls):
        u = 0.5 if span <= 1e-9 else _clamp01((l - lo) / span)
        t = 1.0 - u if start_light else u
        out.append(_mix(c, ramp_colour_at(st, t), amt))
    return out


def _even(p, cols, ctx):
    n = len(cols)
    if n < 2:
        return [tuple(map(float, c)) for c in cols]
    labs = [oklab(c) for c in cols]
    Ls = [l[0] for l in labs]
    if p["range"] == "Custom":
        top, bot = p["lightest"] / 100.0, p["darkest"] / 100.0
    else:
        top, bot = max(Ls), min(Ls)
    g = max(p["curve"], 0.01)
    if p["order"].startswith("Lightness"):
        order = sorted(range(n), key=lambda i: (-Ls[i], i))     # lightest first
        start, end = top, bot
    else:
        order = list(range(n))
        if Ls[0] >= Ls[-1]:
            start, end = top, bot
        else:
            start, end = bot, top
    target = [0.0] * n
    for rank, i in enumerate(order):
        t = (rank / (n - 1.0)) ** g
        target[i] = start + (end - start) * t
    return [from_oklab(target[i], labs[i][1], labs[i][2]) for i in range(n)]


def _temp(p, cols, ctx):
    t, m = p["temp"] / 100.0, p["tint"] / 100.0
    if p["mode"] == CLASSIC:
        return [(c[0] + t * 40.0, c[1] - m * 40.0, c[2] - t * 40.0) for c in cols]
    out = []
    for c in cols:
        L, a, b = oklab(c)
        out.append(from_oklab(L, a + m * 0.08, b + t * 0.08))
    return out


def _posterise(p, cols, ctx):
    n = int(round(p["levels"]))
    n = max(2, n)
    q = lambda v: round(v * (n - 1)) / (n - 1)          # noqa: E731
    if p["space"].startswith("RGB"):
        return [tuple(q(v / 255.0) * 255.0 for v in c) for c in cols]
    out = []
    for c in cols:
        L, a, b = oklab(c)
        out.append(from_oklab(q(_clamp01(L)), a, b))
    return out


_FUNCS = {
    "Levels": _levels, "Brightness / Contrast": _bc,
    "Hue / Saturation / Lightness": _hsl, "Colorise": _colorise,
    "Black & white": _bw, "Invert": _invert, "Gradient map": _gradmap,
    "Even out ramp": _even, "Temperature / Tint": _temp, "Posterise": _posterise,
}


def apply_filter(name, params, colours, ctx=None):
    p = clean_params(name, params)
    cols = [tuple(c) for c in colours]
    return [_round(c) for c in _FUNCS[name](p, cols, ctx or {})]
