"""Settings file, sort settings, presets and project validation."""

import json
import os

from .colour import hex_of, parse_colour
from .constants import (
    APP_DIR, DEFAULT_TOL, ENTRIES, EXPORT_LABELS, EXPORT_LEGACY, LEGACY_SETTINGS_PATH,
    METRICS, PICKER_MODES, PRESET_MARKER, SETTINGS_PATH, SETTINGS_VERSION,
)
from .colormap import CmapState, clean_cmap_settings
from .ramps import clean_ramp_state
from .sorting import (
    OUTLIER_MODES, RAMP_ORDERS, SORT_KEY_NAMES, SORT_METHODS, SORT_METHOD_NAMES,
    default_sort_params,
)


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
    s["export"] = EXPORT_LEGACY.get(s["export"], s["export"])
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
CMAP_SETTING_KEYS = ("cmap_method", "cmap_curve", "cmap_target", "cmap_smooth", "cmap_invul")
PRESET_KEYS = ("exact", "similar", "metric", "tol_de2000", "tol_lab", "tol_rgb",
               "align", "split", "export") + SORT_SETTING_KEYS + CMAP_SETTING_KEYS


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
        exp = EXPORT_LEGACY.get(src["export"], src["export"])
        if exp not in EXPORT_LABELS:
            raise ValueError("Unknown export format '%s'." % src["export"])
        out["export"] = exp
    out.update(clean_sort_settings(src, strict=True))
    out.update(clean_cmap_settings(src, strict=True))
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
        out_h.append({"text": str(h.get("text") or "Entry"), "palette": pal,
                      "cmap": CmapState.from_json(h.get("cmap"))})
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
    loaded = None
    cl = data.get("cmap_loaded")
    if isinstance(cl, dict):
        try:
            rows = cl.get("rows")
            if not (isinstance(rows, list) and 32 <= len(rows) <= 34 and all(
                    isinstance(r, list) and len(r) == ENTRIES and
                    all(isinstance(v, int) and 0 <= v < ENTRIES for v in r) for r in rows)):
                raise ValueError
            lpal = cl.get("pal")
            if not (isinstance(lpal, list) and len(lpal) == ENTRIES):
                raise ValueError
            lp = [parse_colour(x) if isinstance(x, str) else None for x in lpal]
            loaded = {"rows": rows, "pal": lp, "name": str(cl.get("name") or "COLORMAP")}
        except ValueError:
            loaded = None
    pmode = data.get("mode") if data.get("mode") in ("PLAYPAL", "COLORMAP") else None
    return {"history": out_h, "hist_pos": pos, "deleted": idx_list("deleted"),
            "selection": idx_list("selection"), "settings": settings, "ramp": ramp,
            "scratch_sets": sets, "scratch_current": data.get("scratch_current"),
            "recent_colours": recent, "picker_mode": mode, "source": src,
            "cmap_loaded": loaded, "mode": pmode}
