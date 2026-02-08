"""Colormap generation with lighting calculations"""

from PIL import Image
from .utils import COLORS, COLORMAP_ROWS, NUMLIGHTS, best_color


def generate_colormap(palette, with_lighting=True):
    """
    Generate a 34-row colormap from a palette.
    
    Args:
        palette: List of 256 (r, g, b) tuples
        with_lighting: If True, apply progressive darkening (rows 0-31)
                      If False, all rows 0-31 are full brightness
    
    Returns:
        List of 34 lists, each containing 256 palette indices
    """
    colormap = []
    
    if with_lighting:
        # Normal light levels (rows 0-31): progressive darkening
        for level in range(NUMLIGHTS):
            row = []
            for r, g, b in palette:
                # Darken based on light level
                # Level 0 = full bright, level 31 = darkest
                nr = (r * (NUMLIGHTS - level) + NUMLIGHTS // 2) // NUMLIGHTS
                ng = (g * (NUMLIGHTS - level) + NUMLIGHTS // 2) // NUMLIGHTS
                nb = (b * (NUMLIGHTS - level) + NUMLIGHTS // 2) // NUMLIGHTS
                idx = best_color(nr, ng, nb, palette)
                row.append(idx)
            colormap.append(row)
    else:
        # No lighting: all rows 0-31 are full brightness (identity mapping)
        full_bright_row = list(range(COLORS))
        for _ in range(NUMLIGHTS):
            colormap.append(full_bright_row[:])
    
    # Row 32: Invulnerability effect (inverse grayscale)
    invuln = []
    for r, g, b in palette:
        # Convert to grayscale and invert
        fr = r / 255.0
        fg = g / 255.0
        fb = b / 255.0
        gray = fr * 0.299 + fg * 0.587 + fb * 0.144
        gray = 1.0 - gray
        gv = int(gray * 255)
        idx = best_color(gv, gv, gv, palette)
        invuln.append(idx)
    colormap.append(invuln)
    
    # Row 33: Pure black (unused in vanilla Doom, but expected by tools)
    black_row = [best_color(0, 0, 0, palette)] * COLORS
    colormap.append(black_row)
    
    return colormap


def colormap_to_png(colormap, palette, output_path):
    """
    Save colormap as a PNG visualization.
    
    Args:
        colormap: List of 34 rows of 256 palette indices
        palette: List of 256 (r, g, b) tuples
        output_path: Where to save the PNG
    """
    h = len(colormap)
    w = COLORS
    
    img = Image.new("RGB", (w, h))
    px = img.load()
    
    for y in range(h):
        for x in range(w):
            idx = colormap[y][x]
            px[x, y] = palette[idx]
    
    img.save(output_path)


def colormap_to_binary(colormap):
    """
    Convert colormap to raw binary format (8704 bytes).
    
    Args:
        colormap: List of 34 rows of 256 palette indices
        
    Returns:
        bytes object (8704 bytes)
    """
    data = bytearray()
    for row in colormap:
        for idx in row:
            data.append(idx)
    return bytes(data)
