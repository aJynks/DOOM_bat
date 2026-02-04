#!/usr/bin/env python3
"""doompal - Doom palette and colormap tool (Standalone Version)"""
import sys
import os
import struct
from pathlib import Path
from PIL import Image
import numpy as np

__version__ = "1.0.0"


# ============================================================================
# MODULE: utils.py
# ============================================================================


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

# ============================================================================
# MODULE: palette.py
# ============================================================================




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

# ============================================================================
# MODULE: colormap.py
# ============================================================================




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

# ============================================================================
# MODULE: hald.py
# ============================================================================




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

# ============================================================================
# MODULE: cube.py
# ============================================================================




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
    
    # Generate palette-remapped HALD
    hald = generate_palette_hald(palette)
    
    # Convert to .cube
    hald_to_cube(hald, output_path, title)

# ============================================================================
# MODULE: wad.py
# ============================================================================




class WADFile:
    """Simple WAD file reader for extracting lumps"""
    
    def __init__(self, path):
        """
        Open a WAD file and read its directory.
        
        Args:
            path: Path to .wad file
        """
        self.path = Path(path)
        self.lumps = {}
        
        with open(self.path, "rb") as f:
            # Read WAD header
            magic = f.read(4)
            if magic not in (b"IWAD", b"PWAD"):
                raise ValueError(f"Not a valid WAD file: {path}")
            
            numlumps, diroffset = struct.unpack("<II", f.read(8))
            
            # Read directory
            f.seek(diroffset)
            for _ in range(numlumps):
                filepos, size = struct.unpack("<II", f.read(8))
                name = f.read(8).rstrip(b'\x00').decode('ascii', errors='ignore')
                self.lumps[name.upper()] = (filepos, size)
    
    def has_lump(self, name):
        """Check if lump exists in WAD"""
        return name.upper() in self.lumps
    
    def read_lump(self, name):
        """
        Read lump data from WAD.
        
        Args:
            name: Lump name (case-insensitive)
            
        Returns:
            bytes object containing lump data
            
        Raises:
            KeyError: If lump not found
        """
        name = name.upper()
        if name not in self.lumps:
            raise KeyError(f"Lump '{name}' not found in WAD")
        
        filepos, size = self.lumps[name]
        
        with open(self.path, "rb") as f:
            f.seek(filepos)
            return f.read(size)
    
    def list_lumps(self):
        """Get list of all lump names"""
        return list(self.lumps.keys())
    
    def find_boom_colormaps(self):
        """
        Find all Boom colormaps (between C_START and C_END markers).
        
        Returns:
            List of colormap lump names
        """
        lumps = self.list_lumps()
        
        # Find C_START and C_END
        try:
            start_idx = lumps.index("C_START")
            end_idx = lumps.index("C_END")
        except ValueError:
            return []  # No Boom colormaps
        
        # Return lumps between markers
        return lumps[start_idx + 1:end_idx]


def extract_playpal(wad_path):
    """
    Extract PLAYPAL lump from WAD.
    
    Args:
        wad_path: Path to WAD file
        
    Returns:
        bytes object (10752 bytes) or None if not found
    """
    wad = WADFile(wad_path)
    
    if not wad.has_lump("PLAYPAL"):
        return None
    
    return wad.read_lump("PLAYPAL")


def extract_colormap(wad_path, lump_name="COLORMAP"):
    """
    Extract COLORMAP (or Boom colormap) lump from WAD.
    
    Args:
        wad_path: Path to WAD file
        lump_name: Name of colormap lump (default "COLORMAP")
        
    Returns:
        bytes object (8704 bytes) or None if not found
    """
    wad = WADFile(wad_path)
    
    if not wad.has_lump(lump_name):
        return None
    
    return wad.read_lump(lump_name)


def read_wad_lump(wad_path, lump_name):
    """
    Read a lump from WAD file (backward compatibility wrapper).
    
    Args:
        wad_path: Path to WAD file
        lump_name: Lump name
        
    Returns:
        bytes object or None if not found
    """
    wad = WADFile(wad_path)
    
    if not wad.has_lump(lump_name):
        return None
    
    return wad.read_lump(lump_name)


