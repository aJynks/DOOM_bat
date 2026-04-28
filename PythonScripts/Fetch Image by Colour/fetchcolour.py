"""
fetchcolour.py - Scans the current directory (and all subdirs) for PNG files
that are dominantly a specified colour, and copies matches to a destination.

Usage (via bat wrapper):
    fetchcolour -c green -o "D:/output/greens/"
    fetchcolour -colour green -output "D:/output/greens/" -volume 30
    fetchcolour -list
    fetchcolour --help

Requires: Pillow, numpy
    pip install Pillow numpy
"""

import sys
import os

# --- Dependency check ---
try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("ERROR: Missing required packages.")
    print("Run: pip install Pillow numpy")
    sys.exit(1)

import shutil
import re

# ---------------------------------------------------------------------------
# Colour definitions
# Each entry: hue ranges (0-360), sat/val min/max thresholds, description
# Red wraps around 0/360 so it uses two hue ranges.
# Grey/white/black are detected by saturation+value rather than hue.
# ---------------------------------------------------------------------------
COLOURS = {
    "red":    dict(hue=[(0, 15), (345, 360)], sat_min=0.35, val_min=0.15, val_max=1.00,
                   desc="Reds, crimsons, brick"),
    "orange": dict(hue=[(15, 45)],            sat_min=0.40, val_min=0.20, val_max=1.00,
                   desc="Oranges, terracotta, rust"),
    "yellow": dict(hue=[(45, 70)],            sat_min=0.35, val_min=0.25, val_max=1.00,
                   desc="Yellows, gold, mustard"),
    "green":  dict(hue=[(60, 180)],           sat_min=0.15, val_min=0.10, val_max=1.00,
                   desc="Greens, lime, olive, teal-green"),
    "cyan":   dict(hue=[(170, 210)],          sat_min=0.30, val_min=0.15, val_max=1.00,
                   desc="Cyan, aqua, turquoise"),
    "blue":   dict(hue=[(200, 260)],          sat_min=0.25, val_min=0.10, val_max=1.00,
                   desc="Blues, navy, cobalt, sky"),
    "purple": dict(hue=[(260, 310)],          sat_min=0.25, val_min=0.10, val_max=1.00,
                   desc="Purples, violet, indigo"),
    "pink":   dict(hue=[(300, 345)],          sat_min=0.20, val_min=0.30, val_max=1.00,
                   desc="Pinks, magenta, rose, hot-pink"),
    "brown":  dict(hue=[(10, 40)],            sat_min=0.25, val_min=0.05, val_max=0.50,
                   desc="Browns, tan, chocolate, wood tones"),
    "grey":   dict(hue=[(0, 360)],            sat_min=0.00, sat_max=0.12, val_min=0.15, val_max=0.80,
                   desc="Greys, silvers (low saturation, mid brightness)"),
    "black":  dict(hue=[(0, 360)],            sat_min=0.00, val_min=0.00, val_max=0.18,
                   desc="Black and very dark tones"),
    "white":  dict(hue=[(0, 360)],            sat_min=0.00, sat_max=0.15, val_min=0.80, val_max=1.00,
                   desc="White and near-white tones"),
}

DEFAULT_THRESHOLD = 20.0

# Flag aliases: short -> canonical, long -> canonical
FLAG_ALIASES = {
    "-c":       "colour",
    "-colour":  "colour",
    "-v":       "volume",
    "-volume":  "volume",
    "-o":       "output",
    "-output":  "output",
}


# ---------------------------------------------------------------------------
# Colour detection
# ---------------------------------------------------------------------------

