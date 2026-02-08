"""Palette loading, detection, and format conversion"""

import os
from pathlib import Path
from PIL import Image
from .utils import (
    COLORS, BYTES_PER_PALETTE, PLAYPAL_SIZE_BYTES,
    GRID_SIZE, is_png
)


def detect_palette_type(path):
    """
    Detect the type of palette file.
    
    Returns one of:
        - "playpal14PNG": 256×14 PNG
        - "playpal1PNG": 256×1 PNG  
        - "colormap34PNG": 256×34 PNG (colormap - uses row 0 as palette)
        - "sladeStylePNG": 16×16 grid PNG
        - "playpal.pal binary": 10752 bytes (all 14 palettes)
        - "pal0.pal Binary": 768 bytes (single palette)
        - "colormap.cmp binary": 8704 bytes (colormap - needs companion PLAYPAL)
        - None: Unknown format
    """
    if not os.path.isfile(path):
        return None

    if is_png(path):
        with Image.open(path) as im:
            w, h = im.size

            if (w, h) == (COLORS, 14):
                return "playpal14PNG"
            if (w, h) == (COLORS, 1):
                return "playpal1PNG"
            if (w, h) == (COLORS, 34):
                return "colormap34PNG"
            if (w >= GRID_SIZE and h >= GRID_SIZE) and \
               (w % GRID_SIZE == 0) and (h % GRID_SIZE == 0):
                return "sladeStylePNG"
        return None

    # For binary files, use byte size
    size = os.path.getsize(path)
    
    if size == PLAYPAL_SIZE_BYTES:
        return "playpal.pal binary"
    if size == BYTES_PER_PALETTE:
        return "pal0.pal Binary"
    if size == COLORMAP_SIZE_BYTES:
        return "colormap.cmp binary"

    return None


def extract_palette_from_binary(data, palette_index=0):
    """
    Extract a single palette from raw binary data.
    
    Args:
        data: Raw palette bytes (768 or 10752 bytes)
        palette_index: Which palette to extract (0-13)
        
    Returns:
        List of 256 (r, g, b) tuples
    """
    if len(data) % BYTES_PER_PALETTE != 0:
        raise ValueError(f"Invalid palette data size: {len(data)} bytes")
    
    base = palette_index * BYTES_PER_PALETTE
    pal = []
    
    for i in range(COLORS):
        off = base + i * 3
        pal.append((data[off], data[off + 1], data[off + 2]))
    
    return pal


def extract_palette_from_strip(img):
    """
    Extract first row (pal0) from a palette strip PNG.
    
    Args:
        img: PIL Image (256×N or scaled)
        
    Returns:
        List of 256 (r, g, b) tuples
    """
    w, h = img.size
    
    # Handle scaled images
    if w % COLORS != 0:
        raise ValueError(f"Strip PNG width must be multiple of 256. Got {w}.")
    
    scale = w // COLORS
    if h % scale != 0:
        raise ValueError(f"Strip PNG height must be multiple of scale={scale}. Got {h}.")
    
    rows = h // scale
    
    # Downscale if needed
    if scale != 1:
        img = img.resize((COLORS, rows), Image.NEAREST)
    
    # Extract first row
    px = img.load()
    pal = []
    for x in range(COLORS):
        r, g, b = px[x, 0][:3]  # Handle RGBA
        pal.append((r, g, b))
    
    return pal


def extract_palette_from_grid(img):
    """
    Extract palette from SLADE-style 16×16 grid PNG.
    Samples center pixel of each cell.
    
    Args:
        img: PIL Image (divisible by 16 in both dimensions)
        
    Returns:
        List of 256 (r, g, b) tuples
    """
    w, h = img.size
    
    if w % GRID_SIZE != 0 or h % GRID_SIZE != 0:
        raise ValueError(f"Grid PNG must be divisible by 16. Got {w}×{h}.")
    
    cell_w = w // GRID_SIZE
    cell_h = h // GRID_SIZE
    
    px = img.load()
    pal = []
    
    for gy in range(GRID_SIZE):
        cy = gy * cell_h + cell_h // 2
        for gx in range(GRID_SIZE):
            cx = gx * cell_w + cell_w // 2
            r, g, b = px[cx, cy][:3]  # Handle RGBA
            pal.append((r, g, b))
    
    return pal


