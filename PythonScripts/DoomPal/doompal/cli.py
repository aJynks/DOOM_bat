"""Command-line interface and argument parsing"""

import argparse
import sys
from pathlib import Path
from . import __version__


def create_parser():
    """Create the argument parser for doompal CLI"""
    
    parser = argparse.ArgumentParser(
        prog="doompal",
        description="Doom palette and colormap manipulation tool",
        epilog="For more information, visit: https://github.com/yourusername/doompal",
        add_help=False  # We'll add custom help
    )
    
    # Add custom help flags
    parser.add_argument(
        "-h", "--help", "-help",
        action="store_true",
        dest="show_help",
        help="Show this help message"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    
    # Create subparsers for different modes
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")
    
    # Mode 1: Generate .cube from palette
    cube_parser = subparsers.add_parser(
        "cube",
        aliases=["-cube"],
        help="Generate .cube LUT from palette"
    )
    cube_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file (.pal, .png, .wad)"
    )
    cube_parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output .cube file (default: input_name.cube)"
    )
    
    # Mode 2: Batch generation (all outputs)
    batch_parser = subparsers.add_parser(
        "batch",
        help="Generate all outputs (playpal, colormap, blanks)"
    )
    batch_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file"
    )
    batch_parser.add_argument(
        "output",
        type=Path,
        help="Output base name (generates multiple files)"
    )
    batch_parser.add_argument(
        "-slade",
        action="store_true",
        help="Generate SLADE-compatible .pal and .cmp binaries instead of PNGs"
    )
    
    # Mode 3: Generate PLAYPAL
    playpal_parser = subparsers.add_parser(
        "playpal",
        aliases=["-playpal"],
        help="Generate 256×14 PLAYPAL PNG"
    )
    playpal_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file"
    )
    playpal_parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output PNG file (default: input_name_playpal.png)"
    )
    playpal_parser.add_argument(
        "-slade", "--slade",
        action="store_true",
        help="Generate SLADE-compatible playpal.pal binary instead of PNG"
    )
    playpal_parser.add_argument(
        "--blank", "-blank",
        action="store_true",
        help="Generate blank PLAYPAL (all 14 rows same as pal0, no tinting)"
    )
    
    # Mode 4: Generate COLORMAP (with aliases)
    colormap_parser = subparsers.add_parser(
        "colormap",
        aliases=["-colormap", "-colourmap", "colourmap"],
        help="Generate 256×34 colormap PNG with lighting"
    )
    colormap_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file"
    )
    colormap_parser.add_argument(
        "output",
        type=Path,
        nargs='?',
        default=None,
        help="Output PNG file (default: input_name_colormap.png)"
    )
    colormap_parser.add_argument(
        "--blank", "-blank",
        action="store_true",
        help="Generate blank colormap (no lighting, rows 0-31 same, preserve rows 32-33)"
    )
    
    # Mode 5: Generate blank files (playpal + colormap)
    blank_parser = subparsers.add_parser(
        "blank",
        help="Generate blank PLAYPAL and COLORMAP (no tints, no lighting)"
    )
    blank_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file"
    )
    blank_parser.add_argument(
        "output",
        type=Path,
        help="Output base name (generates _playpal.png and _colormap.png)"
    )
    
    # Mode 6: SLADE grid conversion
    slade_parser = subparsers.add_parser(
        "slade",
        aliases=["-slade"],
        help="Generate SLADE-style 16×16 grid palette"
    )
    slade_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file"
    )
    slade_parser.add_argument(
        "output",
        type=Path,
        nargs='?',
        default=None,
        help="Output base name (default: use input filename)"
    )
    slade_parser.add_argument(
        "--playpal", "-playpal",
        action="store_true",
        help="Output binary playpal.pal file (14 palettes) instead of PNG grid"
    )
    slade_parser.add_argument(
        "--cell", "-cell",
        type=int,
        default=8,
        help="Cell size in pixels (default: 8, creates 128×128 output)"
    )
    
    # Mode 6: Extract from WAD
    extract_parser = subparsers.add_parser(
        "extract",
        aliases=["-extract"],
        help="Extract PLAYPAL and COLORMAP from WAD"
    )
    extract_parser.add_argument(
        "wad",
        type=Path,
        help="Input WAD file"
    )
    extract_parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output base name (default: wad_name)"
    )
    extract_parser.add_argument(
        "-boom",
        nargs="?",
        const="__all__",  # Special marker for "extract all"
        metavar="LUMPNAME",
        help="Extract Boom colormaps (optionally specify lump name)"
    )
    extract_parser.add_argument(
        "-boomlist",
        action="store_true",
        help="List Boom colormap lumps without extracting"
    )
    
    # Mode 7: Split palettes into transparent overlay
    split_parser = subparsers.add_parser(
        "split",
        aliases=["-split", "--split"],
        help="Extract tint overlay from PLAYPAL (transparent PNG)"
    )
    split_parser.add_argument(
        "input",
        type=Path,
        help="Input palette file (any format)"
    )
    split_parser.add_argument(
        "output",
        type=Path,
        help="Output transparent overlay PNG"
    )
    
    return parser


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




def parse_args(args=None):
    """
    Parse command-line arguments.
    
    Args:
        args: List of arguments (default: sys.argv[1:])
        
    Returns:
        Namespace object with parsed arguments
    """
    parser = create_parser()
    
    # Handle legacy positional syntax (for backward compatibility)
    # doompal input output → batch mode
    if args is None:
        args = sys.argv[1:]
    
    # Check for help flags first
    if any(arg in ["-h", "--help", "-help"] for arg in args):
        print_compact_help()
        sys.exit(0)
    
    # If first arg doesn't start with - and isn't a known mode, assume batch (default)
    if len(args) >= 1 and not args[0].startswith("-"):
        known_modes = {
            "cube", "-cube",
            "batch",
            "playpal", "-playpal",
            "colormap", "-colormap", "-colourmap", "colourmap",
            "blank",
            "slade", "-slade",
            "extract", "-extract",
            "split", "-split", "--split"
        }
        if args[0] not in known_modes:
            # Default mode: batch (auto-batch when just inputfile is provided)
            # Add default output name based on input filename
            if len(args) == 1:
                # Just input file, derive output name
                from pathlib import Path
                input_path = Path(args[0])
                output_base = input_path.stem
                args = ["batch", args[0], output_base]
            else:
                # Input and output provided
                args = ["batch"] + args
    
    parsed = parser.parse_args(args)
    
    # Handle mode aliases (remove leading dash)
    if parsed.mode and parsed.mode.startswith("-"):
        parsed.mode = parsed.mode[1:]
    
    return parsed
