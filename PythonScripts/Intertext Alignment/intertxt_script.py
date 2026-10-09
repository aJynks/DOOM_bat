#!/usr/bin/env python3
"""
intertext_script.py - Doom UMAPINFO intertext formatter + screen preview.

Turns a plain text file into a UMAPINFO `intertext =` block, word-wrapped to
exact pixel widths of the Doom STCFN font, with center/block/right alignment
blocks. Always writes a 320x200 PNG preview of the intermission text screen.

Run via intertext.bat. Pure standard library, Python 3.8+.
"""

# =============================================================================
#  USER SETTINGS - edit these
# =============================================================================

# IWAD used for the STCFN font, PLAYPAL and -bg flats. A -wad file overrides
# it lump-by-lump (anything the -wad lacks is taken from here).
DEFAULT_IWAD = r"d:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad"

# Default preview scale (nearest-neighbour). -scale overrides.
DEFAULT_SCALE = 2

# =============================================================================

import sys

if sys.version_info < (3, 8):
    sys.stderr.write("intertext needs Python 3.8 or newer "
                     f"(this is {sys.version.split()[0]}).\n"
                     "Install: winget install Python.Python.3.12\n")
    sys.exit(1)

import argparse
import os
import re
import struct
import zlib

# -----------------------------------------------------------------------------
#  Engine constants (vanilla F_TextWrite)
# -----------------------------------------------------------------------------

SCREEN_W = 320
SCREEN_H = 200
TEXT_X = 10          # first column drawn
TEXT_Y = 10          # first line's y
LINE_H = 11          # y step per newline
SPACE_W = 4          # advance for any char outside the font (incl. space)
FONT_FIRST = 33      # '!'
FONT_LAST = 95       # '_'
DEFAULT_WRAP = SCREEN_W - TEXT_X   # 310: engine stops drawing at cx+w > 320

# Vanilla STCFN metrics: char -> (width, height, topoffset).
# Used when no WAD supplies a glyph. Measured from the doom2.wad lumps.
BUILTIN_FONT = {
    33: (4, 7, 0), 34: (7, 4, 0), 35: (7, 7, 0), 36: (7, 8, 0), 37: (9, 7, 0),
    38: (8, 7, 0), 39: (4, 4, 0), 40: (7, 7, 0), 41: (7, 7, 0), 42: (7, 7, 0),
    43: (5, 5, -1), 44: (4, 4, -3), 45: (6, 3, -2), 46: (4, 3, -4),
    47: (7, 7, 0), 48: (8, 7, 0), 49: (5, 7, 0), 50: (8, 7, 0), 51: (8, 7, 0),
    52: (7, 7, 0), 53: (7, 7, 0), 54: (8, 7, 0), 55: (8, 7, 0), 56: (8, 7, 0),
    57: (8, 7, 0), 58: (4, 7, 0), 59: (4, 7, 0), 60: (5, 7, 0), 61: (5, 5, -1),
    62: (5, 7, 0), 63: (8, 7, 0), 64: (9, 8, 0), 65: (8, 7, 0), 66: (8, 7, 0),
    67: (8, 7, 0), 68: (8, 7, 0), 69: (8, 7, 0), 70: (8, 7, 0), 71: (8, 7, 0),
    72: (8, 7, 0), 73: (4, 7, 0), 74: (8, 7, 0), 75: (8, 7, 0), 76: (8, 7, 0),
    77: (9, 7, 0), 78: (8, 7, 0), 79: (8, 7, 0), 80: (8, 7, 0), 81: (8, 8, 0),
    82: (8, 7, 0), 83: (7, 7, 0), 84: (8, 7, 0), 85: (8, 7, 0), 86: (7, 7, 0),
    87: (9, 7, 0), 88: (9, 7, 0), 89: (8, 7, 0), 90: (7, 7, 0), 91: (5, 7, 0),
    92: (7, 7, 0), 93: (5, 7, 0), 94: (7, 5, 0), 95: (8, 3, -4),
}

# Typographic characters that have a sensible font equivalent.
CHAR_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
    "\u2013": "-", "\u2014": "--", "\u2212": "-", "\u2026": "...",
    "\u00a0": " ", "\t": " ", "\u00d7": "X",
}

ALIGNS = ("left", "center", "block", "right")

# -----------------------------------------------------------------------------
#  Console colour
# -----------------------------------------------------------------------------


def _enable_ansi():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            return False
    return True


_COLOR = _enable_ansi()


