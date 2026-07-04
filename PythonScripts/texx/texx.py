#!/usr/bin/env python3
"""
texx.py — TEXTUREx manipulation tool.

Modes:
  texx --convert input [-o out.txt]                        (-c)
      Convert texture definitions to a DoomTools/DEUTEX-style text file.

  texx --compare in1 in2 ... [--filter f ...] [-o out]     (-cmp)
      Merge all inputs into one file of unique texture definitions
      (default: unique-textureX.txt).

  texx --subtract base.txt other1 ... [--filter f ...]     (-sub)
      Copy of base.txt with every texture removed that is identical
      (name + layout) to a definition in the others or the filter
      (default output: <basestem>-subtracted.txt).

  texx --findPatches texturex.txt --sourcedir DIR [-o DIR] (-fp)
      Recursively scan a directory and COPY every file whose name matches
      a patch referenced by the texture file into the output directory
      (default: <inputstem>-patches). Existing files are overwritten.

Accepted inputs (auto-detected by content, not extension):
  * WAD file            — all TEXTURE1/TEXTURE2 lumps (PNAMES read from the
                          same WAD; Doom and Strife binary formats detected)
  * SLADE TEXTURES txt  — WallTexture "NAME", W, H { Patch "NAME", x, y }
  * DoomTools/DEUTEX txt — NAME W H  /  *<tab>PATCH X Y

Compare rules:
  * Texture identity = name + width/height + full patch layout
    (patch names, order, X/Y offsets).
  * Identical name+layout seen again  -> skipped (first input wins).
  * Same name, different layout       -> kept, renamed: trailing number is
    incremented (stem truncated if 8 chars would be exceeded, e.g.
    TESTIT99 -> TESTI100); names without a trailing number get one appended.
  * --filter inputs: any compare texture identical (name+layout) to a filter
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


def do_compare(input_paths, filter_paths, out_path):
    # Filter set: name -> set of layouts
    filter_defs = {}
    for fp in filter_paths:
        for t in load_input(fp):
            filter_defs.setdefault(t.name, set()).add(t.layout())

    # Gather all compare textures in command-line order
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

    write_deutex(out_path, output, "compare", input_paths, filter_paths)

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
               "  texx -cmp resource.wad map01.wad -f doom2.wad\n"
               "  texx -sub mytex.txt other.wad -f doom2.wad\n"
               "  texx -fp texturex.txt -sd \"C:/patches\" -o picked\n")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-c", "--convert", metavar="INPUT",
                      help="convert one input to a DEUTEX-style text file")
    mode.add_argument("-cmp", "--compare", metavar="INPUT", nargs="+",
                      help="merge inputs into a file of unique texture definitions")
    mode.add_argument("-sub", "--subtract", metavar="INPUT", nargs="+",
                      help="base texturex.txt followed by inputs whose identical "
                           "definitions are removed from it")
    mode.add_argument("-fp", "--findPatches", "--findpatches", metavar="TEXTUREX",
                      dest="findPatches",
                      help="copy patch files used by a texturex.txt out of "
                           "--sourcedir into the output directory")
    parser.add_argument("-f", "--filter", metavar="INPUT", nargs="+", default=[],
                        help="definitions to exclude from --compare/--subtract "
                             "output (identical name+layout matches are dropped)")
    parser.add_argument("-sd", "--sourcedir", metavar="DIR",
                        help="directory to scan recursively for patch files "
                             "(--findPatches only)")
    parser.add_argument("-o", "--output", metavar="PATH",
                        help="output file, or output directory for --findPatches "
                             "(defaults: texturex.txt / unique-textureX.txt / "
                             "<base>-subtracted.txt / <input>-patches)")
    args = parser.parse_args()

    if args.sourcedir and not args.findPatches:
        die("--sourcedir only applies to --findPatches")
    if args.filter and not (args.compare or args.subtract):
        die("--filter only applies to --compare and --subtract")

    if args.convert:
        do_convert(args.convert, args.output or "texturex.txt")
    elif args.compare:
        do_compare(args.compare, args.filter, args.output or "unique-textureX.txt")
    elif args.subtract:
        if len(args.subtract) < 2 and not args.filter:
            die("--subtract needs a base file plus at least one other input "
                "(or a --filter)")
        do_subtract(args.subtract, args.filter, args.output)
    else:
        if not args.sourcedir:
            die("--findPatches requires --sourcedir")
        do_find_patches(args.findPatches, args.sourcedir, args.output)


if __name__ == "__main__":
    main()
