#!/usr/bin/env python3
"""
rendertex.py — render multi-patch Doom textures to PNG

Reads texture definitions (WAD, SLADE WallTexture text, DoomTools text),
composites each multi-patch texture from its patches, and writes RGBA PNGs.
"""

# ─────────────────────────────────────────────────────────────────────────────
# IWAD PATHS — edit these if your IWAD locations change
# ─────────────────────────────────────────────────────────────────────────────
IWAD_ALIASES = {
    "doom":     r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom.wad",
    "doom2":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad",
    "tnt":      r"D:\Projects\DoomProjects\_SourcePorts\_iwads\tnt.wad",
    "plutonia": r"D:\Projects\DoomProjects\_SourcePorts\_iwads\plutonia.wad",
    "heretic":  r"D:\Projects\DoomProjects\_SourcePorts\_iwads\heretic.wad",
    "hexen":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\hexen.wad",
    "free1":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom1.wad",
    "free2":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom2.wad",
}
IWAD_DEFAULT = "doom2"
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
import struct
import fnmatch
import re
from pathlib import Path

# ── dependency check ──────────────────────────────────────────────────────────
try:
    from PIL import Image
except ImportError:
    print("Missing dependency: Pillow")
    print("Install with:  pip install Pillow")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
# ANSI colour helpers
# ══════════════════════════════════════════════════════════════════════════════

def _enable_vt():
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass

USE_COLOUR = sys.stdout.isatty()
if USE_COLOUR:
    _enable_vt()

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if USE_COLOUR else text

def BOLD(t):    return _c("1",     t)
def DIM(t):     return _c("2",     t)
def RED(t):     return _c("91",    t)
def YELLOW(t):  return _c("93",    t)
def GREEN(t):   return _c("92",    t)
def CYAN(t):    return _c("96",    t)
def MAGENTA(t): return _c("95",    t)
def WHITE(t):   return _c("97",    t)

# ══════════════════════════════════════════════════════════════════════════════
# HELP
# ══════════════════════════════════════════════════════════════════════════════