def c(text, code):
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def dcyan(t): return c(t, "36")
def cyan(t): return c(t, "96")
def green(t): return c(t, "92")
def yellow(t): return c(t, "93")
def red(t): return c(t, "91")
def gray(t): return c(t, "90")
def white(t): return c(t, "97")


WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(yellow("  WARNING: ") + msg)


def die(msg):
    print(red("ERROR: ") + msg)
    sys.exit(1)


# -----------------------------------------------------------------------------
#  Help
# -----------------------------------------------------------------------------

def print_help():
    bar = dcyan("=" * 72)
    print(bar)
    print(dcyan("  INTERTEXT") + gray("  -  UMAPINFO intertext formatter + screen preview"))
    print(bar)
    print()
    print(cyan("USAGE"))
    print("  intertext " + green("<file.txt>") + " [options]")
    print("  intertext " + green("-sizes") + " [" + green("-wad") + " file]")
    print()
    print(cyan("WHAT IT DOES"))
    print("  Word-wraps your text to the exact pixel widths of the Doom font,")
    print("  applies alignment blocks, and writes:")
    print("    " + white("<name>_intertext.txt") + "   the UMAPINFO intertext block")
    print("    " + white("<name>.png") + "             preview of the text screen (always,")
    print("                           overwritten each run)")
    print("  Doom never wraps text itself, so every line is pre-broken to fit.")
    print()
    print(cyan("SOURCE FORMAT"))
    print("  - Each line you type is a hard line break.")
    print("  - Lines wider than the screen are word-wrapped automatically.")
    print("  - Blank lines stay blank. Text is uppercased (the font has no")
    print("    lowercase).")
    print("  - Alignment blocks (may span any number of lines, no nesting):")
    print("      " + green("center{ ... }") + "  center each line")
    print("      " + green("block{ ... }") + "   keep lines left-aligned to each other,")
    print("                     center the block as a whole")
    print("      " + green("right{ ... }") + "   right-align each line")
    print("      " + green("left{ ... }") + "    explicit left (same as no block)")
    print("  - Use " + green("\\{") + " " + green("\\}") + " " + green("\\\\") +
          " for literal braces / backslash.")
    print("  - Alignment uses 4px spaces, so centering is accurate to ~2px.")
    print()
    print(cyan("OPTIONS"))
    opts = [
        ("-wad <file>", "PWAD/IWAD to take the font, PLAYPAL and -bg from. Any"),
        ("", "lump it lacks falls back to DEFAULT_IWAD (top of script)."),
        ("-o <file>", "write the intertext .txt here instead of <name>_intertext.txt"),
        ("-stdout", "print the intertext block instead of writing the .txt"),
        ("-bg <name|png>", "preview background: a flat or patch lump name (tiled"),
        ("", "like the engine), or a .png file. Default: black."),
        ("-scale <n>", f"preview scale 1-8 (default {DEFAULT_SCALE})"),
        ("-width <px>", f"wrap width (default {DEFAULT_WRAP}; more than that is"),
        ("", "cut off by vanilla-style engines)"),
        ("-report", "print each line's y, x start/end, width and status"),
        ("-sizes", "print the font width table and exit"),
        ("-h, --help", "show this help"),
    ]
    for a, d in opts:
        print("  " + (green(a.ljust(16)) if a else " " * 16) + "  " + d)
    print()
    print(cyan("SCREEN LIMITS"))
    print(f"  Text starts at x={TEXT_X}, y={TEXT_Y}, {LINE_H}px per line. About 17 lines fit")
    print("  on a 200px screen; overflowing lines are reported and shown in red")
    print("  below the cut-off in the preview PNG.")
    print()
    print(cyan("EXAMPLES"))
    ex = [
        ("intertext story.txt", "story_intertext.txt + story.png"),
        ("intertext story.txt -wad citadel.wad", "use the PWAD's font"),
        ("intertext story.txt -bg SLIME16", "preview over a tiled flat"),
        ("intertext story.txt -report", "show per-line pixel positions"),
        ("intertext story.txt -stdout", "print the block, no .txt written"),
        ("intertext -sizes", "dump the font metrics"),
    ]
    for cmd, note in ex:
        print("  " + yellow(cmd.ljust(40)) + gray(note))
    print()


# -----------------------------------------------------------------------------
#  PNG read / write (stdlib)
# -----------------------------------------------------------------------------

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_write(path, width, height, rgb_rows):
    """rgb_rows: list of bytes/bytearray, each width*3 long."""
    raw = bytearray()
    for row in rgb_rows:
        raw.append(0)
        raw += row

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    out = PNG_SIG
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    out += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    out += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)


