#!/usr/bin/env python3
"""
addInvun - recolour the invulnerability row of a WAD's COLORMAP.

Mimics the manual route (export COLORMAP as PNG -> greyscale + invert the
invun line -> Affinity "Recolour" -> convert back to the Doom palette) but
works directly on the lump bytes, so every row except row 32 is left
byte-for-byte untouched.

Colormap lumps are exactly 8704 bytes (34 rows x 256 bytes):
    rows  0-31  light levels
    row   32    invulnerability map  <-- the only row this tool changes
    row   33    unused/filler
"""
# -----------------------------------------------------------------------------
# INVUN COLOURS - the names you type on the command line (case-insensitive)
#
# Values are the same numbers as Affinity Photo's Recolour dialog:
#     hue         0-360   (0 red, 30 orange, 60 yellow, 120 green, 180 cyan,
#                          240 blue, 300 magenta)
#     saturation  0-100   (0 = pure grey, 100 = full colour)
#     lightness   -100 to 100  (0 = no shift)
#
# A bare number is just a hue, meaning (hue, 100, 0) - full saturation and no
# lightness shift, which is usually all you need. Use a (hue, sat, light)
# triple when you want more control.
#
# As with Recolour, black stays black, white stays white and mid-greys take
# the full colour - the brightness of each pixel always comes from the
# greyscale invun row, never from the colour entry.
#
# `addIn -set h,s,l:name` edits this table for you (adds or replaces a line),
# so keep it as one entry per line between `INVUN_COLOURS = {` and `}`.
# -----------------------------------------------------------------------------
INVUN_COLOURS = {
    # name       hue  -or-  (hue, saturation, lightness)
    "red":       0,
    "orange":   30,
    "gold":     45,
    "yellow":   55,
    "lime":     90,
    "green":   120,
    "teal":    165,
    "cyan":    180,
    "blue":    220,
    "indigo":  250,
    "purple":  275,
    "magenta": 300,
    "pink":    (320, 100, 15),
    "brown":   (30, 50, -15),
    "grey":    (0, 0, -33),
}
INVUN_DEFAULT = "grey"
# -----------------------------------------------------------------------------
# OUTPUT - written next to the input WAD as <wadName><OUTPUT_SUFFIX>.wad
# (overwritten if it exists). WADs ending in the suffix are skipped by the
# folder scan so they never get picked up as input.
# -----------------------------------------------------------------------------
OUTPUT_SUFFIX = "_invun"
# -----------------------------------------------------------------------------
# GREYSCALE WEIGHTS - used only when a WAD has its own (non-doom2) PLAYPAL and
# the base row has to be built from that palette's brightness.
# -----------------------------------------------------------------------------
LUMA = (0.299, 0.587, 0.114)
# -----------------------------------------------------------------------------

import base64
import colorsys
import os
import re
import shutil
import struct
import sys

COLORMAP_SIZE  = 34 * 256          # 8704 bytes
INVUN_OFFSET   = 32 * 256          # byte offset of row 32
ROW_SIZE       = 256
PAL_SIZE       = 768               # one palette, 256 x RGB

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

def warn(msg):
    print(c(YELLOW, f"WARNING: {msg}"), file=sys.stderr)

# ── colour table ─────────────────────────────────────────────────────────────

def check_hsl(hue, sat, light, label):
    """Range-check a (hue, sat, light) triple, erroring with `label`."""
    if not 0 <= hue <= 360:
        err(f"{label}: hue {hue:g} is outside 0-360.")
    if not 0 <= sat <= 100:
        err(f"{label}: saturation {sat:g} is outside 0-100.")
    if not -100 <= light <= 100:
        err(f"{label}: lightness {light:g} is outside -100 to 100.")


def fmt_hsl(hsl):
    """(hue, sat, light) -> 'h,s,l' - the form used by -set and 'Colour used'."""
    return ",".join(f"{v:g}" for v in hsl)


_HSL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

def parse_hsl(text, label="colour"):
    """Parse 'h,s,l' -> (h, s, l) floats, or None if it is not in that form."""
    m = _HSL_RE.match(text)
    if not m:
        return None
    hsl = tuple(float(v) for v in m.groups())
    check_hsl(*hsl, label=f"{label} '{text}'")
    return hsl


def load_colour_table():
    """Validate INVUN_COLOURS and return {lowercase name: (hue, sat, light)}."""
    table = {}
    for name, value in INVUN_COLOURS.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            hue, sat, light = float(value), 100.0, 0.0
        elif (isinstance(value, (tuple, list)) and len(value) == 3
              and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                      for v in value)):
            hue, sat, light = (float(v) for v in value)
        else:
            err(f"INVUN_COLOURS['{name}'] = {value!r} - must be a hue number "
                f"or a (hue, saturation, lightness) triple.")
        check_hsl(hue, sat, light, f"INVUN_COLOURS['{name}']")
        key = name.lower()
        if key in table:
            err(f"INVUN_COLOURS has '{name}' twice (names are case-insensitive).")
        table[key] = (hue, sat, light)
    if not table:
        err("INVUN_COLOURS is empty - add at least one colour.")
    if INVUN_DEFAULT.lower() not in table:
        err(f"INVUN_DEFAULT '{INVUN_DEFAULT}' is not in INVUN_COLOURS.")
    return table


def recolour(grey, hue, sat, light):
    """Affinity-style Recolour of one grey value (0-255) -> (r, g, b).

    The grey value becomes HSL lightness (after the lightness shift), hue and
    saturation come from the colour entry: black stays black, white stays
    white, mid-grey gets the full colour.
    """
    l = grey / 255.0
    if light > 0:
        l += (1.0 - l) * (light / 100.0)
    elif light < 0:
        l *= 1.0 + light / 100.0
    r, g, b = colorsys.hls_to_rgb((hue % 360.0) / 360.0, l, sat / 100.0)
    return (round(r * 255), round(g * 255), round(b * 255))


def nearest_index(pal, rgb, cache):
    """Nearest palette index to rgb (plain RGB distance, lowest index wins ties)."""
    hit = cache.get(rgb)
    if hit is not None:
        return hit
    r, g, b = rgb
    best, best_d = 0, None
    for i, (pr, pg, pb) in enumerate(pal):
        d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if best_d is None or d < best_d:
            best, best_d = i, d
            if d == 0:
                break
    cache[rgb] = best
    return best


def build_invun_row(base_row, pal, hue, sat, light):
    """Recolour the greyscale base row and palettise it back to `pal`."""
    cache = {}
    return bytes(nearest_index(pal, recolour(g, hue, sat, light), cache)
                 for g in base_row)

# ── embedded doom2 data ──────────────────────────────────────────────────────

def parse_palette(raw):
    return [tuple(raw[i * 3 : i * 3 + 3]) for i in range(256)]


def doom2_palette():
    return parse_palette(base64.b64decode("".join(DOOM2_PLAYPAL_B64)))


def doom2_colormap():
    return base64.b64decode("".join(DOOM2_COLORMAP_B64))

# ── help / list ──────────────────────────────────────────────────────────────

