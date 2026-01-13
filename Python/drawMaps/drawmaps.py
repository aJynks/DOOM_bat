#!/usr/bin/env python3
"""
Draw Doom maps to transparent PNGs with automap-ish line colours.

Usage:
  py drawmaps2.py source.wad pattern width PNG [layers]

Pattern:
  - Wildcards supported: * and ?
    Examples: "MAP*", "E?M4"
  - Exact map name supported (no * or ?)
    Examples: "MAP01", "E1M1"

Examples:
  py drawmaps2.py "Blood_Born_PT1_(RC5).wad" "MAP*" 1024 PNG
  py drawmaps2.py "doom2.wad" "MAP01" 1024 PNG layers

Outputs:
  MAP09_map.png               (all lines on transparent background)
  MAP09_map_layer1.png        (Walls / one-sided only)   [if layers]
  MAP09_map_layer2.png        (Two-sided only)           [if layers]
  MAP09_map_layer3.png        (Secret only)              [if layers]
  MAP09_map_layer4.png        (Special/Action only)      [if layers]
"""

from omg import WAD, MapEditor
import sys
from PIL import Image, ImageDraw

# --- Linedef flag bits (classic Doom/Boom compatible) ---
ML_SECRET = 0x0020  # "secret" line shows differently on automap in many ports

# --- Colours (RGBA) ---
COL_ONE_SIDED = (255, 0, 0, 255)        # walls (often red)
COL_TWO_SIDED = (190, 140, 90, 255)     # two-sided edges (often brown/tan)
COL_SECRET    = (255, 255, 0, 255)      # secret lines (often yellow)
COL_SPECIAL   = (0, 255, 0, 255)        # special/action lines (often green)
COL_DEFAULT   = (255, 255, 255, 255)    # fallback (unused unless you expand rules)

# Line thickness
THICKNESS = 1


def _linedef_flags(ld):
    return int(getattr(ld, "flags", 0) or 0)


def _linedef_special(ld):
    # omgifol commonly uses .action; some libs use .special
    return int(getattr(ld, "action", getattr(ld, "special", 0)) or 0)


def colour_for_linedef(ld):
    flags = _linedef_flags(ld)
    special = _linedef_special(ld)

    if flags & ML_SECRET:
        return COL_SECRET
    if special != 0:
        return COL_SPECIAL

    two_sided = bool(getattr(ld, "two_sided", False))
    return COL_TWO_SIDED if two_sided else COL_ONE_SIDED


def layer_index_for_linedef(ld):
    """
    Stable per-line-type index:
      1 = one-sided (walls)
      2 = two-sided
      3 = secret
      4 = special/action
    """
    flags = _linedef_flags(ld)
    special = _linedef_special(ld)
    two_sided = bool(getattr(ld, "two_sided", False))

    if flags & ML_SECRET:
        return 3
    if special != 0:
        return 4
    if two_sided:
        return 2
    return 1


def draw_thick_line(draw, p1x, p1y, p2x, p2y, color, thickness):
    draw.line((p1x, p1y, p2x, p2y), fill=color)
    for i in range(1, thickness):
        draw.line((p1x + i, p1y, p2x + i, p2y), fill=color)
        draw.line((p1x - i, p1y, p2x - i, p2y), fill=color)
        draw.line((p1x, p1y + i, p2x, p2y + i), fill=color)
        draw.line((p1x, p1y - i, p2x, p2y - i), fill=color)


