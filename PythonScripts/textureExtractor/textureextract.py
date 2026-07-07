#!/usr/bin/env python3
"""
textureextract.py — Extract textures and flats from a WAD as true-colour PNGs.

    textureextract wadname.wad -iwad iwadname.wad [--nofilter] [-o outdir]
                   [-map MAPNAME]

By default only textures and flats whose NAME is not already present in the
IWAD are written to disk and included in the definition files. This is meant
to pull out "new" content only, leaving stock IWAD resources behind.

    --nofilter        also extract/write everything already found in the IWAD.
    -map MAPNAME      scope extraction to only what one map actually uses
                      (e.g. -map MAP01, -map E1M1), instead of every texture/
                      flat/switch/animation anywhere in the WAD. Reads the
                      map's SIDEDEFS+SECTORS (or TEXTMAP for UDMF maps) to
                      find which names it references. Combines with the
                      IWAD filter above rather than replacing it.

Output (default directory: ./<wad-stem>/):

    <wad-stem>/
        flats/          *.png   (true-colour, opaque)
        patches/        *.png   (true-colour RGBA; grAb chunk = patch offsets)
        texture1.txt            DoomTools/DEUTEX-style texture definitions
        texture2.txt             (only written if the PWAD has a TEXTURE2 lump)
        defswani.txt            DEFSWANI/SWANTBLS-style switch & anim defs
                                  (from the PWAD's ANIMATED/SWITCHES lumps)

Notes:
  * Texture/flat "already in the IWAD" is decided by NAME only, not by
    layout/pixel content — this is a stock-vs-new filter, not a diff tool.
  * defswani.txt filtering is name-based: a SWITCHES entry is dropped when
    BOTH its texture names exist in the IWAD; an ANIMATED entry is dropped
    when BOTH its first/last frame names exist in the IWAD (as textures or
    flats, matching the record type). Exact matches against an IWAD
    ANIMATED/SWITCHES lump (rare — vanilla IWADs don't ship one) are also
    dropped. If any referenced name is new, the entry is kept. --nofilter
    disables this. Separately, exact-duplicate lines within the PWAD's own
    ANIMATED/SWITCHES are always collapsed to one (first occurrence kept) —
    this is not affected by --nofilter.
  * A flat's width/height isn't stored in the WAD; it's inferred from the
    lump size (perfect square, or a handful of known non-square sizes, or a
    64-px-wide fallback). Anything undecidable is skipped with a warning.
  * texture1.txt/texture2.txt are sorted alphabetically by texture name
    (each texture's own patch list keeps its original order). defswani.txt
    is sorted numerically within each section — [SWITCHES] by episode,
    [FLATS]/[TEXTURES] by speed — so matching numbers end up grouped
    together.
  * With -map MAPNAME: a texture/flat is kept only if that map's own
    SIDEDEFS/SECTORS (or UDMF TEXTMAP) reference it — but used names are
    first EXPANDED to complete animation cycles and switch pairs, so if the
    map uses any frame of an animation (even a middle one), every frame of
    that cycle is extracted, and a used switch pulls both its off and on
    textures. Cycles are resolved from the PWAD's ANIMATED/SWITCHES lumps,
    the IWAD's (if present), and the vanilla hardcoded engine tables (which
    vanilla IWADs never store as lumps). defswani entries are kept when
    their cycle/pair intersects the expanded used set. Default output
    directory becomes <wad-stem>_<mapname>/ instead of <wad-stem>/.

Dependencies: none — Python 3 standard library only.
"""

import argparse
import datetime
import math
import os
import re
import struct
import sys
import zlib

WAD_HEADER = struct.Struct("<4sii")
WAD_DIR = struct.Struct("<ii8s")