def find_boom_colormaps(wad_path):
    """
    Find all Boom colormaps in WAD (backward compatibility wrapper).
    
    Returns:
        List of tuples (name, filepos, size)
    """
    wad = WADFile(wad_path)
    colormap_names = wad.find_boom_colormaps()
    
    # Return with filepos and size info
    result = []
    for name in colormap_names:
        if name in wad.lumps:
            filepos, size = wad.lumps[name]
            result.append((name, filepos, size))
    
    return result

# ============================================================================
# HELP FUNCTION
# ============================================================================

def print_compact_help():
    """Print compact command listing"""
    print("doompal - Doom palette and colormap tool")
    print()
    print("USAGE:")
    print("  doompal <input>                                    Auto-batch mode")
    print("  doompal <command> <input> [output] [options]")
    print()
    print("COMMANDS:")
    print("  cube      <input> [output.cube]                   Generate .cube LUT for image editors")
    print("  batch     <input> <o>                             Generate all files (cube, playpal, colormap, split)")
    print("  playpal   <input> [output] [--slade] [--blank]    Generate 256×14 PLAYPAL")
    print("  colormap  <input> <o> [--blank]                   Generate 256×34 colormap with lighting")
    print("  blank     <input> <o>                             Generate blank playpal + colormap (no tints/lighting)")
    print("  slade     <input> <o> [--all] [--cell N]          Generate SLADE-style 16×16 grid palette")
    print("  extract   <wad> [output] [options]                Extract PLAYPAL/COLORMAP from WAD")
    print("  split     <input> <o>                             Generate transparent tint overlay PNG")
    print()
    print("COMMAND DETAILS:")
    print("  cube        Inputs pal0, outputs LUT cube for sRGB image editing apps")
    print()
    print("  batch       Inputs pal0, outputs:")
    print("              - .cube LUT file")
    print("              - 256×14 playpal.png")
    print("              - 256×34 colormap.png")
    print("              - transparent tint split.png")
    print()
    print("  playpal     Input pal0, output 256×14 playpal PNG")
    print("              --slade : Output binary playpal.pal instead of PNG")
    print("              --blank : All 14 rows same (no tinting)")
    print()
    print("  colormap    Input pal0, generate primary colormap with lighting")
    print("              --blank : No lighting (full brightness rows 0-31)")
    print()
    print("  blank       Input pal0, output both:")
    print("              - blank playpal (no tints)")
    print("              - blank colormap (no lighting)")
    print()
    print("  slade       Input palette, generate SLADE-style 16×16 grid pal0.png")
    print("              --playpal : Output binary playpal.pal (14 palettes) instead of PNG")
    print("              --cell N : Cell size (default 8 = 128×128 output)")
    print()
    print("  extract     Extract from WAD (PLAYPAL + primary COLORMAP if found)")
    print("              --boom [LUMPNAME] : Extract specific Boom colormap")
    print("              --boom : Extract all Boom colormaps")
    print("              --boomlist : List all Boom colormaps in WAD")
    print()
    print("  split       Input pal0, output transparent overlay PNG showing")
    print("              damage/item/radsuit tints (apply to blank playpals)")
    print()
    print("SUPPORTED INPUT FORMATS:")
    print("  - playpal.pal        SLADE binary (14 palettes, 10752 bytes)")
    print("  - pal0.pal           SLADE binary (single palette, 768 bytes)")
    print("  - pal0.png           256×1 PNG (DoomTools style)")
    print("  - playpal.png        256×14 PNG (DoomTools style)")
    print("  - colormap.png       256×34 PNG (extracts row 0 as pal0)")
    print("  - slade_pal0.png     16×16 grid PNG (SLADE style)")
    print("  - *.wad              WAD files (extracts PLAYPAL lump)")
    print()
    print("  Note: Binary colormap lumps (.cmp) are NOT valid inputs")
    print()
    print("OPTIONS:")
    print("  -h, --help           Show this help")
    print("  --version            Show version")
    print()
    print("NOTES:")
    print("  Running 'doompal <inputfile>' with no command automatically runs batch mode")



# ============================================================================
# COMMAND FUNCTIONS
# ============================================================================

