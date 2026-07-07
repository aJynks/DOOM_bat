#!/usr/bin/env python3
"""
texx.py — TEXTUREx manipulation tool.

Modes:
  texx --convert input [-o out.txt]                        (-c)
      Convert texture definitions to a DoomTools/DEUTEX-style text file.

  texx --merge in1 in2 ... [--filter f ...] [-o out]       (-m)
      Merge all inputs into one file of unique texture definitions,
      written out sorted alphabetically by texture name (patch layout
      and order within each texture is untouched)
      (default: unique-textureX.txt).

  texx --subtract base.txt other1 ... [--filter f ...]     (-s)
      Copy of base.txt with every texture removed that is identical
      (name + layout) to a definition in the others or the filter
      (default output: <basestem>-subtracted.txt).

  texx --findPatches texturex.txt --sourcedir DIR [-o DIR] (-fp)
      Recursively scan a directory and COPY every file whose name matches
      a patch referenced by the texture file into the output directory
      (default: <inputstem>-patches). Existing files are overwritten.

  texx --animation in1 in2 ... --default base-defswani.txt [-o out]  (-a)
      Merge SWANTBLS/defswani switch+animation definition files into
      --default. --default is reproduced 100% unchanged; new switches
      and flat/texture animations found in the other inputs are appended
      under the correct [SECTION] (default: merged-defswani.txt).
      Any switch/animation whose identity (switch base texture, or
      last+first frame pair) collides with a DIFFERENT definition —
      either against --default or between two merge inputs — is left
      out of the merge entirely and written to <outstem>-conflicts.txt
      for manual review instead.

  texx --remove in1 in2 ... --filter f ... [-o DIR]        (-rm)
      Remove --filter definitions (identical name+layout) from each
      input INDEPENDENTLY -- no merging, no cross-file dedup, no
      renaming. Each input is saved as its own file named
      removed-<original filename> in -o DIR (default: current directory).

  texx --truncate [--path DIR] [-o DIR] [--outputall DIR]  (-t)
      Recursively scan DIR (default: current directory) and truncate
      every filename whose stem exceeds 8 characters down to 8 (the
      extension is left untouched). Trailing digits on the original
      stem are preserved byte-for-byte, including leading zeros
      (fatcat067 -> fatca067); only the alphabetic part is shortened.
      If a truncated name collides with another file in the same
      directory, the trailing number is incremented instead (re-using
      its original zero-padding width where it still fits), or a
      plain 1, 2, 3, ... counter is appended if the original name had
      no trailing number at all.
        * No -o/--outputall: files are renamed in place, recursively.
        * -o DIR: copies ONLY the files that were actually truncated
          into DIR, mirroring the source's subdirectory structure
          (created as needed; existing files overwritten silently).
        * --outputall DIR: same as -o, but copies every file, not
          just the truncated ones.
        * -o and --outputall can both be given (each gets its own
          mirrored copy) but may not point at the same directory.

Null texture:
  Every texx-written output enforces AASTINKY (index 0 in TEXTURE1/2) as
  the FIRST texture, unconditionally, regardless of the mode's own
  ordering (alphabetical for --merge, input order otherwise). If no
  texture named AASTINKY is present in the output, texx adds the
  standard definition itself:
      AASTINKY 24 72
      *	WALL00_3 0 0
      *	WALL00_3 12 -6

Accepted inputs (auto-detected by content, not extension):
  * WAD file            — all TEXTURE1/TEXTURE2 lumps (PNAMES read from the
                          same WAD; Doom and Strife binary formats detected)
  * SLADE TEXTURES txt  — WallTexture "NAME", W, H { Patch "NAME", x, y }
  * DoomTools/DEUTEX txt — NAME W H  /  *<tab>PATCH X Y

Merge rules:
  * Texture identity = name + width/height + full patch layout
    (patch names, order, X/Y offsets).
  * Identical name+layout seen again  -> skipped (first input wins).
  * Same name, different layout       -> kept, renamed: trailing number is
    incremented (stem truncated if 8 chars would be exceeded, e.g.
    TESTIT99 -> TESTI100); names without a trailing number get one appended.
  * --filter inputs: any merge texture identical (name+layout) to a filter
    definition is dropped. Same name but different layout than the filter
    version is kept under its ORIGINAL name (stock-texture replacement).

Dependencies: none — Python 3 standard library only.
"""

import argparse
import datetime
import os
import re
import shutil
import struct
import sys

# ---------------------------------------------------------------- dependency check
# This tool uses only the Python standard library. Nothing to install.
# ----------------------------------------------------------------

WAD_HEADER = struct.Struct("<4sii")
WAD_DIR    = struct.Struct("<ii8s")

# The null texture (index 0 in TEXTURE1/2) must always be first in any
# output. If an input set doesn't already have one, this is the standard
# definition texx will insert.
NULL_TEXTURE_NAME = "AASTINKY"
NULL_TEXTURE_WIDTH = 24
NULL_TEXTURE_HEIGHT = 72
NULL_TEXTURE_PATCHES = (("WALL00_3", 0, 0), ("WALL00_3", 12, -6))