def png_read(data):
    """Decode a PNG. Returns (w, h, rows, grab) where rows[y][x] is (r,g,b) or
    None for transparent, and grab is (x, y) offsets or None. Raises
    ValueError on unsupported files."""
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    pos = 8
    ihdr = None
    plte = None
    trns = None
    grab = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            plte = [tuple(body[i:i + 3]) for i in range(0, len(body) - 2, 3)]
        elif tag == b"tRNS":
            trns = body
        elif tag == b"grAb" and length >= 8:
            grab = struct.unpack(">ii", body[:8])
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if ihdr is None:
        raise ValueError("PNG has no IHDR")
    w, h, depth, ctype, _comp, _filt, interlace = ihdr
    if interlace:
        raise ValueError("interlaced PNGs are not supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise ValueError(f"unsupported PNG colour type {ctype}")
    if depth not in (1, 2, 4, 8, 16):
        raise ValueError(f"unsupported PNG bit depth {depth}")

    raw = zlib.decompress(bytes(idat))
    bits_pp = channels * depth
    bpp = max(1, bits_pp // 8)
    stride = (w * bits_pp + 7) // 8
    rows = []
    prev = bytearray(stride)
    p = 0
    for _y in range(h):
        ftype = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                cc = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - cc), abs(a - cc), abs(a + b - 2 * cc)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else cc)
                line[i] = (line[i] + pr) & 0xFF
        rows.append(line)
        prev = line

    def samples(line):
        if depth == 8:
            return list(line)
        if depth == 16:
            return [line[i] for i in range(0, len(line), 2)]   # high byte
        out = []
        mask = (1 << depth) - 1
        for byte in line:
            for shift in range(8 - depth, -1, -depth):
                out.append((byte >> shift) & mask)
        return out

    trns_key = None
    if trns is not None and ctype == 0 and len(trns) >= 2:
        trns_key = struct.unpack(">H", trns[:2])[0]
        if depth == 16:
            trns_key >>= 8
    elif trns is not None and ctype == 2 and len(trns) >= 6:
        k = struct.unpack(">HHH", trns[:6])
        trns_key = tuple(v >> 8 for v in k) if depth == 16 else k

    scale = 255 // ((1 << min(depth, 8)) - 1) if ctype in (0, 4) else 1
    out_rows = []
    for line in rows:
        s = samples(line)
        row = []
        for x in range(w):
            if ctype == 3:
                idx = s[x]
                if trns is not None and idx < len(trns) and trns[idx] < 128:
                    row.append(None)
                else:
                    row.append(plte[idx] if plte and idx < len(plte) else (0, 0, 0))
            elif ctype == 0:
                v = s[x]
                row.append(None if v == trns_key else (v * scale,) * 3)
            elif ctype == 4:
                v, a = s[x * 2], s[x * 2 + 1]
                row.append(None if a < (1 << (min(depth, 8) - 1)) else (v * scale,) * 3)
            elif ctype == 2:
                px = tuple(s[x * 3:x * 3 + 3])
                row.append(None if px == trns_key else px)
            else:
                r, g, b, a = s[x * 4:x * 4 + 4]
                row.append(None if a < 128 else (r, g, b))
        out_rows.append(row)
    return w, h, out_rows, grab


# -----------------------------------------------------------------------------
#  WAD access
# -----------------------------------------------------------------------------

class Wad:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        with open(path, "rb") as f:
            self.data = f.read()
        if len(self.data) < 12 or self.data[:4] not in (b"IWAD", b"PWAD"):
            raise ValueError("not a WAD file")
        num, ofs = struct.unpack_from("<ii", self.data, 4)
        if num < 0 or ofs < 0 or ofs + num * 16 > len(self.data):
            raise ValueError("corrupt WAD directory")
        self.lumps = []
        for i in range(num):
            lpos, lsize, raw = struct.unpack_from("<ii8s", self.data, ofs + i * 16)
            name = raw.split(b"\0")[0].decode("ascii", "replace").upper()
            self.lumps.append((name, lpos, lsize))

    def _read(self, entry):
        _n, lpos, lsize = entry
        if lpos < 0 or lsize < 0 or lpos + lsize > len(self.data):
            return None
        return self.data[lpos:lpos + lsize]

    def get(self, name):
        """Last lump with this name (PWAD override semantics)."""
        name = name.upper()
        for entry in reversed(self.lumps):
            if entry[0] == name:
                return self._read(entry)
        return None

    def get_flat(self, name):
        """Lump inside an F_START/F_END (or FF_) namespace, or None."""
        name = name.upper()
        found = None
        inside = False
        for entry in self.lumps:
            n = entry[0]
            if n in ("F_START", "FF_START"):
                inside = True
            elif n in ("F_END", "FF_END"):
                inside = False
            elif inside and n == name:
                found = entry
        return self._read(found) if found else None