HELP = """\
{title}

{desc}

{usage_hdr}
  rendertex {def1} [{def2} ...] [{patches} ...] [{iwad}] [{pal}] [{tex}]

{inputs_hdr}
  {def_arg:<22} One or more texture definition files.
                       Accepted formats (auto-detected):
                         {fmt_wad}    WAD containing TEXTURE1/TEXTURE2 + PNAMES
                         {fmt_slade}  SLADE WallTexture text export
                         {fmt_dt}  DoomTools / DEUTEX text definition

{options_hdr}
  {patches_f:<22} Patch source(s): WAD files, directories (recursive),
                       or IWAD aliases — any mix, space separated.
                       Lookup order: directories first (CLI order), then
                       WADs (CLI order), then input WAD, then -iwad.
                       First match found is used.
                       Omit entirely to use just the input WAD + -iwad.

  {iwad_f:<22} Base IWAD for secondary patch lookup and palette fallback.
                       Accepts an alias {aliases} or a path.
                       Default: {default_iwad}

  {pal_f:<22} Explicit palette file (overrides -iwad palette).
                       Accepts: WAD with PLAYPAL, raw .pal, JASC .pal,
                         DoomTools 256-wide PNG, SLADE pal0 grid.

  {tex_f:<22} Render only the listed texture name(s). Accepts globs.
                       e.g.  -tex BIGDOOR1 BIGDOOR2
                             -tex SW1* SW2*
                             -tex *DOOR*

  {clean_f:<22} Also write three DoomTools definition files into each
                       output dir (bare — no comments, ready to paste):
                         {cl1}   full definition minus rendered textures
                         {cl2}   only the rendered textures (original defs)
                         {cl3}  rendered textures as new single-patch entries
                       AASTINKY/AASHITTY are excluded from all three unless {stinky_f}
                       is given, which pins them first in each file instead.
                       {stinky_f} is ignored without {clean_f2}.

  {verbose_f:<22} List every rendered texture, grouped by the patch
                       source(s) that supplied its patches, plus a
                       Not Found group for missing-patch skips.

  {help_f:<22} Show this help.

{output_hdr}
  One output directory per input definition file, named {underscore}stem{close}:
    doom2.wad        →  {ex_wad1}  and  {ex_wad2}
    TEXTURES.txt     →  {ex_txt1}
    floorWall.txt    →  {ex_txt2}

  Only multi-patch textures are rendered.
  Output PNGs are RGBA — residual transparency is preserved.
  Filenames are uppercase: {ex_png}

{palette_hdr}
  1. PLAYPAL from the input definition WAD (if WAD input)
  2. PLAYPAL from a {patches_f2} WAD (first found, CLI order)
  3. {pal_f2} explicit file
  4. PLAYPAL from {iwad_f2}
  5. Error — names the specific patch that needs decoding

{examples_hdr}
  {c1}
    rendertex doom2.wad -patches patches/ -iwad doom2

  {c2}
    rendertex myTextures.txt -patches texwad.wad

  {c3}
    rendertex doom2.wad -patches patches/ -tex BIGDOOR* SW1*

  {c4}
    rendertex base.txt extra.txt -patches tnt d:\\patchdir btw.wad -iwad doom2

  {c5}
    rendertex myDefs.txt -patches texwad.wad -pal mypal.pal

  {c6}
    rendertex texture1.txt -iwad doom2
""".format(
    title   = BOLD(WHITE("rendertex")) + "  —  Doom multi-patch texture renderer",
    desc    = DIM("Composites multi-patch textures from a definition file and writes RGBA PNGs."),
    usage_hdr   = BOLD(CYAN("USAGE")),
    inputs_hdr  = BOLD(CYAN("INPUTS")),
    options_hdr = BOLD(CYAN("OPTIONS")),
    output_hdr  = BOLD(CYAN("OUTPUT")),
    palette_hdr = BOLD(CYAN("PALETTE RESOLUTION ORDER")),
    examples_hdr= BOLD(CYAN("EXAMPLES")),

    def1    = YELLOW("<deffile>"),
    def2    = YELLOW("deffile2"),
    patches = GREEN("-patches") + " " + YELLOW("<src>"),
    iwad    = GREEN("-iwad") + " " + YELLOW("<alias|path>"),
    pal     = GREEN("-pal") + " " + YELLOW("<palfile>"),
    tex     = GREEN("-tex") + " " + YELLOW("<name|glob> ..."),

    def_arg     = YELLOW("<deffile> ..."),
    fmt_wad     = MAGENTA("WAD"),
    fmt_slade   = MAGENTA("SLADE"),
    fmt_dt      = MAGENTA("DoomTools"),

    patches_f   = GREEN("-patches") + " " + YELLOW("<src>"),
    iwad_f      = GREEN("-iwad") + " " + YELLOW("<alias|path>"),
    iwad_f2     = GREEN("-iwad"),
    pal_f       = GREEN("-pal") + " " + YELLOW("<palfile>"),
    pal_f2      = GREEN("-pal"),
    patches_f2  = GREEN("-patches"),
    tex_f       = GREEN("-tex") + " " + YELLOW("<name> ..."),
    help_f      = GREEN("-h") + " / " + GREEN("-help"),
    verbose_f   = GREEN("-verbose") + " / " + GREEN("-v"),
    clean_f     = GREEN("-clean"),
    clean_f2    = GREEN("-clean"),
    stinky_f    = GREEN("+stinky"),
    cl1         = CYAN("_cleaned_*.txt"),
    cl2         = CYAN("_removed_*.txt"),
    cl3         = CYAN("_rendered_*.txt"),
    aliases     = DIM("(" + " | ".join(IWAD_ALIASES.keys()) + ")"),
    default_iwad= MAGENTA(IWAD_DEFAULT),
    underscore  = CYAN("_"),
    close       = "",

    ex_wad1 = CYAN("_texture1/"),
    ex_wad2 = CYAN("_texture2/"),
    ex_txt1 = CYAN("_TEXTURES/"),
    ex_txt2 = CYAN("_floorWall/"),
    ex_png  = CYAN("BIGDOOR1.png"),

    c1 = DIM("# Render all multi-patch textures from doom2.wad using a patch dir"),
    c2 = DIM("# Render from a SLADE text export, patches from a WAD"),
    c3 = DIM("# Only render door and switch textures"),
    c4 = DIM("# Multiple defs; patch chain = d:\\patchdir -> tnt.wad -> btw.wad -> doom2 iwad"),
    c5 = DIM("# Explicit palette file"),
    c6 = DIM("# No -patches at all: everything resolves from the doom2 IWAD"),
)

# ══════════════════════════════════════════════════════════════════════════════
# WAD READER
# ══════════════════════════════════════════════════════════════════════════════

class WadFile:
    """Minimal WAD reader — no external deps."""

    def __init__(self, path):
        self.path = Path(path)
        data = self.path.read_bytes()
        magic = data[:4]
        if magic not in (b'IWAD', b'PWAD'):
            raise ValueError(f"Not a WAD file: {path}")
        num_lumps, dir_offset = struct.unpack_from('<II', data, 4)
        self._lumps = {}   # name (upper) → bytes
        self._lump_order = []
        for i in range(num_lumps):
            off = dir_offset + i * 16
            lump_offset, lump_size = struct.unpack_from('<II', data, off)
            raw_name = data[off+8:off+16].rstrip(b'\x00')
            name = raw_name.decode('ascii', errors='replace').upper()
            lump_data = data[lump_offset:lump_offset+lump_size]
            # Keep first occurrence (standard Doom behaviour)
            if name not in self._lumps:
                self._lumps[name] = lump_data
            self._lump_order.append(name)

    def has(self, name):
        return name.upper() in self._lumps

    def get(self, name):
        return self._lumps.get(name.upper())

    def get_patch_namespace(self):
        """Return all lumps between P_START/P_END or PP_START/PP_END markers."""
        patches = {}
        in_ns = False
        for name in self._lump_order:
            if name in ('P_START', 'PP_START', 'P1_START', 'P2_START', 'P3_START'):
                in_ns = True
                continue
            if name in ('P_END', 'PP_END', 'P1_END', 'P2_END', 'P3_END'):
                in_ns = False
                continue
            if in_ns:
                patches[name.upper()] = self._lumps[name]
        return patches

    def is_iwad(self):
        data = self.path.read_bytes()
        return data[:4] == b'IWAD'


