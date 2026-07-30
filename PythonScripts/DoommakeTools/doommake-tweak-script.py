#!/usr/bin/env python3
# ==============================================================================
# doommake-tweak-script.py
# ------------------------------------------------------------------------------
# DoomMake Project Tweaker - tweaks a fresh DoomMake project:
#   pre-step IWAD fix + template copy + entry target replacement.
#
# Pure-Python replacement for doommake-tweak.ps1. Called by doommake-tweak.bat
# (thin shim), or runnable directly:
#     py doommake-tweak-script.py [-iwadpath "D:\path\to\doom2.wad"]
#
# The editable lists (file templates, entry deletions, append blocks) live in
# the shared __suite_settings.txt under the "tweak" section, alongside dmake
# and doom.
#
# Template/conf SOURCE files are still resolved next to this script, since
# they belong to the tweaker rather than the suite as a whole.
#
# Pure stdlib. No dependencies.
# ==============================================================================

import os
import re
import sys

from _suite_common import (
    load_settings, require_sections, as_str_list,
    CYN, YEL, GRY, RED, GRN, WHT,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FILE_TEMPLATES  = []
ENTRY_DELETIONS = []
APPEND_BLOCKS   = []


def apply_settings():
    global FILE_TEMPLATES, ENTRY_DELETIONS, APPEND_BLOCKS

    path, data = load_settings()
    require_sections(path, data, ("tweak",))

    tweak = data["tweak"]
    if not isinstance(tweak, dict):
        print(f"Error: {path} 'tweak' must be an object.")
        sys.exit(2)

    missing = [k for k in ("file_templates", "entry_deletions",
                           "append_blocks") if k not in tweak]
    if missing:
        print(f"Error: {path} tweak section is missing: {', '.join(missing)}")
        sys.exit(2)

    templates = tweak["file_templates"]
    if not isinstance(templates, list):
        print(f"Error: {path} tweak.file_templates must be a list.")
        sys.exit(2)

    FILE_TEMPLATES = []
    for entry in templates:
        if not isinstance(entry, dict):
            print(f"Error: {path} each tweak.file_templates entry must be an "
                  f"object with source_file / dest_path / prefix.")
            sys.exit(2)
        FILE_TEMPLATES.append({
            "source_file": str(entry.get("source_file", "")),
            "dest_path":   str(entry.get("dest_path", ".")),
            "prefix":      str(entry.get("prefix", "")),
        })

    ENTRY_DELETIONS = as_str_list(tweak["entry_deletions"])
    APPEND_BLOCKS   = as_str_list(tweak["append_blocks"])


# ==============================================================================
# File IO helpers (UTF-8 without BOM, CRLF preserved as written)
# ==============================================================================
def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace",
              newline="") as f:
        return f.read()


