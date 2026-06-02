#!/usr/bin/env python3
"""
doomOffset.py
Scans the current directory and all subdirectories for PNG and Doom
graphic lump (.lmp) files.

For PNG files: reads the grAb chunk for offsets (x, y).
For LMP files: reads the Doom picture-format header for left/top offsets.

For each directory that contains files with offset data, creates/overwrites
dimgconv.txt listing:
    FILENAME graphic X Y
"""

import os
import struct


# ---------------------------------------------------------------------------
# PNG / grAb
# ---------------------------------------------------------------------------

def read_png_grab(filepath):
    """
    Parse a PNG file and return the (x, y) offset from the grAb chunk,
    or None if no grAb chunk is present.
    grAb values are signed 32-bit big-endian integers.
    """
    try:
        with open(filepath, "rb") as f:
            sig = f.read(8)
            if sig != b'\x89PNG\r\n\x1a\n':
                return None
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                length = struct.unpack(">I", header[:4])[0]
                chunk_type = header[4:8]
                chunk_data = f.read(length)
                f.read(4)  # skip CRC
                if chunk_type == b'grAb':
                    if len(chunk_data) >= 8:
                        x = struct.unpack(">i", chunk_data[0:4])[0]
                        y = struct.unpack(">i", chunk_data[4:8])[0]
                        return (x, y)
                if chunk_type == b'IEND':
                    break
    except (IOError, struct.error):
        pass
    return None


# ---------------------------------------------------------------------------
# Doom picture format / .lmp
# ---------------------------------------------------------------------------

# Sanity bounds — anything outside these is almost certainly not a graphic lump
_MAX_DIM   = 4096
_MAX_OFFSET = 4096

def read_lmp_offsets(filepath):
    """
    Read a Doom picture-format lump and return (left_offset, top_offset),
    or None if the file doesn't look like a valid Doom graphic.

    Doom picture header layout (all little-endian):
        uint16  width
        uint16  height
        int16   left_offset
        int16   top_offset
        uint32  column_offsets[width]   (not read here)

    Minimum file size to be credible: 8 bytes (header) + width * 4 (col ptrs).
    """
    try:
        file_size = os.path.getsize(filepath)
        if file_size < 8:
            return None

        with open(filepath, "rb") as f:
            header = f.read(8)

        w, h, left, top = struct.unpack_from("<HHhh", header)

        # Reject obviously non-graphic lumps
        if w == 0 or h == 0:
            return None
        if w > _MAX_DIM or h > _MAX_DIM:
            return None
        if abs(left) > _MAX_OFFSET or abs(top) > _MAX_OFFSET:
            return None
        # File must be at least large enough to hold the column-pointer table
        if file_size < 8 + w * 4:
            return None

        return (left, top)

    except (IOError, struct.error):
        pass
    return None


# ---------------------------------------------------------------------------
# Directory processing
# ---------------------------------------------------------------------------

def process_directory(dirpath, skip_null=False):
    """
    Find all PNG and LMP files in dirpath (non-recursive).
    For PNG: use grAb chunk, defaulting to (0, 0) if absent.
    For LMP: use Doom picture header; skip if it fails validation.
    Writes dimgconv.txt if any qualifying files remain.

    skip_null: if True, entries with offset (0, 0) are excluded.
    """
    try:
        entries = os.listdir(dirpath)
    except PermissionError:
        return

    png_files = sorted(
        e for e in entries
        if e.lower().endswith('.png') and os.path.isfile(os.path.join(dirpath, e))
    )
    lmp_files = sorted(
        e for e in entries
        if e.lower().endswith('.lmp') and os.path.isfile(os.path.join(dirpath, e))
    )

    if not png_files and not lmp_files:
        return

    offset_results = {}   # filename -> (x, y)

    for png in png_files:
        result = read_png_grab(os.path.join(dirpath, png))
        offset_results[png] = result if result is not None else (0, 0)

    for lmp in lmp_files:
        result = read_lmp_offsets(os.path.join(dirpath, lmp))
        if result is not None:
            offset_results[lmp] = result
        # LMPs that fail validation are silently skipped (not graphic lumps)

    if skip_null:
        offset_results = {f: xy for f, xy in offset_results.items() if xy != (0, 0)}

    if not offset_results:
        return

    # Write dimgconv.txt — sorted alphabetically by filename
    out_path = os.path.join(dirpath, "dimgconv.txt")
    lines = []
    for fname in sorted(offset_results):
        x, y = offset_results[fname]
        name_no_ext = os.path.splitext(fname)[0].upper()
        lines.append(f"{name_no_ext} graphic {x} {y}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  Wrote: {out_path}  ({len(lines)} entries)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract Doom graphic offsets from PNG (grAb) and LMP files."
    )
    parser.add_argument(
        "-skipnull", action="store_true",
        help="Exclude files with null or (0, 0) offsets from the output."
    )
    parser.add_argument(
        "-R", action="store_true",
        help="Recurse into subdirectories, writing a dimgconv.txt per folder."
    )
    args = parser.parse_args()

    start = os.getcwd()
    print(f"Scanning: {start}")
    if args.R:
        print("Mode: recursive")
    if args.skipnull:
        print("Mode: skip null/zero offsets")
    print()

    if args.R:
        dirs_processed = 0
        for root, dirs, files in os.walk(start):
            dirs.sort()
            process_directory(root, skip_null=args.skipnull)
            dirs_processed += 1
        print(f"\nDone. Scanned {dirs_processed} director{'y' if dirs_processed == 1 else 'ies'}.")
    else:
        process_directory(start, skip_null=args.skipnull)
        print("\nDone.")


if __name__ == "__main__":
    main()