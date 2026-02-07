# QUICK START GUIDE

## Installation

```bash
cd doompal
pip install -r requirements.txt --break-system-packages
```

## Basic Usage

```bash
# Test that it works
python3 doompal.py --help

# Generate a .cube file from your PLAYPAL
python3 doompal.py cube yourpalette.pal

# Extract from a WAD
python3 doompal.py extract DOOM.WAD

# Generate colormap
python3 doompal.py colormap yourpalette.pal output.png
```

## Building Standalone Executable

```bash
# Install PyInstaller
pip install pyinstaller --break-system-packages

# Build
pyinstaller doompal.spec

# Your executable will be in dist/doompal (or dist/doompal.exe on Windows)
```

## Next Steps

1. **Test with your existing scripts**: Your playpal scripts should still work
2. **Add HALD generation**: The HALD generation is implemented but may need refinement
3. **Add dcolors.c algorithm**: When you get the source, we can add authentic palette generation
4. **Test WAD extraction**: Make sure it works with your custom WADs

## File Structure

```
doompal/
├── doompal.py              # Main CLI entry point
├── doompal/                # Core modules
│   ├── palette.py         # Your extraction logic
│   ├── colormap.py        # Your colormap generation
│   ├── hald.py            # HALD CLUT generation
│   ├── cube.py            # .cube conversion
│   ├── wad.py             # WAD reading
│   ├── cli.py             # Argument parsing
│   └── utils.py           # Shared utilities
├── requirements.txt        # Dependencies
├── doompal.spec           # PyInstaller config
└── README.md              # Full documentation
```

## Known Limitations

1. **Single palette expansion**: Currently just duplicates pal0 to 14 rows
   - This creates a "blank" PLAYPAL suitable for custom work
   - We can add the Carmack algorithm later

2. **HALD generation**: Implemented but not tested with real color grading workflows

3. **No GUI**: Command-line only (as requested)

## Reporting Issues

If you find bugs or have suggestions, please let me know!