class Texture:
    __slots__ = ("name", "width", "height", "patches", "source")

    def __init__(self, name, width, height, patches, source):
        self.name = name.upper()
        self.width = width
        self.height = height
        self.patches = tuple(patches)   # tuple of (NAME, x, y)
        self.source = source            # which input file it came from

    def layout(self):
        return (self.width, self.height, self.patches)

    def key(self):
        return (self.name, self.layout())


def die(msg):
    print(f"texx: error: {msg}", file=sys.stderr)
    sys.exit(1)


def decode_name(raw):
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").upper()


# ================================================================ WAD parsing

def parse_wad(path, data):
    signature, numlumps, dirofs = WAD_HEADER.unpack_from(data, 0)
    if numlumps < 0 or dirofs < 0 or dirofs + numlumps * WAD_DIR.size > len(data):
        die(f"'{path}': corrupt WAD directory")

    lumps = {}
    order = []
    for i in range(numlumps):
        filepos, size, raw = WAD_DIR.unpack_from(data, dirofs + i * WAD_DIR.size)
        name = decode_name(raw)
        if name in ("PNAMES", "TEXTURE1", "TEXTURE2") and name not in lumps:
            if size < 0 or filepos < 0 or filepos + size > len(data):
                die(f"'{path}': lump {name} data outside file")
            lumps[name] = data[filepos:filepos + size]
            order.append(name)

    tex_lumps = [n for n in ("TEXTURE1", "TEXTURE2") if n in lumps]
    if not tex_lumps:
        die(f"'{path}': no TEXTURE1 or TEXTURE2 lump found")
    if "PNAMES" not in lumps:
        die(f"'{path}': has {'/'.join(tex_lumps)} but no PNAMES lump")

    pnames = parse_pnames(path, lumps["PNAMES"])
    textures = []
    for lname in tex_lumps:
        textures += parse_texturex(path, lname, lumps[lname], pnames)
    return textures


def parse_pnames(path, data):
    if len(data) < 4:
        die(f"'{path}': PNAMES lump too small")
    count = struct.unpack_from("<i", data, 0)[0]
    if count < 0 or 4 + count * 8 > len(data):
        die(f"'{path}': PNAMES count ({count}) does not fit lump size")
    return [decode_name(data[4 + i * 8: 4 + i * 8 + 8]) for i in range(count)]


def _try_texturex(data, pnames, doom_format):
    """Parse a binary TEXTUREx lump in one format.

    Returns (defs, exact_fits) where defs is a list of
    (name, w, h, [(patchname, x, y)]) and exact_fits counts textures whose
    computed byte size exactly reaches the next texture's offset (or lump
    end) — used to disambiguate Doom vs Strife format. Returns None if the
    lump is not parseable in this format at all.
    """
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
        # next boundary after this texture's offset
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


def parse_texturex(path, lumpname, data, pnames):
    doom = _try_texturex(data, pnames, doom_format=True)
    strife = _try_texturex(data, pnames, doom_format=False)
    if doom is None and strife is None:
        die(f"'{path}': {lumpname} is not a valid Doom or Strife TEXTUREx lump")
    # Prefer the format whose texture sizes exactly fill the lump layout;
    # ties go to Doom (the canonical format).
    if strife is not None and (doom is None or strife[1] > doom[1]):
        parsed, fmt = strife[0], "Strife"
    else:
        parsed, fmt = doom[0], "Doom"
    src = f"{os.path.basename(path)}:{lumpname} ({fmt} format)"
    return [Texture(n, w, h, p, src) for n, w, h, p in parsed]


# ================================================================ SLADE TEXTURES text

_SLADE_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_SLADE_TEX = re.compile(r'\b(walltexture|texture)\s+"([^"]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\{',
                        re.I)
_SLADE_PATCH = re.compile(r'\bpatch\s+"([^"]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)', re.I)


def parse_slade(path, text):
    text = _SLADE_COMMENTS.sub("", text)
    textures = []
    src = os.path.basename(path)
    for m in _SLADE_TEX.finditer(text):
        name, w, h = m.group(2), int(m.group(3)), int(m.group(4))
        # find the matching closing brace of this block
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        block = text[m.end():i - 1]
        patches = [(pm.group(1).upper(), int(pm.group(2)), int(pm.group(3)))
                   for pm in _SLADE_PATCH.finditer(block)]
        textures.append(Texture(name, w, h, patches, src))
    if not textures:
        die(f"'{path}': looks like a SLADE TEXTURES file but no texture blocks parsed")
    return textures


# ================================================================ DEUTEX text

def parse_deutex(path, text):
    defs = []          # (name, w, h, [patches])
    current = None
    for linenum, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("*"):
            if current is None:
                die(f"'{path}' line {linenum}: patch line before any texture line")
            parts = line[1:].split()
            if len(parts) < 3:
                die(f"'{path}' line {linenum}: malformed patch line: {line!r}")
            try:
                current.append((parts[0].upper(), int(parts[1]), int(parts[2])))
            except ValueError:
                die(f"'{path}' line {linenum}: bad patch offsets: {line!r}")
        else:
            parts = line.split()
            if len(parts) < 3:
                die(f"'{path}' line {linenum}: malformed texture line: {line!r}")
            try:
                current = []
                defs.append((parts[0], int(parts[1]), int(parts[2]), current))
            except ValueError:
                die(f"'{path}' line {linenum}: bad texture dimensions: {line!r}")
    src = os.path.basename(path)
    return [Texture(n, w, h, p, src) for n, w, h, p in defs]