def open_wad(path, label):
    if not path:
        return None
    if not os.path.isfile(path):
        warn(f"{label} not found: {path}")
        return None
    try:
        return Wad(path)
    except (OSError, ValueError) as e:
        warn(f"{label} could not be read ({e}): {path}")
        return None


def lookup(wads, name, flat=False):
    """First hit across wads (in priority order). Returns (data, wad) or (None, None)."""
    for w in wads:
        data = w.get_flat(name) if flat else w.get(name)
        if data is not None:
            return data, w
    return None, None


def decode_patch(data, palette):
    """Doom picture format -> (w, h, leftofs, topofs, rows of rgb/None)."""
    if len(data) < 8:
        return None
    w, h, lo, to = struct.unpack_from("<hhhh", data, 0)
    if w <= 0 or h <= 0 or w > 4096 or h > 4096 or 8 + w * 4 > len(data):
        return None
    colofs = struct.unpack_from(f"<{w}i", data, 8)
    rows = [[None] * w for _ in range(h)]
    for x in range(w):
        pos = colofs[x]
        if pos < 0 or pos >= len(data):
            return None
        last = -1
        while pos < len(data):
            top = data[pos]
            if top == 0xFF:
                break
            if top <= last:           # tall-patch cumulative topdelta
                top += last
            last = top
            if pos + 2 >= len(data):
                break
            length = data[pos + 1]
            pos += 3
            if pos + length > len(data):
                break
            for i in range(length):
                y = top + i
                if 0 <= y < h:
                    rows[y][x] = palette[data[pos + i]]
            pos += length + 1
    return w, h, lo, to, rows


def decode_graphic(data, palette):
    """Patch or PNG lump -> (w, h, lo, to, rows) or None."""
    if data.startswith(PNG_SIG):
        try:
            w, h, rows, grab = png_read(data)
        except (ValueError, zlib.error):
            return None
        lo, to = grab if grab else (0, 0)
        return w, h, lo, to, rows
    return decode_patch(data, palette)


# -----------------------------------------------------------------------------
#  Font
# -----------------------------------------------------------------------------

class Glyph:
    __slots__ = ("w", "h", "lo", "to", "rows", "source")

    def __init__(self, w, h, lo, to, rows, source):
        self.w, self.h, self.lo, self.to, self.rows, self.source = w, h, lo, to, rows, source


class Font:
    def __init__(self, wads):
        self.wads = wads
        self.palette, self.palette_src = self._load_palette()
        self.glyphs = {}
        for code in range(FONT_FIRST, FONT_LAST + 1):
            lump = f"STCFN{code:03d}"
            data, src = lookup(wads, lump)
            g = None
            if data is not None:
                dec = decode_graphic(data, self.palette)
                if dec:
                    g = Glyph(*dec, source=src.name)
                else:
                    warn(f"{lump} in {src.name} is not a valid graphic - using built-in metrics")
            if g is None:
                bw, bh, bt = BUILTIN_FONT[code]
                g = Glyph(bw, bh, 0, bt, None, "built-in")
            self.glyphs[code] = g

    def _load_palette(self):
        data, src = lookup(self.wads, "PLAYPAL")
        if data is not None and len(data) >= 768:
            return [tuple(data[i * 3:i * 3 + 3]) for i in range(256)], src.name
        return [(i, i, i) for i in range(256)], "greyscale fallback"

    def advance(self, ch):
        o = ord(ch)
        if FONT_FIRST <= o <= FONT_LAST:
            return self.glyphs[o].w
        return SPACE_W

    def text_width(self, s):
        return sum(self.advance(ch) for ch in s)

    def sources(self):
        counts = {}
        for g in self.glyphs.values():
            counts[g.source] = counts.get(g.source, 0) + 1
        return counts

    def has_real_glyphs(self):
        return any(g.rows is not None for g in self.glyphs.values())


# -----------------------------------------------------------------------------
#  Source parsing
# -----------------------------------------------------------------------------

BLOCK_OPEN = re.compile(r"(?<![A-Za-z0-9_])(center|block|right|left)\{", re.IGNORECASE)


class SrcLine:
    __slots__ = ("align", "text", "lineno", "block_id")

    def __init__(self, align, text, lineno, block_id):
        self.align, self.text, self.lineno, self.block_id = align, text, lineno, block_id


