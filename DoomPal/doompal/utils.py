"""Shared utilities and constants for doompal"""

# Palette constants
COLORS = 256
BYTES_PER_COLOR = 3
BYTES_PER_PALETTE = COLORS * BYTES_PER_COLOR  # 768
PALETTES_PER_PLAYPAL = 14
PLAYPAL_SIZE_BYTES = PALETTES_PER_PLAYPAL * BYTES_PER_PALETTE  # 10752

# Colormap constants
COLORMAP_ROWS = 34
COLORMAP_SIZE_BYTES = COLORS * COLORMAP_ROWS  # 8704
NUMLIGHTS = 32

# Grid constants
GRID_SIZE = 16  # 16×16 = 256 colors

# PNG signature for file type detection
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def is_png(path):
    """Check if file is a PNG by reading signature"""
    try:
        with open(path, "rb") as f:
            return f.read(8) == PNG_SIGNATURE
    except:
        return False


def best_color(r, g, b, palette):
    """
    Find the closest color in palette to given RGB values using
    Euclidean distance in RGB space.
    
    Args:
        r, g, b: Target RGB values (0-255)
        palette: List of (r, g, b) tuples
        
    Returns:
        Index of closest palette color
    """
    best_dist = (r * r + g * g + b * b) * 2
    best_index = 0

    for i, (pr, pg, pb) in enumerate(palette):
        dr = r - pr
        dg = g - pg
        db = b - pb
        dist = dr * dr + dg * dg + db * db
        
        if dist < best_dist:
            if dist == 0:
                return i
            best_dist = dist
            best_index = i

    return best_index
