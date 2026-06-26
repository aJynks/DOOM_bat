#!/usr/bin/env python3
"""
splitFlats - cut a single image into 64x64 tiles, palette-matched with
seamless tile edges.

Fixed pipeline every run:
  1. Build the true-colour canvas: the source is padded up to the next
     multiple of 64 in each dimension and aligned inside it (default:
     centered, -a to change). The padded area is filled by a single
     full-canvas background image (-b) or a repeating 64x64 tile (-bt),
     and the source is composited on top with a hard binary alpha mask
     (opaque source wins, transparent reveals background; no blending/AA).
  2. Quantise the whole canvas to the supplied Doom palette (-pal, required).
  3. Edge-match in palette/index space: the two pixels straddling every
     internal 64 cut are set to one shared palette index, so adjacent tiles
     share identical edges and show no seam in software renderers.
  4. Slice and write paletted (indexed) PNGs using that palette.

A palette (-pal) is REQUIRED on every run. A background (-b or -bt) is
required UNLESS the input is already an exact multiple of 64 in both
dimensions (otherwise the padding would be empty transparency with nothing
to match against). Use -sq to print the required canvas size for an image.

Accepted -pal inputs:
  - raw PLAYPAL lump or .pal file (first palette)
  - JASC .pal text palette
  - WAD file containing a PLAYPAL lump (errors if absent)
  - DoomTools playpal PNG (256 wide; row 0 is the base palette)
  - SLADE pal0.png (16x16 grid of swatches; block centres sampled)
  - a plain 256-pixel image (16x16 at 1px, or a 1px strip)
"""

import os
import struct
import sys
from pathlib import Path

# Dependency check
try:
    from PIL import Image
except ImportError:
    print("Missing dependency. Install with: pip install Pillow")
    sys.exit(1)

TILE = 64
PALETTE_COLORS = 256
PALETTE_BYTES = PALETTE_COLORS * 3

ALIGN_CHOICES = {
    'topleft', 'top', 'topright',
    'left', 'center', 'right',
    'bottomleft', 'bottom', 'bottomright',
}


def die(msg):
    print(f"Error: {msg}")
    sys.exit(1)


HELP_FLAGS = {'-h', '--help', '-help'}


def _supports_color():
    """True if stdout is a terminal that can show ANSI colour. Enables VT
    processing on modern Windows consoles so the escapes render there too."""
    if os.environ.get('NO_COLOR') is not None:
        return False
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    if sys.platform == 'win32':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            handle = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if not k.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            k.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            return False
    return True


