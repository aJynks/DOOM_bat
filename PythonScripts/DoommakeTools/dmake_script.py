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
#   - Shared editable data lives in _dmake_settings.conf, loaded via
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

from _suite_common import (
    load_settings, require_sections, as_str_dict, as_str_list,
    find_on_path, resolve_cmd, run_cmd,
    full_path, normalize_dirpath,
    WHT, CYN, DCYN, YEL, GRY, DGRY, RED,
)

# ==============================================================================
# Settings - loaded from _dmake_settings.conf (found on PATH)
# ------------------------------------------------------------------------------
# All editable data (IWAD paths, hack types, clean strip sets, defaults) lives
# in _dmake_settings.conf, shared with doom_script.py and
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
                 "editpatch", "strip", "--targets")

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
