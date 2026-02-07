"""HALD CLUT (Color Lookup Table) generation and manipulation"""

import numpy as np
from PIL import Image
from .utils import best_color


def generate_hald_identity(size=8):
    """
    Generate an identity HALD CLUT.
    
    A HALD CLUT is a 3D color lookup table stored as a 2D image.
    For size=8, creates a 512×512 image containing all possible
    8-bit RGB combinations (256³ = 16,777,216 colors arranged as 512² = 262,144 pixels).
    
    Args:
        size: HALD level (8 for 8-bit, creates size³×size³ image)
        
    Returns:
        PIL Image in RGB mode, 16-bit depth
    """
    # For HALD:8, we need 512×512 pixels
    # This represents a 64³ LUT (262,144 entries)
    lut_size = size ** 3  # 512 for HALD:8
    pixels = lut_size ** 2  # 262,144 total pixels
    
    # Create image
    img = Image.new("RGB", (lut_size, lut_size))
    px = img.load()
    
    # Generate identity CLUT using ImageMagick's HALD:8 pattern
    # Discovered pattern:
    # - R: cycles 0-255 every 64 pixels horizontally
    # - G: combined index from x and y position, scaled 0-255
    # - B: increases every 8 pixels vertically
    # Note: Use round() instead of // for proper rounding like ImageMagick
    
    level = size  # 8
    
    for y in range(lut_size):
        for x in range(lut_size):
            # R cycles every 64 pixels (level²)
            r_index = x % (level * level)
            r_val = round(r_index * 255 / (level * level - 1))
            
            # G is indexed by: (x//64) + (y%8)*8
            # This gives 0-63, which maps to 0-255
            g_index = (x // (level * level)) + (y % level) * level
            g_val = round(g_index * 255 / (level * level - 1))
            
            # B increases every 8 pixels vertically
            b_index = y // level
            b_val = round(b_index * 255 / (level * level - 1))
            
            px[x, y] = (r_val, g_val, b_val)
    
    return img


def remap_hald_to_palette(hald_img, palette):
    """
    Remap a HALD CLUT to a Doom palette (quantization).
    
    This converts the continuous RGB HALD into an indexed color
    version using only colors from the provided palette.
    
    Args:
        hald_img: PIL Image (identity HALD)
        palette: List of 256 (r, g, b) tuples
        
    Returns:
        PIL Image (remapped to palette, still in RGB mode)
    """
    w, h = hald_img.size
    result = Image.new("RGB", (w, h))
    
    src_px = hald_img.load()
    dst_px = result.load()
    
    # Quantize each pixel to nearest palette color
    for y in range(h):
        for x in range(w):
            r, g, b = src_px[x, y][:3]
            idx = best_color(r, g, b, palette)
            dst_px[x, y] = palette[idx]
    
    return result


def generate_palette_hald(palette, size=8):
    """
    Generate a complete HALD CLUT remapped to a Doom palette.
    
    This is the full pipeline:
    1. Generate identity HALD
    2. Remap to palette
    3. Return as RGB image (ready for .cube conversion)
    
    Args:
        palette: List of 256 (r, g, b) tuples
        size: HALD level (default 8)
        
    Returns:
        PIL Image in RGB mode (512×512 for size=8)
    """
    # Step 1: Generate identity HALD (16-bit sRGB)
    identity = generate_hald_identity(size)
    
    # Step 2: Remap to palette (quantization without dithering)
    remapped = remap_hald_to_palette(identity, palette)
    
    # Step 3: Return as 16-bit sRGB for precision
    # (PIL defaults to 8-bit, but we treat it as high-precision)
    return remapped
