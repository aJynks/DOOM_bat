#!/usr/bin/env python3
# ==============================================================================
# doom_script.py
# ------------------------------------------------------------------------------
# DOOM RUNNER - source port launcher wrapper.
#
# Pure-Python replacement for doom_runDoomWad.ps1. Called by doom.bat (thin
# shim), or runnable directly:  py doom_script.py [args...]
#
# All editable data (source port exes, IWAD paths, pak WAD lists, default
# port/IWAD) lives in the shared __suite_settings.txt, alongside dmake and
# doommake-tweak.
#
# Behaviour (unchanged from the PowerShell version):
#   - Selects a source port by keyword, an IWAD by keyword
#   - Expands pak sets; --add puts paks at the END of the -file list
#   - Normal folders: 1 WAD auto-loads, >1 shows an ASCII menu, 0 launches bare
#   - DoomMake project folders: uses doom-loader.conf for release/dehacked/
#     iwad/warp/skill/defaultPort
#   - choco/crl use -merge instead of -file, and pick up ./build/dehacked.deh
#   - kex gets -skipmovies appended
#   - Unrecognised arguments pass straight through to the port
#
# Pure stdlib. No dependencies.
# ==============================================================================

import os
import re
import sys

from _suite_common import (
    load_settings, require_sections, as_str_dict,
    clear_screen, paint, run_exe, COLOUR,
    CYN, YEL, WHT, GRY, RED,
)

# ==============================================================================
# Settings (populated from __suite_settings.txt at startup)
# ==============================================================================
SOURCE_PORTS = {}
IWADS        = {}
PAKS         = {}
DEFAULT_PORT = "nyan"
DEFAULT_IWAD = "doom2"


def apply_settings():
    global SOURCE_PORTS, IWADS, PAKS, DEFAULT_PORT, DEFAULT_IWAD

    path, data = load_settings()
    require_sections(path, data, ("iwads", "source_ports", "paks", "defaults"))

    SOURCE_PORTS = as_str_dict(data["source_ports"])
    IWADS        = as_str_dict(data["iwads"])

    paks = data["paks"]
    if not isinstance(paks, dict):
        print(f"Error: {path} 'paks' must be an object of name -> [wad paths]")
        sys.exit(2)
    PAKS = {}
    for name, wads in paks.items():
        if not isinstance(wads, list):
            print(f"Error: {path} pak '{name}' must be a list of WAD paths")
            sys.exit(2)
        PAKS[str(name)] = [str(w) for w in wads]

    defaults     = data["defaults"]
    DEFAULT_PORT = str(defaults.get("run_port", "nyan"))
    DEFAULT_IWAD = str(defaults.get("run_iwad", "doom2"))


# ==============================================================================
# Error helpers
# ==============================================================================
def show_boxed_error(lines):
    max_len = max(len(x) for x in lines)
    border = "-" * (max_len + 6)
    print(RED(border))
    for line in lines:
        print(RED("|  " + line.ljust(max_len) + "  |"))
    print(RED(border))


def validate_path(path, kind, name):
    """Exit 1 with a boxed error if a path is blank or missing."""
    if path is None or not str(path).strip():
        show_boxed_error([f"-- Error : {kind} <{name}> is blank --"])
        sys.exit(1)
    if not os.path.exists(path):
        show_boxed_error([f"-- Error : {kind} <{name}> not found --"])
        sys.exit(1)


# ==============================================================================
# Argument helpers
# ==============================================================================
def has_arg(args_list, flag):
    """True if the flag is present, either exactly (-warp) or in a merged
    form (-warp7, -warp=7, -warp:7)."""
    fl = flag.lower()
    for a in args_list:
        if a is None:
            continue
        s = str(a).lower()
        if s == fl:
            return True
        if s.startswith(fl) and len(s) > len(fl):
            if re.match(r"^[0-9=:\-]$", s[len(fl)]):
                return True
    return False


