"""
textureX_gen.py
Scans the current directory and all subfolders for image files.
In each folder containing at least one image, writes a _textureX.txt
with entries in the format:

name width height
*   name 0 0

Usage:
  textureX_gen           -- generate _textureX.txt files
  textureX_gen --clean   -- delete all _textureX.txt files found

Dependencies: Pillow
Install: pip install Pillow
"""

import sys
import subprocess

# ── dependency check ────────────────────────────────────────────────────────
try:
    from PIL import Image
except ImportError:
    print("Pillow not found. Installing: pip install Pillow")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image

import os
import argparse

# ── config ───────────────────────────────────────────────────────────────────
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tga", ".tiff", ".tif",
    ".webp", ".pcx", ".ppm", ".pgm", ".pbm", ".ico", ".dds",
}
OUTPUT_FILENAME = "_textureX.txt"


def get_image_files(folder):
    """Return a sorted list of image filenames (no subfolders) in folder."""
    entries = []
    try:
        for f in os.listdir(folder):
            if os.path.isfile(os.path.join(folder, f)):
                ext = os.path.splitext(f)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    entries.append(f)
    except PermissionError:
        pass
    return sorted(entries)


def get_image_size(filepath):
    """Return (width, height) for an image, or (0, 0) on failure."""
    try:
        with Image.open(filepath) as img:
            return img.size  # (width, height)
    except Exception:
        return (0, 0)


def write_texture_file(folder, image_files):
    """Write _textureX.txt into folder for the given image file list."""
    out_path = os.path.join(folder, OUTPUT_FILENAME)
    lines = []

    for i, filename in enumerate(image_files):
        stem = os.path.splitext(filename)[0]
        filepath = os.path.join(folder, filename)
        w, h = get_image_size(filepath)

        lines.append(f"{stem} {w} {h}")
        lines.append(f"*   {stem} 0 0")

        # blank line between entries (not after the last one)
        if i < len(image_files) - 1:
            lines.append("")

    content = "\n".join(lines) + "\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    return out_path


def clean(root):
    """Delete all _textureX.txt files found under root."""
    print(f"Cleaning from: {root}\n")
    deleted = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        if OUTPUT_FILENAME in filenames:
            target = os.path.join(dirpath, OUTPUT_FILENAME)
            try:
                os.remove(target)
                rel = os.path.relpath(target, root)
                print(f"  Deleted  {rel}")
                deleted += 1
            except Exception as e:
                print(f"  ERROR deleting {target}: {e}")

    print(f"\nDone. {deleted} file(s) deleted.")


def generate(root):
    """Generate _textureX.txt files in every folder that contains images."""
    print(f"Scanning from: {root}\n")
    processed = 0

    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        images = get_image_files(dirpath)
        if not images:
            continue

        out = write_texture_file(dirpath, images)
        rel = os.path.relpath(out, root)
        print(f"  [{len(images):3d} image(s)]  {rel}")
        processed += 1

    print(f"\nDone. {OUTPUT_FILENAME} written in {processed} folder(s).")


def main():
    parser = argparse.ArgumentParser(
        description="Generate or clean _textureX.txt image listing files."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help=f"Delete all {OUTPUT_FILENAME} files found in this dir and subfolders.",
    )
    args = parser.parse_args()

    root = os.getcwd()

    if args.clean:
        clean(root)
    else:
        generate(root)


if __name__ == "__main__":
    main()