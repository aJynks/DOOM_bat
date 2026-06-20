#!/usr/bin/env python3
"""
compareImages.py - Remove (or set aside) PNG files in the CURRENT directory
tree that are content-duplicates of any PNG in a reference directory tree.

Matching is by CONTENT ONLY - names are irrelevant. A local file whose
content matches ANY reference file is a duplicate. Same name with different
content is kept (it's an override).

Compare modes:
    default  - byte hash (MD5 of file bytes); exact-file duplicates only
    --pixel  - decoded pixel data via Pillow; catches re-exports that are
               pixel-identical but byte-different

Designed to live on PATH: it always operates on the directory you RUN it
from (os.getcwd()), never on the directory the script file lives in.

USAGE:
    compareImages.py -p <referenceDir>             (dry run - report only)
    compareImages.py -p <referenceDir> --commit    (delete duplicates)
    compareImages.py -p <referenceDir> --save      (move duplicates to .\\_removed\\,
                                                    preserving relative paths)
OPTIONS:
    --pixel    Compare decoded pixels instead of file bytes (needs Pillow).
    --quiet    Only print the summary.
"""

import sys
import os
import argparse
import hashlib

REMOVED_DIRNAME = '_removed'


def dep_check_pixel():
    try:
        import PIL  # noqa
        return True
    except ImportError:
        print("ERROR: --pixel needs Pillow. Install with:  pip install Pillow")
        return False


def byte_hash(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pixel_hash(path):
    """Hash of decoded RGBA pixel data + size; falls back to byte hash."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            im = im.convert('RGBA')
            h = hashlib.md5()
            h.update(f"{im.size[0]}x{im.size[1]}:".encode())
            h.update(im.tobytes())
            return 'px:' + h.hexdigest()
    except Exception as e:
        print(f"  WARN: could not decode {path} ({e}); using byte hash")
        return 'by:' + byte_hash(path)


def collect_pngs(rootdir, exclude_subtrees):
    """Yield full paths of .png files under rootdir, skipping excluded subtrees."""
    rootdir = os.path.abspath(rootdir)
    excl = [os.path.abspath(e) for e in exclude_subtrees]
    for root, dirs, files in os.walk(rootdir):
        absroot = os.path.abspath(root)
        # prune excluded subtrees
        dirs[:] = [d for d in dirs
                   if not any(os.path.join(absroot, d) == e or
                              os.path.join(absroot, d).startswith(e + os.sep)
                              for e in excl)]
        if any(absroot == e or absroot.startswith(e + os.sep) for e in excl):
            continue
        for fname in files:
            if fname.lower().endswith('.png'):
                yield os.path.join(root, fname)


def main():
    ap = argparse.ArgumentParser(
        description="Delete or set aside PNGs in the current dir tree that are "
                    "content-duplicates of PNGs in a reference dir tree.")
    ap.add_argument('-p', '--refdir', required=True,
                    help="Reference directory (searched recursively for .png)")
    ap.add_argument('--commit', action='store_true', help="Delete duplicates")
    ap.add_argument('--save', action='store_true',
                    help=f"Move duplicates to .\\{REMOVED_DIRNAME}\\ preserving paths")
    ap.add_argument('--pixel', action='store_true',
                    help="Compare decoded pixels (needs Pillow) instead of file bytes")
    ap.add_argument('--quiet', action='store_true', help="Only print the summary")
    args = ap.parse_args()

    if args.commit and args.save:
        sys.exit("ERROR: --commit and --save are mutually exclusive - pick one.")
    if args.pixel and not dep_check_pixel():
        sys.exit(1)
    if not os.path.isdir(args.refdir):
        sys.exit(f"ERROR: reference dir not found: {args.refdir}")

    cwd = os.getcwd()                      # the dir the user is in - NOT the script's dir
    refdir = os.path.abspath(args.refdir)
    removed_root = os.path.join(cwd, REMOVED_DIRNAME)

    hasher = pixel_hash if args.pixel else byte_hash

    mode = "COMMIT (delete)" if args.commit else ("SAVE (move)" if args.save else "DRY RUN")
    print(f"[{mode}] compare mode: {'pixel' if args.pixel else 'byte hash'}")
    print(f"Reference: {refdir}")
    print(f"Scanning:  {cwd}")
    print()

    # build reference hash set (sizes first as a cheap pre-filter for byte mode)
    ref_files = list(collect_pngs(refdir, []))
    if not ref_files:
        sys.exit("ERROR: no .png files found in the reference dir. Refusing to run.")
    ref_sizes = {os.path.getsize(p) for p in ref_files}
    ref_hashes = set()
    for p in ref_files:
        ref_hashes.add(hasher(p))
    print(f"Reference set: {len(ref_files)} png files, {len(ref_hashes)} unique contents")

    # scan current tree; exclude _removed always, and the reference subtree if nested
    excludes = [removed_root]
    if refdir == cwd or refdir.startswith(cwd + os.sep):
        excludes.append(refdir)

    matches = []
    kept = 0
    for full in collect_pngs(cwd, excludes):
        if not args.pixel and os.path.getsize(full) not in ref_sizes:
            kept += 1
            continue  # cheap pre-filter: byte-identical implies same size
        if hasher(full) in ref_hashes:
            matches.append(full)
        else:
            kept += 1

    per_dir = {}
    for full in matches:
        per_dir[os.path.dirname(full)] = per_dir.get(os.path.dirname(full), 0) + 1

    verb = "DEL " if args.commit else ("MOVE" if args.save else "dupe")
    done = errors = 0
    for full in sorted(matches):
        rel = os.path.relpath(full, cwd)
        if not args.quiet:
            print(f"  {verb}  {rel}")
        try:
            if args.commit:
                os.remove(full)
                done += 1
            elif args.save:
                dest = os.path.join(removed_root, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if os.path.exists(dest):
                    os.remove(dest)   # re-run: overwrite older set-aside copy
                os.replace(full, dest)
                done += 1
        except OSError as e:
            errors += 1
            print(f"  ERROR on {rel}: {e}")

    print()
    if per_dir:
        print("Per-directory duplicate counts:")
        for d in sorted(per_dir):
            print(f"  {per_dir[d]:5d}   {os.path.relpath(d, cwd)}")
        print()
    action = ("deleted" if args.commit else
              f"moved to {REMOVED_DIRNAME}\\" if args.save else "would be removed")
    print(f"Summary: {kept} kept, {done if (args.commit or args.save) else len(matches)} {action}"
          + (f", {errors} errors" if errors else ""))
    if not (args.commit or args.save) and matches:
        print("\nDRY RUN - nothing changed. Re-run with --commit to delete "
              f"or --save to move into {REMOVED_DIRNAME}\\.")


if __name__ == '__main__':
    main()