def print_help():
    """Print a formatted, optionally coloured help screen with examples."""
    color = _supports_color()

    def s(code, text):
        return f"\033[{code}m{text}\033[0m" if color else text

    title = lambda t: s('1;36', t)      # bold cyan
    sect = lambda t: s('1;4', t)        # bold underline
    flag = lambda t: s('32', t)         # green
    arg = lambda t: s('2', t)           # dim
    cmd = lambda t: s('33', t)          # yellow
    note = lambda t: s('90', t)         # grey
    bar = s('90', '─' * 64)

    def opt(flags, argtxt, desc):
        left = flag(flags) + (' ' + arg(argtxt) if argtxt else '')
        # pad on the visible (un-coloured) length
        visible = flags + (' ' + argtxt if argtxt else '')
        pad = ' ' * max(2, 30 - len(visible))
        return f"  {left}{pad}{desc}"

    lines = [
        bar,
        f"  {title('splitFlats')}  {note('— slice an image into seamless 64x64 Doom flats')}",
        bar,
        "",
        f"  {sect('USAGE')}",
        f"    {cmd('splitflats')} {arg('<image>')} {flag('--palette')} {arg('<pal>')} [options]",
        "",
        f"  {sect('OPTIONS')}",
        opt('-pal, --palette', '<file>', note('REQUIRED.') + ' Doom palette source (see below)'),
        opt('-b,   --background', '<img>', 'Full-canvas background image (size from --sizequery)'),
        opt('-bt,  --backgroundTile', '<img>', '64x64 background tile, repeated behind the cut'),
        opt('-a,   --align', '<pos>', 'Source placement when padded (default: center)'),
        f"  {' ' * 30}{note('topleft top topright  left center right  bottomleft bottom bottomright')}",
        opt('-n,   --name', '<prefix>', 'Sequential tile names: prefix + 001, 002, ...'),
        opt('-d,   --directory', '<name>', 'Output folder name (default: split)'),
        opt('-sq,  --sizequery', '', 'Print the required canvas size and exit'),
        opt('-h,   --help', '', 'Show this help'),
        "",
        f"  {sect('PALETTE INPUTS')} {note('(--palette)')}",
        f"    {note('•')} raw PLAYPAL lump or .pal file   {note('(first palette)')}",
        f"    {note('•')} JASC .pal text palette",
        f"    {note('•')} WAD containing a PLAYPAL lump   {note('(errors if absent)')}",
        f"    {note('•')} DoomTools playpal PNG           {note('(256 wide; row 0 used)')}",
        f"    {note('•')} SLADE pal0.png                  {note('(16x16 swatch grid)')}",
        "",
        f"  {sect('NOTES')}",
        f"    {note('•')} Output tiles are indexed PNGs in Doom palette order.",
        f"    {note('•')} A background is required unless width and height are both",
        f"      exact multiples of 64.",
        f"    {note('•')} Tile edges are matched in palette space so adjacent flats",
        f"      show no seam in software renderers.",
        "",
        f"  {sect('EXAMPLES')}",
        f"    {note('# exact-fit image, just needs a palette')}",
        f"    {cmd('splitflats')} wall.png {flag('--palette')} doom2.wad",
        "",
        f"    {note('# odd-size image: fill the padding with a background, centred')}",
        f"    {cmd('splitflats')} logo.png {flag('--palette')} pal0.png {flag('--background')} bg.png {flag('--align')} center",
        "",
        f"    {note('# name the tiles FLOOR001.. into a chosen folder')}",
        f"    {cmd('splitflats')} art.png {flag('--palette')} playpal.pal {flag('--name')} FLOOR {flag('--directory')} myflats",
        "",
        f"    {note('# tile a 64x64 background behind the cut')}",
        f"    {cmd('splitflats')} art.png {flag('--palette')} playpal.lmp {flag('--backgroundTile')} grid64.png",
        "",
        f"    {note('# just ask what canvas size you need to build')}",
        f"    {cmd('splitflats')} art.png {flag('--sizequery')}",
        bar,
    ]
    print("\n".join(lines))


def parse_arguments(argv):
    """Parse command line arguments into an options dict."""
    if any(a in HELP_FLAGS for a in argv):
        print_help()
        sys.exit(0)

    opts = {
        'input': None,
        'directory': 'split',
        'align': 'center',
        'name': None,           # -n flat sequential basename override
        'bg_tile': None,        # -bt path
        'bg_full': None,        # -b path
        'palette': None,        # -pal path (required)
        'sizequery': False,     # -sq: print required 64-grid size and exit
    }

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]

        if arg in ('-d', '--directory'):
            if i + 1 >= n:
                die(f"{arg} requires a value")
            opts['directory'] = argv[i + 1]
            i += 2

        elif arg in ('-a', '--align'):
            if i + 1 >= n:
                die(f"{arg} requires a value")
            value = argv[i + 1].lower()
            if value not in ALIGN_CHOICES:
                die(f"Invalid align '{argv[i + 1]}'. "
                    f"Choose from: {', '.join(sorted(ALIGN_CHOICES))}")
            opts['align'] = value
            i += 2

        elif arg in ('-n', '--name'):
            if i + 1 >= n:
                die(f"{arg} requires a value")
            opts['name'] = argv[i + 1]
            i += 2

        elif arg in ('-sq', '--sizequery'):
            opts['sizequery'] = True
            i += 1

        elif arg in ('-pal', '--palette'):
            if i + 1 >= n:
                die(f"{arg} requires a value")
            opts['palette'] = argv[i + 1]
            i += 2

        elif arg in ('-bt', '--backgroundTile'):
            if i + 1 >= n:
                die(f"{arg} requires a value")
            opts['bg_tile'] = argv[i + 1]
            i += 2

        elif arg in ('-b', '--background'):
            # Background image is required (use -sq to query the size).
            if i + 1 >= n or argv[i + 1].startswith('-'):
                die("-b requires an image filename (use -sq to query the "
                    "required canvas size)")
            opts['bg_full'] = argv[i + 1]
            i += 2

        elif arg.startswith('-'):
            die(f"Unknown option '{arg}'")

        else:
            if opts['input'] is not None:
                die("Only one input file is supported "
                    f"(already have '{opts['input']}', also got '{arg}')")
            opts['input'] = arg
            i += 1

    return opts