def cmd_cube(args):
    """Generate .cube LUT from palette"""
    input_path = args.input
    
    # Determine output path
    if args.output:
        output_path = args.output
        # Auto-add .cube extension if missing
        if not str(output_path).endswith(".cube"):
            output_path = Path(str(output_path) + ".cube")
    else:
        # Use input name with .cube extension
        output_path = input_path.with_suffix(".cube")
    
    try:
        print(f"Loading palette from: {input_path}")
        
        # Handle WAD files
        if input_path.suffix.lower() == ".wad":
            data = extract_playpal(input_path)
            if data is None:
                print(f"ERROR: PLAYPAL not found in WAD: {input_path}", file=sys.stderr)
                return 1
            
            # Extract pal0 from PLAYPAL
            palette = extract_palette_from_binary(data, 0)
        else:
            palette = load_palette(input_path)
        
        print(f"Generating HALD CLUT and converting to .cube...")
        
        # Generate HALD and convert to cube
        
        hald_identity = generate_hald_identity(size=8)
        hald_indexed = remap_hald_to_palette(hald_identity, palette)
        
        # Ensure output is RGB mode (should already be, but be explicit)
        if hald_indexed.mode != "RGB":
            hald_indexed = hald_indexed.convert("RGB")
        
        hald_to_cube(hald_indexed, output_path)
        
        print(f"Successfully wrote: {output_path}")
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_batch(args):
    """Generate all outputs (cube, playpal, colormap, split)"""
    input_path = args.input
    output_base = args.output
    
    try:
        # Check if input is a WAD file
        if str(input_path).lower().endswith('.wad'):
            return cmd_batch_wad(input_path, output_base)
        
        # Regular batch processing for palette files
        print(f"Loading palette from: {input_path}")
        palette = load_palette(input_path)
        
        # Expand to 14 palettes
        palettes = expand_palette_to_14(palette)
        
        outputs = {}
        
        # 1. Generate .cube LUT
        print("Generating .cube LUT...")
        cube_path = Path(f"{output_base}.cube")
        hald_identity = generate_hald_identity(size=8)
        hald_indexed = remap_hald_to_palette(hald_identity, palette)
        if hald_indexed.mode != "RGB":
            hald_indexed = hald_indexed.convert("RGB")
        hald_to_cube(hald_indexed, cube_path)
        outputs["Cube LUT"] = cube_path
        
        # 2. Generate 256×14 PLAYPAL PNG
        print("Generating PLAYPAL...")
        playpal_path = Path(f"{output_base}_playpal.png")
        img = Image.new("RGB", (COLORS, 14))
        px = img.load()
        for row in range(14):
            for col in range(COLORS):
                px[col, row] = palettes[row][col]
        img.save(playpal_path)
        outputs["PLAYPAL"] = playpal_path
        
        # 3. Generate 256×34 colormap with lighting
        print("Generating colormap...")
        colormap_path = Path(f"{output_base}_colormap.png")
        colormap = generate_colormap(palette, with_lighting=True)
        colormap_to_png(colormap, palette, colormap_path)
        outputs["COLORMAP"] = colormap_path
        
        # 4. Generate transparent tint split overlay
        print("Generating tint split overlay...")
        split_path = Path(f"{output_base}_split.png")
        out = Image.new("RGBA", (COLORS, 14))
        out_px = out.load()
        
        # Row 0: fully transparent
        for x in range(COLORS):
            out_px[x, 0] = (0, 0, 0, 0)
        
        # Rows 1-13: tint colors with alpha
        tints = [
            None,  # Row 0
            ((252, 2, 3), 0.11),
            ((255, 0, 0), 0.22),
            ((255, 0, 0), 0.33),
            ((255, 0, 0), 0.44),
            ((255, 0, 0), 0.55),
            ((255, 0, 0), 0.66),
            ((255, 0, 0), 0.77),
            ((255, 0, 0), 0.88),
            ((215, 185, 68), 0.12),
            ((215, 185, 68), 0.25),
            ((215, 185, 68), 0.375),
            ((215, 185, 68), 0.50),
            ((3, 253, 3), 0.125),
        ]
        
        for row in range(1, 14):
            tint_color, tint_amount = tints[row]
            alpha = int(tint_amount * 255)
            for x in range(COLORS):
                r, g, b = tint_color
                out_px[x, row] = (r, g, b, alpha)
        
        out.save(split_path)
        outputs["Tint split"] = split_path
        
        print("\nGenerated files:")
        for name, path in outputs.items():
            print(f"  {name}: {path}")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_batch_wad(wad_path, output_base):
    """Special batch processing for WAD files"""
    
    print(f"Processing WAD file: {wad_path}")
    outputs = {}
    
    # Step 1 & 2: Check for PLAYPAL and COLORMAP
    playpal_data = read_wad_lump(wad_path, "PLAYPAL")
    colormap_data = read_wad_lump(wad_path, "COLORMAP")
    
    # Step 3: Error if neither present
    if not playpal_data and not colormap_data:
        print("ERROR: WAD contains neither PLAYPAL nor COLORMAP lumps", file=sys.stderr)
        return 1
    
    # Determine which palette to use (pal0)
    if playpal_data:
        print("Found PLAYPAL in WAD")
        palette = extract_palette_from_binary(playpal_data, 0)
        all_palettes = [extract_palette_from_binary(playpal_data, i) for i in range(14)]
    elif colormap_data:
        print("Found COLORMAP in WAD (no PLAYPAL)")
        # Extract palette from colormap row 0
        # Note: colormap stores indices, need to reconstruct palette
        # For now, we'll create it from the colormap PNG visualization
        print("Warning: Extracting palette from COLORMAP indices - may not be accurate")
        # This is a fallback - ideally WADs should have PLAYPAL
        palette = None
        all_palettes = None
    else:
        print("ERROR: No valid palette source found", file=sys.stderr)
        return 1
    
    # Step 4: Extract COLORMAP as PNG if present
    colormap_png_path = None
    if colormap_data and playpal_data:
        print("Extracting COLORMAP as PNG...")
        colormap_png_path = Path(f"{output_base}_colormap.png")
        img = Image.new("RGB", (COLORS, 34))
        px = img.load()
        for row in range(34):
            for col in range(COLORS):
                idx = colormap_data[row * COLORS + col]
                px[col, row] = palette[idx] if idx < len(palette) else (0, 0, 0)
        img.save(colormap_png_path)
        outputs["COLORMAP (extracted)"] = colormap_png_path
    
    # Step 5: Extract PLAYPAL as 256×14 PNG if present
    playpal_png_path = None
    if playpal_data:
        print("Extracting PLAYPAL as PNG...")
        playpal_png_path = Path(f"{output_base}_playpal.png")
        img = Image.new("RGB", (COLORS, 14))
        px = img.load()
        for row in range(14):
            for col in range(COLORS):
                px[col, row] = all_palettes[row][col]
        img.save(playpal_png_path)
        outputs["PLAYPAL (extracted)"] = playpal_png_path
    
    # Step 6: Colormap preference (already handled - we extracted it if present)
    # Step 7: If no PLAYPAL, create from colormap row 0
    if not playpal_data and colormap_data:
        print("ERROR: Cannot reliably extract palette from COLORMAP without PLAYPAL", file=sys.stderr)
        print("COLORMAP contains palette indices, not RGB values", file=sys.stderr)
        return 1
    
    # Step 8: If no colormap, generate one from PLAYPAL
    if not colormap_data and playpal_data:
        print("Generating COLORMAP from PLAYPAL...")
        colormap_png_path = Path(f"{output_base}_colormap.png")
        colormap = generate_colormap(palette, with_lighting=True)
        colormap_to_png(colormap, palette, colormap_png_path)
        outputs["COLORMAP (generated)"] = colormap_png_path
    
    # Step 9: Generate cube from pal0
    if palette:
        print("Generating .cube LUT from pal0...")
        cube_path = Path(f"{output_base}.cube")
        hald_identity = generate_hald_identity(size=8)
        hald_indexed = remap_hald_to_palette(hald_identity, palette)
        if hald_indexed.mode != "RGB":
            hald_indexed = hald_indexed.convert("RGB")
        hald_to_cube(hald_indexed, cube_path)
        outputs["Cube LUT"] = cube_path
    
    # Step 10: Create split PNG version
    if all_palettes:
        print("Generating tint split overlay...")
        split_path = Path(f"{output_base}_split.png")
        out = Image.new("RGBA", (COLORS, 14))
        out_px = out.load()
        
        for x in range(COLORS):
            out_px[x, 0] = (0, 0, 0, 0)
        
        tints = [
            None,
            ((252, 2, 3), 0.11),
            ((255, 0, 0), 0.22),
            ((255, 0, 0), 0.33),
            ((255, 0, 0), 0.44),
            ((255, 0, 0), 0.55),
            ((255, 0, 0), 0.66),
            ((255, 0, 0), 0.77),
            ((255, 0, 0), 0.88),
            ((215, 185, 68), 0.12),
            ((215, 185, 68), 0.25),
            ((215, 185, 68), 0.375),
            ((215, 185, 68), 0.50),
            ((3, 253, 3), 0.125),
        ]
        
        for row in range(1, 14):
            tint_color, tint_amount = tints[row]
            alpha = int(tint_amount * 255)
            for x in range(COLORS):
                r, g, b = tint_color
                out_px[x, row] = (r, g, b, alpha)
        
        out.save(split_path)
        outputs["Tint split"] = split_path
    
    # Step 11: Extract all Boom colormaps if found
    boom_colormaps = find_boom_colormaps(wad_path)
    if boom_colormaps and playpal_data:
        print(f"Found {len(boom_colormaps)} Boom colormap(s), extracting...")
        with open(wad_path, 'rb') as f:
            for name, filepos, size in boom_colormaps:
                f.seek(filepos)
                data = f.read(size)
                
                # Save as PNG
                png_path = Path(f"{output_base}_{name}.png")
                img = Image.new("RGB", (COLORS, 34))
                px = img.load()
                for row in range(34):
                    for col in range(COLORS):
                        idx = data[row * COLORS + col]
                        px[col, row] = palette[idx] if idx < len(palette) else (0, 0, 0)
                img.save(png_path)
                outputs[f"Boom colormap ({name})"] = png_path
    
    print("\nGenerated files:")
    for name, path in outputs.items():
        print(f"  {name}: {path}")
    
    return 0