def remove_flag_with_value(args_list, flag):
    """Drop a flag and its value, including merged forms."""
    if not args_list:
        return []
    fl = flag.lower()
    out = []
    i = 0
    while i < len(args_list):
        a = args_list[i]
        if a is None:
            i += 1
            continue
        s  = str(a)
        sl = s.lower()

        # exact match: drop it and its following value
        if sl == fl:
            i += 2
            continue

        # merged forms: -warp7, -warp=7, -warp:7
        if sl.startswith(fl) and len(sl) > len(fl):
            if re.match(r"^[0-9=:\-]$", sl[len(fl)]):
                i += 1
                continue

        out.append(s)
        i += 1
    return out


def ensure_kex_skipmovies(port_name, args_list):
    """KEX-only: append -skipmovies at the END of the final command args."""
    if port_name != "kex":
        return list(args_list)
    for a in args_list:
        if a is not None and str(a).lower() == "-skipmovies":
            return list(args_list)
    return list(args_list) + ["-skipmovies"]


def get_load_command(port_name):
    """Chocolate Doom and CRL need -merge for vanilla-style resource
    merging. Other ports use the normal -file behaviour."""
    if port_name.lower() in ("choco", "crl"):
        return "-merge"
    return "-file"


# ==============================================================================
# Debug launch helper
# ==============================================================================
def format_command_arg(arg):
    if arg is None:
        return '""'
    s = str(arg)
    if s == "":
        return '""'
    if re.search(r"[\s&()\[\]{}^=;!'+,`~]", s):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def invoke_doom_with_debug(exe_path, arg_list):
    print("")
    print(YEL("== Final Doom command =="))
    pretty = format_command_arg(exe_path) + " " + \
        " ".join(format_command_arg(a) for a in arg_list)
    print(CYN(pretty))
    print("")
    return run_exe(exe_path, arg_list)