# ══════════════════════════════════════════════════════════════════════════════
# PALETTE LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_palette_from_playpal(data):
    """Return list of 256 (R,G,B) from raw PLAYPAL lump data (first palette)."""
    if len(data) < 768:
        raise ValueError("PLAYPAL lump too short")
    return [(data[i*3], data[i*3+1], data[i*3+2]) for i in range(256)]

def load_palette(source, label="palette"):
    """
    Load a 256-colour palette from various sources.
    source: WadFile, or path to .pal / .png file
    Returns list of 256 (R,G,B) tuples.
    """
    if isinstance(source, WadFile):
        raw = source.get('PLAYPAL')
        if raw is None:
            raise ValueError(f"No PLAYPAL lump in {source.path}")
        return load_palette_from_playpal(raw)

    path = Path(source)
    ext = path.suffix.lower()
    data = path.read_bytes()

    # Raw binary .pal (768 bytes or multiple of 768)
    if ext == '.pal':
        # JASC PAL?
        text = data[:20].decode('ascii', errors='replace')
        if text.startswith('JASC-PAL'):
            lines = data.decode('ascii', errors='replace').splitlines()
            colours = []
            for line in lines[3:]:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) == 3:
                        colours.append(tuple(int(p) for p in parts))
            if len(colours) != 256:
                raise ValueError(f"JASC PAL must have 256 entries, got {len(colours)}")
            return colours
        # Raw binary
        if len(data) % 768 != 0:
            raise ValueError(f"Raw .pal file size must be multiple of 768")
        return load_palette_from_playpal(data[:768])

    if ext == '.png':
        img = Image.open(path).convert('RGBA')
        w, h = img.size
        # DoomTools playpal PNG: 256 wide, row 0 = base palette
        if w == 256:
            pal = []
            for x in range(256):
                r, g, b, a = img.getpixel((x, 0))
                pal.append((r, g, b))
            return pal
        # SLADE pal0 grid: 128x128, 8x8 cells of 16x16
        if w == 128 and h == 128:
            pal = []
            cell = 16
            for row in range(16):
                for col in range(16):
                    cx = col * cell + cell // 2
                    cy = row * cell + cell // 2
                    r, g, b, a = img.getpixel((cx, cy))
                    pal.append((r, g, b))
            return pal
        raise ValueError(f"Unrecognised palette PNG size {w}x{h}")

    if ext in ('.wad',):
        wad = WadFile(path)
        return load_palette(wad, label)

    raise ValueError(f"Unrecognised palette file type: {path}")


# ══════════════════════════════════════════════════════════════════════════════
# DOOM PICTURE FORMAT DECODER
# ══════════════════════════════════════════════════════════════════════════════

def decode_doom_picture(data, palette):
    """
    Decode a Doom column-format graphic lump to RGBA Image.
    Transparent pixels (column gaps) become (0,0,0,0).
    """
    if len(data) < 8:
        raise ValueError("Lump too short to be a Doom picture")
    width, height, left, top = struct.unpack_from('<HHhh', data, 0)
    if width == 0 or height == 0 or width > 4096 or height > 4096:
        raise ValueError(f"Implausible picture dimensions {width}x{height}")

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    pixels = img.load()

    col_ptrs = struct.unpack_from(f'<{width}I', data, 8)

    for x, ptr in enumerate(col_ptrs):
        while ptr < len(data):
            topdelta = data[ptr]; ptr += 1
            if topdelta == 0xFF:
                break
            count = data[ptr]; ptr += 1
            ptr += 1  # unused padding byte
            for i in range(count):
                if ptr >= len(data):
                    break
                idx = data[ptr]; ptr += 1
                y = topdelta + i
                if 0 <= y < height:
                    r, g, b = palette[idx]
                    pixels[x, y] = (r, g, b, 255)
            ptr += 1  # unused padding byte

    return img


# ══════════════════════════════════════════════════════════════════════════════
# PATCH SOURCE
# ══════════════════════════════════════════════════════════════════════════════