def show_help(table):
    names = ", ".join(table)
    try:
        print(f"""
{c(BOLD, 'addInvun - recolour the invulnerability row of a WAD COLORMAP')}

{c(CYAN, 'USAGE')}
  addIn [colour | h,s,l] [file.wad] [--picker]
  addIn -set h,s,l:name
  {c(DIM, 'Arguments can be given in any order. All are optional.')}

{c(CYAN, 'WHAT IT DOES')}
  {c(DIM, 'Takes the doom2 invulnerability row as a greyscale, inverted base,')}
  {c(DIM, 'recolours it Affinity-Recolour style with the chosen colour, converts')}
  {c(DIM, 'it back to the palette and swaps it into row 32 of the COLORMAP. Every')}
  {c(DIM, 'other byte of the colormap is left untouched.')}
  {c(DIM, f'Writes <wadName>{OUTPUT_SUFFIX}.wad next to the input WAD (overwriting it)')}
  {c(DIM, 'containing only the patched COLORMAP.')}

  {c(GREEN, 'COLORMAP')}   {c(DIM, "the WAD's own, or the embedded doom2 one if it has none")}
  {c(GREEN, 'PLAYPAL')}    {c(DIM, "the WAD's own, or the embedded doom2 one if it has none")}
  {c(GREEN, 'Base row')}   {c(DIM, 'embedded doom2 row; if the WAD has its own non-doom2')}
             {c(DIM, "PLAYPAL, built from that palette's brightness instead")}

{c(CYAN, 'ARGUMENTS')}
  {c(GREEN, 'colour')}           A name from INVUN_COLOURS at the top of the script.
                   {c(DIM, f'Colours: {names}')}
                   {c(DIM, f'Default if omitted: {INVUN_DEFAULT}')}
  {c(GREEN, 'h,s,l')}            A one-off colour as hue,saturation,lightness - the
                   {c(DIM, 'same numbers as Affinity Recolour, e.g. 210,85,-10.')}
  {c(GREEN, 'file.wad')}         WAD to patch. If omitted, the current folder is
                   {c(DIM, 'scanned: one WAD is used automatically, several give a')}
                   {c(DIM, f'selection menu. *{OUTPUT_SUFFIX}.wad files are ignored.')}

{c(CYAN, 'OPTIONS')}
  {c(GREEN, '--picker  -picker')}  Open a Recolour-style window (hue / saturation /
                     {c(DIM, 'lightness sliders, colour square, in-game preview) set')}
                     {c(DIM, 'to the chosen colour. OK patches with the picked values')}
                     {c(DIM, 'and prints them as "Colour used : h,s,l".')}
  {c(GREEN, '-set h,s,l:name')}    Save a colour into INVUN_COLOURS in this script, then
                     {c(DIM, 'exit (no WAD is patched). An existing name is replaced')}
                     {c(DIM, 'and its old value printed. A .bak copy is made first.')}
  {c(GREEN, '--list  -list')}      List the colours with an in-palette preview ramp.
  {c(GREEN, '-h  --help  /?')}     Show this help.

{c(CYAN, 'EXAMPLES')}
  addIn
      {c(DIM, f'Patch the WAD in this folder with "{INVUN_DEFAULT}".')}
  addIn red
      {c(DIM, 'Patch the WAD in this folder with red (menu if there are several).')}
  addIn mymap.wad blue
      {c(DIM, 'Patch mymap.wad with blue.')}
  addIn red --picker
      {c(DIM, 'Open the picker starting from red, patch with whatever you pick.')}
  addIn 210,85,-10
      {c(DIM, 'Patch with a one-off colour (e.g. pasted from "Colour used").')}
  addIn -set 210,85,-10:blood
      {c(DIM, 'Save that colour as a preset called "blood".')}
  addIn --list
      {c(DIM, 'Show every colour name and what it looks like.')}
""")
    except BrokenPipeError:
        pass
    sys.exit(0)


def show_list(table):
    pal = doom2_palette()
    try:
        pad = max(len(k) for k in table)
        print(f"\n{c(CYAN, 'INVUN COLOURS')}  {c(DIM, '(h,s,l) - preview in the doom2 palette')}")
        steps = [round(i * 255 / 23) for i in range(24)]
        for name, (h, s, l) in table.items():
            tag = f"  {c(DIM, '(default)')}" if name == INVUN_DEFAULT.lower() else ""
            vals = fmt_hsl((h, s, l)).ljust(12)
            swatch = ""
            if _COLOUR:
                cache = {}
                for g in steps:
                    r, gg, b = pal[nearest_index(pal, recolour(g, h, s, l), cache)]
                    swatch += f"\033[48;2;{r};{gg};{b}m \033[0m"
            print(f"  {c(GREEN, name.ljust(pad))}  {c(DIM, vals)} {swatch}{tag}")
        print()
    except BrokenPipeError:
        pass
    sys.exit(0)

# ── picker window ────────────────────────────────────────────────────────────

def import_tkinter():
    try:
        import tkinter
        return tkinter
    except ImportError:
        err("--picker needs tkinter, which comes with Python but was not installed.\n"
            "       It cannot be installed with pip: re-run the Python installer,\n"
            "       choose Modify, and tick 'tcl/tk and IDLE'.")