def build_colour_mask(arr_float, colour_key):
    """Returns a boolean pixel mask for the given colour. arr_float is H x W x 3 float32 (0-1)."""
    cfg = COLOURS[colour_key]
    r, g, b = arr_float[:, :, 0], arr_float[:, :, 1], arr_float[:, :, 2]

    maxc  = np.maximum(np.maximum(r, g), b)
    minc  = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    v = maxc
    s = np.where(maxc != 0, delta / maxc, 0.0)

    hue = np.zeros_like(r)
    mask_r = (maxc == r) & (delta != 0)
    mask_g = (maxc == g) & (delta != 0)
    mask_b = (maxc == b) & (delta != 0)
    hue[mask_r] = (60 * ((g[mask_r] - b[mask_r]) / delta[mask_r])) % 360
    hue[mask_g] = (60 * ((b[mask_g] - r[mask_g]) / delta[mask_g]) + 120)
    hue[mask_b] = (60 * ((r[mask_b] - g[mask_b]) / delta[mask_b]) + 240)

    hue_mask = np.zeros(r.shape, dtype=bool)
    for (hmin, hmax) in cfg["hue"]:
        hue_mask |= (hue >= hmin) & (hue <= hmax)

    sat_max = cfg.get("sat_max", 1.0)
    mask = (
        hue_mask &
        (s >= cfg["sat_min"]) & (s <= sat_max) &
        (v >= cfg["val_min"]) & (v <= cfg["val_max"])
    )
    return mask


def analyse_png(filepath, colour_key, threshold_pct):
    """Returns True if >= threshold_pct of visible pixels match the colour."""
    try:
        img = Image.open(filepath).convert("RGBA")
    except Exception as e:
        print(f"  [SKIP] Could not open: {filepath} ({e})")
        return False

    r, g, b, a = img.split()
    alpha        = np.array(a)
    visible_mask = alpha > 10
    total_visible = visible_mask.sum()
    if total_visible == 0:
        return False

    arr        = np.array(Image.merge("RGB", (r, g, b)), dtype=np.float32) / 255.0
    colour_mask = build_colour_mask(arr, colour_key)
    match_pct   = (colour_mask & visible_mask).sum() / total_visible * 100.0
    return match_pct >= threshold_pct


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args(raw_env):
    """
    Parse the raw FETCHCOLOUR_ARGS environment string (or sys.argv).
    All flags are position-independent. -o path may contain spaces and a
    trailing backslash-quote (Windows batch artefact) which we clean up.

    Returns: (colour_key, threshold_pct, dest_root)
    """
    # Tokenise: find all flag positions first, then extract values between them.
    # Known flags and their values: -c/-colour, -v/-volume, -o/-output
    # The -o value is everything between -o and the next recognised flag (or end).
    # This handles spaces in the output path without quoting issues.

    # Normalise: collapse multiple spaces
    s = re.sub(r'  +', ' ', raw_env.strip())

    # Build a list of (position, flag_canonical) for each recognised flag token
    # We scan word by word
    tokens = s.split(' ')

    colour_key    = None
    threshold_pct = DEFAULT_THRESHOLD
    dest_root     = None

    i = 0
    while i < len(tokens):
        tok = tokens[i].lower()
        if tok in FLAG_ALIASES:
            canon = FLAG_ALIASES[tok]
            i += 1
            if i >= len(tokens):
                print(f"ERROR: {tok} requires a value.")
                sys.exit(1)

            if canon == "colour":
                colour_key = tokens[i].lower()

            elif canon == "volume":
                try:
                    threshold_pct = float(tokens[i])
                except ValueError:
                    print(f"ERROR: -volume value must be a number, got: {tokens[i]}")
                    sys.exit(1)

            elif canon == "output":
                # Collect tokens until the next recognised flag (or end)
                path_parts = []
                while i < len(tokens) and tokens[i].lower() not in FLAG_ALIASES:
                    path_parts.append(tokens[i])
                    i += 1
                raw_path = " ".join(path_parts)
                # Strip stray quotes and trailing backslash (Windows bat artefact)
                raw_path = raw_path.strip().strip('"').strip("'").rstrip("\\")
                dest_root = os.path.abspath(raw_path)
                continue  # i already advanced inside the while loop

        i += 1

    return colour_key, threshold_pct, dest_root


# ---------------------------------------------------------------------------
# Help / list
# ---------------------------------------------------------------------------

