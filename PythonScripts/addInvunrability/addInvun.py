#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# INVUN SOURCE ALIASES — edit these if your invun WAD locations change
# ─────────────────────────────────────────────────────────────────────────────
INVUN_ALIASES = {
    "grey":     r"D:\Projects\DoomProjects\_SourcePorts\_Wads and Mods\_tweaks\All Ports\Invuns\doom2-pal0-NewInVun-brown.wad",
    "brown":    r"D:\Projects\DoomProjects\_SourcePorts\_Wads and Mods\_tweaks\All Ports\Invuns\doom2-pal0-NewInVun-grey.wad",
}
INVUN_DEFAULT = "brown"
# ─────────────────────────────────────────────────────────────────────────────
# IWAD PATHS — edit these if your IWAD locations change
# ─────────────────────────────────────────────────────────────────────────────
IWAD_ALIASES = {
    "doom":     r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom.wad",
    "doom2":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad",
    "tnt":      r"D:\Projects\DoomProjects\_SourcePorts\_iwads\tnt.wad",
    "plutonia": r"D:\Projects\DoomProjects\_SourcePorts\_iwads\plutonia.wad",
    "heretic":  r"D:\Projects\DoomProjects\_SourcePorts\_iwads\heretic.wad",
    "hexen":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\hexen.wad",
    "free1":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom1.wad",
    "free2":    r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom2.wad",
}
IWAD_DEFAULT = "doom2"
# ─────────────────────────────────────────────────────────────────────────────

"""
addInvun — swap the invulnerability colormap row into a WAD's COLORMAP.

Reads the primary COLORMAP from an input WAD (or an IWAD if the input has
none), replaces row 32 (the invulnerability map) with row 32 taken from a
source WAD's COLORMAP, and writes a minimal PWAD containing only the patched
colormap lump(s).

Colormap lumps are always exactly 8704 bytes (34 rows x 256 bytes):
    rows  0-31  light levels
    row   32    invulnerability map  <-- the row this tool swaps
    row   33    unused/filler
"""

import os
import struct
import sys

COLORMAP_SIZE  = 34 * 256          # 8704 bytes
INVUN_OFFSET   = 32 * 256          # byte offset of row 32
INVUN_ROW_SIZE = 256

# ── colour handling ──────────────────────────────────────────────────────────

def _supports_colour():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
                return False
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # VT processing
        except Exception:
            return False
    return True

_COLOUR = _supports_colour()

def c(code, text):
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text

BOLD, CYAN, GREEN, YELLOW, RED, DIM = "1", "1;36", "1;32", "1;33", "1;31", "90"

def err(msg):
    print(c(RED, f"ERROR: {msg}"), file=sys.stderr)
    sys.exit(1)

# ── help ─────────────────────────────────────────────────────────────────────

def show_help():
    invun_names = ", ".join(INVUN_ALIASES)
    iwad_names  = ", ".join(IWAD_ALIASES)
    try:
        _print_help(invun_names, iwad_names)
    except BrokenPipeError:
        pass
    sys.exit(0)


def _print_help(invun_names, iwad_names):
    print(f"""
{c(BOLD, 'addInvun — swap the invulnerability colormap row into a WAD COLORMAP')}

{c(CYAN, 'USAGE')}
  addInvun input.wad [source.wad | alias] [--iwad path|alias] [+2ndary]

{c(CYAN, 'WHAT IT DOES')}
  {c(DIM, 'Copies row 32 (the invulnerability map) of the source WAD COLORMAP')}
  {c(DIM, 'into the input WAD COLORMAP — the lighting rows (0-31) are untouched.')}
  {c(DIM, 'Writes <inputStem>-invun.wad (PWAD) next to the input WAD, containing')}
  {c(DIM, 'only the patched colormap lump(s).')}

{c(CYAN, 'ARGUMENTS')}
  {c(GREEN, 'input.wad')}        WAD whose COLORMAP is used as the base.
                   {c(DIM, 'If it has no COLORMAP, --iwad becomes required and')}
                   {c(DIM, 'supplies the base colormap instead.')}
  {c(GREEN, 'source')}           WAD (path) or alias providing the invulnerability row.
                   {c(DIM, f'Aliases: {invun_names}')}
                   {c(DIM, f'Default if omitted: {INVUN_DEFAULT}')}

{c(CYAN, 'OPTIONS')}
  {c(GREEN, '--iwad path|alias')}  Fallback base colormap when input.wad has none.
                     {c(DIM, f'Aliases: {iwad_names}')}
                     {c(DIM, f'Bare --iwad uses the default: {IWAD_DEFAULT}')}
  {c(GREEN, '+2ndary')}            Also patch every secondary colormap lump found in
  {c(GREEN, '+secondary')}         the input WAD (any lump of exactly 8704 bytes that
                     {c(DIM, 'is not COLORMAP, e.g. BLUMAP, REDMAP) and include')}
                     {c(DIM, 'them in the output WAD under their original names.')}
  {c(GREEN, '-h  --help  -help')}  Show this help.

{c(CYAN, 'EXAMPLES')}
  addInvun mymap.wad
      {c(DIM, f'Patch mymap.wad COLORMAP with the "{INVUN_DEFAULT}" alias invun row.')}
  addInvun mymap.wad grey
      {c(DIM, 'Use the "grey" alias as the invun source.')}
  addInvun mymap.wad D:\\wads\\custom.wad
      {c(DIM, 'Use an explicit WAD as the invun source.')}
  addInvun mymap.wad grey --iwad doom2
      {c(DIM, 'mymap.wad has no COLORMAP — take the base from doom2.wad.')}
  addInvun mymap.wad brown +2ndary
      {c(DIM, 'Also patch secondary colormaps (BLUMAP etc.) from mymap.wad.')}
""")