def open_image(path, what):
    """Open and fully load an image, or die with a clear message."""
    try:
        img = Image.open(path)
        img.load()
        return img
    except Exception:
        die(f"Could not open/read {what}: {path}")


def padded_size(iw, ih):
    """Round each dimension up to the next multiple of the tile size."""
    pw = -(-iw // TILE) * TILE
    ph = -(-ih // TILE) * TILE
    return pw, ph


def align_offset(align, pw, ph, iw, ih):
    """Top-left paste offset for the source inside the padded canvas."""
    horiz = {
        'left': 0,
        'center': (pw - iw) // 2,
        'right': pw - iw,
    }
    vert = {
        'top': 0,
        'center': (ph - ih) // 2,
        'bottom': ph - ih,
    }
    h_key = ('left' if align in ('topleft', 'left', 'bottomleft')
             else 'right' if align in ('topright', 'right', 'bottomright')
             else 'center')
    v_key = ('top' if align in ('topleft', 'top', 'topright')
             else 'bottom' if align in ('bottomleft', 'bottom', 'bottomright')
             else 'center')
    return horiz[h_key], vert[v_key]


def build_canvas(pw, ph, bg_tile_img, bg_full_img):
    """Create the background layer the source will be composited over."""
    canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    if bg_tile_img is not None:
        # Canvas is always a whole multiple of TILE -> one clean copy per cell.
        for ty in range(0, ph, TILE):
            for tx in range(0, pw, TILE):
                canvas.paste(bg_tile_img, (tx, ty))
    elif bg_full_img is not None:
        canvas.paste(bg_full_img, (0, 0))
    return canvas


def composite_source(canvas, src, offset):
    """Lay the source over the canvas with a hard binary alpha mask:
    any non-zero alpha is treated as opaque source, the rest reveals
    the background. No blending."""
    alpha = src.getchannel("A")
    mask = alpha.point(lambda a: 255 if a > 0 else 0)
    canvas.paste(src, offset, mask)


def palette_from_raw_playpal(data, source_name):
    """Read the first 256 RGB triplets from a raw PLAYPAL-like byte block."""
    if len(data) < PALETTE_BYTES:
        die(f"Palette file is too small to contain 256 RGB colours: {source_name}")
    first = data[:PALETTE_BYTES]
    return [(first[i], first[i + 1], first[i + 2])
            for i in range(0, PALETTE_BYTES, 3)]


def palette_from_jasc_pal(text, source_name):
    """Read a JASC-PAL text palette."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or lines[0].upper() != 'JASC-PAL':
        return None
    try:
        count = int(lines[2])
    except ValueError:
        die(f"Invalid JASC palette colour count: {source_name}")
    if count < PALETTE_COLORS or len(lines) < 3 + PALETTE_COLORS:
        die(f"JASC palette must contain at least 256 colours: {source_name}")

    pal = []
    for line in lines[3:3 + PALETTE_COLORS]:
        parts = line.split()
        if len(parts) != 3:
            die(f"Invalid JASC palette colour line: {source_name}")
        try:
            rgb = tuple(int(v) for v in parts)
        except ValueError:
            die(f"Invalid JASC palette RGB value: {source_name}")
        if any(v < 0 or v > 255 for v in rgb):
            die(f"JASC palette RGB values must be 0-255: {source_name}")
        pal.append(rgb)
    return pal


def palette_from_wad_playpal(data, source_name):
    """Read the first PLAYPAL palette from an IWAD/PWAD byte block."""
    if len(data) < 12 or data[:4] not in (b'IWAD', b'PWAD'):
        return None
    try:
        num_lumps, dir_offset = struct.unpack_from('<II', data, 4)
    except struct.error:
        die(f"Invalid WAD header: {source_name}")
    if dir_offset < 0 or dir_offset + num_lumps * 16 > len(data):
        die(f"Invalid WAD directory: {source_name}")

    for i in range(num_lumps):
        entry = dir_offset + i * 16
        lump_offset, lump_size = struct.unpack_from('<II', data, entry)
        name_bytes = data[entry + 8:entry + 16]
        lump_name = name_bytes.split(b'\0', 1)[0].decode('ascii', 'ignore').upper()
        if lump_name == 'PLAYPAL':
            if lump_offset + lump_size > len(data):
                die(f"PLAYPAL lump points outside WAD file: {source_name}")
            if lump_size < PALETTE_BYTES:
                die(f"PLAYPAL lump is too small in WAD: {source_name}")
            return palette_from_raw_playpal(
                data[lump_offset:lump_offset + lump_size],
                f"PLAYPAL in {source_name}"
            )
    die(f"No PLAYPAL lump found in WAD: {source_name}")


def palette_from_image(path):
    """Read 256 palette colours from a palette image, in Doom index order.

    Supported layouts (auto-detected by dimensions):
      - DoomTools playpal PNG: 256 wide, row 0 is the base palette (extra rows
        are the tinted PLAYPALs) -> read row 0.
      - A plain 256-pixel image (e.g. 16x16 at 1px, or a 1px strip) -> read
        every pixel in reading order.
      - SLADE pal0.png: a 16x16 grid of equal swatches -> sample each block's
        centre in reading order.
    """
    img = open_image(path, "palette image").convert("RGB")
    w, h = img.size
    px = img.load()

    # DoomTools-style PLAYPAL strip: 256 wide, the first row is the palette.
    if w == 256 and h <= 16:
        return [px[x, 0] for x in range(256)]

    # Plain 256-pixel palette (16x16 @ 1px, 1x256, etc.).
    if w * h == PALETTE_COLORS:
        return [px[x, y] for y in range(h) for x in range(w)]

    # SLADE pal0.png swatch grid: 16x16 blocks, sample the centre of each.
    if w % 16 == 0 and h % 16 == 0:
        bw, bh = w // 16, h // 16
        return [px[c * bw + bw // 2, r * bh + bh // 2]
                for r in range(16) for c in range(16)]

    die(f"Can't read palette image {path} ({w}x{h}). Expected a 256-wide "
        f"PLAYPAL strip (row 0 used), a 256-pixel 1px palette, or a 16x16 "
        f"swatch grid (both dimensions divisible by 16).")


def load_doom_palette(path):
    """Load a 256-colour Doom palette from PNG/PAL/PLAYPAL/WAD input."""
    p = Path(path)
    if not p.is_file():
        die(f"Palette file not found: {p}")

    data = p.read_bytes()

    # WAD container with PLAYPAL lump.
    wad_pal = palette_from_wad_playpal(data, str(p))
    if wad_pal is not None:
        return wad_pal

    # JASC .pal text.
    try:
        text = data.decode('ascii')
    except UnicodeDecodeError:
        text = None
    if text is not None:
        jasc_pal = palette_from_jasc_pal(text, str(p))
        if jasc_pal is not None:
            return jasc_pal

    # Raw PLAYPAL lump or binary .pal.
    suffix = p.suffix.lower()
    if suffix in ('.pal', '.lmp', '.playpal') or len(data) in (768, 10752):
        return palette_from_raw_playpal(data, str(p))

    # Image palette: SLADE pal0.png, DoomTools palette PNG, etc.
    try:
        return palette_from_image(p)
    except Exception as e:
        die(f"Could not read palette as WAD, JASC/raw PLAYPAL, or image: {p} ({e})")


def make_pil_palette_image(palette):
    """Build a tiny P-mode image Pillow can use as a fixed quantize palette."""
    if len(palette) != PALETTE_COLORS:
        die("Internal error: palette must contain exactly 256 colours")
    pal_img = Image.new('P', (1, 1))
    flat = []
    for r, g, b in palette:
        flat.extend([r, g, b])
    pal_img.putpalette(flat)
    return pal_img


def quantize_to_palette(img, palette):
    """Convert an image to indexed colour using the supplied exact palette."""
    pal_img = make_pil_palette_image(palette)
    rgb = img.convert('RGB')
    try:
        dither_none = Image.Dither.NONE
    except AttributeError:
        dither_none = Image.NONE
    indexed = rgb.quantize(palette=pal_img, dither=dither_none)
    indexed.putpalette(pal_img.getpalette())
    return indexed


def nearest_palette_index(rgb, palette, cache):
    """Find the closest palette index to an RGB colour using squared distance."""
    if rgb in cache:
        return cache[rgb]
    r, g, b = rgb
    best_i = 0
    best_d = None
    for i, (pr, pg, pb) in enumerate(palette):
        dr = r - pr
        dg = g - pg
        db = b - pb
        d = dr * dr + dg * dg + db * db
        if best_d is None or d < best_d:
            best_d = d
            best_i = i
            if d == 0:
                break
    cache[rgb] = best_i
    return best_i


def edge_match_indexed_canvas(canvas, palette):
    """Palette-aware edge matching for a P-mode image.

    The canvas is already converted to the final Doom palette. For each seam
    pair, average the two palette RGB colours, find the nearest palette entry,
    and write that same final palette index to both sides of the seam.
    """
    if canvas.mode != 'P':
        die("Internal error: indexed edge matching needs a P-mode image")

    w, h = canvas.size
    px = canvas.load()
    nearest_cache = {}
    pair_cache = {}

    def avg_idx(ai, bi):
        key = (ai, bi) if ai <= bi else (bi, ai)
        if key in pair_cache:
            return pair_cache[key]
        a = palette[ai]
        b = palette[bi]
        avg = ((a[0] + b[0] + 1) // 2,
               (a[1] + b[1] + 1) // 2,
               (a[2] + b[2] + 1) // 2)
        mi = nearest_palette_index(avg, palette, nearest_cache)
        pair_cache[key] = mi
        return mi

    # Internal vertical seams: columns TILE, 2*TILE, ... ; pair (x-1, x)
    for x in range(TILE, w, TILE):
        for y in range(h):
            m = avg_idx(px[x - 1, y], px[x, y])
            px[x - 1, y] = m
            px[x, y] = m

    # Internal horizontal seams: rows TILE, 2*TILE, ... ; pair (y-1, y)
    for y in range(TILE, h, TILE):
        for x in range(w):
            m = avg_idx(px[x, y - 1], px[x, y])
            px[x, y - 1] = m
            px[x, y] = m

    return canvas

def split_canvas(canvas, base_name, output_dir, name_override=None):
    """Cut the canvas into TILE-sized tiles, left->right, top->bottom.

    With name_override set, tiles are named with a flat 3-digit counter
    in cut order (NAME001, NAME002, ...); a '_' is inserted before the
    number when the override is 4 chars or fewer, keeping every name
    within 8 characters. Without it, the default R###-C### scheme is used.
    """
    pw, ph = canvas.size
    tiles_x = pw // TILE
    tiles_y = ph // TILE
    sep = '_' if (name_override is not None and len(name_override) <= 4) else ''
    created = []
    seq = 0
    palette = canvas.getpalette() if canvas.mode == 'P' else None
    for y in range(tiles_y):
        for x in range(tiles_x):
            left = x * TILE
            top = y * TILE
            tile = canvas.crop((left, top, left + TILE, top + TILE))
            if palette is not None:
                tile.putpalette(palette)
            seq += 1
            if name_override is not None:
                name = f"{name_override}{sep}{seq:03d}.png"
            else:
                name = f"{base_name}_R{y + 1:03d}-C{x + 1:03d}.png"
            tile.save(output_dir / name, format="PNG")
            created.append(name)
    return created


def main():
    opts = parse_arguments(sys.argv[1:])

    if opts['input'] is None:
        die("No input file given.")

    input_path = Path(opts['input'])
    if not input_path.is_file():
        die(f"Input file not found: {input_path}")

    src = open_image(input_path, "input image").convert("RGBA")
    iw, ih = src.size
    pw, ph = padded_size(iw, ih)

    # -sq: report the required 64-grid canvas size and stop. Needs nothing else.
    if opts['sizequery']:
        print(f"{pw}x{ph}")
        sys.exit(0)

    if opts['bg_tile'] is not None and opts['bg_full'] is not None:
        die("-bt and -b cannot be used together")

    # A palette is required on every (non-query) run.
    if opts['palette'] is None:
        die("A palette is required: supply -pal <PNG/PAL/PLAYPAL/WAD>.")

    exact_fit = (iw % TILE == 0 and ih % TILE == 0)

    # Edge matching needs real content across every internal cut. If the image
    # doesn't fit the grid exactly it gets padded, so a background is required
    # to fill that padding with something to match against.
    if not exact_fit and opts['bg_tile'] is None and opts['bg_full'] is None:
        die(f"Image ({iw}x{ih}) isn't a multiple of {TILE}, so it would be "
            f"padded with transparency. Supply -b or -bt, or use an image whose "
            f"width and height are both multiples of {TILE} "
            f"(use -sq to print the size -b would need).")

    # -n naming constraints (Doom-legal 8-char lump names)
    if opts['name'] is not None:
        if not (1 <= len(opts['name']) <= 5):
            die("-n name must be 1-5 characters "
                "(5 max, so name + 3-digit number stays within 8)")
        total = (pw // TILE) * (ph // TILE)
        if total > 999:
            die(f"-n uses a 3-digit counter (max 999 tiles); "
                f"this input produces {total}")

    # Load palette.
    palette = load_doom_palette(opts['palette'])

    # Load background layers (with strict size checks).
    bg_tile_img = None
    bg_full_img = None

    if opts['bg_tile'] is not None:
        bt = open_image(opts['bg_tile'], "background tile").convert("RGBA")
        if bt.size != (TILE, TILE):
            die(f"Background tile must be {TILE}x{TILE}, "
                f"got {bt.size[0]}x{bt.size[1]}")
        bg_tile_img = bt

    if opts['bg_full'] is not None:
        bf = open_image(opts['bg_full'], "background image").convert("RGBA")
        if bf.size != (pw, ph):
            die(f"Background image must be {pw}x{ph} for this input, "
                f"got {bf.size[0]}x{bf.size[1]}")
        bg_full_img = bf

    # 1. Build the true-colour canvas, composite the source on top.
    canvas = build_canvas(pw, ph, bg_tile_img, bg_full_img)
    offset = align_offset(opts['align'], pw, ph, iw, ih)
    composite_source(canvas, src, offset)

    # 2. Quantise the whole canvas to the final Doom palette, then
    # 3. edge-match in palette/index space so seam pixels are matched as final
    #    palette indices.
    canvas = quantize_to_palette(canvas, palette)
    edge_match_indexed_canvas(canvas, palette)

    # 4. Slice and write paletted tiles.
    output_dir = input_path.parent / opts['directory']
    output_dir.mkdir(exist_ok=True)
    created = split_canvas(canvas, input_path.stem, output_dir, opts['name'])

    # Report
    if bg_tile_img is not None:
        bg_desc = f"tile ({opts['bg_tile']})"
    elif bg_full_img is not None:
        bg_desc = f"image ({opts['bg_full']})"
    else:
        bg_desc = "none (exact fit)"

    print(f"Input:      {input_path.name} ({iw}x{ih})")
    print(f"Canvas:     {pw}x{ph}  (align: {opts['align']})")
    print(f"Background: {bg_desc}")
    print(f"Palette:    {opts['palette']}")
    print(f"Output dir: {output_dir}")
    print(f"Tiles:      {len(created)}")
    for name in created:
        print(f"  {name}")


if __name__ == "__main__":
    main()
