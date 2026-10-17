"""COLORMAP: generation from the palette, hand overrides, diagnostics and
"create fade colours".

Rows 0..31 are light levels (0 = full bright), row 32 is invulnerability,
row 33 is all dark. Classic generation matches Freedoom's generator (and
id's dcolors.c): blend each colour toward the fade target by (32-row)/32
and take the nearest palette colour by plain RGB distance.

Everything here is keyed by palette slot index; CmapState.remap() keeps
hand edits attached to their colours when the palette is reordered or
culled.
"""

import bisect
import math
import os
import struct

from .colour import hex_of, oklab, oklab_to_rgbf, parse_colour
from .constants import ENTRIES

ROWS = 34
LIGHT_ROWS = 32
INVUL_ROW = 32
DARK_ROW = 33

CMAP_METHODS = ["Perceptual (OKLab)", "Classic (RGB, like id / Freedoom)"]
INVUL_MODES = ["Inverse grey (Doom)", "From loaded COLORMAP", "None (same as row 0)"]
CMAP_EXPORTS = [("COLORMAP lump (.lmp)", ".lmp"), ("COLORMAP image (256x34 .png)", ".png")]

DIAG_TYPES = {
    "crush": ("Early crush", "#ff3030"),
    "drift": ("Hue drift", "#ff9a00"),
    "jump": ("Big jump", "#ffe100"),
    "miss": ("Far from ideal", "#d050ff"),
}


def default_cmap_settings():
    return {"cmap_method": CMAP_METHODS[0], "cmap_curve": 1.0, "cmap_target": [0, 0, 0],
            "cmap_smooth": True, "cmap_invul": INVUL_MODES[0]}


def clean_cmap_settings(src, strict=False):
    out = {}

    def bad(k):
        if strict:
            raise ValueError("Bad value for '%s'." % k)

    if "cmap_method" in src:
        if src["cmap_method"] in CMAP_METHODS:
            out["cmap_method"] = src["cmap_method"]
        else:
            bad("cmap_method")
    if "cmap_invul" in src:
        if src["cmap_invul"] in INVUL_MODES:
            out["cmap_invul"] = src["cmap_invul"]
        else:
            bad("cmap_invul")
    if "cmap_curve" in src:
        v = src["cmap_curve"]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out["cmap_curve"] = float(min(max(v, 0.25), 4.0))
        else:
            bad("cmap_curve")
    if "cmap_smooth" in src:
        if isinstance(src["cmap_smooth"], bool):
            out["cmap_smooth"] = src["cmap_smooth"]
        else:
            bad("cmap_smooth")
    if "cmap_target" in src:
        v = src["cmap_target"]
        if isinstance(v, (list, tuple)) and len(v) == 3 and \
                all(isinstance(x, int) and 0 <= x <= 255 for x in v):
            out["cmap_target"] = list(v)
        else:
            bad("cmap_target")
    return out


