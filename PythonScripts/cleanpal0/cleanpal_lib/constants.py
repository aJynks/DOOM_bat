"""Shared constants, paths and small formatting helpers."""

import os


VERSION = "2.8.2"
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "cleanpal")
SETTINGS_PATH = os.path.join(APP_DIR, "cleanpal_settings.json")
LEGACY_SETTINGS_PATH = os.path.join(SCRIPT_DIR, "cleanpal_settings.json")
PRESET_DIR = os.path.join(APP_DIR, "presets")
PRESET_MARKER = "cleanpal_preset"


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
    ("Analysis PNGs (identical / similar / aligned)", None, None),
]
EXPORT_LABELS = [e[0] for e in EXPORTS]
# old labels found in settings / presets / projects -> current label
EXPORT_LEGACY = {"Analysis PNGs (identical / simular / aligned)":
                 "Analysis PNGs (identical / similar / aligned)"}


PICKER_MODES = ["RGB Sliders", "HSL Sliders", "HSL Colour Wheel"]


def fmt_tol(v):
    s = ("%.3f" % v).rstrip("0")
    if s.endswith("."):
        s += "0"
    return s