def cmd_playpal(args):
    """Generate 256×14 PLAYPAL PNG or SLADE .pal binary"""
    input_path = args.input
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        # Default: input_name_playpal.png (or .pal for -slade)
        ext = ".pal" if args.slade else ".png"
        output_path = input_path.with_stem(f"{input_path.stem}_playpal").with_suffix(ext)
    
    # Auto-add correct extension if missing
    if args.slade and not str(output_path).endswith(".pal"):
        output_path = Path(str(output_path) + ".pal")
    elif not args.slade and not str(output_path).endswith(".png"):
        output_path = Path(str(output_path) + ".png")
    
    try:
        print(f"Loading palette from: {input_path}")
        
        # Try to load all 14 palettes
        kind = detect_palette_type(str(input_path))
        
        if kind in ("playpal14PNG", "playpal.pal binary"):
            # Has 14 palettes
            if args.blank:
                # Blank mode: use only pal0 for all 14 rows
                palette = load_palette(input_path, palette_index=0)
                palettes = [palette] * 14
                print("Note: Generating blank PLAYPAL (all 14 rows same as pal0)")
            else:
                palettes = load_all_palettes(input_path)
        else:
            # Single palette
            palette = load_palette(input_path)
            if args.blank:
                # Blank mode: repeat pal0 for all 14 rows
                palettes = [palette] * 14
                print("Note: Generating blank PLAYPAL (all 14 rows same as pal0)")
            else:
                # Expand to 14 with tinting
                palettes = expand_palette_to_14(palette)
                print("Note: Single palette detected, generating 14 palettes with damage/bonus/radsuit tints")
        
        if args.slade:
            # Write SLADE-compatible binary .pal file
            with open(output_path, "wb") as f:
                for pal in palettes:
                    for r, g, b in pal:
                        f.write(bytes((r, g, b)))
            print(f"Successfully wrote SLADE playpal.pal: {output_path}")
        else:
            # Create 256×14 PNG
            img = Image.new("RGB", (COLORS, 14))
            px = img.load()
            
            for row in range(14):
                for col in range(COLORS):
                    px[col, row] = palettes[row][col]
            
            img.save(output_path)
            print(f"Successfully wrote: {output_path}")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_colormap(args):
    """Generate 256×34 colormap PNG with or without lighting"""
    input_path = args.input
    output_path = args.output
    
    try:
        print(f"Loading palette from: {input_path}")
        palette = load_palette(input_path)  # Always use pal0
        
        if args.blank:
            print("Generating blank colormap (no lighting)...")
            colormap = generate_colormap(palette, with_lighting=False)
        else:
            print("Generating colormap with lighting...")
            colormap = generate_colormap(palette, with_lighting=True)
        
        colormap_to_png(colormap, palette, output_path)
        
        print(f"Successfully wrote: {output_path}")
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_blank(args):
    """Generate blank PLAYPAL and COLORMAP (no tints, no lighting)"""
    input_path = args.input
    output_base = args.output
    
    try:
        print(f"Loading palette from: {input_path}")
        palette = load_palette(input_path)
        
        outputs = {}
        
        # Generate blank PLAYPAL (all 14 rows same as pal0)
        print("Generating blank PLAYPAL (all 14 rows same)...")
        playpal_path = Path(f"{output_base}_playpal.png")
        img_playpal = Image.new("RGB", (COLORS, 14))
        px_playpal = img_playpal.load()
        
        for row in range(14):
            for col in range(COLORS):
                px_playpal[col, row] = palette[col]
        
        img_playpal.save(playpal_path)
        outputs["Blank PLAYPAL"] = playpal_path
        
        # Generate blank COLORMAP (no lighting, but preserve invuln/black rows)
        print("Generating blank COLORMAP (no lighting)...")
        colormap_path = Path(f"{output_base}_colormap.png")
        colormap = generate_colormap(palette, with_lighting=False)
        colormap_to_png(colormap, palette, colormap_path)
        outputs["Blank COLORMAP"] = colormap_path
        
        print("\nGenerated files:")
        for name, path in outputs.items():
            print(f"  {name}: {path}")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_slade(args):
    """Generate SLADE-style 16×16 grid palette or binary playpal.pal"""
    input_path = args.input
    output_base = args.output
    cell_size = args.cell
    
    # Fix: Default output to input filename if not provided
    if output_base is None:
        output_base = input_path.stem
    else:
        # Convert to string to avoid Path issues
        output_base = str(output_base)
    
    try:
        print(f"Loading palette from: {input_path}")
        
        # Determine if we have 14 palettes or just 1
        kind = detect_palette_type(str(input_path))
        
        # Always try to get/generate 14 palettes for --playpal
        if kind in ("playpal14PNG", "playpal.pal binary"):
            # Load all 14 palettes
            palettes = load_all_palettes(input_path)
        else:
            # Single palette - expand to 14 with tints
            palette = load_palette(input_path)
            palettes = expand_palette_to_14(palette)
            print("Note: Expanding single palette to 14 with tints")
        
        # Handle --playpal flag (output binary .pal file with all 14 palettes)
        if args.playpal:
            output_path = Path(output_base)
            # Don't double-add extension
            if not str(output_path).endswith('.pal'):
                output_path = Path(str(output_path) + '.pal')
            
            print(f"Writing binary playpal.pal (14 palettes)...")
            with open(output_path, 'wb') as f:
                for pal in palettes:
                    for r, g, b in pal:
                        f.write(bytes((r, g, b)))
            
            print(f"Wrote: {output_path} (10752 bytes)")
            return 0
        
        # Generate grid PNG (just pal0)
        grid_size = GRID_SIZE * cell_size  # 16 * 8 = 128 by default
        pal = palettes[0]  # Just pal0
        
        # Create 16×16 grid
        img = Image.new("RGB", (grid_size, grid_size))
        px = img.load()
        
        idx = 0
        for gy in range(GRID_SIZE):
            for gx in range(GRID_SIZE):
                color = pal[idx]
                
                # Fill cell
                x0 = gx * cell_size
                y0 = gy * cell_size
                for yy in range(y0, y0 + cell_size):
                    for xx in range(x0, x0 + cell_size):
                        px[xx, yy] = color
                
                idx += 1
        
        # Don't double-add .png extension
        output_path = Path(output_base + "_pal0")
        if not str(output_path).endswith('.png'):
            output_path = Path(str(output_path) + '.png')
        
        img.save(output_path)
        print(f"Wrote: {output_path} ({grid_size}×{grid_size})")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_extract(args):
    """Extract PLAYPAL and COLORMAP from WAD"""
    wad_path = args.wad
    
    # Determine output base name
    if args.output:
        output_base = args.output
    else:
        output_base = wad_path.stem
    
    try:
        wad = WADFile(wad_path)
        
        # Handle -boomlist
        if args.boomlist:
            boom_maps = wad.find_boom_colormaps()
            if boom_maps:
                print("Boom colormaps found:")
                for name in boom_maps:
                    print(f"  - {name}")
            else:
                print("No Boom colormaps found (no C_START/C_END markers)")
            return 0
        
        # Determine what to extract
        extract_playpal_lump = True
        extract_colormap_lump = True
        extract_boom = []
        
        if args.boom is not None:
            if args.boom == "__all__":
                # Extract all Boom colormaps only
                extract_playpal_lump = False
                extract_colormap_lump = False
                extract_boom = wad.find_boom_colormaps()
            else:
                # Extract specific Boom colormap only
                extract_playpal_lump = False
                extract_colormap_lump = False
                extract_boom = [args.boom.upper()]
        else:
            # Default: extract everything
            extract_boom = wad.find_boom_colormaps()
        
        extracted = []
        
        # Extract PLAYPAL
        if extract_playpal_lump:
            if wad.has_lump("PLAYPAL"):
                data = wad.read_lump("PLAYPAL")
                
                # Save .pal binary
                pal_path = Path(f"{output_base}_playpal.pal")
                pal_path.write_bytes(data)
                extracted.append(f"PLAYPAL → {pal_path}")
                
                # Save PNG visualization
                img = Image.new("RGB", (COLORS, 14))
                px = img.load()
                for row in range(14):
                    pal = extract_palette_from_binary(data, row)
                    for col in range(COLORS):
                        px[col, row] = pal[col]
                
                png_path = Path(f"{output_base}_playpal.png")
                img.save(png_path)
                extracted.append(f"PLAYPAL → {png_path} (visualization)")
            else:
                print("WARNING: PLAYPAL not found in WAD")
        
        # Extract COLORMAP
        if extract_colormap_lump:
            if wad.has_lump("COLORMAP"):
                data = wad.read_lump("COLORMAP")
                
                # Save .cmp binary
                cmp_path = Path(f"{output_base}_colormap.cmp")
                cmp_path.write_bytes(data)
                extracted.append(f"COLORMAP → {cmp_path}")
                
                # Save PNG visualization
                # Load primary palette for visualization
                if wad.has_lump("PLAYPAL"):
                    playpal_data = wad.read_lump("PLAYPAL")
                    palette = extract_palette_from_binary(playpal_data, 0)
                    
                    img = Image.new("RGB", (COLORS, 34))
                    px = img.load()
                    
                    for y in range(34):
                        for x in range(COLORS):
                            idx = data[y * COLORS + x]
                            px[x, y] = palette[idx]
                    
                    png_path = Path(f"{output_base}_colormap.png")
                    img.save(png_path)
                    extracted.append(f"COLORMAP → {png_path} (visualization)")
            else:
                print("WARNING: COLORMAP not found in WAD")
        
        # Extract Boom colormaps
        for lump_name in extract_boom:
            if wad.has_lump(lump_name):
                data = wad.read_lump(lump_name)
                
                # Save .cmp binary
                cmp_path = Path(f"{output_base}_{lump_name}.cmp")
                cmp_path.write_bytes(data)
                extracted.append(f"{lump_name} → {cmp_path}")
                
                # Save PNG visualization (if PLAYPAL available)
                if wad.has_lump("PLAYPAL"):
                    playpal_data = wad.read_lump("PLAYPAL")
                    palette = extract_palette_from_binary(playpal_data, 0)
                    
                    rows = len(data) // COLORS
                    img = Image.new("RGB", (COLORS, rows))
                    px = img.load()
                    
                    for y in range(rows):
                        for x in range(COLORS):
                            idx = data[y * COLORS + x]
                            px[x, y] = palette[idx]
                    
                    png_path = Path(f"{output_base}_{lump_name}.png")
                    img.save(png_path)
                    extracted.append(f"{lump_name} → {png_path} (visualization)")
        
        if extracted:
            print("Extracted files:")
            for item in extracted:
                print(f"  {item}")
            return 0
        else:
            print("No lumps extracted")
            return 1
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_split(args):
    """
    Extract tint overlay from palette as transparent PNG.
    
    Creates a 256×14 RGBA PNG where:
    - Row 0 is fully transparent (pal0 has no tint)
    - Rows 1-13 show only the tint color with appropriate transparency
    
    Accepts any palette format and generates the full playpal internally.
    """
    input_path = args.input
    output_path = args.output
    
    # Auto-add .png extension if not present
    if not str(output_path).lower().endswith('.png'):
        output_path = Path(str(output_path) + '.png')
    
    try:
        print(f"Loading palette from: {input_path}")
        
        # Load palette from any format
        palette = load_palette(input_path)
        
        # Generate full 14-palette playpal
        palettes = expand_palette_to_14(palette)
        
        # Create output RGBA image
        out = Image.new("RGBA", (COLORS, 14))
        out_px = out.load()
        
        # Row 0: fully transparent (pal0 has no tint)
        for x in range(COLORS):
            out_px[x, 0] = (0, 0, 0, 0)
        
        # Rows 1-13: extract the tint
        # Known tint amounts and colors from palette.py
        tints = [
            None,  # Row 0 - no tint
            ((252, 2, 3), 0.11),      # Row 1
            ((255, 0, 0), 0.22),      # Row 2
            ((255, 0, 0), 0.33),      # Row 3
            ((255, 0, 0), 0.44),      # Row 4
            ((255, 0, 0), 0.55),      # Row 5
            ((255, 0, 0), 0.66),      # Row 6
            ((255, 0, 0), 0.77),      # Row 7
            ((255, 0, 0), 0.88),      # Row 8
            ((215, 185, 68), 0.12),   # Row 9
            ((215, 185, 68), 0.25),   # Row 10
            ((215, 185, 68), 0.375),  # Row 11
            ((215, 185, 68), 0.50),   # Row 12
            ((3, 253, 3), 0.125),     # Row 13
        ]
        
        for row in range(1, 14):
            tint_color, tint_amount = tints[row]
            
            # Use the tint color with alpha based on tint amount
            # Convert amount (0.0-1.0) to alpha (0-255)
            alpha = int(tint_amount * 255)
            
            for x in range(COLORS):
                r, g, b = tint_color
                out_px[x, row] = (r, g, b, alpha)
        
        out.save(output_path)
        print(f"Successfully wrote transparent overlay: {output_path}")
        print("Note: Row 0 is fully transparent, rows 1-13 show tint colors with transparency")
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1