# ============================================================ state
class CmapState:
    """Hand edits to the COLORMAP, keyed by palette slot."""

    def __init__(self):
        self.overrides = {}      # (row, src) -> target slot
        self.fullbright = set()  # slots that never darken
        self.limits = {}         # src -> frozenset of allowed target slots
        self.curves = {}         # src -> fade curve for that colour

    def copy(self):
        c = CmapState()
        c.overrides = dict(self.overrides)
        c.fullbright = set(self.fullbright)
        c.limits = dict(self.limits)
        c.curves = dict(self.curves)
        return c

    def __eq__(self, other):
        return isinstance(other, CmapState) and self.to_json() == other.to_json()

    def empty(self):
        return not (self.overrides or self.fullbright or self.limits or self.curves)

    def permute(self, newpos):
        """Palette reordered: newpos[old] = new slot."""
        self.overrides = {(r, newpos[s]): newpos[t] for (r, s), t in self.overrides.items()}
        self.fullbright = {newpos[i] for i in self.fullbright}
        self.limits = {newpos[s]: frozenset(newpos[t] for t in v)
                       for s, v in self.limits.items()}
        self.curves = {newpos[s]: v for s, v in self.curves.items()}

    def remap(self, mapping, owner=None):
        """Palette culled / packed: mapping[old] = new slot or None.
        Edits pointing at a removed colour follow its kept owner (exact /
        similar merge) when there is one, else they are dropped.
        Returns the number of hand-set cells that were dropped."""
        owner = owner or {}

        def tgt(t):
            n = mapping.get(t)
            if n is None and t in owner:
                n = mapping.get(owner[t])
            return n

        dropped = 0
        ov = {}
        for (r, s), t in self.overrides.items():
            ns, nt = mapping.get(s), tgt(t)
            if ns is None:
                continue              # the colour itself is gone: its column goes
            if nt is None:
                dropped += 1
                continue
            ov[(r, ns)] = nt
        self.overrides = ov
        self.fullbright = {mapping[i] for i in self.fullbright if mapping.get(i) is not None}
        lim = {}
        for s, v in self.limits.items():
            ns = mapping.get(s)
            if ns is None:
                continue
            nv = frozenset(x for x in (tgt(t) for t in v) if x is not None)
            if nv:
                lim[ns] = nv
        self.limits = lim
        self.curves = {mapping[s]: v for s, v in self.curves.items()
                       if mapping.get(s) is not None}
        return dropped

    def invalidate(self, slots):
        """These slots got new colours: their own fades go back to auto and
        hand edits pointing at them are dropped. Returns how many hand-set
        cells of OTHER colours were dropped."""
        slots = set(slots)
        dropped = sum(1 for (r, s), t in self.overrides.items()
                      if s not in slots and t in slots)
        self.overrides = {(r, s): t for (r, s), t in self.overrides.items()
                          if s not in slots and t not in slots}
        self.fullbright -= slots
        for s in slots:
            self.limits.pop(s, None)
            self.curves.pop(s, None)
        lim = {}
        for s, v in self.limits.items():
            nv = frozenset(t for t in v if t not in slots)
            if nv:
                lim[s] = nv
        self.limits = lim
        return dropped

    def clear_rows(self, slots):
        slots = set(slots)
        self.overrides = {k: t for k, t in self.overrides.items() if k[1] not in slots}

    def to_json(self):
        return {"overrides": sorted([r, s, t] for (r, s), t in self.overrides.items()),
                "fullbright": sorted(self.fullbright),
                "limits": {str(s): sorted(v) for s, v in sorted(self.limits.items())},
                "curves": {str(s): v for s, v in sorted(self.curves.items())}}

    @classmethod
    def from_json(cls, d):
        c = cls()
        if not isinstance(d, dict):
            return c

        def ok(i, hi=ENTRIES):
            return isinstance(i, int) and not isinstance(i, bool) and 0 <= i < hi

        for item in d.get("overrides") or []:
            if isinstance(item, list) and len(item) == 3 and ok(item[0], ROWS - 1) \
                    and ok(item[1]) and ok(item[2]):
                c.overrides[(item[0], item[1])] = item[2]
        c.fullbright = {i for i in (d.get("fullbright") or []) if ok(i)}
        for k, v in (d.get("limits") or {}).items():
            try:
                s = int(k)
            except (TypeError, ValueError):
                continue
            if ok(s) and isinstance(v, list):
                vv = frozenset(i for i in v if ok(i))
                if vv:
                    c.limits[s] = vv
        for k, v in (d.get("curves") or {}).items():
            try:
                s = int(k)
            except (TypeError, ValueError):
                continue
            if ok(s) and isinstance(v, (int, float)) and not isinstance(v, bool):
                c.curves[s] = float(min(max(v, 0.25), 4.0))
        return c