class PatchSource:
    """
    Wraps either a WAD file or a recursive directory for patch lookup.
    First-found-first-used. Case-insensitive name matching.
    """

    def __init__(self, src_path):
        self.path = Path(src_path)
        self._is_wad = False
        self._wad = None
        self._wad_patches = {}   # upper name → bytes
        self._dir_index = {}     # upper stem → Path

        if not self.path.exists():
            raise FileNotFoundError(f"Patch source not found: {src_path}")

        if self.path.is_file():
            self._wad = WadFile(self.path)
            self._is_wad = True
            self._wad_patches = self._wad.get_patch_namespace()
            # If no namespace markers, fall back to ALL lumps with data
            if not self._wad_patches:
                self._wad_patches = {
                    k: v for k, v in self._wad._lumps.items()
                    if v and k not in ('PLAYPAL','COLORMAP','TEXTURE1','TEXTURE2',
                                       'PNAMES','ENDOOM','DMXGUS','GENMIDI',
                                       'DEHACKED','MAPINFO')
                }
        else:
            # Directory — build stem index
            IMAGE_EXTS = {'.png', '.bmp', '.tga', '.gif', '.ppm', '.jpg', '.jpeg'}
            for p in self.path.rglob('*'):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                    stem = p.stem.upper()
                    if stem not in self._dir_index:
                        self._dir_index[stem] = p
                    elif p.suffix.lower() == '.png':
                        # Prefer PNG over other formats on collision
                        self._dir_index[stem] = p

    def get_raw(self, name):
        """Return raw bytes for named patch, or None if not found."""
        upper = name.upper()
        if self._is_wad:
            return self._wad_patches.get(upper)
        else:
            p = self._dir_index.get(upper)
            return p.read_bytes() if p else None

    def get_image(self, name, palette):
        """
        Return RGBA PIL Image for named patch.
        palette is a list of 256 (R,G,B) tuples — required if the patch
        is in Doom picture format (WAD source). Can be None for dir sources
        since PNGs are already decoded.
        Returns None if patch not found.
        """
        raw = self.get_raw(name)
        if raw is None:
            return None

        if self._is_wad:
            if palette is None:
                raise RuntimeError(
                    f"Palette required to decode patch '{name}' from WAD "
                    f"'{self.path.name}' but none is available.\n"
                    f"  Supply -iwad or -pal to provide a PLAYPAL."
                )
            return decode_doom_picture(raw, palette)
        else:
            # Directory source — load image file directly
            from io import BytesIO
            return Image.open(BytesIO(raw)).convert('RGBA')

    @property
    def label(self):
        return str(self.path)


# ══════════════════════════════════════════════════════════════════════════════
# TEXTURE DEFINITION PARSERS
# ══════════════════════════════════════════════════════════════════════════════

class TextureDef:
    __slots__ = ('name', 'width', 'height', 'patches')

    def __init__(self, name, width, height, patches):
        self.name = name
        self.width = width
        self.height = height
        # patches: list of (patch_name, originx, originy)
        self.patches = patches


# ── Binary WAD parser ─────────────────────────────────────────────────────────

def _parse_binary_texturex(lump_data, pnames_data):
    """Parse a binary TEXTUREx lump. Returns list of TextureDef."""
    if len(pnames_data) < 4:
        raise ValueError("PNAMES lump too short")
    num_pnames = struct.unpack_from('<I', pnames_data, 0)[0]
    pnames = []
    for i in range(num_pnames):
        off = 4 + i * 8
        raw = pnames_data[off:off+8].rstrip(b'\x00')
        pnames.append(raw.decode('ascii', errors='replace').upper())

    num_tex = struct.unpack_from('<I', lump_data, 0)[0]
    offsets = struct.unpack_from(f'<{num_tex}I', lump_data, 4)
    textures = []

    for i in range(num_tex):
        off = offsets[i]
        name    = lump_data[off:off+8].rstrip(b'\x00').decode('ascii', errors='replace').upper()
        width   = struct.unpack_from('<H', lump_data, off+12)[0]
        height  = struct.unpack_from('<H', lump_data, off+14)[0]
        pcount  = struct.unpack_from('<H', lump_data, off+20)[0]
        patches = []
        for j in range(pcount):
            poff = off + 22 + j * 10
            ox, oy, pidx = struct.unpack_from('<hhH', lump_data, poff)
            if pidx < len(pnames):
                patches.append((pnames[pidx], ox, oy))
            else:
                patches.append((f'PATCH_{pidx}', ox, oy))
        textures.append(TextureDef(name, width, height, patches))

    return textures


def parse_wad(wad):
    """Extract all texture definitions from a WAD. Returns dict lump_name → [TextureDef]."""
    pnames_data = wad.get('PNAMES')
    if pnames_data is None:
        raise ValueError(f"No PNAMES lump in {wad.path.name}")

    result = {}
    for lump in ('TEXTURE1', 'TEXTURE2'):
        data = wad.get(lump)
        if data:
            result[lump] = _parse_binary_texturex(data, pnames_data)
    return result


# ── SLADE WallTexture text parser ────────────────────────────────────────────

