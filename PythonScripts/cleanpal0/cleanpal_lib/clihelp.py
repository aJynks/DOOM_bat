"""Command-line --help output (no third-party dependencies)."""

import os
import sys

from .constants import VERSION


# ============================================================ help (no deps)
def _ansi_ok():
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")  # enable VT processing on Win10+
    return True


def print_help():
    c = _ansi_ok()

    def k(code, s):
        return "\033[%sm%s\033[0m" % (code, s) if c else s

    def H(s):
        return k("1;33", s)

    def C(s):
        return k("36", s)

    def D(s):
        return k("90", s)

    out = [
        "",
        k("1;37", "cleanpal") + "  v%s   " % VERSION
        + D("Doom PLAYPAL / COLORMAP editor"),
        "",
        H("USAGE"),
        "  " + C("cleanpal") + " [input]",
        "",
        "  Opens the GUI. With an input file it loads straight into the",
        "  viewer, otherwise use the Open button.",
        "",
        H("INPUTS") + D("  (pal0 = the first 256 colours)"),
        "  " + C(".wad") + "   WAD containing a PLAYPAL lump",
        "  " + C(".cleanpal") + "  cleanpal project (history + settings)",
        "  " + C(".pal") + "   SLADE playpal.pal (N x 768 bytes) or pal0.pal (768 bytes)",
        "  " + C(".png") + "   SLADE pal0.png         16x16 grid (128x128 or scaled square)",
        "         DoomTools playpal.png  256x14, row 0",
        "         COLORMAP image         256x34, line 0",
        "",
        H("PLAYPAL TOOLS") + D("  (GUI windows, one at a time)"),
        "  " + C("Cull") + "      matching, Align, delete, Snapshot (culling only runs here)",
        "  " + C("Move") + "      drag colours to new slots          } need a clean",
        "  " + C("Reorder") + "   sort colours into ramps            } snapshot",
        "  " + C("Paint") + "     palette ramps and solid fills      }",
        "",
        H("MATCHING") + D("  (Cull tools, runs in order)"),
        "  " + C("1. Remove exact") + "     exact RGB copies removed, first occurrence kept",
        "  " + C("2. Remove similar") + "   works on what stage 1 left; transitive clusters,",
        "                      lowest index kept. CIEDE2000 (default 1.5),",
        "                      CIE Lab dE76 (2.0) or weighted RGB (1.1)",
        "  " + C("Align") + "              packs kept colours toward index 0",
        "",
        H("REORDER TOOLS") + D("  (GUI window)"),
        "  " + C("Curved ramps") + "     default - chains each colour to its nearest darker",
        "                   neighbour, allowing hue-shifted (bending) ramps",
        "  " + C("Line ramps") + "       repeatedly fits straight lines through RGB space",
        "  " + C("Shade families") + "   groups by R:G:B ratio (scaled toward black)",
        "  " + C("Hue bands") + "        greys, then hue groups by lightness",
        "  " + C("Stepped hue") + "      Zucconi hue x lightness buckets (smooth grid)",
        "  " + C("Gradient path") + "    one smooth nearest-colour chain",
        "  " + C("Single key") + "       plain sort by lightness, hue, R, G, B, ...",
        "  " + C("Reverse") + "          reverses the order",
        "  Whole palette, or Selected: the selection is sorted and gathered into",
        "  one block starting at the first selected slot.",
        "",
        H("PAINT TOOLS / PICKER / SCRATCH") + D("  (GUI windows)"),
        "  " + C("Paint ramp") + "       select cells (blank or filled), set start / end",
        "                   colours, add nodes, blend OKLab / RGB / OKLCH, ease",
        "                   in / out; one ramp step per selected cell",
        "  " + C("Paint fill") + "       one colour into every selected cell",
        "  " + C("Colour picker") + "    popup: RGB sliders, HSL sliders, HSL wheel; hex,",
        "                   screen eyedropper, recent colours; live editing",
        "  " + C("Scratch palette") + "  named sets of temporary swatches; drag onto the",
        "                   grid, ramp nodes or the picker; import / export .gpl",
        "",
        H("COLORMAP MODE") + D("  (Mode dropdown in the GUI)"),
        "  The 34 light tables generated live from the palette (Perceptual, or",
        "  Classic = Freedoom's generator), hand edits by painting cells, bulk",
        "  fade tools, diagnostics, " + C("Create fade colours") + " into empty slots,",
        "  .lmp / 256x34 .png import and export, and lit previews (sector light,",
        "  distance, corridor view) using vanilla's light-table maths.",
        "",
        H("PROJECTS"),
        "  " + C("Save project") + " writes a .cleanpal file: every snapshot, the",
        "  current entry, deleted marks, selection, all settings, ramp and scratch",
        "  sets. Open it like any palette:  " + C("cleanpal mywork.cleanpal"),
        "",
        H("RAMP TEST"),
        "  " + C("cleanpal --ramptest <palette> [folder]"),
        "  Shuffles the palette, runs every method, scores how many of the",
        "  palette's own ramps come back intact and writes a comparison PNG",
        "  (<name>_ramptest.png, current folder by default). No GUI.",
        "",
        H("EXPORTS"),
        "  " + C("DoomTools playpal.png") + "        256x14, Doom red / gold / green tints",
        "  " + C("DoomTools blank playpal.png") + "  256x14, pal0 in every row",
        "  " + C("SLADE pal0.png") + "               128x128 grid",
        "  " + C("SLADE pal0.pal") + "               768 bytes",
        "  " + C("SLADE playpal.pal") + "            14 x 768 bytes, tinted",
        "  " + C("Analysis PNGs") + "                -identical- / -similar- / -aligned- (+ split)",
        "  " + D("Removed / empty slots: transparent in PNGs, green (0,255,0) in .pal"),
        "",
        H("SETTINGS"),
        "  Saved on exit to %APPDATA%\\cleanpal\\cleanpal_settings.json.",
        "  Save / Load preset buttons store matching, sort + export setups as .json",
        "  (default folder %APPDATA%\\cleanpal\\presets).",
        "",
        H("EXAMPLES"),
        "  " + C("cleanpal") + "                       " + D("open empty, pick a file"),
        "  " + C("cleanpal PLAYPAL.png") + "           " + D("DoomTools playpal / SLADE pal0.png"),
        "  " + C("cleanpal doom2.wad") + "             " + D("pal0 from the PLAYPAL lump"),
        "  " + C("cleanpal --ramptest doom2.wad") + "  " + D("compare the sort methods"),
        "  " + C('cleanpal "D:\\Pal0\\playpal.pal"') + "  " + D("SLADE binary palette"),
        "",
    ]
    print("\n".join(out))