# ============================================================ nearest search
class Matcher:
    """Nearest palette slot for a colour, in RGB or OKLab, restricted to a
    pool of slots. Sorted-axis search with pruning plus a result cache."""

    def __init__(self, rgbs, pool, perceptual):
        self.perceptual = perceptual
        self.rgbs = rgbs
        self.pool = sorted(pool)
        self._labs = {}
        self.items = []                  # (key, coords, slot), sorted by key
        for i in self.pool:
            co = self.coords(rgbs[i])
            self.items.append((self._key(co), co, i))
        self.items.sort()
        self.keys = [it[0] for it in self.items]
        self.cache = {}

    def coords(self, rgb):
        if self.perceptual:
            k = tuple(int(round(v)) for v in rgb)
            v = self._labs.get(k)
            if v is None:
                v = self._labs[k] = oklab(k)
            return v
        return tuple(float(x) for x in rgb)

    def _key(self, co):
        if self.perceptual:
            return co[0]
        return (co[0] + co[1] + co[2]) / math.sqrt(3.0)

    def dist(self, rgb_a, rgb_b):
        a, b = self.coords(rgb_a), self.coords(rgb_b)
        return math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))

    def nearest(self, rgb, allowed=None):
        if allowed is not None:
            co = self.coords(rgb)
            best, bi = None, None
            for i in sorted(allowed):
                if self.rgbs[i] is None:
                    continue
                c2 = self.coords(self.rgbs[i])
                d = sum((co[k] - c2[k]) ** 2 for k in range(3))
                if best is None or d < best:
                    best, bi = d, i
            return bi
        key = tuple(round(v, 3) for v in rgb)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        if not self.items:
            return None
        co = self.coords(rgb)
        q = self._key(co)
        pos = bisect.bisect_left(self.keys, q)
        best, bi = None, None
        lo, hi = pos - 1, pos
        n = len(self.items)
        while lo >= 0 or hi < n:
            dl = q - self.keys[lo] if lo >= 0 else None
            dh = self.keys[hi] - q if hi < n else None
            if dh is None or (dl is not None and dl <= dh):
                k, d1 = lo, dl
                lo -= 1
            else:
                k, d1 = hi, dh
                hi += 1
            lim = None if best is None else best + 1e-7      # float slack: keep ties
            if lim is not None and d1 * d1 > lim:
                if (lo < 0 or (q - self.keys[lo]) ** 2 > lim) and \
                        (hi >= n or (self.keys[hi] - q) ** 2 > lim):
                    break
                continue
            c2 = self.items[k][1]
            d = (co[0] - c2[0]) ** 2 + (co[1] - c2[1]) ** 2 + (co[2] - c2[2]) ** 2
            slot = self.items[k][2]
            if best is None or d < best - 1e-9 or (abs(d - best) <= 1e-9 and slot < bi):
                best, bi = d, slot
        self.cache[key] = bi
        return bi


# ============================================================ generation
def _blend(a, b, f):
    """f = 1 -> a, f = 0 -> b."""
    return tuple(b[k] + (a[k] - b[k]) * f for k in range(3))


def ideal_path(src, row, curve, target, anchors=None):
    """Ideal (float RGB) colour of `src` at a light row.
    anchors: sorted [(row, rgb)] of hand-set steps for smooth auto-fill."""
    if not anchors:
        f = ((LIGHT_ROWS - row) / float(LIGHT_ROWS)) ** curve
        return _blend(src, target, f)
    pts = [(0, tuple(src))] + [a for a in anchors if a[0] > 0] + [(LIGHT_ROWS, tuple(target))]
    if anchors and anchors[0][0] == 0:
        pts[0] = (0, tuple(anchors[0][1]))
    for (ra, ca), (rb, cb) in zip(pts, pts[1:]):
        if ra <= row <= rb:
            u = 0.0 if rb == ra else (row - ra) / float(rb - ra)
            f = (1.0 - u) ** curve
            return _blend(ca, cb, f)
    return tuple(target)


class CmapResult:
    def __init__(self):
        self.rows = [[0] * ENTRIES for _ in range(ROWS)]
        self.ideal = {}           # (row, src) -> float rgb (rows 1..32)
        self.source = {}          # (row, src) -> "auto" / "override" / "bright" / "bad"
        self.matcher = None
        self.pool = []