def parse_slade_text(text):
    """
    Parse SLADE-format texture definition text.
    Returns dict {'TEXTURES': [TextureDef]}.
    Handles WallTexture only; Texture/Flat blocks are skipped.
    """
    textures = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Skip comments and blank lines
        if not line or line.startswith('//'):
            i += 1
            continue

        m = re.match(
            r'^WallTexture\s+"([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)',
            line, re.IGNORECASE
        )
        if m:
            tex_name = m.group(1).upper()
            width    = int(m.group(2))
            height   = int(m.group(3))
            patches  = []

            # Advance to opening brace
            i += 1
            while i < len(lines) and '{' not in lines[i]:
                i += 1
            i += 1  # skip '{'

            # Read until closing brace
            while i < len(lines):
                inner = lines[i].strip()
                if inner.startswith('}'):
                    break
                pm = re.match(
                    r'^Patch\s+"([^"]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)',
                    inner, re.IGNORECASE
                )
                if pm:
                    patches.append((pm.group(1).upper(),
                                    int(pm.group(2)),
                                    int(pm.group(3))))
                i += 1
            textures.append(TextureDef(tex_name, width, height, patches))
        else:
            # Skip Texture/Flat blocks and anything else
            if re.match(r'^(Texture|Flat)\s+"', line, re.IGNORECASE):
                # Skip to matching brace
                while i < len(lines) and '{' not in lines[i]:
                    i += 1
                depth = 0
                while i < len(lines):
                    if '{' in lines[i]: depth += 1
                    if '}' in lines[i]: depth -= 1
                    i += 1
                    if depth <= 0:
                        break
                continue
        i += 1

    return {'TEXTURES': textures}


# ── DoomTools / DEUTEX text parser ───────────────────────────────────────────

def parse_doomtools_text(text):
    """
    Parse DoomTools/DEUTEX texture definition text.
    Format:
        ; comment
        NAME W H
        * PATCH X Y
        (blank line between textures)
    Returns dict {'TEXTURES': [TextureDef]}.
    """
    textures = []
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(';'):
            if current:
                textures.append(current)
                current = None
            continue

        if line.startswith('*'):
            # Patch line: * PATCHNAME X Y  (tab or space separated)
            parts = line[1:].split()
            if len(parts) >= 3 and current:
                current.patches.append((parts[0].upper(),
                                        int(parts[1]),
                                        int(parts[2])))
        else:
            # Texture header: NAME W H
            if current:
                textures.append(current)
            parts = line.split()
            if len(parts) >= 3:
                try:
                    w = int(parts[1])
                    h = int(parts[2])
                    current = TextureDef(parts[0].upper(), w, h, [])
                except ValueError:
                    current = None
            else:
                current = None

    if current:
        textures.append(current)

    return {'TEXTURES': textures}


# ── Auto-detect and parse a definition file ───────────────────────────────────

def _is_binary_texturex(data):
    """Heuristic: first 4 bytes are a plausible texture count for a binary lump."""
    if len(data) < 8:
        return False
    # Check for IWAD/PWAD magic first
    if data[:4] in (b'IWAD', b'PWAD'):
        return False
    try:
        num = struct.unpack_from('<I', data, 0)[0]
        if num == 0 or num > 10000:
            return False
        # First offset should point somewhere sane
        first_off = struct.unpack_from('<I', data, 4)[0]
        return 4 + num * 4 <= first_off <= len(data)
    except Exception:
        return False


def detect_and_parse(path):
    """
    Auto-detect format and parse.
    Returns (source_label, dict_of_lump_to_texlist, wad_or_None)
    """
    p = Path(path)
    raw = p.read_bytes()

    # WAD?
    if raw[:4] in (b'IWAD', b'PWAD'):
        wad = WadFile(p)
        defs = parse_wad(wad)
        return (str(p), defs, wad)

    # Text file
    try:
        text = raw.decode('utf-8', errors='replace')
    except Exception:
        raise ValueError(f"Cannot decode file as text: {p}")

    # Strip blank lines and comments (// SLADE-style, ; DoomTools/DEUTEX-style)
    meaningful = [
        l.strip() for l in text.splitlines()
        if l.strip()
        and not l.strip().startswith('//')
        and not l.strip().startswith(';')
    ]
    stripped = '\n'.join(meaningful)

    # SLADE WallTexture text?
    if re.search(r'^WallTexture\s+"', stripped, re.IGNORECASE | re.MULTILINE):
        defs = parse_slade_text(text)
        return (str(p), defs, None)

    # DoomTools text?
    # Probe the first meaningful line for the "NAME W H" pattern
    if meaningful:
        parts = meaningful[0].split()
        if len(parts) >= 3:
            try:
                int(parts[1]); int(parts[2])
                defs = parse_doomtools_text(text)
                return (str(p), defs, None)
            except ValueError:
                pass

    raise ValueError(
        f"Cannot determine format of '{p.name}'. "
        f"Expected: WAD, SLADE WallTexture text, or DoomTools text."
    )


# ══════════════════════════════════════════════════════════════════════════════
# OUTPUT DIR NAMING
# ══════════════════════════════════════════════════════════════════════════════

def output_dir_name(input_path, lump_name):
    """
    Derive output directory name from input file stem + lump name.
    WAD → _texture1 / _texture2
    Text file → _stem (preserving original case)
    """
    stem = Path(input_path).stem
    if lump_name in ('TEXTURE1', 'TEXTURE2'):
        return f"_{lump_name.lower()}"
    else:
        return f"_{stem}"


