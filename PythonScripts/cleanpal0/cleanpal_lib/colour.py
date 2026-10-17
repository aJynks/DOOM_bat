"""Colour maths: sRGB / Lab / OKLab / HSL conversions, distances, parsing."""

import math


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
