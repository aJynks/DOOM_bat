#!/usr/bin/env python3
"""
texx.py — TEXTUREx manipulation tool.

Modes:
  texx --convert input [-o out.txt]                        (-c)
      Convert texture definitions to a DoomTools/DEUTEX-style text file.

  texx --merge in1 in2 ... [--filter f ...] [--resolveDups] [-o out]  (-m)
      Merge all inputs into one file of unique texture definitions,
      written out sorted alphabetically by texture name (patch layout
      and order within each texture is untouched)
      (default: unique-textureX.txt).
      True duplicates (identical name+layout across inputs) and
      --filter matches are always written to a side file,
      duplicates-<out>.txt, under their ORIGINAL names, for review.
      --resolveDups additionally writes duplicates-resolved-<out>.txt:
      every true duplicate, renamed so each is unique (first occurrence
      always keeps its name; later ones get renamed). This does NOT
      change unique-textureX.txt itself -- it's a separate file only.

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

def write_deutex(path, textures, mode, inputs, filters, enforce_null=True):
    if enforce_null:
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


def do_merge(input_paths, filter_paths, out_path, resolve_dups):
    # Filter set: name -> {layout: source filter file}
    filter_defs = {}
    for fp in filter_paths:
        batch = load_input(fp)
        print(f"Read {len(batch):>5} definition(s) from filter '{fp}'")
        for t in batch:
            filter_defs.setdefault(t.name, {}).setdefault(t.layout(), fp)

    # Gather all merge textures in command-line order
    all_textures = []
    for ip in input_paths:
        batch = load_input(ip)
        print(f"Read {len(batch):>5} definition(s) from '{ip}'")
        all_textures += batch

    # Reserve every original input name so renames never collide with
    # a texture that appears later in the input stream.
    taken = {t.name for t in all_textures}

    kept_source = {}   # name -> {layout: source of the kept (first) occurrence}
    output = []
    renamed = []             # (old_name, new_name, source) -- diff-layout collisions
    dup_skipped = []         # (texture, kept_source) -- identical dupes, dropped
    filtered_skipped = []    # (texture, filter_source) -- removed by --filter

    for t in all_textures:
        fdefs = filter_defs.get(t.name)
        if fdefs and t.layout() in fdefs:
            filtered_skipped.append((t, fdefs[t.layout()]))
            continue
        seen = kept_source.setdefault(t.name, {})
        if t.layout() in seen:
            dup_skipped.append((t, seen[t.layout()]))
            continue
        if seen:  # same name, different layout -> rename this one
            new_name = make_unique_name(t.name, taken)
            taken.add(new_name)
            renamed.append((t.name, new_name, t.source))
            seen[t.layout()] = t.source
            output.append(Texture(new_name, t.width, t.height, t.patches, t.source))
        else:
            seen[t.layout()] = t.source
            output.append(t)

    output.sort(key=lambda t: t.name)
    write_deutex(out_path, output, "merge", input_paths, filter_paths)

    out_dir = os.path.dirname(out_path)
    stem = os.path.splitext(os.path.basename(out_path))[0]
    base = stem[len("unique-"):] if stem.startswith("unique-") else stem

    # duplicates-textureX.txt: every skipped duplicate + filter-removed
    # definition, kept under its ORIGINAL name, for manual review.
    dupfile_path = None
    dup_report_textures = [t for t, _ in dup_skipped] + [t for t, _ in filtered_skipped]
    if dup_report_textures:
        dupfile_path = os.path.join(out_dir, f"duplicates-{base}.txt")
        dup_out = sorted(dup_report_textures, key=lambda t: t.name)
        write_deutex(dupfile_path, dup_out, "merge (duplicates)",
                     input_paths, filter_paths, enforce_null=False)

    # duplicates-resolved-textureX.txt: only with --resolveDups, only the
    # true duplicates (not filter-removed), renamed so each is unique.
    resolved_path = None
    resolved_renames = []
    if resolve_dups and dup_skipped:
        resolved_out = []
        for t, kept_src in dup_skipped:
            new_name = make_unique_name(t.name, taken)
            taken.add(new_name)
            resolved_renames.append((t.name, new_name, t.source, kept_src))
            resolved_out.append(Texture(new_name, t.width, t.height, t.patches, t.source))
        resolved_out.sort(key=lambda t: t.name)
        resolved_path = os.path.join(out_dir, f"duplicates-resolved-{base}.txt")
        write_deutex(resolved_path, resolved_out, "merge (duplicates resolved)",
                     input_paths, filter_paths, enforce_null=False)

    print()
    if renamed:
        print(f"Renamed {len(renamed)} same-name/different-layout texture(s):")
        for old, new, src in renamed:
            print(f"  {old:<8} -> {new:<8}  (from {src})")
        print()
    if dup_skipped:
        print(f"Skipped {len(dup_skipped)} duplicate(s) "
              f"(identical to a definition already kept):")
        for t, kept_src in dup_skipped:
            print(f"  {t.name:<8} (from {t.source})  -- identical to definition "
                  f"from {kept_src}")
        print()
    if filtered_skipped:
        print(f"Removed {len(filtered_skipped)} definition(s) matched by --filter:")
        for t, filt_src in filtered_skipped:
            print(f"  {t.name:<8} (from {t.source})  -- matches filter "
                  f"'{filt_src}'")
        print()
    if resolved_renames:
        print(f"Resolved {len(resolved_renames)} duplicate(s) via --resolveDups "
              f"(renamed, written to {resolved_path}):")
        for old, new, src, kept_src in resolved_renames:
            print(f"  {old:<8} -> {new:<8}  (from {src}, kept copy from {kept_src})")
        print()

    print(f"{len(all_textures)} definitions in  ->  {len(output)} unique definitions out")
    print(f"  duplicates skipped: {len(dup_skipped)}")
    if filter_paths:
        print(f"  removed by filter:  {len(filtered_skipped)}")
    print(f"Wrote: {out_path}")
    if dupfile_path:
        print(f"Wrote: {dupfile_path}")
    if resolved_path:
        print(f"Wrote: {resolved_path}")


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


# ================================================================ colored --help

def _term_supports_color():
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _enable_windows_vt():
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class _Palette:
    def __init__(self, enabled):
        if enabled:
            self.bold = "\033[1m"
            self.dim = "\033[2m"
            self.head = "\033[1;36m"    # bold cyan -- section headers
            self.flag = "\033[92m"      # bright green -- flag names
            self.req = "\033[93m"       # yellow -- required markers
            self.reset = "\033[0m"
        else:
            self.bold = self.dim = self.head = self.flag = self.req = self.reset = ""


def _help_section(pal, title, blurb, flags):
    lines = [f"{pal.head}{title}{pal.reset}"]
    for b in blurb:
        lines.append(f"  {pal.dim}{b}{pal.reset}")
    lines.append("")
    for flag_text, desc, required in flags:
        marker = f"  {pal.req}(required){pal.reset}" if required else ""
        if flag_text:
            lines.append(f"    {pal.flag}{flag_text:<28}{pal.reset}{desc}{marker}")
        else:
            lines.append(f"    {'':<28}{desc}{marker}")
    lines.append("")
    return "\n".join(lines)


def print_custom_help():
    _enable_windows_vt()
    pal = _Palette(_term_supports_color())
    out = []

    out.append(f"{pal.bold}texx{pal.reset} -- TEXTUREx / DEUTEX manipulation tool")
    out.append("")
    out.append("Six independent modes for building and cleaning up Doom TEXTUREx")
    out.append("definitions and SWANTBLS switch/animation tables. Pick exactly")
    out.append("one mode per run.")
    out.append("")

    out.append(_help_section(
        pal, "CONVERT   (-c, --convert)",
        ["Turn a single WAD, SLADE TEXTURES file, or DEUTEX texturex.txt",
         "into a clean DoomTools/DEUTEX-style text file. Use this to",
         "normalize one source into the text format the other modes expect."],
        [
            ("-c, --convert INPUT", "file/WAD to convert", False),
            ("-o, --output PATH", "default: texturex.txt", False),
        ]))

    out.append(_help_section(
        pal, "MERGE   (-m, --merge)",
        ["Combine several texture sources into one file of unique",
         "definitions -- e.g. stitching multiple community texture packs",
         "into a single set for a megaproject. Output is sorted",
         "alphabetically by texture name; patch layout/order within each",
         "texture is untouched. True duplicates and --filter matches are",
         "written out to a duplicates-<out>.txt side file for review."],
        [
            ("-m, --merge IN [IN...]", "files to merge", False),
            ("-f, --filter IN [IN...]", "drop anything matching these (e.g. doom2.txt)", False),
            ("--resolveDups", "also write duplicates-resolved-<out>.txt with", False),
            ("", "true duplicates renamed uniquely (doesn't touch the", False),
            ("", "main output)", False),
            ("-o, --output PATH", "default: unique-textureX.txt", False),
        ]))

    out.append(_help_section(
        pal, "SUBTRACT   (-s, --subtract)",
        ["Start from one base texturex.txt and strip out any definition",
         "identical (name + layout) to one found in the other inputs or",
         "--filter. Use this to pull IWAD-native textures back out of a",
         "texture file that accidentally included them."],
        [
            ("-s, --subtract BASE IN...", "base file, then files to compare against", False),
            ("-f, --filter IN [IN...]", "additional definitions to remove", False),
            ("-o, --output PATH", "default: <base>-subtracted.txt", False),
        ]))

    out.append(_help_section(
        pal, "REMOVE   (-rm, --remove)",
        ["Like --subtract, but for many files at once, each handled fully",
         "independently -- no merging, no renaming, no cross-file dedup.",
         "Use this to strip IWAD textures out of several map-specific",
         "texture files in one pass, keeping them as separate files."],
        [
            ("-rm, --remove IN [IN...]", "files to clean, each processed on its own", False),
            ("-f, --filter IN [IN...]", "definitions to remove from every input", True),
            ("-o, --output DIR", "default: current directory", False),
        ]))

    out.append(_help_section(
        pal, "FIND PATCHES   (-fp, --findPatches)",
        ["Scan a directory tree and copy out every patch graphic referenced",
         "by a texturex.txt. Use this to collect just the patches a texture",
         "set actually needs out of a much bigger resource folder."],
        [
            ("-fp, --findPatches TEXTUREX", "texture file to read patch names from", False),
            ("-sd, --sourcedir DIR", "directory to scan recursively", True),
            ("-o, --output DIR", "default: <input>-patches", False),
        ]))

    out.append(_help_section(
        pal, "ANIMATION MERGE   (-a, --animation, --animations)",
        ["Merge SWANTBLS/defswani switch + animation definition files",
         "([SWITCHES]/[FLATS]/[TEXTURES]) into one --default file that is",
         "reproduced 100% unchanged. New switches/animations from the",
         "other inputs are appended; anything that conflicts with the",
         "default, or between two inputs, is skipped and written to a",
         "-conflicts.txt side file for manual review instead."],
        [
            ("-a, --animation IN [IN...]", "defswani files to merge in", False),
            ("--default FILE", "base file, kept 100% unchanged", True),
            ("-o, --output PATH", "default: merged-defswani.txt", False),
        ]))

    out.append(f"{pal.head}NOTES{pal.reset}")
    out.append(f"  {pal.dim}Inputs are auto-detected by content, not extension: WAD files{pal.reset}")
    out.append(f"  {pal.dim}(TEXTURE1/TEXTURE2 + PNAMES), SLADE TEXTURES .txt, or DoomTools/{pal.reset}")
    out.append(f"  {pal.dim}DEUTEX .txt. --subtract's base and --findPatches's input must be{pal.reset}")
    out.append(f"  {pal.dim}DoomTools .txt specifically.{pal.reset}")
    out.append("")
    out.append(f"  {pal.dim}Filter semantics (--merge/--subtract/--remove): a definition{pal.reset}")
    out.append(f"  {pal.dim}identical in name AND layout to a filter entry is dropped; a{pal.reset}")
    out.append(f"  {pal.dim}definition with the same name but a DIFFERENT layout is kept{pal.reset}")
    out.append(f"  {pal.dim}under its original name (stock-texture replacement).{pal.reset}")
    out.append("")
    out.append(f"  {pal.dim}Every output enforces {pal.reset}{pal.flag}AASTINKY{pal.reset}{pal.dim} (the null texture,{pal.reset}")
    out.append(f"  {pal.dim}index 0) as the first entry -- moved to the front if present,{pal.reset}")
    out.append(f"  {pal.dim}or synthesized and inserted if missing entirely. (Not applied{pal.reset}")
    out.append(f"  {pal.dim}to --merge's duplicates-*.txt diagnostic side files.){pal.reset}")
    out.append("")

    out.append(f"{pal.head}EXAMPLES{pal.reset}")
    out.append("  texx -c mywad.wad")
    out.append("  texx -c slade-export.txt -o texture1.txt")
    out.append("  texx -m resource.wad map01.wad -f doom2.wad")
    out.append("  texx -m 32in24.txt jimmytex.txt -f doom2.txt --resolveDups")
    out.append("  texx -s mytex.txt other.wad -f doom2.wad")
    out.append("  texx -rm texture01.txt texture02.txt -f doom2-textures.txt")
    out.append("  texx -fp texturex.txt -sd \"C:/patches\" -o picked")
    out.append("  texx -a 32in24-defswani.txt jimmytex-defswani.txt "
                "--default doom2-defswani.txt")
    out.append("")

    print("\n".join(out))


# ================================================================ CLI

def main():
    if any(a in ("-h", "--help", "-help") for a in sys.argv[1:]):
        print_custom_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="texx",
        add_help=False,
        description="TEXTUREx manipulation tool. Run 'texx --help' for full usage.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-c", "--convert", metavar="INPUT",
                      help="convert one input to a DEUTEX-style text file")
    mode.add_argument("-m", "--merge", metavar="INPUT", nargs="+",
                      help="merge inputs into a file of unique texture definitions")
    parser.add_argument("--resolveDups", action="store_true",
                        help="--merge only: also write "
                             "duplicates-resolved-<out>.txt containing every "
                             "true duplicate (identical name+layout), renamed "
                             "so each is unique. Does not change unique-"
                             "textureX.txt itself.")
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
    parser.add_argument("-o", "--output", metavar="PATH",
                        help="output file, or output directory for --findPatches/"
                             "--remove "
                             "(defaults: texturex.txt / unique-textureX.txt / "
                             "<base>-subtracted.txt / <input>-patches / "
                             "merged-defswani.txt / current directory)")
    args = parser.parse_args()

    if args.sourcedir and not args.findPatches:
        die("--sourcedir only applies to --findPatches")
    if args.filter and not (args.merge or args.subtract or args.remove):
        die("--filter only applies to --merge, --subtract, and --remove")
    if args.default and not args.animation:
        die("--default only applies to --animation")
    if args.resolveDups and not args.merge:
        die("--resolveDups only applies to --merge")

    if args.convert:
        do_convert(args.convert, args.output or "texturex.txt")
    elif args.merge:
        do_merge(args.merge, args.filter, args.output or "unique-textureX.txt",
                 args.resolveDups)
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
    else:
        if not args.filter:
            die("--remove requires --filter (nothing to remove otherwise)")
        do_remove(args.remove, args.filter, args.output)


if __name__ == "__main__":
    main()