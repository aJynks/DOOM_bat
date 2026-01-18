#!/usr/bin/env python3
"""
Draw Doom maps to transparent PNGs with automap-ish line colours.

Usage:
  py drawmaps.py source.wad [options]

Options:
  -m, --map PATTERN       Map pattern (wildcards: * ?) or exact name
                          Default: draws ALL maps in WAD
  -s, --size WIDTH        Image width in pixels (default: 1024)
  -t, --thickness N       Line thickness (default: 1)
  -b, --background [COLOR] Background color: 'black' (default if flag used) 
                          or hex code (#1ecbe1). Omit flag for transparent.
                          Use: -b (black), -b #1ecbe1 (custom color)
  --layers                Generate separate layer PNGs for each line type
  -h, --help              Show this help message

Examples:
  py drawmaps.py doom2.wad
  py drawmaps.py doom2.wad -m MAP01
  py drawmaps.py doom2.wad -m "MAP*" -s 2048
  py drawmaps.py doom2.wad -m "E?M4" -t 2 -b
  py drawmaps.py doom2.wad -b #1ecbe1
  py drawmaps.py doom2.wad -b
  py drawmaps.py doom2.wad --layers

Outputs:
  MAP09_map.png               (all lines)
  MAP09_map_layer1.png        (Walls / one-sided only)   [if --layers]
  MAP09_map_layer2.png        (Two-sided only)           [if --layers]
  MAP09_map_layer3.png        (Secret only)              [if --layers]
  MAP09_map_layer4.png        (Special/Action only)      [if --layers]
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


def parse_background_color(color_str):
    """
    Parse background color from string.
    Returns (r, g, b, a) tuple.
    Accepts:
      - 'black' -> (0, 0, 0, 255)
      - '#RRGGBB' hex code -> (r, g, b, 255)
      - None/empty -> (0, 0, 0, 0) transparent
    """
    if not color_str:
        return (0, 0, 0, 0)  # Transparent
    
    color_str = color_str.strip().lower()
    
    if color_str == "black":
        return (0, 0, 0, 255)
    
    # Try to parse hex color
    if color_str.startswith("#"):
        color_str = color_str[1:]
    
    # Must be 6 hex digits
    if len(color_str) != 6:
        raise ValueError(f"Invalid hex color: must be #RRGGBB format (e.g., #1ecbe1)")
    
    try:
        r = int(color_str[0:2], 16)
        g = int(color_str[2:4], 16)
        b = int(color_str[4:6], 16)
        return (r, g, b, 255)
    except ValueError:
        raise ValueError(f"Invalid hex color: {color_str} (must be valid hex digits)")


def drawmap(wad, name, width, save_layers=False, thickness=1, bg_color=(0, 0, 0, 0)):
    edit, xmin, ymin, xmax, ymax = _compute_scaled_editor(wad, name, width)

    w = (xmax - xmin) + 8
    h = (ymax - ymin) + 8

    # All-lines image
    im_all = Image.new("RGBA", (w, h), bg_color)
    draw_all = ImageDraw.Draw(im_all)

    # Optional per-type layer images
    layer_imgs = None
    layer_draws = None
    if save_layers:
        # 1..4 used; index 0 unused for convenience
        layer_imgs = [None] + [Image.new("RGBA", (w, h), bg_color) for _ in range(4)]
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
        draw_thick_line(draw_all, p1x, p1y, p2x, p2y, color, thickness)

        # Draw into per-type layer map (if enabled)
        if save_layers:
            idx = layer_index_for_linedef(ld)
            draw_thick_line(layer_draws[idx], p1x, p1y, p2x, p2y, color, thickness)

    del draw_all
    im_all.save(f"{name}_map.png", "PNG")

    if save_layers:
        for i in range(1, 5):
            layer_imgs[i].save(f"{name}_map_layer{i}.png", "PNG")


def show_help():
    print(__doc__)


def main(argv):
    if len(argv) < 2:
        show_help()
        return 1

    # Check for help flag
    if "-h" in argv or "--help" in argv:
        show_help()
        return 0

    # First arg is always the WAD file
    source = argv[1]

    # Initialize all variables
    pattern = None
    width = 1024
    save_layers = False
    thickness = 1
    bg_color = (0, 0, 0, 0)  # Transparent by default

    # Parse arguments
    i = 2
    while i < len(argv):
        arg = argv[i]

        if arg in ("-m", "--map"):
            if i + 1 >= len(argv):
                print(f"Error: {arg} requires a value")
                return 1
            pattern = argv[i + 1]
            i += 2
        elif arg in ("-s", "--size"):
            if i + 1 >= len(argv):
                print(f"Error: {arg} requires a value")
                return 1
            try:
                width = int(argv[i + 1])
            except ValueError:
                print(f"Error: {arg} requires a numeric value")
                return 1
            i += 2
        elif arg in ("-t", "--thickness"):
            if i + 1 >= len(argv):
                print(f"Error: {arg} requires a value")
                return 1
            try:
                thickness = int(argv[i + 1])
            except ValueError:
                print(f"Error: {arg} requires a numeric value")
                return 1
            i += 2
        elif arg in ("-b", "--background"):
            # Check if next arg exists and is not another flag
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                # Color value provided
                try:
                    bg_color = parse_background_color(argv[i + 1])
                except ValueError as e:
                    print(f"Error: {e}")
                    show_help()
                    return 1
                i += 2
            else:
                # No color value, default to black
                bg_color = (0, 0, 0, 255)
                i += 1
        elif arg == "--layers":
            save_layers = True
            i += 1
        else:
            print(f"Error: Unknown option: {arg}")
            show_help()
            return 1

    print(f"Loading {source}...")
    try:
        wad = WAD()
        wad.from_file(source)
    except Exception as e:
        print(f"Error loading WAD: {e}")
        return 1

    # Determine which maps to draw
    if pattern is None:
        # Draw ALL maps
        map_names = list(wad.maps.keys())
        print(f"Drawing all {len(map_names)} maps...")
    else:
        # Convert pattern to uppercase for case-insensitive matching
        pattern_upper = pattern.upper()

        # Wildcard detection: if pattern has * or ?, treat as wildcard; otherwise exact map name.
        is_wild = ("*" in pattern_upper) or ("?" in pattern_upper)

        if is_wild:
            # Use uppercase pattern for wildcard search
            map_names = list(wad.maps.find(pattern_upper))
        else:
            # Exact mode: search case-insensitively
            # First try direct lookup with uppercase
            if pattern_upper in wad.maps:
                map_names = [pattern_upper]
            else:
                # Fallback: check all map names case-insensitively
                all_maps = list(wad.maps.keys())
                map_names = [m for m in all_maps if m.upper() == pattern_upper]

        if not map_names:
            print(f"No maps matched: {pattern}")
            print(f"Available maps in WAD: {', '.join(list(wad.maps.keys())[:10])}" + 
                  (f" ... ({len(wad.maps)} total)" if len(wad.maps) > 10 else ""))
            return 2

    # Draw all matched maps
    for name in map_names:
        status = f"Drawing {name} ({width}px"
        if thickness > 1:
            status += f", thickness={thickness}"
        if bg_color != (0, 0, 0, 0):
            if bg_color == (0, 0, 0, 255):
                status += ", black bg"
            else:
                status += f", bg=#{bg_color[0]:02x}{bg_color[1]:02x}{bg_color[2]:02x}"
        if save_layers:
            status += ", with layers"
        status += ")"
        print(status)
        
        try:
            drawmap(wad, name, width, save_layers=save_layers, thickness=thickness, bg_color=bg_color)
        except Exception as e:
            print(f"Error drawing {name}: {e}")

    print(f"\nDone! Generated {len(map_names)} map(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))