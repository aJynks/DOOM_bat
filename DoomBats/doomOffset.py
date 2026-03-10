#!/usr/bin/env python3
"""
grab2txt.py
Scans the current directory and all subdirectories for PNG files.
For each directory that contains PNGs where at least one has a grAb chunk,
creates/overwrites dimgconv.txt listing:
    FILENAME graphic X Y
for every PNG in that directory (with or without grAb — only those WITH grAb are listed).
"""

import os
import struct


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
                return None  # Not a valid PNG
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
                        x = struct.unpack(">i", chunk_data[0:4])[0]  # signed
                        y = struct.unpack(">i", chunk_data[4:8])[0]  # signed
                        return (x, y)
                if chunk_type == b'IEND':
                    break
    except (IOError, struct.error):
        pass
    return None


def process_directory(dirpath):
    """
    Find all PNG files in dirpath (non-recursive).
    If at least one has a grAb chunk, write dimgconv.txt.
    """
    try:
        entries = os.listdir(dirpath)
    except PermissionError:
        return

    png_files = sorted(
        e for e in entries
        if e.lower().endswith('.png') and os.path.isfile(os.path.join(dirpath, e))
    )

    if not png_files:
        return

    # Gather grAb data for each PNG
    grab_results = {}
    for png in png_files:
        full = os.path.join(dirpath, png)
        result = read_png_grab(full)
        if result is not None:
            grab_results[png] = result

    if not grab_results:
        return  # No grAb chunks found in this dir — skip

    # Write dimgconv.txt
    out_path = os.path.join(dirpath, "dimgconv.txt")
    lines = []
    for png in png_files:
        if png in grab_results:
            x, y = grab_results[png]
            name_no_ext = os.path.splitext(png)[0].upper()
            lines.append(f"{name_no_ext} graphic {x} {y}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  Wrote: {out_path}  ({len(lines)} entries)")


def main():
    start = os.getcwd()
    print(f"Scanning from: {start}\n")

    dirs_processed = 0
    for root, dirs, files in os.walk(start):
        # Sort dirs for consistent traversal order
        dirs.sort()
        process_directory(root)
        dirs_processed += 1

    print(f"\nDone. Scanned {dirs_processed} director{'y' if dirs_processed == 1 else 'ies'}.")


if __name__ == "__main__":
    main()