"""Ramp maker: multi-node gradients, blend spaces and easing."""

import math

from .colour import oklab, oklab_to_rgbf, rgb_round


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
