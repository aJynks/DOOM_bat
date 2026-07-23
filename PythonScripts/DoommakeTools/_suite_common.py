#!/usr/bin/env python3
# ==============================================================================
# _suite_common.py
# ------------------------------------------------------------------------------
# Shared support module for the dmake tool suite:
#     dmake.bat     -> dmake_script.py
#     doommake-tweak.bat -> doommake-tweak-script.py
#     doom.bat      -> doom_script.py
#
# Provides:
#   - Settings loading from _dmake_settings.conf (JSON + full-line comments)
#   - ANSI colour helpers (NO_COLOR aware, VT enabled on Windows)
#   - PATH lookup / external command execution
#
# All three scripts live in the same PATH directory, so a plain
# "import _suite_common" resolves (sys.path[0] is the script's own folder).
#
# Pure stdlib. No dependencies.
# ==============================================================================

import json
import os
import subprocess
import sys

SETTINGS_FILENAME = "_dmake_settings.conf"


# ==============================================================================
# Colour handling
# ==============================================================================
def _use_colour():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if not k32.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            if not k32.SetConsoleMode(h, mode.value | 0x0004):  # ENABLE_VT
                return False
        except Exception:
            return False
    return True


COLOUR = _use_colour()

# Foreground codes approximating the PowerShell console colours
FG = {
    "black":     "30",
    "red":       "91",
    "green":     "92",
    "yellow":    "93",
    "cyan":      "96",
    "white":     "97",
    "gray":      "37",
    "darkgray":  "90",
    "darkcyan":  "36",
}

BG = {
    "darkblue": "44",
    "gray":     "47",
    "black":    "40",
}


def paint(text, fg=None, bg=None):
    """Wrap text in ANSI colour codes. Returns text unchanged when colour
    is disabled (NO_COLOR, not a TTY, or VT unavailable)."""
    if not COLOUR:
        return text
    codes = []
    if fg and fg in FG:
        codes.append(FG[fg])
    if bg and bg in BG:
        codes.append(BG[bg])
    if not codes:
        return text
    return "\x1b[" + ";".join(codes) + "m" + text + "\x1b[0m"


def WHT(t):  return paint(t, "white")
def CYN(t):  return paint(t, "cyan")
def DCYN(t): return paint(t, "darkcyan")
def YEL(t):  return paint(t, "yellow")
def GRY(t):  return paint(t, "gray")
def DGRY(t): return paint(t, "darkgray")
def RED(t):  return paint(t, "red")
def GRN(t):  return paint(t, "green")


def clear_screen():
    """Clear the console, for the interactive menu redraw."""
    if COLOUR:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
    else:
        os.system("cls" if os.name == "nt" else "clear")


# ==============================================================================
# PATH / command helpers
# ==============================================================================
def find_on_path(name):
    """Locate a file on PATH by exact filename (equivalent of where.exe).
    Also checks this module's own directory first, so suite files are found
    even if the tools dir somehow isn't on PATH. Returns the first match
    or None."""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, name)
    if os.path.isfile(cand):
        return cand

    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        cand = os.path.join(d.strip('"'), name)
        if os.path.isfile(cand):
            return cand
    return None


def resolve_cmd(name):
    """Resolve an external command the way cmd would: try the bare name
    through PATHEXT, then explicit common extensions. Returns a full path
    or None."""
    import shutil
    p = shutil.which(name)
    if p:
        return p
    for ext in (".exe", ".bat", ".cmd", ".py"):
        p = shutil.which(name + ext)
        if p:
            return p
    return None


def run_cmd(name, args, feed=None):
    """Run an external command by name (resolved on PATH). .py files are
    dispatched through the py launcher; everything else runs directly. If
    `feed` is given it is piped to stdin. Returns the exit code, or 2 if
    the tool cannot be found or launched."""
    path = resolve_cmd(name)
    if not path:
        print(f"Error: '{name}' not found on PATH.")
        return 2

    if path.lower().endswith(".py"):
        launcher = resolve_cmd("py") or sys.executable
        cmd = [launcher, path] + list(args)
    else:
        cmd = [path] + list(args)

    try:
        if feed is not None:
            r = subprocess.run(cmd, input=feed, text=True)
        else:
            r = subprocess.run(cmd)
        return r.returncode
    except FileNotFoundError:
        print(f"Error: could not launch '{name}' ({path}).")
        return 2


def run_exe(exe_path, args):
    """Run an executable by full path (no PATH resolution). Returns the
    exit code."""
    try:
        r = subprocess.run([exe_path] + list(args))
        return r.returncode
    except FileNotFoundError:
        print(f"Error: could not launch: {exe_path}")
        return 2
    except OSError as e:
        print(f"Error: could not launch {exe_path}: {e}")
        return 2


# ==============================================================================
# Path helpers
# ==============================================================================
def full_path(p):
    """Absolute, normalised path anchored at the current working directory."""
    return os.path.normpath(os.path.abspath(p))


def normalize_dirpath(path):
    """Trim trailing \\ or / from a directory path, but never strip a drive
    root ("D:\\" stays "D:\\")."""
    if not path:
        return path
    p = path.rstrip("\\/")
    if len(p) == 2 and p[1] == ":" and p[0].isalpha():
        p += "\\"
    return p


# ==============================================================================
# Settings
# ==============================================================================
def load_settings():
    """Locate _dmake_settings.conf on PATH, strip full-line # and //
    comments (blanked rather than removed so JSON error line numbers stay
    accurate), and parse it as JSON.

    Returns (path, data). Exits 2 with a clear message on any failure."""
    path = find_on_path(SETTINGS_FILENAME)
    if not path:
        print(f"Error: {SETTINGS_FILENAME} not found on PATH.")
        print("The dmake tool suite (dmake / doom / doommake-tweak) reads all of its")
        print("editable data from that shared file. It should sit in the same")
        print("PATH directory as the tools themselves.")
        sys.exit(2)

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw_lines = f.read().splitlines()
    except OSError as e:
        print(f"Error: cannot read {path}: {e}")
        sys.exit(2)

    cooked = []
    for ln in raw_lines:
        t = ln.lstrip()
        cooked.append("" if (t.startswith("#") or t.startswith("//")) else ln)

    try:
        data = json.loads("\n".join(cooked))
    except json.JSONDecodeError as e:
        print(f"Error: cannot parse {path}")
        print(f"  line {e.lineno}, column {e.colno}: {e.msg}")
        print("  (Reminder: backslashes in paths must be doubled, no trailing")
        print("   commas, and comments must be on their own line.)")
        sys.exit(2)

    if not isinstance(data, dict):
        print(f"Error: {path} must contain a JSON object at the top level.")
        sys.exit(2)

    return path, data


def require_sections(path, data, keys):
    """Exit 2 if any of the named top-level sections are missing."""
    missing = [k for k in keys if k not in data]
    if missing:
        print(f"Error: {path} is missing required section(s): "
              f"{', '.join(missing)}")
        sys.exit(2)


def as_str_dict(obj):
    """Coerce a parsed JSON object into a plain {str: str} dict."""
    if not isinstance(obj, dict):
        return {}
    return {str(k): str(v) for k, v in obj.items()}


def as_str_list(obj):
    """Coerce a parsed JSON array into a plain [str] list."""
    if not isinstance(obj, list):
        return []
    return [str(x) for x in obj]
