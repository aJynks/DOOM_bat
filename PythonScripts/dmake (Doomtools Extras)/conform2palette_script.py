#!/usr/bin/env python3
# ==============================================================================
# conform2palette_script.py
# ------------------------------------------------------------------------------
# Standalone WAD repaletter. Called by conform2palette.bat (thin shim), or
# runnable directly:  py conform2palette_script.py [input.wad [output.wad]] ...
#
# Converts every graphic in a WAD to a target palette and writes a classic-
# format copy. Doom pictures, flats, palettised PNGs and truecolour PNGs all
# come out as standard Doom pictures (or raw flats in a flat namespace).
# PLAYPAL is replaced with (or, if absent, given) the target's 14 palettes.
# Every other lump is copied byte-for-byte; names, order, markers and
# namespaces never change.
#
#   Target palette : -pal <file or IWAD alias>, else doom2.
#   Source palette : the input WAD's own PLAYPAL, else doom2 (a WAD without
#                    PLAYPAL is drawn in the IWAD palette).
#   Output         : explicit name, else <stem>-palettised.wad next to the
#                    input; -replace overwrites the input instead.
#   No input WAD   : batch mode - every .wad in the current folder, with a
#                    [y]es/[n]o/[a]ll/[s]kip all prompt per WAD.
#
# This is the standalone build of "dmake conform2palette" WITHOUT the
# DoomTools project-folder behaviour. It is fully self-contained: it does not
# read __suite_settings.txt or import _suite_common.py. Edit the settings
# block below.
#
# Pure stdlib. No dependencies.
# ==============================================================================

import os
import re
import struct
import sys
import tempfile
import zlib

# ##############################################################################
# ##   SETTINGS - EDIT HERE                                                   ##
# ##############################################################################

# IWADs: alias -> path (usable as -pal <alias>; doom2 is the default palette)
IWADS = {
    "doom":     r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom.wad",
    "doom2":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad",
    "tnt":      r"D:\Projects\DoomProjects\_SourcePorts\_iwads\tnt.wad",
    "plutonia": r"D:\Projects\DoomProjects\_SourcePorts\_iwads\plutonia.wad",
    "heretic":  r"D:\Projects\DoomProjects\_SourcePorts\_iwads\heretic.wad",
    "hexen":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\hexen.wad",
    "free1":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom1.wad",
    "free2":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom2.wad",
    "doom94":   r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom_1993.wad",
    "doom294":  r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2_1994.wad",
}

# IWAD alias used when -pal is not given, and for input WADs without PLAYPAL
CONFORM_DEFAULT_IWAD = "doom2"

# Suffix for the default output name: <stem><suffix>.wad
CONFORM_SUFFIX = "-palettised"

# ##############################################################################

IWAD_LIST = ", ".join(IWADS.keys())

CONFORM_TOOL            = "conform2palette"
CONFORM_PROJECT_SUPPORT = False
# Project folders are unused in this standalone build (project mode is off).
CONFORM_INPUT_DIRS      = []
CONFORM_OUTPUT_DIR      = "."


# ==============================================================================
# Colour handling (NO_COLOR aware, VT enabled on Windows)
# ==============================================================================
def _use_colour():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not k32.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            if not k32.SetConsoleMode(h, mode.value | 0x0004):
                return False
        except Exception:
            return False
    return True


COLOUR = _use_colour()


def _paint(code):
    def f(t):
        return f"\x1b[{code}m{t}\x1b[0m" if COLOUR else t
    return f


WHT, CYN, DCYN, YEL = _paint("97"), _paint("96"), _paint("36"), _paint("93")
GRY, DGRY, RED, GRN = _paint("37"), _paint("90"), _paint("91"), _paint("92")


def full_path(p):
    return os.path.normpath(os.path.abspath(p))


# ==============================================================================
# Engine
# ==============================================================================
PNG_SIG = b"\x89PNG\r\n\x1a\n"

# 4x4 ordered-dither thresholds for partial alpha (alpha > t -> opaque).
# alpha 255 is always opaque, alpha 0 always transparent.
_BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
BAYER_T = tuple(tuple(m * 16 + 8 for m in row) for row in _BAYER4)

# Near-tie tolerance for colour matching (redmean distance units). When the
# best match is not exact, the LOWEST index within best+TOL wins.
MATCH_TIE_TOL = 4


class ConformError(Exception):
    pass


# ------------------------------------------------------------------------------
# WAD reading / writing
# ------------------------------------------------------------------------------
def wad_parse(data, label):
    """Parse WAD bytes into (magic, entries). Each entry is a dict with
    raw (8-byte name), name (clean upper str), off, size, data."""
    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        raise ConformError(f"{label} is not a WAD file")
    num, diro = struct.unpack_from("<ii", data, 4)
    if num < 0 or diro < 0 or diro + num * 16 > len(data):
        raise ConformError(f"{label} has a corrupt WAD header")
    entries = []
    for i in range(num):
        base = diro + i * 16
        off, size = struct.unpack_from("<ii", data, base)
        raw = data[base + 8: base + 16]
        name = raw.split(b"\x00", 1)[0].decode("ascii", "replace").upper()
        if size > 0:
            if off < 0 or off + size > len(data):
                raise ConformError(f"{label}: lump {name} points outside the file")
            lump = data[off: off + size]
        else:
            lump = b""
        entries.append({"raw": raw, "name": name, "off": off,
                        "size": size, "data": lump})
    return data[0:4], entries


def wad_last_lump(entries, name):
    """Return the data of the LAST lump with this name (as ports do), or None."""
    found = None
    for e in entries:
        if e["name"] == name:
            found = e["data"]
    return found


def wad_write(path, magic, entries):
    """Write entries to a WAD. Lump data in order, directory at the end.
    Zero-size lumps keep their original offset value."""
    with open(path, "wb") as out:
        out.write(magic)
        out.write(struct.pack("<ii", len(entries), 0))
        dir_rows = []
        for e in entries:
            d = e["data"]
            if d:
                off = out.tell()
                out.write(d)
            else:
                off = e["off"]
            dir_rows.append((off, len(d), e["raw"]))
        diro = out.tell()
        for off, size, raw in dir_rows:
            out.write(struct.pack("<ii", off, size))
            out.write(raw)
        out.seek(4)
        out.write(struct.pack("<ii", len(entries), diro))