def print_help():
    print("""
fetchcolour - Copy PNGs matching a dominant colour into a destination folder.

USAGE:
  fetchcolour -c COLOUR -o "dest/path/" [-v PERCENT]
  fetchcolour -list
  fetchcolour --help

FLAGS (short and long forms are equivalent, any order):
  -c  / -colour  COLOUR    Colour to search for (required). Use -list for options.
  -o  / -output  PATH      Destination directory (required).
  -v  / -volume  PERCENT   Min % of visible pixels that must match (default: 20)
  -list                    List all available colour names and exit
  --help                   Show this help and exit

EXAMPLES:
  fetchcolour -c green -o "D:/out/greens/"
  fetchcolour -colour green -output "D:/out/greens/" -volume 15
  fetchcolour -o "D:/out/reds/" -c red -v 30
  fetchcolour -list

NOTES:
  - Scans the current directory and all subdirectories
  - Transparent pixels are ignored when calculating colour percentage
  - Original files are copied byte-for-byte (no re-encoding)
  - Subfolder structure is preserved in the destination
  - Do not include a trailing backslash in the output path
""")


def print_list():
    print("\nAvailable colours for -c / -colour:\n")
    max_len = max(len(k) for k in COLOURS)
    for name, cfg in COLOURS.items():
        print(f"  {name:<{max_len}}  {cfg['desc']}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Args arrive via FETCHCOLOUR_ARGS env var (set by bat wrapper) to avoid
    # Windows batch quote-mangling. Fall back to sys.argv for direct use.
    raw_env = os.environ.get("FETCHCOLOUR_ARGS", "").strip()
    if not raw_env:
        raw_env = " ".join(sys.argv[1:])

    if not raw_env or raw_env.strip() in ("--help", "-help", "-h"):
        print_help()
        sys.exit(0)

    if raw_env.strip() in ("-list", "--list"):
        print_list()
        sys.exit(0)

    # Also catch flags anywhere in args
    tokens_lower = raw_env.lower().split()
    if "--help" in tokens_lower or "-help" in tokens_lower or "-h" in tokens_lower:
        print_help()
        sys.exit(0)
    if "-list" in tokens_lower or "--list" in tokens_lower:
        print_list()
        sys.exit(0)

    colour_key, threshold_pct, dest_root = parse_args(raw_env)

    if colour_key is None:
        print("ERROR: -c / -colour is required. Use -list to see available colours.")
        sys.exit(1)
    if colour_key not in COLOURS:
        print(f"ERROR: Unknown colour '{colour_key}'. Use -list to see available colours.")
        sys.exit(1)
    if dest_root is None:
        print("ERROR: -o / -output is required. Specify a destination directory.")
        sys.exit(1)

    src_root = os.getcwd()
    print(f"Source    : {src_root}")
    print(f"Dest      : {dest_root}")
    print(f"Colour    : {colour_key}  ({COLOURS[colour_key]['desc']})")
    print(f"Threshold : {threshold_pct}% of visible pixels")
    print("-" * 60)

    found = skipped = copied = errors = 0

    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [
            d for d in dirnames
            if os.path.abspath(os.path.join(dirpath, d)) != dest_root
        ]
        for filename in filenames:
            if not filename.lower().endswith(".png"):
                continue
            filepath = os.path.join(dirpath, filename)
            found += 1
            if analyse_png(filepath, colour_key, threshold_pct):
                rel_path  = os.path.relpath(filepath, src_root)
                dest_path = os.path.join(dest_root, rel_path)
                try:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(filepath, dest_path)
                    print(f"  [COPY] {rel_path}")
                    copied += 1
                except Exception as e:
                    print(f"  [ERROR] Could not copy {rel_path}: {e}")
                    errors += 1
            else:
                skipped += 1

    print("-" * 60)
    print(f"Scanned : {found} PNG(s)")
    print(f"Copied  : {copied} ({colour_key} match)")
    print(f"Skipped : {skipped} (no match)")
    if errors:
        print(f"Errors  : {errors}")
    print("Done.")


if __name__ == "__main__":
    main()