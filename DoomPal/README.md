# doompal

A cross-platform CLI tool for Doom palette and colormap manipulation.

## Features

- **HALD CLUT to .cube conversion** - Generate color grading LUTs from Doom palettes
- **Palette extraction** - Extract PLAYPAL and COLORMAP from WAD files
- **Colormap generation** - Create standard or blank colormaps with customizable lighting
- **Format conversion** - Convert between multiple palette formats (.pal, .png, .wad)
- **SLADE compatibility** - Export palettes in SLADE-compatible formats

## Supported Input Formats

- `.wad` - Doom WAD files (extracts PLAYPAL lump)
- `.pal` - Raw palette binary (768 bytes for single palette, 10752 for all 14)
- `.png` - Various palette PNG formats:
  - 256×1 (single row strip)
  - 256×14 (DoomTools style)
  - 16×16 grid (SLADE style)

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/doompal.git
cd doompal

# Install dependencies
pip install -r requirements.txt --break-system-packages

# Run directly
python doompal.py --help
```

### Building Standalone Executables

```bash
# Install PyInstaller
pip install pyinstaller --break-system-packages

# Build for your platform
pyinstaller doompal.spec

# Executable will be in dist/doompal (or dist/doompal.exe on Windows)
```

## Usage

### Generate .cube LUT from palette

```bash
# Auto-names output as input.cube
doompal -cube palette.pal

# Specify output name
doompal -cube palette.pal mycube.cube

# Works with any palette format
doompal -cube DOOM.WAD
doompal -cube pal0.png
```

### Batch generation (all outputs)

```bash
# Generates:
#   output_playpal.png (256×14)
#   output_colormap.png (256×34 with lighting)
#   output_playpal_blank.png (pal0 repeated)
#   output_colormap_blank.png (no lighting)
doompal input.pal output
```

### Individual operations

```bash
# Generate PLAYPAL strip (256×14)
doompal -playpal input.pal output.png

# Generate colormap with lighting
doompal -colormap input.pal output.png
# Also accepts -colourmap

# Generate SLADE grid palette
doompal -slade input.pal output        # Just pal0
doompal -slade input.pal output -all   # All 14 palettes
```

### Extract from WAD

```bash
# Extract everything (PLAYPAL + COLORMAP + Boom colormaps)
doompal -extract DOOM.WAD output

# Outputs:
#   output_playpal.pal (Slade format)
#   output_playpal.png (256×14 visualization)
#   output_colormap.cmp (Slade format)
#   output_colormap.png (256×34 visualization)
#   output_LUMPNAME.cmp + .png (for each Boom colormap)

# Extract only Boom colormaps
doompal -extract DOOM.WAD output -boom

# Extract specific Boom colormap
doompal -extract DOOM.WAD output -boom WATERMAP

# List Boom colormaps without extracting
doompal -extract DOOM.WAD -boomlist
```

## Credits

- **PNG to .cube conversion** adapted from [png2cube by picturefx](https://picturefx.itch.io/png2cube-converter-for-linux-and-windows)
- **HALD CLUT generation** based on ImageMagick's HALD implementation
- Doom palette utilities inspired by the Doom modding community

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.