# ================================================================ input dispatch

def load_input(path):
    if not os.path.isfile(path):
        die(f"input file '{path}' does not exist")
    with open(path, "rb") as f:
        blob = f.read()

    if blob[:4] in (b"IWAD", b"PWAD"):
        return parse_wad(path, blob)

    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = blob.decode("latin-1")
        except UnicodeDecodeError:
            die(f"'{path}' is neither a WAD nor a readable text file")

    stripped = _SLADE_COMMENTS.sub("", text)
    if _SLADE_TEX.search(stripped):
        return parse_slade(path, text)
    return parse_deutex(path, text)


# ================================================================ renaming

_TRAILING_NUM = re.compile(r"^(.*?)(\d+)$")


def make_unique_name(name, taken):
    m = _TRAILING_NUM.match(name)
    if m:
        stem, num = m.group(1), int(m.group(2)) + 1
    else:
        stem, num = name, 2
    while True:
        digits = str(num)
        room = 8 - len(digits)
        if room <= 0:
            die(f"cannot generate a unique 8-char name for '{name}'")
        candidate = (stem[:room] + digits).upper()
        if candidate not in taken:
            return candidate
        num += 1


# ================================================================ output

def write_deutex(path, textures, mode, inputs, filters):
    null_tex = None
    rest = []
    for t in textures:
        if null_tex is None and t.name == NULL_TEXTURE_NAME:
            null_tex = t
        else:
            rest.append(t)
    if null_tex is None:
        null_tex = Texture(NULL_TEXTURE_NAME, NULL_TEXTURE_WIDTH,
                            NULL_TEXTURE_HEIGHT, NULL_TEXTURE_PATCHES,
                            "texx (synthesized null texture)")
        print(f"NOTE: '{NULL_TEXTURE_NAME}' (the null texture) was not present "
              f"-- added it as texture 0.")
    textures = [null_tex] + rest

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"; File generated by TEXX ({mode}) on {now}",
             "; This is also compatible with DEUTEX!",
             f"; Inputs: {', '.join(os.path.basename(p) for p in inputs)}"]
    if filters:
        lines.append(f"; Filter: {', '.join(os.path.basename(p) for p in filters)}")
    lines.append("")
    for t in textures:
        lines.append(f"{t.name} {t.width} {t.height}")
        for pname, x, y in t.patches:
            lines.append(f"*\t{pname} {x} {y}")
        lines.append("")
    try:
        with open(path, "w", encoding="ascii", errors="replace", newline="\n") as f:
            f.write("\n".join(lines))
    except OSError as e:
        die(f"cannot write '{path}': {e}")


# ================================================================ modes

def do_convert(input_path, out_path):
    textures = load_input(input_path)
    write_deutex(out_path, textures, "convert", [input_path], [])
    print(f"Converted {len(textures)} texture definition(s) from '{input_path}'.")
    print(f"Wrote: {out_path}")


def do_merge(input_paths, filter_paths, out_path):
    # Filter set: name -> set of layouts
    filter_defs = {}
    for fp in filter_paths:
        for t in load_input(fp):
            filter_defs.setdefault(t.name, set()).add(t.layout())

    # Gather all merge textures in command-line order
    all_textures = []
    for ip in input_paths:
        batch = load_input(ip)
        print(f"Read {len(batch):>5} definition(s) from '{ip}'")
        all_textures += batch

    # Reserve every original input name so renames never collide with
    # a texture that appears later in the input stream.
    taken = {t.name for t in all_textures}

    emitted_layouts = {}   # original name -> set of layouts already output
    output = []
    renamed, skipped_dup, skipped_filtered = [], 0, 0

    for t in all_textures:
        if t.layout() in filter_defs.get(t.name, ()):
            skipped_filtered += 1
            continue
        seen = emitted_layouts.setdefault(t.name, set())
        if t.layout() in seen:
            skipped_dup += 1
            continue
        if seen:  # same name, different layout -> rename this one
            new_name = make_unique_name(t.name, taken)
            taken.add(new_name)
            renamed.append((t.name, new_name, t.source))
            seen.add(t.layout())
            output.append(Texture(new_name, t.width, t.height, t.patches, t.source))
        else:
            seen.add(t.layout())
            output.append(t)

    output.sort(key=lambda t: t.name)

    write_deutex(out_path, output, "merge", input_paths, filter_paths)

    print()
    if renamed:
        print(f"Renamed {len(renamed)} same-name/different-layout texture(s):")
        for old, new, src in renamed:
            print(f"  {old:<8} -> {new:<8}  (from {src})")
        print()
    print(f"{len(all_textures)} definitions in  ->  {len(output)} unique definitions out")
    print(f"  duplicates skipped: {skipped_dup}")
    if filter_paths:
        print(f"  removed by filter:  {skipped_filtered}")
    print(f"Wrote: {out_path}")