# ── WAD reading / writing ────────────────────────────────────────────────────

def read_wad_directory(path):
    """Return (data, [(name, offset, size), ...]) for a WAD file."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        err(f"Cannot read '{path}': {e}")

    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        err(f"'{path}' is not a valid WAD file (bad header).")

    numlumps, diroffset = struct.unpack_from("<ii", data, 4)
    if diroffset < 0 or diroffset + numlumps * 16 > len(data):
        err(f"'{path}' has a corrupt directory.")

    lumps = []
    for i in range(numlumps):
        entry = data[diroffset + i * 16 : diroffset + i * 16 + 16]
        offset, size = struct.unpack_from("<ii", entry, 0)
        name = entry[8:16].split(b"\0")[0].decode("ascii", "replace").upper()
        lumps.append((name, offset, size))
    return data, lumps


def get_lump(data, lumps, name):
    """Return bytes of first lump with the given name, or None."""
    for lname, offset, size in lumps:
        if lname == name:
            return data[offset : offset + size]
    return None


def get_colormap(path, label):
    """Read a WAD and return its COLORMAP lump bytes, validating size."""
    data, lumps = read_wad_directory(path)
    cmap = get_lump(data, lumps, "COLORMAP")
    if cmap is None:
        return None, data, lumps
    if len(cmap) != COLORMAP_SIZE:
        err(f"COLORMAP in {label} '{path}' is {len(cmap)} bytes — "
            f"expected {COLORMAP_SIZE} (34 x 256). Not a valid colormap.")
    return cmap, data, lumps


def write_pwad(path, lump_list):
    """Write a PWAD containing the given [(name, bytes), ...] lumps."""
    body = bytearray()
    directory = bytearray()
    lump_data_start = 12
    pos = lump_data_start
    for name, payload in lump_list:
        body += payload
        directory += struct.pack("<ii", pos, len(payload))
        directory += name.encode("ascii")[:8].ljust(8, b"\0")
        pos += len(payload)

    header = b"PWAD" + struct.pack("<ii", len(lump_list), lump_data_start + len(body))
    try:
        with open(path, "wb") as f:
            f.write(header + body + directory)
    except OSError as e:
        err(f"Cannot write '{path}': {e}")

# ── argument handling ────────────────────────────────────────────────────────

def resolve_alias(value, table, kind):
    """Resolve an alias or return the value as a path (must exist)."""
    key = value.lower()
    if key in table:
        path = table[key]
        if not os.path.isfile(path):
            err(f"{kind} alias '{value}' points to '{path}' which does not exist.\n"
                f"       Edit the alias table at the top of addInvun.py.")
        return path
    if not os.path.isfile(value):
        err(f"'{value}' is not a known {kind} alias and not an existing file.\n"
            f"       Known aliases: {', '.join(table)}")
    return value


def parse_args(argv):
    if not argv or any(a.lower() in ("-h", "--help", "-help") for a in argv):
        show_help()

    do_secondary = False
    args = []
    iwad_value = None
    i = 0
    while i < len(argv):
        a = argv[i]
        al = a.lower()
        if al in ("+2ndary", "+secondary"):
            do_secondary = True
        elif al in ("--iwad", "-iwad"):
            if i + 1 < len(argv) and not argv[i + 1].startswith(("-", "+")):
                iwad_value = argv[i + 1]
                i += 1
            else:
                iwad_value = IWAD_DEFAULT
        elif a.startswith("-"):
            err(f"Unknown option '{a}'. Use -h for help.")
        else:
            args.append(a)
        i += 1

    if not args:
        err("No input WAD given (options were supplied but no WAD). Use -h for help.")
    if len(args) > 2:
        err(f"Too many positional arguments: {args}")

    input_path = args[0]
    source_value = args[1] if len(args) == 2 else INVUN_DEFAULT
    return input_path, source_value, iwad_value, do_secondary

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    input_path, source_value, iwad_value, do_secondary = parse_args(sys.argv[1:])

    if not os.path.isfile(input_path):
        err(f"Input WAD '{input_path}' does not exist.")

    # ── base colormap: input WAD, falling back to --iwad ──
    base_cmap, input_data, input_lumps = get_colormap(input_path, "input WAD")
    base_from_iwad = None

    if base_cmap is None:
        if iwad_value is None:
            found = []
            fseen = set()
            for name, offset, size in input_lumps:
                if size == COLORMAP_SIZE and name not in fseen:
                    fseen.add(name)
                    found.append(name)
            extra = ""
            if found:
                extra = (f"\n       Note: the input WAD does contain "
                         f"{len(found)} colormap-sized lump(s): {', '.join(found)}\n"
                         f"       but none is named COLORMAP, so there is no primary "
                         f"colormap to use as a base.")
            err(f"'{input_path}' contains no COLORMAP lump.\n"
                f"       You must also supply the IWAD to take the base colormap from:\n"
                f"           addInvun {input_path} {source_value} --iwad {IWAD_DEFAULT}\n"
                f"       Known IWAD aliases: {', '.join(IWAD_ALIASES)}{extra}")
        iwad_path = resolve_alias(iwad_value, IWAD_ALIASES, "IWAD")
        base_cmap, _, _ = get_colormap(iwad_path, "IWAD")
        if base_cmap is None:
            err(f"IWAD '{iwad_path}' contains no COLORMAP lump either. "
                f"Cannot obtain a base colormap.")
        base_from_iwad = iwad_path

    # ── invulnerability row from the source WAD ──
    source_path = resolve_alias(source_value, INVUN_ALIASES, "invun source")
    src_cmap, _, _ = get_colormap(source_path, "source WAD")
    if src_cmap is None:
        err(f"Source WAD '{source_path}' contains no COLORMAP lump.\n"
            f"       The whole point is to copy its invulnerability row — "
            f"it must have a COLORMAP.")
    invun_row = src_cmap[INVUN_OFFSET : INVUN_OFFSET + INVUN_ROW_SIZE]

    def patch(cmap):
        return cmap[:INVUN_OFFSET] + invun_row + cmap[INVUN_OFFSET + INVUN_ROW_SIZE:]

    out_lumps = [("COLORMAP", patch(base_cmap))]

    # ── secondary colormaps: always detect from the input WAD; only patch
    #    and include them in the output when +2ndary/+secondary is set ──
    secondary_names = []
    seen = {"COLORMAP"}
    for name, offset, size in input_lumps:
        if size == COLORMAP_SIZE and name not in seen:
            seen.add(name)
            secondary_names.append(name)
            if do_secondary:
                out_lumps.append((name, patch(input_data[offset : offset + size])))

    # ── write output PWAD next to the input ──
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(os.path.dirname(os.path.abspath(input_path)),
                            f"{stem}-invun.wad")
    write_pwad(out_path, out_lumps)

    # ── report ──
    print(c(BOLD, "addInvun"))
    if base_from_iwad:
        print(f"  Base colormap : {c(YELLOW, base_from_iwad)} "
              f"{c(DIM, '(input WAD had no COLORMAP)')}")
    else:
        print(f"  Base colormap : {input_path}")
    print(f"  Invun row from: {source_path}")
    if secondary_names:
        joined = ", ".join(secondary_names)
        if do_secondary:
            print(f"  Secondaries   : {joined} {c(DIM, '(patched + included)')}")
        else:
            print(f"  Secondaries   : {c(YELLOW, joined)} "
                  f"{c(DIM, '(detected, not patched — use +2ndary to include them)')}")
    print(f"  {c(GREEN, 'Wrote')}         : {out_path} "
          f"{c(DIM, f'({len(out_lumps)} lump' + ('s' if len(out_lumps) != 1 else '') + ')')}")


if __name__ == "__main__":
    main()