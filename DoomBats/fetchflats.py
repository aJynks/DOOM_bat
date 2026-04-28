"""
fetchflats.py - Scans the current directory (and all subdirs) for PNG files
that are exactly 64x64 pixels, and copies matches to a destination directory.

Usage (via bat wrapper):
    fetchflats -o "dest/path/"
    fetchflats --help

Requires: Pillow
    pip install Pillow
"""

import sys
import os
import re
import shutil

# --- Dependency check ---
try:
    from PIL import Image
except ImportError:
    print("ERROR: Missing required package: Pillow")
    print("Run: pip install Pillow")
    sys.exit(1)

TARGET_SIZE = (64, 64)

FLAG_ALIASES = {
    "-o":       "output",
    "-output":  "output",
}


def parse_args(raw_env):
    """Parse FETCHFLATS_ARGS string. Returns dest_root or None."""
    s = re.sub(r'  +', ' ', raw_env.strip())
    tokens = s.split(' ')
    dest_root = None

    i = 0
    while i < len(tokens):
        tok = tokens[i].lower()
        if tok in FLAG_ALIASES:
            canon = FLAG_ALIASES[tok]
            i += 1
            if canon == "output":
                path_parts = []
                while i < len(tokens) and tokens[i].lower() not in FLAG_ALIASES:
                    path_parts.append(tokens[i])
                    i += 1
                raw_path = " ".join(path_parts).strip().strip('"').strip("'").rstrip("\\")
                dest_root = os.path.abspath(raw_path)
                continue
        i += 1

    return dest_root


def print_help():
    print("""
fetchflats - Copy PNGs that are exactly 64x64 pixels into a destination folder.

USAGE:
  fetchflats -o "dest/path/"
  fetchflats --help

FLAGS:
  -o  / -output  PATH    Destination directory (required).
  --help                 Show this help and exit

EXAMPLES:
  fetchflats -o "D:/out/flats/"
  fetchflats -o "_flats"
  fetchflats -o "..\\_flats"

NOTES:
  - Scans the current directory and all subdirectories
  - Only copies PNGs that are exactly 64x64 pixels
  - Original files are copied byte-for-byte (no re-encoding)
  - Subfolder structure is preserved in the destination
""")


def main():
    raw_env = os.environ.get("FETCHFLATS_ARGS", "").strip()
    if not raw_env:
        raw_env = " ".join(sys.argv[1:])

    tokens_lower = raw_env.lower().split()
    if not raw_env or "--help" in tokens_lower or "-help" in tokens_lower or "-h" in tokens_lower:
        print_help()
        sys.exit(0)

    dest_root = parse_args(raw_env)

    if dest_root is None:
        print("ERROR: -o / -output is required. Specify a destination directory.")
        print('Run: fetchflats --help')
        sys.exit(1)

    src_root = os.getcwd()
    print(f"Source : {src_root}")
    print(f"Dest   : {dest_root}")
    print(f"Size   : {TARGET_SIZE[0]}x{TARGET_SIZE[1]} px")
    print("-" * 60)

    found = skipped = copied = errors = 0

    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [
            d for d in dirnames
            if os.path.abspath(os.path.join(dirpath, d)) != dest_root
        ]
        for filename in filenames:
            if not filename.lower().endswith(".png"):
                continue
            filepath = os.path.join(dirpath, filename)
            found += 1
            try:
                with Image.open(filepath) as img:
                    size = img.size
            except Exception as e:
                print(f"  [SKIP] Could not open: {filepath} ({e})")
                skipped += 1
                continue

            if size == TARGET_SIZE:
                rel_path  = os.path.relpath(filepath, src_root)
                dest_path = os.path.join(dest_root, rel_path)
                try:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(filepath, dest_path)
                    print(f"  [COPY] {rel_path}")
                    copied += 1
                except Exception as e:
                    print(f"  [ERROR] Could not copy {rel_path}: {e}")
                    errors += 1
            else:
                skipped += 1

    print("-" * 60)
    print(f"Scanned : {found} PNG(s)")
    print(f"Copied  : {copied} (64x64 match)")
    print(f"Skipped : {skipped} (wrong size or unreadable)")
    if errors:
        print(f"Errors  : {errors}")
    print("Done.")


if __name__ == "__main__":
    main()