def generate(rgbs, deleted, settings, state, loaded=None):
    """Build the 34 x 256 COLORMAP for the working palette.
    loaded: {"rows", "pal"} of a loaded COLORMAP (for the invul option)."""
    perceptual = settings.get("cmap_method", CMAP_METHODS[0]) == CMAP_METHODS[0]
    curve = float(settings.get("cmap_curve", 1.0))
    target = tuple(settings.get("cmap_target", (0, 0, 0)))
    smooth = bool(settings.get("cmap_smooth", True))
    invul = settings.get("cmap_invul", INVUL_MODES[0])
    deleted = deleted or set()
    pool = [i for i, c in enumerate(rgbs) if c is not None and i not in deleted]
    res = CmapResult()
    res.pool = pool
    m = Matcher(rgbs, pool, perceptual)
    res.matcher = m
    if not pool:
        return res
    dark = m.nearest(target)
    ov = state.overrides
    loaded_lookup = None
    if invul == INVUL_MODES[1] and loaded and len(loaded.get("rows", [])) > INVUL_ROW:
        loaded_lookup = {}
        for j, c in enumerate(loaded["pal"]):
            if c is not None:
                loaded_lookup.setdefault(tuple(c), j)

    for s in range(ENTRIES):
        src = rgbs[s]
        if src is None:
            for r in range(ROWS):
                res.rows[r][s] = ov.get((r, s), dark) if r < DARK_ROW else dark
            continue
        allowed = state.limits.get(s)
        if allowed is not None:
            allowed = [t for t in allowed if t in pool or t == s] or None
        c_curve = state.curves.get(s, curve)
        anchors = None
        if smooth:
            hs = sorted((r, t) for (r, ss), t in ov.items() if ss == s and r < LIGHT_ROWS
                        and t < ENTRIES and rgbs[t] is not None and t not in deleted)
            if hs:
                anchors = [(r, rgbs[t]) for r, t in hs]
        bright = s in state.fullbright
        for r in range(LIGHT_ROWS):
            t = ov.get((r, s))
            if t is not None and t < ENTRIES and rgbs[t] is not None and t not in deleted:
                res.rows[r][s] = t
                res.source[(r, s)] = "override"
                if r:
                    res.ideal[(r, s)] = ideal_path(src, r, c_curve, target, anchors)
                continue
            if t is not None:
                res.source[(r, s)] = "bad"       # hand-set target no longer usable
            if bright or r == 0:
                res.rows[r][s] = m.nearest(src)      # lowest slot holding this colour
                res.source.setdefault((r, s), "bright" if bright and r else "auto")
                continue
            ideal = ideal_path(src, r, c_curve, target, anchors)
            res.ideal[(r, s)] = ideal
            res.rows[r][s] = m.nearest(ideal, allowed)
            res.source.setdefault((r, s), "auto")
        # invulnerability
        t = ov.get((INVUL_ROW, s))
        if t is not None and t < ENTRIES and rgbs[t] is not None and t not in deleted:
            res.rows[INVUL_ROW][s] = t
            res.source[(INVUL_ROW, s)] = "override"
        else:
            if invul == INVUL_MODES[2]:
                res.rows[INVUL_ROW][s] = res.rows[0][s]
            else:
                want = None
                if loaded_lookup is not None:
                    j = loaded_lookup.get(tuple(src))
                    if j is not None:
                        tj = loaded["rows"][INVUL_ROW][j]
                        if 0 <= tj < len(loaded["pal"]) and loaded["pal"][tj] is not None:
                            want = loaded["pal"][tj]
                if want is None:
                    g = round(src[0] * 0.2126 + src[1] * 0.7152 + src[2] * 0.0722)
                    want = (255 - g,) * 3
                res.ideal[(INVUL_ROW, s)] = tuple(float(v) for v in want)
                res.rows[INVUL_ROW][s] = m.nearest(want)
            res.source[(INVUL_ROW, s)] = "auto"
        res.rows[DARK_ROW][s] = dark
    return res


# ============================================================ diagnostics
def _lch(rgb):
    L, a, b = oklab(tuple(int(round(v)) for v in rgb))
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def diagnose(rgbs, res, state):
    """Flag poor fade steps: {(row, src): type}. Types: crush, drift, jump, miss."""
    flags = {}
    for s, src in enumerate(rgbs):
        if src is None or s in state.fullbright:
            continue
        sL, sC, sh = _lch(src)
        prevL = sL
        prev_ideal_L = sL
        for r in range(1, LIGHT_ROWS):
            t = res.rows[r][s]
            act = rgbs[t]
            ideal = res.ideal.get((r, s))
            if act is None or ideal is None:
                continue
            aL, aC, ah = _lch(act)
            iL, iC, ih = _lch(ideal)
            f = None
            if aL < 0.07 and iL > 0.22:
                f = "crush"
            elif sC > 0.05 and aC > 0.03 and iC > 0.02 and \
                    abs((ah - ih + 180.0) % 360.0 - 180.0) > 40.0:
                f = "drift"
            elif abs(aL - prevL) > max(0.09, 3.0 * abs(iL - prev_ideal_L)):
                f = "jump"
            else:
                d = math.sqrt(sum((x - y) ** 2 for x, y in
                                  zip(oklab(act), oklab(tuple(int(round(v)) for v in ideal)))))
                if d > 0.09:
                    f = "miss"
            if f:
                flags[(r, s)] = f
            prevL, prev_ideal_L = aL, iL
    return flags