# ══════════════════════════════════════════════════════════════════════════════
# CORE RENDERER
# ══════════════════════════════════════════════════════════════════════════════

def composite_texture(tex, patch_sources, palette):
    """
    Composite a TextureDef into an RGBA Image.
    patch_sources: list of PatchSource objects (tried in order).
    palette: list of 256 (R,G,B), or None if all sources are dir-based.
    Returns (Image, list_of_missing_patch_names, set_of_sources_used).
    """
    canvas = Image.new('RGBA', (tex.width, tex.height), (0, 0, 0, 0))
    missing = []
    sources_used = set()   # PatchSource objects that supplied >=1 patch

    for patch_name, ox, oy in tex.patches:
        patch_img = None
        for src in patch_sources:
            try:
                patch_img = src.get_image(patch_name, palette)
            except RuntimeError as e:
                raise
            if patch_img is not None:
                sources_used.add(id(src))
                break

        if patch_img is None:
            missing.append(patch_name)
            continue

        # Clip patch to canvas bounds
        pw, ph = patch_img.size
        # Source rectangle within the patch
        sx = max(0, -ox)
        sy = max(0, -oy)
        # Destination on canvas
        dx = max(0, ox)
        dy = max(0, oy)
        # How much fits
        cw = min(pw - sx, tex.width  - dx)
        ch = min(ph - sy, tex.height - dy)

        if cw <= 0 or ch <= 0:
            continue  # entirely outside canvas

        region = patch_img.crop((sx, sy, sx + cw, sy + ch))
        # Alpha-composite onto canvas at (dx, dy)
        tmp = Image.new('RGBA', (tex.width, tex.height), (0, 0, 0, 0))
        tmp.paste(region, (dx, dy))
        canvas = Image.alpha_composite(canvas, tmp)

    return canvas, missing, sources_used


# ══════════════════════════════════════════════════════════════════════════════
# --clean OUTPUT (DoomTools definition text files)
# ══════════════════════════════════════════════════════════════════════════════

STINKY_NAMES = {'AASTINKY', 'AASHITTY'}   # Doom 1 / Doom 2 null textures

def format_doomtools_entry(tex):
    """Format one TextureDef as a DoomTools text entry."""
    lines = [f"{tex.name} {tex.width} {tex.height}"]
    for patch_name, ox, oy in tex.patches:
        lines.append(f"*\t{patch_name} {ox} {oy}")
    return '\n'.join(lines)


def write_doomtools_file(path, tex_list, stinky_texs=()):
    """
    Write a bare DoomTools definition file: no comments, no header.
    tex_list is sorted alphabetically; stinky_texs (null textures) are
    pinned first in their original order.
    """
    entries = []
    for tex in stinky_texs:
        entries.append(format_doomtools_entry(tex))
    for tex in sorted(tex_list, key=lambda t: t.name):
        entries.append(format_doomtools_entry(tex))
    Path(path).write_text('\n\n'.join(entries) + '\n', encoding='ascii')


def write_clean_files(out_dir, def_stem, tex_list, rendered_names, stinky):
    """
    Emit the three --clean files into out_dir:
      _cleaned_<stem>.txt  — original defs minus rendered (minus AASTINKY unless +stinky)
      _removed_<stem>.txt  — original multi-patch defs of rendered textures only
      _rendered_<stem>.txt — rendered textures as new single-patch entries
    """
    rendered_set = set(rendered_names)

    # Null texture(s) present in the definition, original order preserved
    stinky_texs = []
    if stinky:
        stinky_texs = [t for t in tex_list if t.name in STINKY_NAMES]

    # Null textures excluded from the sorted body in all cases
    body = [t for t in tex_list if t.name not in STINKY_NAMES]

    cleaned  = [t for t in body if t.name not in rendered_set]
    removed  = [t for t in body if t.name in rendered_set]
    rendered = [
        TextureDef(t.name, t.width, t.height, [(t.name, 0, 0)])
        for t in removed
    ]

    out_dir = Path(out_dir)
    files = [
        (out_dir / f"_cleaned_{def_stem}.txt",  cleaned),
        (out_dir / f"_removed_{def_stem}.txt",  removed),
        (out_dir / f"_rendered_{def_stem}.txt", rendered),
    ]
    for path, texs in files:
        write_doomtools_file(path, texs, stinky_texs)
    return [p for p, _ in files]