def parse_source(text):
    """Split source into SrcLines carrying alignment. Blocks always occupy
    their own lines: an opener/closer on its own line produces no blank line."""
    lines = []
    buf = []
    align = "left"
    block_id = None
    next_block = 0
    lineno = 1
    buf_line = 1
    open_line = 0
    i = 0
    n = len(text)

    def push(force=False):
        nonlocal buf, buf_line
        s = "".join(buf)
        if force or s.strip():
            lines.append(SrcLine(align, s, buf_line, block_id))
        buf = []
        buf_line = lineno

    def skip_to_eol(pos):
        """After an opener/closer: swallow trailing spaces and one newline."""
        nonlocal lineno
        j = pos
        while j < n and text[j] in " \t":
            j += 1
        if j < n and text[j] == "\n":
            lineno += 1
            return j + 1
        return pos

    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] in "{}\\":
            buf.append(text[i + 1])
            i += 2
            continue
        if ch == "\n":
            push(force=True)
            lineno += 1
            buf_line = lineno
            i += 1
            continue
        m = BLOCK_OPEN.match(text, i)
        if m:
            if block_id is not None:
                die(f"line {lineno}: '{m.group(0)}' opened inside another block "
                    f"(opened on line {open_line}) - blocks cannot nest")
            push()                      # text before opener on same line
            align = m.group(1).lower()
            block_id = next_block
            next_block += 1
            open_line = lineno
            i = skip_to_eol(m.end())
            buf_line = lineno
            continue
        if ch == "}":
            if block_id is None:
                die(f"line {lineno}: '}}' with no open block (use \\}} for a literal brace)")
            push()                      # text before closer on same line
            align = "left"
            block_id = None
            i = skip_to_eol(i + 1)
            buf_line = lineno
            continue
        buf.append(ch)
        i += 1

    if block_id is not None:
        die(f"block opened on line {open_line} is never closed with '}}'")
    if buf:
        push(force=True)
    # Drop trailing blank lines.
    while lines and not lines[-1].text.strip():
        lines.pop()
    return lines


# -----------------------------------------------------------------------------
#  Normalisation, wrapping, alignment
# -----------------------------------------------------------------------------

def normalise(s):
    for k, v in CHAR_MAP.items():
        s = s.replace(k, v)
    return s.upper()


class OutLine:
    __slots__ = ("text", "lineno", "align")

    def __init__(self, text, lineno, align):
        self.text, self.lineno, self.align = text, lineno, align


def wrap_line(s, font, width, lineno, keep_indent):
    """Greedy pixel word-wrap. Returns list of strings (no trailing spaces)."""
    if not s.strip():
        return [""]
    tokens = re.findall(r" +|[^ ]+", s)
    out = []
    cur = ""
    pending = ""
    first = True
    for tok in tokens:
        if tok[0] == " ":
            if cur == "" and first and keep_indent:
                cur = tok               # leading indent on the first line
            elif cur.strip():
                pending = tok
            continue
        first = False
        cand = cur + pending + tok
        if font.text_width(cand) <= width:
            cur = cand
            pending = ""
            continue
        if cur.strip():
            out.append(cur.rstrip())
        cur = ""
        pending = ""
        # word alone too wide -> hard split
        if font.text_width(tok) > width:
            warn(f"line {lineno}: '{tok}' is wider than {width}px on its own - split mid-word")
            piece = ""
            for ch in tok:
                if font.text_width(piece + ch) > width and piece:
                    out.append(piece)
                    piece = ""
                piece += ch
            cur = piece
        else:
            cur = tok
    if cur.strip():
        out.append(cur.rstrip())
    return out or [""]