def write_text_no_bom(path, text):
    """Write UTF-8 with no BOM, and no newline translation - the content
    already carries the line endings we want."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# ==============================================================================
# PRE-STEP: Resolve {{PROJECT_IWAD}} placeholder in doommake.properties
# ------------------------------------------------------------------------------
# doommake --project-type creates doommake.properties from a template that
# contains the literal placeholder {{PROJECT_IWAD}}. When piped via stdin the
# value may not be substituted. We accept the real IWAD path as an optional
# argument and patch the file directly before running any doommake commands.
# ==============================================================================
def fix_project_iwad(iwad_path):
    props_path = os.path.join(".", "doommake.properties")
    if not os.path.isfile(props_path):
        return

    try:
        content = read_text(props_path)
    except OSError as e:
        print(RED(f"  [WARNING] Cannot read doommake.properties: {e}"))
        return

    if "{{PROJECT_IWAD}}" not in content:
        return

    # If no path was passed, try to find one already written in the file
    if not iwad_path:
        for raw in content.splitlines():
            if re.match(r"^\s*iwad\s*=", raw) and "{{" not in raw:
                iwad_path = raw.split("=", 1)[1].strip()
                break

    if iwad_path and os.path.exists(iwad_path):
        print(CYN(f"  [Fixing] Replacing {{{{PROJECT_IWAD}}}} -> {iwad_path}"))
        # The properties file is Java-style: backslashes must be escaped.
        content = content.replace("{{PROJECT_IWAD}}",
                                  iwad_path.replace("\\", "\\\\"))
        try:
            write_text_no_bom(props_path, content)
        except OSError as e:
            print(RED(f"  [WARNING] Cannot write doommake.properties: {e}"))
    else:
        print(RED("  [WARNING] {{PROJECT_IWAD}} placeholder found but no valid IWAD path available."))
        print(RED("            Pass it with: doommake-tweak -iwadpath 'D:\\path\\to\\doom2.wad'"))
        print(YEL("            Continuing, but doommake steps may fail..."))


# ==============================================================================
# STEP 2: Copy File Templates
# ==============================================================================
def copy_file_template(source_file, dest_path, prefix):
    dest_filename = source_file.replace(f"doommake-tweak-{prefix}", "")
    source_full   = os.path.join(SCRIPT_DIR, source_file)

    # Conf dest_path values are written Windows-style (".\\src\\decohack").
    # Normalise the separators so the path resolves identically regardless of
    # which slash style the conf uses, and so printed paths look consistent.
    clean_dest = dest_path.replace("\\", os.sep).replace("/", os.sep)
    dest_full  = os.path.normpath(os.path.join(clean_dest, dest_filename))

    if not os.path.isfile(source_full):
        print(RED(f"  [WARNING] Template not found: {source_file}"))
        return

    try:
        dest_dir = os.path.dirname(dest_full)
        if dest_dir and not os.path.isdir(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        with open(source_full, "rb") as src, open(dest_full, "wb") as dst:
            dst.write(src.read())
        print(GRN(f"  [File Created] {dest_full}"))
    except OSError as e:
        print(RED(f"  [WARNING] Could not copy {source_file}: {e}"))


def step_copy_templates():
    print("")
    print(CYN("STEP 2: Creating files from templates..."))

    if not FILE_TEMPLATES:
        print(YEL("  [None] No file templates listed - nothing to copy."))
        return

    for t in FILE_TEMPLATES:
        copy_file_template(t["source_file"], t["dest_path"], t["prefix"])


# ==============================================================================
# STEP 3: Delete Stock Entry Targets
# ------------------------------------------------------------------------------
# The stock `make` and `release` entries call only stock functions, but our
# modified versions call tweak functions (doDehWad, doPalette). RookScript
# requires functions to be defined before they are called, so the modified
# entries must live BELOW the tweak functions. We delete the stock entries
# here; modified versions are re-added at the end of the file in STEP 4.
# The `/**** TARGET: ... ****/` comment block directly above each entry is
# deleted with it, so no orphaned headers are left behind.
# ==============================================================================
SCRIPT_PATH = os.path.join(".", "doommake.script")


def remove_check_entry(entry_name):
    """Delete a `check entry <name>(args) { ... }` block, brace-matched so
    any nesting inside is handled, plus the comment block above it."""
    try:
        content = read_text(SCRIPT_PATH)
    except OSError as e:
        print(RED(f"  [WARNING] Cannot read doommake.script: {e}"))
        return

    m = re.search(r"check entry " + re.escape(entry_name) + r"\(args\)\s*\{",
                  content)
    if not m:
        print(YEL(f"  [Skipped] 'check entry {entry_name}(args)' not found "
                  f"(already deleted?)"))
        return

    # Walk forward from the opening brace, tracking depth
    open_brace = content.index("{", m.start())
    depth = 0
    end_index = -1
    i = open_brace
    while i < len(content):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                end_index = i
                break
        i += 1

    if end_index == -1:
        print(RED(f"  [WARNING] Could not find matching closing brace for "
                  f"'{entry_name}'"))
        return

    # Extend backwards to swallow the /**** TARGET ****/ comment block above,
    # but only if nothing but comment text sits between it and the entry.
    delete_start = m.start()
    comment_start = content.rfind("/****", 0, m.start())
    if comment_start >= 0:
        between = content[comment_start:m.start()]
        if "}" not in between:
            delete_start = comment_start

    content = (content[:delete_start].rstrip()
               + "\r\n\r\n"
               + content[end_index + 1:].lstrip("\r\n"))

    try:
        write_text_no_bom(SCRIPT_PATH, content)
    except OSError as e:
        print(RED(f"  [WARNING] Cannot write doommake.script: {e}"))
        return

    print(GRN(f"  [Deleted] stock entry '{entry_name}'"))


def step_delete_entries():
    print("")
    print(CYN("STEP 3: Deleting stock entry targets..."))

    if not ENTRY_DELETIONS:
        print(YEL("  [None] No entry targets listed - nothing to delete."))
        return

    for name in ENTRY_DELETIONS:
        remove_check_entry(name)


# ==============================================================================
# STEP 4: Append Functions & Entry Targets to doommake.script
# ------------------------------------------------------------------------------
# All tweak blocks are appended to the END of the file in listed order.
# Each conf file's FIRST LINE is a unique marker comment used for duplicate
# detection. It is KEPT in the appended output - that is what makes the
# check work on a re-run: the marker is searched for in doommake.script, and
# the block is skipped if found. (The original PowerShell version stripped
# the marker before appending, so it could never be found again and every
# re-run appended the blocks a second time.) The markers are comments, so
# RookScript ignores them, and they double as a record of which tweak
# blocks are installed.
#
# Banners (START OF TWEAK, MODIFIED STOCK TARGETS, END OF TWEAK) live inside
# the conf files themselves, so nothing is hardcoded here. The modified
# make/release entries are appended last, AFTER the tweak functions they
# call - RookScript requires functions to be defined before their call sites.
# ==============================================================================
def step_append_blocks():
    print("")
    print(CYN("STEP 4: Appending new functions and entry targets..."))

    try:
        content = read_text(SCRIPT_PATH)
    except OSError as e:
        print(RED(f"  [WARNING] Cannot read doommake.script: {e}"))
        return

    appended = 0

    for block in APPEND_BLOCKS:
        conf_path = os.path.join(SCRIPT_DIR, block)

        if not os.path.isfile(conf_path):
            print(RED(f"  [WARNING] Config file not found: {block}"))
            continue

        try:
            lines = re.split(r"\r?\n", read_text(conf_path))
        except OSError as e:
            print(RED(f"  [WARNING] Cannot read {block}: {e}"))
            continue

        if not lines:
            continue

        marker = lines[0].strip()

        # Duplicate detection: if the marker line is already present, skip.
        if marker and marker in content:
            print(YEL(f"  [Skipped] '{block}' already appended (marker found)"))
            continue

        # Append the WHOLE block, marker line included, so the marker is
        # there to be found the next time this runs.
        block_content = "\r\n".join(lines).rstrip()
        content = content.rstrip() + "\r\n\r\n" + block_content + "\r\n"

        print(GRN(f"  [Appended] {block}"))
        appended += 1

    try:
        write_text_no_bom(SCRIPT_PATH, content)
    except OSError as e:
        print(RED(f"  [WARNING] Cannot write doommake.script: {e}"))
        return

    if appended == 0:
        print(YEL("  [None] Nothing new appended."))


# ==============================================================================
# Help
# ==============================================================================
def show_help():
    print("")
    print(CYN("==============================================================================="))
    print(WHT("  DOOMTWEAK  -  DoomMake project tweaker"))
    print(CYN("==============================================================================="))
    print("")
    print("  Tweaks a freshly created DoomMake project:")
    print("    - Patches the {{PROJECT_IWAD}} placeholder in doommake.properties")
    print("    - Copies template files into the project")
    print("    - Deletes the stock make/release entry targets")
    print("    - Appends the tweak functions and modified entry targets")
    print("")
    print(WHT("USAGE"))
    print(GRY("  doommake-tweak [-iwadpath \"D:\\path\\to\\doom2.wad\"]"))
    print("")
    print(WHT("OPTIONS"))
    print(YEL("  -iwadpath f  ") + "IWAD path used to resolve {{PROJECT_IWAD}}")
    print("               " + GRY("(aliases: -iwad, -i; may also be given positionally)"))
    print(YEL("  --help       ") + "Show this help")
    print("")
    print(WHT("NOTES"))
    print(GRY("  - Must be run from the root of a DoomMake project."))
    print(GRY("  - Template and conf source files are read from the folder"))
    print(GRY("    containing this tool."))
    print(GRY("  - The lists of templates, deletions and append blocks are edited"))
    print(GRY("    in __suite_settings.txt under the \"tweak\" section."))
    print(GRY("  - Normally run automatically by 'dmake create'."))
    print("")


# ==============================================================================
# Main
# ==============================================================================
def main(argv):
    iwad_path = ""

    i = 0
    while i < len(argv):
        a = argv[i].lower()
        if a in ("--help", "-help", "/help", "help", "-h", "/?"):
            show_help()
            return 0
        if a in ("-iwadpath", "-iwad", "-i"):
            if i + 1 >= len(argv):
                print(f"Error: {argv[i]} requires a path")
                return 2
            iwad_path = argv[i + 1]
            i += 2
            continue
        # First bare positional is treated as the IWAD path
        if not iwad_path and not a.startswith("-"):
            iwad_path = argv[i]
        i += 1

    apply_settings()

    print("")
    print("===============================================")
    print("=== DoomMake Project Tweaker for MBF21 Wads ===")
    print("===============================================")
    print("")

    # Validate we're in a DoomMake project
    if not os.path.isfile("doommake.script"):
        print(RED("ERROR: doommake.script not found. Are you in a DoomMake "
                  "project root?"))
        return 1

    fix_project_iwad(iwad_path)
    step_copy_templates()
    step_delete_entries()
    step_append_blocks()

    print("")
    print(CYN("=========================================="))
    print(GRN("== Template copy complete. ==============="))
    print(CYN("=========================================="))
    print("")
    return 0


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("")
        sys.exit(130)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