# ==============================================================================
# ASCII menu selector (arrow keys, redraw per keypress)
# ==============================================================================
def _read_key():
    """Return one of: 'up', 'down', 'enter', 'esc', or None.

    Windows uses msvcrt (arrow keys arrive as a two-byte sequence prefixed
    with 0x00 or 0xE0). POSIX uses termios raw mode so the menu is testable
    outside Windows."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "up"
            if ch2 == b"P":
                return "down"
            return None
        if ch == b"\r":
            return "enter"
        if ch == b"\x1b":
            return "esc"
        return None

    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "up"
            if seq == "[B":
                return "down"
            return "esc"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_from_list_ascii(title, items, display_key="name"):
    """Boxed arrow-key selector. `items` is a list of dicts; a synthetic
    [None] entry is prepended. Returns the chosen dict, or None if
    cancelled."""
    if len(items) < 1:
        return None

    none_item = {"name": "[None]", "full_name": None, "__is_none": True}
    items = [none_item] + list(items)

    rows = [str(it.get(display_key, "")) for it in items]
    max_item_len = max(len(r) for r in rows)
    inner_w = max(max_item_len + 4, len(title) + 2)

    top    = "+" + ("-" * inner_w) + "+"
    sep    = "|" + ("-" * inner_w) + "|"
    bottom = "+" + ("-" * inner_w) + "+"

    def fill_line(content, fg, bg):
        print(paint("|" + content.ljust(inner_w) + "|", fg, bg))

    idx = 0
    try:
        while True:
            clear_screen()

            print(paint(top, "cyan", "darkblue"))
            print(paint("|" + (" " + title).ljust(inner_w) + "|",
                        "white", "darkblue"))
            print(paint(sep, "cyan", "darkblue"))

            for i, row in enumerate(rows):
                label = "  " + row
                if i == idx:
                    fill_line(label, "black", "gray")
                else:
                    fill_line(label, "white", "darkblue")

            fill_line("", "white", "darkblue")
            fill_line("  Up/Down: move   Enter: select   Esc: cancel",
                      "gray", "darkblue")
            print(paint(bottom, "cyan", "darkblue"))

            key = _read_key()
            if key == "up" and idx > 0:
                idx -= 1
            elif key == "down" and idx < len(rows) - 1:
                idx += 1
            elif key == "enter":
                return items[idx]
            elif key == "esc":
                return None
    finally:
        clear_screen()


# ==============================================================================
# DoomMake helpers
# ==============================================================================
def get_doommake_project_name(project_props_path):
    if not os.path.isfile(project_props_path):
        show_boxed_error(
            ["-- Error : DoomMake file <doommake.project.properties> not found --"])
        sys.exit(1)

    line = None
    try:
        with open(project_props_path, "r", encoding="utf-8-sig",
                  errors="replace") as f:
            for raw in f:
                if re.match(r"^\s*doommake\.project\.name\s*=", raw):
                    line = raw
                    break
    except OSError:
        line = None

    if not line or not line.strip():
        show_boxed_error(
            ["-- Error : doommake.project.name not found in project properties --"])
        sys.exit(1)

    name = line.split("=", 1)[1].strip()
    if not name:
        show_boxed_error(
            ["-- Error : doommake.project.name is blank in project properties --"])
        sys.exit(1)

    return name


def get_doommake_iwad_path(doommake_props_path):
    if not os.path.isfile(doommake_props_path):
        return None
    try:
        with open(doommake_props_path, "r", encoding="utf-8-sig",
                  errors="replace") as f:
            for raw in f:
                if re.match(r"^\s*doommake\.iwad\s*=", raw):
                    v = raw.split("=", 1)[1].strip()
                    return v if v else None
    except OSError:
        return None
    return None


def ensure_doom_loader_conf(conf_path, release_wad_rel_path):
    """Create doom-loader.conf on first run in a DoomMake project."""
    if os.path.isfile(conf_path):
        return

    iwad_path = get_doommake_iwad_path(
        os.path.join(os.getcwd(), "doommake.properties"))

    # Doom1-style episode IWADs need a two-part warp ("1 1")
    warp_default = "1"
    if iwad_path and iwad_path.strip():
        iwad_file = os.path.basename(iwad_path).lower()
        if iwad_file in ("doom.wad", "doom1.wad", "free1.wad", "freedoom1.wad"):
            warp_default = "1 1"

    content = [
        "Wads:",
        f"release = {release_wad_rel_path}",
        "dehacked = ./build/dehacked.wad",
        "iwad = " + (iwad_path if iwad_path else ""),
        "",
        "Default Warps",
        f"warp = {warp_default}",
        "skill = 4",
        "",
        f"defaultPort = {DEFAULT_PORT}",
        "",
    ]

    try:
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
    except OSError as e:
        show_boxed_error([f"-- Error : cannot write doom-loader.conf : {e} --"])
        sys.exit(1)


def read_doom_loader_conf(conf_path):
    if not os.path.isfile(conf_path):
        show_boxed_error(["-- Error : doom-loader.conf not found --"])
        sys.exit(1)

    cfg = {
        "release": None, "dehacked": None, "iwad": None,
        "warp": None, "skill": None, "defaultport": None,
    }

    try:
        with open(conf_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        show_boxed_error([f"-- Error : cannot read doom-loader.conf : {e} --"])
        sys.exit(1)

    for raw in lines:
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        if re.match(r"^\s*Wads\s*:\s*$", line):
            continue
        if re.match(r"^\s*Default\s+Warps\s*:?\s*$", line):
            continue

        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$", line)
        if m:
            k = m.group(1).strip().lower()
            v = m.group(2).strip()
            if k in cfg:
                cfg[k] = v

    return cfg


# ==============================================================================
# Help
# ==============================================================================
def header_line(text):
    print(CYN(text))


def section_header(title):
    print("")
    print(YEL("== " + title + " =="))


def show_help():
    print("")
    header_line("===============================================================================")
    header_line(" DOOM RUNNER - doom")
    header_line("===============================================================================")

    section_header("USAGE")
    print(WHT("  doom [PORT] [IWAD] [PAK...] [OPTIONS...] [--add PAK...]"))
    print("")
    print(GRY("  Examples:"))
    print(GRY("    doom"))
    print(GRY("    doom doom2"))
    print(GRY("    doom dsda doom2"))
    print(GRY("    doom pak1"))
    print(GRY("    doom dsda doom2 pak1 -warp 2 -skill 4"))
    print(GRY("    doom -warp 7                 (uses default skill from doom-loader.conf in project dirs)"))
    print(GRY("    doom pak1 --add pak2          (pak1 loads first, pak2 loads LAST)"))
    print(GRY("    doom -warp 5 -nosound pak1 --add pak3 pak6"))
    print(GRY("    doom -file mywad.wad          (if [None] is selected in the menu, this CLI -file is used)"))

    section_header("WHAT THIS SCRIPT DOES")
    print(WHT("  Launcher wrapper that:"))
    print(WHT("  - Selects a source port by keyword"))
    print(WHT("  - Selects an IWAD by keyword"))
    print(WHT("  - Expands pak sets (pak1, pak2, ...)"))
    print(WHT("  - In normal folders:"))
    print(WHT("      * 1 WAD in folder -> auto loads it"))
    print(WHT("      * >1 WADs -> ASCII menu to pick one (or [None])"))
    print(WHT("      * [None] -> no folder WAD is added; any CLI -file is used as-is"))
    print(WHT("      * 0 WADs -> launches port + IWAD only"))
    print(WHT("  - In DoomMake project folders:"))
    print(WHT("      * uses doom-loader.conf to load ./build/<project>.wad"))
    print(WHT("      * optionally loads ./build/dehacked.wad (skips if missing)"))
    print(WHT("      * reads default warp/skill from doom-loader.conf, CLI overrides them"))

    section_header("KEYWORDS")
    print(WHT("  SOURCE PORTS (edit 'source_ports' in __suite_settings.txt):"))
    print(GRY("    " + ", ".join(sorted(SOURCE_PORTS.keys()))))
    print("")
    print(WHT("  IWADS (edit 'iwads' in __suite_settings.txt):"))
    print(GRY("    " + ", ".join(sorted(IWADS.keys()))))
    print("")
    print(WHT("  PAKS (edit 'paks' in __suite_settings.txt):"))
    paks = ", ".join(sorted(PAKS.keys())) or "(none defined)"
    print(GRY("    " + paks))

    section_header("PAK BEHAVIOUR")
    print(WHT("  Paks expand into a list of WAD paths that are loaded FIRST."))
    print(WHT("  Then the folder-selected WAD (normal mode) OR project release WAD (DoomMake mode)."))
    print("")
    print(WHT("  --add <pak> loads paks at the VERY END of the -file list instead."))
    print(WHT("  You can chain multiple pak names after --add."))
    print("")
    print(GRY("  Example:"))
    print(GRY("    doom pak1 --add pak2"))
    print(GRY("  Becomes:"))
    print(GRY("    -file <pak1 wads...> <auto/project wad> <pak2 wads...>"))
    print("")
    print(WHT("  doom --listpaks    (prints all defined pak names and exits)"))

    section_header("DOOMMAKE PROJECT MODE")
    print(WHT("  A DoomMake project is detected when ALL of these exist in the current folder:"))
    print(GRY("    doommake.properties"))
    print(GRY("    doommake.script"))
    print(GRY("    doommake.project.properties"))
    print("")
    print(WHT("  On first run, if doom-loader.conf does not exist, it is created."))
    print(WHT("  The release wad name is taken from doommake.project.properties:"))
    print(GRY("    doommake.project.name=MyProject"))
    print(WHT("  Which becomes:"))
    print(GRY("    release = ./build/MyProject.wad"))
    print("")
    print(WHT("  doom-loader.conf format:"))
    print(GRY("    Wads:"))
    print(GRY("    release = ./build/MyProject.wad"))
    print(GRY("    dehacked = ./build/dehacked.wad"))
    print(GRY("    iwad = D:/.../doom2.wad"))
    print(GRY(""))
    print(GRY("    Default Warps"))
    print(GRY("    warp = 1"))
    print(GRY("    skill = 4"))
    print("")
    print(WHT("  Notes:"))
    print(WHT("  - release is REQUIRED (must exist)"))
    print(WHT("  - dehacked is OPTIONAL (if missing, it is ignored)"))
    print(WHT("  - warp/skill are DEFAULTS only; CLI overrides them if provided"))
    print(WHT("  - If you include the word 'menu' anywhere (project folders only), warp/skill are ignored."))
    print(WHT("  - --skip : omit the release WAD entirely (ignored outside project folders)"))
    print(GRY("             Useful when passing a custom -file directly:"))
    print(GRY("             doom doom -nosound -warp 1 1 -file build\\editor-assets.wad --skip"))

    section_header("OPTIONS PASS-THROUGH")
    print(WHT("  Any arguments not recognised as PORT/IWAD/PAK are passed to the port."))
    print(GRY("  Examples:"))
    print(GRY("    doom dsda doom2 -warp 1 -skill 4 -complevel 9"))
    print(GRY("    doom woof doom2 -record demo.lmp"))

    section_header("EDITING SETTINGS")
    print(WHT("  All editable data lives in __suite_settings.txt (shared with dmake"))
    print(WHT("  and doommake-tweak), in the same PATH folder as these tools:"))
    print(WHT("  1) source_ports : keyword -> exe path"))
    print(WHT("  2) iwads        : keyword -> iwad path"))
    print(WHT("  3) paks         : pakN    -> list of WAD paths"))
    print(WHT("  4) defaults     : run_port / run_iwad"))
    print("")
    print(WHT("  It is JSON, so backslashes in paths must be doubled:"))
    print(GRY('    "pak1": ['))
    print(GRY('        "D:\\\\path\\\\one.wad",'))
    print(GRY('        "D:\\\\path\\\\two.wad"'))
    print(GRY("    ]"))
    print(WHT("  Use commas between items, no trailing comma on the last item."))

    section_header("HELP")
    print(GRY("  doom --help"))
    print(GRY("  doom -h"))
    print(GRY("  doom /?"))
    print("")
    print(GRY("  doom --listpaks    (list all defined pak names)"))

    print("")
    header_line("===============================================================================")
    print("")


def show_list_paks():
    print("")
    print(YEL("== Defined Paks =="))
    if not PAKS:
        print(GRY("  (none defined)"))
    else:
        for key in sorted(PAKS.keys()):
            n = len(PAKS[key])
            print(CYN(f"  {key}  ({n} WAD{'s' if n != 1 else ''})"))
    print("")


# ==============================================================================
# Argument scanning shared by both modes
# ==============================================================================
def scan_args(command_raw, swallow_menu=False):
    """Split raw args into port/iwad/pak selections and pass-through args."""
    state = {
        "port_name": DEFAULT_PORT,
        "iwad_name": DEFAULT_IWAD,
        "port": SOURCE_PORTS.get(DEFAULT_PORT),
        "iwad": IWADS.get(DEFAULT_IWAD),
        "filtered": [],
        "pak_wads": [],
        "add_pak_wads": [],
        "used_pak_names": [],
        "port_explicit": False,
        "iwad_explicit": False,
    }
    in_add_mode = False

    for arg in command_raw:
        if arg is None:
            continue
        s = str(arg)

        # --add switch: subsequent pak names go to the tail list
        if s.lower() == "--add":
            in_add_mode = True
            continue

        # swallow 'menu' so ports never see it as a filename/arg
        if swallow_menu and s.lower() == "menu":
            continue

        if s in IWADS:
            state["iwad"] = IWADS[s]
            state["iwad_name"] = s
            state["iwad_explicit"] = True
            continue

        if s in SOURCE_PORTS:
            state["port"] = SOURCE_PORTS[s]
            state["port_name"] = s
            state["port_explicit"] = True
            continue

        if s in PAKS:
            if len(PAKS[s]) == 0:
                show_boxed_error([f"-- Error : Pak <{s}> contains no WADs --"])
                sys.exit(1)
            if in_add_mode:
                state["add_pak_wads"].extend(PAKS[s])
            else:
                state["used_pak_names"].append(s)
                state["pak_wads"].extend(PAKS[s])
            continue

        state["filtered"].append(s)

    return state


def validate_selection(state):
    validate_path(state["port"], "Source Port", state["port_name"])
    validate_path(state["iwad"], "IWAD", state["iwad_name"])

    for i, w in enumerate(state["pak_wads"]):
        name = "{0}#{1}".format("+".join(state["used_pak_names"]), i + 1)
        validate_path(w, "Pak WAD", name)

    for i, w in enumerate(state["add_pak_wads"]):
        validate_path(w, "Add-Pak WAD", f"add#{i + 1}")


# ==============================================================================
# Main
# ==============================================================================
def main(argv):
    apply_settings()

    command_raw = list(argv)

    # ---- Help (early exit) ---------------------------------------------------
    help_tokens = ("--help", "-help", "/help", "help", "-h", "/?")
    if any(str(a).lower() in help_tokens for a in command_raw):
        show_help()
        return 0

    # ---- --listpaks (early exit) --------------------------------------------
    listpak_tokens = ("--listpaks", "-listpaks", "/listpaks")
    if any(str(a).lower() in listpak_tokens for a in command_raw):
        show_list_paks()
        return 0

    # ---- --skip: strip unconditionally; only meaningful in DoomMake mode -----
    skip_release = False
    cleaned = []
    for a in command_raw:
        if a is not None and str(a).lower() != "--skip":
            cleaned.append(a)
        else:
            skip_release = True
    command_raw = cleaned

    # ---- Detect DoomMake project in the current directory --------------------
    cwd = os.getcwd()
    required = ("doommake.properties", "doommake.script",
                "doommake.project.properties")
    has_project = all(os.path.isfile(os.path.join(cwd, f)) for f in required)

    if has_project:
        return run_doommake_mode(command_raw, cwd, skip_release)
    return run_normal_mode(command_raw)


# ------------------------------------------------------------------------------
# DoomMake project mode
# ------------------------------------------------------------------------------
def run_doommake_mode(command_raw, cwd, skip_release):
    project_name = get_doommake_project_name(
        os.path.join(cwd, "doommake.project.properties"))

    conf_path   = os.path.join(cwd, "doom-loader.conf")
    release_rel = f"./build/{project_name}.wad"

    ensure_doom_loader_conf(conf_path, release_rel)
    loader = read_doom_loader_conf(conf_path)

    # menu mode: if 'menu' appears anywhere, ignore ALL -warp/-skill (CLI + conf)
    menu_mode = any(a is not None and str(a).lower() == "menu"
                    for a in command_raw)

    state = scan_args(command_raw, swallow_menu=True)

    # conf iwad overrides the default, unless the user set one on the CLI
    if not state["iwad_explicit"] and loader["iwad"] and loader["iwad"].strip():
        state["iwad"] = loader["iwad"]
        state["iwad_name"] = "conf"

    # conf defaultPort applies only if the user did not specify a port
    if loader["defaultport"] and loader["defaultport"].strip() \
            and not state["port_explicit"]:
        conf_port = loader["defaultport"].lower()
        if conf_port in SOURCE_PORTS:
            state["port_name"] = conf_port
            state["port"]      = SOURCE_PORTS[conf_port]

    validate_selection(state)

    # ---- Resolve loader paths relative to the current directory --------------
    release_path = None
    if not skip_release:
        if not loader["release"] or not loader["release"].strip():
            show_boxed_error(
                ["-- Error : doom-loader.conf missing key <release> --"])
            sys.exit(1)
        release_path = os.path.join(cwd, loader["release"])
        validate_path(release_path, "Project WAD", "release")

    # Chocolate Doom / CRL need the compiled DEH loaded separately.
    # This intentionally checks ./build/dehacked.deh, not the dehacked WAD entry.
    dehacked_deh_path = None
    if state["port_name"] in ("choco", "crl"):
        candidate = os.path.join(cwd, "build", "dehacked.deh")
        if os.path.isfile(candidate):
            dehacked_deh_path = candidate

    # Build the PWAD list: paks first, then release (unless --skip), then --add.
    # The .deh patch is NOT in this list; it is appended as -deh afterwards.
    file_list = []
    file_list.extend(state["pak_wads"])
    if not skip_release:
        file_list.append(release_path)
    file_list.extend(state["add_pak_wads"])

    filtered = state["filtered"]

    if menu_mode:
        filtered = remove_flag_with_value(filtered, "-warp")
        filtered = remove_flag_with_value(filtered, "-skill")
    else:
        # Apply conf defaults ONLY if the user did not supply them
        if not has_arg(filtered, "-warp"):
            if loader["warp"] and loader["warp"].strip():
                warp_parts = [p for p in re.split(r"\s+", loader["warp"]) if p]
                if warp_parts:
                    filtered = filtered + ["-warp"] + warp_parts
        if not has_arg(filtered, "-skill"):
            if loader["skill"] and loader["skill"].strip():
                filtered = filtered + ["-skill", loader["skill"]]

    filtered = ensure_kex_skipmovies(state["port_name"], filtered)
    load_cmd = get_load_command(state["port_name"])

    if file_list:
        launch_args = ["-iwad", state["iwad"], load_cmd] + file_list
    else:
        launch_args = ["-iwad", state["iwad"]]

    if dehacked_deh_path is not None:
        launch_args += ["-deh", dehacked_deh_path]

    launch_args += filtered

    return invoke_doom_with_debug(state["port"], launch_args)


# ------------------------------------------------------------------------------
# Normal mode (NOT a DoomMake project)
# ------------------------------------------------------------------------------
def run_normal_mode(command_raw):
    state = scan_args(command_raw, swallow_menu=False)
    validate_selection(state)

    # WAD detection / selection in the current directory
    wad_path = os.getcwd()
    try:
        wad_files = sorted(
            (e for e in os.scandir(wad_path)
             if e.is_file() and e.name.lower().endswith(".wad")),
            key=lambda e: e.name)
    except OSError:
        wad_files = []

    wad_full_path = None

    if len(wad_files) == 1:
        wad_full_path = wad_files[0].path
    elif len(wad_files) > 1:
        items = [{"name": e.name, "full_name": e.path} for e in wad_files]
        selected = select_from_list_ascii(
            f"Select a WAD to run ( {wad_path} )", items, "name")
        if selected is None:
            return 0
        if selected.get("__is_none"):
            wad_full_path = None
        else:
            wad_full_path = selected["full_name"]

    filtered = state["filtered"]

    if state["pak_wads"] or wad_full_path is not None or state["add_pak_wads"]:
        file_list = []
        file_list.extend(state["pak_wads"])
        if wad_full_path is not None:
            file_list.append(wad_full_path)
        file_list.extend(state["add_pak_wads"])

        filtered = ensure_kex_skipmovies(state["port_name"], filtered)
        load_cmd = get_load_command(state["port_name"])
        launch_args = ["-iwad", state["iwad"], load_cmd] + file_list + filtered
        return invoke_doom_with_debug(state["port"], launch_args)

    filtered = ensure_kex_skipmovies(state["port_name"], filtered)
    launch_args = ["-iwad", state["iwad"]] + filtered
    return invoke_doom_with_debug(state["port"], launch_args)


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
