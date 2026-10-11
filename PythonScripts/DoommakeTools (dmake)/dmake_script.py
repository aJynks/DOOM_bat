#!/usr/bin/env python3
# ==============================================================================
# dmake_script.py
# ------------------------------------------------------------------------------
# Wrapper for doommake with optional post-run of doom.bat
#
# Pure-Python replacement for dmakeScript.ps1. Called by dmake.bat (thin shim),
# or runnable directly:  py dmake_script.py [args...]
#
# Behaviour:
#   - If ANY argument is "update":
#       Run doomtools --update && --update-cleanup && --update-shell && --update-docs
#       Ignore all other arguments
#   - If ANY argument is "create":    Enter create mode (standalone)
#   - If ANY argument is "explode":   Enter explode mode (standalone)
#   - If ANY argument is "watch":     Enter watch mode (standalone)
#   - If ANY argument is "texturex":  Enter texturex mode (standalone)
#   - If ANY argument is "editpatch": Enter editpatch mode (standalone)
#   - If ANY argument is "strip":     Enter strip mode (standalone; WAD lump
#                                     stripper)
#   - If ANY argument is "conform2palette":
#                                     Enter conform2palette mode (standalone;
#                                     repalettes every graphic in a WAD to a
#                                     new palette - native)
#   - If ANY argument is "--targets": Show the targets help (standalone)
#   - Arguments before "--" are passed to doommake
#   - If "--" is present, doom.bat is run after doommake
#   - Arguments after "--" are passed to doom.bat
#   - If doommake returns non-zero, doom.bat will NOT run
#
# Notes vs the old dmakeScript.ps1:
#   - Functionally identical; "strip" (formerly "clean") no longer needs the
#     external dmake_clean.py worker - the WAD stripping is native here.
#   - Paths/filenames containing spaces and parentheses ( ) work correctly.
#     Files on disk are never renamed; only the DERIVED project name in explode
#     mode is sanitised (spaces -> underscores).
#   - Directory paths work with or without a trailing \ or /.
#   - When "create -d" changes directory, the change is propagated back to the
#     calling cmd shell via the DMAKE_CD_FILE env var (set by dmake.bat).
#   - Shared editable data lives in __suite_settings.txt, loaded via
#     _suite_common.py. Sibling suite tools (doommake-tweak, doom) are .bat/.py.
#
# Pure stdlib. No dependencies.
# ==============================================================================

import locale
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib

from _suite_common import (
    load_settings, require_sections, as_str_dict, as_str_list,
    find_on_path, resolve_cmd, run_cmd,
    full_path, normalize_dirpath,
    WHT, CYN, DCYN, YEL, GRY, DGRY, RED, GRN,
)

# ==============================================================================
# Settings - loaded from __suite_settings.txt (found on PATH)
# ------------------------------------------------------------------------------
# All editable data (IWAD paths, hack types, clean strip sets, defaults) lives
# in __suite_settings.txt, shared with doom_script.py and
# doommake-tweak-script.py.
# The variables below are populated by apply_settings() at startup.
# ==============================================================================
IWADS          = {}
IWAD_LIST      = ""
HACK_TYPES     = []
HACK_TYPE_LIST = ""
CLEAN_STRIP_SETS = {}   # flag-name (lowercase) -> list of lump names, from conf
DEFAULTS       = {}

# ==============================================================================
# Helpers
# ==============================================================================

def sanitize_project_name(name):
    """Sanitise a derived project name: spaces become underscores.
    Parentheses are legal in directory names and are left untouched."""
    return name.replace(" ", "_")


def publish_cd_out(directory):
    """Propagate a directory change back to the calling cmd shell (via
    dmake.bat's DMAKE_CD_FILE handshake). No-op when the env var is absent."""
    cd_file = os.environ.get("DMAKE_CD_FILE")
    if cd_file:
        enc = locale.getpreferredencoding(False)
        try:
            with open(cd_file, "w", encoding=enc, newline="") as f:
                f.write(directory)
        except OSError as e:
            print(f"Warning: could not write CD handshake file: {e}")


def test_dir_empty(path):
    """True if the directory is empty, or doesn't exist yet (nothing to
    conflict with). Used to guard "create" so it never runs into an occupied
    folder."""
    if not os.path.exists(path):
        return True
    try:
        return len(os.listdir(path)) == 0
    except OSError:
        return False


def assert_project_root(cmd_name):
    """Verify we are in a DoomTools project root; exit 2 if not."""
    for f in ("doommake.script", "doommake.project.properties",
              "doommake.properties"):
        if not os.path.isfile(f):
            print(f"Error: {f} not found in current directory.")
            print(f"{cmd_name} must be run from the root of a DoomTools project.")
            sys.exit(2)


def apply_settings():
    """Populate the module-level settings variables from the shared conf."""
    global IWADS, IWAD_LIST, HACK_TYPES, HACK_TYPE_LIST
    global CLEAN_STRIP_SETS, DEFAULTS

    path, data = load_settings()
    require_sections(path, data,
                     ("iwads", "hack_types", "clean_strip_sets", "defaults"))

    strips = data["clean_strip_sets"]
    if not isinstance(strips, dict) or not strips:
        print(f"Error: {path} clean_strip_sets must be a non-empty object of "
              f"flag-name -> list-of-lump-names.")
        sys.exit(2)

    # Every key becomes a --<key> flag for "dmake strip". No key is special;
    # texturex/anims/deco/info/clean are just the ones that ship by default.
    # Keyed lowercase so flag matching is case-insensitive.
    CLEAN_STRIP_SETS = {}
    for name, lumps in strips.items():
        CLEAN_STRIP_SETS[str(name).lower()] = as_str_list(lumps)

    IWADS          = as_str_dict(data["iwads"])
    IWAD_LIST      = ", ".join(IWADS.keys())
    HACK_TYPES     = as_str_list(data["hack_types"])
    HACK_TYPE_LIST = ", ".join(HACK_TYPES)
    DEFAULTS       = dict(data["defaults"])


# ==============================================================================
# Mode: update  (standalone; ignores all other args)
# ==============================================================================
def invoke_update_mode():
    for flag in ("--update", "--update-cleanup", "--update-shell",
                 "--update-docs"):
        err = run_cmd("doomtools", [flag])
        if err != 0:
            sys.exit(err)
    sys.exit(0)


# ==============================================================================
# Mode: create  (standalone)
#   dmake create [ProjectName] [-i/-iwad iwad] [-h/-hacktype hacktype]
#                              [-d/-directory folder] [-nodeco]
#
#   Defaults (used for anything not given):
#     ProjectName   megawad
#     directory     ./_DT_Projects/_Current
#     iwad          doom2
#     hacktype      dsdhacked  (ignored/omitted if -nodeco is given)
#
#   -nodeco drops the decohack module entirely (no DEHACKED patch at all).
#   -h/-hacktype and -nodeco together is an error - they contradict.
# ==============================================================================
def invoke_create_mode(rest):
    iwad_name    = DEFAULTS.get("create_iwad", "doom2")
    hack_type    = DEFAULTS.get("create_hacktype", "dsdhacked")
    dir_name     = DEFAULTS.get("create_directory", "./_DT_Projects/_Current")
    default_name = DEFAULTS.get("create_name", "megawad")
    no_deco      = False
    hacktype_set = False

    IWAD_FLAGS     = ("-i", "-iwad")
    HACKTYPE_FLAGS = ("-h", "-hacktype")
    DIR_FLAGS      = ("-d", "-directory")

    # A leading token that isn't a recognised flag is the project name;
    # otherwise the name defaults (create_name) and parsing starts at rest[0].
    if rest and rest[0] and rest[0].lower() not in (
            IWAD_FLAGS + HACKTYPE_FLAGS + DIR_FLAGS + ("-nodeco",)):
        project_name = rest[0]
        i = 1
    else:
        project_name = default_name
        i = 0

    while i < len(rest):
        a = rest[i].lower()
        if a in IWAD_FLAGS:
            if i + 1 >= len(rest):
                print(f"Error: {rest[i]} requires an IWAD name")
                sys.exit(2)
            iwad_name = rest[i + 1]
            i += 2
        elif a in HACKTYPE_FLAGS:
            if i + 1 >= len(rest):
                print(f"Error: {rest[i]} requires a hack type")
                sys.exit(2)
            hack_type = rest[i + 1]
            hacktype_set = True
            i += 2
        elif a in DIR_FLAGS:
            if i + 1 >= len(rest):
                print(f"Error: {rest[i]} requires a directory name")
                sys.exit(2)
            dir_name = normalize_dirpath(rest[i + 1])
            i += 2
        elif a == "-nodeco":
            no_deco = True
            i += 1
        else:
            i += 1  # Unknown argument - skip it

    if no_deco and hacktype_set:
        print("Error: -h/-hacktype sets a DECOHack patch type, but -nodeco removes")
        print("the decohack module entirely. Use one or the other, not both.")
        sys.exit(2)

    # Guard: never touch a non-empty target directory. Checked first, before
    # anything else runs (no doommake, no directory creation, no tweak).
    target_dir = dir_name if dir_name else os.getcwd()

    if not test_dir_empty(target_dir):
        print(f"Error: Directory is not empty: {target_dir}")
        print("dmake create requires an empty target directory.")
        sys.exit(2)

    iwad_path = IWADS.get(iwad_name)

    print("I am in create mode")
    print("")
    print(f"Project Name : {project_name}")
    print(f"IWAD Path    : {iwad_path if iwad_path else ''}")
    if no_deco:
        print("Hack Type    : (none - no decohack module)")
    else:
        print(f"Hack Type    : {hack_type}")
    print(f"Directory    : {dir_name}")
    print("")

    if not iwad_path:
        print(f"Error: IWAD path not found for: {iwad_name}")
        print(f"Available IWADs: {IWAD_LIST}")
        sys.exit(2)

    if not no_deco and hack_type not in HACK_TYPES:
        print(f"Error: Unknown hack type: {hack_type}")
        print(f"Available hack types: {HACK_TYPE_LIST}")
        sys.exit(2)

    if dir_name:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        os.chdir(dir_name)

    # Feed the interactive prompts via stdin. doommake only prompts for a
    # patch type when the decohack module is present, so the feed is
    # shorter (no third line) when -nodeco is set.
    modules = ["assets", "maps", "texturesboom"] if no_deco \
              else ["assets", "maps", "decohack", "texturesboom"]
    feed = f"{project_name}\n{iwad_path}\n" if no_deco \
           else f"{project_name}\n{iwad_path}\n{hack_type}\n"
    create_err = run_cmd("doommake",
                         ["--project-type", "wad", "./", "-n"] + modules,
                         feed=feed)

    if create_err != 0:
        print(RED(f"Error: doommake --project-type failed (exit {create_err}). Skipping tweak."))
        if dir_name:
            publish_cd_out(os.getcwd())
        sys.exit(create_err)

    tweak_err = run_cmd("doommake-tweak", ["-iwadpath", iwad_path])

    if tweak_err != 0:
        print(RED(f"Error: doommake-tweak failed (exit {tweak_err}). Skipping doommake complete."))
        if dir_name:
            publish_cd_out(os.getcwd())
        sys.exit(tweak_err)

    err = run_cmd("doommake", ["complete"])

    if dir_name:
        # Leave the calling shell inside the new directory (matches old dmake.bat)
        publish_cd_out(os.getcwd())

    sys.exit(err)