def die(msg):
    print(f"textureextract: error: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"textureextract: warning: {msg}", file=sys.stderr)


def decode_name(raw):
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").upper()


class Texture:
    __slots__ = ("name", "width", "height", "patches", "lump")

    def __init__(self, name, width, height, patches, lump):
        self.name = name.upper()
        self.width = width
        self.height = height
        self.patches = tuple(patches)   # tuple of (patchname, x, y)
        self.lump = lump                # "TEXTURE1" or "TEXTURE2"


# ================================================================ WAD access

class Wad:
    """A parsed WAD: raw bytes + directory + name -> data lookup."""

    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        if self.data[:4] not in (b"IWAD", b"PWAD"):
            die(f"'{path}' is not a valid WAD file")
        signature, numlumps, dirofs = WAD_HEADER.unpack_from(self.data, 0)
        if numlumps < 0 or dirofs < 0 or dirofs + numlumps * WAD_DIR.size > len(self.data):
            die(f"'{path}': corrupt WAD directory")
        self.path = path
        self.entries = []   # (name, filepos, size) in on-disk order
        for i in range(numlumps):
            filepos, size, raw = WAD_DIR.unpack_from(self.data, dirofs + i * WAD_DIR.size)
            self.entries.append((decode_name(raw), filepos, size))

        # name -> data. Later entries win, matching normal WAD lookup rules.
        self.by_name = {}
        for name, filepos, size in self.entries:
            if size < 0 or filepos < 0 or filepos + size > len(self.data):
                continue
            self.by_name[name] = self.data[filepos:filepos + size]

    def get(self, name):
        return self.by_name.get(name)

    def flat_names(self):
        """Names of lumps between F_START/FF_START and F_END/FF_END markers,
        in first-seen order, skipping zero-size marker lumps."""
        names = []
        seen = set()
        in_flats = False
        for name, filepos, size in self.entries:
            if name in ("F_START", "FF_START"):
                in_flats = True
                continue
            if name in ("F_END", "FF_END"):
                in_flats = False
                continue
            if in_flats and size > 0 and name not in seen:
                seen.add(name)
                names.append(name)
        return names


# ================================================================ single-map scoping

# Lump names that belong to a map, in the order they follow the map marker
# lump (e.g. "MAP01" or "E1M1"). Used to find where one map's lumps end and
# either the next map or an unrelated lump begins.
MAP_LUMP_NAMES = {
    "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS", "NODES",
    "SECTORS", "REJECT", "BLOCKMAP", "BEHAVIOR", "SCRIPTS",
    "TEXTMAP", "ZNODES", "ENDMAP", "DIALOGUE", "LIGHTS", "MACROS",
    "GL_VERT", "GL_SEGS", "GL_SSECT", "GL_NODES", "GL_PVS",
}

SIDEDEF = struct.Struct("<hh8s8s8sh")
SECTOR = struct.Struct("<hh8s8shhh")


def find_map_lumps(wad, mapname):
    """Return {lumpname: data} for the named map, or None if not found."""
    mapname = mapname.upper()
    entries = wad.entries
    for i, (name, filepos, size) in enumerate(entries):
        if name != mapname:
            continue
        group = {}
        j = i + 1
        while j < len(entries) and entries[j][0] in MAP_LUMP_NAMES:
            lname, lfilepos, lsize = entries[j]
            if lfilepos >= 0 and lsize >= 0 and lfilepos + lsize <= len(wad.data):
                group[lname] = wad.data[lfilepos:lfilepos + lsize]
            j += 1
        return group
    return None


def parse_sidedefs(data):
    """Wall texture names (upper/lower/middle) used by a binary SIDEDEFS lump."""
    names = set()
    if not data:
        return names
    for i in range(len(data) // SIDEDEF.size):
        _, _, upper, lower, mid, _ = SIDEDEF.unpack_from(data, i * SIDEDEF.size)
        for raw in (upper, lower, mid):
            n = decode_name(raw)
            if n and n != "-":
                names.add(n)
    return names


def parse_sectors(data):
    """Floor/ceiling flat names used by a binary SECTORS lump."""
    names = set()
    if not data:
        return names
    for i in range(len(data) // SECTOR.size):
        _, _, floor, ceil, _, _, _ = SECTOR.unpack_from(data, i * SECTOR.size)
        names.add(decode_name(floor))
        names.add(decode_name(ceil))
    return names


def parse_udmf_names(textmap_data):
    """Wall/flat texture names referenced by a UDMF TEXTMAP lump (text format)."""
    tex, flats = set(), set()
    if not textmap_data:
        return tex, flats
    text = textmap_data.decode("ascii", "replace")
    for m in re.finditer(r'texture(?:top|bottom|middle)\s*=\s*"([^"]*)"', text, re.IGNORECASE):
        n = m.group(1).strip().upper()
        if n and n != "-":
            tex.add(n)
    for m in re.finditer(r'texture(?:floor|ceiling)\s*=\s*"([^"]*)"', text, re.IGNORECASE):
        n = m.group(1).strip().upper()
        if n:
            flats.add(n)
    return tex, flats


def map_used_names(wad, mapname):
    """Return (texture_names, flat_names) actually referenced by one map,
    or die() if the map can't be found."""
    group = find_map_lumps(wad, mapname)
    if group is None:
        die(f"map '{mapname}' not found in '{wad.path}'")
    if "TEXTMAP" in group:
        return parse_udmf_names(group.get("TEXTMAP"))
    return parse_sidedefs(group.get("SIDEDEFS")), parse_sectors(group.get("SECTORS"))


# ================================================================ PNAMES / TEXTUREx

def parse_pnames(wad):
    data = wad.get("PNAMES")
    if data is None:
        return []
    if len(data) < 4:
        die(f"'{wad.path}': PNAMES lump too small")
    count = struct.unpack_from("<i", data, 0)[0]
    if count < 0 or 4 + count * 8 > len(data):
        die(f"'{wad.path}': PNAMES count ({count}) does not fit lump size")
    return [decode_name(data[4 + i * 8: 4 + i * 8 + 8]) for i in range(count)]


def _try_texturex(data, pnames, doom_format):
    """Parse a binary TEXTUREx lump in one format (Doom or Strife).
    Returns (defs, exact_fits) or None if unparseable in this format."""
    hdr_size, patch_size = (22, 10) if doom_format else (18, 6)
    if len(data) < 4:
        return None
    count = struct.unpack_from("<i", data, 0)[0]
    if count < 0 or 4 + count * 4 > len(data):
        return None
    offsets = struct.unpack_from(f"<{count}i", data, 4)
    boundaries = sorted(set(offsets)) + [len(data)]
    out = []
    exact_fits = 0
    for off in offsets:
        if off < 0 or off + hdr_size > len(data):
            return None
        name = decode_name(data[off:off + 8])
        width, height = struct.unpack_from("<hh", data, off + 12)
        pc_off = off + 20 if doom_format else off + 16
        patchcount = struct.unpack_from("<h", data, pc_off)[0]
        if patchcount < 0 or patchcount > 4096:
            return None
        pbase = pc_off + 2
        end = pbase + patchcount * patch_size
        if end > len(data):
            return None
        nxt = next((b for b in boundaries if b > off), len(data))
        if end == nxt:
            exact_fits += 1
        patches = []
        for i in range(patchcount):
            po = pbase + i * patch_size
            ox, oy, pidx = struct.unpack_from("<hhh", data, po)
            if pidx < 0 or pidx >= len(pnames):
                return None
            patches.append((pnames[pidx], ox, oy))
        out.append((name, width, height, patches))
    return out, exact_fits


def parse_texturex_lump(wad, lumpname, pnames):
    data = wad.get(lumpname)
    if data is None:
        return []
    doom = _try_texturex(data, pnames, doom_format=True)
    strife = _try_texturex(data, pnames, doom_format=False)
    if doom is None and strife is None:
        die(f"'{wad.path}': {lumpname} is not a valid Doom or Strife TEXTUREx lump")
    if strife is not None and (doom is None or strife[1] > doom[1]):
        parsed = strife[0]
    else:
        parsed = doom[0]
    return [Texture(n, w, h, p, lumpname) for n, w, h, p in parsed]


def parse_textures(wad):
    pnames = parse_pnames(wad)
    return parse_texturex_lump(wad, "TEXTURE1", pnames), parse_texturex_lump(wad, "TEXTURE2", pnames)


# ================================================================ ANIMATED / SWITCHES

# The vanilla Doom/Doom2 animation and switch tables. These are HARDCODED in
# the engine (p_spec.c animdefs / p_switch.c alphSwitchList) — vanilla IWADs
# contain no ANIMATED/SWITCHES lump — so when expanding a map's used names to
# full animation cycles we must know them ourselves. Same content as Boom's
# SWANTBLS defaults. Records mirror parse_animated / parse_switches output.
VANILLA_ANIMATED = [
    # (istexture, last, first, speed)
    (0, "NUKAGE3", "NUKAGE1", 8), (0, "FWATER4", "FWATER1", 8),
    (0, "SWATER4", "SWATER1", 8), (0, "LAVA4", "LAVA1", 8),
    (0, "BLOOD3", "BLOOD1", 8), (0, "RROCK08", "RROCK05", 8),
    (0, "SLIME04", "SLIME01", 8), (0, "SLIME08", "SLIME05", 8),
    (0, "SLIME12", "SLIME09", 8),
    (1, "BLODGR4", "BLODGR1", 8), (1, "SLADRIP3", "SLADRIP1", 8),
    (1, "BLODRIP4", "BLODRIP1", 8), (1, "FIREWALL", "FIREWALA", 8),
    (1, "GSTFONT3", "GSTFONT1", 8), (1, "FIRELAVA", "FIRELAV3", 8),
    (1, "FIREMAG3", "FIREMAG1", 8), (1, "FIREBLU2", "FIREBLU1", 8),
    (1, "ROCKRED3", "ROCKRED1", 8), (1, "BFALL4", "BFALL1", 8),
    (1, "SFALL4", "SFALL1", 8), (1, "WFALL4", "WFALL1", 8),
    (1, "DBRAIN4", "DBRAIN1", 8),
]

VANILLA_SWITCHES = [
    # (off_texture, on_texture, episode)
    ("SW1BRCOM", "SW2BRCOM", 1), ("SW1BRN1", "SW2BRN1", 1),
    ("SW1BRN2", "SW2BRN2", 1), ("SW1BRNGN", "SW2BRNGN", 1),
    ("SW1BROWN", "SW2BROWN", 1), ("SW1COMM", "SW2COMM", 1),
    ("SW1COMP", "SW2COMP", 1), ("SW1DIRT", "SW2DIRT", 1),
    ("SW1EXIT", "SW2EXIT", 1), ("SW1GRAY", "SW2GRAY", 1),
    ("SW1GRAY1", "SW2GRAY1", 1), ("SW1METAL", "SW2METAL", 1),
    ("SW1PIPE", "SW2PIPE", 1), ("SW1SLAD", "SW2SLAD", 1),
    ("SW1STARG", "SW2STARG", 1), ("SW1STON1", "SW2STON1", 1),
    ("SW1STON2", "SW2STON2", 1), ("SW1STONE", "SW2STONE", 1),
    ("SW1STRTN", "SW2STRTN", 1),
    ("SW1BLUE", "SW2BLUE", 2), ("SW1CMT", "SW2CMT", 2),
    ("SW1GARG", "SW2GARG", 2), ("SW1GSTON", "SW2GSTON", 2),
    ("SW1HOT", "SW2HOT", 2), ("SW1LION", "SW2LION", 2),
    ("SW1SATYR", "SW2SATYR", 2), ("SW1SKIN", "SW2SKIN", 2),
    ("SW1VINE", "SW2VINE", 2), ("SW1WOOD", "SW2WOOD", 2),
    ("SW1PANEL", "SW2PANEL", 3), ("SW1ROCK", "SW2ROCK", 3),
    ("SW1MET2", "SW2MET2", 3), ("SW1WDMET", "SW2WDMET", 3),
    ("SW1BRIK", "SW2BRIK", 3), ("SW1MOD1", "SW2MOD1", 3),
    ("SW1ZIM", "SW2ZIM", 3), ("SW1STON6", "SW2STON6", 3),
    ("SW1TEK", "SW2TEK", 3), ("SW1MARB", "SW2MARB", 3),
    ("SW1SKULL", "SW2SKULL", 3),
]


def anim_frames(rec, flat_order, tex_order):
    """All frame names of one ANIMATED record, in cycle order.

    An animation's frames are defined POSITIONALLY: every flat lump (or
    TEXTUREx entry) between `first` and `last` inclusive, in directory/
    definition order — the WAD stores no explicit frame list. flat_order and
    tex_order are name lists in that order. Falls back to {first, last} if
    the endpoints can't both be located."""
    istexture, last, first, speed = rec
    order = tex_order if istexture == 1 else flat_order
    try:
        i, j = order.index(first), order.index(last)
    except ValueError:
        return {first, last}
    if i > j:
        i, j = j, i
    return set(order[i:j + 1])


def expand_used_names(used_tex, used_flats, all_anims, all_switches, flat_order, tex_order):
    """Grow the map's used-name sets so animation cycles and switch pairs are
    complete: if ANY frame of a cycle is used, all of its frames are; if
    either state of a switch is used, both are. Repeats until stable (a
    newly added frame can itself belong to another entry)."""
    used_tex, used_flats = set(used_tex), set(used_flats)
    changed = True
    while changed:
        changed = False
        for rec in all_anims:
            frames = anim_frames(rec, flat_order, tex_order)
            target = used_tex if rec[0] == 1 else used_flats
            if frames & target and not frames <= target:
                target |= frames
                changed = True
        for name1, name2, episode in all_switches:
            if (name1 in used_tex) != (name2 in used_tex):
                used_tex |= {name1, name2}
                changed = True
    return used_tex, used_flats


def parse_animated(data):
    """23-byte records: istexture(1) + last(9) + first(9) + speed(4)."""
    recs = []
    if not data:
        return recs
    for i in range(len(data) // 23):
        off = i * 23
        istexture = data[off]
        if istexture == 0xFF:
            break
        last = decode_name(data[off + 1:off + 10])
        first = decode_name(data[off + 10:off + 19])
        speed = struct.unpack_from("<i", data, off + 19)[0]
        if istexture not in (0, 1):
            warn(f"ANIMATED: unrecognised record type {istexture} for {first}->{last}, skipped")
            continue
        recs.append((istexture, last, first, speed))
    return recs


def parse_switches(data):
    """20-byte records: name1(9) + name2(9) + episode(2). episode==0 terminates."""
    recs = []
    if not data:
        return recs
    for i in range(len(data) // 20):
        off = i * 20
        episode = struct.unpack_from("<h", data, off + 18)[0]
        if episode == 0:
            break
        name1 = decode_name(data[off:off + 9])
        name2 = decode_name(data[off + 9:off + 18])
        recs.append((name1, name2, episode))
    return recs


def _format_table(rows, header_cols):
    """Space-pad columns (all but the last) so a monospaced view lines up
    cleanly, regardless of how long any individual name is. Returns a list
    of text lines, header included (as a comment)."""
    ncols = len(header_cols)
    widths = [len(h) for h in header_cols]
    str_rows = [[str(v) for v in r] for r in rows]
    for r in str_rows:
        for i in range(ncols):
            widths[i] = max(widths[i], len(r[i]))

    def fmt(cols):
        parts = [cols[i].ljust(widths[i]) if i < ncols - 1 else cols[i]
                 for i in range(ncols)]
        return "  ".join(parts).rstrip()

    lines = ["; " + fmt(list(header_cols))]
    lines += [fmt(r) for r in str_rows]
    return lines


def dedup_keep_first(seq):
    """Return (deduped_list, num_duplicates_removed), preserving first-seen order."""
    seen = set()
    out = []
    dupes = 0
    for item in seq:
        if item in seen:
            dupes += 1
            continue
        seen.add(item)
        out.append(item)
    return out, dupes


def write_defswani(path, switches, anim_flats, anim_textures, wad_name, filtered):
    # Numerical order: group entries by their leading number (episode / speed),
    # ascending, so matching numbers sit together. Ties keep their original
    # relative order (stable sort).
    switches = sorted(switches, key=lambda r: r[2])        # (name1, name2, episode)
    anim_flats = sorted(anim_flats, key=lambda r: r[2])     # (last, first, speed)
    anim_textures = sorted(anim_textures, key=lambda r: r[2])

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"; Generated by textureextract from '{os.path.basename(wad_name)}' on {now}",
        "; DEFSWANI/SWANTBLS format (compatible with DoomTools WSwAnTbl / swantbls)",
    ]
    if filtered:
        lines.append("; Filtered: entries fully satisfiable by the IWAD (all referenced "
                      "names exist there) are excluded (--nofilter to disable)")
    lines.append("")
    lines.append("[SWITCHES]")
    lines += _format_table(
        [(episode, name1, name2) for name1, name2, episode in switches],
        ("epi", "texture1(off)", "texture2(on)"))
    lines.append("")
    lines.append("[FLATS]")
    lines += _format_table(
        [(speed, last, first) for last, first, speed in anim_flats],
        ("spd", "last", "first"))
    lines.append("")
    lines.append("[TEXTURES]")
    lines += _format_table(
        [(speed, last, first) for last, first, speed in anim_textures],
        ("spd", "last", "first"))
    lines.append("")
    with open(path, "w", encoding="ascii", errors="replace", newline="\n") as f:
        f.write("\n".join(lines))


# ================================================================ texture1.txt / texture2.txt

def write_texturex(path, textures, wad_name, filtered):
    # Alphabetical by texture name only; each texture's own patch list keeps
    # whatever order it was defined in (never reordered).
    textures = sorted(textures, key=lambda t: t.name)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"; Generated by textureextract from '{os.path.basename(wad_name)}' on {now}",
        "; DoomTools/DEUTEX-style texture definitions",
    ]
    if filtered:
        lines.append("; Filtered: textures already present in the IWAD are excluded (--nofilter to disable)")
    lines.append("")
    for t in textures:
        lines.append(f"{t.name} {t.width} {t.height}")
        for pname, x, y in t.patches:
            lines.append(f"*\t{pname} {x} {y}")
        lines.append("")
    with open(path, "w", encoding="ascii", errors="replace", newline="\n") as f:
        f.write("\n".join(lines))


# ================================================================ picture (patch) decoding

def decode_patch(data):
    """Decode a Doom picture-format lump. Returns (w, h, leftofs, topofs, pixels)
    where pixels[y][x] is a palette index or None (transparent). Supports
    tall-patch (cumulative topdelta) posts."""
    if len(data) < 8:
        return None
    width, height, leftoffset, topoffset = struct.unpack_from("<hhhh", data, 0)
    if width <= 0 or height <= 0 or width > 4096 or height > 4096:
        return None
    if 8 + width * 4 > len(data):
        return None
    colofs = struct.unpack_from(f"<{width}i", data, 8)
    pixels = [[None] * width for _ in range(height)]
    for x in range(width):
        off = colofs[x]
        if off < 0 or off >= len(data):
            continue
        pos = off
        last_topdelta = -1
        while pos < len(data):
            topdelta = data[pos]
            if topdelta == 0xFF:
                break
            if topdelta <= last_topdelta:
                topdelta += last_topdelta
            last_topdelta = topdelta
            pos += 1
            if pos >= len(data):
                break
            length = data[pos]
            pos += 1
            pos += 1  # unused padding byte
            if pos + length > len(data):
                break
            column = pixels
            for i in range(length):
                y = topdelta + i
                if 0 <= y < height:
                    column[y][x] = data[pos + i]
            pos += length
            pos += 1  # unused padding byte
    return width, height, leftoffset, topoffset, pixels


# ================================================================ flat dimensions

_KNOWN_FLAT_SIZES = {
    8192: (64, 128),
    32768: (256, 128),
    20480: (128, 160),
    64000: (320, 200),
}


def flat_dims(size):
    root = math.isqrt(size)
    if root > 0 and root * root == size:
        return root, root
    if size in _KNOWN_FLAT_SIZES:
        return _KNOWN_FLAT_SIZES[size]
    if size > 0 and size % 64 == 0:
        return 64, size // 64
    return None


# ================================================================ palette + PNG output

def load_palette(pwad, iwad):
    data = pwad.get("PLAYPAL")
    if data is None:
        data = iwad.get("PLAYPAL")
    if data is None or len(data) < 768:
        die("no usable PLAYPAL lump found in the PWAD or IWAD")
    return [(data[i * 3], data[i * 3 + 1], data[i * 3 + 2]) for i in range(256)]


def write_png(path, width, height, rows_rgba, grab=None):
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for row in rows_rgba:
        raw.append(0)
        raw.extend(row)
    idat = zlib.compress(bytes(raw), 9)

    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += chunk(b"IHDR", ihdr)
    if grab is not None:
        out += chunk(b"grAb", struct.pack(">ii", grab[0], grab[1]))
    out += chunk(b"IDAT", idat)
    out += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)


# ================================================================ main

def main():
    parser = argparse.ArgumentParser(
        prog="textureextract",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Extract textures and flats from a WAD as true-colour PNGs, "
                    "and write DoomTools-style texture1.txt/texture2.txt plus a "
                    "defswani.txt (from ANIMATED/SWITCHES).",
        epilog="examples:\n"
               "  textureextract mywad.wad -iwad doom2.wad\n"
               "  textureextract mywad.wad -iwad doom2.wad --nofilter\n"
               "  textureextract mywad.wad -iwad doom2.wad -o build/mywad_assets\n"
               "  textureextract mywad.wad -iwad doom2.wad -map MAP01\n")
    parser.add_argument("wad", help="the PWAD to extract from")
    parser.add_argument("-iwad", "--iwad", required=True, metavar="IWAD",
                        help="the IWAD to filter against (and fall back to for PLAYPAL)")
    parser.add_argument("--nofilter", action="store_true",
                        help="do not filter out textures/flats already present in the IWAD")
    parser.add_argument("-o", "--output", metavar="DIR",
                        help="output directory (default: ./<wad-stem>/, or "
                             "./<wad-stem>_<mapname>/ with -map)")
    parser.add_argument("-map", "--map", dest="map", metavar="MAPNAME",
                        help="only extract what this one map uses (e.g. MAP01, E1M1) "
                             "instead of everything in the WAD")
    args = parser.parse_args()

    if not os.path.isfile(args.wad):
        die(f"'{args.wad}' does not exist")
    if not os.path.isfile(args.iwad):
        die(f"'{args.iwad}' does not exist")

    pwad = Wad(args.wad)
    iwad = Wad(args.iwad)

    palette = load_palette(pwad, iwad)
    palette_rgba = [bytes((r, g, b, 255)) for (r, g, b) in palette]
    transparent = b"\x00\x00\x00\x00"

    tex1, tex2 = parse_textures(pwad)
    itex1, itex2 = parse_textures(iwad)
    iwad_tex_names = {t.name for t in itex1 + itex2}

    pwad_flats = pwad.flat_names()
    iwad_flat_names = set(iwad.flat_names())

    filt = not args.nofilter

    map_textures = map_flats = None
    if args.map:
        map_textures, map_flats = map_used_names(pwad, args.map)
        # A map's geometry references only ONE frame of an animated flat/
        # texture (usually the first) and one state of a switch — the rest of
        # the cycle exists only via the animation table. Expand the used-name
        # sets to whole cycles/pairs, using every table we know about: the
        # PWAD's ANIMATED/SWITCHES, the IWAD's (rarely present), and the
        # vanilla hardcoded engine tables (vanilla IWADs ship no lump).
        flat_order = list(pwad_flats)
        flat_order += [n for n in iwad.flat_names() if n not in set(flat_order)]
        tex_order = [t.name for t in tex1 + tex2]
        seen_tex = set(tex_order)
        tex_order += [t.name for t in itex1 + itex2 if t.name not in seen_tex]

        all_anims = (parse_animated(pwad.get("ANIMATED"))
                     + parse_animated(iwad.get("ANIMATED"))
                     + VANILLA_ANIMATED)
        all_switches = (parse_switches(pwad.get("SWITCHES"))
                        + parse_switches(iwad.get("SWITCHES"))
                        + VANILLA_SWITCHES)
        map_textures, map_flats = expand_used_names(
            map_textures, map_flats, all_anims, all_switches, flat_order, tex_order)

    def tex_ok(name):
        return (not filt or name not in iwad_tex_names) and \
               (map_textures is None or name in map_textures)

    def flat_ok(name):
        return (not filt or name not in iwad_flat_names) and \
               (map_flats is None or name in map_flats)

    keep_tex1 = [t for t in tex1 if tex_ok(t.name)]
    keep_tex2 = [t for t in tex2 if tex_ok(t.name)]
    keep_flats = [n for n in pwad_flats if flat_ok(n)]

    if args.map:
        default_dir = f"{os.path.splitext(os.path.basename(args.wad))[0]}_{args.map.lower()}"
    else:
        default_dir = os.path.splitext(os.path.basename(args.wad))[0]
    outdir = args.output or default_dir
    flats_dir = os.path.join(outdir, "flats")
    patches_dir = os.path.join(outdir, "patches")
    os.makedirs(flats_dir, exist_ok=True)
    os.makedirs(patches_dir, exist_ok=True)

    # ---------------- flats ----------------
    flat_written = 0
    flat_skipped = []
    for name in keep_flats:
        data = pwad.get(name)
        dims = flat_dims(len(data))
        if dims is None:
            flat_skipped.append(name)
            continue
        w, h = dims
        rows = []
        for y in range(h):
            base = y * w
            rows.append(b"".join(palette_rgba[b] for b in data[base:base + w]))
        write_png(os.path.join(flats_dir, name + ".png"), w, h, rows)
        flat_written += 1

    # ---------------- patches ----------------
    tex_source = keep_tex1 + keep_tex2
    wanted_patches = sorted({pname for t in tex_source for pname, _, _ in t.patches})

    patch_written = 0
    patch_missing = []
    for pname in wanted_patches:
        data = pwad.get(pname)
        decoded = decode_patch(data) if data is not None else None
        if decoded is None:
            patch_missing.append(pname)
            continue
        w, h, lox, loy, pixels = decoded
        rows = []
        for y in range(h):
            rows.append(b"".join(transparent if v is None else palette_rgba[v] for v in pixels[y]))
        write_png(os.path.join(patches_dir, pname + ".png"), w, h, rows, grab=(lox, loy))
        patch_written += 1

    # ---------------- texture1.txt / texture2.txt ----------------
    write_texturex(os.path.join(outdir, "texture1.txt"), keep_tex1, args.wad, filt)
    has_texture2 = pwad.get("TEXTURE2") is not None
    if has_texture2:
        write_texturex(os.path.join(outdir, "texture2.txt"), keep_tex2, args.wad, filt)

    # ---------------- defswani.txt ----------------
    anims = parse_animated(pwad.get("ANIMATED"))
    switches = parse_switches(pwad.get("SWITCHES"))

    if filt:
        # Most vanilla IWADs (Doom, Doom2, Heretic, Hexen...) ship NO
        # ANIMATED/SWITCHES lump at all — that data is hardcoded in the
        # engine, not stored as a lump. So comparing PWAD records against an
        # IWAD lump (which is usually just plain absent) misses almost every
        # stock entry. Instead: an entry is "stock" if every name it
        # references is itself a name already found in the IWAD (same
        # name-based test used for flats/textures above) — e.g. a switch
        # entry is dropped only if BOTH its off and on texture names are
        # IWAD textures; an animated cycle is dropped only if BOTH its
        # first and last frame names are IWAD flats/textures. If either
        # name is new, the whole entry is kept, since it can't be fully
        # satisfied by the IWAD alone.
        iwad_anims_exact = set(parse_animated(iwad.get("ANIMATED")))
        iwad_switches_exact = set(parse_switches(iwad.get("SWITCHES")))

        def anim_is_stock(rec):
            istexture, last, first, speed = rec
            names = iwad_tex_names if istexture == 1 else iwad_flat_names
            return rec in iwad_anims_exact or (last in names and first in names)

        def switch_is_stock(rec):
            name1, name2, episode = rec
            return rec in iwad_switches_exact or (name1 in iwad_tex_names and name2 in iwad_tex_names)

        anims = [a for a in anims if not anim_is_stock(a)]
        switches = [s for s in switches if not switch_is_stock(s)]

    if args.map:
        # map_textures/map_flats were expanded above to full cycles, so if
        # the map touched ANY frame of an animation, its first/last names
        # are guaranteed to be in the set by now.
        def anim_on_map(rec):
            istexture, last, first, speed = rec
            names = map_textures if istexture == 1 else map_flats
            return last in names or first in names

        def switch_on_map(rec):
            name1, name2, episode = rec
            return name1 in map_textures or name2 in map_textures

        anims = [a for a in anims if anim_on_map(a)]
        switches = [s for s in switches if switch_on_map(s)]

    # Drop exact-duplicate records within the PWAD itself (keeping the first
    # occurrence). It's common for a PWAD's ANIMATED/SWITCHES to contain the
    # same entry several times over (e.g. merged from multiple source WADs
    # that each embedded a full copy) — there's no reason to repeat it here.
    anims, anim_dupes = dedup_keep_first(anims)
    switches, switch_dupes = dedup_keep_first(switches)

    anim_flats = [(last, first, speed) for (t, last, first, speed) in anims if t == 0]
    anim_textures = [(last, first, speed) for (t, last, first, speed) in anims if t == 1]
    write_defswani(os.path.join(outdir, "defswani.txt"), switches, anim_flats, anim_textures, args.wad, filt)

    # ---------------- summary ----------------
    print(f"Output directory: {outdir}")
    if args.map:
        print(f"Scope: only content used by map '{args.map.upper()}'")
    print(f"Flats:    {flat_written} written"
          + (f", {len(flat_skipped)} skipped (unrecognised dimensions)" if flat_skipped else ""))
    print(f"Patches:  {patch_written} written"
          + (f", {len(patch_missing)} missing/undecodable" if patch_missing else ""))
    tex_summary = f"Textures: {len(keep_tex1)} in texture1.txt"
    if has_texture2:
        tex_summary += f", {len(keep_tex2)} in texture2.txt"
    print(tex_summary)
    if switches or anims:
        print(f"defswani.txt: {len(switches)} switch(es), "
              f"{len(anim_flats)} animated flat(s), {len(anim_textures)} animated texture(s)")
    if switch_dupes or anim_dupes:
        print(f"defswani.txt: removed {switch_dupes} duplicate switch line(s), "
              f"{anim_dupes} duplicate ANIMATED line(s)")
    if filt:
        print("(filtered: only content not present in the IWAD; use --nofilter to include everything)")
    if flat_skipped:
        print("Flats with unrecognised dimensions: " + ", ".join(flat_skipped))
    if patch_missing:
        print("Patches not found/decodable in the PWAD: " + ", ".join(patch_missing))


if __name__ == "__main__":
    main()