def parse_args(argv):
    args = argv[1:]

    if not args or any(a in ('-h', '--h', '-help', '--help') for a in args):
        print(HELP)
        sys.exit(0)

    def_files    = []
    patches_srcs = []     # zero or more; empty = silent fallthrough to input WAD + IWAD
    iwad_src     = None
    pal_src      = None
    tex_filter   = []
    verbose      = False
    clean        = False
    stinky       = False

    i = 0
    while i < len(args):
        a = args[i]
        al = a.lstrip('-').lower()  # normalise --flag → flag

        if a.startswith('-') and al in ('patches', 'p'):
            # Collect zero or more values until the next flag.
            # Zero values = silently fall through to input WAD + IWAD.
            i += 1
            while i < len(args) and not args[i].startswith('-') and args[i] != '+stinky':
                patches_srcs.append(args[i])
                i += 1
            continue
        elif a.startswith('-') and al == 'iwad':
            if i + 1 >= len(args) or args[i + 1].startswith('-'):
                print(RED("Error: -iwad requires a value (alias or path)."))
                sys.exit(1)
            i += 1
            iwad_src = args[i]
        elif a.startswith('-') and al == 'pal':
            if i + 1 >= len(args) or args[i + 1].startswith('-'):
                print(RED("Error: -pal requires a value (palette file)."))
                sys.exit(1)
            i += 1
            pal_src = args[i]
        elif a.startswith('-') and al == 'tex':
            i += 1
            while i < len(args) and not args[i].startswith('-') and args[i] != '+stinky':
                tex_filter.append(args[i].upper())
                i += 1
            continue
        elif a.startswith('-') and al in ('verbose', 'v'):
            verbose = True
        elif a.startswith('-') and al == 'clean':
            clean = True
        elif a == '+stinky':
            stinky = True
        elif a.startswith('-'):
            print(RED(f"Unknown option: {a}"))
            sys.exit(1)
        else:
            def_files.append(a)
        i += 1

    if not def_files:
        print(RED("Error: no texture definition file(s) specified."))
        print(f"Run {GREEN('rendertex -help')} for usage.")
        sys.exit(1)

    # Resolve IWAD (alias or path)
    if iwad_src is None:
        iwad_src = IWAD_DEFAULT
    iwad_path = IWAD_ALIASES.get(iwad_src.lower(), iwad_src)

    # Resolve -patches values: alias wins over same-named local path
    resolved_patches = [IWAD_ALIASES.get(s.lower(), s) for s in patches_srcs]

    return def_files, resolved_patches, iwad_path, pal_src, tex_filter, verbose, clean, stinky


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    def_files, patches_srcs, iwad_path, pal_src, tex_filter, verbose, clean, stinky = parse_args(sys.argv)

    # ── Load -patches sources, split into dirs and WADs ──────────────────────
    # Lookup order: dirs (CLI order) → WADs (CLI order) → input WAD → IWAD
    dir_sources = []
    wad_sources = []

    for src in patches_srcs:
        try:
            ps = PatchSource(src)
        except FileNotFoundError as e:
            print(RED(f"Error: {e}"))
            sys.exit(1)
        except Exception as e:
            print(RED(f"Error loading patch source '{src}': {e}"))
            sys.exit(1)
        if ps._is_wad:
            wad_sources.append(ps)
        else:
            dir_sources.append(ps)
        print(DIM(f"Patch source: {src}" + ("  (dir)" if not ps._is_wad else "  (wad)")))

    # ── IWAD (last patch source + last palette fallback) ─────────────────────
    iwad_wad = None
    iwad_ps  = None
    if iwad_path and Path(iwad_path).exists():
        try:
            iwad_wad = WadFile(iwad_path)
            iwad_ps  = PatchSource(iwad_path)
            print(DIM(f"IWAD:         {iwad_path}"))
        except Exception as e:
            print(YELLOW(f"Warning: could not load IWAD '{iwad_path}': {e}"))
    elif iwad_path:
        print(YELLOW(f"Warning: IWAD not found at '{iwad_path}' — skipping as patch/palette source"))

    # ── Pre-load palette fallbacks ────────────────────────────────────────────
    # Full order: input WAD → -patches WADs (first found) → -pal → -iwad
    patches_pal = None
    for ps in wad_sources:
        try:
            patches_pal = load_palette(ps._wad)
            print(DIM(f"Palette:      PLAYPAL found in patches WAD '{ps.path.name}'"))
            break
        except Exception:
            continue

    explicit_pal = None
    if pal_src:
        try:
            explicit_pal = load_palette(pal_src, label="-pal")
            print(DIM(f"Palette:      {pal_src} (-pal)"))
        except Exception as e:
            print(RED(f"Error loading palette '{pal_src}': {e}"))
            sys.exit(1)

    iwad_pal = None
    if iwad_wad:
        try:
            iwad_pal = load_palette(iwad_wad)
        except Exception:
            pass  # IWAD may not have a PLAYPAL

    # ── Process each definition file ──────────────────────────────────────────
    for def_path in def_files:
        print()
        print(BOLD(CYAN(f"── {def_path}")))

        try:
            label, all_defs, def_wad = detect_and_parse(def_path)
        except Exception as e:
            print(RED(f"  Error reading '{def_path}': {e}"))
            continue

        # ── Patch chain for this definition ───────────────────────────────
        # dirs → -patches WADs → input WAD (if WAD input) → IWAD
        # Each entry paired with a (kind, name) label for verbose grouping.
        patch_sources = []
        source_labels = {}   # id(PatchSource) → heading string

        for ps in dir_sources:
            patch_sources.append(ps)
            source_labels[id(ps)] = f"Patch Dir : {ps.path}"
        for ps in wad_sources:
            patch_sources.append(ps)
            source_labels[id(ps)] = f"Wad : {ps.path.name}"
        if def_wad:
            try:
                dps = PatchSource(def_wad.path)
                patch_sources.append(dps)
                source_labels[id(dps)] = f"Wad : {dps.path.name}"
            except Exception:
                pass
        if iwad_ps:
            patch_sources.append(iwad_ps)
            source_labels[id(iwad_ps)] = f"iWad : {iwad_ps.path.name}"

        if not patch_sources:
            print(YELLOW("  Warning: no patch sources available — all textures will be skipped as missing"))

        # ── Palette for this input ─────────────────────────────────────────
        def_pal = None
        if def_wad:
            try:
                def_pal = load_palette(def_wad)
                print(DIM(f"  Palette: from input WAD"))
            except Exception:
                pass

        # Resolution order: input WAD → patches WADs → -pal → -iwad
        palette = def_pal or patches_pal or explicit_pal or iwad_pal

        # ── Per-lump rendering ─────────────────────────────────────────────
        for lump_name, tex_list in all_defs.items():
            out_dir_name = output_dir_name(def_path, lump_name)
            out_dir = Path(out_dir_name)
            out_dir.mkdir(exist_ok=True)

            # Apply -tex filter
            if tex_filter:
                filtered = [
                    t for t in tex_list
                    if any(fnmatch.fnmatch(t.name.upper(), pat) for pat in tex_filter)
                ]
            else:
                filtered = tex_list

            rendered_names   = []
            skipped_single   = []
            skipped_missing  = []   # (tex_name, [missing_patch_names])
            # id(source) → [tex names], insertion follows patch_sources order
            source_usage     = {id(s): [] for s in patch_sources}

            total = len(filtered)
            print(f"  {CYAN(lump_name)}  →  {YELLOW(out_dir_name)}  "
                  f"({total} texture{'s' if total != 1 else ''} to consider)")

            for tex in filtered:
                # Null textures (AASTINKY / AASHITTY) are never rendered
                if tex.name in STINKY_NAMES:
                    continue

                if len(tex.patches) <= 1:
                    skipped_single.append(tex.name)
                    continue

                try:
                    img, missing, used = composite_texture(tex, patch_sources, palette)
                except RuntimeError as e:
                    # Palette missing for WAD patch decode
                    print(RED(f"    Fatal: {e}"))
                    sys.exit(1)

                if missing:
                    skipped_missing.append((tex.name, missing))
                    continue

                out_path = out_dir / f"{tex.name}.png"
                img.save(out_path)
                rendered_names.append(tex.name)
                for sid in used:
                    source_usage[sid].append(tex.name)

            # ── Per-lump summary ───────────────────────────────────────────
            rendered_count = len(rendered_names)
            print()
            print(f"  {BOLD('Results for')} {CYAN(lump_name)}:")

            if skipped_single:
                print(f"    {DIM('Skipped (single-patch):')}  {len(skipped_single)}")

            if skipped_missing:
                print(f"    {YELLOW('Skipped (missing patches):')}  {len(skipped_missing)}")
                for tex_name, missing_patches in skipped_missing:
                    mp = ', '.join(dict.fromkeys(missing_patches))
                    print(f"      {YELLOW(tex_name)}  ←  {DIM(mp)}")

            print(f"    {GREEN('Rendered:')}  {rendered_count} texture{'s' if rendered_count != 1 else ''}")

            # ── Verbose: per-source texture listings ───────────────────────
            if verbose:
                for src in patch_sources:
                    names = source_usage[id(src)]
                    if not names:
                        continue
                    print()
                    print(f"  {BOLD(MAGENTA('--== ' + source_labels[id(src)] + ' ==--'))}")
                    for n in names:
                        print(f"  {n}")

                if skipped_missing:
                    print()
                    print(f"  {BOLD(RED('--== Not Found ==--'))}")
                    for tex_name, _ in skipped_missing:
                        print(f"  {tex_name}")

            # ── --clean: emit definition text files ─────────────────────────
            if clean:
                clean_stem = out_dir_name.lstrip('_')
                written = write_clean_files(
                    out_dir, clean_stem, tex_list, rendered_names, stinky
                )
                print()
                for p in written:
                    print(f"    {GREEN('Wrote:')}  {p}")

        # Check for unmatched -tex patterns
        if tex_filter:
            # Collect all rendered names across all lumps
            all_names = set()
            for tex_list in all_defs.values():
                all_names.update(t.name.upper() for t in tex_list)
            unmatched = [
                pat for pat in tex_filter
                if not any(fnmatch.fnmatch(n, pat) for n in all_names)
            ]
            if unmatched:
                print(f"    {YELLOW('Warning: -tex patterns matched nothing:')}  "
                      f"{', '.join(unmatched)}")

    print()


if __name__ == '__main__':
    main()