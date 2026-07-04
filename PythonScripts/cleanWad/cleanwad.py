#!/usr/bin/env python3
"""
cleanwad.py — remove duplicate-named lumps from a Doom WAD.

    cleanwad input.wad output.wad

Rules:
  * Name-only comparison (case-insensitive). Content is never compared.
  * The FIRST occurrence of a name is kept; later ones are dropped.
  * Map lump groups are exempt and pass through untouched:
      - Doom-format maps  (header + THINGS/LINEDEFS/.../BLOCKMAP/BEHAVIOR/SCRIPTS)
      - UDMF maps         (header + TEXTMAP ... ENDMAP)
      - GL-node groups    (GL header + GL_VERT/GL_SEGS/GL_SSECT/GL_NODES/GL_PVS)
  * Namespace marker lumps (any name ending in _START or _END, e.g. F_START,
    FF_END, P_START, SS_END, TX_START, HI_END ...) are exempt.
  * Output is a fresh rewrite: original lump order preserved, signature
    (PWAD/IWAD) preserved. Output is written even when no duplicates exist.

Dependencies: none — Python 3 standard library only.
"""

import argparse
import os
import struct
import sys

# ---------------------------------------------------------------- dependency check
# This tool uses only the Python standard library. Nothing to install.
# ----------------------------------------------------------------

HEADER_STRUCT = struct.Struct("<4sii")   # signature, numlumps, dirofs
DIR_STRUCT    = struct.Struct("<ii8s")   # filepos, size, name

# Doom-format map data lumps (contiguous after the map header)
MAP_LUMPS = {
    "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS",
    "NODES", "SECTORS", "REJECT", "BLOCKMAP", "BEHAVIOR", "SCRIPTS",
}

# GL-node lumps (contiguous after a GL header lump)
GL_LUMPS = {"GL_VERT", "GL_SEGS", "GL_SSECT", "GL_NODES", "GL_PVS"}


class Lump:
    __slots__ = ("raw_name", "name", "filepos", "size", "index", "exempt")

    def __init__(self, raw_name, filepos, size, index):
        self.raw_name = raw_name                     # original 8 bytes, preserved on write
        self.name = raw_name.split(b"\x00", 1)[0].decode("ascii", "replace").upper()
        self.filepos = filepos
        self.size = size
        self.index = index
        self.exempt = False


def die(msg):
    print(f"cleanwad: error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_wad(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        die(f"cannot read '{path}': {e}")

    if len(data) < HEADER_STRUCT.size:
        die(f"'{path}' is too small to be a WAD file")

    signature, numlumps, dirofs = HEADER_STRUCT.unpack_from(data, 0)
    if signature not in (b"IWAD", b"PWAD"):
        die(f"'{path}' is not a WAD file (bad signature {signature!r})")
    if numlumps < 0 or dirofs < 0 or dirofs + numlumps * DIR_STRUCT.size > len(data):
        die(f"'{path}' has a corrupt directory (numlumps={numlumps}, dirofs={dirofs})")

    lumps = []
    for i in range(numlumps):
        filepos, size, raw_name = DIR_STRUCT.unpack_from(data, dirofs + i * DIR_STRUCT.size)
        if size < 0 or (size > 0 and (filepos < 0 or filepos + size > len(data))):
            die(f"lump #{i} has data outside the file (filepos={filepos}, size={size})")
        lumps.append(Lump(raw_name, filepos, size, i))

    return signature, data, lumps


def mark_exempt(lumps):
    """Flag map groups, GL-node groups, and namespace markers as exempt."""
    n = len(lumps)
    i = 0
    while i < n:
        nxt = lumps[i + 1].name if i + 1 < n else None

        # UDMF map: header, TEXTMAP, ..., ENDMAP (inclusive)
        if nxt == "TEXTMAP":
            lumps[i].exempt = True
            i += 1
            while i < n:
                lumps[i].exempt = True
                if lumps[i].name == "ENDMAP":
                    break
                i += 1
            i += 1
            continue

        # Doom-format map: header followed by THINGS, then contiguous map lumps
        if nxt == "THINGS":
            lumps[i].exempt = True
            i += 1
            while i < n and lumps[i].name in MAP_LUMPS:
                lumps[i].exempt = True
                i += 1
            continue

        # GL-node group: header followed by GL_VERT, then contiguous GL lumps
        if nxt == "GL_VERT":
            lumps[i].exempt = True
            i += 1
            while i < n and lumps[i].name in GL_LUMPS:
                lumps[i].exempt = True
                i += 1
            continue

        # Namespace markers
        if lumps[i].name.endswith("_START") or lumps[i].name.endswith("_END"):
            lumps[i].exempt = True

        i += 1


def dedup(lumps):
    """Keep-first dedup over non-exempt lumps. Returns (kept, removed)."""
    seen = set()
    kept, removed = [], []
    for lump in lumps:
        if lump.exempt:
            kept.append(lump)
            continue
        if lump.name in seen:
            removed.append(lump)
        else:
            seen.add(lump.name)
            kept.append(lump)
    return kept, removed


def write_wad(path, signature, src_data, kept):
    body = bytearray()
    directory = bytearray()
    offset = HEADER_STRUCT.size

    for lump in kept:
        if lump.size > 0:
            body += src_data[lump.filepos:lump.filepos + lump.size]
        directory += DIR_STRUCT.pack(offset if lump.size > 0 else 0,
                                     lump.size, lump.raw_name)
        offset += lump.size

    header = HEADER_STRUCT.pack(signature, len(kept), HEADER_STRUCT.size + len(body))
    try:
        with open(path, "wb") as f:
            f.write(header)
            f.write(body)
            f.write(directory)
    except OSError as e:
        die(f"cannot write '{path}': {e}")


def main():
    parser = argparse.ArgumentParser(
        prog="cleanwad",
        description="Remove duplicate-named lumps from a WAD (keep first occurrence). "
                    "Map groups and namespace markers are never touched.")
    parser.add_argument("input", help="source WAD file")
    parser.add_argument("output", help="cleaned WAD file to write")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        die(f"input file '{args.input}' does not exist")

    in_abs = os.path.abspath(args.input)
    out_abs = os.path.abspath(args.output)
    if in_abs == out_abs or (os.path.exists(out_abs) and os.path.samefile(in_abs, out_abs)):
        die("input and output must be different files")

    signature, data, lumps = read_wad(args.input)
    mark_exempt(lumps)
    kept, removed = dedup(lumps)
    write_wad(args.output, signature, data, kept)

    if removed:
        print(f"Removed {len(removed)} duplicate lump(s):")
        for lump in removed:
            print(f"  {lump.name:<8}  index {lump.index:>5}  {lump.size:>9} bytes")
        saved = sum(l.size for l in removed)
        print(f"\n{len(lumps)} lumps in  ->  {len(kept)} lumps out  ({saved} bytes of lump data removed)")
    else:
        print(f"No duplicate lump names found ({len(lumps)} lumps).")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