def load_deutex_only(path):
    """Load a file that MUST be a DoomTools/DEUTEX text file (no auto-detect)."""
    if not os.path.isfile(path):
        die(f"input file '{path}' does not exist")
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:4] in (b"IWAD", b"PWAD"):
        die(f"'{path}' is a WAD file — this mode requires a DoomTools texturex.txt")
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("latin-1")
    if _SLADE_TEX.search(_SLADE_COMMENTS.sub("", text)):
        die(f"'{path}' is a SLADE TEXTURES file — this mode requires a "
            f"DoomTools texturex.txt")
    return parse_deutex(path, text)


def do_subtract(input_paths, filter_paths, out_path):
    base_path = input_paths[0]
    other_paths = input_paths[1:]
    base = load_deutex_only(base_path)
    print(f"Read {len(base):>5} definition(s) from base '{base_path}'")

    remove = set()
    for p in other_paths + filter_paths:
        batch = load_input(p)
        print(f"Read {len(batch):>5} definition(s) from '{p}'")
        remove.update(t.key() for t in batch)

    kept = [t for t in base if t.key() not in remove]
    removed = [t for t in base if t.key() in remove]

    if out_path is None:
        stem = os.path.splitext(os.path.basename(base_path))[0]
        out_path = f"{stem}-subtracted.txt"
    write_deutex(out_path, kept, "subtract", input_paths, filter_paths)

    print()
    if removed:
        print(f"Removed {len(removed)} identical texture(s):")
        for t in removed:
            print(f"  {t.name}")
    print(f"\n{len(base)} definitions in  ->  {len(kept)} definitions out")
    print(f"Wrote: {out_path}")


def do_remove(input_paths, filter_paths, out_dir):
    filter_defs = {}
    for fp in filter_paths:
        batch = load_input(fp)
        print(f"Read {len(batch):>5} definition(s) from filter '{fp}'")
        for t in batch:
            filter_defs.setdefault(t.name, set()).add(t.layout())

    out_dir = out_dir or "."
    os.makedirs(out_dir, exist_ok=True)

    print()
    for ip in input_paths:
        textures = load_input(ip)
        kept = [t for t in textures if t.layout() not in filter_defs.get(t.name, ())]
        removed = [t for t in textures if t.layout() in filter_defs.get(t.name, ())]

        out_path = os.path.join(out_dir, f"removed-{os.path.basename(ip)}")
        write_deutex(out_path, kept, "remove", [ip], filter_paths)

        print(f"'{ip}': {len(textures)} in  ->  {len(removed)} removed  ->  "
              f"{len(kept)} written")
        for t in removed:
            print(f"  removed: {t.name}")
        print(f"  Wrote: {out_path}")
        print()


def do_find_patches(input_path, source_dir, out_dir):
    if not os.path.isdir(source_dir):
        die(f"source directory '{source_dir}' does not exist")
    textures = load_deutex_only(input_path)

    # Each patch name is collected only once, however many textures use it.
    wanted = {pname for t in textures for pname, _, _ in t.patches}
    print(f"{len(textures)} texture definition(s) referencing "
          f"{len(wanted)} unique patch name(s)")

    if out_dir is None:
        stem = os.path.splitext(os.path.basename(input_path))[0]
        out_dir = f"{stem}-patches"
    os.makedirs(out_dir, exist_ok=True)
    out_abs = os.path.abspath(out_dir)

    # Full recursive scan first (never descending into the output dir),
    # THEN copy — so freshly copied files are never re-scanned.
    matches = {}    # filename.lower() -> first full path found
    shadowed = []   # (shadowed path, winning path)
    found_stems = set()
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs
                   if os.path.abspath(os.path.join(root, d)) != out_abs]
        for fname in sorted(files):
            stem = os.path.splitext(fname)[0].upper()
            if stem not in wanted:
                continue
            found_stems.add(stem)
            key = fname.lower()
            full = os.path.join(root, fname)
            if key in matches:
                shadowed.append((full, matches[key]))
            else:
                matches[key] = full

    copied = 0
    for full in sorted(matches.values()):
        try:
            shutil.copy2(full, os.path.join(out_abs, os.path.basename(full)))
            copied += 1
        except OSError as e:
            die(f"cannot copy '{full}': {e}")

    missing = sorted(wanted - found_stems)
    print(f"Copied {copied} file(s) to '{out_dir}'")
    if shadowed:
        print(f"\nWARNING: {len(shadowed)} file(s) shadowed by an identical "
              f"filename in another subdirectory (not copied):")
        for lost, winner in shadowed:
            print(f"  {lost}  (used: {winner})")
    if missing:
        print(f"\nWARNING: {len(missing)} referenced patch(es) had NO matching "
              f"file in '{source_dir}':")
        for name in missing:
            print(f"  {name}")


# ================================================================ filename truncation

