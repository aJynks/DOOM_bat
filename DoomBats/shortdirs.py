"""
shortdirs.py - Renames directories in the current dir (and subdirs) so that
all folder names are max 8 characters, using smart shortening.

Shortening strategy (applied in order until <= 8 chars):
  1. Already short enough - leave alone
  2. Remove non-leading vowels (Textures -> Txtrs)
  3. Preserve leading chars + numeric suffix, compress middle
  4. Hard truncate to 8 chars as last resort
  Conflicts (two names -> same result) get a numeric suffix: Name -> Nam0001

Usage (via bat wrapper):
    shortdirs                  (rename for real)
    shortdirs -dry             (dry run, no changes made)
    shortdirs --help

No other flags needed - always operates on current directory.
"""

import sys
import os
import re

MAX_LEN = 8


# ---------------------------------------------------------------------------
# Smart shortening
# ---------------------------------------------------------------------------

VOWELS = set('aeiouAEIOU')


def clean(name):
    """Remove spaces and any non-alphanumeric characters (Doom naming rules)."""
    return re.sub(r'[^A-Za-z0-9]', '', name)


def strip_vowels(name):
    """Remove non-leading vowels from name."""
    if not name:
        return name
    return name[0] + re.sub(r'[aeiou]', '', name[1:], flags=re.IGNORECASE)


def shorten(name):
    """
    Shorten a directory name to MAX_LEN chars using smart strategies.
    1. Strip spaces and special characters (alphanumeric only)
    2. If still too long, preserve trailing numeric suffix
    3. Strip non-leading vowels from base
    4. Hard truncate as last resort
    """
    # Step 1: clean to alphanumeric only
    name = clean(name)

    # Already short enough after cleaning
    if len(name) <= MAX_LEN:
        return name

    # Step 2: split off trailing numeric suffix to always preserve it
    m = re.match(r'^(.*?)(\d+)$', name)
    base, suffix = (m.group(1), m.group(2)) if m else (name, '')

    budget = MAX_LEN - len(suffix)
    if budget <= 0:
        return name[:MAX_LEN]

    # Step 3: strip vowels from base
    shortened_base = strip_vowels(base)

    # Step 4: hard truncate to budget
    return shortened_base[:budget] + suffix


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------

def resolve_conflicts(rename_map):
    """
    rename_map: dict of { original_name -> proposed_short_name }
    Returns a new dict with conflicts resolved by appending a numeric suffix.
    The suffix replaces the last N chars to stay within MAX_LEN.
    """
    # Group originals by their proposed short name
    from collections import defaultdict
    by_short = defaultdict(list)
    for orig, short in rename_map.items():
        by_short[short].append(orig)

    resolved = {}
    for short, originals in by_short.items():
        if len(originals) == 1:
            resolved[originals[0]] = short
        else:
            # Multiple originals map to the same short name - number them
            for idx, orig in enumerate(sorted(originals), start=1):
                suffix = str(idx).zfill(4)              # e.g. "0001"
                base   = short[:MAX_LEN - len(suffix)]  # trim base to fit
                resolved[orig] = base + suffix

    return resolved


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

def print_help():
    print("""
shortdirs - Rename folders to max 8 characters using smart shortening.

USAGE:
  shortdirs          Rename directories for real
  shortdirs -dry     Dry run - show proposed renames without making changes
  shortdirs --help   Show this help and exit

SHORTENING STRATEGY:
  1. Names already <= 8 chars are left untouched
  2. Non-leading vowels are stripped  (Textures -> Txtrs)
  3. Trailing numbers are always preserved  (Walls01 -> Wlls01)
  4. Hard truncation as last resort
  5. Conflicts get a numeric suffix  (TxtrsWll -> Txt0001, Txt0002)

NOTES:
  - Operates on the current directory and all subdirectories
  - Renames are done deepest-first so parent renames don't break child paths
  - Case is preserved
  - Use -dry first to preview changes before committing
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    raw_env = os.environ.get("SHORTDIRS_ARGS", "").strip()
    if not raw_env:
        raw_env = " ".join(sys.argv[1:])

    tokens = raw_env.lower().split()
    if "--help" in tokens or "-help" in tokens or "-h" in tokens:
        print_help()
        sys.exit(0)

    dry_run = "-dry" in tokens or "--dry" in tokens

    src_root = os.getcwd()
    print(f"Root    : {src_root}")
    print(f"Mode    : {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (renaming for real)'}")
    print("-" * 60)

    # Collect all directories, deepest first so we rename leaves before parents
    all_dirs = []
    for dirpath, dirnames, _ in os.walk(src_root, topdown=False):
        for d in dirnames:
            all_dirs.append((dirpath, d))

    # Filter to only those needing shortening
    needs_rename = [(parent, d) for parent, d in all_dirs if shorten(d) != d]

    if not needs_rename:
        print("No directory names exceed 8 characters. Nothing to do.")
        sys.exit(0)

    # Build rename map per parent directory (conflicts are per-parent)
    # Group by parent
    from collections import defaultdict
    by_parent = defaultdict(dict)
    for parent, d in needs_rename:
        by_parent[parent][d] = shorten(d)

    # Resolve conflicts within each parent
    final_map = {}  # (parent, original) -> new_name
    for parent, rename_map in by_parent.items():
        resolved = resolve_conflicts(rename_map)
        for orig, new in resolved.items():
            final_map[(parent, orig)] = new

    # Display plan
    skipped = renamed = errors = 0
    changes = [(p, o, n) for (p, o), n in final_map.items() if o != n]
    for (parent, orig), new in sorted(final_map.items()):
        if orig == new:
            continue
        rel_parent = os.path.relpath(parent, src_root) if parent != src_root else '.'
        print(f"  {rel_parent}\\{orig}  ->  {new}")

    print("-" * 60)
    print(f"To rename : {len(changes)}")

    if dry_run:
        print("\nDry run complete. No changes made. Run without -dry to apply.")
        sys.exit(0)

    if not changes:
        print("Nothing to rename.")
        sys.exit(0)

    # Confirm
    print()
    answer = input("Proceed with renaming? [y/N]: ").strip().lower()
    if answer != 'y':
        print("Aborted.")
        sys.exit(0)

    # Apply renames deepest-first (all_dirs is already deepest-first from topdown=False)
    for (parent, orig), new in final_map.items():
        if orig == new:
            continue
        src = os.path.join(parent, orig)
        dst = os.path.join(parent, new)
        if not os.path.exists(src):
            print(f"  [SKIP]  {src} (no longer exists, possibly already renamed)")
            skipped += 1
            continue
        if os.path.exists(dst):
            print(f"  [SKIP]  {orig} -> {new} (destination already exists)")
            skipped += 1
            continue
        try:
            os.rename(src, dst)
            print(f"  [DONE]  {orig} -> {new}")
            renamed += 1
        except Exception as e:
            print(f"  [ERROR] {orig} -> {new}: {e}")
            errors += 1

    print("-" * 60)
    print(f"Renamed : {renamed}")
    if skipped:
        print(f"Skipped : {skipped}")
    if errors:
        print(f"Errors  : {errors}")
    print("Done.")


if __name__ == "__main__":
    main()