# ------------------------------------------------------------------------------
# PNG decoding (stdlib only: zlib + struct)
#   Colour types 0/2/3/4/6, bit depths 1-16, Adam7 interlace, tRNS, grAb.
#   Returns (width, height, [ (r,g,b,a), ... ], grab_or_None).
# ------------------------------------------------------------------------------
def _png_unfilter(raw, pos, rowbytes, rows, bpp):
    out = []
    prev = bytearray(rowbytes)
    for _ in range(rows):
        if pos >= len(raw):
            raise ConformError("PNG image data is truncated")
        ft = raw[pos]
        pos += 1
        line = bytearray(raw[pos: pos + rowbytes])
        pos += rowbytes
        if len(line) < rowbytes:
            raise ConformError("PNG image data is truncated")
        if ft == 1:
            for i in range(bpp, rowbytes):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(rowbytes):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(rowbytes):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(rowbytes):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                line[i] = (line[i] + pr) & 0xFF
        elif ft != 0:
            raise ConformError(f"PNG uses unknown filter type {ft}")
        out.append(line)
        prev = line
    return out, pos


def _png_row_samples(line, count, depth):
    if depth == 8:
        return list(line[:count])
    if depth == 16:
        return [(line[2 * i] << 8) | line[2 * i + 1] for i in range(count)]
    per = 8 // depth
    mask = (1 << depth) - 1
    res = []
    for i in range(count):
        byte = line[i // per]
        shift = 8 - depth * (i % per + 1)
        res.append((byte >> shift) & mask)
    return res


def png_decode(data):
    if data[:8] != PNG_SIG:
        raise ConformError("not a PNG")
    pos = 8
    ihdr = None
    plte = None
    trns = None
    grab = None
    idat = []
    while pos + 8 <= len(data):
        length, ctype = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8: pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body[:13])
        elif ctype == b"PLTE":
            plte = body
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"grAb" and len(body) >= 8:
            grab = struct.unpack(">ii", body[:8])
        elif ctype == b"IDAT":
            idat.append(body)
        elif ctype == b"IEND":
            break
    if not ihdr:
        raise ConformError("PNG has no IHDR chunk")

    w, h, depth, ctyp, _comp, _filt, interlace = ihdr
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctyp)
    if channels is None or depth not in (1, 2, 4, 8, 16) or w == 0 or h == 0:
        raise ConformError("PNG uses an unsupported format")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as e:
        raise ConformError(f"PNG data is corrupt ({e})")

    maxv = (1 << depth) - 1

    def scale(v):
        if depth == 16:
            return v >> 8
        if depth == 8:
            return v
        return v * 255 // maxv

    pal = []
    if plte:
        pal = [tuple(plte[i:i + 3]) for i in range(0, len(plte) - 2, 3)]
    pal_alpha = list(trns) if (ctyp == 3 and trns) else []
    key_gray = struct.unpack(">H", trns[:2])[0] if (ctyp == 0 and trns and len(trns) >= 2) else None
    key_rgb = struct.unpack(">HHH", trns[:6]) if (ctyp == 2 and trns and len(trns) >= 6) else None

    bits_pp = channels * depth
    bpp = max(1, bits_pp // 8)
    pixels = [(0, 0, 0, 0)] * (w * h)

    if interlace:
        passes = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                  (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
    else:
        passes = ((0, 0, 1, 1),)

    rpos = 0
    for xs, ys, xstep, ystep in passes:
        pw = (w - xs + xstep - 1) // xstep
        ph = (h - ys + ystep - 1) // ystep
        if pw <= 0 or ph <= 0:
            continue
        rowbytes = (pw * bits_pp + 7) // 8
        rows, rpos = _png_unfilter(raw, rpos, rowbytes, ph, bpp)
        for ry, line in enumerate(rows):
            y = ys + ry * ystep
            s = _png_row_samples(line, pw * channels, depth)
            for rx in range(pw):
                x = xs + rx * xstep
                k = rx * channels
                if ctyp == 0:
                    v = s[k]
                    g = scale(v)
                    px = (g, g, g, 0 if v == key_gray else 255)
                elif ctyp == 2:
                    rv, gv, bv = s[k], s[k + 1], s[k + 2]
                    a = 0 if key_rgb == (rv, gv, bv) else 255
                    px = (scale(rv), scale(gv), scale(bv), a)
                elif ctyp == 3:
                    idx = s[k]
                    r, g, b = pal[idx] if idx < len(pal) else (0, 0, 0)
                    a = pal_alpha[idx] if idx < len(pal_alpha) else 255
                    px = (r, g, b, a)
                elif ctyp == 4:
                    g = scale(s[k])
                    px = (g, g, g, scale(s[k + 1]))
                else:
                    px = (scale(s[k]), scale(s[k + 1]), scale(s[k + 2]),
                          scale(s[k + 3]))
                pixels[y * w + x] = px
    return w, h, pixels, grab


# ------------------------------------------------------------------------------
# Palette sources
#   Every loader returns a list of 768-byte palettes (at least one).
# ------------------------------------------------------------------------------
def _split_palettes(blob, label):
    n = len(blob) // 768
    if n < 1:
        raise ConformError(f"{label}: palette data is shorter than 768 bytes")
    return [bytes(blob[i * 768:(i + 1) * 768]) for i in range(n)]


def _palettes_from_png(data, label):
    w, h, px, _ = png_decode(data)

    def row(y):
        return bytes(c for x in range(256) for c in px[y * w + x][:3])

    if w == 256:
        # DoomTools layout: one palette per row. 14 rows = a full PLAYPAL;
        # any other height is treated as a colourmap image (row 0 only).
        if h == 14:
            return [row(y) for y in range(14)]
        return [row(0)]
    if w == h and w % 16 == 0:
        # SLADE layout: 16x16 grid of swatches, sampled at each cell centre.
        cell = w // 16
        out = bytearray()
        for i in range(256):
            cx = (i % 16) * cell + cell // 2
            cy = (i // 16) * cell + cell // 2
            out += bytes(px[cy * w + cx][:3])
        return [bytes(out)]
    raise ConformError(
        f"{label}: unrecognised palette image layout ({w}x{h}). Expected a "
        f"256-wide image (one palette per row) or a square 16x16-swatch grid.")


def _palettes_from_text(text, label):
    lines = [ln.strip() for ln in text.splitlines()]
    rgb = bytearray()
    if lines and lines[0].upper().startswith("JASC-PAL"):
        for ln in lines[3:]:
            parts = ln.split()
            if len(parts) >= 3:
                rgb += bytes(max(0, min(255, int(p))) for p in parts[:3])
    else:  # GIMP .gpl
        for ln in lines[1:]:
            if not ln or ln.startswith("#") or ":" in ln.split()[0]:
                continue
            parts = ln.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                rgb += bytes(max(0, min(255, int(p))) for p in parts[:3])
    return _split_palettes(rgb, label)


def load_palette_file(path):
    label = path
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ConformError(f"cannot read palette source {path}: {e}")

    if data[0:4] in (b"IWAD", b"PWAD"):
        _, entries = wad_parse(data, label)
        lump = wad_last_lump(entries, "PLAYPAL")
        if not lump:
            raise ConformError(f"{label} has no PLAYPAL lump")
        return _split_palettes(lump, label)

    if data[:8] == PNG_SIG:
        return _palettes_from_png(data, label)

    if data[0:4] == b"RIFF" and data[8:12] == b"PAL ":
        p = 12
        while p + 8 <= len(data):
            cid, clen = struct.unpack_from("<4sI", data, p)
            if cid == b"data":
                count = struct.unpack_from("<H", data, p + 10)[0]
                rgb = bytearray()
                for i in range(count):
                    q = p + 12 + i * 4
                    rgb += data[q:q + 3]
                return _split_palettes(rgb, label)
            p += 8 + clen + (clen & 1)
        raise ConformError(f"{label}: RIFF palette has no data chunk")

    head = data[:16].lstrip(b"\xef\xbb\xbf")
    if head.upper().startswith(b"JASC-PAL") or head.startswith(b"GIMP Palette"):
        return _palettes_from_text(data.decode("utf-8-sig", "replace"), label)

    if len(data) >= 768 and len(data) % 768 == 0:
        return _split_palettes(data, label)

    raise ConformError(
        f"{label}: unrecognised palette format. Supported: WAD with PLAYPAL, "
        f"raw PLAYPAL lump, palette PNG (DoomTools/SLADE/colourmap), "
        f".pal (raw, JASC or RIFF), GIMP .gpl")


def generate_playpal(pal0):
    """Build a standard 14-palette PLAYPAL from palette 0, using the classic
    Doom tints: 8 red (pain), 4 gold (bonus), 1 green (radsuit)."""
    base = [pal0[i:i + 3] for i in range(0, 768, 3)]

    def blend(target, f):
        out = bytearray()
        for c in base:
            for ch in range(3):
                v = c[ch] + (target[ch] - c[ch]) * f
                out.append(max(0, min(255, int(round(v)))))
        return bytes(out)

    pals = [bytes(pal0)]
    for i in range(1, 9):
        pals.append(blend((255, 0, 0), i / 9.0))
    for i in range(1, 5):
        pals.append(blend((215, 186, 69), i / 8.0))
    pals.append(blend((0, 255, 0), 1 / 8.0))
    return pals


def build_playpal(pals):
    """Full 14-palette lump: use all 14 if supplied, else generate from pal0."""
    if len(pals) >= 14:
        return b"".join(pals[:14]), False
    return b"".join(generate_playpal(pals[0])), True


# ------------------------------------------------------------------------------
# Colour matching
# ------------------------------------------------------------------------------
class PaletteMatcher:
    """Nearest-colour matcher against a target palette (weighted 'redmean'
    RGB). Exact match: lowest exact index. Otherwise the lowest index within
    MATCH_TIE_TOL of the best distance (coin-flips go to the earlier index)."""

    def __init__(self, pal0):
        self.pal = [tuple(pal0[i:i + 3]) for i in range(0, 768, 3)]
        self.cache = {}

    def nearest(self, r, g, b):
        key = (r << 16) | (g << 8) | b
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        dists = []
        for pr, pg, pb in self.pal:
            rm = (r + pr) >> 1
            dr, dg, db = r - pr, g - pg, b - pb
            dists.append((((512 + rm) * dr * dr) >> 8) + 4 * dg * dg
                         + (((767 - rm) * db * db) >> 8))
        best = min(dists)
        limit = best if best == 0 else best + MATCH_TIE_TOL
        for i, d in enumerate(dists):
            if d <= limit:
                self.cache[key] = i
                return i
        return 0  # unreachable

    def index_table(self, src_pal0):
        return bytes(self.nearest(src_pal0[i], src_pal0[i + 1], src_pal0[i + 2])
                     for i in range(0, 768, 3))


# ------------------------------------------------------------------------------
# Graphic formats
# ------------------------------------------------------------------------------
def remap_picture(data, table):
    """Validate a Doom picture and remap its pixel bytes through table.
    Returns new bytes, or None if the data is not a valid Doom picture.
    Header, offsets and post structure are untouched; shared posts are
    only remapped once."""
    n = len(data)
    if n < 8:
        return None
    w, h = struct.unpack_from("<hh", data, 0)
    if w <= 0 or h <= 0 or w > 4096 or h > 4096:
        return None
    colstart = 8 + 4 * w
    if colstart > n:
        return None
    offs = struct.unpack_from(f"<{w}I", data, 8)
    out = bytearray(data)
    done = bytearray(n)
    for off in offs:
        if off < colstart or off >= n:
            return None
        p = off
        posts = 0
        while True:
            if p >= n:
                return None
            if data[p] == 0xFF:
                break
            if p + 1 >= n:
                return None
            ln = data[p + 1]
            end = p + 4 + ln
            if end > n:
                return None
            for q in range(p + 2, end):   # pad, pixels, pad
                if not done[q]:
                    out[q] = table[data[q]]
                    done[q] = 1
            p = end
            posts += 1
            if posts > 4096:
                return None
    return bytes(out)


def encode_picture(w, h, idx, opaque, left, top):
    """Encode indexed pixels + opacity mask as a Doom picture. Images taller
    than 254 use DeePsea-style relative topdeltas (bridging empty posts as
    needed), as supported by Boom-derived ports."""
    cols = []
    for x in range(w):
        col = bytearray()
        lasttop = -1
        y = 0
        while y < h:
            if not opaque[y * w + x]:
                y += 1
                continue
            start = y
            run = bytearray()
            while y < h and opaque[y * w + x] and len(run) < 254:
                run.append(idx[y * w + x])
                y += 1
            while True:
                if start > lasttop and start <= 254:
                    delta = start
                elif lasttop >= 254 and start - lasttop <= min(lasttop, 254):
                    delta = start - lasttop
                elif lasttop < 254:
                    col += bytes((254, 0, 0, 0))   # bridge to absolute 254
                    lasttop = 254
                    continue
                else:
                    step = min(lasttop, 254)
                    col += bytes((step, 0, 0, 0))  # relative bridge
                    lasttop += step
                    continue
                col += bytes((delta, len(run), run[0])) + run + bytes((run[-1],))
                lasttop = start
                break
        col.append(0xFF)
        cols.append(bytes(col))

    left = max(-32768, min(32767, left))
    top = max(-32768, min(32767, top))
    head = bytearray(struct.pack("<hhhh", w, h, left, top))
    off = 8 + 4 * w
    for c in cols:
        head += struct.pack("<I", off)
        off += len(c)
    return bytes(head) + b"".join(cols)


def png_to_doom(data, matcher, as_flat):
    """Convert PNG lump data to a raw flat or a Doom picture."""
    w, h, px, grab = png_decode(data)
    idx = bytearray(w * h)
    opaque = [True] * (w * h)
    for i, (r, g, b, a) in enumerate(px):
        if not as_flat and a <= BAYER_T[(i // w) & 3][(i % w) & 3]:
            opaque[i] = False
            continue
        idx[i] = matcher.nearest(r, g, b)
    if as_flat:
        return bytes(idx)
    if w > 4096 or h > 4096:
        raise ConformError(f"PNG is too large for a Doom picture ({w}x{h})")
    left, top = grab if grab else (0, 0)
    return encode_picture(w, h, idx, opaque, left, top)


# ------------------------------------------------------------------------------
# Lump classification
# ------------------------------------------------------------------------------
_NS_START = {}
_NS_END = {}
for _fam, _starts, _ends in (
        ("sprite",   ("S_START", "SS_START"), ("S_END", "SS_END")),
        ("patch",    ("P_START", "PP_START", "P1_START", "P2_START", "P3_START"),
                     ("P_END", "PP_END", "P1_END", "P2_END", "P3_END")),
        ("flat",     ("F_START", "FF_START", "F1_START", "F2_START", "F3_START"),
                     ("F_END", "FF_END", "F1_END", "F2_END", "F3_END")),
        ("texture",  ("TX_START",), ("TX_END",)),
        ("hires",    ("HI_START",), ("HI_END",)),
        ("colormap", ("C_START",), ("C_END",)),
        ("skip",     ("A_START", "V_START", "VX_START", "DS_START"),
                     ("A_END", "V_END", "VX_END", "DS_END"))):
    for _n in _starts:
        _NS_START[_n] = _fam
    for _n in _ends:
        _NS_END[_n] = _fam

GRAPHIC_NAMESPACES = ("sprite", "patch", "texture", "hires")

NON_GRAPHIC_NAMES = {
    "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS", "NODES",
    "SECTORS", "REJECT", "BLOCKMAP", "BEHAVIOR", "SCRIPTS", "TEXTMAP",
    "ZNODES", "DIALOGUE", "ENDMAP", "LEAFS", "LIGHTS", "MACROS",
    "PLAYPAL", "COLORMAP", "ENDOOM", "ENDTEXT", "ENDBOOM", "ENDSTRF",
    "GENMIDI", "DMXGUS", "DMXGUSC", "TEXTURE1", "TEXTURE2", "TEXTURES",
    "PNAMES", "ANIMATED", "SWITCHES", "DEHACKED", "DECOHACK", "MAPINFO",
    "UMAPINFO", "ZMAPINFO", "EMAPINFO", "DECORATE", "ZSCRIPT", "SNDINFO",
    "SNDSEQ", "LANGUAGE", "GAMEINFO", "KEYCONF", "CREDITS", "WADINFO",
    "COMPLVL", "OPTIONS", "SBARDEF", "SKYDEFS", "TRAKINFO", "TRANMAP",
    "WATERMAP", "FOGMAP", "TINTTAB", "LOCKDEFS", "TERRAIN", "ANIMDEFS",
    "GLDEFS", "MODELDEF", "FONTDEFS", "ALTHUDCF", "SNDCURVE", "X11R6RGB",
    "DEMOLOOP", "MUSINFO", "GAMECONF", "MENUDEF", "CVARINFO", "__VER__",
}
NON_GRAPHIC_PREFIXES = ("DEMO", "GL_", "D_", "XLAT")
_MAP_MARKER = re.compile(r"^(MAP\d\d|E\dM\d)$")


def _is_text(data):
    if b"\x00" in data:
        return False
    return all(b in (9, 10, 13) or 32 <= b <= 126 or b >= 128 for b in data)


def _is_known_non_graphic(name, data):
    if name in NON_GRAPHIC_NAMES or _MAP_MARKER.match(name):
        return True
    if name.startswith(NON_GRAPHIC_PREFIXES):
        return True
    for magic in (b"MUS\x1a", b"MThd", b"RIFF", b"OggS", b"fLaC", b"ID3",
                  b"IMPM", b"PK\x03\x04", b"IWAD", b"PWAD"):
        if data.startswith(magic):
            return True
    if data[:15] == b"Extended Module":
        return True
    if len(data) >= 8:   # DMX digital sound: format 3 + sample count
        fmt = struct.unpack_from("<H", data, 0)[0]
        samples = struct.unpack_from("<I", data, 4)[0]
        if fmt == 3 and 8 + samples <= len(data) + 32:
            return True
    return _is_text(data)


FLAT_SIZES = (4096, 8192, 16384, 65536)


# ------------------------------------------------------------------------------
# Project helpers (disabled in the standalone build)
# ------------------------------------------------------------------------------
def is_project_root():
    return False


def project_iwad_candidates():
    return []


def find_project_palette():
    return None, None


# ------------------------------------------------------------------------------
# The conversion pass
# ------------------------------------------------------------------------------
def conform_entries(entries, matcher, table, playpal):
    stats = {"picture": 0, "flat": 0, "png-picture": 0, "png-flat": 0,
             "playpal": 0, "copied": 0, "playpal_added": False}
    warnings = []
    stack = []
    out = []

    for e in entries:
        name, data = e["name"], e["data"]
        new = dict(e)

        if name in _NS_START:
            stack.append(_NS_START[name])
            out.append(new)
            stats["copied"] += 1
            continue
        if name in _NS_END:
            fam = _NS_END[name]
            if fam in stack:
                while stack and stack.pop() != fam:
                    pass
            out.append(new)
            stats["copied"] += 1
            continue

        ns = stack[-1] if stack else None
        result = None
        kind = None

        try:
            if name == "PLAYPAL":
                result, kind = playpal, "playpal"
            elif not data or ns in ("colormap", "skip"):
                pass
            elif ns == "flat":
                if data[:8] == PNG_SIG:
                    result, kind = png_to_doom(data, matcher, True), "png-flat"
                elif len(data) not in FLAT_SIZES and remap_picture(data, table):
                    result, kind = remap_picture(data, table), "picture"
                else:
                    result, kind = data.translate(table), "flat"
            elif data[:8] == PNG_SIG:
                result, kind = png_to_doom(data, matcher, False), "png-picture"
            elif ns in GRAPHIC_NAMESPACES:
                pic = remap_picture(data, table)
                if pic is not None:
                    result, kind = pic, "picture"
                else:
                    warnings.append(f"{name}: in a graphics namespace but not a "
                                    f"recognisable graphic - copied unchanged")
            elif not _is_known_non_graphic(name, data):
                pic = remap_picture(data, table)
                if pic is not None:
                    result, kind = pic, "picture"
        except ConformError as ex:
            warnings.append(f"{name}: {ex} - copied unchanged")
            result, kind = None, None

        if result is not None:
            new["data"] = result
            stats[kind] += 1
        else:
            stats["copied"] += 1
        out.append(new)

    if stats["playpal"] == 0:
        # Input had no PLAYPAL: give the output the target palette as its
        # first lump, so it is self-describing.
        out.insert(0, {"raw": b"PLAYPAL\x00", "name": "PLAYPAL", "off": 0,
                       "size": len(playpal), "data": playpal})
        stats["playpal"] = 1
        stats["playpal_added"] = True

    return out, stats, warnings


# ------------------------------------------------------------------------------
# Palette resolution
# ------------------------------------------------------------------------------
def _iwad_lookup(key):
    for k, p in IWADS.items():
        if k.lower() == key.lower():
            return p
    return None


def resolve_pal_arg(value):
    """-pal value: an existing file is used as a palette source; anything
    else is looked up as an IWAD alias. Returns (palettes, label)."""
    if os.path.isfile(value):
        return load_palette_file(value), value
    path = _iwad_lookup(value)
    if not path:
        raise ConformError(f"-pal '{value}' is neither a file nor an IWAD alias. "
                           f"Aliases: {IWAD_LIST}")
    if not os.path.isfile(path):
        raise ConformError(f"IWAD not found: {path}")
    return load_palette_file(path), f"{path} (IWAD: {value})"


def resolve_fallback_iwad(project):
    """The IWAD whose palette is the fallback (target when nothing else is
    found, and source for input WADs with no PLAYPAL). Project mode:
    doom-loader.conf, doommake.properties, then doom2. Otherwise doom2."""
    if project:
        for p, src in project_iwad_candidates():
            if os.path.isfile(p):
                return p, src
    path = _iwad_lookup(CONFORM_DEFAULT_IWAD)
    if not path:
        raise ConformError(f"default IWAD '{CONFORM_DEFAULT_IWAD}' is not defined "
                           f"in the iwads list")
    if not os.path.isfile(path):
        raise ConformError(f"IWAD not found: {path}")
    return path, CONFORM_DEFAULT_IWAD


class ConformContext:
    """Target palette + shared matcher for one run (single file or batch)."""

    def __init__(self, pal_arg, project):
        self.project = project
        self._iwad = None
        pals = None
        if pal_arg:
            pals, self.pal_label = resolve_pal_arg(pal_arg)
        elif project:
            path, pals = find_project_palette()
            if pals:
                self.pal_label = f"{path} (project)"
        if pals is None:
            path, src = resolve_fallback_iwad(project)
            pals = load_palette_file(path)
            self.pal_label = f"{path} (IWAD: {src})"
        self.playpal, self.generated = build_playpal(pals)
        self.tgt_pal0 = self.playpal[:768]
        self.matcher = PaletteMatcher(self.tgt_pal0)

    def iwad_pal0(self):
        if self._iwad is None:
            path, src = resolve_fallback_iwad(self.project)
            pals = load_palette_file(path)
            self._iwad = (pals[0], f"IWAD palette ({src})")
        return self._iwad

    def load_input(self, path):
        """Read a WAD and work out its source palette. Returns
        (magic, entries, src_pal0, src_label)."""
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            raise ConformError(f"cannot read {path}: {e}")
        magic, entries = wad_parse(data, path)
        lump = wad_last_lump(entries, "PLAYPAL")
        if lump:
            if len(lump) < 768:
                raise ConformError(f"{path}: PLAYPAL is shorter than 768 bytes")
            return magic, entries, bytes(lump[:768]), "input PLAYPAL"
        pal0, label = self.iwad_pal0()
        return magic, entries, pal0, f"no PLAYPAL - read as {label}"

    def convert(self, magic, entries, src_pal0, out_path):
        table = self.matcher.index_table(src_pal0)
        new_entries, stats, warnings = conform_entries(entries, self.matcher,
                                                       table, self.playpal)
        write_wad_atomic(out_path, magic, new_entries)
        return new_entries, stats, warnings


def write_wad_atomic(out_path, magic, entries):
    """Write via a temp file in the output folder, then swap it into place,
    so a failure never damages an existing file."""
    out_dir = os.path.dirname(full_path(out_path))
    fd, tmp = tempfile.mkstemp(prefix=".conform_", suffix=".tmp", dir=out_dir)
    os.close(fd)
    try:
        wad_write(tmp, magic, entries)
        os.replace(tmp, out_path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ConformError(f"cannot write {out_path}: {e}")


def graphics_count(stats):
    return (stats["picture"] + stats["flat"] + stats["png-picture"]
            + stats["png-flat"])


# ------------------------------------------------------------------------------
# Mode entry
# ------------------------------------------------------------------------------
def invoke_conform_mode(rest):
    positionals = []
    in_arg = out_arg = pal_arg = None
    keep = replace = False

    i = 0
    while i < len(rest):
        a = rest[i]
        al = a.lower()
        if al in ("-h", "-help", "--help", "/?"):
            show_conform_help()
            sys.exit(0)
        if al in ("-pal", "-input", "-output"):
            if i + 1 >= len(rest):
                print(RED(f"Error: {a} requires a value"))
                sys.exit(2)
            v = rest[i + 1]
            if al == "-pal":
                pal_arg = v
            elif al == "-input":
                in_arg = v
            else:
                out_arg = v
            i += 2
        elif al == "-keep" and CONFORM_PROJECT_SUPPORT:
            keep = True
            i += 1
        elif al == "-replace":
            replace = True
            i += 1
        elif al.startswith("-") and len(al) > 1:
            opts = "-pal  -input  -output  " + ("-keep  " if CONFORM_PROJECT_SUPPORT else "") + "-replace  -h"
            print(RED(f"Error: unknown option '{a}'"))
            if al in ("-i", "-iwad"):
                print("-iwad was removed: use -pal <iwad alias> instead (e.g. -pal doom2)")
            print(f"Options: {opts}")
            sys.exit(2)
        else:
            positionals.append(a)
            i += 1

    if in_arg is None and positionals:
        in_arg = positionals.pop(0)
    if out_arg is None and positionals:
        out_arg = positionals.pop(0)
    if positionals:
        print(YEL(f"Note: ignoring extra argument(s): {' '.join(positionals)}"))

    try:
        project = is_project_root() if CONFORM_PROJECT_SUPPORT else False
        keep, replace = _conform_switch_notes(project, keep, replace)
        if in_arg:
            _run_conform_single(project, in_arg, out_arg, pal_arg, keep, replace)
        else:
            if out_arg:
                raise ConformError("an output name needs an input WAD")
            _run_conform_batch(project, pal_arg, keep, replace)
    except ConformError as e:
        print(RED(f"Error: {e}"))
        sys.exit(2)
    except KeyboardInterrupt:
        print("")
        print(YEL("Cancelled."))
        sys.exit(130)
    sys.exit(0)


def _conform_switch_notes(project, keep, replace):
    if project and replace:
        print(YEL("Note: -replace has no effect in project mode (in-place is the default)."))
        replace = False
    if not project and keep:
        print(YEL("Note: -keep has no effect outside a project (a renamed copy is the default)."))
        keep = False
    return keep, replace


def _label(text):
    return GRY(f"  {text:<9}: ")


def _print_header(title, ctx, rows):
    print(WHT(f"{CONFORM_TOOL} - {title}"))
    for k, v in rows:
        print(_label(k) + CYN(v))
    print(_label("Palette") + CYN(ctx.pal_label))
    if ctx.generated:
        print(" " * 13 + DGRY("(single palette - tints 1-13 generated)"))
    print("")


# ------------------------------------------------------------------------------
# Single WAD
# ------------------------------------------------------------------------------
def _run_conform_single(project, in_arg, out_arg, pal_arg, keep, replace):
    if out_arg and (keep or replace):
        raise ConformError(f"{'-keep' if keep else '-replace'} cannot be combined "
                           f"with an explicit output name")

    # ---- Input ----------------------------------------------------------------
    def candidates(p):
        yield p
        if not os.path.splitext(p)[1]:
            yield p + ".wad"

    in_path = None
    for c in candidates(in_arg):
        if os.path.isfile(c):
            in_path = c
            break
    if not in_path and project:
        for d in CONFORM_INPUT_DIRS:
            for c in candidates(in_arg):
                p = os.path.join(d, c)
                if os.path.isfile(p):
                    in_path = p
                    break
            if in_path:
                break
    if not in_path:
        where = (" (also searched " + ", ".join(CONFORM_INPUT_DIRS) + ")") if project else ""
        raise ConformError(f"input WAD not found: {in_arg}{where}")

    # ---- Output ---------------------------------------------------------------
    stem = os.path.splitext(os.path.basename(in_path))[0]
    make_out_dir = False
    if out_arg:
        if os.path.dirname(out_arg) or not project:
            out_path = out_arg
        else:
            out_path = os.path.join(CONFORM_OUTPUT_DIR, out_arg)
            make_out_dir = True
    elif project:
        name = f"{stem}{CONFORM_SUFFIX}.wad" if keep else os.path.basename(in_path)
        out_path = os.path.join(CONFORM_OUTPUT_DIR, name)
        make_out_dir = True
    elif replace:
        out_path = in_path
    else:
        out_path = os.path.join(os.path.dirname(in_path), f"{stem}{CONFORM_SUFFIX}.wad")

    out_dir = os.path.dirname(full_path(out_path))
    if not os.path.isdir(out_dir):
        if make_out_dir:
            os.makedirs(out_dir, exist_ok=True)
        else:
            raise ConformError(f"output folder does not exist: {out_dir}")
    in_place = full_path(in_path).lower() == full_path(out_path).lower()

    # ---- Convert --------------------------------------------------------------
    ctx = ConformContext(pal_arg, project)
    magic, entries, src_pal0, src_label = ctx.load_input(in_path)

    _print_header("repalette WAD graphics", ctx, [
        ("Mode", "DoomTools project" if project else "folder"),
        ("Input", in_path),
        ("Source", src_label),
        ("Output", out_path + ("  (in place)" if in_place else "")),
    ])

    if src_pal0 == ctx.tgt_pal0:
        print(DGRY("Nothing to do: the input's palette already matches the target palette."))
        return

    new_entries, stats, warnings = ctx.convert(magic, entries, src_pal0, out_path)

    for w in warnings:
        print(YEL(f"  Warning: {w}"))
    if warnings:
        print("")
    print(f"  Doom pictures remapped : {stats['picture']}")
    print(f"  Flats remapped         : {stats['flat']}")
    print(f"  PNG -> Doom picture    : {stats['png-picture']}")
    print(f"  PNG -> flat            : {stats['png-flat']}")
    print(f"  PLAYPAL                : {'added' if stats['playpal_added'] else 'replaced'}")
    print(f"  Copied unchanged       : {stats['copied']}")
    print("")
    print(GRN(f"Wrote {len(new_entries)} lump(s) -> {out_path}"))


# ------------------------------------------------------------------------------
# Batch: every WAD in src/wads/textures (project) or the current folder
# ------------------------------------------------------------------------------
def _ask_convert():
    prompt = ("        Convert?  " + YEL("[y]") + "es  " + YEL("[n]") + "o  "
              + YEL("[a]") + "ll  " + YEL("[s]") + "kip all : ")
    while True:
        try:
            ans = input(prompt).strip().lower()
        except EOFError:
            print("")
            return "s"
        if ans[:1] in ("y", "n", "a", "s"):
            return ans[:1]


def _run_conform_batch(project, pal_arg, keep, replace):
    folder = CONFORM_OUTPUT_DIR if project else "."
    if not os.path.isdir(folder):
        raise ConformError(f"folder not found: {folder}")
    names = sorted((f for f in os.listdir(folder)
                    if f.lower().endswith(".wad")
                    and os.path.isfile(os.path.join(folder, f))), key=str.lower)

    ctx = ConformContext(pal_arg, project)
    if project:
        mode = f"DoomTools project  ({folder})"
        output = f"<name>{CONFORM_SUFFIX}.wad" if keep else "overwrite in place"
    else:
        mode = f"folder  ({full_path(folder)})"
        output = "overwrite in place" if replace else f"<name>{CONFORM_SUFFIX}.wad"
    _print_header("batch", ctx, [("Mode", mode), ("Output", output)])

    if not names:
        print(DGRY(f"  No WAD files found in {folder}"))
        return

    plan, already, previous, failed = [], [], [], []
    for n in names:
        p = os.path.join(folder, n)
        stem = os.path.splitext(n)[0]
        if not project and stem.lower().endswith(CONFORM_SUFFIX.lower()):
            previous.append(n)
            continue
        try:
            _m, _e, src_pal0, _l = ctx.load_input(p)
        except ConformError as e:
            failed.append((n, str(e)))
            continue
        if src_pal0 == ctx.tgt_pal0:
            already.append(n)
            continue
        if project:
            out = os.path.join(folder, f"{stem}{CONFORM_SUFFIX}.wad") if keep else p
        else:
            out = p if replace else os.path.join(folder, f"{stem}{CONFORM_SUFFIX}.wad")
        plan.append((n, p, out))

    parts = [f"{len(plan)} to convert"]
    if already:
        parts.append(f"{len(already)} already conformed")
    if previous:
        parts.append(f"{len(previous)} skipped")
    if failed:
        parts.append(f"{len(failed)} unreadable")
    print("  " + WHT(f"Found {len(names)} WAD(s): ") + ", ".join(parts))
    width = max(len(n) for n in names)
    for n in already:
        print(DGRY(f"    = {n:<{width}}  already conformed"))
    for n in previous:
        print(DGRY(f"    - {n:<{width}}  previous output"))
    for n, err in failed:
        print(RED(f"    x {n:<{width}}  {err}"))
    print("")

    converted = skipped = 0
    errors = len(failed)
    mode_all = mode_skip = False
    total = len(plan)
    for k, (n, p, out) in enumerate(plan, 1):
        dest = "in place" if full_path(out).lower() == full_path(p).lower() \
            else os.path.basename(out)
        print("  " + DCYN(f"[{k}/{total}] ") + WHT(f"{n:<{width}}") + GRY(f"  -> {dest}"))
        if mode_skip:
            print(DGRY("        - skipped"))
            skipped += 1
            continue
        if not mode_all:
            ans = _ask_convert()
            if ans == "n":
                print(DGRY("        - skipped"))
                skipped += 1
                continue
            if ans == "s":
                mode_skip = True
                print(DGRY("        - skipped"))
                skipped += 1
                continue
            if ans == "a":
                mode_all = True
        try:
            magic, entries, src_pal0, _l = ctx.load_input(p)
            _ne, stats, warnings = ctx.convert(magic, entries, src_pal0, out)
            for w in warnings:
                print(YEL(f"        ! {w}"))
            extra = ", PLAYPAL added" if stats["playpal_added"] else ""
            print(GRN(f"        + {graphics_count(stats)} graphics converted{extra}"))
            converted += 1
        except ConformError as e:
            print(RED(f"        x {e}"))
            errors += 1

    print("")
    print(DGRY("  " + "-" * 48))
    fail_txt = f"Failed {errors}"
    print("  " + GRN(f"Converted {converted}") + "   " + GRY(f"Skipped {skipped}")
          + "   " + GRY(f"Already conformed {len(already)}") + "   "
          + (RED(fail_txt) if errors else GRY(fail_txt)))


# ==============================================================================
# Help
# ==============================================================================
def show_conform_help():
    t = CONFORM_TOOL
    print("")
    print(DCYN("=============================================================================="))
    print(WHT(f"  {t.upper()}  -  repalette every graphic in a WAD"))
    print(DCYN("=============================================================================="))
    print("")
    print("  Converts every graphic in a WAD to a new palette and writes a classic-")
    print("  format copy. Doom pictures, flats, palettised PNGs and truecolour PNGs")
    print("  all come out as standard Doom pictures (or raw flats in a flat")
    print("  namespace). PLAYPAL is replaced with (or given) the target's 14")
    print("  palettes. Every other lump (colormaps, TEXTUREx, ENDOOM, sounds,")
    print("  maps...) is copied byte-for-byte. Names, order and markers never change.")
    print("")

    print(WHT("USAGE"))
    keep = " | -keep" if CONFORM_PROJECT_SUPPORT else ""
    print(GRY(f"  {t} input.wad [output.wad] [-pal palette] [-replace{keep}]"))
    print(GRY(f"  {t} [-pal palette] [-replace{keep}]") + DGRY("      (batch)"))
    print("")

    print(WHT("OPTIONS"))
    print(YEL("  -pal x         ") + "Target palette: an IWAD alias, or a palette file:")
    print("                 " + GRY("IWAD aliases: ") + DGRY(IWAD_LIST))
    print("                 " + "WAD with PLAYPAL, raw PLAYPAL lump, DoomTools palette")
    print("                 " + "PNG (256 wide, one palette per row), SLADE pal0.png")
    print("                 " + "(16x16 grid), colourmap PNG (row 0), .pal (raw, JASC")
    print("                 " + "or RIFF; one or many palettes), GIMP .gpl")
    print(YEL("  -input / -output ") + "Explicit alternatives to the positional names")
    if CONFORM_PROJECT_SUPPORT:
        print(YEL("  -keep          ") + f"Project mode only: write <name>{CONFORM_SUFFIX}.wad")
        print(YEL("  -replace       ") + "Outside a project only: overwrite the input WAD")
    else:
        print(YEL("  -replace       ") + f"Overwrite the input instead of writing <name>{CONFORM_SUFFIX}.wad")
    print(YEL("  -h, --help     ") + "Show this help")
    print("")

    print(WHT("BATCH MODE  (no input WAD)"))
    where = "src/wads/textures (project) or the current folder" if CONFORM_PROJECT_SUPPORT \
        else "the current folder"
    print(GRY(f"  Every .wad in {where} is offered"))
    print(GRY("  in turn:  ") + YEL("[y]") + GRY("es  ") + YEL("[n]") + GRY("o  ")
          + YEL("[a]") + GRY("ll (no more prompts)  ") + YEL("[s]") + GRY("kip all"))
    print(GRY(f"  WADs already in the target palette and earlier *{CONFORM_SUFFIX}.wad"))
    print(GRY("  outputs are listed but not offered."))
    print("")

    if CONFORM_PROJECT_SUPPORT:
        print(WHT("OUTSIDE A DOOMTOOLS PROJECT"))
    else:
        print(WHT("DEFAULTS"))
    print(GRY(f"  Output  : <name>{CONFORM_SUFFIX}.wad next to the input (-replace: overwrite)"))
    print(GRY(f"  Palette : -pal, else {CONFORM_DEFAULT_IWAD}"))
    print("")

    if CONFORM_PROJECT_SUPPORT:
        print(WHT("INSIDE A DOOMTOOLS PROJECT ROOT"))
        print(GRY("  Input   : as given, else searched in src/wads/textures, then build"))
        print(GRY(f"  Output  : overwrite in place in src/wads/textures (-keep: <name>{CONFORM_SUFFIX}.wad)"))
        print(GRY("            A bare output filename is also placed in src/wads/textures."))
        print(GRY("  Palette : -pal, else the first found in src/assets/palettes,"))
        print(GRY("            build/convert/palettes, src/convert/palettes,"))
        print(GRY("            else the project IWAD"))
        print(GRY(f"  IWAD    : doom-loader.conf, doommake.properties, else {CONFORM_DEFAULT_IWAD}"))
        print("")

    print(WHT("NOTES"))
    print(GRY("  - Source palette: the input's own PLAYPAL; a WAD without one is read"))
    fb = "the project IWAD palette (or doom2)" if CONFORM_PROJECT_SUPPORT else f"the {CONFORM_DEFAULT_IWAD} palette"
    print(GRY(f"    as {fb}."))
    print(GRY("  - A single-palette source gets the standard 13 tint palettes generated."))
    print(GRY("  - Nearest colour by weighted RGB; ties go to the lowest index."))
    print(GRY("  - PNG grAb offsets carry over; partial alpha is ordered-dithered."))
    print(GRY("  - Overwrites go via a temp file, so a failure never damages the input."))
    print(GRY("  - WAD files only (no PK3)."))
    print("")

    print(WHT("EXAMPLES"))
    print(GRY(f"  {t} res.wad -pal mypal.png   ") + DGRY(f"- -> res{CONFORM_SUFFIX}.wad"))
    print(GRY(f"  {t} res.wad -pal doom2       ") + DGRY("- convert to the doom2 palette"))
    print(GRY(f"  {t} res.wad new.wad -pal tnt ") + DGRY("- TNT palette, -> new.wad"))
    print(GRY(f"  {t}                          ") + DGRY("- batch: offer every WAD"))
    if CONFORM_PROJECT_SUPPORT:
        print(GRY(f"  {t} res.wad -keep            ") + DGRY(f"- (project) -> res{CONFORM_SUFFIX}.wad"))
    print("")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    try:
        invoke_conform_mode(sys.argv[1:])
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