# ============================================================ create fade colours
def fade_misses(rgbs, res, scope, state, weights=None):
    """Light-row steps whose fade lands far from its ideal colour.
    Returns [(ideal_lab, ideal_rgb, current_dist, weight, src, row)]."""
    out = []
    for s in scope:
        src = rgbs[s]
        if src is None or s in state.fullbright:
            continue
        w0 = 1.0 if not weights else max(weights.get(s, 0), 0) ** 0.5 + 0.05
        for r in range(1, LIGHT_ROWS):
            if res.source.get((r, s)) == "override":
                continue
            ideal = res.ideal.get((r, s))
            t = res.rows[r][s]
            if ideal is None or rgbs[t] is None:
                continue
            il = oklab(tuple(int(round(v)) for v in ideal))
            al = oklab(rgbs[t])
            d = math.sqrt(sum((x - y) ** 2 for x, y in zip(il, al)))
            if d > 0.015:
                # darker steps are seen less: weight by the ideal's lightness
                out.append((il, tuple(int(round(v)) for v in ideal), d,
                            w0 * (0.35 + il[0]), s, r))
    return out


def propose_fade_colours(rgbs, res, scope, state, budget, weights=None):
    """Greedy: the new colours that most reduce weighted fade error.
    Returns (proposals, before, after); each proposal is a dict with rgb,
    gain, serves (colour count), rows (min, max)."""
    misses = fade_misses(rgbs, res, scope, state, weights)
    return greedy_new_colours(misses, budget)