def _hls_rgb(hue, l, s):
    r, g, b = colorsys.hls_to_rgb((hue % 360.0) / 360.0, l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def run_picker(start, pal, start_label):
    """Affinity-style Recolour window. Returns (h, s, l) ints, or None if cancelled."""
    tk = import_tkinter()
    try:
        root = tk.Tk()
    except tk.TclError as e:
        err(f"Cannot open the picker window: {e}")

    BG, FG, DIMFG = "#3c3c3c", "#e6e6e6", "#a0a0a0"
    ENTRY_BG, BTN_BG, BTN_HI = "#1f1f1f", "#565656", "#6a6a6a"
    FONT = ("Segoe UI", 10)
    TRACK_W, TRACK_H, KNOB_R = 300, 12, 8
    PAD = KNOB_R + 2

    root.title(f"addInvun - Recolour ({start_label})")
    root.configure(bg=BG)
    root.resizable(False, False)

    state = {"h": int(round(start[0])), "s": int(round(start[1])),
             "l": int(round(start[2])), "result": None}
    sliders = []

    class Slider:
        def __init__(self, parent, row, label, key, lo, hi, unit, track_fn):
            self.key, self.lo, self.hi, self.track_fn = key, lo, hi, track_fn
            tk.Label(parent, text=label, bg=BG, fg=FG, font=FONT, anchor="w").grid(
                row=row * 2, column=0, sticky="w", padx=14, pady=(10, 0))
            self.cv = tk.Canvas(parent, width=TRACK_W + 2 * PAD,
                                height=TRACK_H + 2 * PAD, bg=BG,
                                highlightthickness=0, cursor="hand2")
            self.cv.grid(row=row * 2 + 1, column=0, padx=(14 - PAD, 4))
            box = tk.Frame(parent, bg=BG)
            box.grid(row=row * 2 + 1, column=1, padx=(0, 14), sticky="w")
            self.var = tk.StringVar()
            self.entry = tk.Entry(box, textvariable=self.var, width=5, bg=ENTRY_BG,
                                  fg=FG, insertbackground=FG, relief="flat",
                                  font=FONT, justify="right")
            self.entry.pack(side="left", ipady=3)
            tk.Label(box, text=unit, bg=BG, fg=DIMFG, font=FONT, width=2,
                     anchor="w").pack(side="left", padx=(3, 0))
            self.cv.bind("<Button-1>", self.on_drag)
            self.cv.bind("<B1-Motion>", self.on_drag)
            self.cv.bind("<MouseWheel>", self.on_wheel)
            self.entry.bind("<Return>", self.commit)
            self.entry.bind("<KP_Enter>", self.commit)
            self.entry.bind("<FocusOut>", self.commit)

        def set_value(self, v):
            state[self.key] = max(self.lo, min(self.hi, int(round(v))))
            refresh()

        def on_drag(self, e):
            t = max(0.0, min(1.0, (e.x - PAD) / TRACK_W))
            self.set_value(self.lo + t * (self.hi - self.lo))

        def on_wheel(self, e):
            self.set_value(state[self.key] + (1 if e.delta > 0 else -1))

        def commit(self, e=None):
            try:
                v = float(self.var.get())
            except ValueError:
                v = state[self.key]
            self.set_value(v)
            return "break"

        def draw(self):
            cv = self.cv
            cv.delete("all")
            y0, y1 = PAD, PAD + TRACK_H
            step = 2
            for x in range(0, TRACK_W, step):
                colour = _hex(self.track_fn(x / (TRACK_W - 1)))
                cv.create_rectangle(PAD + x, y0, PAD + x + step, y1,
                                    outline="", fill=colour)
            t = (state[self.key] - self.lo) / (self.hi - self.lo)
            kx, ky = PAD + t * TRACK_W, PAD + TRACK_H / 2
            cv.create_oval(kx - KNOB_R, ky - KNOB_R, kx + KNOB_R, ky + KNOB_R,
                           outline="#ffffff", width=2, fill=_hex(self.track_fn(t)))
            self.var.set(str(state[self.key]))

    top = tk.Frame(root, bg=BG)
    top.pack(fill="x", pady=(4, 0))
    sliders.append(Slider(top, 0, "Hue", "h", 0, 360, "\u00b0",
                          lambda t: _hls_rgb(t * 360, 0.5, 1.0)))
    sliders.append(Slider(top, 1, "Saturation", "s", 0, 100, "%",
                          lambda t: _hls_rgb(state["h"], 0.5, t)))
    sliders.append(Slider(top, 2, "Lightness", "l", -100, 100, "%",
                          lambda t: (round(t * 255),) * 3))

    # colour square + in-game preview strip
    bottom = tk.Frame(root, bg=BG)
    bottom.pack(fill="x", padx=14, pady=(14, 0))
    SW = 52
    swatch = tk.Canvas(bottom, width=SW, height=SW, bg=BG, highlightthickness=1,
                       highlightbackground="#222222")
    swatch.pack(side="left")
    right = tk.Frame(bottom, bg=BG)
    right.pack(side="left", padx=(12, 0), fill="x")
    tk.Label(right, text="In-game preview (palettised)", bg=BG, fg=DIMFG,
             font=("Segoe UI", 9), anchor="w").pack(anchor="w")
    STRIP_W, STRIP_H, STRIP_N = 256, 30, 64
    strip = tk.Canvas(right, width=STRIP_W, height=STRIP_H, bg=BG,
                      highlightthickness=1, highlightbackground="#222222")
    strip.pack(anchor="w", pady=(4, 0))

    def refresh():
        h, s, l = state["h"], state["s"], state["l"]
        for sl in sliders:
            sl.draw()
        swatch.delete("all")
        swatch.create_rectangle(0, 0, SW + 2, SW + 2, outline="",
                                fill=_hex(recolour(128, h, s, l)))
        strip.delete("all")
        cache = {}
        cell = STRIP_W / STRIP_N
        for i in range(STRIP_N):
            g = round(i * 255 / (STRIP_N - 1))
            rgb = pal[nearest_index(pal, recolour(g, h, s, l), cache)]
            strip.create_rectangle(round(i * cell), 0, round((i + 1) * cell) + 1,
                                   STRIP_H + 2, outline="", fill=_hex(rgb))

    def ok(e=None):
        # take any typed-but-uncommitted numbers first - committing one box
        # redraws the others and would overwrite what was typed in them
        pending = [(sl, sl.var.get()) for sl in sliders]
        for sl, text in pending:
            try:
                v = float(text)
            except ValueError:
                continue
            state[sl.key] = max(sl.lo, min(sl.hi, int(round(v))))
        state["result"] = (state["h"], state["s"], state["l"])
        root.destroy()

    def cancel(e=None):
        root.destroy()

    buttons = tk.Frame(root, bg=BG)
    buttons.pack(fill="x", padx=14, pady=14)
    for text, cmd in (("Cancel", cancel), ("OK", ok)):
        tk.Button(buttons, text=text, command=cmd, width=9, bg=BTN_BG, fg=FG,
                  activebackground=BTN_HI, activeforeground=FG, relief="flat",
                  font=FONT, bd=0, pady=3).pack(side="right", padx=(6, 0))

    root.bind("<Return>", ok)
    root.bind("<KP_Enter>", ok)
    root.bind("<Escape>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)

    refresh()
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()
    return state["result"]

# ── -set: save a preset into this script ─────────────────────────────────────

def _num(v):
    return int(v) if float(v).is_integer() else v


def format_entry(name, hsl):
    """One aligned INVUN_COLOURS line, matching the hand-written ones."""
    key = f'"{name}":'
    h, s, l = (_num(v) for v in hsl)
    return f"    {key.ljust(max(11, len(key) + 1))}({h}, {s}, {l}),"


def do_set(spec, table):
    value, sep, name = spec.rpartition(":")
    if not sep or not value.strip() or not name.strip():
        err(f"-set needs h,s,l:name - e.g. -set 210,85,-10:blood (got '{spec}').")
    hsl = parse_hsl(value, "-set value")
    if hsl is None:
        err(f"-set value '{value}' is not h,s,l - e.g. 210,85,-10.")
    name = name.strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        err(f"-set name '{name}' must be letters, digits, _ or - only.")

    script = os.path.abspath(__file__)
    try:
        with open(script, "r", encoding="utf-8", newline="") as f:
            text = f.read()
    except OSError as e:
        err(f"Cannot read '{script}': {e}")

    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"^INVUN_COLOURS\s*=\s*\{\s*(#.*)?$", ln)), None)
    end = None
    if start is not None:
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^\}\s*(#.*)?$", lines[i])), None)
    if start is None or end is None:
        err("Could not find the INVUN_COLOURS = { ... } block in the script.\n"
            "       It must start with 'INVUN_COLOURS = {' and end with '}' on\n"
            "       their own lines.")

    key_re = re.compile(r'^\s*"([^"]+)"\s*:')
    found = None
    for i in range(start + 1, end):
        m = key_re.match(lines[i])
        if m and m.group(1).lower() == name:
            found = i
            break

    entry = format_entry(name, hsl)
    if found is not None:
        lines[found] = entry
    else:
        lines.insert(end, entry)
    new_text = nl.join(lines)

    try:
        compile(new_text, script, "exec")
    except SyntaxError as e:
        err(f"Edit would break the script ({e}). Nothing was changed.")

    try:
        shutil.copy2(script, script + ".bak")
        with open(script, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
    except OSError as e:
        err(f"Cannot write '{script}': {e}")

    print(c(BOLD, "addInvun -set"))
    if found is not None:
        old = table.get(name)
        was = f" {c(DIM, f'(was {fmt_hsl(old)})')}" if old else ""
        print(f"  {c(GREEN, 'Updated')} : {name} = {fmt_hsl(hsl)}{was}")
    else:
        print(f"  {c(GREEN, 'Added')}   : {name} = {fmt_hsl(hsl)}")
    print(f"  {c(DIM, 'Backup  : ' + script + '.bak')}")
    sys.exit(0)

# ── WAD reading / writing ────────────────────────────────────────────────────

def read_wad(path):
    """Return (data, [(name, offset, size), ...]) for a WAD file."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        err(f"Cannot read '{path}': {e}")

    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        err(f"'{path}' is not a valid WAD file (bad header).")

    numlumps, diroffset = struct.unpack_from("<ii", data, 4)
    if numlumps < 0 or diroffset < 0 or diroffset + numlumps * 16 > len(data):
        err(f"'{path}' has a corrupt directory.")

    lumps = []
    for i in range(numlumps):
        entry = data[diroffset + i * 16 : diroffset + i * 16 + 16]
        offset, size = struct.unpack_from("<ii", entry, 0)
        name = entry[8:16].split(b"\0")[0].decode("ascii", "replace").upper()
        if offset < 0 or size < 0 or offset + size > len(data):
            err(f"'{path}': lump '{name}' points outside the file.")
        lumps.append((name, offset, size))
    return data, lumps


def last_lump(data, lumps, name):
    """Bytes of the LAST lump with this name (the one the engine uses), or None."""
    found = None
    for lname, offset, size in lumps:
        if lname == name:
            found = data[offset : offset + size]
    return found


def write_pwad(path, lump_list):
    """Write a PWAD containing the given [(name, bytes), ...] lumps."""
    body = bytearray()
    directory = bytearray()
    pos = 12
    for name, payload in lump_list:
        body += payload
        directory += struct.pack("<ii", pos, len(payload))
        directory += name.encode("ascii")[:8].ljust(8, b"\0")
        pos += len(payload)
    header = b"PWAD" + struct.pack("<ii", len(lump_list), 12 + len(body))
    try:
        with open(path, "wb") as f:
            f.write(header + body + directory)
    except OSError as e:
        err(f"Cannot write '{path}': {e}")

# ── WAD selection ────────────────────────────────────────────────────────────

def find_wads():
    """Sorted *.wad files in the current folder, minus generated output WADs."""
    suffix = f"{OUTPUT_SUFFIX.lower()}.wad"
    names = []
    try:
        with os.scandir(".") as it:
            for entry in it:
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                low = entry.name.lower()
                if low.endswith(".wad") and not low.endswith(suffix):
                    names.append(entry.name)
    except OSError:
        pass
    names.sort(key=str.lower)
    return names


def pick_wad():
    wads = find_wads()
    if not wads:
        err("No .wad files in this folder. Give one on the command line.")
    if len(wads) == 1:
        return wads[0]
    if not sys.stdin.isatty():
        err(f"{len(wads)} WADs in this folder and no terminal to ask with - "
            f"name one on the command line:\n       " + "\n       ".join(wads))

    print(c(BOLD, f"\n{len(wads)} WADs found in this folder:\n"))
    width = len(str(len(wads)))
    for i, name in enumerate(wads, 1):
        print(f"  {c(GREEN, str(i).rjust(width))}  {name}")
    prompt = f"\nSelect WAD {c(DIM, f'[1-{len(wads)}, q=quit]')}: "
    while True:
        try:
            reply = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if reply in ("q", "quit", ""):
            sys.exit(0)
        if reply.isdigit() and 1 <= int(reply) <= len(wads):
            print()
            return wads[int(reply) - 1]
        print(c(RED, "  Not a valid selection. Try again."))

# ── arguments ────────────────────────────────────────────────────────────────

def parse_args(argv, table):
    """Return (wad, colour_name, custom_hsl, picker)."""
    if any(a.lower() in ("-h", "--help", "-help", "/?") for a in argv):
        show_help(table)
    if any(a.lower() in ("--list", "-list") for a in argv):
        show_list(table)
    if any(a.lower() in ("-set", "--set") for a in argv):
        if len(argv) != 2 or argv[0].lower() not in ("-set", "--set"):
            err("-set is used on its own: addIn -set h,s,l:name")
        do_set(argv[1], table)

    wad = colour = custom = None
    picker = False
    for a in argv:
        al = a.lower()
        if al in ("--picker", "-picker"):
            picker = True
            continue
        if a.startswith("-"):
            err(f"Unknown option '{a}'. Use -h for help.")
        hsl = parse_hsl(a)
        if al in table or hsl is not None:
            if colour is not None or custom is not None:
                err(f"Two colours given - pick one.")
            if al in table:
                colour = al
            else:
                custom = hsl
        elif al.endswith(".wad") or os.path.isfile(a):
            if wad is not None:
                err(f"Two WADs given ('{wad}' and '{a}') - one at a time.")
            wad = a
        else:
            err(f"'{a}' is not a known colour, an h,s,l value or an existing file.\n"
                f"       Colours: {', '.join(table)}")
    if colour is None and custom is None:
        colour = INVUN_DEFAULT.lower()
    return wad, colour, custom, picker

# ── main ─────────────────────────────────────────────────────────────────────

def main(argv):
    table = load_colour_table()
    wad_path, colour, custom, picker = parse_args(argv, table)
    if wad_path is None:
        wad_path = pick_wad()
    if not os.path.isfile(wad_path):
        err(f"WAD '{wad_path}' does not exist.")

    data, lumps = read_wad(wad_path)
    d2_pal = doom2_palette()

    # base colormap: the WAD's own, else embedded doom2
    cmap = last_lump(data, lumps, "COLORMAP")
    if cmap is None:
        cmap = doom2_colormap()
        cmap_src = c(YELLOW, "embedded doom2") + c(DIM, " (WAD has no COLORMAP)")
    elif len(cmap) != COLORMAP_SIZE:
        err(f"COLORMAP in '{wad_path}' is {len(cmap)} bytes - expected "
            f"{COLORMAP_SIZE} (34 x 256). Not a standard colormap.")
    else:
        cmap_src = "WAD"

    # palette: the WAD's first PLAYPAL palette, else embedded doom2
    playpal = last_lump(data, lumps, "PLAYPAL")
    if playpal is None:
        pal = d2_pal
        pal_src = c(YELLOW, "embedded doom2") + c(DIM, " (WAD has no PLAYPAL)")
    elif len(playpal) < PAL_SIZE:
        warn(f"PLAYPAL in '{wad_path}' is only {len(playpal)} bytes - using doom2's.")
        pal = d2_pal
        pal_src = c(YELLOW, "embedded doom2") + c(DIM, " (WAD PLAYPAL too short)")
    else:
        pal = parse_palette(playpal[:PAL_SIZE])
        pal_src = "WAD" + (c(DIM, " (same as doom2)") if pal == d2_pal else "")

    # base row: embedded doom2 row, unless the palette is not doom2's
    if pal == d2_pal:
        base_row = DOOM2_INVUN_BASE
        base_src = "embedded doom2"
    else:
        wr, wg, wb = LUMA
        base_row = [max(0, min(255, round(wr * r + wg * g + wb * b)))
                    for r, g, b in pal]
        base_src = c(YELLOW, "built from WAD palette") + c(DIM, " (custom PLAYPAL)")

    if custom is not None:
        hsl, label = custom, "custom"
    else:
        hsl, label = table[colour], colour

    if picker:
        picked = run_picker(hsl, pal, label)
        if picked is None:
            print(c(YELLOW, "Picker cancelled - nothing written."))
            return
        hsl = tuple(float(v) for v in picked)
        label = f"picker {c(DIM, f'(started from {label})')}"

    hue, sat, light = hsl
    row = build_invun_row(base_row, pal, hue, sat, light)
    patched = cmap[:INVUN_OFFSET] + row + cmap[INVUN_OFFSET + ROW_SIZE:]

    stem = os.path.splitext(os.path.basename(wad_path))[0]
    out_path = os.path.join(os.path.dirname(os.path.abspath(wad_path)),
                            f"{stem}{OUTPUT_SUFFIX}.wad")
    write_pwad(out_path, [("COLORMAP", patched)])

    print(c(BOLD, "addInvun"))
    print(f"  WAD         : {wad_path}")
    print(f"  Colour      : {c(GREEN, label)}")
    print(f"  Colour used : {c(BOLD, fmt_hsl(hsl))}")
    print(f"  Colormap    : {cmap_src}")
    print(f"  Palette     : {pal_src}")
    print(f"  Base row    : {base_src}")
    print(f"  {c(GREEN, 'Wrote')}       : {out_path}")

# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDED DOOM2 DATA - generated from doom2.wad, no need to edit
# ─────────────────────────────────────────────────────────────────────────────

# Row 32 of the doom2 COLORMAP as SLADE would display it, greyscaled and
# inverted: one 0-255 grey per palette index (0 = black, 255 = white).
DOOM2_INVUN_BASE = [
      0,  24,  16,  76, 255,  24,  16,  16,   0,  52,  36,  24,  16,  64,  56,  44,
    208, 200, 188, 180, 176, 164, 156, 148, 136, 128, 124, 116, 108, 104,  96,  88,
     84,  76,  72,  64,  64,  56,  52,  52,  44,  36,  32,  32,  32,  24,  24,  16,
    244, 236, 236, 228, 220, 216, 208, 208, 200, 188, 184, 176, 168, 156, 148, 148,
    136, 128, 124, 124, 116, 108,  96,  96,  88,  76,  72,  64,  56,  52,  44,  36,
    244, 236, 228, 228, 216, 208, 208, 196, 188, 184, 176, 168, 164, 156, 148, 144,
    136, 128, 124, 116, 108, 104,  96,  88,  84,  72,  72,  64,  56,  52,  44,  36,
    200, 188, 176, 164, 148, 136, 124, 116, 104,  88,  76,  64,  52,  36,  24,  16,
    176, 168, 156, 148, 144, 136, 128, 124, 116, 104, 104,  96,  88,  84,  72,  72,
    136, 124, 116, 104,  88,  76,  64,  52, 124, 116, 104,  96,  84,  76,  64,  56,
    244, 208, 184, 156, 128, 104,  84,  56, 255, 236, 216, 188, 164, 144, 124,  96,
     76,  72,  64,  64,  64,  56,  52,  52,  44,  44,  36,  36,  32,  24,  24,  16,
    244, 216, 188, 164, 136, 108,  84,  64,  36,  32,  32,  24,  24,  16,  16,  16,
    255, 244, 228, 216, 200, 184, 168, 156, 144, 136, 128, 124, 116, 104,  96,  88,
    255, 255, 248, 244, 244, 236, 228, 228,  88,  76,  72,  64,  64,  52,  36,  32,
     16,  16,  16,   0,   0,   0,   0,   0, 180, 220, 184, 116,  88,  72,  52, 128,
]

# First palette of the doom2 PLAYPAL (768 bytes, base64)
DOOM2_PLAYPAL_B64 = (
    "AAAAHxcLFw8HS0tL////GxsbExMTCwsLBwcHLzcfIysPFx8HDxcATzsrRzMjPysb/7e396ur86Oj"
    "65eX54+P34eH23t703Nzy2trx2Njv1tbu1dXs09Pr0dHpz8/ozs7mzMzly8vjysriyMjgx8ffxsb"
    "dxcXcxMTaw8PZwsLXwcHWwcHUwcHTwAARwAAQwAA/+vf/+PT/9vH/9O7/8+z/8en/7+b/7uT/7OD"
    "96t776Nz55tr35Nj14tbz4NTy39Pv3tLs3NHq29Do2s/m2M7j183h1czf1Mvd08ra0cnX0MjUz8f"
    "SzcbPy8XMysTKyMP7+/v5+fn39/f29vb09PTy8vLx8fHv7+/t7e3s7Ozq6urp6enn5+fl5eXk5OT"
    "i4uLg4ODf39/d3d3b29va2trY2NjW1tbV1dXT09PR0dHQ0NDOzs7Nzc3Ly8vJycnIyMjd/9vb+9n"
    "Z99fX89XW79PU69HS58/Q5M3P4MvN3MrL2MjJ1MbH0MXFzMPEyMLCxcHv6ePt5+Hr5d/p493n4dv"
    "m39rk3tji3Nbg2tXe2NPd19Lb1dDZ1M/X0s3V0MzUz8vn4Njj3dTg2tLd18/Z1MzW0crTzsjQzMb"
    "e39jb3NXZ2tPW2NHU1c7R08zP0crNz8n//9z69tX17tDw5svr3sfm1sTh0MHcysA/////9vb/7u7"
    "/5ub/3t7/19f/z8//x8f/wAA7wAA4wAA1wAAywAAvwAAswAApwAAmwAAiwAAfwAAcwAAZwAAWwAA"
    "TwAAQwAA5+f/x8f/q6v/j4//c3P/U1P/Nzf/Gxv/AAD/AADjAADLAACzAACbAACDAABrAABT////"
    "/+vb/9e7/8eb/7N7/6Nb/487/38b83MX628P32cP118Ly1cHw08At0cAr0MA///////X//+z//+P"
    "//9r//9H//8j//8Apz8AnzcAky8AhyMATzsnQy8bNyMTLxsLAABTAABHAAA7AAAvAAAjAAAXAAAL"
    "AAAA/59D/+dL/3v//wD/zwDPnwCbbwBrp2tr"
)

# The full doom2 COLORMAP (8704 bytes, base64)
DOOM2_COLORMAP_B64 = (
    "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4"
    "OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3Bx"
    "cnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanBKmq"
    "q6ytrq+wsbKztLW2t7i5uru8vS0vwMHCw8TFxsfIycrLzM3OzwTR0tPU1dbX2Nna29zd3t8E4eLj"
    "5OXm5+jp6uvs7e7vz/Hy8/T19gD4+fr7/P3+/wABAgMEBQYHCAkKCwwNDg8REhMUFRUXGBgZGxsc"
    "HR8fISEiIyQlJicoKSsrLC0uLzEyMzQ1Njc3OTo7PD0+P0BAQkNDREVHR0hJSktMTU5PUVJTVFVW"
    "V1hZWltcXV5fX2FhYmRkZWdnA2lqa2xtbm9wcXJzdHV2d3h5ent8fX5/gYKDhIWGhoiIioqLjI2P"
    "DZCRkpOUlZaXmJmam5ydnp+goaKjpKWmpwSpEKusra6vsLKztLS1tre4ubq7vL0tL8DBwsPExcbH"
    "yMnKy8zNzs8EMTQ2OdXW19na29vc3d/oBOHi4+Tl5ufo6err7O3u78/x8vP09fYA+Pn6+/z9/v8A"
    "AQJpUAUGBwgJCgsM7A4PERITFRUWFxgZGhscHR4fICEiIyQlJicoKSorLCwuLy8xMjM1NTY3OTk6"
    "Ozw9PkBAQUJDREVGR0hJSktMl01OT1JTVFVWV1dZWltcXF1fX2BhYmNkZWZnaANqamxsbW5vcXJz"
    "dHV2d3h5eXp7fH1+f4GCg4SFhoeIiYqLjI2Ojw2GkoqLjZUOTZmam5ucnZ+f5KGio6SlpqdQMhEU"
    "rK2ur7Gys7S1tre4ubq7vLwtLi9SwcLDxMXGx8nKy8vMzc7PUDI0NzrV1tja2tvc3d7f6FAx4uPk"
    "+ebn6erq6w4P7u/P8fLz9PX2ANah+vv8/f7/AAECalEFBgcICQoLDA4P7hITFBUWFxgZGhscHB0e"
    "ICAiIiMkJiYnKCkqLCwsLi8vUzM0NRESOTk6Ozw9Pj9AQUJDREVFRkhISUpLTJdOT09TVFVWV1hZ"
    "WltcXF1eX2BhYmJkZWVmaGhpamtsbW1vb3Fyc3R1dnd4eXp7fHx9fn+Cg4SFhoeIiYmLi4yNjg0N"
    "h5KTjJXsDk2ZmpucnZ6fCaGio6SkpaanUVQSFBatrq+ys7S1tra3uLm6u7y9LS4vU8LDw8TFxsfJ"
    "ysvMzc3O8VFUNTk7PNbZ2tvc3N7f6OlRMjTjoaHm5+nq66cOD+7v8fLy8/T19gDWofr7/P3+/wAB"
    "AmpSBQYHCAkKCwwOD+4TFBUVFxcYGRscHB0eHyAhIiMkJSYmKCgqKywsLi4vL1RVERESExM6Ozw9"
    "Pj9AQUFCRERFRkdISUlKS0xNTk9PVFVWV1hZWltcXF1eX2BgYmJjZGVmZ2gDaWtrbG1ubwVyc3R1"
    "dXZ3eHl6e3x8fX5/g4OEhoeHiImKi4yNjY8NDYeSk5SV7A5NmZubnJ2enwmhoqOkpaanp1JVEhUX"
    "Ga6vsrO0tba3uLm5uru8vS0uL1TCw8TExcbHycrLzM3Oz/FSVBE5Oz0/2tvb3N3e3+jpUlTToaGh"
    "5ufq6uunDg9P7/Hy8/P09fYAPqL6/P39/ogAAgJqUwUGBwgJCgsMDg/uExUVFxcYGRobHB0eHyAh"
    "IiIkJCYmJygpKyssLC4vLy9WVleAgIAUOzw9PT5AQUJCQ0RFRkZISElKS5aXTU5PAVVWV1hZWltc"
    "XV1eX2BhYWJjZGVmZmcDA2pra21tbm8FcnN0dXZ3eHh5ent8fX5+f4OEhYaHiImKi4yMjY6PDQ6I"
    "iouUlZaXD5qbnJydnp8JoaKjpKWmp6dTVhMVGBqus7O0tba3t7i5uru8vL0tLy9VWMPExcXGycnK"
    "y8zNzs/xU1aAgDw+P9rb3Nze3+jp6lNV06GhoqLn6uunpw7uT+/x8vP09PX2AD+i+vz9/v6IAAIC"
    "a1QGBgcICgsLDA4P7oAVFhcY//8bHBweHh8gIiIkJCUmJygoKSssLC4vLy8vV1eAgICAgTw8PT5A"
    "QUFCQ0RFRkZHSElJSktMl01OTwFXV1hZWltcXF1eX19gYWJjZGRlZmdoA2lqa2xtbW5vBXN0dXV2"
    "d3h5enp7fH1+f3+EhYaHiIiJiouMjY6ODQ4OkpOMjY+W7U6am5ydnp8JCaGio6SlpqenVFeAFhkb"
    "HbS0tba2t7i5ubq7vL0tLi8vV1nDxMXGxsrKy8zMzc7P8VRXgIA9P0Db3Nze3ujo6epUVoChoqKi"
    "5+rrp6ft7u8B8fLz9PX19gA/ovr8/f7+iQACAmtWBgYHCAoLDAwPD+6Bghf/////HBwdHh8gISIi"
    "JCQmJigoKSssLC4uLy8vL1hZgICAgYGCPT5AQEFCQ0RERUZHSElJSkpLTE1NTk8BV1laWltcXF1e"
    "X2BgYWJiY2VlZmdnA2lqa2xsbW1uBQVzdHV2d3d4eXp6e3x9fn9/hYaHiIiJiouMjY2Ojw0ODomL"
    "jI3sDg9Om5ucnZ6fCQmio6Okpaanp1ZZgBcZHB60tLW2t7i4ubq6u7y9LS4vL1haXMTFxsbKysvM"
    "zc3Oz/FWWICBPT+k3Nzd3t/o6erqVleAgKKioqPrp6enD+7vAfHy8/T19fYAQKIV/P3+/okAAgJs"
    "VwYHCAgKCwwMD+5PgYKD/////xwdHh8fICIiJCQlJicoKCssLCwuLy8vLy9ZgICAgYGCgj5AQEFC"
    "Q0RERUZHSEhJSkpLTJdNTk9PAVlaW1tcXV1eX2BhYWJjY2RlZWZnaANqamtsbW1ubwUFdHV1dnd4"
    "eXl6e3x8fX5/f4aGh4iJiouMjI2Ojw0ODg+Ki42V7A4PTpucnJ2enwkJoqOkRaWmpyxXgIEYGh0f"
    "tbW2t7e4ubm6u7y9vS0vLy9ZW13ExcbKysrLzM3Ozs/yV1mAgj5ApNzd3t/o6erq61dYgICioqOj"
    "p6enKQ/u7wHy8vP09fX2AEGjFfz9/v6KAAICbFgGBwgICgsMDA/uT4KD/////xwcRR9GRyIiJCQl"
    "JiYoKCksLCwsLy8vLy8vWoCBgYKCg4NAQEFCQ0RERUZHR0hJSUpKS0ztTU5PTwFaW1xcXV5eX2Bg"
    "YWJjY2RlZmZnaANpamprbG1ubm8FBXR1dnd3eHl6ent8fH1+f3+Gh4iJioqLjI2Ojo8NDg4PioyN"
    "jpaXD06bnJ2enwkJCaKjpEVIpqcsWICC/xsdH7a2t7e4ubm6u7u8vS0uLy8vWlxeYMXGy8vLzMzN"
    "zs/P8liAgYNAQaTcpd/o6Kbq6qdYgICBoqOjo6enpykPT+8B8vPz9PX19gCko138/f7+iwACB2xZ"
    "BgcICAoLDAwP7k+D//////8cRUZGR0ciIiQkJiYnKCgrLCwsLi8vLy8vL1uBgoKDg4SQkEFCQ0RE"
    "RUZGR0hJSUpKS0xMTU7uTwEBW1xdXV5fX2BhYWJiY2RlZWZnaAMDamprbG1tbm5vBQV1dnZ3eHl5"
    "ent7fH19fn9/h4iJiYqLjIyNjo4NDQ4PD4uMjY8Ol05PnJ2dnp8JCW+jo6RFSKenLFlcg/8cHSC2"
    "tre4uLm6uru8vb0tLi8vL1tdX2FjxsvLy8zNzc7P8fJZXIKDQUJDpaXopqam6qenWYCBgqOjo6On"
    "p6cqTk8BAfLz8/T19vYApKP//f3+/osAAgdtWwYHCAgKC38MTk9P//////+IiUZGR0hISUkkJiYm"
    "KCgsLCwsLC8vLy8vLy9cgoKDg4SQkEFCQ0RFRUZGR0hJSUlKS5ZM7U1O7k8BAVxdXl5fYGBhYmJj"
    "Y2RlZWZnZ2gDaWpra2xtbW5vBQUFdXZ3eHh5enp7e3x9fX5/B4iIiYqLjIyNjo+PDQ4ODw+MjY4N"
    "Dg9OT5ydnZ6fCQlvo5FFR0mnpyxbXYT/HB4ht7e4uLm5uru7vL0tLS8vLy9cXmBiZMvLy8vMzc7O"
    "z/HyW1yDkEFDpaWl6Kampqenp1uBgoOjo6Okp6enK05PAQHy8/T09fb2AEOj//39/v6MAAIHbVwG"
    "BwgIBQsMCE5PT////4iIiYpGR0dJSUlJJiYmKCgrLCwsLC8vLy8vLy8vXoODhISFkIaRQ0RFRUZH"
    "R0hJSUlKS5ZMTO0PTk9PAQFdXl9fYGFhYmNjZGRlZmZnaGgDaWpra2xtbW5ubwUFBnZ3d3h5eXp6"
    "e3x8fX5+fwiJiYqLjIyNjo6PDQ4ODw9OjI2P7JcPTk+cnZ6fCQkKCpCRRUhJS0wsXF6F/x0fIbi4"
    "uLm5uru7vLy9LS4vLy8vXV9hY2XMzMzMzc3Ozs/x81xehJBDRKWlpqampqanp6dcgoOQo6OkpKen"
    "KyxOTwEC8/P09PX29gBEpP/9/v5tjAACB21dBgcICAULDAjuTwH/h4iIiYqLi4tISUlJSiYmKCgo"
    "LCwsLC8vLy8vLy8vAl+EhIWFhoeRkURFRUZHR0hISUlKSpZMTO0P7k5PAQEBX19gYGFiYmNjZGVl"
    "ZmZnZ2gDaWpqa2xsbW5ub28FBQZ2d3h4eXp6e3t8fH1+fn8IiYqLjIyNjY6PDQ0ODg9OTo2ODQ4P"
    "Tk9PnZ6enwkJCgqRkUVISkxN711fhYgeICK4uLm5urq7vLy9LS0vLy8vAl9gYmRlzMzMzM3Nzs/P"
    "8vNdX4WGQ0Slpaampqanp6enXV6EkJGkpKSnpyssT08BAvPz9PX19vYARaT//f7+bY0AAghuXgYH"
    "CAh+C38IT08Bh4iIiYqKi4tJSUlJSuwODu0oLCwsLCwvLy8vLy8vAgJghYWGhoeHiJJFRUZHSEhJ"
    "SUpKSktMTO3tD+5PTwEBAmBgYWFiY2NkZGVlZmZnZ2gDaWpra2xsbW1ubm8FBQYGd3h4eXl6e3t8"
    "fH19fn9/CIqLjIyNjo6PDQ0ODg8PTu6Njw0OD05PT52en58JbgoFkZJHSEpMTe9eYIeIHyEjJbm5"
    "urq7vLy9vS0uLy8vLwJgYmNlZszMzMzNzs7P8fLzXmCGh5JFRqampqanp6enp15fkJGRpKSkpyss"
    "LE8BAQLz9PT19fb2AEak//3+/m6OAAcIbl8HBwgIC39/CE9PAYiIiYqLi4yNjUmPjw3sDg4PDyws"
    "LCwvLy8vLy8vLwICYWKGh4eIiJKSk5NHSEhJSUpKSkuWTO3tD+7uT08BAQJhYWJiY2RkZWVlZmZn"
    "aGgDaWpqa2tsbW1ubm8FBQUGBnh4eXl6ent7fHx9fX5/fwiLjIyNjo6PDQ0ODg8PTk5Pjg0Olw9O"
    "TwGen58JCW8KBZGTSElLTO7vX2KIiUYiIyW5urq7vLy9vS0uLy8vLy8CYWJkZWfNzc3Nzc7Oz/Hy"
    "819hh4hFRkempqanp6enp6dfYZiRkaSkpSssLCxPAQEC8/T09fX29gBHRWP9/v5ujgAHCG5hBwcI"
    "CAt/fwhPAQGJiYqLi4yNjY6Ojw3sDg7tDw/uLCwvLy8vLy8vAgICAmKYiIiIiYmJk5NHSEhJSUlK"
    "S5aWTO3tDw/uT09PAQECYmJjY2RlZWVmZmdnaAMDaWpqa2xsbW1tbm9vBQUFBgZ4eXl6ent7fHx8"
    "fX5+f38IjIyNjo6PDQ0ODg4PD05PT48NDg9OT08Bnp+fCW5vCgWSk0hKS0zu72FiiIpHIiQmuru7"
    "vLy9vS0tLi8vLy8CAmJjZWZozc3Nzc7Oz8/x8vNhYoiJk0dIpqanp6enp6crYZiYkZJFpaUsLCwv"
    "TwEBAvP09PX19vYASEVk/v7+b48ABwhvYgcHCAAGfwcITwEBiouLjIyNjY6PDQ0NDg4PDw/u7u7v"
    "7+8vLy8vAgICAgJjZIiJiYqKiouLlElJSUpKS5ZMTO3tDw/u7k9PAQECAmNkZGRlZWZmZ2doaANp"
    "aWpra2xsbW1tbm5vBQUFBgYGeXl6enp7e3x8fX1+fn9/CI2Njo6PDQ0ODg8PD05PT08NDg4PTk8B"
    "AZ+fCQlvCgUFk5RJSkxN7u9iZImLSCQlJ7u7vLy9vS0tLi8vLy8vAgJjZWZnA83Nzc3Ozs/x8vP0"
    "YmOJipNISaanp6enp6csLGKYmZKTk6WlLCwsL08BAgL09PX19vYAAEhHZf7+/m8NAAcIb2MHCAgA"
    "Bn8HCAEBAYuLjI2Njo6PDQ0ODg4PDw/u7u7v7+/v7+/vAgICAgICZGWJioqLi4uMlElJSkpKS5ZM"
    "TO3tD+7u7k9PAQEBAgJkZWVlZmZnZ2hoAwNpampra2xsbW1tbm5vBQUFBQYGBnl5enp7e3x8fX19"
    "fn9/BwiNjo6PDQ0ODg8PD05vT08FDQ4PTk9PAQGfCQlubwUFAZOUSktMTe/vY2WLjEkkJii7vLy9"
    "vS0tLi8vLy8vAgICZGVnaGnOzs7Ozs/P8fLz9GNkiouUSUmnp6enp6csLCxjmZmTk0hIpiws7y8B"
    "AQIC9PT19fb2AABJSGb+/m1vDgAICAVkBwgIAAZ/CAgBAQKMjI2Ojo6PDQ4ODg4PD+7u7u7v7+/v"
    "7+8BAgICAgICAmVmi4uLjIyMjY2VlUqWlpZM7e0PD+7u7k9P7wEBAgICZWZmZmdoaGgDA2lqamtr"
    "bGxsbW1tbm5vbwUFBQYGBgd6enp7e3x8fH19fn5/fwgIjo8NDQ4ODg8Pbk5PT08FAQ4PD05PTwEB"
    "bQlubwUFAQaUlEtMTe7v72RmjI1JJicpvLy9vS0tLi8vLy8vLwICAmVnaANqzs7Ozs/P8fLy8/Rk"
    "ZYuMlElKp6enp6csLCwsZJqak5SUSKbv7+8vAQECAvT09fX29gAASpRn/v5uBQ4ACAgFZQcICAAG"
    "BwgIAQECjY2Ojo8NDQ4ODg8PD+7u7u/v7+/v7+8BAgICAgICAgJmZ4yMjI2NjZWVj+yWlkwO7Q8P"
    "D+7u7k9P7wEBAQICAmZnZ2hoAwNpaWpqamtrbGxtbW1ubm5vbwUFBQYGBgYHenp7e3x8fH19fX5+"
    "f38ICI8Na2wObW0Pbm5vT08FAQEOD05PTwEBAglub28FBQEGlJVLTE3u7+9lZ42Oj5YoKb29LS0t"
    "Li8vLy8vLwICAgJmaANqa87Ozs7P8fHy8/T0ZWeMjZVKS6enp0xN7izv72Wbm5SUlEpK7+/v7wEC"
    "AgL09fX19vYAAEpKaP7+bgUPAAgIBWcHCAgAfwcICAECAo6Ojw0NDQ4ODw8PD+7u7u/v7+/v7+8B"
    "AQICAgICAgICaGgDjY2Ojo6PDeyWDg7t7Q8P7u7u7k9P7wEBAQICAgdoaAMDA2lqampra2tsbGxt"
    "bW1ubm5vBQUFBQUGBgYHB3t7e3x8fH19fX5+f39/CAhrbGxtbW1ubm5vb08FAQEBD05OTwEBAQJu"
    "b28FBQUGBpVLTE3u7+8BZ2iOjw0OKCu9LS0uLi8vLy8vLwICAgICaANqa2zPz8/Pz/Hy8vP09Gdo"
    "jY6PS0xMTE1N7u7v7+9nm5yclUpLS+/v7+8BAgIH9PX19vb2AABLSmn+/m8FDwAICAVoCAgAAAcH"
    "CAgCAgKPDQ0ODg4PDw8P7u7u7u/v7+/v7wEBAgICAgICAgICAgNpaY6Oj48NDewODu0PDw8P7u7u"
    "T0/v7wEBAQECAgIHA2lpampqa2trbGxsbW1tbW5ubm9vBQUFBQYGBgYGBwd7e3x8fH19fX5+fn9/"
    "fwgIbG1tbW5ubm9vbwUFBQEBAU5OT08BAQICb28FBQUGBgaVS5dN7u/vAmhpjw0ODywsLS0uLy8v"
    "Ly8vLwICAgICAgNqa2xtz8/Pz/Hy8vPz9PVoA46P7ExMTU3u7u7v7+/vaAOcnUtLS0vv7+8BAgIC"
    "CPX19fb29gAATEtq/m1vBu4ACAgGaQgIAAAHCAgAAgICDQ4ODg4PDw/u7u7u7+/v7+8BAQEBAgIC"
    "AgICAgICCAhqamoNDQ0NDg4O7Q8PD+7u7u5PT+/vAQEBAQECAgIHCGpqamtra2xsbG1tbW1ubm5u"
    "b28FBQUFBQYGBgYGBwcHfHx8fH19fX5+fn9/fwgICG1tbm5ub29vBQUFAQEBBgJOT08BAQECAm8F"
    "BQUGBgZ/S5dNTk/vAQJpag0ODw8sLC4vLy8vLy8vLwICAgICAghqa2xtbfHx8fHy8vPz9PT1aWoN"
    "DQ7tTe7u7u/v7+/v72lqnZ5LS0xM7+8BAgICBwj19fX29vYAAO1Ma/5uBQZvAAgIBmoICAAABwgI"
    "AAICBw4ODw8PD+7u7u7v7+/v7wEBAQECAgICAgICAgICCAgIa2tsbA4ODg4PDw8P7u7u7k9PT+8B"
    "AQEBAQICAgIHBwhra2xsbGxtbW1tbW5ubm5vb28FBQUFBQYGBgYGBwcHB3x8fX19fX5+fn5/f38I"
    "CAhubm5vb28FBQUFAQEBBgICT08BAQECAgIFBQUGBgZ/B5dNTk/vAQECamsODw/u7y8vLy8vLy8v"
    "LwICAgICAggIa2xtbW7y8vLy8vPz9PT19WprbA4PD+7u7+/v7+/v7+9qa56fl5dNTe8BAgICAgcI"
    "9fX29vb2AABNl2xubwUGbwAIAAZsCAgAAAcICAACBwdtD25u7u7u7+/v7+8BAQEBAQICAgICAgIC"
    "AgICCAgICGxtbW1tDw8PD+7u7u5PT+/vAQEBAQEBAQICAgIHBwgIbGxtbW1tbW5ubm5ub29vBQUF"
    "BQUFBgYGBgYGBwcHBwh9fX19fn5+fn9/f38HCAgAb29vbwUFBQUBAQEGBgICAgUBAQECAgIHBQYG"
    "BgYHBwcJTk5PAQECAmxtbQ/u7u8vLy8vLy8vAgICAgICAggICGxtbW5v8vLy8vPz9PT09fVsbG0P"
    "D+7u7+/v7+/v7wEBbGyfCU1NTk4BAgICAgcICPX29vb2AAAA7k5tbgUFBgUACAAHbQgIAAAICAgA"
    "BwcIbm9vb29P7+8BAQEBAQECAgICAgICAgICAggICAgICAhtbW5ubm7u7u5PT09P7wEBAQEBAQEC"
    "AgICAgIHBwgICG1tbm5ubm5vb29vBQUFBQUFBQYGBgYGBgYHBwcHBwgIfX1+fn5+fn9/f39/CAgI"
    "AG8FBQUFBQEBBgYGAgICBwcBAQECAgIHBwYGBgYHBwcHTk9PAQECAgJtbW7u7+/vLy8vLwICAgIC"
    "AgICAggICAhtbm5vBfPz8/Pz9PT09fX2bW1uTu5P7+/v7+8BAQECAm1tCQlOTk5OAgICAgcHCAj2"
    "9vb29gAAAO9Obm8FBgcBAAgAB24IAAAACAgAAAcICG8FBQUFAQEBAQEBAgICAgICAgICAgICCAgI"
    "CAgICAgAbm9vb29vT09PTwEBAQEBAQEBAgICAgICAgIHBwgICAhub29vb28FBQUFBQUFBQUGBgYG"
    "BgYGBwcHBwcHBwgICH5+fn5+f39/f38HCAgIAAAFBQUGBgYGBgYCAgIHBwcHBgYCAgcHCAgGBgYH"
    "BwcHCApPAQECAgICbm9vBQEBAQICAgICAgICAgICCAgICAgAbm9vBQX09PT09PT19fX19m5ub09P"
    "7+8BAQEBAgICAgJubm8KCgoKCgICAgIHCAgI9vb29gAAAADvT28FBgYHBgAAAAdvAAAAAAgIAAAI"
    "CAgFBQEBAQECAgICAgICAgICAgIHCAgICAgICAgICAAAAAUFBQUFBQEBAQEBAQECAgICAgICAgIC"
    "BwcHCAgICAgIBQUFBQUFBQUFBgYGBgYGBgYGBgcHBwcHBwcICAgICAh+fn9/f39/fwcICAgICAAA"
    "BgYGBgYGAgcHBwcHBwcICAICBwcHCAgIBwcHBwcICAgBAQECAgICCG8FBQEBAgICAgICAgICAgII"
    "CAgICAgAAAUFBQYG9PT09PX19fX29vZvBQUBAQEBAgICAgICAgICbwUFAQEBCwsCAgIICAgIAPb2"
    "9vYAAAAAAQEFBgYHBwIAAAAIBQAAAAAIAAAACAgIBgYGAgICAgICAgcHBwcHBwgICAgICAgICAgI"
    "CAAAAAAGBgYGBgYGBgICAgICAgICAgIHBwcHCAgICAgICAgIAAYGBgYGBgYGBgYGBgYHBwcHBwcH"
    "BwcHCAgICAgICAgAf39/f38HBwgICAgICAAAAAYGBwcHBwcHBwcHCAgICAgHBwcICAgICAcHBwgI"
    "CAgIAQICAgIICAgFBgYGAgICAgICAggICAgICAgICAAAAAAGBgYGBvX19fX19fX29vb2BQYGBgIC"
    "AgICAgICAgICCAUGBgEBCwsMCAgICAgIAAD29vYAAAAAAAICBgYHBwgHAAAACAYAAAAAAAAAAAgA"
    "AAcHBwcHBwcHBwgICAgICAgICAgICAgAAAAAAAAAAAAABgcHBwcHBwcHBwcHBwcICAgICAgICAgI"
    "CAgICAAAAAAGBwcHBwcHBwcHBwcHBwcHCAgICAgICAgICAgIAAAAAAcHCAgICAgICAgIAAAAAAAH"
    "BwcICAgICAgICAgICAgICAgICAgICAAICAgICAgIAAIHBwgICAgABgcHBwcHCAgICAgICAgIAAAA"
    "AAAAAAAABwcHBwf29vb29vb29vb2AAYGBwcHBwcICAgICAgICAgGBgcCAgIMDAgICAAIAAAAAAAA"
    "AAAAAAAHAgcHCAgICAAAAAAIAAAAAAAAAAAAAAAICAgICAgICAgICAgAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAgICAgICAgICAgICAgICAgICAAAAAAAAAAAAAAAAAAACAgICAgICAgICAgICAgICAgICAAA"
    "AAAAAAAAAAAAAAAICAgICAAAAAAAAAAAAAAACAgICAgICAgAAAAAAAAAAAgIAAAAAAAACAAAAAAA"
    "AAAICAgIAAAAAAgICAgICAgAAAAAAAAAAAAAAAAAAAAAAAgICAgI9vb29vb29gAAAAAICAgICAgI"
    "CAgAAAAAAAAACAgICAgICAgAAAAAAAAAAAAAAAAAAAAACAgICAgAAAgEUVBZAFFQUARVU1FQV1ZU"
    "bWxqA2hmZWRiYWBfXl1cW1pZWFdXVlVVVFNSUlJRUVAHBgYFb25tbWxqaWhnZWRkYmFgYF9eXFxb"
    "WVhXVlVUUwcGBQVubW1ramloZ2ZlZGNiYWBfXl1cW1pYWFdWVVRTbGpoZmRiYF9dW1lXVVNRUGhn"
    "ZWRjYmFgX11dXFtaWFhiYF9dW1lXVWBfXVxaWVdWB21pZWFdWlYABm5qZmNgXFlYV1dXVlVVVFRT"
    "U1JRUVAHbmpmYl5aV1NSUlFRUFBQAAcFbmxpZ2VjYmFgX11cWwAACAcHBgUFW1lYV1dVU1JQUFAE"
    "BAQEBANvaV9bWFVhAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
)


if __name__ == "__main__":
    main(sys.argv[1:])