# ==============================================================================
# Mode: explode  (standalone)
#   dmake explode filename.wad [-i iwad] [-p]
# ==============================================================================
def invoke_explode_mode(rest):
    iwad_name   = DEFAULTS.get("create_iwad", "doom2")
    use_wad_pal = False

    if not rest or not rest[0]:
        print("Error: WAD filename required")
        print("Usage: dmake explode filename.wad [-i iwad]")
        sys.exit(2)

    explode_wad = rest[0]
    i = 1
    while i < len(rest):
        a = rest[i].lower()
        if a == "-i":
            if i + 1 >= len(rest):
                print("Error: -i requires an IWAD name")
                sys.exit(2)
            iwad_name = rest[i + 1]
            i += 2
        elif a == "-p":
            use_wad_pal = True
            i += 1
        else:
            i += 1  # Unknown argument - skip it

    iwad_path = IWADS.get(iwad_name)

    # Derive project name from the WAD filename.
    # The file on disk is NEVER renamed - spaces and ( ) in the real path are
    # fine. Only the derived name is sanitised: spaces -> underscores.
    stem         = os.path.splitext(os.path.basename(explode_wad))[0]
    clean_stem   = sanitize_project_name(stem)
    project_name = f"_{clean_stem}"

    print("I am in explode mode")
    print("")
    print(f"WAD File     : {explode_wad}")
    print(f"Project Name : {project_name}")
    if use_wad_pal:
        print(f"PLAYPAL      : {explode_wad} (from input WAD)")
    else:
        print(f"IWAD Path    : {iwad_path if iwad_path else ''}")
    print("")

    if not iwad_path:
        print(f"Error: IWAD path not found for: {iwad_name}")
        print(f"Available IWADs: {IWAD_LIST}")
        sys.exit(2)

    palette = explode_wad if use_wad_pal else iwad_path

    # Feed the interactive prompts (name, IWAD, patch type) via stdin
    feed = f"{clean_stem}\n{iwad_path}\ndsdhacked\n"
    err = run_cmd("doommake",
                  [project_name, "--convert-palette", palette,
                   "--convert", "--explode", explode_wad],
                  feed=feed)
    sys.exit(err)


# ==============================================================================
# Mode: watch  (standalone; ignores all other args)
# ==============================================================================
def invoke_watch_mode():
    assert_project_root("dmake watch")

    print(f"Watching project in: {os.getcwd()}")
    print("")

    watch_script = find_on_path("dmake_watch.py")
    if not watch_script:
        print("Error: dmake_watch.py not found on PATH.")
        sys.exit(2)

    launcher = resolve_cmd("py") or sys.executable
    try:
        r = subprocess.run([launcher, watch_script])
        sys.exit(r.returncode)
    except KeyboardInterrupt:
        sys.exit(130)


# ==============================================================================
# Mode: texturex  (standalone; wadtex TEXTURE1/TEXTURE2 extraction wrapper)
#   dmake texturex [-x1 | -x2] [-file wad.wad] [-output name.txt]
#
#     -x1 / -x2     Which lump to export (TEXTURE1 / TEXTURE2).
#                   If NEITHER is given, BOTH lumps are extracted.
#     -file <wad>   Source WAD. If omitted, falls back to .\build\textures.wad.
#     -output <f>   Output filename (single-lump only). Defaults to
#                   texture1.txt / texture2.txt. Ignored when extracting both.
#
#   Output location:
#     -file given    -> current directory
#     -file omitted  -> the directory ABOVE the current one
#
#   No DoomTools project-root check is performed.
# ==============================================================================
def invoke_texturex_mode(all_args):
    extract  = None   # 'TEXTURE1' | 'TEXTURE2' | None (= both)
    wad_file = None   # explicit wad via -file
    out_name = None   # explicit filename via -output

    i = 0
    while i < len(all_args):
        a = all_args[i].lower()
        if a == "-x1":
            extract = "TEXTURE1"
            i += 1
        elif a == "-x2":
            extract = "TEXTURE2"
            i += 1
        elif a == "-file":
            if i + 1 >= len(all_args):
                print("Error: -file requires a WAD path")
                sys.exit(2)
            wad_file = all_args[i + 1]
            i += 2
        elif a == "-output":
            if i + 1 >= len(all_args):
                print("Error: -output requires a filename")
                sys.exit(2)
            out_name = all_args[i + 1]
            i += 2
        else:
            i += 1  # includes the 'texturex' keyword itself

    # Resolve source WAD and output directory
    if wad_file:
        if not os.path.isfile(wad_file):
            print(f"Error: WAD not found: {wad_file}")
            sys.exit(2)
        out_dir = os.getcwd()                              # explicit wad -> current dir
    else:
        wad_file = os.path.join(os.getcwd(), "build", "textures.wad")
        if not os.path.isfile(wad_file):
            print(r"Error: .\build\textures.wad not found.")
            print("Run this from a DoomTools project root, or specify a WAD with -file.")
            sys.exit(2)
        out_dir = os.path.dirname(os.getcwd())             # fallback -> one dir up
        if not out_dir:
            out_dir = os.getcwd()

    # Export one lump to a filename within out_dir (absolute names honoured as-is)
    def export_lump(lump, file_name):
        p = file_name if os.path.isabs(file_name) else os.path.join(out_dir, file_name)
        print(f"  {lump} -> {p}")
        return run_cmd("wadtex", [wad_file, "--export", p, "--entry-name", lump])

    print("dmake texturex - wadtex extraction")
    print(f"  Source WAD : {wad_file}")
    print("")

    if not extract:
        # No lump chosen -> extract BOTH (wadtex writes a template if a lump is absent)
        if out_name:
            print("Note: -output ignored when extracting both lumps.")
            print("")
        export_lump("TEXTURE1", "texture1.txt")
        err = export_lump("TEXTURE2", "texture2.txt")
        sys.exit(err)

    # Single lump
    if not out_name:
        out_name = "texture1.txt" if extract == "TEXTURE1" else "texture2.txt"
    err = export_lump(extract, out_name)
    sys.exit(err)


# ==============================================================================
# Mode: editpatch  (standalone)
# ==============================================================================
def invoke_editpatch_mode(all_args):
    use_txt = any(a.lower() == "-txt" for a in all_args)
    if use_txt:
        err = run_cmd("wadtex", ["--gui"])
    else:
        err = run_cmd("wadtex", ["--gui-editor"])
    sys.exit(err)


# ==============================================================================
# Mode: strip  (standalone; strips named lumps out of a WAD - native)
#   dmake strip input.wad [--<stripset> ...] [--lumps NAME1 NAME2 ...]
#                         [--output newwadname.wad]
#
#   Every key in "clean_strip_sets" in the conf becomes a --<key> flag that
#   strips the lumps listed under it. Nothing is hardcoded here: the shipped
#   sets (--texturex, --anims, --deco, --info, --clean, --texture1,
#   --texture2) are just the default entries, and any key added to the conf
#   becomes a usable flag with no code change.
#
#     --lumps      Strip the literally named lumps (greedy until next --flag)
#     --output f   Output WAD path (default: <inputstem>_cleaned.wad, next to
#                  the input)
#
#   Flags combine freely; all requested names are unioned into one strip set.
#   Lumps not present in the WAD are silently ignored (never an error).
#   An unknown --flag is an error listing the available ones.
#   With no WAD, or a WAD but no strip flags, the strip help is shown and
#   nothing is done. No DoomTools project-root check is performed.
#
#   NOTE: named "strip" (not "clean") so it does not shadow the doommake
#   "clean" build target - "dmake clean" passes straight through to doommake.
# ==============================================================================
def strip_wad_lumps(in_path, out_path, strip_names):
    """Copy a WAD, removing every lump whose name is in strip_names
    (case-insensitive). Kept lumps are copied byte-for-byte; only the
    directory is rebuilt. Returns 0 on success, 2 on error."""
    names = {n.upper() for n in strip_names if n.strip()}

    def err(msg):
        print(f"Error: {msg}")
        return 2

    if not names:
        return err("no lump names given")

    if not os.path.isfile(in_path):
        return err(f"input WAD not found: {in_path}")

    if full_path(in_path).lower() == full_path(out_path).lower():
        return err("input and output are the same file - refusing to overwrite the source")

    try:
        with open(in_path, "rb") as f:
            data = f.read()
    except OSError as e:
        return err(f"cannot read input WAD: {e}")

    # ---- Parse header --------------------------------------------------------
    if len(data) < 12:
        return err("file too small to be a WAD")

    magic = data[0:4]
    if magic not in (b"IWAD", b"PWAD"):
        return err(f"not a WAD file (bad magic: {magic!r})")

    num_lumps, dir_offset = struct.unpack_from("<ii", data, 4)

    if num_lumps < 0 or dir_offset < 0:
        return err("corrupt WAD header (negative lump count or directory offset)")
    if dir_offset + num_lumps * 16 > len(data):
        return err("corrupt WAD header (directory extends past end of file)")

    # ---- Parse directory -----------------------------------------------------
    # Each entry: <int32 offset> <int32 size> <8-byte name, NUL padded>
    entries = []  # (offset, size, raw_name_bytes, clean_name_str)
    for i in range(num_lumps):
        base = dir_offset + i * 16
        off, size = struct.unpack_from("<ii", data, base)
        raw_name = data[base + 8: base + 16]
        clean = raw_name.split(b"\x00", 1)[0].decode("ascii", "replace").upper()
        entries.append((off, size, raw_name, clean))

    # ---- Partition kept / removed --------------------------------------------
    kept    = []
    removed = []
    for entry in entries:
        if entry[3] in names:
            removed.append(entry[3])
        else:
            kept.append(entry)

    # ---- Write output WAD ----------------------------------------------------
    # Layout: 12-byte header, lump data in original order, directory at the end.
    try:
        with open(out_path, "wb") as out:
            out.write(magic)
            out.write(struct.pack("<ii", len(kept), 0))  # dir offset patched below

            new_entries = []
            for off, size, raw_name, clean in kept:
                if size > 0:
                    if off < 0 or off + size > len(data):
                        return err(f"corrupt lump entry (data out of bounds): {clean}")
                    new_off = out.tell()
                    out.write(data[off: off + size])
                else:
                    # Zero-size lump (markers etc). Offset value is irrelevant;
                    # keep the original as some tools store meaningful values.
                    new_off = off
                new_entries.append((new_off, size, raw_name))

            new_dir_offset = out.tell()
            for new_off, size, raw_name in new_entries:
                out.write(struct.pack("<ii", new_off, size))
                out.write(raw_name)

            out.seek(4)
            out.write(struct.pack("<ii", len(kept), new_dir_offset))
    except OSError as e:
        return err(f"cannot write output WAD: {e}")

    # ---- Report --------------------------------------------------------------
    if removed:
        print(f"Removed {len(removed)} lump(s): {', '.join(removed)}")
    else:
        print("No matching lumps found - wrote unmodified copy.")
    print(f"Kept {len(kept)} lump(s) -> {out_path}")
    return 0