def greedy_new_colours(misses, budget):
    """misses: [(ideal_lab, ideal_rgb, current_dist, weight, src, row)].
    Picks up to `budget` new colours (from the ideal colours) that most
    reduce the weighted distance. Returns (proposals, before, after)."""
    if not misses or budget <= 0:
        tot = sum(m[2] * m[3] for m in misses)
        return [], tot, tot
    cur = [m[2] for m in misses]
    before = sum(cur[k] * misses[k][3] for k in range(len(misses)))
    cell = 0.06

    def bucket(lab):
        return (int(lab[0] // cell), int(lab[1] // cell), int(lab[2] // cell))

    grid = {}
    for k, m in enumerate(misses):
        grid.setdefault(bucket(m[0]), []).append(k)
    cands = {}
    for m in misses:                              # candidate = a miss's ideal colour
        cands.setdefault(tuple(int(v) for v in m[1]), m[0])
    cands = list(cands.items())
    if len(cands) > 500:                          # thin very large sets
        step = len(cands) / 500.0
        cands = [cands[int(i * step)] for i in range(500)]
    hood = []
    for rgb, lab in cands:
        b = bucket(lab)
        lst = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for k in grid.get((b[0] + dx, b[1] + dy, b[2] + dz), ()):
                        m = misses[k][0]
                        d = math.sqrt((lab[0] - m[0]) ** 2 + (lab[1] - m[1]) ** 2
                                      + (lab[2] - m[2]) ** 2)
                        if d < misses[k][2]:
                            lst.append((k, d))
        hood.append(lst)
    props = []
    used = set()
    for _ in range(int(budget)):
        best = None
        for ci, lst in enumerate(hood):
            if ci in used:
                continue
            gain = 0.0
            for k, d in lst:
                if d < cur[k]:
                    gain += (cur[k] - d) * misses[k][3]
            if best is None or gain > best[0]:
                best = (gain, ci)
        if best is None or best[0] <= 1e-6:
            break
        gain, ci = best
        used.add(ci)
        rgb, lab = cands[ci]
        srcs, rows = set(), []
        for k, d in hood[ci]:
            if d < cur[k]:
                cur[k] = d
                srcs.add(misses[k][4])
                rows.append(misses[k][5])
        props.append({"rgb": tuple(rgb), "gain": gain, "serves": len(srcs),
                      "srcs": sorted(srcs), "rows": (min(rows), max(rows)) if rows else (0, 0)})
    after = sum(cur[k] * misses[k][3] for k in range(len(misses)))
    return props, before, after


# ============================================================ fade ramps (Ramp tool on fades)
def _lch_of(rgb):
    L, a, b = oklab(tuple(int(round(min(max(v, 0), 255))) for v in rgb))
    return L, math.hypot(a, b), math.atan2(b, a)


def relative_colour(ref_anchor, node_rgb, anchor):
    """The node colour, re-expressed for another strip's anchor (Relative):
    same lightness ratio, chroma ratio and hue turn as node vs ref_anchor."""
    rL, rC, rh = _lch_of(ref_anchor)
    nL, nC, nh = _lch_of(node_rgb)
    aL, aC, ah = _lch_of(anchor)
    L = min(1.0, aL * (nL / rL)) if rL > 1e-3 else nL
    grey = 0.02
    if rC >= grey:
        C = aC * (nC / rC)
    else:
        C = aC + nC                       # grey reference: add the node's colourfulness
    if rC >= grey and aC >= grey:
        h = ah + (nh - rh)
    elif aC < grey:
        h = nh                            # grey anchor: take the node's hue
    else:
        h = ah
    return oklab_to_rgbf(L, C * math.cos(h), C * math.sin(h))


def fade_ramp_rows(state, ref_anchor, strips, anchors, matcher, limits=None):
    """Snapped fades for every strip.
    strips: {src: start_row}; anchors: {src: rgb before the range (or the
    colour itself for start 0)}. Returns {src: [(row, ideal_rgb, slot, dist)]}."""
    from .ramps import ramp_colour_at

    out = {}
    for s, r0 in strips.items():
        anc = tuple(anchors[s])
        st = {"space": state["space"], "ease": state["ease"],
              "strength": state["strength"], "ease_scope": state["ease_scope"],
              "nodes": []}
        for k, n in enumerate(state["nodes"]):
            rgb = anc if k == 0 else relative_colour(ref_anchor, n["rgb"], anc)
            st["nodes"].append({"pos": n["pos"], "rgb": [min(max(v, 0.0), 255.0)
                                                         for v in rgb]})
        a = r0 - 1 if r0 > 0 else 0
        span = float(LIGHT_ROWS - 1 - a) or 1.0
        allowed = (limits or {}).get(s)
        rows = []
        for row in range(r0, LIGHT_ROWS):
            t = (row - a) / span
            ideal = ramp_colour_at(st, t)
            if row == 0:
                slot = s                  # full bright is always the colour itself
            else:
                slot = matcher.nearest(ideal, allowed)
            dist = 0.0
            if slot is not None and matcher.rgbs[slot] is not None:
                il = oklab(tuple(int(round(v)) for v in ideal))
                sl = oklab(matcher.rgbs[slot])
                dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(il, sl)))
            rows.append((row, ideal, slot, dist))
        out[s] = rows
    return out


# ============================================================ bulk edit helpers
def fade_within(rgbs, slots, steps_per_level, order, past_end, dark_slot):
    """Overrides that make each selected colour fade down through the
    selection itself. Returns {(row, src): target}."""
    cols = [s for s in slots if rgbs[s] is not None]
    if order == "Lightness":
        cols.sort(key=lambda s: -oklab(rgbs[s])[0])
    n = len(cols)
    out = {}
    for k, s in enumerate(cols):
        for r in range(LIGHT_ROWS):
            pos = k + r * steps_per_level
            j = int(math.floor(pos + 1e-9))
            if j < n:
                out[(r, s)] = cols[j]
            elif past_end == "Black" and dark_slot is not None:
                out[(r, s)] = dark_slot
    return out


def fade_shape(rgbs, res, s):
    """A colour's fade as OKLab offsets from the colour itself (row -> delta)."""
    base = oklab(rgbs[s])
    shape = {}
    for r in range(LIGHT_ROWS):
        t = res.rows[r][s]
        if rgbs[t] is None:
            continue
        lt = oklab(rgbs[t])
        shape[r] = tuple(lt[k] - base[k] for k in range(3))
    return shape


