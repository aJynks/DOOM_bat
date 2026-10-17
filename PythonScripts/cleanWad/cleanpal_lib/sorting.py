"""Sort-into-ramps methods and the --ramptest benchmark."""

import heapq
import math
import os

from .colour import _hsv, oklab
from .palette_io import load_palette


GREY_CHROMA = 0.025          # OKLab chroma below this = grey
JOIN_DIST = 0.10             # OKLab distance limit for joining an outlier
HUE_CUT = 10.0               # OKLab hue where the wheel starts (just below red)



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