def _truncate_stem_unique(stem, ext, taken_lower, maxlen=8):
    """Truncate a filename stem to maxlen chars, unique (case-insensitive,
    extension-aware) against taken_lower.

    Trailing digits on the original stem are preserved verbatim (leading
    zeros and all) as long as no collision occurs -- only the alphabetic
    prefix is shortened. If the naive truncation collides with something
    already in taken_lower, falls back to an incrementing counter: the
    existing trailing number is bumped by 1 (re-zero-padded to its
    original width where that still fits), or a plain unpadded 1, 2, 3,
    ... counter is appended if the stem had no trailing number at all.
    """
    m = _TRAILING_NUM.match(stem)
    if m:
        prefix, digits = m.group(1), m.group(2)
    else:
        prefix, digits = stem, ""

    room = maxlen - len(digits)
    if room >= 0:
        candidate = prefix[:room] + digits
    else:
        # digits alone already exceed maxlen (pathological) -- keep only
        # the trailing digits that fit and drop the prefix entirely.
        digits = digits[-maxlen:]
        prefix = ""
        candidate = digits
    if (candidate + ext).lower() not in taken_lower:
        return candidate

    if digits:
        num, width = int(digits) + 1, len(digits)
    else:
        num, width = 1, 0
    while True:
        num_str = str(num)
        if width and len(num_str) < width:
            num_str = num_str.zfill(width)
        room = maxlen - len(num_str)
        if room <= 0:
            die(f"cannot generate a unique {maxlen}-char name for "
                f"'{stem}{ext}' -- ran out of room for a counter")
        candidate = prefix[:room] + num_str
        if (candidate + ext).lower() not in taken_lower:
            return candidate
        num += 1


def do_truncate(source_dir, out_dir, outall_dir):
    if not os.path.isdir(source_dir):
        die(f"source directory '{source_dir}' does not exist")

    out_abs = os.path.abspath(out_dir) if out_dir else None
    outall_abs = os.path.abspath(outall_dir) if outall_dir else None
    skip_abs = {p for p in (out_abs, outall_abs) if p}

    # Full recursive scan first, grouped by directory (uniqueness is
    # scoped per-directory, same as the filesystem itself enforces).
    # Never descend into an -o/--outputall dir that happens to live
    # inside the source tree.
    by_dir = {}
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs
                   if os.path.abspath(os.path.join(root, d)) not in skip_abs]
        if files:
            by_dir[os.path.relpath(root, source_dir)] = sorted(files)

    plan = []   # (rel_root, old_name, new_name, was_truncated)
    for rel_root, files in sorted(by_dir.items()):
        taken_lower = set()
        short, long_ = [], []
        for fname in files:
            stem, ext = os.path.splitext(fname)
            (short if len(stem) <= 8 else long_).append((fname, stem, ext))

        # Names that already fit get first claim on the namespace.
        for fname, _stem, _ext in short:
            taken_lower.add(fname.lower())
            plan.append((rel_root, fname, fname, False))

        for fname, stem, ext in long_:
            new_stem = _truncate_stem_unique(stem, ext, taken_lower)
            new_name = new_stem + ext
            taken_lower.add(new_name.lower())
            plan.append((rel_root, fname, new_name, True))

    truncated = [p for p in plan if p[3]]
    print(f"Scanned '{source_dir}': {len(plan)} file(s), "
          f"{len(truncated)} need truncation")
    for rel_root, old_name, new_name, _changed in truncated:
        rel_old = os.path.join(rel_root, old_name) if rel_root != "." else old_name
        print(f"  {rel_old}  ->  {new_name}")

    if out_dir is None and outall_dir is None:
        renamed = 0
        for rel_root, old_name, new_name, changed in plan:
            if not changed:
                continue
            old_path = os.path.join(source_dir, rel_root, old_name)
            new_path = os.path.join(source_dir, rel_root, new_name)
            try:
                os.replace(old_path, new_path)
                renamed += 1
            except OSError as e:
                die(f"cannot rename '{old_path}': {e}")
        print(f"\nRenamed {renamed} file(s) in place under '{source_dir}'.")
        return

    for label, dest, only_truncated in (
        ("-o/--output", out_dir, True),
        ("--outputall", outall_dir, False),
    ):
        if dest is None:
            continue
        copied = 0
        for rel_root, old_name, new_name, changed in plan:
            if only_truncated and not changed:
                continue
            src_path = os.path.join(source_dir, rel_root, old_name)
            dst_dir = os.path.join(dest, rel_root) if rel_root != "." else dest
            os.makedirs(dst_dir, exist_ok=True)
            dst_path = os.path.join(dst_dir, new_name)
            try:
                shutil.copy2(src_path, dst_path)
                copied += 1
            except OSError as e:
                die(f"cannot copy '{src_path}': {e}")
        kind = "truncated files only" if only_truncated else "all files"
        print(f"\n{label}: copied {copied} file(s) to '{dest}' ({kind}).")


# ================================================================ defswani (SWANTBLS) text
#
# [SWITCHES] lines:            epi   tex1   tex2
# [FLATS] / [TEXTURES] lines:  spd   last   first

_DEFSWANI_SECTION = re.compile(r'^\[(\w+)\]$')


class SwitchEntry:
    __slots__ = ("epi", "tex1", "tex2", "source")

    def __init__(self, epi, tex1, tex2, source):
        self.epi = epi
        self.tex1 = tex1.upper()
        self.tex2 = tex2.upper()
        self.source = source

    def line(self):
        return (self.epi, self.tex1, self.tex2)

    def key(self):
        return self.tex1


class AnimEntry:
    __slots__ = ("spd", "last", "first", "source")

    def __init__(self, spd, last, first, source):
        self.spd = spd
        self.last = last.upper()
        self.first = first.upper()
        self.source = source

    def line(self):
        return (self.spd, self.last, self.first)

    def key(self):
        return (self.last, self.first)