def invoke_strip_mode(rest):
    # No arguments at all, or first argument is a flag (WAD forgotten)
    # -> help, do nothing
    if not rest or not rest[0] or rest[0].startswith("--"):
        show_strip_help()
        sys.exit(0)

    input_wad = rest[0]
    out_name  = None
    strip_set = {}   # dict keyed by upper-cased name -> original casing (order kept)

    def add(name):
        strip_set.setdefault(name.upper(), name.upper())

    i = 1
    while i < len(rest):
        a = rest[i].lower()
        if a == "--lumps":
            # Greedily consume names until the next --flag or end of args
            i += 1
            consumed = 0
            while i < len(rest) and not rest[i].startswith("--"):
                add(rest[i])
                consumed += 1
                i += 1
            if consumed == 0:
                print("Error: --lumps requires at least one lump name")
                sys.exit(2)
        elif a == "--output":
            if i + 1 >= len(rest):
                print("Error: --output requires a filename")
                sys.exit(2)
            out_name = rest[i + 1]
            i += 2
        elif a.startswith("--") and a[2:] in CLEAN_STRIP_SETS:
            # Any strip-set name from the conf works as a --<name> flag.
            for n in CLEAN_STRIP_SETS[a[2:]]:
                add(n)
            i += 1
        elif a.startswith("--"):
            # An unknown --flag is an error rather than a silent no-op, so a
            # typo can't quietly strip nothing.
            available = ", ".join("--" + k for k in CLEAN_STRIP_SETS.keys())
            print(f"Error: unknown strip flag '{rest[i]}'")
            print(f"Available strip flags (from clean_strip_sets in the conf): "
                  f"{available}")
            print("Plus: --lumps NAME1 NAME2 ...   --output FILE")
            sys.exit(2)
        else:
            i += 1  # Non-flag stray token - skip it

    # WAD given but nothing requested -> help, do nothing
    if not strip_set:
        show_strip_help()
        sys.exit(0)

    if not os.path.isfile(input_wad):
        print(f"Error: WAD not found: {input_wad}")
        sys.exit(2)

    # Resolve output path: --output verbatim, else <inputstem>_cleaned.wad
    # next to the input file.
    if not out_name:
        in_dir = os.path.dirname(input_wad)
        stem   = os.path.splitext(os.path.basename(input_wad))[0]
        out_name = os.path.join(in_dir, f"{stem}_cleaned.wad") if in_dir \
                   else f"{stem}_cleaned.wad"

    # Never clobber the source
    if full_path(input_wad).lower() == full_path(out_name).lower():
        print("Error: output path is the same as the input WAD.")
        print("Use --output to write the cleaned WAD somewhere else.")
        sys.exit(2)

    names = list(strip_set.values())

    print("dmake strip - lump stripper")
    print(f"  Input WAD  : {input_wad}")
    print(f"  Output WAD : {out_name}")
    print(f"  Stripping  : {', '.join(names)}")
    print("")

    sys.exit(strip_wad_lumps(input_wad, out_name, names))


# ==============================================================================
# Mode: conform2palette  (standalone; repalettes every graphic in a WAD - native)
#   dmake conform2palette input.wad [output.wad] [-i/-iwad iwad] [-pal source]
#                                   [-keep | -replace]
#
#   Converts every graphic in the input WAD to a target palette and writes a
#   classic-format copy of the WAD. Doom pictures, flats, palettised PNGs and
#   truecolour PNGs all come out as standard Doom pictures (or raw flats in a
#   flat namespace). PLAYPAL is replaced with the target's 14 palettes.
#   Every other lump is copied byte-for-byte; names, order, markers and
#   namespaces never change.
#
#   Source palette : always the input WAD's own PLAYPAL (error if missing).
#   Target palette : -pal, else the project palette (project mode only),
#                    else the IWAD palette.
#
#   Project mode (run from a DoomTools project root) only changes defaults:
#     - input not found -> searched in src/wads/textures, then build
#     - output default  -> src/wads/textures/<inputname>   (-keep: <stem>-palettised.wad)
#     - palette         -> src/assets/palettes, build/convert/palettes,
#                          src/convert/palettes
#     - IWAD fallback   -> doom-loader.conf, doommake.properties, doom2
#   Outside a project:
#     - output default  -> <stem>-palettised.wad next to the input
#                          (-replace: overwrite the input)
#     - IWAD fallback   -> doom2
#
#   The search folders are standard DoomTools project folders and are
#   deliberately hardcoded (not in the settings file).
# ==============================================================================

CONFORM_INPUT_DIRS   = [os.path.join("src", "wads", "textures"), "build"]
CONFORM_OUTPUT_DIR   = os.path.join("src", "wads", "textures")
CONFORM_PALETTE_DIRS = [os.path.join("src", "assets", "palettes"),
                        os.path.join("build", "convert", "palettes"),
                        os.path.join("src", "convert", "palettes")]
CONFORM_DEFAULT_IWAD = "doom2"
CONFORM_SUFFIX       = "-palettised"

PNG_SIG = b"\x89PNG\r\n\x1a\n"

# 4x4 ordered-dither thresholds for partial alpha (alpha > t -> opaque).
# alpha 255 is always opaque, alpha 0 always transparent.
_BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
BAYER_T = tuple(tuple(m * 16 + 8 for m in row) for row in _BAYER4)

# Near-tie tolerance for colour matching (redmean distance units). When the
# best match is not exact, the LOWEST index within best+TOL wins.
MATCH_TIE_TOL = 4


class ConformError(Exception):
    pass


# ------------------------------------------------------------------------------
# WAD reading / writing
# ------------------------------------------------------------------------------
def wad_parse(data, label):
    """Parse WAD bytes into (magic, entries). Each entry is a dict with
    raw (8-byte name), name (clean upper str), off, size, data."""
    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        raise ConformError(f"{label} is not a WAD file")
    num, diro = struct.unpack_from("<ii", data, 4)
    if num < 0 or diro < 0 or diro + num * 16 > len(data):
        raise ConformError(f"{label} has a corrupt WAD header")
    entries = []
    for i in range(num):
        base = diro + i * 16
        off, size = struct.unpack_from("<ii", data, base)
        raw = data[base + 8: base + 16]
        name = raw.split(b"\x00", 1)[0].decode("ascii", "replace").upper()
        if size > 0:
            if off < 0 or off + size > len(data):
                raise ConformError(f"{label}: lump {name} points outside the file")
            lump = data[off: off + size]
        else:
            lump = b""
        entries.append({"raw": raw, "name": name, "off": off,
                        "size": size, "data": lump})
    return data[0:4], entries


def wad_last_lump(entries, name):
    """Return the data of the LAST lump with this name (as ports do), or None."""
    found = None
    for e in entries:
        if e["name"] == name:
            found = e["data"]
    return found


def wad_write(path, magic, entries):
    """Write entries to a WAD. Lump data in order, directory at the end.
    Zero-size lumps keep their original offset value."""
    with open(path, "wb") as out:
        out.write(magic)
        out.write(struct.pack("<ii", len(entries), 0))
        dir_rows = []
        for e in entries:
            d = e["data"]
            if d:
                off = out.tell()
                out.write(d)
            else:
                off = e["off"]
            dir_rows.append((off, len(d), e["raw"]))
        diro = out.tell()
        for off, size, raw in dir_rows:
            out.write(struct.pack("<ii", off, size))
            out.write(raw)
        out.seek(4)
        out.write(struct.pack("<ii", len(entries), diro))


# ------------------------------------------------------------------------------
# PNG decoding (stdlib only: zlib + struct)
#   Colour types 0/2/3/4/6, bit depths 1-16, Adam7 interlace, tRNS, grAb.
#   Returns (width, height, [ (r,g,b,a), ... ], grab_or_None).
# ------------------------------------------------------------------------------
def _png_unfilter(raw, pos, rowbytes, rows, bpp):
    out = []
    prev = bytearray(rowbytes)
    for _ in range(rows):
        if pos >= len(raw):
            raise ConformError("PNG image data is truncated")
        ft = raw[pos]
        pos += 1
        line = bytearray(raw[pos: pos + rowbytes])
        pos += rowbytes
        if len(line) < rowbytes:
            raise ConformError("PNG image data is truncated")
        if ft == 1:
            for i in range(bpp, rowbytes):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(rowbytes):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(rowbytes):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(rowbytes):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                line[i] = (line[i] + pr) & 0xFF
        elif ft != 0:
            raise ConformError(f"PNG uses unknown filter type {ft}")
        out.append(line)
        prev = line
    return out, pos


