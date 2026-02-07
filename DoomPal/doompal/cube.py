"""
.cube LUT file generation

Adapted from png2cube by picturefx
https://picturefx.itch.io/png2cube-converter-for-linux-and-windows
"""

import numpy as np
from PIL import Image


def validate_lut_dimensions(image_array):
    """
    Validate that image dimensions match a valid HALD CLUT.
    
    Args:
        image_array: numpy array of image (height, width, channels)
        
    Returns:
        LUT size (e.g., 64 for a 512×512 HALD:8)
        
    Raises:
        ValueError: If dimensions don't match a valid HALD CLUT
    """
    height, width, _ = image_array.shape
    total_pixels = width * height
    lut_size = int(round(total_pixels ** (1/3)))
    
    if lut_size ** 3 != total_pixels:
        raise ValueError(
            f"Image dimensions do not match a valid HALD CLUT. "
            f"Got {width}×{height} ({total_pixels} pixels). "
            f"Expected a cube (e.g., 512×512 for 64³ = 262,144 pixels)."
        )
    
    return lut_size


def hald_to_cube(hald_image, output_path, title=None):
    """
    Convert a HALD CLUT PNG to a .cube LUT file.
    
    Args:
        hald_image: PIL Image or path to PNG file
        output_path: Where to save the .cube file
        title: Optional title for the LUT (defaults to filename)
    """
    # Load image if path provided
    if isinstance(hald_image, str):
        hald_image = Image.open(hald_image)
    
    # Convert to RGB numpy array
    img_array = np.array(hald_image.convert("RGB"))
    
    # Validate dimensions
    lut_size = validate_lut_dimensions(img_array)
    
    # Flatten and normalize to 0.0-1.0
    pixels = img_array.reshape(-1, 3).astype(np.float32) / 255.0
    
    # Determine title
    if title is None:
        from pathlib import Path
        title = Path(output_path).stem
    
    # Write .cube file
    with open(output_path, "w") as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {lut_size}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        
        # Write LUT data in correct order: B→G→R
        for b in range(lut_size):
            for g in range(lut_size):
                for r in range(lut_size):
                    idx = r + g * lut_size + b * lut_size * lut_size
                    r_out, g_out, b_out = pixels[idx]
                    f.write(f"{r_out:.6f} {g_out:.6f} {b_out:.6f}\n")


def palette_to_cube(palette, output_path, title=None):
    """
    Generate a .cube LUT directly from a Doom palette.
    
    This is the complete pipeline:
    1. Generate HALD CLUT
    2. Remap to palette
    3. Convert to .cube
    
    Args:
        palette: List of 256 (r, g, b) tuples
        output_path: Where to save the .cube file
        title: Optional title for the LUT
    """
    from .hald import generate_palette_hald
    
    # Generate palette-remapped HALD
    hald = generate_palette_hald(palette)
    
    # Convert to .cube
    hald_to_cube(hald, output_path, title)