def load_palette(path, palette_index=0):
    """
    Load a palette from any supported format.
    
    Args:
        path: Path to palette file (.pal, .png, or .wad)
        palette_index: Which palette to extract (0-13), default 0
        
    Returns:
        List of 256 (r, g, b) tuples
        
    Raises:
        ValueError: If format is invalid or unsupported
    """
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Palette file not found: {path}")
    
    kind = detect_palette_type(str(path))
    
    if kind is None:
        raise ValueError(f"Unsupported palette format: {path}")
    
    # Handle PNG formats
    if kind in ("playpal14PNG", "playpal1PNG", "colormap34PNG", "sladeStylePNG"):
        with Image.open(path) as img:
            # Force conversion to sRGB colorspace
            # Some images may have palette mode or other color modes that need explicit conversion
            # Convert to RGB first to ensure proper color representation
            if img.mode == "P":
                # Palette mode - convert using the embedded palette
                img = img.convert("RGB")
            elif img.mode != "RGB":
                # Other modes (RGBA, L, etc.) - convert to RGB
                img = img.convert("RGB")
            
            # Now img is guaranteed to be RGB mode
            if kind in ("playpal14PNG", "playpal1PNG", "colormap34PNG"):
                # All use first row (row 0) as the palette
                return extract_palette_from_strip(img)
            else:  # sladeStylePNG
                return extract_palette_from_grid(img)
    
    # Handle binary formats
    data = path.read_bytes()
    return extract_palette_from_binary(data, palette_index)


def load_all_palettes(path):
    """
    Load all 14 palettes from a PLAYPAL file.
    
    Args:
        path: Path to PLAYPAL file (.pal or .png with 14 rows)
        
    Returns:
        List of 14 palettes, each a list of 256 (r, g, b) tuples
        
    Raises:
        ValueError: If file doesn't contain 14 palettes
    """
    path = Path(path)
    kind = detect_palette_type(str(path))
    
    if kind == "playpal14PNG":
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            
            # Handle scaled images
            if w % COLORS != 0:
                raise ValueError(f"Invalid PLAYPAL width: {w}")
            scale = w // COLORS
            if scale > 1:
                img = img.resize((COLORS, h // scale), Image.NEAREST)
            
            px = img.load()
            palettes = []
            
            for row in range(14):
                pal = []
                for x in range(COLORS):
                    r, g, b = px[x, row][:3]
                    pal.append((r, g, b))
                palettes.append(pal)
            
            return palettes
    
    elif kind == "playpal.pal binary":
        data = path.read_bytes()
        return [extract_palette_from_binary(data, i) for i in range(14)]
    
    else:
        raise ValueError(f"File does not contain 14 palettes: {path}")


def _clamp8(x):
    """Clamp value to 0-255 range"""
    if x < 0:
        return 0
    if x > 255:
        return 255
    return int(round(x))


def _blend(src, tint, amount):
    """
    Blend source color with tint color.
    
    Args:
        src: (r, g, b) source color
        tint: (r, g, b) tint color
        amount: blend amount 0.0-1.0 (0=src, 1=tint)
        
    Returns:
        (r, g, b) blended color
    """
    sr, sg, sb = src
    tr, tg, tb = tint
    return (
        _clamp8(sr * (1.0 - amount) + tr * amount),
        _clamp8(sg * (1.0 - amount) + tg * amount),
        _clamp8(sb * (1.0 - amount) + tb * amount),
    )


def expand_palette_to_14(pal0):
    """
    Generate all 14 Doom palettes from pal0 using damage/bonus/radsuit tinting.
    
    This approximates the original Doom palette generation algorithm:
    - Pal 0: Normal
    - Pal 1-8: Red tints (damage/berserk)
    - Pal 9-12: Yellow tints (bonus pickups)
    - Pal 13: Green tint (radiation suit)
    
    Based on algorithm by discord user, derived from Doom Wiki documentation.
    
    Args:
        pal0: Single palette (list of 256 RGB tuples)
        
    Returns:
        List of 14 palettes (each a list of 256 RGB tuples)
    """
    if len(pal0) != 256:
        raise ValueError("pal0 must have 256 colors")
    
    palettes = []
    
    # Palette 0: Normal (unchanged)
    palettes.append(pal0[:])
    
    # Palettes 1-8: Damage/berserk (red tints)
    # Pal 1: 11% toward RGB(252, 2, 3)
    pal1_tint = (252, 2, 3)
    palettes.append([_blend(c, pal1_tint, 0.11) for c in pal0])
    
    # Pal 2-8: 22%, 33%, 44%, 55%, 66%, 77%, 88% toward red
    red_tint = (255, 0, 0)
    for n in range(2, 9):
        amount = 0.11 * n
        palettes.append([_blend(c, red_tint, amount) for c in pal0])
    
    # Palettes 9-12: Bonus pickups (yellow tints)
    # 12%, 25%, 37.5%, 50% toward RGB(215, 185, 68)
    bonus_tint = (215, 185, 68)
    bonus_amounts = [0.12, 0.25, 0.375, 0.50]
    for amount in bonus_amounts:
        palettes.append([_blend(c, bonus_tint, amount) for c in pal0])
    
    # Palette 13: Radiation suit (green tint)
    # 12.5% toward RGB(3, 253, 3)
    rad_tint = (3, 253, 3)
    palettes.append([_blend(c, rad_tint, 0.125) for c in pal0])
    
    if len(palettes) != 14:
        raise AssertionError(f"Expected 14 palettes, got {len(palettes)}")
    
    return palettes