def _compute_scaled_editor(wad, name, width):
    """
    Returns:
      edit (MapEditor) with vertexes scaled to ints
      xmin, ymin, xmax, ymax (scaled ints)
    """
    xsize = width - 8
    edit = MapEditor(wad.maps[name])

    xmin = ymin = 32767
    xmax = ymax = -32768

    for v in edit.vertexes:
        xmin = min(xmin, v.x)
        xmax = max(xmax, v.x)
        ymin = min(ymin, -v.y)
        ymax = max(ymax, -v.y)

    denom = (xmax - xmin) if (xmax - xmin) != 0 else 1
    scale = xsize / float(denom)

    xmin = int(xmin * scale)
    xmax = int(xmax * scale)
    ymin = int(ymin * scale)
    ymax = int(ymax * scale)

    # Apply scaling (omgifol requires ints in vertex coords)
    for v in edit.vertexes:
        v.x = int(v.x * scale)
        v.y = int(-v.y * scale)

    return edit, xmin, ymin, xmax, ymax


def drawmap(wad, name, width, save_layers=False):
    edit, xmin, ymin, xmax, ymax = _compute_scaled_editor(wad, name, width)

    w = (xmax - xmin) + 8
    h = (ymax - ymin) + 8

    # All-lines image
    im_all = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_all = ImageDraw.Draw(im_all)

    # Optional per-type layer images
    layer_imgs = None
    layer_draws = None
    if save_layers:
        # 1..4 used; index 0 unused for convenience
        layer_imgs = [None] + [Image.new("RGBA", (w, h), (0, 0, 0, 0)) for _ in range(4)]
        layer_draws = [None] + [ImageDraw.Draw(layer_imgs[i]) for i in range(1, 5)]

    # Draw one-sided first then two-sided last (helps mimic automap emphasis)
    edit.linedefs.sort(key=lambda ld: bool(getattr(ld, "two_sided", False)))

    for ld in edit.linedefs:
        p1x = edit.vertexes[ld.vx_a].x - xmin + 4
        p1y = edit.vertexes[ld.vx_a].y - ymin + 4
        p2x = edit.vertexes[ld.vx_b].x - xmin + 4
        p2y = edit.vertexes[ld.vx_b].y - ymin + 4

        color = colour_for_linedef(ld)

        # Draw into combined map
        draw_thick_line(draw_all, p1x, p1y, p2x, p2y, color, THICKNESS)

        # Draw into per-type layer map (if enabled)
        if save_layers:
            idx = layer_index_for_linedef(ld)
            draw_thick_line(layer_draws[idx], p1x, p1y, p2x, p2y, color, THICKNESS)

    del draw_all
    im_all.save(f"{name}_map.png", "PNG")

    if save_layers:
        for i in range(1, 5):
            layer_imgs[i].save(f"{name}_map_layer{i}.png", "PNG")


def main(argv):
    # Accept both:
    #   py drawmaps2.py wad pattern width PNG
    #   py drawmaps2.py wad pattern width PNG layers
    if len(argv) < 5:
        print("\nUsage:\n  py drawmaps2.py source.wad pattern width PNG [layers]\n")
        return 1

    source = argv[1]
    pattern = argv[2]
    width = int(argv[3])
    fmt = argv[4].upper()

    save_layers = (len(argv) >= 6 and argv[5].lower() == "layers")

    if fmt != "PNG":
        print("Note: this script outputs PNG only (needs transparency). Ignoring format:", fmt)

    print(f"Loading {source}...")
    wad = WAD()
    wad.from_file(source)

    # Wildcard detection: if pattern has * or ?, treat as wildcard; otherwise exact map name.
    is_wild = ("*" in pattern) or ("?" in pattern)

    if is_wild:
        map_names = list(wad.maps.find(pattern))
    else:
        # Exact mode: only draw that one map if it exists
        # (still supports patterns like MAP01 without accidentally drawing extras)
        if pattern in wad.maps:
            map_names = [pattern]
        else:
            # As fallback, try find and then filter exact (some WADs store names oddly)
            map_names = [m for m in wad.maps.find(pattern) if m == pattern]

    if not map_names:
        print(f"No maps matched: {pattern}")
        return 2

    for name in map_names:
        print(f"Drawing {name}" + (" (with layers)" if save_layers else ""))
        drawmap(wad, name, width, save_layers=save_layers)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