# ============================================================================
# MAIN
# ============================================================================

class Args:
    """Simple argument container"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def main():
    """Main entry point"""
    # Handle help
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help', '-help']:
        print_compact_help()
        return 0
    
    if sys.argv[1] in ['--version', '-v']:
        print(f"doompal version {__version__}")
        return 0
    
    # Determine command
    command = sys.argv[1]
    known_commands = ['cube', 'batch', 'playpal', 'colormap', 'colourmap', 
                      'blank', 'slade', 'extract', 'split']
    
    if command not in known_commands:
        # Auto-batch mode
        command = 'batch'
        input_path = Path(sys.argv[1])
        cmd_args = [sys.argv[1], input_path.stem] + sys.argv[2:]
    else:
        # Filter out flags from positional args
        cmd_args = [arg for arg in sys.argv[2:] if not arg.startswith('-')]
    
    # Build args object
    args = Args(
        input=Path(cmd_args[0]) if len(cmd_args) > 0 else None,
        output=Path(cmd_args[1]) if len(cmd_args) > 1 else None,
        slade='--slade' in sys.argv or '-slade' in sys.argv,
        blank='--blank' in sys.argv,
        all='--all' in sys.argv or '-all' in sys.argv,
        playpal='--playpal' in sys.argv,
        boom='--boom' in sys.argv or '-boom' in sys.argv,
        boom_list='--boomlist' in sys.argv or '-boomlist' in sys.argv,
        cell=8
    )
    
    # Extract --cell value if present
    for i, arg in enumerate(sys.argv):
        if arg == '--cell' and i+1 < len(sys.argv):
            try:
                args.cell = int(sys.argv[i+1])
            except ValueError:
                pass
    
    # Route to command handler
    try:
        if command == 'cube':
            return cmd_cube(args)
        elif command == 'batch':
            return cmd_batch(args)
        elif command == 'playpal':
            return cmd_playpal(args)
        elif command in ['colormap', 'colourmap']:
            return cmd_colormap(args)
        elif command == 'blank':
            return cmd_blank(args)
        elif command == 'slade':
            return cmd_slade(args)
        elif command == 'extract':
            return cmd_extract(args)
        elif command == 'split':
            return cmd_split(args)
        else:
            print(f"ERROR: Unknown command: {command}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