def _fmt_switch(e):
    return f"{e.epi}\t{e.tex1:<15} {e.tex2}"


def _fmt_anim(e):
    return f"{e.spd}\t{e.last:<12} {e.first}"


def parse_defswani(path):
    if not os.path.isfile(path):
        die(f"input file '{path}' does not exist")
    with open(path, "rb") as f:
        blob = f.read()
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("latin-1")

    source = os.path.basename(path)
    switches, flats, textures = [], [], []
    section = None
    for linenum, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _DEFSWANI_SECTION.match(line)
        if m:
            section = m.group(1).upper()
            continue
        parts = line.split()
        if section == "SWITCHES":
            if len(parts) < 3:
                die(f"'{path}' line {linenum}: malformed switch line: {line!r}")
            try:
                epi = int(parts[0])
            except ValueError:
                die(f"'{path}' line {linenum}: bad epi number: {line!r}")
            switches.append(SwitchEntry(epi, parts[1], parts[2], source))
        elif section in ("FLATS", "TEXTURES"):
            if len(parts) < 3:
                die(f"'{path}' line {linenum}: malformed animation line: {line!r}")
            try:
                spd = int(parts[0])
            except ValueError:
                die(f"'{path}' line {linenum}: bad speed value: {line!r}")
            entry = AnimEntry(spd, parts[1], parts[2], source)
            (flats if section == "FLATS" else textures).append(entry)
        else:
            die(f"'{path}' line {linenum}: data line outside a recognized "
                f"[SECTION]: {line!r}")
    return {"switches": switches, "flats": flats, "textures": textures}


_EPI_HEADERS = {1: "# Shareware Doom", 2: "# Registered Doom", 3: "# All Versions"}


def write_defswani(path, switches, flats, textures, default_path, merge_paths):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# This file is input for SWANTBLS.EXE, it specifies the switchnames",
        "# and animated textures and flats usable with BOOM. The output of",
        "# SWANTBLS is two lumps, SWITCHES.LMP and ANIMATED.LMP that should",
        "# be inserted in the PWAD as lumps.",
        "#",
        "# Of course, this is also readable by WSWANTBL.",
        "#",
        f"# Generated by TEXX (animation-merge) on {now}",
        f"# Default (100% preserved): {os.path.basename(default_path)}",
        f"# Merged in: {', '.join(os.path.basename(p) for p in merge_paths)}",
        "",
        "# switches usable with each IWAD, 1=SW, 2=registered DOOM, 3=DOOM2",
        "[SWITCHES]",
        "# epi   texture1        texture2",
        "",
    ]

    by_epi = {}
    for e in switches:
        by_epi.setdefault(e.epi, []).append(e)
    for epi in sorted(by_epi):
        lines.append(_EPI_HEADERS.get(epi, f"# Episode {epi}"))
        for e in by_epi[epi]:
            lines.append(_fmt_switch(e))
        lines.append("")

    lines.append("# animated flats, spd is number of frames between changes")
    lines.append("# 65536 = warping, in EE")
    lines.append("[FLATS]")
    lines.append("# spd   last        first")
    for e in flats:
        lines.append(_fmt_anim(e))
    lines.append("")

    lines.append("# animated textures, spd is number of frames between changes")
    lines.append("[TEXTURES]")
    lines.append("# spd   last        first")
    for e in textures:
        lines.append(_fmt_anim(e))
    lines.append("")

    try:
        with open(path, "w", encoding="ascii", errors="replace", newline="\n") as f:
            f.write("\n".join(lines))
    except OSError as e:
        die(f"cannot write '{path}': {e}")


def _fmt_key(key):
    return key if isinstance(key, str) else "/".join(key)


def write_conflicts(path, sections):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# TEXX animation-merge conflicts - generated {now}",
        "# None of these lines were added to the merged output.",
        "# Review each group and manually copy the line you want back into",
        "# the merged file (strip the trailing comment first).",
        "",
    ]
    for label, conflict_vs_default, conflict_among_merge in sections:
        if not conflict_vs_default and not conflict_among_merge:
            continue
        fmt = _fmt_switch if label == "SWITCHES" else _fmt_anim
        lines.append(f"[{label}]")
        for key, dflt, differing in conflict_vs_default:
            lines.append(f"# CONFLICT {_fmt_key(key)} -- differs from default "
                         f"(default line kept in merged output)")
            lines.append(f"{fmt(dflt)}\t# {dflt.source} (default, kept)")
            for e in differing:
                lines.append(f"{fmt(e)}\t# {e.source}")
            lines.append("")
        for key, group in conflict_among_merge:
            n = len({e.line() for e in group})
            lines.append(f"# CONFLICT {_fmt_key(key)} -- {n} differing line(s) among merge "
                         f"files, none added")
            for e in group:
                lines.append(f"{fmt(e)}\t# {e.source}")
            lines.append("")
    try:
        with open(path, "w", encoding="ascii", errors="replace", newline="\n") as f:
            f.write("\n".join(lines))
    except OSError as e:
        die(f"cannot write '{path}': {e}")