def apply_shape(rgbs, matcher, shape, s):
    """Overrides for colour s following a copied fade shape."""
    base = oklab(rgbs[s])
    out = {}
    for r, d in shape.items():
        lab = (max(0.0, base[0] + d[0]), base[1] + d[1], base[2] + d[2])
        out[(r, s)] = matcher.nearest(oklab_to_rgbf(*lab))
    return out


# ============================================================ files
def read_wad_lump(path, name):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        raise ValueError("Not a valid WAD file (bad header).")
    numlumps, infotableofs = struct.unpack_from("<ii", data, 4)
    found = None
    for i in range(numlumps):
        off = infotableofs + i * 16
        if off + 16 > len(data):
            break
        filepos, size = struct.unpack_from("<ii", data, off)
        nm = data[off + 8: off + 16].split(b"\x00")[0].decode("ascii", "replace")
        if nm.upper() == name:
            found = data[filepos: filepos + size]     # last one wins, like the engine
    return found


def rows_from_bytes(raw):
    n = min(len(raw) // ENTRIES, ROWS)
    if n < LIGHT_ROWS:
        raise ValueError("COLORMAP data is too small (%d bytes)." % len(raw))
    return [list(raw[r * ENTRIES:(r + 1) * ENTRIES]) for r in range(n)]


def load_colormap(path, palette):
    """Rows from a WAD (COLORMAP lump), a raw .lmp, or a 256 x 32..34 image
    whose pixels are palette colours."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wad":
        raw = read_wad_lump(path, "COLORMAP")
        if raw is None:
            raise ValueError("No COLORMAP lump in this WAD.")
        return rows_from_bytes(raw)
    if ext == ".png":
        from PIL import Image

        with Image.open(path) as im:
            im.load()
            img = im.convert("RGB")
        w, h = img.size
        if w != ENTRIES or not LIGHT_ROWS <= h <= ROWS:
            raise ValueError("A COLORMAP image must be 256 wide and 32-34 rows tall "
                             "(this one is %dx%d)." % (w, h))
        lookup = {}
        for i, c in enumerate(palette):
            if c is not None:
                lookup.setdefault(tuple(c), i)
        m = Matcher(palette, [i for i, c in enumerate(palette) if c is not None], False)
        px = img.load()
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                c = px[x, y]
                row.append(lookup[c] if c in lookup else m.nearest(c))
            rows.append(row)
        return rows
    with open(path, "rb") as fh:
        return rows_from_bytes(fh.read())


def write_colormap(path, rows, palette):
    if path.lower().endswith(".png"):
        from PIL import Image

        img = Image.new("RGB", (ENTRIES, len(rows)))
        px = img.load()
        for y, row in enumerate(rows):
            for x, t in enumerate(row):
                c = palette[t] if 0 <= t < len(palette) else None
                px[x, y] = tuple(c) if c is not None else (0, 255, 0)
        img.save(path)
    else:
        with open(path, "wb") as fh:
            fh.write(bytes(v & 0xFF for row in rows for v in row))


def import_overrides(rgbs, res, loaded):
    """Cells where a loaded COLORMAP differs from the current auto result,
    matched by colour. Returns {(row, src): target}."""
    lpal = loaded["pal"]
    first = {}
    for j, c in enumerate(lpal):
        if c is not None:
            first.setdefault(tuple(c), j)
    here = {}
    for i, c in enumerate(rgbs):
        if c is not None:
            here.setdefault(tuple(c), i)
    out = {}
    for s, c in enumerate(rgbs):
        if c is None:
            continue
        j = first.get(tuple(c))
        if j is None:
            continue
        for r in range(min(len(loaded["rows"]), LIGHT_ROWS)):   # light rows only
            tj = loaded["rows"][r][j]
            if not 0 <= tj < len(lpal) or lpal[tj] is None:
                continue
            tc = tuple(lpal[tj])
            t = here.get(tc)
            if t is None:
                t = res.matcher.nearest(tc)
            if t is not None and t != res.rows[r][s]:
                out[(r, s)] = t
    return out


def hexes(cols):
    return [hex_of(c) if c is not None else None for c in cols]


def from_hexes(lst):
    return [parse_colour(x) if isinstance(x, str) else None for x in lst]