def pad_spaces(px):
    return max(0, px // SPACE_W)


def layout(src_lines, font, width):
    out = []
    blocks = {}   # block_id -> list of (index in out)
    for sl in src_lines:
        text = normalise(sl.text)
        if sl.align == "left":
            for w in wrap_line(text.rstrip(), font, width, sl.lineno, keep_indent=True):
                out.append(OutLine(w, sl.lineno, "left"))
        elif sl.align in ("center", "right"):
            for w in wrap_line(text.strip(), font, width, sl.lineno, keep_indent=False):
                if w:
                    tw = font.text_width(w)
                    if sl.align == "center":
                        n = round((width - tw) / 2 / SPACE_W)
                        while n > 0 and n * SPACE_W + tw > width:
                            n -= 1
                    else:
                        n = pad_spaces(width - tw)
                    w = " " * max(0, n) + w
                out.append(OutLine(w, sl.lineno, sl.align))
        else:  # block
            idxs = blocks.setdefault(sl.block_id, [])
            for w in wrap_line(text.rstrip(), font, width, sl.lineno, keep_indent=True):
                idxs.append(len(out))
                out.append(OutLine(w, sl.lineno, "block"))

    # block alignment: dedent, then shift whole block by its widest line
    for idxs in blocks.values():
        texts = [out[i].text for i in idxs]
        indents = [len(t) - len(t.lstrip(" ")) for t in texts if t.strip()]
        common = min(indents) if indents else 0
        texts = [t[common:] if t.strip() else "" for t in texts]
        widest = max((font.text_width(t) for t in texts), default=0)
        n = round((width - widest) / 2 / SPACE_W)
        while n > 0 and n * SPACE_W + widest > width:
            n -= 1
        for i, t in zip(idxs, texts):
            out[i].text = (" " * max(0, n) + t) if t else ""
    return out


def check_chars(src_lines, font):
    bad = {}
    for sl in src_lines:
        for ch in normalise(sl.text):
            o = ord(ch)
            if ch == " " or FONT_FIRST <= o <= FONT_LAST:
                continue
            bad.setdefault(ch, []).append(sl.lineno)
    for ch, where in sorted(bad.items()):
        lines = sorted(set(where))
        shown = ", ".join(str(x) for x in lines[:6]) + (" ..." if len(lines) > 6 else "")
        warn(f"character {ch!r} (U+{ord(ch):04X}) has no glyph in the Doom font - "
             f"drawn as a 4px gap (line {shown})")


# -----------------------------------------------------------------------------
#  Measurement (mirrors F_TextWrite)
# -----------------------------------------------------------------------------

class Measured:
    __slots__ = ("y", "x0", "x1", "bottom", "status", "drawn")

    def __init__(self):
        self.y = self.x0 = self.x1 = self.bottom = 0
        self.status = "ok"
        self.drawn = True


def measure(out_lines, font):
    """Per-line geometry + overflow status, following the engine loop exactly,
    including vanilla's 'stop everything' when a glyph passes x=320."""
    res = []
    stopped = False
    for i, ol in enumerate(out_lines):
        m = Measured()
        m.y = TEXT_Y + i * LINE_H
        cx = TEXT_X
        first = None
        last = None
        bottom = None
        top = None
        for ch in ol.text:
            o = ord(ch)
            if not (FONT_FIRST <= o <= FONT_LAST):
                cx += SPACE_W
                continue
            g = font.glyphs[o]
            if cx + g.w > SCREEN_W:
                stopped = True
                m.status = "stops"
                break
            if first is None:
                first = cx
            gy = m.y - g.to
            bottom = max(bottom or 0, gy + g.h)
            top = gy if top is None else min(top, gy)
            cx += g.w
            last = cx
        if stopped and m.status != "stops":
            m.drawn = False
        m.x0 = first if first is not None else 0
        m.x1 = last if last is not None else 0
        m.bottom = bottom or 0
        if m.status != "stops" and bottom is not None:
            if top >= SCREEN_H:
                m.status = "hidden"
            elif bottom > SCREEN_H:
                m.status = "partial"
        elif m.status != "stops" and m.y >= SCREEN_H:
            m.status = "hidden-blank"
        res.append(m)
        if stopped and m.status == "stops":
            # every later line is never drawn
            for _ in range(i + 1, len(out_lines)):
                mm = Measured()
                mm.y = TEXT_Y + (len(res)) * LINE_H
                mm.drawn = False
                mm.status = "not drawn"
                res.append(mm)
            break
    return res


# -----------------------------------------------------------------------------
#  Rendering
# -----------------------------------------------------------------------------

def load_background(spec, wads, palette):
    """Returns (w, h, rows) tile or None."""
    if not spec:
        return None
    if spec.lower().endswith(".png"):
        if not os.path.isfile(spec):
            warn(f"background PNG not found: {spec}")
            return None
        try:
            with open(spec, "rb") as f:
                w, h, rows, _ = png_read(f.read())
            return w, h, rows
        except (OSError, ValueError, zlib.error) as e:
            warn(f"background PNG unreadable ({e}): {spec}")
            return None
    name = spec.upper()
    data, src = lookup(wads, name, flat=True)
    if data is None:
        data, src = lookup(wads, name)
    if data is None:
        warn(f"background lump '{name}' not found in any WAD - using black")
        return None
    if len(data) == 4096:
        rows = [[palette[data[y * 64 + x]] for x in range(64)] for y in range(64)]
        return 64, 64, rows
    dec = decode_graphic(data, palette)
    if dec:
        w, h, _lo, _to, rows = dec
        return w, h, rows
    warn(f"background lump '{name}' is not a flat or graphic - using black")
    return None


def render(out_lines, meas, font, bg, scale):
    needed = SCREEN_H
    for m in meas:
        if m.drawn and m.bottom:
            needed = max(needed, m.bottom + 4)
        elif not m.drawn:
            needed = max(needed, m.y + LINE_H)
    overflow = needed > SCREEN_H
    H = needed if overflow else SCREEN_H
    W = SCREEN_W
    canvas = [[(0, 0, 0)] * W for _ in range(H)]

    if bg:
        bw, bh, brows = bg
        for y in range(H):
            row = brows[y % bh]
            canvas[y] = [row[x % bw] or (0, 0, 0) for x in range(W)]

    block_col = (200, 200, 200) if not font.has_real_glyphs() else (255, 0, 255)

    def put(x, y, col):
        if 0 <= x < W and 0 <= y < H:
            canvas[y][x] = col

    ghost = (90, 90, 90)
    for ol, m in zip(out_lines, meas):
        cx = TEXT_X
        for ch in ol.text:
            o = ord(ch)
            if not (FONT_FIRST <= o <= FONT_LAST):
                cx += SPACE_W
                continue
            g = font.glyphs[o]
            stop = cx + g.w > SCREEN_W
            gx, gy = cx - g.lo, m.y - g.to
            for yy in range(g.h):
                for xx in range(g.w):
                    if g.rows is None:
                        col = block_col
                    else:
                        col = g.rows[yy][xx]
                        if col is None:
                            continue
                    if stop or not m.drawn:
                        col = ghost         # text the engine never draws
                    put(gx + xx, gy + yy, col)
            cx += g.w
        if m.status == "stops":
            for y in range(m.y - 2, m.y + 9):
                put(SCREEN_W - 1, y, (255, 0, 0))

    if overflow:
        for y in range(SCREEN_H, H):
            row = canvas[y]
            canvas[y] = [((r + 255) // 2, g // 3, b // 3) for (r, g, b) in row]
        canvas[SCREEN_H] = [(255, 0, 0)] * W

    rows_out = []
    for row in canvas:
        line = bytearray()
        for px in row:
            line += bytes(px) * scale
        b = bytes(line)
        rows_out.extend([b] * scale)
    return W * scale, H * scale, rows_out, overflow


# -----------------------------------------------------------------------------
#  Output
# -----------------------------------------------------------------------------

def umapinfo_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_intertext(out_lines):
    body = [f'"{umapinfo_escape(ol.text)}"' for ol in out_lines]
    return "intertext =\n" + ",\n".join(body) + "\n"


def print_sizes(font):
    print(cyan("FONT METRICS") + gray(f"   (palette: {font.palette_src})"))
    print(gray("  char  lump        w   h  xofs yofs  source"))
    for code in range(FONT_FIRST, FONT_LAST + 1):
        g = font.glyphs[code]
        print(f"  {chr(code)!s:<4}  STCFN{code:03d}  {g.w:>3} {g.h:>3}  {g.lo:>4} {g.to:>4}  "
              + (gray(g.source) if g.source == "built-in" else g.source))
    print(f"  {'space':<16}{SPACE_W:>3}       (engine constant, also any char outside the font)")


def print_report(out_lines, meas):
    print()
    print(cyan("LINE REPORT"))
    print(gray("    #     y   x0   x1  width  status     text"))
    for i, (ol, m) in enumerate(zip(out_lines, meas), 1):
        width = m.x1 - m.x0 if m.x1 else 0
        st = m.status
        stc = {"ok": green, "partial": yellow}.get(st, red)
        if st == "hidden-blank":
            st, stc = "off", gray
        t = ol.text.lstrip(" ")
        txt = t if len(t) <= 48 else t[:45] + "..."
        xs = f"{m.x0:>4} {m.x1:>4}  {width:>5}" if m.x1 else f"{'':>4} {'':>4}  {'':>5}"
        print(f"  {i:>3}  {m.y:>4} {xs}  {stc(st.ljust(9))}  {txt}")


# -----------------------------------------------------------------------------
#  Main
# -----------------------------------------------------------------------------

def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main():
    argv = sys.argv[1:]
    if not argv or any(a in ("-h", "--help", "/?", "-help") for a in argv):
        print_help()
        return 0

    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("input", nargs="?")
    ap.add_argument("-wad")
    ap.add_argument("-o")
    ap.add_argument("-stdout", action="store_true")
    ap.add_argument("-bg")
    ap.add_argument("-scale", type=int, default=DEFAULT_SCALE)
    ap.add_argument("-width", type=int, default=DEFAULT_WRAP)
    ap.add_argument("-report", action="store_true")
    ap.add_argument("-sizes", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        print(gray("Run 'intertext -h' for help."))
        return 1

    if not 1 <= args.scale <= 8:
        die("-scale must be 1-8")
    if args.width < 16:
        die("-width is too small")

    print(dcyan("intertext") + gray(" - UMAPINFO intertext formatter"))

    # WADs in priority order: -wad first, then DEFAULT_IWAD
    wads = []
    w = open_wad(args.wad, "-wad file")
    if args.wad and w is None:
        die("cannot continue without the requested -wad file")
    if w:
        wads.append(w)
    iw = None
    if not (w and os.path.abspath(args.wad) == os.path.abspath(DEFAULT_IWAD)):
        iw = open_wad(DEFAULT_IWAD, "DEFAULT_IWAD")
        if iw:
            wads.append(iw)

    font = Font(wads)
    srcs = font.sources()
    desc = ", ".join(f"{n} from {s}" for s, n in sorted(srcs.items(), key=lambda kv: -kv[1]))
    print("  Font:    " + desc)
    if "built-in" in srcs:
        if srcs["built-in"] == len(font.glyphs):
            warn("no STCFN lumps found - widths use the built-in vanilla table and the "
                 "preview draws characters as solid blocks")
        else:
            warn(f"{srcs['built-in']} glyph(s) missing from the WADs - built-in metrics used "
                 "(shown magenta in the preview)")
    print("  Palette: " + font.palette_src)

    if args.sizes:
        print()
        print_sizes(font)
        return 0

    if not args.input:
        die("no input file given (run 'intertext -h' for help)")
    if not os.path.isfile(args.input):
        die(f"input file not found: {args.input}")

    if args.width > DEFAULT_WRAP:
        warn(f"-width {args.width} is wider than {DEFAULT_WRAP}px - vanilla F_TextWrite stops "
             "drawing ALL remaining text at the first glyph past x=320")

    src_path = os.path.abspath(args.input)
    base, _ext = os.path.splitext(src_path)
    txt_out = os.path.abspath(args.o) if args.o else base + "_intertext.txt"
    png_out = base + ".png"
    if txt_out == src_path or png_out == src_path:
        die("output would overwrite the input file - rename the input or use -o")

    src_lines = parse_source(read_text(src_path))
    if not src_lines:
        die("input file has no text")
    check_chars(src_lines, font)
    out_lines = layout(src_lines, font, args.width)
    meas = measure(out_lines, font)

    # overflow / cut-off reporting
    partial = [i + 1 for i, m in enumerate(meas) if m.status == "partial"]
    hidden = [i + 1 for i, m in enumerate(meas) if m.status == "hidden"]
    stops = [i + 1 for i, m in enumerate(meas) if m.status == "stops"]
    if stops:
        print(red("  CUT-OFF: ") + f"line {stops[0]} runs past x=320 - the engine stops drawing "
              "there and NOTHING after it is shown")
        WARNINGS.append("horizontal cut-off")
    if partial or hidden:
        parts = []
        if partial:
            parts.append(f"line {partial[0]} is partially cut")
        if hidden:
            parts.append(f"line{'s' if len(hidden) > 1 else ''} "
                         f"{hidden[0]}{'-' + str(hidden[-1]) if len(hidden) > 1 else ''} "
                         "not visible")
        count = len(partial) + len(hidden)
        print(red("  OVERFLOW: ") + f"{count} line{'s' if count > 1 else ''} draw past the bottom "
              f"of the screen ({', '.join(parts)})")
        print(gray("            ports may clip these; strict vanilla-compatible engines may error"))
        WARNINGS.append("vertical overflow")

    block = build_intertext(out_lines)
    if args.stdout:
        print()
        print(block, end="")
        print()
    else:
        os.makedirs(os.path.dirname(txt_out) or ".", exist_ok=True)
        with open(txt_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(block)
        print("  Wrote:   " + green(txt_out) + gray(f"  ({len(out_lines)} lines)"))

    bg = load_background(args.bg, wads, font.palette)
    pw, ph, rows, overflowed = render(out_lines, meas, font, bg, args.scale)
    png_write(png_out, pw, ph, rows)
    note = f"  ({pw}x{ph}" + (", extended to show overflow" if overflowed else "") + ")"
    print("  Wrote:   " + green(png_out) + gray(note))

    if args.report:
        print_report(out_lines, meas)

    print()
    if WARNINGS:
        print(yellow(f"Done with {len(WARNINGS)} warning(s)."))
    else:
        print(green("Done."))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