def _png_row_samples(line, count, depth):
    if depth == 8:
        return list(line[:count])
    if depth == 16:
        return [(line[2 * i] << 8) | line[2 * i + 1] for i in range(count)]
    per = 8 // depth
    mask = (1 << depth) - 1
    res = []
    for i in range(count):
        byte = line[i // per]
        shift = 8 - depth * (i % per + 1)
        res.append((byte >> shift) & mask)
    return res


def png_decode(data):
    if data[:8] != PNG_SIG:
        raise ConformError("not a PNG")
    pos = 8
    ihdr = None
    plte = None
    trns = None
    grab = None
    idat = []
    while pos + 8 <= len(data):
        length, ctype = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8: pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body[:13])
        elif ctype == b"PLTE":
            plte = body
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"grAb" and len(body) >= 8:
            grab = struct.unpack(">ii", body[:8])
        elif ctype == b"IDAT":
            idat.append(body)
        elif ctype == b"IEND":
            break
    if not ihdr:
        raise ConformError("PNG has no IHDR chunk")

    w, h, depth, ctyp, _comp, _filt, interlace = ihdr
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctyp)
    if channels is None or depth not in (1, 2, 4, 8, 16) or w == 0 or h == 0:
        raise ConformError("PNG uses an unsupported format")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as e:
        raise ConformError(f"PNG data is corrupt ({e})")

    maxv = (1 << depth) - 1

    def scale(v):
        if depth == 16:
            return v >> 8
        if depth == 8:
            return v
        return v * 255 // maxv

    pal = []
    if plte:
        pal = [tuple(plte[i:i + 3]) for i in range(0, len(plte) - 2, 3)]
    pal_alpha = list(trns) if (ctyp == 3 and trns) else []
    key_gray = struct.unpack(">H", trns[:2])[0] if (ctyp == 0 and trns and len(trns) >= 2) else None
    key_rgb = struct.unpack(">HHH", trns[:6]) if (ctyp == 2 and trns and len(trns) >= 6) else None

    bits_pp = channels * depth
    bpp = max(1, bits_pp // 8)
    pixels = [(0, 0, 0, 0)] * (w * h)

    if interlace:
        passes = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                  (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
    else:
        passes = ((0, 0, 1, 1),)

    rpos = 0
    for xs, ys, xstep, ystep in passes:
        pw = (w - xs + xstep - 1) // xstep
        ph = (h - ys + ystep - 1) // ystep
        if pw <= 0 or ph <= 0:
            continue
        rowbytes = (pw * bits_pp + 7) // 8
        rows, rpos = _png_unfilter(raw, rpos, rowbytes, ph, bpp)
        for ry, line in enumerate(rows):
            y = ys + ry * ystep
            s = _png_row_samples(line, pw * channels, depth)
            for rx in range(pw):
                x = xs + rx * xstep
                k = rx * channels
                if ctyp == 0:
                    v = s[k]
                    g = scale(v)
                    px = (g, g, g, 0 if v == key_gray else 255)
                elif ctyp == 2:
                    rv, gv, bv = s[k], s[k + 1], s[k + 2]
                    a = 0 if key_rgb == (rv, gv, bv) else 255
                    px = (scale(rv), scale(gv), scale(bv), a)
                elif ctyp == 3:
                    idx = s[k]
                    r, g, b = pal[idx] if idx < len(pal) else (0, 0, 0)
                    a = pal_alpha[idx] if idx < len(pal_alpha) else 255
                    px = (r, g, b, a)
                elif ctyp == 4:
                    g = scale(s[k])
                    px = (g, g, g, scale(s[k + 1]))
                else:
                    px = (scale(s[k]), scale(s[k + 1]), scale(s[k + 2]),
                          scale(s[k + 3]))
                pixels[y * w + x] = px
    return w, h, pixels, grab


# ------------------------------------------------------------------------------
# Palette sources
#   Every loader returns a list of 768-byte palettes (at least one).
# ------------------------------------------------------------------------------
def _split_palettes(blob, label):
    n = len(blob) // 768
    if n < 1:
        raise ConformError(f"{label}: palette data is shorter than 768 bytes")
    return [bytes(blob[i * 768:(i + 1) * 768]) for i in range(n)]


def _palettes_from_png(data, label):
    w, h, px, _ = png_decode(data)

    def row(y):
        return bytes(c for x in range(256) for c in px[y * w + x][:3])

    if w == 256:
        # DoomTools layout: one palette per row. 14 rows = a full PLAYPAL;
        # any other height is treated as a colourmap image (row 0 only).
        if h == 14:
            return [row(y) for y in range(14)]
        return [row(0)]
    if w == h and w % 16 == 0:
        # SLADE layout: 16x16 grid of swatches, sampled at each cell centre.
        cell = w // 16
        out = bytearray()
        for i in range(256):
            cx = (i % 16) * cell + cell // 2
            cy = (i // 16) * cell + cell // 2
            out += bytes(px[cy * w + cx][:3])
        return [bytes(out)]
    raise ConformError(
        f"{label}: unrecognised palette image layout ({w}x{h}). Expected a "
        f"256-wide image (one palette per row) or a square 16x16-swatch grid.")


def _palettes_from_text(text, label):
    lines = [ln.strip() for ln in text.splitlines()]
    rgb = bytearray()
    if lines and lines[0].upper().startswith("JASC-PAL"):
        for ln in lines[3:]:
            parts = ln.split()
            if len(parts) >= 3:
                rgb += bytes(max(0, min(255, int(p))) for p in parts[:3])
    else:  # GIMP .gpl
        for ln in lines[1:]:
            if not ln or ln.startswith("#") or ":" in ln.split()[0]:
                continue
            parts = ln.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                rgb += bytes(max(0, min(255, int(p))) for p in parts[:3])
    return _split_palettes(rgb, label)


def load_palette_file(path):
    label = path
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ConformError(f"cannot read palette source {path}: {e}")

    if data[0:4] in (b"IWAD", b"PWAD"):
        _, entries = wad_parse(data, label)
        lump = wad_last_lump(entries, "PLAYPAL")
        if not lump:
            raise ConformError(f"{label} has no PLAYPAL lump")
        return _split_palettes(lump, label)

    if data[:8] == PNG_SIG:
        return _palettes_from_png(data, label)

    if data[0:4] == b"RIFF" and data[8:12] == b"PAL ":
        p = 12
        while p + 8 <= len(data):
            cid, clen = struct.unpack_from("<4sI", data, p)
            if cid == b"data":
                count = struct.unpack_from("<H", data, p + 10)[0]
                rgb = bytearray()
                for i in range(count):
                    q = p + 12 + i * 4
                    rgb += data[q:q + 3]
                return _split_palettes(rgb, label)
            p += 8 + clen + (clen & 1)
        raise ConformError(f"{label}: RIFF palette has no data chunk")

    head = data[:16].lstrip(b"\xef\xbb\xbf")
    if head.upper().startswith(b"JASC-PAL") or head.startswith(b"GIMP Palette"):
        return _palettes_from_text(data.decode("utf-8-sig", "replace"), label)

    if len(data) >= 768 and len(data) % 768 == 0:
        return _split_palettes(data, label)

    raise ConformError(
        f"{label}: unrecognised palette format. Supported: WAD with PLAYPAL, "
        f"raw PLAYPAL lump, palette PNG (DoomTools/SLADE/colourmap), "
        f".pal (raw, JASC or RIFF), GIMP .gpl")


def generate_playpal(pal0):
    """Build a standard 14-palette PLAYPAL from palette 0, using the classic
    Doom tints: 8 red (pain), 4 gold (bonus), 1 green (radsuit)."""
    base = [pal0[i:i + 3] for i in range(0, 768, 3)]

    def blend(target, f):
        out = bytearray()
        for c in base:
            for ch in range(3):
                v = c[ch] + (target[ch] - c[ch]) * f
                out.append(max(0, min(255, int(round(v)))))
        return bytes(out)

    pals = [bytes(pal0)]
    for i in range(1, 9):
        pals.append(blend((255, 0, 0), i / 9.0))
    for i in range(1, 5):
        pals.append(blend((215, 186, 69), i / 8.0))
    pals.append(blend((0, 255, 0), 1 / 8.0))
    return pals


def build_playpal(pals):
    """Full 14-palette lump: use all 14 if supplied, else generate from pal0."""
    if len(pals) >= 14:
        return b"".join(pals[:14]), False
    return b"".join(generate_playpal(pals[0])), True


# ------------------------------------------------------------------------------
# Colour matching
# ------------------------------------------------------------------------------
class PaletteMatcher:
    """Nearest-colour matcher against a target palette (weighted 'redmean'
    RGB). Exact match: lowest exact index. Otherwise the lowest index within
    MATCH_TIE_TOL of the best distance (coin-flips go to the earlier index)."""

    def __init__(self, pal0):
        self.pal = [tuple(pal0[i:i + 3]) for i in range(0, 768, 3)]
        self.cache = {}

    def nearest(self, r, g, b):
        key = (r << 16) | (g << 8) | b
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        dists = []
        for pr, pg, pb in self.pal:
            rm = (r + pr) >> 1
            dr, dg, db = r - pr, g - pg, b - pb
            dists.append((((512 + rm) * dr * dr) >> 8) + 4 * dg * dg
                         + (((767 - rm) * db * db) >> 8))
        best = min(dists)
        limit = best if best == 0 else best + MATCH_TIE_TOL
        for i, d in enumerate(dists):
            if d <= limit:
                self.cache[key] = i
                return i
        return 0  # unreachable

    def index_table(self, src_pal0):
        return bytes(self.nearest(src_pal0[i], src_pal0[i + 1], src_pal0[i + 2])
                     for i in range(0, 768, 3))


# ------------------------------------------------------------------------------
# Graphic formats
# ------------------------------------------------------------------------------
def remap_picture(data, table):
    """Validate a Doom picture and remap its pixel bytes through table.
    Returns new bytes, or None if the data is not a valid Doom picture.
    Header, offsets and post structure are untouched; shared posts are
    only remapped once."""
    n = len(data)
    if n < 8:
        return None
    w, h = struct.unpack_from("<hh", data, 0)
    if w <= 0 or h <= 0 or w > 4096 or h > 4096:
        return None
    colstart = 8 + 4 * w
    if colstart > n:
        return None
    offs = struct.unpack_from(f"<{w}I", data, 8)
    out = bytearray(data)
    done = bytearray(n)
    for off in offs:
        if off < colstart or off >= n:
            return None
        p = off
        posts = 0
        while True:
            if p >= n:
                return None
            if data[p] == 0xFF:
                break
            if p + 1 >= n:
                return None
            ln = data[p + 1]
            end = p + 4 + ln
            if end > n:
                return None
            for q in range(p + 2, end):   # pad, pixels, pad
                if not done[q]:
                    out[q] = table[data[q]]
                    done[q] = 1
            p = end
            posts += 1
            if posts > 4096:
                return None
    return bytes(out)


def encode_picture(w, h, idx, opaque, left, top):
    """Encode indexed pixels + opacity mask as a Doom picture. Images taller
    than 254 use DeePsea-style relative topdeltas (bridging empty posts as
    needed), as supported by Boom-derived ports."""
    cols = []
    for x in range(w):
        col = bytearray()
        lasttop = -1
        y = 0
        while y < h:
            if not opaque[y * w + x]:
                y += 1
                continue
            start = y
            run = bytearray()
            while y < h and opaque[y * w + x] and len(run) < 254:
                run.append(idx[y * w + x])
                y += 1
            while True:
                if start > lasttop and start <= 254:
                    delta = start
                elif lasttop >= 254 and start - lasttop <= min(lasttop, 254):
                    delta = start - lasttop
                elif lasttop < 254:
                    col += bytes((254, 0, 0, 0))   # bridge to absolute 254
                    lasttop = 254
                    continue
                else:
                    step = min(lasttop, 254)
                    col += bytes((step, 0, 0, 0))  # relative bridge
                    lasttop += step
                    continue
                col += bytes((delta, len(run), run[0])) + run + bytes((run[-1],))
                lasttop = start
                break
        col.append(0xFF)
        cols.append(bytes(col))

    left = max(-32768, min(32767, left))
    top = max(-32768, min(32767, top))
    head = bytearray(struct.pack("<hhhh", w, h, left, top))
    off = 8 + 4 * w
    for c in cols:
        head += struct.pack("<I", off)
        off += len(c)
    return bytes(head) + b"".join(cols)


def png_to_doom(data, matcher, as_flat):
    """Convert PNG lump data to a raw flat or a Doom picture."""
    w, h, px, grab = png_decode(data)
    idx = bytearray(w * h)
    opaque = [True] * (w * h)
    for i, (r, g, b, a) in enumerate(px):
        if not as_flat and a <= BAYER_T[(i // w) & 3][(i % w) & 3]:
            opaque[i] = False
            continue
        idx[i] = matcher.nearest(r, g, b)
    if as_flat:
        return bytes(idx)
    if w > 4096 or h > 4096:
        raise ConformError(f"PNG is too large for a Doom picture ({w}x{h})")
    left, top = grab if grab else (0, 0)
    return encode_picture(w, h, idx, opaque, left, top)


# ------------------------------------------------------------------------------
# Lump classification
# ------------------------------------------------------------------------------
_NS_START = {}
_NS_END = {}
for _fam, _starts, _ends in (
        ("sprite",   ("S_START", "SS_START"), ("S_END", "SS_END")),
        ("patch",    ("P_START", "PP_START", "P1_START", "P2_START", "P3_START"),
                     ("P_END", "PP_END", "P1_END", "P2_END", "P3_END")),
        ("flat",     ("F_START", "FF_START", "F1_START", "F2_START", "F3_START"),
                     ("F_END", "FF_END", "F1_END", "F2_END", "F3_END")),
        ("texture",  ("TX_START",), ("TX_END",)),
        ("hires",    ("HI_START",), ("HI_END",)),
        ("colormap", ("C_START",), ("C_END",)),
        ("skip",     ("A_START", "V_START", "VX_START", "DS_START"),
                     ("A_END", "V_END", "VX_END", "DS_END"))):
    for _n in _starts:
        _NS_START[_n] = _fam
    for _n in _ends:
        _NS_END[_n] = _fam

GRAPHIC_NAMESPACES = ("sprite", "patch", "texture", "hires")

NON_GRAPHIC_NAMES = {
    "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS", "NODES",
    "SECTORS", "REJECT", "BLOCKMAP", "BEHAVIOR", "SCRIPTS", "TEXTMAP",
    "ZNODES", "DIALOGUE", "ENDMAP", "LEAFS", "LIGHTS", "MACROS",
    "PLAYPAL", "COLORMAP", "ENDOOM", "ENDTEXT", "ENDBOOM", "ENDSTRF",
    "GENMIDI", "DMXGUS", "DMXGUSC", "TEXTURE1", "TEXTURE2", "TEXTURES",
    "PNAMES", "ANIMATED", "SWITCHES", "DEHACKED", "DECOHACK", "MAPINFO",
    "UMAPINFO", "ZMAPINFO", "EMAPINFO", "DECORATE", "ZSCRIPT", "SNDINFO",
    "SNDSEQ", "LANGUAGE", "GAMEINFO", "KEYCONF", "CREDITS", "WADINFO",
    "COMPLVL", "OPTIONS", "SBARDEF", "SKYDEFS", "TRAKINFO", "TRANMAP",
    "WATERMAP", "FOGMAP", "TINTTAB", "LOCKDEFS", "TERRAIN", "ANIMDEFS",
    "GLDEFS", "MODELDEF", "FONTDEFS", "ALTHUDCF", "SNDCURVE", "X11R6RGB",
    "DEMOLOOP", "MUSINFO", "GAMECONF", "MENUDEF", "CVARINFO", "__VER__",
}
NON_GRAPHIC_PREFIXES = ("DEMO", "GL_", "D_", "XLAT")
_MAP_MARKER = re.compile(r"^(MAP\d\d|E\dM\d)$")


def _is_text(data):
    if b"\x00" in data:
        return False
    return all(b in (9, 10, 13) or 32 <= b <= 126 or b >= 128 for b in data)


def _is_known_non_graphic(name, data):
    if name in NON_GRAPHIC_NAMES or _MAP_MARKER.match(name):
        return True
    if name.startswith(NON_GRAPHIC_PREFIXES):
        return True
    for magic in (b"MUS\x1a", b"MThd", b"RIFF", b"OggS", b"fLaC", b"ID3",
                  b"IMPM", b"PK\x03\x04", b"IWAD", b"PWAD"):
        if data.startswith(magic):
            return True
    if data[:15] == b"Extended Module":
        return True
    if len(data) >= 8:   # DMX digital sound: format 3 + sample count
        fmt = struct.unpack_from("<H", data, 0)[0]
        samples = struct.unpack_from("<I", data, 4)[0]
        if fmt == 3 and 8 + samples <= len(data) + 32:
            return True
    return _is_text(data)


FLAT_SIZES = (4096, 8192, 16384, 65536)


# ------------------------------------------------------------------------------
# Project helpers
# ------------------------------------------------------------------------------
def is_project_root():
    return all(os.path.isfile(f) for f in
               ("doommake.script", "doommake.project.properties",
                "doommake.properties"))


def _unescape_java_prop(v):
    out = []
    i = 0
    while i < len(v):
        c = v[i]
        if c == "\\" and i + 1 < len(v):
            out.append(v[i + 1])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def project_iwad_candidates():
    """IWAD paths from the project, in priority order, with labels."""
    found = []
    if os.path.isfile("doom-loader.conf"):
        try:
            with open("doom-loader.conf", "r", encoding="utf-8-sig",
                      errors="replace") as f:
                for ln in f:
                    m = re.match(r"^\s*iwad\s*=\s*(.+?)\s*$", ln, re.I)
                    if m:
                        found.append((m.group(1), "doom-loader.conf"))
                        break
        except OSError:
            pass
    try:
        with open("doommake.properties", "r", encoding="utf-8-sig",
                  errors="replace") as f:
            for ln in f:
                m = re.match(r"^\s*doommake\.iwad\s*=\s*(.+?)\s*$", ln)
                if m:
                    found.append((_unescape_java_prop(m.group(1)),
                                  "doommake.properties"))
                    break
    except OSError:
        pass
    return found


def find_project_palette():
    """Search the DoomTools palette folders. Files named PLAYPAL (any
    extension) are tried first in each folder. Returns (path, palettes)
    or (None, None)."""
    for d in CONFORM_PALETTE_DIRS:
        if not os.path.isdir(d):
            continue
        files = []
        for fn in sorted(os.listdir(d), key=str.lower):
            full = os.path.join(d, fn)
            if not os.path.isfile(full) or fn.startswith("."):
                continue
            if fn.lower().endswith((".md", ".txt")):
                continue
            files.append(fn)
        files.sort(key=lambda fn: 0 if os.path.splitext(fn)[0].upper() == "PLAYPAL" else 1)
        for fn in files:
            full = os.path.join(d, fn)
            try:
                return full, load_palette_file(full)
            except ConformError as e:
                print(DGRY(f"  (skipping {full}: {e})"))
    return None, None


# ------------------------------------------------------------------------------
# The conversion pass
# ------------------------------------------------------------------------------
def conform_entries(entries, matcher, table, playpal):
    stats = {"picture": 0, "flat": 0, "png-picture": 0, "png-flat": 0,
             "playpal": 0, "copied": 0}
    warnings = []
    stack = []
    out = []

    for e in entries:
        name, data = e["name"], e["data"]
        new = dict(e)

        if name in _NS_START:
            stack.append(_NS_START[name])
            out.append(new)
            stats["copied"] += 1
            continue
        if name in _NS_END:
            fam = _NS_END[name]
            if fam in stack:
                while stack and stack.pop() != fam:
                    pass
            out.append(new)
            stats["copied"] += 1
            continue

        ns = stack[-1] if stack else None
        result = None
        kind = None

        try:
            if name == "PLAYPAL":
                result, kind = playpal, "playpal"
            elif not data or ns in ("colormap", "skip"):
                pass
            elif ns == "flat":
                if data[:8] == PNG_SIG:
                    result, kind = png_to_doom(data, matcher, True), "png-flat"
                elif len(data) not in FLAT_SIZES and remap_picture(data, table):
                    result, kind = remap_picture(data, table), "picture"
                else:
                    result, kind = data.translate(table), "flat"
            elif data[:8] == PNG_SIG:
                result, kind = png_to_doom(data, matcher, False), "png-picture"
            elif ns in GRAPHIC_NAMESPACES:
                pic = remap_picture(data, table)
                if pic is not None:
                    result, kind = pic, "picture"
                else:
                    warnings.append(f"{name}: in a graphics namespace but not a "
                                    f"recognisable graphic - copied unchanged")
            elif not _is_known_non_graphic(name, data):
                pic = remap_picture(data, table)
                if pic is not None:
                    result, kind = pic, "picture"
        except ConformError as ex:
            warnings.append(f"{name}: {ex} - copied unchanged")
            result, kind = None, None

        if result is not None:
            new["data"] = result
            stats[kind] += 1
        else:
            stats["copied"] += 1
        out.append(new)

    return out, stats, warnings


# ------------------------------------------------------------------------------
# Mode entry
# ------------------------------------------------------------------------------
def invoke_conform_mode(rest):
    if not rest:
        show_conform_help()
        sys.exit(0)

    positionals = []
    in_arg = out_arg = pal_arg = iwad_arg = None
    keep = replace = False

    i = 0
    while i < len(rest):
        a = rest[i]
        al = a.lower()
        if al in ("-i", "-iwad", "-pal", "-input", "-output"):
            if i + 1 >= len(rest):
                print(f"Error: {a} requires a value")
                sys.exit(2)
            v = rest[i + 1]
            if al in ("-i", "-iwad"):
                iwad_arg = v
            elif al == "-pal":
                pal_arg = v
            elif al == "-input":
                in_arg = v
            else:
                out_arg = v
            i += 2
        elif al == "-keep":
            keep = True
            i += 1
        elif al == "-replace":
            replace = True
            i += 1
        elif al.startswith("-") and len(al) > 1:
            print(f"Error: unknown conform2palette option '{a}'")
            print("Options: -i/-iwad  -pal  -input  -output  -keep  -replace")
            sys.exit(2)
        else:
            positionals.append(a)
            i += 1

    if in_arg is None and positionals:
        in_arg = positionals.pop(0)
    if out_arg is None and positionals:
        out_arg = positionals.pop(0)
    if positionals:
        print(f"Note: ignoring extra argument(s): {' '.join(positionals)}")

    if not in_arg:
        show_conform_help()
        sys.exit(0)

    try:
        _run_conform(in_arg, out_arg, pal_arg, iwad_arg, keep, replace)
    except ConformError as e:
        print(RED(f"Error: {e}"))
        sys.exit(2)
    sys.exit(0)


def _run_conform(in_arg, out_arg, pal_arg, iwad_arg, keep, replace):
    project = is_project_root()

    # ---- Mode-specific switches -------------------------------------------------
    if project and replace:
        print(YEL("Note: -replace has no effect in project mode (in-place is the default)."))
        replace = False
    if not project and keep:
        print(YEL("Note: -keep has no effect outside a project (a renamed copy is the default)."))
        keep = False
    if out_arg and (keep or replace):
        raise ConformError(f"{'-keep' if keep else '-replace'} cannot be combined "
                           f"with an explicit output name")

    # ---- Input ----------------------------------------------------------------
    def candidates(p):
        yield p
        if not os.path.splitext(p)[1]:
            yield p + ".wad"

    in_path = None
    for c in candidates(in_arg):
        if os.path.isfile(c):
            in_path = c
            break
    if not in_path and project:
        for d in CONFORM_INPUT_DIRS:
            for c in candidates(in_arg):
                p = os.path.join(d, c)
                if os.path.isfile(p):
                    in_path = p
                    break
            if in_path:
                break
    if not in_path:
        where = " (also searched " + ", ".join(CONFORM_INPUT_DIRS) + ")" if project else ""
        raise ConformError(f"input WAD not found: {in_arg}{where}")

    # ---- Output ---------------------------------------------------------------
    stem = os.path.splitext(os.path.basename(in_path))[0]
    make_out_dir = False
    if out_arg:
        if os.path.dirname(out_arg):
            out_path = out_arg
        elif project:
            out_path = os.path.join(CONFORM_OUTPUT_DIR, out_arg)
            make_out_dir = True
        else:
            out_path = out_arg
    elif project:
        name = f"{stem}{CONFORM_SUFFIX}.wad" if keep else os.path.basename(in_path)
        out_path = os.path.join(CONFORM_OUTPUT_DIR, name)
        make_out_dir = True
    elif replace:
        out_path = in_path
    else:
        out_path = os.path.join(os.path.dirname(in_path), f"{stem}{CONFORM_SUFFIX}.wad")

    out_dir = os.path.dirname(full_path(out_path))
    if not os.path.isdir(out_dir):
        if make_out_dir:
            os.makedirs(out_dir, exist_ok=True)
        else:
            raise ConformError(f"output folder does not exist: {out_dir}")

    in_place = full_path(in_path).lower() == full_path(out_path).lower()

    # ---- Read input + source palette ------------------------------------------
    try:
        with open(in_path, "rb") as f:
            in_data = f.read()
    except OSError as e:
        raise ConformError(f"cannot read input WAD: {e}")
    magic, entries = wad_parse(in_data, in_path)

    src_lump = wad_last_lump(entries, "PLAYPAL")
    if not src_lump:
        raise ConformError(f"{in_path} has no PLAYPAL - it already uses the IWAD "
                           f"palette, so there is nothing to conform")
    if len(src_lump) < 768:
        raise ConformError(f"{in_path}: PLAYPAL is shorter than 768 bytes")
    src_pal0 = bytes(src_lump[:768])

    # ---- Target palette ---------------------------------------------------------
    pal_label = None
    pals = None
    if pal_arg:
        if not os.path.isfile(pal_arg):
            raise ConformError(f"palette source not found: {pal_arg}")
        pals = load_palette_file(pal_arg)
        pal_label = pal_arg
    elif project:
        path, pals = find_project_palette()
        if pals:
            pal_label = f"{path} (project)"

    if pals is None:
        iwad_path = None
        if iwad_arg:
            iwad_path = IWADS.get(iwad_arg)
            if not iwad_path:
                raise ConformError(f"unknown IWAD '{iwad_arg}'. Available: {IWAD_LIST}")
            label = iwad_arg
        else:
            label = None
            if project:
                for p, src in project_iwad_candidates():
                    if os.path.isfile(p):
                        iwad_path, label = p, src
                        break
            if not iwad_path:
                iwad_path = IWADS.get(CONFORM_DEFAULT_IWAD)
                label = CONFORM_DEFAULT_IWAD
                if not iwad_path:
                    raise ConformError(f"default IWAD '{CONFORM_DEFAULT_IWAD}' is not "
                                       f"defined in the settings iwads list")
        if not os.path.isfile(iwad_path):
            raise ConformError(f"IWAD not found: {iwad_path}")
        pals = load_palette_file(iwad_path)
        pal_label = f"{iwad_path} (IWAD: {label})"

    playpal, generated = build_playpal(pals)
    tgt_pal0 = playpal[:768]

    print("dmake conform2palette - repalette WAD graphics")
    print(f"  Mode       : {'DoomTools project' if project else 'standalone'}")
    print(f"  Input WAD  : {in_path}")
    print(f"  Output WAD : {out_path}{'  (in place)' if in_place else ''}")
    print(f"  Palette    : {pal_label}")
    if generated:
        print(DGRY("               (single palette - tints 1-13 generated)"))
    print("")

    if tgt_pal0 == src_pal0:
        print("Nothing to do: the input's palette already matches the target palette.")
        return

    # ---- Convert --------------------------------------------------------------
    matcher = PaletteMatcher(tgt_pal0)
    table = matcher.index_table(src_pal0)
    new_entries, stats, warnings = conform_entries(entries, matcher, table, playpal)

    # ---- Write (temp file + swap, so a failure never damages anything) -----
    fd, tmp = tempfile.mkstemp(prefix=".conform_", suffix=".tmp", dir=out_dir)
    os.close(fd)
    try:
        wad_write(tmp, magic, new_entries)
        os.replace(tmp, out_path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ConformError(f"cannot write output WAD: {e}")

    # ---- Report ---------------------------------------------------------------
    for w in warnings:
        print(YEL(f"  Warning: {w}"))
    if warnings:
        print("")
    print(f"  Doom pictures remapped : {stats['picture']}")
    print(f"  Flats remapped         : {stats['flat']}")
    print(f"  PNG -> Doom picture    : {stats['png-picture']}")
    print(f"  PNG -> flat            : {stats['png-flat']}")
    print(f"  PLAYPAL replaced       : {stats['playpal']}")
    print(f"  Copied unchanged       : {stats['copied']}")
    print("")
    print(GRN(f"Wrote {len(new_entries)} lump(s) -> {out_path}"))


# ==============================================================================
# Main mode: split args at "--", run doommake, optionally run doom.bat
# ==============================================================================
def invoke_main_mode(arg_list):
    dm_args        = []
    doom_args      = []
    seen_dash_dash = False

    for a in arg_list:
        if not seen_dash_dash and a == "--":
            seen_dash_dash = True
        elif seen_dash_dash:
            doom_args.append(a)
        else:
            dm_args.append(a)

    # ---- Run doommake ----------------------------------------------------------
    dm_err = run_cmd("doommake", dm_args)

    if dm_err != 0:
        sys.exit(dm_err)

    # ---- Run doom.bat if requested ----------------------------------------------
    if seen_dash_dash:
        sys.exit(run_cmd("doom.bat", doom_args))

    sys.exit(0)


# ==============================================================================
# Dispatcher
# ==============================================================================
KEYWORD_MODES = ("update", "create", "explode", "watch", "texturex",
                 "editpatch", "strip", "conform2palette", "--targets")

def invoke_dmake(arg_list):
    if arg_list is None:
        arg_list = []

    # ---- Scan ALL arguments for special commands ---------------------------------
    for a in arg_list:
        kw = a.lower()
        if kw == "update":
            invoke_update_mode()
        elif kw == "create":
            invoke_create_mode(rest_after_keyword(arg_list, "create"))
        elif kw == "explode":
            invoke_explode_mode(rest_after_keyword(arg_list, "explode"))
        elif kw == "watch":
            invoke_watch_mode()
        elif kw == "texturex":
            invoke_texturex_mode(arg_list)
        elif kw == "editpatch":
            invoke_editpatch_mode(arg_list)
        elif kw == "strip":
            invoke_strip_mode(rest_after_keyword(arg_list, "strip"))
        elif kw == "conform2palette":
            invoke_conform_mode(rest_after_keyword(arg_list, "conform2palette"))
        elif kw == "--targets":
            show_targets_help()
            sys.exit(0)

    # ---- Help triggers ------------------------------------------------------------
    if arg_list:
        if arg_list[0].lower() in ("--help", "-h", "/h", "/?", "help"):
            show_dmake_help()
            sys.exit(0)

    invoke_main_mode(arg_list)


def rest_after_keyword(arg_list, keyword):
    """Return everything after the first occurrence of a keyword
    (case-insensitive)."""
    for i, a in enumerate(arg_list):
        if a.lower() == keyword.lower():
            return list(arg_list[i + 1:])
    return []


# ##############################################################################
# ##############################################################################
# ##                                                                          ##
# ##   HELP TEXT - EDIT BELOW                                                 ##
# ##                                                                          ##
# ##   All help screens live here so they are easy to find and update.       ##
# ##   They are plain print blocks - change wording/colours freely.          ##
# ##                                                                          ##
# ##############################################################################
# ##############################################################################

# ==============================================================================
# HELP: dmake --help / -h / /h / /? / help
# ==============================================================================
def show_dmake_help():
    print("")
    print(DCYN("=============================================================================="))
    print(WHT("  DMAKE  -  doommake wrapper with optional doom.bat launch"))
    print(DCYN("=============================================================================="))
    print("")
    print("  dmake forwards arguments to doommake. If " + YEL('"--"') + " is present, doom.bat is run")
    print("  after doommake finishes, receiving any arguments after the " + YEL('"--"') + ".")
    print("")

    print(WHT("USAGE"))
    print(GRY("  dmake [doommake_args...]              - Run doommake"))
    print(GRY("  dmake [doommake_args...] -- [args...] - Run doommake then doom.bat"))
    print(GRY("  dmake <command> [options]             - Run a special dmake command"))
    print("")

    print(WHT("SPECIAL COMMANDS"))
    print(CYN("  create    ") + "[Name] [-i/-h/-d ...] [-nodeco]     - Create a new tweaked DoomMake project")
    print(CYN("  explode   ") + "filename.wad [-i iwad] [-p]        - Explode a WAD into a DoomMake project")
    print(CYN("  watch     ") + "                                   - Watch project, rebuild on file changes")
    print(CYN("  texturex  ") + "[-x1|-x2] [-file wad] [-output txt] - Extract TEXTURE1/TEXTURE2 (both if neither)")
    print(CYN("  editpatch ") + "[-txt]                             - Open DECOHack patch editor GUI")
    print(CYN("  strip     ") + "input.wad [strip flags]            - Strip lumps out of a WAD (see STRIP OPTIONS)")
    print(CYN("  conform2palette ") + "in.wad [out.wad] [opts]    - Repalette every graphic in a WAD (see CONFORM2PALETTE)")
    print(CYN("  update    ") + "                                   - Update DoomTools to the latest version")
    print(CYN("  --targets ") + "                                   - Show all available doommake targets")
    print(CYN("  --help    ") + "                                   - Show this help")
    print("")

    print(WHT("CREATE OPTIONS"))
    print(GRY(f"  Project name defaults to {DEFAULTS.get('create_name', 'megawad')}; all options are optional."))
    print(YEL("  -i, -iwad       ") + f"iwad  IWAD to use (default: {DEFAULTS.get('create_iwad', 'doom2')})")
    print("                  " + GRY("Options: ") + DGRY(IWAD_LIST))
    print(YEL("  -h, -hacktype   ") + f"ht    DECOHack patch type to use (default: {DEFAULTS.get('create_hacktype', 'dsdhacked')})")
    print("                  " + GRY("Options: ") + DGRY(HACK_TYPE_LIST))
    print("                  " + DGRY("Error if combined with -nodeco."))
    print(YEL("  -d, -directory  ") + "dir   Directory to create the project in")
    print("                  " + DGRY(f"(default: {DEFAULTS.get('create_directory', './_DT_Projects/_Current')} - must be empty if it already exists)"))
    print(YEL("  -nodeco         ") + "      Skip the decohack module entirely - no DEHACKED patch at all")
    print("")

    print(WHT("EXPLODE OPTIONS"))
    print(YEL("  -i iwad    ") + f"IWAD to use (default: {DEFAULTS.get('create_iwad', 'doom2')})")
    print("             " + GRY("Options: ") + DGRY(IWAD_LIST))
    print(YEL("  -p         ") + "Use the input WAD's own PLAYPAL instead of the IWAD")
    print("             " + DGRY("(use for WADs with custom palettes)"))
    print("")

    print(WHT("TEXTUREX OPTIONS"))
    print(YEL("  -x1        ") + "Extract the TEXTURE1 lump")
    print(YEL("  -x2        ") + "Extract the TEXTURE2 lump")
    print("             " + DGRY("(omit both -x1 and -x2 to extract BOTH lumps)"))
    print(YEL("  -file wad  ") + r"Source WAD (default: .\build\textures.wad)")
    print(YEL("  -output f  ") + "Output filename, single lump only (default: texture1.txt / texture2.txt)")
    print("             " + DGRY("With -file: saved in current dir. Without: saved one dir up."))
    print("")

    print(WHT("EDITPATCH OPTIONS"))
    print(YEL("  -txt       ") + "Open the text file viewer instead of the patch editor")
    print("")

    print(WHT("STRIP OPTIONS"))
    for line in strip_flag_help_lines():
        print(line)
    print(YEL("  --lumps    ") + "NAME1 NAME2 ...  Strip the named lumps (any kind)")
    print(YEL("  --output f ") + "Output WAD (default: <inputname>_cleaned.wad next to the input)")
    print("             " + DGRY("Flags combine freely. Strip sets are defined in the conf;"))
    print("             " + DGRY("add a key there and it becomes a --<key> flag. Missing lumps skipped."))
    print("")

    print(WHT("CONFORM2PALETTE OPTIONS"))
    print(YEL("  -i, -iwad  ") + f"IWAD whose palette is the fallback target (default: {CONFORM_DEFAULT_IWAD})")
    print(YEL("  -pal src   ") + "Target palette: WAD, palette PNG, .pal, .gpl or raw PLAYPAL")
    print(YEL("  -keep      ") + f"Project mode: write <name>{CONFORM_SUFFIX}.wad instead of in place")
    print(YEL("  -replace   ") + "Outside a project: overwrite the input instead of a renamed copy")
    print("             " + DGRY("Run 'dmake conform2palette' alone for the full help."))
    print("")

    print(WHT("EXAMPLES"))
    print(GRY("  dmake create                          ") + DGRY("- megawad in ./_DT_Projects/_Current, doom2"))
    print(GRY("  dmake create MyWAD                    ") + DGRY("- MyWAD in ./_DT_Projects/_Current, doom2"))
    print(GRY("  dmake create MyWAD -i doom -d MyDir   ") + DGRY("- New doom project in MyDir folder"))
    print(GRY("  dmake create -iwad tnt -nodeco        ") + DGRY("- megawad, tnt IWAD, no DEHACKED patch"))
    print(GRY("  dmake explode summoner.wad            ") + DGRY("- Explode WAD using doom2 palette"))
    print(GRY("  dmake explode summoner.wad -p         ") + DGRY("- Explode WAD using its own palette"))
    print(GRY("  dmake explode summoner.wad -i tnt -p  ") + DGRY("- Explode with TNT IWAD, own palette"))
    print(GRY("  dmake texturex                       ") + DGRY(r"- Extract BOTH lumps from .\build\textures.wad"))
    print(GRY("  dmake texturex -x1                    ") + DGRY(r"- Extract only TEXTURE1 from .\build\textures.wad"))
    print(GRY("  dmake texturex -x2 -file mod.wad      ") + DGRY("- Extract TEXTURE2 from mod.wad to current dir"))
    print(GRY("  dmake strip mod.wad --clean           ") + DGRY("- Full strip -> mod_cleaned.wad"))
    print(GRY("  dmake strip mod.wad --lumps MAP01     ") + DGRY("- Strip only the MAP01 marker lump"))
    print(GRY("  dmake conform2palette mod.wad -pal mypal.png ") + DGRY(f"- -> mod{CONFORM_SUFFIX}.wad"))
    print(GRY("  dmake -- -skill 4 -warp 1             ") + DGRY("- Build then launch with doom.bat"))
    print(GRY("  dmake make -- -skill 4 -warp 1        ") + DGRY("- Run make then launch with doom.bat"))
    print(GRY("  dmake update                          ") + DGRY("- Update DoomTools"))
    print("")


# ==============================================================================
# HELP: dmake --targets
# ==============================================================================
def show_targets_help():
    print("")
    print("")
    print(WHT("DMAKE-ONLY commands:"))
    print(CYN("  dmake --targets            - Show this target list"))
    print(CYN("  dmake create [Name]        - Create a new tweaked DoomMake project (defaults: see -help)"))
    print(CYN("  dmake explode file.wad     - Explode a WAD into a DoomMake project"))
    print(CYN("  dmake watch                - Watch project and rebuild on file changes"))
    print(CYN("  dmake texturex             - Extract TEXTURE1/TEXTURE2 from a WAD"))
    print(CYN("  dmake editpatch            - Open DECOHack patch editor GUI"))
    print(CYN("  dmake strip input.wad      - Strip lumps out of a WAD (dmake strip for help)"))
    print(CYN("  dmake conform2palette in.wad - Repalette every graphic in a WAD (run alone for help)"))
    print(CYN("  dmake update               - Update DoomTools to the latest version"))
    print("")
    print(WHT("DEFAULT targets:"))
    print(GRY("  doommake all               - Full build + editor/texture WADs + release WAD (no zip)"))
    print(GRY("  doommake assets            - Convert and merge assets WAD"))
    print(GRY("  doommake clean             - Delete the build directory"))
    print(GRY("  doommake convert           - Convert graphics, sprites, sounds and palettes"))
    print(GRY("  doommake converttextures   - Convert texture flats and patches to Doom format"))
    print(GRY("  doommake editor            - Rebuild the editor WAD"))
    print(GRY("  doommake init              - Initialise the build directory"))
    print(GRY("  doommake make              - [MODIFIED] Full build + release WAD, no dist zip"))
    print(GRY("  doommake maps              - Merge the maps WAD"))
    print(GRY("  doommake maptextures       - Export a WAD of only textures used in maps"))
    print(GRY("  doommake patch             - Compile the DeHackEd patch and show budget"))
    print(GRY("  doommake rebuildpalettes   - Rebuild primary palettes and colormaps"))
    print(GRY("  doommake rebuildtextures   - Rebuild texture listings in src/textures"))
    print(GRY("  doommake release           - [MODIFIED] Full build + release, dehacked & palette WADs, dist zip"))
    print(GRY("  doommake textures          - Convert and merge textures WAD"))
    print("")
    print(WHT("TWEAK targets:"))
    print(YEL("  doommake complete          - Runs release, editorrelease, texturesrelease, playpal, deco (no zip)"))
    print(YEL("  doommake deco              - Compile DECOHack and build a DEHACKED-only WAD"))
    print(YEL("  doommake editorrelease     - Same as release, but ALL textures + only MAP99 (if present)"))
    print(YEL("  doommake editorreleasenotexturex - Same as editorrelease, but with no TEXTURE1/2, PNAMES, ANIMATED, SWITCHES"))
    print(YEL("  doommake final             - Same as complete, but also creates the dist zip"))
    print(YEL("  doommake fresh             - Clean build dir, then full build and create release WAD"))
    print(YEL("  doommake playpal           - Convert palettes and colormaps into a palette-only WAD"))
    print(YEL("  doommake texturesrelease   - Standard texture WAD, plus wadinfo/credits and palette data"))
    print("")


# ==============================================================================
# HELP: dmake strip  (shown when strip is run with no WAD, or no strip flags)
# ==============================================================================
def strip_flag_help_lines():
    """Render one help line per strip set defined in the conf, so the flag
    list always matches clean_strip_sets. Each line shows the flag and the
    lumps it strips (truncated if very long)."""
    lines = []
    for key, lumps in CLEAN_STRIP_SETS.items():
        flag = ("--" + key).ljust(11)
        joined = ", ".join(lumps)
        if len(joined) > 58:
            joined = joined[:55] + "..."
        lines.append(YEL("  " + flag) + "Strip " + joined)
    return lines


def show_strip_help():
    print("")
    print(DCYN("=============================================================================="))
    print(WHT("  DMAKE STRIP  -  strip lumps out of a WAD"))
    print(DCYN("=============================================================================="))
    print("")
    print("  Copies a WAD, removing the requested lumps. Everything kept is copied")
    print("  byte-for-byte; only the lump directory is rebuilt. The input WAD is")
    print("  never modified. Lumps that are not present are silently skipped.")
    print("")

    print(WHT("USAGE"))
    print(GRY("  dmake strip input.wad [strip flags] [--output newwadname.wad]"))
    print("")

    print(WHT("STRIP FLAGS") + GRY("  (defined in clean_strip_sets in the conf)"))
    for line in strip_flag_help_lines():
        print(line)
    print(YEL("  --lumps    ") + "NAME1 NAME2 ...  Strip the named lumps (any kind)")
    print("")

    print(WHT("OPTIONS"))
    print(YEL("  --output f ") + "Output WAD path (default: <inputname>_cleaned.wad next to input)")
    print("")

    print(WHT("NOTES"))
    print(GRY("  - Flags combine freely; all requested lump names are unioned together."))
    print(GRY("  - Strip sets live in the conf - add a key and it becomes a --<key> flag."))
    print(GRY("  - A lump that isn't found is skipped - it is never an error."))
    print(GRY("  - With no strip flags, nothing is done and this help is shown."))
    print(GRY("  - Unknown --flags are an error, listing the available ones."))
    print(GRY("  - Named 'strip' so it does not clash with the doommake 'clean'"))
    print(GRY("    build target - 'dmake clean' still deletes the build directory."))
    print("")

    print(WHT("EXAMPLES"))
    print(GRY("  dmake strip mod.wad --clean                    ") + DGRY("- Full strip -> mod_cleaned.wad"))
    print(GRY("  dmake strip mod.wad --texturex --anims         ") + DGRY("- Strip texture + animation lumps"))
    print(GRY("  dmake strip mod.wad --deco                     ") + DGRY("- Strip DEHACKED and DECOHACK"))
    print(GRY("  dmake strip mod.wad --info                     ") + DGRY("- Strip __VER__, WADINFO, CREDITS"))
    print(GRY("  dmake strip mod.wad --clean --output final.wad ") + DGRY("- Full strip to a chosen name"))
    print("")


# ==============================================================================
# HELP: dmake conform2palette  (shown when run with no input WAD)
# ==============================================================================
def show_conform_help():
    print("")
    print(DCYN("=============================================================================="))
    print(WHT("  DMAKE CONFORM2PALETTE  -  repalette every graphic in a WAD"))
    print(DCYN("=============================================================================="))
    print("")
    print("  Converts every graphic in a WAD to a new palette and writes a classic-")
    print("  format copy. Doom pictures, flats, palettised PNGs and truecolour PNGs")
    print("  all come out as standard Doom pictures (or raw flats in a flat")
    print("  namespace). PLAYPAL is replaced with the target's 14 palettes. Every")
    print("  other lump (colormaps, TEXTUREx, ENDOOM, sounds, maps...) is copied")
    print("  byte-for-byte. Names, order, markers and namespaces never change.")
    print("")

    print(WHT("USAGE"))
    print(GRY("  dmake conform2palette input.wad [output.wad] [-iwad name] [-pal source]"))
    print(GRY("                                  [-keep | -replace]"))
    print("")

    print(WHT("OPTIONS"))
    print(YEL("  -i, -iwad name ") + f"IWAD palette used as the fallback target (default: {CONFORM_DEFAULT_IWAD})")
    print("                 " + GRY("Options: ") + DGRY(IWAD_LIST))
    print(YEL("  -pal source    ") + "Target palette. Accepts: WAD with PLAYPAL, raw PLAYPAL lump,")
    print("                 " + "DoomTools palette PNG (256 wide, one palette per row),")
    print("                 " + "SLADE pal0.png (16x16 grid), colourmap PNG (row 0),")
    print("                 " + ".pal (raw, JASC or RIFF; one or many palettes), GIMP .gpl")
    print(YEL("  -input / -output ") + "Explicit alternatives to the positional names")
    print(YEL("  -keep          ") + f"Project mode only: write <name>{CONFORM_SUFFIX}.wad")
    print(YEL("  -replace       ") + "Outside a project only: overwrite the input WAD")
    print("")

    print(WHT("OUTSIDE A DOOMTOOLS PROJECT"))
    print(GRY(f"  Output  : <name>{CONFORM_SUFFIX}.wad next to the input (-replace: overwrite)"))
    print(GRY(f"  Palette : -pal, else the -iwad palette (default {CONFORM_DEFAULT_IWAD})"))
    print("")

    print(WHT("INSIDE A DOOMTOOLS PROJECT ROOT"))
    print(GRY("  Input   : as given, else searched in src/wads/textures, then build"))
    print(GRY(f"  Output  : src/wads/textures/<name>.wad (-keep: <name>{CONFORM_SUFFIX}.wad)"))
    print(GRY("            A bare output filename is also placed in src/wads/textures."))
    print(GRY("  Palette : -pal, else the first found in src/assets/palettes,"))
    print(GRY("            build/convert/palettes, src/convert/palettes"))
    print(GRY("  IWAD    : -iwad, else doom-loader.conf, doommake.properties, doom2"))
    print("")

    print(WHT("NOTES"))
    print(GRY("  - The input WAD must have its own PLAYPAL (that is the source palette)."))
    print(GRY("  - A single-palette source gets the standard 13 tint palettes generated."))
    print(GRY("  - Nearest colour by weighted RGB; ties go to the lowest index."))
    print(GRY("  - PNG grAb offsets carry over; partial alpha is ordered-dithered."))
    print(GRY("  - Overwrites go via a temp file, so a failure never damages the input."))
    print(GRY("  - WAD files only (no PK3)."))
    print("")

    print(WHT("EXAMPLES"))
    print(GRY("  dmake conform2palette res.wad -pal mypal.png      ") + DGRY(f"- -> res{CONFORM_SUFFIX}.wad"))
    print(GRY("  dmake conform2palette res.wad new.wad -iwad tnt   ") + DGRY("- TNT palette, -> new.wad"))
    print(GRY("  dmake conform2palette res.wad -pal p.pal -replace ") + DGRY("- overwrite res.wad"))
    print(GRY("  dmake conform2palette res.wad                     ") + DGRY("- (project) auto palette, in place"))
    print(GRY("  dmake conform2palette res.wad -keep               ") + DGRY(f"- (project) -> res{CONFORM_SUFFIX}.wad"))
    print("")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    try:
        apply_settings()
        invoke_dmake(sys.argv[1:])
    except KeyboardInterrupt:
        print("")
        sys.exit(130)
    except BrokenPipeError:
        # Output was piped to something that closed early (head, more, etc.)
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