def _print_conflicts(label, conflict_vs_default, conflict_among_merge):
    if not conflict_vs_default and not conflict_among_merge:
        return
    fmt = _fmt_switch if label == "SWITCHES" else _fmt_anim
    for key, dflt, differing in conflict_vs_default:
        print(f"CONFLICT [{label}] {_fmt_key(key)}: differs from default (default line kept)")
        print(f"  {fmt(dflt)}    ({dflt.source}, default, kept)")
        for e in differing:
            print(f"  {fmt(e)}    ({e.source})")
    for key, group in conflict_among_merge:
        n = len({e.line() for e in group})
        print(f"CONFLICT [{label}] {_fmt_key(key)}: {n} differing line(s) among merge "
              f"files, not added")
        for e in group:
            print(f"  {fmt(e)}    ({e.source})")


def _merge_section(default_entries, merge_entries_by_file):
    """Merge one section (switches, flats, or textures).

    default_entries: entries parsed from --default; kept 100% unmodified.
    merge_entries_by_file: [(filename, [entries]), ...] in command-line order.

    Returns (output_entries, added, duplicates,
             conflict_vs_default, conflict_among_merge)
    conflict_vs_default:  [(key, default_entry, [differing merge entries])]
    conflict_among_merge: [(key, [entries across all distinct lines])]
    """
    default_by_key = {}
    for e in default_entries:
        default_by_key.setdefault(e.key(), []).append(e)

    by_key = {}
    for _fname, entries in merge_entries_by_file:
        for e in entries:
            by_key.setdefault(e.key(), []).append(e)

    output = list(default_entries)
    added = 0
    duplicates = 0
    conflict_vs_default = []
    conflict_among_merge = []

    for key, entries in by_key.items():
        if key in default_by_key:
            dflt = default_by_key[key][0]
            differing = [e for e in entries if e.line() != dflt.line()]
            duplicates += len(entries) - len(differing)
            if differing:
                conflict_vs_default.append((key, dflt, differing))
        else:
            distinct = {}
            for e in entries:
                distinct.setdefault(e.line(), []).append(e)
            if len(distinct) == 1:
                group = next(iter(distinct.values()))
                output.append(group[0])
                added += 1
                duplicates += len(group) - 1
            else:
                group = []
                for line_entries in distinct.values():
                    group.extend(line_entries)
                conflict_among_merge.append((key, group))

    return output, added, duplicates, conflict_vs_default, conflict_among_merge


def do_animation(merge_paths, default_path, out_path):
    default_data = parse_defswani(default_path)
    print(f"Read default '{default_path}': "
          f"{len(default_data['switches'])} switch(es), "
          f"{len(default_data['flats'])} flat animation(s), "
          f"{len(default_data['textures'])} texture animation(s)")

    merge_data = []
    for mp in merge_paths:
        d = parse_defswani(mp)
        print(f"Read '{mp}': "
              f"{len(d['switches'])} switch(es), "
              f"{len(d['flats'])} flat animation(s), "
              f"{len(d['textures'])} texture animation(s)")
        merge_data.append((mp, d))

    results = {}
    for section in ("switches", "flats", "textures"):
        merge_entries_by_file = [(mp, d[section]) for mp, d in merge_data]
        results[section] = _merge_section(default_data[section], merge_entries_by_file)

    out_sw, add_sw, dup_sw, cvd_sw, cam_sw = results["switches"]
    out_fl, add_fl, dup_fl, cvd_fl, cam_fl = results["flats"]
    out_tx, add_tx, dup_tx, cvd_tx, cam_tx = results["textures"]

    write_defswani(out_path, out_sw, out_fl, out_tx, default_path, merge_paths)

    any_conflicts = any((cvd_sw, cam_sw, cvd_fl, cam_fl, cvd_tx, cam_tx))
    conflicts_path = None
    if any_conflicts:
        stem = os.path.splitext(out_path)[0]
        conflicts_path = f"{stem}-conflicts.txt"
        write_conflicts(conflicts_path, [
            ("SWITCHES", cvd_sw, cam_sw),
            ("FLATS", cvd_fl, cam_fl),
            ("TEXTURES", cvd_tx, cam_tx),
        ])

    print()
    print(f"Switches:  {len(default_data['switches'])} default + {add_sw} added "
          f"({dup_sw} duplicate(s) skipped) = {len(out_sw)}")
    print(f"Flats:     {len(default_data['flats'])} default + {add_fl} added "
          f"({dup_fl} duplicate(s) skipped) = {len(out_fl)}")
    print(f"Textures:  {len(default_data['textures'])} default + {add_tx} added "
          f"({dup_tx} duplicate(s) skipped) = {len(out_tx)}")

    if any_conflicts:
        print()
        _print_conflicts("SWITCHES", cvd_sw, cam_sw)
        _print_conflicts("FLATS", cvd_fl, cam_fl)
        _print_conflicts("TEXTURES", cvd_tx, cam_tx)
        print(f"\nConflicts written to: {conflicts_path}  (review and copy back "
              f"what you need)")

    print(f"\nWrote: {out_path}")


# ================================================================ CLI

