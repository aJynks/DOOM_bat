#!/usr/bin/env python3
"""
doompal - Doom Palette and Colormap Utilities
Main CLI entry point
"""

import sys

def check_dependencies():
    """Check if required packages are installed"""
    missing = []
    
    try:
        import PIL
    except ImportError:
        missing.append("Pillow")
    
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    
    if missing:
        print("ERROR: Missing required dependencies!", file=sys.stderr)
        print("", file=sys.stderr)
        print("Missing packages:", ", ".join(missing), file=sys.stderr)
        print("", file=sys.stderr)
        print("To install, run:", file=sys.stderr)
        print(f"  pip install {' '.join(missing)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or install all dependencies at once:", file=sys.stderr)
        print("  pip install Pillow numpy", file=sys.stderr)
        sys.exit(1)

# Check dependencies before importing
check_dependencies()

from pathlib import Path
from PIL import Image

from doompal import __version__
from doompal.cli import parse_args
from doompal.palette import load_palette, load_all_palettes, expand_palette_to_14, detect_palette_type
from doompal.colormap import generate_colormap, colormap_to_png, colormap_to_binary
from doompal.cube import palette_to_cube
from doompal.wad import WADFile, extract_playpal, extract_colormap
from doompal.utils import COLORS, GRID_SIZE


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
            from doompal.palette import extract_palette_from_binary
            palette = extract_palette_from_binary(data, 0)
        else:
            palette = load_palette(input_path)
        
        print(f"Generating HALD CLUT and converting to .cube...")
        
        # Generate HALD and convert to cube
        from doompal.hald import generate_hald_identity, remap_hald_to_palette
        from doompal.cube import hald_to_cube
        
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
        from doompal.hald import generate_hald_identity, remap_hald_to_palette
        from doompal.cube import hald_to_cube
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
        split_path = Path(f"{output_base}_playpal_split.png")
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
        
        # 5. Generate blank PLAYPAL (all 14 rows same as pal0)
        print("Generating blank PLAYPAL...")
        blank_playpal_path = Path(f"{output_base}_playpal_blank.png")
        img_blank = Image.new("RGB", (COLORS, 14))
        px_blank = img_blank.load()
        for row in range(14):
            for col in range(COLORS):
                px_blank[col, row] = palette[col]  # All rows same as pal0
        img_blank.save(blank_playpal_path)
        outputs["PLAYPAL (blank)"] = blank_playpal_path
        
        # 6. Generate blank colormap (no lighting)
        print("Generating blank colormap...")
        blank_colormap_path = Path(f"{output_base}_colormap_blank.png")
        colormap_blank = generate_colormap(palette, with_lighting=False)
        colormap_to_png(colormap_blank, palette, blank_colormap_path)
        outputs["COLORMAP (blank)"] = blank_colormap_path
        
        print("\nGenerated files:")
        for name, path in outputs.items():
            print(f"  {name}: {path}")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_batch_wad(wad_path, output_base):
    """Special batch processing for WAD files"""
    from doompal.wad import read_wad_lump, find_boom_colormaps
    from doompal.palette import extract_palette_from_binary
    from doompal.hald import generate_hald_identity, remap_hald_to_palette
    from doompal.cube import hald_to_cube
    
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
        split_path = Path(f"{output_base}_playpal_split.png")
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
    
    # Step 11: Generate blank PLAYPAL (all 14 rows same as pal0)
    if palette and all_palettes:
        print("Generating blank PLAYPAL...")
        blank_playpal_path = Path(f"{output_base}_playpal_blank.png")
        img_blank = Image.new("RGB", (COLORS, 14))
        px_blank = img_blank.load()
        for row in range(14):
            for col in range(COLORS):
                px_blank[col, row] = palette[col]  # All rows same as pal0
        img_blank.save(blank_playpal_path)
        outputs["PLAYPAL (blank)"] = blank_playpal_path
    
    # Step 12: Generate blank colormap (no lighting)
    if palette:
        print("Generating blank colormap...")
        blank_colormap_path = Path(f"{output_base}_colormap_blank.png")
        colormap_blank = generate_colormap(palette, with_lighting=False)
        colormap_to_png(colormap_blank, palette, blank_colormap_path)
        outputs["COLORMAP (blank)"] = blank_colormap_path
    
    # Step 13: Extract all Boom colormaps if found
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
        # Default: filename_playpal.png (in current directory, not input's directory)
        ext = ".pal" if args.slade else ".png"
        filename_stem = Path(input_path.name).stem
        output_path = Path(f"{filename_stem}_playpal{ext}")
    
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
    
    # Default output if not provided
    if output_path is None:
        filename_stem = Path(input_path.name).stem
        output_path = Path(f"{filename_stem}_colormap.png")
    
    # Ensure .png extension
    if not str(output_path).endswith('.png'):
        output_path = Path(str(output_path) + '.png')
    
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
    
    # Fix: Default output to input filename (not path) if not provided
    if output_base is None:
        # Use only filename, not full path - outputs go to current directory
        output_base = Path(input_path.name).stem
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
                from doompal.palette import extract_palette_from_binary
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
                    from doompal.palette import extract_palette_from_binary
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
                    from doompal.palette import extract_palette_from_binary
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
        from doompal.palette import expand_palette_to_14
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


def main():
    """Main entry point"""
    args = parse_args()
    
    if not args.mode:
        print("ERROR: No mode specified. Use --help for usage information.", file=sys.stderr)
        return 1
    
    # Dispatch to appropriate command handler
    handlers = {
        "cube": cmd_cube,
        "batch": cmd_batch,
        "playpal": cmd_playpal,
        "colormap": cmd_colormap,
        "colourmap": cmd_colormap,  # Alias
        "blank": cmd_blank,
        "slade": cmd_slade,
        "extract": cmd_extract,
        "split": cmd_split,
    }
    
    handler = handlers.get(args.mode)
    if handler:
        return handler(args)
    else:
        print(f"ERROR: Unknown mode: {args.mode}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