def main():
    parser = argparse.ArgumentParser(
        prog="texx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="TEXTUREx manipulation: convert texture definitions to a\n"
                    "DoomTools/DEUTEX text file, merge inputs into unique\n"
                    "definitions, subtract definitions, or gather patch files.\n\n"
                    "Inputs (auto-detected by content): WAD files (TEXTURE1/TEXTURE2\n"
                    "+ PNAMES), SLADE TEXTURES .txt, DoomTools/DEUTEX .txt.\n"
                    "--subtract base and --findPatches input must be DoomTools .txt.",
        epilog="examples:\n"
               "  texx -c mywad.wad\n"
               "  texx -c slade-export.txt -o texture1.txt\n"
               "  texx -m resource.wad map01.wad -f doom2.wad\n"
               "  texx -s mytex.txt other.wad -f doom2.wad\n"
               "  texx -fp texturex.txt -sd \"C:/patches\" -o picked\n"
               "  texx -a 32in24-defswani.txt jimmytex-defswani.txt "
               "--default doom2-defswani.txt\n"
               "  texx -rm texture01.txt texture02.txt -f doom2-textures.txt\n"
               "  texx -t --path \"C:/mymod/patches\"\n"
               "  texx -t --path \"C:/mymod/patches\" -o \"C:/mymod/short\"\n")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-c", "--convert", metavar="INPUT",
                      help="convert one input to a DEUTEX-style text file")
    mode.add_argument("-m", "--merge", metavar="INPUT", nargs="+",
                      help="merge inputs into a file of unique texture definitions")
    mode.add_argument("-s", "--subtract", metavar="INPUT", nargs="+",
                      help="base texturex.txt followed by inputs whose identical "
                           "definitions are removed from it")
    mode.add_argument("-fp", "--findPatches", "--findpatches", metavar="TEXTUREX",
                      dest="findPatches",
                      help="copy patch files used by a texturex.txt out of "
                           "--sourcedir into the output directory")
    mode.add_argument("-a", "--animation", "--animations", metavar="INPUT",
                      nargs="+",
                      help="merge SWANTBLS/defswani switch+animation files into "
                           "--default (which is kept 100%% unchanged); needs --default")
    mode.add_argument("-rm", "--remove", metavar="INPUT", nargs="+",
                      help="remove --filter definitions from each input "
                           "INDEPENDENTLY (no merging); each is saved as "
                           "removed-<original filename> (needs --filter)")
    mode.add_argument("-t", "--truncate", action="store_true",
                      help="recursively truncate filenames over 8 chars "
                           "under --path (needs no INPUT argument)")
    parser.add_argument("-f", "--filter", metavar="INPUT", nargs="+", default=[],
                        help="definitions to exclude from --merge/--subtract/"
                             "--remove output (identical name+layout matches "
                             "are dropped)")
    parser.add_argument("-sd", "--sourcedir", metavar="DIR",
                        help="directory to scan recursively for patch files "
                             "(--findPatches only)")
    parser.add_argument("--default", metavar="DEFAULT",
                        help="base defswani.txt that is reproduced 100%% unchanged "
                             "(--animation only, required)")
    parser.add_argument("-path", "--path", metavar="DIR",
                        help="directory to scan recursively (--truncate only, "
                             "default: current directory)")
    parser.add_argument("-o", "--output", metavar="PATH",
                        help="output file, or output directory for --findPatches/"
                             "--remove/--truncate "
                             "(defaults: texturex.txt / unique-textureX.txt / "
                             "<base>-subtracted.txt / <input>-patches / "
                             "merged-defswani.txt / current directory; for "
                             "--truncate, omitting this renames in place, "
                             "while giving it copies only the truncated files "
                             "into DIR)")
    parser.add_argument("--outputall", metavar="DIR",
                        help="like --output, but copies every file, not just "
                             "the ones that were truncated (--truncate only)")
    args = parser.parse_args()

    if args.sourcedir and not args.findPatches:
        die("--sourcedir only applies to --findPatches")
    if args.filter and not (args.merge or args.subtract or args.remove):
        die("--filter only applies to --merge, --subtract, and --remove")
    if args.default and not args.animation:
        die("--default only applies to --animation")
    if args.path and not args.truncate:
        die("-path/--path only applies to --truncate")
    if args.outputall and not args.truncate:
        die("--outputall only applies to --truncate")
    if args.truncate and args.output and args.outputall:
        if os.path.abspath(args.output) == os.path.abspath(args.outputall):
            die("--output and --outputall cannot be the same directory")

    if args.convert:
        do_convert(args.convert, args.output or "texturex.txt")
    elif args.merge:
        do_merge(args.merge, args.filter, args.output or "unique-textureX.txt")
    elif args.subtract:
        if len(args.subtract) < 2 and not args.filter:
            die("--subtract needs a base file plus at least one other input "
                "(or a --filter)")
        do_subtract(args.subtract, args.filter, args.output)
    elif args.findPatches:
        if not args.sourcedir:
            die("--findPatches requires --sourcedir")
        do_find_patches(args.findPatches, args.sourcedir, args.output)
    elif args.animation:
        if not args.default:
            die("--animation requires --default")
        do_animation(args.animation, args.default, args.output or "merged-defswani.txt")
    elif args.truncate:
        do_truncate(args.path or ".", args.output, args.outputall)
    else:
        if not args.filter:
            die("--remove requires --filter (nothing to remove otherwise)")
        do_remove(args.remove, args.filter, args.output)


if __name__ == "__main__":
    main()