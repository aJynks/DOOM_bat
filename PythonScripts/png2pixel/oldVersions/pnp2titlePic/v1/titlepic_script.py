#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
titlepic_script.py  -  crop + reduce any image into a 426x200 widescreen Doom
                       title screen, with a realtime preview.

The crop box is locked to 426:240 (true 16:9 once Doom stretches the 200 lines
by 1.2) and the output is always the 426x200 lump.

Pipeline
    source (any size)
      -> crop (426:240)
      -> high quality resize (Lanczos / area / majority etc, optionally in linear light)
           true-colour branch 426x240, paletted branch 426x200
      -> image tweaks (Tweak Image window: each tool is applied in turn)
      -> unsharp mask
      -> palette match (OKLab / CIELAB / redmean / RGB) + optional dither
      -> Export:  <n>-paletted.png        426x200 indexed
                  <n>-truecolour.png      426x240 RGB, before palette matching
                  <n>-truecolour-200.png  426x200 RGB, before palette matching
                  (a dialog with tick boxes picks which files are written)

Projects (.titlepic, JSON) store every setting, the applied tweaks and the
palette, so a look can be reused on new images or a whole folder.

Run with -h for the command line help.
"""
import json
import math
import os
import queue
import sys
import threading
import time
import traceback

PROJECT_EXT_HELP = ".titlepic"


# ==========================================================================
#  Help (house style)
# ==========================================================================
def _enable_ansi():
    if os.name == "nt":
        os.system("")


C_H = "\033[1;96m"
C_O = "\033[93m"
C_D = "\033[37m"
C_E = "\033[92m"
C_R = "\033[0m"
C_T = "\033[1;97m"


def print_help():
    _enable_ansi()
    print(f"""
{C_T}titlepic{C_R} {C_D}- crop and reduce an image to a 426x200 widescreen Doom title screen{C_R}

{C_H}USAGE{C_R}
  titlepic [image] [-project FILE] [-pal PALETTE] [-o OUTDIR]

{C_H}ARGUMENTS{C_R}
  {C_O}image{C_R}              Image to open on startup (any size, any format Pillow reads).

{C_H}OPTIONS{C_R}
  {C_O}-project{C_R}           Load a {PROJECT_EXT_HELP} project (all settings, tweaks and palette).
  {C_O}-pal, --palette{C_R}    Palette to match against. Default: Doom 2 PLAYPAL palette 0
                     (embedded). Accepts:
                       SLADE pal0.png / doomtools-playpal.png (16x16 swatch grid)
                       any indexed (P mode) image's palette
                       a WAD containing PLAYPAL (palette 0)
                       raw .pal / .lmp / PLAYPAL (first 768 bytes)
                       JASC-PAL text, GIMP .gpl
  {C_O}-o, --outdir{C_R}       Folder Export writes into. Default: next to the source image.
  {C_O}-h, --help{C_R}         Show this help.

{C_H}OUTPUT{C_R}
  The crop box is locked to 426:240, the true 16:9 shape once Doom stretches
  the 200 lines by 1.2. The lump is always 426x200.

{C_H}FILTERS{C_R}
  Lanczos / Box / Bicubic / Hamming / Bilinear / Nearest, plus
  Majority (pixel art)  each output pixel takes the most common source colour
                        in its footprint; keeps pixel art crisp
  Linear light          averages in linear light (gamma-correct)

{C_H}EXPORT{C_R}
  Export opens a dialog: folder, name, and a tick box per file:
    <name>-paletted.png        426x200  indexed PNG, uses the active palette
    <name>-truecolour.png      426x240  RGB, after tweaks + sharpen, before palette match
    <name>-truecolour-200.png  426x200  RGB, same but at lump size (squashed)

{C_H}PROCESS FOLDER{C_R}
  Runs the current settings over every image in a folder, writing the files
  ticked in Export.
    426x200  processed as-is
    426x240  squashed to 426x200 first (current filter / linear light)
    other    skipped and listed by name and size in the report
  Files already named *-paletted / *-truecolour / *-truecolour-200 are ignored.
  Tick boxes (default on): apply tweaks, apply sharpen.

{C_H}GUI{C_R}
  Preview     mouse wheel zooms (4 steps a notch, Shift+wheel 1 step), drag pans,
              double-click / Fit fits. Zoom and position are kept through
              adjustments; opening an image or Fit resets
  Compare     toolbar button, On / Off: the original crop (left) and the result
              (right) side by side, each pane zooms / pans / fits on its own
  Readout     image size in pixels and zoom, bottom-left of each view
  Divider     drag the bar between image and controls to resize the panel
  Crop        drag inside the box to move, an edge to move that side (the box
              grows centred to keep 426:240), a corner to resize, mouse wheel
              to scale, Enter = OK, Esc = cancel, Max = largest box
  Tweak       pick a tool and adjust; picking another tool carries the look forward.
              Reset tool = tool defaults, Reset = back to source, Undo = step back,
              Apply = accept + close (closing otherwise asks to discard)
  Sliders     double-click a slider's label to reset it
  Palette     click swatches to exclude/include indices

{C_H}EXAMPLES{C_R}
  {C_E}titlepic{C_R}
  {C_E}titlepic art\\title_source.jpg{C_R}
  {C_E}titlepic art\\title_source.jpg -project looks\\hellish.titlepic{C_R}
  {C_E}titlepic render.png -pal pal0.png -o graphics{C_R}
""")


# ==========================================================================
#  Dependency check
# ==========================================================================
def check_deps(need_tk=True):
    missing = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("pillow")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    if missing:
        _enable_ansi()
        print(f"\n{C_O}titlepic: missing dependencies:{C_R} {', '.join(missing)}")
        print(f"  install with:  {C_E}pip install {' '.join(missing)}{C_R}\n")
        sys.exit(1)
    if need_tk:
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print("\ntitlepic: tkinter is not available. Reinstall Python from python.org "
                  "with the 'tcl/tk and IDLE' option ticked.\n")
            sys.exit(1)


class _Args:
    image = None
    palette = None
    outdir = None
    project = None


def parse_args(argv):
    a = _Args()
    i = 0
    while i < len(argv):
        t = argv[i]
        if t in ("-h", "--help", "/?"):
            print_help()
            sys.exit(0)
        elif t in ("-pal", "--palette"):
            i += 1
            a.palette = argv[i] if i < len(argv) else None
        elif t in ("-o", "--outdir"):
            i += 1
            a.outdir = argv[i] if i < len(argv) else None
        elif t in ("-project", "--project"):
            i += 1
            a.project = argv[i] if i < len(argv) else None
        elif t.startswith("-"):
            _enable_ansi()
            print(f"{C_O}titlepic: unknown option {t}{C_R}  (titlepic -h for help)")
            sys.exit(2)
        else:
            a.image = t
        i += 1
    return a


# Help and the dependency check run before numpy / Pillow / tkinter are imported,
# so -h works and a missing package gets a one-line install command, not a traceback.
if __name__ == "__main__":
    if any(t in ("-h", "--help", "/?") for t in sys.argv[1:]):
        print_help()
        sys.exit(0)
    check_deps(need_tk=True)

import numpy as np                                                        # noqa: E402
import tkinter as tk                                                      # noqa: E402
from tkinter import colorchooser, filedialog, messagebox, ttk             # noqa: E402,F401
from PIL import Image, ImageDraw, ImageOps, ImageTk                        # noqa: E402

Image.MAX_IMAGE_PIXELS = None


# ==========================================================================
#  Constants and the embedded Doom 2 palette
# ==========================================================================
OUT_W = 426
OUT_H = 200          # lump height
DISP_H = 240         # display height (200 * 1.2)
CROP_RATIO = OUT_W / DISP_H
PROJECT_EXT = ".titlepic"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tga", ".tif", ".tiff", ".webp", ".pcx")

# --------------------------------------------------------------------------
#  Doom 2 PLAYPAL palette 0 (embedded so the default never needs a file)
# --------------------------------------------------------------------------
DOOM2_PAL0_HEX = (
    "0000001f170b170f074b4b4bffffff1b1b1b1313130b0b0b0707072f371f232b0f171f070f17004f3b2b4733233f2b1b"
    "ffb7b7f7ababf3a3a3eb9797e78f8fdf8787db7b7bd37373cb6b6bc76363bf5b5bbb5757b34f4faf4747a73f3fa33b3b"
    "9b3333972f2f8f2b2b8b2323831f1f7f1b1b7717177313136b0f0f670b0b5f07075b07075307074f0000470000430000"
    "ffebdfffe3d3ffdbc7ffd3bbffcfb3ffc7a7ffbf9bffbb93ffb383f7ab7befa373e79b6bdf9363d78b5bcf8353cb7f4f"
    "bf7b4bb37347ab6f43a36b3f9b633b8f5f378757337f532f774f2b6b47275f4323533f1f4b371b3f2f17332b132b230f"
    "efefefe7e7e7dfdfdfdbdbdbd3d3d3cbcbcbc7c7c7bfbfbfb7b7b7b3b3b3abababa7a7a79f9f9f9797979393938b8b8b"
    "8383837f7f7f7777776f6f6f6b6b6b6363635b5b5b5757574f4f4f4747474343433b3b3b3737372f2f2f272727232323"
    "77ff6f6fef6767df5f5fcf575bbf4f53af474b9f3f4393373f832f37732b2f632327531b1f431717330f13230b0b1707"
    "bfa78fb79f87af977fa78f779f876f9b7f6b937b638b735b836b577b634f775f4b6f574367533f5f4b37574333533f2f"
    "9f83638f7753836b4b775f3f6753335b472b4f3b2343331b7b7f636f7357676b4f5b634753573b474f333f472b373f27"
    "ffff73ebdb57d7bb43c39b2faf7b1f9b5b13874307732b00ffffffffdbdbffbbbbff9b9bff7b7bff5f5fff3f3fff1f1f"
    "ff0000ef0000e30000d70000cb0000bf0000b30000a700009b00008b00007f00007300006700005b00004f0000430000"
    "e7e7ffc7c7ffababff8f8fff7373ff5353ff3737ff1b1bff0000ff0000e30000cb0000b300009b00008300006b000053"
    "ffffffffebdbffd7bbffc79bffb37bffa35bff8f3bff7f1bf37317eb6f0fdf670fd75f0bcb5707c34f00b74700af4300"
    "ffffffffffd7ffffb3ffff8fffff6bffff47ffff23ffff00a73f009f3700932f008723004f3b27432f1b3723132f1b0b"
    "00005300004700003b00002f00002300001700000b000000ff9f43ffe74bff7bffff00ffcf00cf9f009b6f006ba76b6b"
)


# ==========================================================================
#  Colour math, palettes, palette matcher and dithering
# ==========================================================================
# --------------------------------------------------------------------------
#  Colour math
# --------------------------------------------------------------------------
def srgb_to_linear(x):
    x = np.asarray(x, dtype=np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x):
    x = np.clip(np.asarray(x, dtype=np.float32), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055).astype(np.float32)


def linear_to_oklab(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return np.stack([L, A, B], axis=-1).astype(np.float32)


def oklab_to_linear(lab):
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    l = L + 0.3963377774 * A + 0.2158037573 * B
    m = L - 0.1055613458 * A - 0.0638541728 * B
    s = L - 0.0894841775 * A - 1.2914855480 * B
    l, m, s = l ** 3, m ** 3, s ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def linear_to_cielab(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    X = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    Y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b)
    Z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)
    fx, fy, fz = f(X), f(Y), f(Z)
    return np.stack([116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)], axis=-1).astype(np.float32)


def features(rgb01, metric):
    """rgb01: (N,3) sRGB 0..1 -> (features (N,3), chroma (N,) or None)."""
    if metric in ("rgb", "redmean"):
        return (rgb01 * 255.0).astype(np.float32), None
    lin = srgb_to_linear(rgb01)
    if metric == "oklab":
        lab = linear_to_oklab(lin) * 100.0      # L 0..100, a/b roughly -40..40
    else:
        lab = linear_to_cielab(lin)
    chroma = np.hypot(lab[:, 1], lab[:, 2]).astype(np.float32)
    return lab.astype(np.float32), chroma


# --------------------------------------------------------------------------
#  Palette
# --------------------------------------------------------------------------
class Palette:
    _uid = 0

    def __init__(self, rgb, name):
        Palette._uid += 1
        self.uid = Palette._uid
        self.rgb = np.asarray(rgb, dtype=np.uint8).reshape(256, 3)
        self.name = name

    @classmethod
    def doom2(cls):
        data = bytes.fromhex("".join(DOOM2_PAL0_HEX))
        return cls(np.frombuffer(data, dtype=np.uint8), "Doom 2 (PLAYPAL 0)")

    def pil_palette(self):
        return self.rgb.reshape(-1).tolist()


def _pad768(data):
    data = list(data[:768])
    data += [0] * (768 - len(data))
    return data


def load_palette(path):
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        raw = fh.read()

    # WAD
    if raw[:4] in (b"IWAD", b"PWAD"):
        import struct
        numlumps, diroff = struct.unpack_from("<ii", raw, 4)
        found = None
        for i in range(numlumps):
            pos, size, lname = struct.unpack_from("<ii8s", raw, diroff + i * 16)
            if lname.rstrip(b"\0").upper() == b"PLAYPAL":
                found = (pos, size)          # last one wins, like the engine
        if not found:
            raise ValueError("no PLAYPAL lump in WAD")
        pos, size = found
        if size < 768:
            raise ValueError("PLAYPAL lump is too small")
        return Palette(np.frombuffer(raw[pos:pos + 768], dtype=np.uint8), f"{name} PLAYPAL")

    # Text palettes
    head = raw[:16]
    if head.startswith(b"JASC-PAL"):
        lines = raw.decode("ascii", "ignore").split()
        count = int(lines[2])
        vals = [int(v) for v in lines[3:3 + count * 3]]
        return Palette(_pad768(vals), name)
    if head.startswith(b"GIMP Palette"):
        vals = []
        for line in raw.decode("utf-8", "ignore").splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("#") or ":" in line.split()[0]:
                continue
            parts = line.split()
            try:
                vals += [int(parts[0]), int(parts[1]), int(parts[2])]
            except (ValueError, IndexError):
                continue
        return Palette(_pad768(vals), name)

    # Images
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        im = None
    if im is not None:
        w, h = im.size
        if w % 16 == 0 and h % 16 == 0:
            rgbim = im.convert("RGB")
            cw, ch = w // 16, h // 16
            vals = []
            for gy in range(16):
                for gx in range(16):
                    vals += list(rgbim.getpixel((gx * cw + cw // 2, gy * ch + ch // 2)))
            return Palette(vals, name)
        if im.mode == "P" and im.getpalette():
            return Palette(_pad768(im.getpalette()), name)
        raise ValueError("image is not a 16x16 swatch grid or an indexed image")

    # Raw
    if len(raw) >= 768:
        return Palette(np.frombuffer(raw[:768], dtype=np.uint8), name)
    raise ValueError("unrecognised palette format")


def parse_indices(text):
    out = set()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if a > b:
                a, b = b, a
            for i in range(a, b + 1):
                if 0 <= i <= 255:
                    out.add(i)
        else:
            i = int(part)
            if 0 <= i <= 255:
                out.add(i)
    return out


def format_indices(s):
    s = sorted(s)
    parts = []
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[j] + 1:
            j += 1
        parts.append(str(s[i]) if i == j else f"{s[i]}-{s[j]}")
        i = j + 1
    return ", ".join(parts)


# --------------------------------------------------------------------------
#  Palette matcher
# --------------------------------------------------------------------------
LUT_BITS = 6
LUT_N = 1 << LUT_BITS
LUT_SHIFT = 8 - LUT_BITS


class Matcher:
    CHUNK = 8192

    def __init__(self, pal, excluded, metric, kL, protect):
        active = np.array([i for i in range(256) if i not in excluded], dtype=np.int32)
        if active.size == 0:
            active = np.arange(256, dtype=np.int32)
        self.active = active
        self.metric = metric
        self.kL = float(kL)
        self.protect = float(protect)
        prgb = pal.rgb[active].astype(np.float32) / 255.0
        self.pfeat, self.pchroma = features(prgb, metric)
        self._lut = None

    def _dist(self, f, c):
        pf = self.pfeat
        if self.metric == "rgb":
            d = f[:, None, :] - pf[None, :, :]
            return np.einsum("npk,npk->np", d, d)
        if self.metric == "redmean":
            rm = (f[:, None, 0] + pf[None, :, 0]) * 0.5
            dr = f[:, None, 0] - pf[None, :, 0]
            dg = f[:, None, 1] - pf[None, :, 1]
            db = f[:, None, 2] - pf[None, :, 2]
            return (2.0 + rm / 256.0) * dr * dr + 4.0 * dg * dg + (2.0 + (255.0 - rm) / 256.0) * db * db
        dL = f[:, None, 0] - pf[None, :, 0]
        da = f[:, None, 1] - pf[None, :, 1]
        db = f[:, None, 2] - pf[None, :, 2]
        d = self.kL * dL * dL + da * da + db * db
        if self.protect > 0.0:
            loss = np.maximum(c[:, None] - self.pchroma[None, :], 0.0)
            d += self.protect * loss * loss
        return d

    def match(self, rgb01, cancel=None):
        """rgb01 (N,3) sRGB 0..1 -> palette indices (N,) int32, or None if cancelled."""
        f, c = features(rgb01.astype(np.float32), self.metric)
        n = f.shape[0]
        out = np.empty(n, dtype=np.int32)
        for s in range(0, n, self.CHUNK):
            if cancel and cancel():
                return None
            e = min(n, s + self.CHUNK)
            out[s:e] = np.argmin(self._dist(f[s:e], None if c is None else c[s:e]), axis=1)
        return self.active[out]

    def lut(self, cancel=None):
        if self._lut is None:
            v = ((np.arange(LUT_N, dtype=np.float32) * (1 << LUT_SHIFT)) + ((1 << LUT_SHIFT) - 1) / 2.0) / 255.0
            r, g, b = np.meshgrid(v, v, v, indexing="ij")
            grid = np.stack([r.ravel(), g.ravel(), b.ravel()], axis=1)
            res = self.match(grid, cancel)
            if res is None:
                return None
            self._lut = res.astype(np.int32)
        return self._lut


# --------------------------------------------------------------------------
#  Dithering
# --------------------------------------------------------------------------
ED_KERNELS = {
    "Floyd-Steinberg": ([(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)], 16),
    "Atkinson": ([(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)], 8),
    "Sierra Lite": ([(1, 0, 2), (-1, 1, 1), (0, 1, 1)], 4),
    "Sierra": ([(1, 0, 5), (2, 0, 3), (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2),
                (-1, 2, 2), (0, 2, 3), (1, 2, 2)], 32),
    "Jarvis-Judice-Ninke": ([(1, 0, 7), (2, 0, 5), (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
                             (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1)], 48),
    "Stucki": ([(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
                (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1)], 42),
    "Burkes": ([(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2)], 32),
}
ORDERED = ("Bayer 2x2", "Bayer 4x4", "Bayer 8x8", "Noise (IGN)")
DITHER_MODES = ["None"] + list(ED_KERNELS.keys()) + list(ORDERED)


def bayer(n):
    m = np.array([[0]], dtype=np.float32)
    while m.shape[0] < n:
        k = m.shape[0]
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (n * n) - 0.5


def ordered_offsets(mode, h, w):
    if mode == "Noise (IGN)":
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        t = np.mod(0.06711056 * x + 0.00583715 * y, 1.0)
        return (np.mod(52.9829189 * t, 1.0) - 0.5).astype(np.float32)
    n = {"Bayer 2x2": 2, "Bayer 4x4": 4, "Bayer 8x8": 8}[mode]
    m = bayer(n)
    return np.tile(m, (h // n + 1, w // n + 1))[:h, :w]


def error_diffuse(img255, lut, pal_rgb, mode, strength, clamp, serpentine, cancel):
    """Error diffusion in sRGB space, nearest lookups through the LUT."""
    taps, div = ED_KERNELS[mode]
    taps = [(dx, dy, wt / div) for dx, dy, wt in taps]
    maxdy = max(t[1] for t in taps)
    H, W, _ = img255.shape
    rows = img255.reshape(H, W * 3).tolist()
    pal = pal_rgb.astype(np.float64).tolist()
    lutl = lut.tolist()
    S = LUT_SHIFT
    B2 = LUT_BITS * 2
    B1 = LUT_BITS
    buf = [[0.0] * (W * 3) for _ in range(maxdy + 1)]
    out = np.empty((H, W), dtype=np.int32)
    for y in range(H):
        if cancel and (y & 7) == 0 and cancel():
            return None
        cur = buf[0]
        row = rows[y]
        orow = [0] * W
        rev = serpentine and (y & 1)
        xs = range(W - 1, -1, -1) if rev else range(W)
        for x in xs:
            i3 = x * 3
            r = row[i3] + cur[i3]
            g = row[i3 + 1] + cur[i3 + 1]
            b = row[i3 + 2] + cur[i3 + 2]
            r = 0.0 if r < 0.0 else (255.0 if r > 255.0 else r)
            g = 0.0 if g < 0.0 else (255.0 if g > 255.0 else g)
            b = 0.0 if b < 0.0 else (255.0 if b > 255.0 else b)
            idx = lutl[((int(r) >> S) << B2) | ((int(g) >> S) << B1) | (int(b) >> S)]
            orow[x] = idx
            p = pal[idx]
            er = (r - p[0]) * strength
            eg = (g - p[1]) * strength
            eb = (b - p[2]) * strength
            if er > clamp: er = clamp
            elif er < -clamp: er = -clamp
            if eg > clamp: eg = clamp
            elif eg < -clamp: eg = -clamp
            if eb > clamp: eb = clamp
            elif eb < -clamp: eb = -clamp
            for dx, dy, wt in taps:
                xx = x - dx if rev else x + dx
                if 0 <= xx < W:
                    tb = buf[dy]
                    j = xx * 3
                    tb[j] += er * wt
                    tb[j + 1] += eg * wt
                    tb[j + 2] += eb * wt
        out[y] = orow
        buf.pop(0)
        buf.append([0.0] * (W * 3))
    return out


# ==========================================================================
#  Image tweak tools (Tweak Image window) and sharpening
# ==========================================================================
# --------------------------------------------------------------------------
#  Image tweak tools
#  Every tool works on an (H,W,3) float32 sRGB image in 0..1 and returns one.
# --------------------------------------------------------------------------
RANGES = ["Reds", "Yellows", "Greens", "Cyans", "Blues", "Magentas"]
_HUE_CENTRES = None


def to_ok(x):
    return linear_to_oklab(srgb_to_linear(x))


def from_ok(lab):
    return linear_to_srgb(oklab_to_linear(lab))


def luma(x):
    return (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]).astype(np.float32)


def hue_centres():
    global _HUE_CENTRES
    if _HUE_CENTRES is None:
        prim = np.array([[1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 1, 1], [0, 0, 1], [1, 0, 1]], dtype=np.float32)
        lab = linear_to_oklab(prim)
        _HUE_CENTRES = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0
    return _HUE_CENTRES


def hue_weights(lab):
    """(6,H,W) weights per colour range (a partition of unity around the hue
    wheel), multiplied by a chroma ramp so greys are not affected."""
    c = hue_centres()
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
    ramp = np.clip(np.hypot(lab[..., 1], lab[..., 2]) / 0.05, 0.0, 1.0)
    out = []
    n = len(c)
    for i in range(n):
        ci, cp, cn = c[i], c[(i - 1) % n], c[(i + 1) % n]
        d = (h - ci + 180.0) % 360.0 - 180.0
        span_n = (cn - ci) % 360.0
        span_p = (ci - cp) % 360.0
        w = np.where(d >= 0, 1.0 - d / span_n, 1.0 + d / span_p)
        out.append(np.clip(w, 0.0, 1.0) * ramp)
    return np.stack(out).astype(np.float32)


def _range_weight(lab, name):
    if name == "Master":
        return np.ones(lab.shape[:2], dtype=np.float32)
    return hue_weights(lab)[RANGES.index(name)]


def monotone_lut(points, n=1024):
    pts = {}
    for px, py in points:
        pts[min(max(float(px), 0.0), 1.0)] = min(max(float(py), 0.0), 1.0)
    xs = np.array(sorted(pts), dtype=np.float64)
    ys = np.array([pts[k] for k in xs], dtype=np.float64)
    t = np.linspace(0.0, 1.0, n)
    if len(xs) < 2:
        return t.astype(np.float32)
    if len(xs) == 2:
        return np.clip(np.interp(t, xs, ys), 0, 1).astype(np.float32)
    d = np.diff(ys) / np.diff(xs)
    m = np.empty(len(xs))
    m[0], m[-1] = d[0], d[-1]
    m[1:-1] = (d[:-1] + d[1:]) / 2.0
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
    for k in range(len(d)):
        if d[k] == 0:
            m[k] = m[k + 1] = 0.0
        else:
            a, b = m[k] / d[k], m[k + 1] / d[k]
            s = a * a + b * b
            if s > 9.0:
                tau = 3.0 / math.sqrt(s)
                m[k], m[k + 1] = tau * a * d[k], tau * b * d[k]
    i = np.clip(np.searchsorted(xs, t, side="right") - 1, 0, len(xs) - 2)
    h = xs[i + 1] - xs[i]
    s = np.clip((t - xs[i]) / h, 0.0, 1.0)
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    y = h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]
    y = np.where(t < xs[0], ys[0], np.where(t > xs[-1], ys[-1], y))
    return np.clip(y, 0.0, 1.0).astype(np.float32)


def _channels(name):
    return {"RGB": [0, 1, 2], "Red": [0], "Green": [1], "Blue": [2]}[name]


def t_basic(x, p):
    bp = p["black"] / 255.0
    wp = max(p["white"] / 255.0, bp + 1.0 / 255.0)
    x = np.clip((x - bp) / (wp - bp), 0.0, 1.0)
    if p["gamma"] != 1.0:
        x = np.power(x, 1.0 / p["gamma"])
    if p["brightness"]:
        x = x + p["brightness"] / 200.0
    if p["contrast"]:
        x = (x - 0.5) * (2.0 ** (p["contrast"] / 50.0)) + 0.5
    x = np.clip(x, 0.0, 1.0).astype(np.float32)
    if p["saturation"] != 100 or p["hue"] != 0:
        lab = to_ok(x)
        s = p["saturation"] / 100.0
        ang = math.radians(p["hue"])
        ca, sa = math.cos(ang) * s, math.sin(ang) * s
        a, b = lab[..., 1].copy(), lab[..., 2].copy()
        lab[..., 1] = a * ca - b * sa
        lab[..., 2] = a * sa + b * ca
        x = from_ok(lab)
    return x


def t_levels(x, p):
    ib, iw = p["in_black"] / 255.0, max(p["in_white"], p["in_black"] + 1) / 255.0
    ob, ow = p["out_black"] / 255.0, p["out_white"] / 255.0
    y = x.copy()
    for c in _channels(p["channel"]):
        v = np.clip((x[..., c] - ib) / (iw - ib), 0.0, 1.0) ** (1.0 / p["gamma"])
        y[..., c] = ob + v * (ow - ob)
    return y


def t_curves(x, p):
    lut = monotone_lut(p["points"])
    y = x.copy()
    for c in _channels(p["channel"]):
        y[..., c] = lut[np.clip((x[..., c] * 1023.0 + 0.5).astype(np.int32), 0, 1023)]
    return y


def t_brightcon(x, p):
    y = x + p["brightness"] / 200.0
    if p["contrast"]:
        y = (y - 0.5) * (2.0 ** (p["contrast"] / 50.0)) + 0.5
    return y


def t_exposure(x, p):
    lin = srgb_to_linear(x) * (2.0 ** p["exposure"]) + p["offset"] / 100.0
    y = linear_to_srgb(lin)
    if p["gamma"] != 1.0:
        y = np.power(np.clip(y, 0, 1), 1.0 / p["gamma"])
    return y


def t_hsl(x, p):
    lab = to_ok(x)
    w = _range_weight(lab, p["range"])
    ang = np.radians(p["hue"]) * w
    s = 1.0 + p["saturation"] / 100.0 * w
    a, b = lab[..., 1], lab[..., 2]
    ca, sa = np.cos(ang), np.sin(ang)
    lab[..., 1] = (a * ca - b * sa) * s
    lab[..., 2] = (a * sa + b * ca) * s
    l = p["lightness"] / 100.0 * w
    L = lab[..., 0]
    lab[..., 0] = np.where(l > 0, L + l * (1.0 - L), L * (1.0 + l))
    return from_ok(lab)


def t_vibrance(x, p):
    lab = to_ok(x)
    C = np.hypot(lab[..., 1], lab[..., 2])
    f = (1.0 + p["vibrance"] / 100.0 * (1.0 - np.clip(C / 0.25, 0.0, 1.0))) * (1.0 + p["saturation"] / 100.0)
    lab[..., 1] *= f
    lab[..., 2] *= f
    return from_ok(lab)


def t_colour_balance(x, p):
    Y = luma(x)
    w = {"Shadows": (1.0 - Y) ** 2, "Highlights": Y ** 2, "Midtones": 4.0 * Y * (1.0 - Y)}[p["tones"]]
    d = np.array([p["cyan_red"], p["magenta_green"], p["yellow_blue"]], dtype=np.float32) / 100.0 * 0.25
    y = x + w[..., None] * d
    if p["preserve"]:
        y = y + (Y - luma(y))[..., None]
    return y


def t_white_balance(x, p):
    lin = srgb_to_linear(x)
    t, n = p["temperature"] / 100.0, p["tint"] / 100.0
    m = np.array([(1 + 0.25 * t) * (1 + 0.12 * n), 1 - 0.2 * n, (1 - 0.25 * t) * (1 + 0.12 * n)], dtype=np.float32)
    y = lin * m
    Y0 = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    Y1 = 0.2126 * y[..., 0] + 0.7152 * y[..., 1] + 0.0722 * y[..., 2]
    y = y * (Y0 / np.maximum(Y1, 1e-6))[..., None]
    return linear_to_srgb(y)


def t_shadows_highlights(x, p):
    lab = to_ok(x)
    L = lab[..., 0]
    bl = gaussian_blur(L[..., None], max(0.5, p["radius"]))[..., 0]
    ms, mh = (1.0 - bl) ** 2, bl ** 2
    s, h = p["shadows"] / 100.0, p["highlights"] / 100.0
    if s:
        L = L + s * ms * ((1.0 - L) if s > 0 else L) * 0.8
    if h:
        L = L + h * mh * ((1.0 - L) if h > 0 else L) * 0.8
    lab[..., 0] = L
    return from_ok(lab)


def t_colorize(x, p):
    lab = to_ok(x)
    L = lab[..., 0]
    l = p["lightness"] / 100.0
    L = L + l * (1.0 - L) if l > 0 else L * (1.0 + l)
    C = p["saturation"] / 100.0 * 0.2
    ang = math.radians(p["hue"])
    col = np.stack([L, np.full_like(L, C * math.cos(ang)), np.full_like(L, C * math.sin(ang))], axis=-1)
    y = from_ok(col)
    k = p["strength"] / 100.0
    return x * (1.0 - k) + y * k


def t_black_white(x, p):
    lab = to_ok(x)
    C = np.hypot(lab[..., 1], lab[..., 2])
    w = hue_weights(lab)
    adj = sum(w[i] * (p[r.lower()] - 50.0) / 100.0 for i, r in enumerate(RANGES))
    L = np.clip(lab[..., 0] + C * adj * 1.5, 0.0, 1.0)
    grey = from_ok(np.stack([L, np.zeros_like(L), np.zeros_like(L)], axis=-1))
    k = p["strength"] / 100.0
    return x * (1.0 - k) + grey * k


def t_channel_mixer(x, p):
    c = ["Red", "Green", "Blue"].index(p["output"])
    y = x.copy()
    y[..., c] = (p["red"] * x[..., 0] + p["green"] * x[..., 1] + p["blue"] * x[..., 2]) / 100.0 + p["constant"] / 100.0
    return y


def _hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def t_gradient_map(x, p):
    t = np.clip(luma(x), 0.0, 1.0)[..., None]
    c0, c1, c2 = _hex_rgb(p["shadow"]), _hex_rgb(p["mid"]), _hex_rgb(p["highlight"])
    if p["use_mid"]:
        lo = c0 + (c1 - c0) * np.clip(t * 2.0, 0, 1)
        hi = c1 + (c2 - c1) * np.clip(t * 2.0 - 1.0, 0, 1)
        y = np.where(t < 0.5, lo, hi)
    else:
        y = c0 + (c2 - c0) * t
    k = p["strength"] / 100.0
    return x * (1.0 - k) + y * k


def t_selective(x, p):
    name = p["range"]
    if name in RANGES:
        w = hue_weights(to_ok(x))[RANGES.index(name)]
    else:
        Y = luma(x)
        sat = np.clip((x.max(-1) - x.min(-1)) / 0.25, 0.0, 1.0)
        if name == "Whites":
            w = np.clip((Y - 0.66) / 0.34, 0.0, 1.0)
        elif name == "Blacks":
            w = np.clip((0.33 - Y) / 0.33, 0.0, 1.0)
        else:
            w = (1.0 - sat) * (1.0 - np.abs(2.0 * Y - 1.0))
    y = x.copy()
    for c, key in enumerate(("cyan", "magenta", "yellow")):
        y[..., c] = x[..., c] * (1.0 - p[key] / 100.0 * w)
    y = y * (1.0 - p["black"] / 100.0 * 0.6 * w)[..., None]
    return y


def t_invert(x, p):
    return x + (1.0 - 2.0 * x) * (p["amount"] / 100.0)


def t_posterize(x, p):
    n = max(2, int(p["levels"]))
    return np.round(np.clip(x, 0, 1) * (n - 1)) / (n - 1)


def t_threshold(x, p):
    v = (luma(x) >= p["level"] / 255.0).astype(np.float32)
    return np.repeat(v[..., None], 3, axis=-1)


# param spec:
#   ("s", key, label, lo, hi, resolution, default)   slider
#   ("c", key, label, [values], default)            dropdown
#   ("b", key, label, default)                      tick box
#   ("col", key, label, "#rrggbb")                  colour button
#   ("curve", key, default_points)                  curve editor
CHANS = ["RGB", "Red", "Green", "Blue"]
TOOLS = {
    "Basic": (t_basic, [
        ("s", "black", "Black", 0, 254, 1, 0),
        ("s", "white", "White", 1, 255, 1, 255),
        ("s", "gamma", "Gamma", 0.2, 3.0, 0.01, 1.0),
        ("s", "brightness", "Brightness", -100, 100, 1, 0),
        ("s", "contrast", "Contrast", -100, 100, 1, 0),
        ("s", "saturation", "Saturation", 0, 300, 1, 100),
        ("s", "hue", "Hue", -180, 180, 1, 0)]),
    "Levels": (t_levels, [
        ("c", "channel", "Channel", CHANS, "RGB"),
        ("s", "in_black", "Input black", 0, 254, 1, 0),
        ("s", "in_white", "Input white", 1, 255, 1, 255),
        ("s", "gamma", "Gamma", 0.1, 5.0, 0.01, 1.0),
        ("s", "out_black", "Output black", 0, 255, 1, 0),
        ("s", "out_white", "Output white", 0, 255, 1, 255)]),
    "Curves": (t_curves, [
        ("c", "channel", "Channel", CHANS, "RGB"),
        ("curve", "points", [[0.0, 0.0], [1.0, 1.0]])]),
    "Brightness / Contrast": (t_brightcon, [
        ("s", "brightness", "Brightness", -100, 100, 1, 0),
        ("s", "contrast", "Contrast", -100, 100, 1, 0)]),
    "Exposure": (t_exposure, [
        ("s", "exposure", "Exposure (stops)", -5.0, 5.0, 0.05, 0.0),
        ("s", "offset", "Offset", -50, 50, 1, 0),
        ("s", "gamma", "Gamma", 0.1, 5.0, 0.01, 1.0)]),
    "HSL": (t_hsl, [
        ("c", "range", "Range", ["Master"] + RANGES, "Master"),
        ("s", "hue", "Hue", -180, 180, 1, 0),
        ("s", "saturation", "Saturation", -100, 200, 1, 0),
        ("s", "lightness", "Lightness", -100, 100, 1, 0)]),
    "Vibrance": (t_vibrance, [
        ("s", "vibrance", "Vibrance", -100, 200, 1, 0),
        ("s", "saturation", "Saturation", -100, 200, 1, 0)]),
    "Colour Balance": (t_colour_balance, [
        ("c", "tones", "Tones", ["Shadows", "Midtones", "Highlights"], "Midtones"),
        ("s", "cyan_red", "Cyan / Red", -100, 100, 1, 0),
        ("s", "magenta_green", "Magenta / Green", -100, 100, 1, 0),
        ("s", "yellow_blue", "Yellow / Blue", -100, 100, 1, 0),
        ("b", "preserve", "Preserve luminosity", True)]),
    "White Balance": (t_white_balance, [
        ("s", "temperature", "Temperature", -100, 100, 1, 0),
        ("s", "tint", "Tint (green / magenta)", -100, 100, 1, 0)]),
    "Shadows / Highlights": (t_shadows_highlights, [
        ("s", "shadows", "Shadows", -100, 100, 1, 0),
        ("s", "highlights", "Highlights", -100, 100, 1, 0),
        ("s", "radius", "Radius (px)", 1, 40, 1, 10)]),
    "Colorize": (t_colorize, [
        ("s", "hue", "Hue", 0, 360, 1, 25),
        ("s", "saturation", "Saturation", 0, 100, 1, 50),
        ("s", "lightness", "Lightness", -100, 100, 1, 0),
        ("s", "strength", "Strength", 0, 100, 1, 100)]),
    "Black & White": (t_black_white, [
        ("s", "reds", "Reds", -100, 200, 1, 50),
        ("s", "yellows", "Yellows", -100, 200, 1, 50),
        ("s", "greens", "Greens", -100, 200, 1, 50),
        ("s", "cyans", "Cyans", -100, 200, 1, 50),
        ("s", "blues", "Blues", -100, 200, 1, 50),
        ("s", "magentas", "Magentas", -100, 200, 1, 50),
        ("s", "strength", "Strength", 0, 100, 1, 100)]),
    "Channel Mixer": (t_channel_mixer, [
        ("c", "output", "Output channel", ["Red", "Green", "Blue"], "Red"),
        ("s", "red", "Red %", -200, 200, 1, 100),
        ("s", "green", "Green %", -200, 200, 1, 0),
        ("s", "blue", "Blue %", -200, 200, 1, 0),
        ("s", "constant", "Constant", -100, 100, 1, 0)]),
    "Gradient Map": (t_gradient_map, [
        ("col", "shadow", "Shadows", "#000000"),
        ("b", "use_mid", "Use midtone colour", True),
        ("col", "mid", "Midtones", "#8b2323"),
        ("col", "highlight", "Highlights", "#ffd7a0"),
        ("s", "strength", "Strength", 0, 100, 1, 100)]),
    "Selective Colour": (t_selective, [
        ("c", "range", "Colours", RANGES + ["Whites", "Neutrals", "Blacks"], "Reds"),
        ("s", "cyan", "Cyan", -100, 100, 1, 0),
        ("s", "magenta", "Magenta", -100, 100, 1, 0),
        ("s", "yellow", "Yellow", -100, 100, 1, 0),
        ("s", "black", "Black", -100, 100, 1, 0)]),
    "Invert": (t_invert, [
        ("s", "amount", "Amount", 0, 100, 1, 100)]),
    "Posterize": (t_posterize, [
        ("s", "levels", "Levels", 2, 32, 1, 6)]),
    "Threshold": (t_threshold, [
        ("s", "level", "Level", 0, 255, 1, 128)]),
}
TOOL_NAMES = list(TOOLS.keys())


def tool_defaults(name):
    d = {}
    for spec in TOOLS[name][1]:
        if spec[0] == "s":
            d[spec[1]] = spec[6]
        elif spec[0] == "c":
            d[spec[1]] = spec[4]
        elif spec[0] == "b":
            d[spec[1]] = spec[3]
        elif spec[0] == "col":
            d[spec[1]] = spec[3]
        elif spec[0] == "curve":
            d[spec[1]] = [list(pt) for pt in spec[2]]
    return d


def apply_tool(x, name, params):
    fn = TOOLS[name][0]
    p = tool_defaults(name)
    p.update(params)
    return np.clip(fn(x.astype(np.float32), p), 0.0, 1.0).astype(np.float32)


def apply_tweaks(x, ops):
    for op in ops:
        x = apply_tool(x, op["tool"], op["params"])
    return x


def gaussian_blur(x, sigma):
    rad = max(1, int(math.ceil(sigma * 3.0)))
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1, dtype=np.float32) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(x, ((rad, rad), (0, 0), (0, 0)), mode="edge")
    y = np.zeros_like(x)
    for i, kv in enumerate(k):
        y += kv * p[i:i + x.shape[0]]
    p = np.pad(y, ((0, 0), (rad, rad), (0, 0)), mode="edge")
    z = np.zeros_like(x)
    for i, kv in enumerate(k):
        z += kv * p[:, i:i + x.shape[1]]
    return z


def apply_sharpen(x, amount, radius):
    if amount <= 0:
        return x
    blur = gaussian_blur(x, max(0.2, radius))
    return np.clip(x + (amount / 100.0) * (x - blur), 0.0, 1.0).astype(np.float32)


# ==========================================================================
#  Loading, resampling and palettising
# ==========================================================================
Image.MAX_IMAGE_PIXELS = None


# --------------------------------------------------------------------------
#  Resampling / palettising helpers
# --------------------------------------------------------------------------
MAJORITY = "Majority (pixel art)"
FILTERS = ["Lanczos", "Box (area average)", "Bicubic", "Hamming", "Bilinear", "Nearest", MAJORITY]


def _pil_filter(name):
    R = Image.Resampling
    return {"Lanczos": R.LANCZOS, "Box (area average)": R.BOX, "Bicubic": R.BICUBIC,
            "Hamming": R.HAMMING, "Bilinear": R.BILINEAR, "Nearest": R.NEAREST}[name]


def max_crop(sw, sh, ratio=CROP_RATIO):
    """Largest centred crop box with the given ratio; ratio None = the whole image."""
    if ratio is None:
        return (0.0, 0.0, float(sw), float(sh))
    if sw / sh > ratio:
        h = float(sh)
        w = h * ratio
    else:
        w = float(sw)
        h = w / ratio
    x = (sw - w) / 2.0
    y = (sh - h) / 2.0
    return (x, y, x + w, y + h)


def load_source(path):
    """-> PIL image: RGBA if the source has any transparency, otherwise RGB."""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        if im.getextrema()[3][0] == 255:          # alpha channel, but nothing transparent
            return im.convert("RGB")
        return im
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(im, dtype=np.float32)
        arr = np.clip(arr / (65535.0 if arr.max() > 255 else 255.0) * 255.0, 0, 255).astype(np.uint8)
        im = Image.fromarray(arr, "L")
    return im.convert("RGB")


def flatten(img):
    """RGBA -> RGB over black (Title mode ignores transparency)."""
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        return Image.alpha_composite(bg, img).convert("RGB")
    return img


def float_channels(img, linear):
    a = np.asarray(img, dtype=np.float32) / 255.0
    if linear:
        a = srgb_to_linear(a)
    return [Image.fromarray(np.ascontiguousarray(a[..., i]), "F") for i in range(3)]


def make_getter(img):
    """Lazy single-entry cache of the source in the form a resizer asks for:
    rgb (flattened float channels), u8 (RGBA uint8 array), u8f (flattened RGBA uint8)."""
    cache = {}

    def get(kind, linear=False):
        key = (kind, bool(linear) if kind == "rgb" else None)
        if key not in cache:
            cache.clear()
            if kind == "rgb":
                cache[key] = float_channels(flatten(img), linear)
            elif kind == "u8f":
                cache[key] = np.asarray(flatten(img).convert("RGBA"), dtype=np.uint8)
            else:
                cache[key] = np.asarray(img.convert("RGBA"), dtype=np.uint8)
        return cache[key]
    return get


def resample(chans, size, box, filter_name, linear):
    filt = _pil_filter(filter_name)
    out = np.stack([np.asarray(c.resize(size, resample=filt, box=box), dtype=np.float32)
                    for c in chans], axis=-1)
    if linear:
        return linear_to_srgb(out)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def majority_resample(src, size, box, thr=0.5):
    """Pixel-art downscale. Each output pixel takes the most common source colour
    in its footprint (sampled on an up-to-6x6 grid); ties go to the colour closest
    to the footprint's average, and transparent loses ties.
    src (H,W,4) uint8 -> (rgb (h,w,3) float 0..1, mask (h,w) bool)."""
    SH, SW = src.shape[:2]
    W, H = size
    x0, y0, x1, y1 = box if box else (0.0, 0.0, float(SW), float(SH))
    sx, sy = (x1 - x0) / W, (y1 - y0) / H
    kx = int(min(6, max(1, round(sx))))
    ky = int(min(6, max(1, round(sy))))
    xi = np.floor(x0 + (np.arange(W)[:, None] + (np.arange(kx)[None, :] + 0.5) / kx) * sx).astype(np.int64)
    yi = np.floor(y0 + (np.arange(H)[:, None] + (np.arange(ky)[None, :] + 0.5) / ky) * sy).astype(np.int64)
    xi = np.clip(xi, 0, SW - 1)
    yi = np.clip(yi, 0, SH - 1)
    n = kx * ky
    a_cut = max(1, int(round(thr * 255)))
    rgb_out = np.zeros((H, W, 3), dtype=np.float32)
    mask = np.zeros((H, W), dtype=bool)
    rows = max(1, int(4000000 // max(1, W * n * n)))
    for r0 in range(0, H, rows):
        r1 = min(H, r0 + rows)
        smp = src[yi[r0:r1][:, None, :, None], xi[None, :, None, :]].reshape(r1 - r0, W, n, 4)
        op = smp[..., 3] >= a_cut
        key = (smp[..., 0].astype(np.int64) << 16) | (smp[..., 1].astype(np.int64) << 8) | smp[..., 2]
        key = np.where(op, key, -1)
        counts = (key[..., :, None] == key[..., None, :]).sum(-1)
        rgbf = smp[..., :3].astype(np.float32)
        nop = op.sum(-1, keepdims=True)
        mean = (rgbf * op[..., None]).sum(-2) / np.maximum(nop, 1)
        dist = ((rgbf - mean[..., None, :]) ** 2).sum(-1)
        dist = np.where(op, dist, 200000.0)
        best = np.argmax(counts.astype(np.float64) * 1e6 - dist, axis=-1)
        pick = np.take_along_axis(smp, best[..., None, None], axis=2)[..., 0, :]
        rgb_out[r0:r1] = pick[..., :3] / 255.0
        mask[r0:r1] = pick[..., 3] >= a_cut
    return rgb_out, mask


def resize_rgb(get, size, box, filter_name, linear):
    """Title mode resize (transparency flattened over black)."""
    if filter_name == MAJORITY:
        return majority_resample(get("u8f"), size, box)[0]
    return resample(get("rgb", linear), size, box, filter_name, linear)


def palettize(pl, matcher, pal_rgb, mode, strength_pct, clamp, serpentine, cancel=None):
    """pl (H,W,3) sRGB 0..1 -> (H,W) uint8 palette indices, or None if cancelled."""
    H, W, _ = pl.shape
    st = strength_pct / 100.0
    if mode == "None" or st <= 0.0:
        idx = matcher.match(pl.reshape(-1, 3), cancel)
        if idx is None:
            return None
        idx = idx.reshape(H, W)
    elif mode in ORDERED:
        off = ordered_offsets(mode, H, W) * (st * 64.0 / 255.0)
        src = np.clip(pl + off[..., None], 0.0, 1.0)
        idx = matcher.match(src.reshape(-1, 3), cancel)
        if idx is None:
            return None
        idx = idx.reshape(H, W)
    else:
        lut = matcher.lut(cancel)
        if lut is None:
            return None
        idx = error_diffuse(pl * 255.0, lut, pal_rgb, mode, st, float(clamp), serpentine, cancel)
        if idx is None:
            return None
    return idx.astype(np.uint8)


def to_u8(x):
    return (np.clip(x, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def paletted_image(idx, pal):
    im = Image.fromarray(idx, "P")
    im.putpalette(pal.pil_palette())
    return im


def save_paletted(idx, pal, path):
    paletted_image(idx, pal).save(path, optimize=True)


def ops_key(ops):
    return json.dumps(ops, sort_keys=True)


# ==========================================================================
#  Stage-cached pipeline and Process Folder
# ==========================================================================
class Pipeline:
    """Stage-cached title pipeline. Stage values are (tc 426x240, pl 426x200)."""

    def __init__(self):
        self.src_key = None
        self.get = None
        self._matchers = {}
        self._reset()

    def _reset(self):
        self._c_resize = (None, None)
        self._c_base = (None, None)
        self._c_adjust = (None, None)
        self._c_pal = (None, None)

    def set_source(self, key, img):
        if key != self.src_key:
            self.src_key = key
            self.get = make_getter(img)
            self._reset()

    def resized(self, p):
        key = (self.src_key, p["crop"], p["filter"], p["linear"])
        if self._c_resize[0] != key:
            tc = resize_rgb(self.get, (OUT_W, DISP_H), p["crop"], p["filter"], p["linear"])
            pl = resize_rgb(self.get, (OUT_W, OUT_H), p["crop"], p["filter"], p["linear"])
            self._c_resize = (key, (tc, pl))
        return key, self._c_resize[1]

    def base(self, p):
        """resized + applied tweaks (before the tool currently being edited)."""
        rkey, (tc, pl) = self.resized(p)
        key = (rkey, ops_key(p["tweaks"]))
        if self._c_base[0] != key:
            self._c_base = (key, (apply_tweaks(tc, p["tweaks"]), apply_tweaks(pl, p["tweaks"])))
        return key, self._c_base[1]

    def adjusted(self, p):
        bkey, (tc, pl) = self.base(p)
        pend = p.get("pending")
        key = (bkey, ops_key(pend), p["sharpen"], p["radius"])
        if self._c_adjust[0] != key:
            if pend:
                tc = apply_tool(tc, pend["tool"], pend["params"])
                pl = apply_tool(pl, pend["tool"], pend["params"])
            tc = apply_sharpen(tc, p["sharpen"], p["radius"])
            pl = apply_sharpen(pl, p["sharpen"], p["radius"])
            self._c_adjust = (key, (tc, pl))
        return key, self._c_adjust[1]

    def matcher(self, p):
        pal = p["palette"]
        mkey = (pal.uid, tuple(sorted(p["excluded"])), p["metric"], p["kL"], p["protect"])
        m = self._matchers.get(mkey)
        if m is None:
            if len(self._matchers) > 4:
                self._matchers.clear()
            m = Matcher(pal, p["excluded"], p["metric"], p["kL"], p["protect"])
            self._matchers[mkey] = m
        return mkey, m

    def paletted(self, p, cancel=None):
        akey, (_, pl) = self.adjusted(p)
        mkey, m = self.matcher(p)
        dkey = (p["dither"], p["strength"], p["clamp"], p["serpentine"])
        key = (akey, mkey, dkey)
        if self._c_pal[0] == key:
            return self._c_pal[1]
        idx = palettize(pl, m, p["palette"].rgb, p["dither"], p["strength"], p["clamp"], p["serpentine"], cancel)
        if idx is None:
            return None
        self._c_pal = (key, idx)
        return idx


# --------------------------------------------------------------------------
#  Processing pipeline (stage cached)
# --------------------------------------------------------------------------
def list_folder_images(folder):
    out = []
    for name in sorted(os.listdir(folder), key=str.lower):
        low = name.lower()
        if not low.endswith(IMAGE_EXTS):
            continue
        stem = os.path.splitext(low)[0]
        if stem.endswith(("-paletted", "-truecolour", "-truecolour-200")):
            continue
        if os.path.isfile(os.path.join(folder, name)):
            out.append(name)
    return out


def process_folder(p, matcher, indir, outdir, do_tweaks, do_sharpen, progress=None):
    """Batch run, writing the files ticked in the Export dialog.
    426x200 sources are used as-is, 426x240 sources are squashed to 426x200,
    anything else is skipped. Returns (processed, skipped[(name, (w,h))], errors[(name, msg)])."""
    files = list_folder_images(indir)
    os.makedirs(outdir, exist_ok=True)
    ops = p["tweaks"] if do_tweaks else []
    want = p["export"]
    processed, skipped, errors = [], [], []

    def finish(x):
        x = apply_tweaks(x, ops)
        return apply_sharpen(x, p["sharpen"], p["radius"]) if do_sharpen else x

    for n, name in enumerate(files, 1):
        if progress:
            progress(n, len(files), name)
        path = os.path.join(indir, name)
        stem = os.path.splitext(name)[0]
        try:
            src = load_source(path)
            get = make_getter(src)
            if src.size == (OUT_W, OUT_H):
                pl, tc240 = get("u8f")[..., :3].astype(np.float32) / 255.0, None
            elif src.size == (OUT_W, DISP_H):
                tc240 = get("u8f")[..., :3].astype(np.float32) / 255.0
                pl = resize_rgb(get, (OUT_W, OUT_H), None, p["filter"], p["linear"])
            else:
                skipped.append((name, src.size))
                continue
            pl = finish(pl)
            if want.get("x_t_pal"):
                idx = palettize(pl, matcher, p["palette"].rgb, p["dither"], p["strength"], p["clamp"],
                                p["serpentine"], None)
                save_paletted(idx, p["palette"], os.path.join(outdir, f"{stem}-paletted.png"))
            if want.get("x_t_tc") and tc240 is not None:
                Image.fromarray(to_u8(finish(tc240)), "RGB").save(
                    os.path.join(outdir, f"{stem}-truecolour.png"), optimize=True)
            if want.get("x_t_tc200"):
                Image.fromarray(to_u8(pl), "RGB").save(os.path.join(outdir, f"{stem}-truecolour-200.png"),
                                                       optimize=True)
            processed.append(name)
        except Exception as e:
            errors.append((name, str(e)))
    return processed, skipped, errors


# ==========================================================================
#  GUI: DPI scaling, fonts and constants
# ==========================================================================
UI_SCALE = 1.0          # extra manual multiplier on top of the DPI factor
DPI_F = 1.0             # real screen DPI / 96, set by dpi_init()


def dpi_init(root):
    """Measure the screen DPI once the Tk root exists. Fonts are in points so Tk
    scales them; anything sized in pixels goes through S()."""
    global DPI_F
    try:
        DPI_F = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        DPI_F = 1.0


def S(v):
    return max(1, int(round(v * UI_SCALE * DPI_F)))


def F(pt):
    return max(6, int(round(pt * UI_SCALE)))


METRICS = [("OKLab (perceptual)", "oklab"), ("CIELAB", "cielab"),
           ("Redmean RGB", "redmean"), ("RGB (euclidean)", "rgb")]
METRIC_NAMES = [m[0] for m in METRICS]
METRIC_CODE = dict(METRICS)
METRIC_NAME = {v: k for k, v in METRICS}
MAX_ZOOM = 16
ZOOM_STEPS = 4          # preview zoom steps per wheel notch (Shift+wheel = 1)
BG = "#1e1e1e"
FONT = ("Segoe UI", F(10))
SMALL = ("Segoe UI", F(9))


# ==========================================================================
#  GUI: Tweak Image window
# ==========================================================================
# ======================================================================
#  Tweak Image window
# ======================================================================
class TweakWindow:
    """Tool palette. Picking another tool carries the current look forward
    (the tool's effect is committed and the next tool starts from it).
    Apply accepts the look and closes; closing otherwise asks to discard."""

    def __init__(self, app):
        self.app = app
        self.start_ops = [dict(op) for op in app.tweaks]
        self.ops = [dict(op) for op in app.tweaks]     # working look for this session
        self.top = tk.Toplevel(app.root)
        self.top.title("Tweak Image")
        self.top.transient(app.root)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.top.geometry(f"{S(480)}x{S(680)}")
        self.hist = None
        self.points = None
        self.curve_drag = None
        self.vars = {}
        self._building = False
        self.tool = TOOL_NAMES[0]

        head = ttk.Frame(self.top, padding=S(8))
        head.pack(fill="x")
        ttk.Label(head, text="Tool").pack(side="left", padx=(0, S(6)))
        self.tool_var = tk.StringVar(value=self.tool)
        cb = ttk.Combobox(head, textvariable=self.tool_var, values=TOOL_NAMES, state="readonly",
                          height=len(TOOL_NAMES))
        cb.pack(side="left", fill="x", expand=True)
        cb.bind("<MouseWheel>", lambda e: "break")
        ttk.Button(head, text="Reset tool", command=self.reset_tool).pack(side="left", padx=(S(6), 0))
        self.tool_var.trace_add("write", lambda *a: self.switch_tool())

        bot = ttk.Frame(self.top, padding=S(8))
        bot.pack(side="bottom", fill="x")
        self.applied = ttk.Label(bot, text="", wraplength=S(450), foreground="#246")
        self.applied.pack(fill="x", pady=(0, S(6)))
        bf = ttk.Frame(bot)
        bf.pack(fill="x")
        ttk.Button(bf, text="Apply", command=self.apply).pack(side="left", padx=(0, S(4)))
        ttk.Button(bf, text="Undo", command=self.undo).pack(side="left", padx=S(4))
        ttk.Button(bf, text="Reset", command=self.reset_image).pack(side="left", padx=S(4))
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")

        self.ctrl = ttk.Frame(self.top, padding=(S(8), 0))
        self.ctrl.pack(fill="both", expand=True)
        self.load_tool(self.tool)

    # -- session state ---------------------------------------------------
    def load_tool(self, name):
        """Show a tool with its default settings (no effect yet)."""
        self.tool = name
        self._building = True
        self.build_panel()
        self._building = False
        self.push_pending()
        self.draw_graphs()
        self.refresh_label()

    def params(self):
        p = {}
        for k, v in self.vars.items():
            try:
                p[k] = v.get()
            except tk.TclError:
                p[k] = tool_defaults(self.tool)[k]
        if self.points is not None and self.curve_canvas is not None:
            p["points"] = [list(pt) for pt in self.points]
        return p

    def modified(self):
        d = tool_defaults(self.tool)
        for k, v in self.params().items():
            dv = d.get(k)
            if isinstance(dv, float) or isinstance(v, float):
                if abs(float(v) - float(dv)) > 1e-9:
                    return True
            elif v != dv:
                return True
        return False

    def current_op(self):
        return {"tool": self.tool, "params": self.params()} if self.modified() else None

    def push_pending(self):
        self.app.pending = self.current_op()
        self.app.schedule(60)
        self.refresh_label()

    def commit_current(self):
        op = self.current_op()
        if op:
            self.ops.append(op)
        self.app.pending = None

    def switch_tool(self):
        name = self.tool_var.get()
        if name == self.tool:
            return
        self.commit_current()
        self.load_tool(name)

    def reset_tool(self):
        self.load_tool(self.tool)

    def reset_image(self):
        if not self.ops and not self.modified():
            return
        if messagebox.askyesno("Tweak Image", "Reset the image back to the source?", parent=self.top):
            self.ops = []
            self.load_tool(self.tool)

    def undo(self):
        if self.modified():
            self.load_tool(self.tool)          # first undo clears the tool being edited
        elif self.ops:
            self.ops.pop()
            self.load_tool(self.tool)

    def changed(self):
        return self.modified() or self.ops != self.start_ops

    def apply(self):
        self.commit_current()
        self.app.tweaks = self.ops
        self._finish()

    def close(self):
        if self.changed() and not messagebox.askyesno(
                "Tweak Image", "Changes not applied.\n\nDiscard them?", parent=self.top):
            return
        self._finish()

    def _finish(self):
        self.app.pending = None
        self.app.tweak_win = None
        self.top.destroy()
        self.app.update_tweak_summary()
        self.app.schedule()

    def refresh_label(self):
        names = [op["tool"] for op in self.ops]
        txt = " \u2192 ".join(names) if names else "(source)"
        if self.modified():
            txt += f"  \u2192 [{self.tool}]"
        self.applied.configure(text="Look: " + txt)

    def want_hist(self):
        return self.tool in ("Levels", "Curves")

    def build_panel(self):
        for w in self.ctrl.winfo_children():
            w.destroy()
        self.vars = {}
        self.hist_canvas = None
        self.curve_canvas = None
        name = self.tool_var.get()
        self.tool = name
        d = tool_defaults(name)
        f = self.ctrl
        f.columnconfigure(1, weight=1)
        row = 0
        if name == "Levels":
            self.hist_canvas = tk.Canvas(f, width=S(300), height=S(90), bg="#fafafa",
                                         highlightthickness=1, highlightbackground="#999")
            self.hist_canvas.grid(row=row, column=0, columnspan=2, pady=S(4))
            row += 1
        for spec in TOOLS[name][1]:
            kind, key = spec[0], spec[1]
            if kind == "s":
                _, _, label, lo, hi, res, dv = spec
                var = tk.DoubleVar(value=dv) if isinstance(res, float) else tk.IntVar(value=dv)
                lab = ttk.Label(f, text=label)
                lab.grid(row=row, column=0, sticky="sw", padx=(0, S(6)))
                sc = tk.Scale(f, from_=lo, to=hi, resolution=res, orient="horizontal", variable=var,
                              showvalue=True, highlightthickness=0, length=S(220),
                              sliderlength=S(22), width=S(14), font=SMALL)
                sc.grid(row=row, column=1, sticky="ew")
                lab.bind("<Double-Button-1>", lambda e, v=var, dv=dv: v.set(dv))
            elif kind == "c":
                _, _, label, values, dv = spec
                var = tk.StringVar(value=dv)
                ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", padx=(0, S(6)), pady=S(3))
                c = ttk.Combobox(f, textvariable=var, values=values, state="readonly")
                c.grid(row=row, column=1, sticky="ew", pady=S(3))
                c.bind("<MouseWheel>", lambda e: "break")
            elif kind == "b":
                _, _, label, dv = spec
                var = tk.BooleanVar(value=dv)
                ttk.Checkbutton(f, text="  " + label, variable=var, style="Big.TCheckbutton").grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=S(3))
            elif kind == "col":
                _, _, label, dv = spec
                var = tk.StringVar(value=dv)
                ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", padx=(0, S(6)), pady=S(3))
                btn = tk.Button(f, bg=dv, activebackground=dv, width=8, relief="raised")
                btn.configure(command=lambda v=var, b=btn: self.pick_colour(v, b))
                btn.grid(row=row, column=1, sticky="w", pady=S(3))
            elif kind == "curve":
                self.points = [list(pt) for pt in d[key]]
                self.curve_canvas = tk.Canvas(f, width=S(300), height=S(300), bg="#fafafa",
                                              highlightthickness=1, highlightbackground="#999")
                self.curve_canvas.grid(row=row, column=0, columnspan=2, pady=S(6))
                self.curve_canvas.bind("<ButtonPress-1>", self.curve_press)
                self.curve_canvas.bind("<B1-Motion>", self.curve_move)
                self.curve_canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "curve_drag", None))
                self.curve_canvas.bind("<Button-3>", self.curve_delete)
                row += 1
                ttk.Label(f, text="Click to add a point, drag to move, right-click to delete.",
                          foreground="#666", font=SMALL).grid(row=row, column=0, columnspan=2, sticky="w")
                row += 1
                continue
            self.vars[key] = var
            var.trace_add("write", lambda *a, k=key: self.on_change(k))
            row += 1

    def pick_colour(self, var, btn):
        res = colorchooser.askcolor(color=var.get(), parent=self.top)
        if res and res[1]:
            var.set(res[1])
            btn.configure(bg=res[1], activebackground=res[1])

    def on_change(self, key):
        if self._building:
            return
        if self.tool == "Channel Mixer" and key == "output":
            ident = {"Red": (100, 0, 0), "Green": (0, 100, 0), "Blue": (0, 0, 100)}[self.vars["output"].get()]
            self._building = True
            for k, v in zip(("red", "green", "blue"), ident):
                self.vars[k].set(v)
            self._building = False
        self.push_pending()
        self.draw_graphs()

    # -- histogram / curve drawing ---------------------------------------
    def set_hist(self, hist):
        self.hist = hist
        self.draw_graphs()

    def _hist_for_channel(self):
        if self.hist is None:
            return None
        ch = self.vars.get("channel")
        name = ch.get() if ch else "RGB"
        return self.hist[{"RGB": 0, "Red": 1, "Green": 2, "Blue": 3}[name]]

    def _draw_hist(self, c, w, h, colour):
        hist = self._hist_for_channel()
        if hist is None:
            return
        m = max(1.0, float(np.percentile(hist, 99.5)))
        for i in range(256):
            v = min(1.0, hist[i] / m)
            x = i * w / 256.0
            c.create_rectangle(x, h - v * h, x + w / 256.0 + 1, h, fill=colour, outline="")

    def draw_graphs(self):
        if self.hist_canvas is not None:
            c = self.hist_canvas
            c.delete("all")
            w, h = int(c.cget("width")), int(c.cget("height"))
            self._draw_hist(c, w, h, "#888")
            p = self.params()
            for key, col in (("in_black", "#000"), ("in_white", "#fff")):
                if key in p:
                    x = p[key] * w / 255.0
                    c.create_line(x, 0, x, h, fill="#c00", width=S(1))
        if self.curve_canvas is not None:
            c = self.curve_canvas
            c.delete("all")
            n = int(c.cget("width"))
            self._draw_hist(c, n, n, "#ddd")
            for i in range(1, 4):
                c.create_line(i * n / 4, 0, i * n / 4, n, fill="#ccc")
                c.create_line(0, i * n / 4, n, i * n / 4, fill="#ccc")
            c.create_line(0, n, n, 0, fill="#bbb", dash=(3, 3))
            lut = monotone_lut(self.points, 256)
            coords = []
            for i in range(256):
                coords += [i * n / 255.0, n - lut[i] * n]
            c.create_line(*coords, fill="#222", width=S(2))
            r = S(5)
            for px, py in self.points:
                X, Y = px * n, n - py * n
                c.create_oval(X - r, Y - r, X + r, Y + r, fill="#fff", outline="#000", width=S(1))

    def _curve_xy(self, e):
        n = int(self.curve_canvas.cget("width"))
        return min(max(e.x / n, 0.0), 1.0), min(max(1.0 - e.y / n, 0.0), 1.0), n

    def curve_press(self, e):
        x, y, n = self._curve_xy(e)
        tol = S(9) / n
        for i, (px, py) in enumerate(self.points):
            if abs(px - x) <= tol and abs(py - y) <= tol:
                self.curve_drag = i
                return
        self.points.append([x, y])
        self.points.sort(key=lambda pt: pt[0])
        self.curve_drag = next(i for i, pt in enumerate(self.points) if pt[0] == x and pt[1] == y)
        self.on_change("points")

    def curve_move(self, e):
        if self.curve_drag is None:
            return
        x, y, n = self._curve_xy(e)
        i = self.curve_drag
        eps = 1.0 / 255.0
        lo = self.points[i - 1][0] + eps if i > 0 else 0.0
        hi = self.points[i + 1][0] - eps if i < len(self.points) - 1 else 1.0
        self.points[i] = [min(max(x, lo), hi), y]
        self.on_change("points")

    def curve_delete(self, e):
        if len(self.points) <= 2:
            return
        x, y, n = self._curve_xy(e)
        tol = S(9) / n
        for i, (px, py) in enumerate(self.points):
            if abs(px - x) <= tol and abs(py - y) <= tol:
                del self.points[i]
                self.on_change("points")
                return

# ======================================================================
#  Process Folder dialog
# ======================================================================


# ==========================================================================
#  GUI: Export dialog
# ==========================================================================
EXPORT_ITEMS = [("t_pal", "x_t_pal", "Paletted  426x200", "-paletted.png"),
                ("t_tc", "x_t_tc", "Truecolour  426x240", "-truecolour.png"),
                ("t_tc200", "x_t_tc200", "Truecolour  426x200", "-truecolour-200.png")]


class ExportDialog:
    def __init__(self, app):
        self.app = app
        V = app.v
        self.items = EXPORT_ITEMS
        self.top = tk.Toplevel(app.root)
        self.top.title("Export")
        self.top.transient(app.root)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.top.bind("<Escape>", lambda e: self.close())
        self.top.bind("<Return>", lambda e: self.run())
        f = ttk.Frame(self.top, padding=S(10))
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        self.folder = tk.StringVar(value=app.outdir or os.path.dirname(app.src_path))
        self.stem = tk.StringVar(value=os.path.splitext(os.path.basename(app.src_path))[0])
        ttk.Label(f, text="Folder").grid(row=0, column=0, sticky="w", padx=(0, S(6)), pady=S(4))
        ttk.Entry(f, textvariable=self.folder, width=50).grid(row=0, column=1, sticky="ew", pady=S(4))
        ttk.Button(f, text="Browse...", command=self.browse).grid(row=0, column=2, padx=(S(6), 0), pady=S(4))
        ttk.Label(f, text="Name").grid(row=1, column=0, sticky="w", padx=(0, S(6)), pady=S(4))
        ttk.Entry(f, textvariable=self.stem, width=50).grid(row=1, column=1, sticky="ew", pady=S(4))
        r = 2
        for kind, key, label, suffix in self.items:
            row = ttk.Frame(f)
            row.grid(row=r, column=0, columnspan=3, sticky="w", pady=S(1))
            ttk.Checkbutton(row, text="  " + label, variable=V[key], style="Big.TCheckbutton").pack(side="left")
            ttk.Label(row, text="   <name>" + suffix, foreground="#666", font=SMALL).pack(side="left")
            r += 1
        ttk.Label(f, text="Process Folder writes the same ticked files.",
                  foreground="#666", font=SMALL).grid(row=r, column=0, columnspan=3, sticky="w", pady=(S(2), 0))
        r += 1
        bf = ttk.Frame(f)
        bf.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(S(8), 0))
        ttk.Button(bf, text="Export", command=self.run).pack(side="left")
        ttk.Button(bf, text="Cancel", command=self.close).pack(side="right")
        self.top.grab_set()

    def browse(self):
        d = filedialog.askdirectory(parent=self.top, initialdir=self.folder.get() or None)
        if d:
            self.folder.set(os.path.normpath(d))

    def run(self):
        folder, stem = self.folder.get().strip(), self.stem.get().strip()
        if not folder or not stem:
            messagebox.showerror("Export", "Set a folder and a name.", parent=self.top)
            return
        jobs = {kind: os.path.join(folder, stem + suffix)
                for kind, key, _, suffix in self.items if self.app.v[key].get()}
        if not jobs:
            messagebox.showerror("Export", "Tick at least one file to write.", parent=self.top)
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Export", f"Could not create the folder:\n{e}", parent=self.top)
            return
        exist = [os.path.basename(q) for q in jobs.values() if os.path.exists(q)]
        if exist and not messagebox.askyesno("Export", "Overwrite?\n\n" + "\n".join(exist), parent=self.top):
            return
        self.app.outdir = folder
        self.close()
        self.app.start_export(jobs)

    def close(self):
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()


# ==========================================================================
#  GUI: Process Folder dialog
# ==========================================================================
class BatchDialog:
    def __init__(self, app):
        self.app = app
        V = app.v
        self.top = tk.Toplevel(app.root)
        self.top.title("Process Folder")
        self.top.transient(app.root)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        f = ttk.Frame(self.top, padding=S(10))
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        for r, (label, key) in enumerate((("Input folder", "b_in"), ("Output folder", "b_out"))):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, S(6)), pady=S(4))
            ttk.Entry(f, textvariable=V[key], width=50).grid(row=r, column=1, sticky="ew", pady=S(4))
            ttk.Button(f, text="Browse...", command=lambda k=key: self.browse(k)).grid(
                row=r, column=2, padx=(S(6), 0), pady=S(4))
        for r, (label, key) in enumerate((("Apply image tweaks", "b_tweaks"),
                                          ("Apply sharpen", "b_sharpen")), start=2):
            ttk.Checkbutton(f, text="  " + label, variable=V[key], style="Big.TCheckbutton").grid(
                row=r, column=0, columnspan=3, sticky="w", pady=S(2))
        r = 4
        self.note = ttk.Label(f, text="", foreground="#666", wraplength=S(520), font=SMALL)
        self.note.grid(row=r, column=0, columnspan=3, sticky="w", pady=(S(6), S(4)))
        bf = ttk.Frame(f)
        bf.grid(row=r + 1, column=0, columnspan=3, sticky="ew", pady=(S(6), 0))
        self.run_btn = ttk.Button(bf, text="Run", command=self.run)
        self.run_btn.pack(side="left")
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")
        self.prog = ttk.Label(f, text="")
        self.prog.grid(row=r + 2, column=0, columnspan=3, sticky="w", pady=(S(6), 0))
        self.refresh_note()

    def refresh_note(self):
        files = ", ".join("<name>" + suf for _, key, _, suf in EXPORT_ITEMS if self.app.v[key].get())
        files = ("Writes the files ticked in Export: " + files + ". ") if files else \
            "Nothing is ticked in Export, so nothing would be written. "
        self.note.configure(text=files + "426x200 images are processed as-is, 426x240 are squashed to 200, "
                                         "anything else is skipped and reported. Uses the current palette, "
                                         "dither and resize filter.")

    def browse(self, key):
        d = filedialog.askdirectory(parent=self.top, initialdir=self.app.v[key].get() or None)
        if d:
            self.app.v[key].set(os.path.normpath(d))
            if key == "b_in" and not self.app.v["b_out"].get():
                self.app.v["b_out"].set(os.path.join(os.path.normpath(d),
                                                     "titlepic_out"))

    def run(self):
        indir, outdir = self.app.v["b_in"].get().strip(), self.app.v["b_out"].get().strip()
        if not indir or not os.path.isdir(indir):
            messagebox.showerror("Process Folder", "Pick an existing input folder.", parent=self.top)
            return
        if not outdir:
            messagebox.showerror("Process Folder", "Pick an output folder.", parent=self.top)
            return
        if not self.app.start_batch(indir, outdir, self.top):
            return
        self.run_btn.state(["disabled"])
        self.prog.configure(text="Starting...")

    def progress(self, n, total, name):
        self.prog.configure(text=f"{n} / {total}   {name}")

    def done(self):
        self.run_btn.state(["!disabled"])
        self.prog.configure(text="Done.")

    def close(self):
        self.app.batch_dlg = None
        self.top.destroy()


# ==========================================================================
#  GUI: main window
# ==========================================================================
HANDLE = 10   # crop handle size in pixels, set from the DPI in run_gui()


# ======================================================================
#  Main app
# ======================================================================
class App:
    def __init__(self, root, args):
        self.args = args
        self.root = root
        root.geometry(f"{S(1400)}x{S(860)}")
        root.minsize(S(900), S(600))

        self.pipe = Pipeline()
        self.palette = Palette.doom2()
        self.raw_src = None          # the image as loaded
        self.src = None
        self.src_path = None
        self.src_key = 0
        self.crop = None
        self.mode = "preview"
        self.tmp_crop = None
        self.drag = None
        self.outdir = self.args.outdir
        self.project_path = None
        self.tweaks = []
        self.pending = None
        self.tweak_win = None
        self.batch_dlg = None
        self._loading = False
        self.compare = False         # side by side: original (left) and result (right)
        self.ozoom = None            # original pane: its own zoom and pan
        self.opan = [0.0, 0.0]
        self._cmp_photos = []
        self._orig_cache = None
        self.preview_tag = ""

        self.cv = threading.Condition()
        self.pending_preview = None
        self.pending_save = None
        self.pending_batch = None
        self.gen = 0
        self.results = queue.Queue()
        self.after_id = None
        self.preview_img = None
        self.photo = None
        self.crop_disp = None
        self.zoom = None
        self.pan = [0.0, 0.0]
        self.pan_drag = None

        self._vars()
        self._build()
        self._title()
        threading.Thread(target=self._worker, daemon=True).start()
        root.after(30, self._poll)

        if self.args.project:
            self._load_project(self.args.project)
        if self.args.palette:
            self._load_palette(self.args.palette)
        if self.args.image:
            root.after(50, lambda: self._open(self.args.image))
        else:
            self._redraw()

    def _title(self):
        t = "titlepic - 426x200 Doom title screen reducer"
        if self.project_path:
            t += f"  [{os.path.basename(self.project_path)}]"
        self.root.title(t)

    # ---------------- variables ----------------
    def _vars(self):
        V = self.v = {}
        V["filter"] = tk.StringVar(value="Lanczos")
        V["linear"] = tk.BooleanVar(value=True)
        V["sharpen"] = tk.IntVar(value=0)
        V["radius"] = tk.DoubleVar(value=0.8)
        V["pal_on"] = tk.BooleanVar(value=False)
        V["metric"] = tk.StringVar(value=METRIC_NAMES[0])
        V["kL"] = tk.DoubleVar(value=1.0)
        V["protect"] = tk.IntVar(value=0)
        V["exclude"] = tk.StringVar(value="")
        V["dither"] = tk.StringVar(value="None")
        V["strength"] = tk.IntVar(value=75)
        V["clamp"] = tk.IntVar(value=96)
        V["serpentine"] = tk.BooleanVar(value=True)
        V["raw"] = tk.BooleanVar(value=False)
        # process folder settings (saved in the project, never trigger renders)
        V["b_in"] = tk.StringVar(value="")
        V["b_out"] = tk.StringVar(value="")
        V["b_tweaks"] = tk.BooleanVar(value=True)
        V["b_sharpen"] = tk.BooleanVar(value=True)
        # export ticks (saved in the project, never trigger renders)
        for k in ("x_t_pal", "x_t_tc", "x_t_tc200"):
            V[k] = tk.BooleanVar(value=True)
        self.defaults = {k: var.get() for k, var in V.items()}
        for k, var in V.items():
            if not k.startswith(("b_", "x_")):
                var.trace_add("write", lambda *a, k=k: self._changed(k))

    # ---------------- layout ----------------
    def _big_check_style(self, style):
        """Image-based checkbox indicator, so its size follows the DPI."""
        n = S(16)
        imgs = {}
        for name, checked, dis in (("off", False, False), ("on", True, False),
                                   ("doff", False, True), ("don", True, True)):
            im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, n - 1, n - 1), fill="#f0f0f0" if dis else "#ffffff",
                        outline="#a0a0a0" if dis else "#404040", width=max(1, n // 12))
            if checked:
                col = "#a0a0a0" if dis else "#1f8a4c"
                d.line([(n * 0.2, n * 0.52), (n * 0.42, n * 0.74), (n * 0.80, n * 0.26)],
                       fill=col, width=max(2, n // 6), joint="curve")
            imgs[name] = ImageTk.PhotoImage(im)
        self._chk_imgs = imgs
        style.element_create("Big.Checkbutton.indicator", "image", imgs["off"],
                             ("disabled", "selected", imgs["don"]),
                             ("disabled", imgs["doff"]),
                             ("selected", imgs["on"]))
        style.layout("Big.TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Big.Checkbutton.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"})]})]})])
        style.configure("Big.TCheckbutton", padding=(S(2), S(3)))

    def _build(self):
        root = self.root
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=FONT)
        style.configure("TButton", padding=(S(6), S(3)))
        style.configure("Vertical.TScrollbar", arrowsize=S(16), width=S(16))
        style.configure("Horizontal.TScrollbar", arrowsize=S(16), width=S(16))
        style.configure("TCombobox", arrowsize=S(14), padding=S(2))
        style.configure("TSpinbox", arrowsize=S(14), padding=S(2))
        root.option_add("*TCombobox*Listbox.font", FONT)
        self._big_check_style(style)

        bar = ttk.Frame(root, padding=(S(4), S(3)))
        bar.pack(side="top", fill="x")

        def btn(text, cmd):
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side="left", padx=S(2))
            return b

        def sep():
            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=S(6))

        btn("Open...", self._open_dialog)
        self.btn_crop = btn("Crop", self._enter_crop)
        btn("Palette...", self._palette_dialog)
        sep()
        self.btn_export = btn("Export", self._export)
        btn("Process Folder...", self._batch_dialog)
        sep()
        btn("Load Project...", self._load_project_dialog)
        btn("Save Project...", self._save_project_dialog)
        sep()
        btn("Fit", self._zoom_fit)
        self.btn_compare = btn("Compare: Off", self._toggle_compare)
        self.zoom_label = ttk.Label(bar, text="Zoom: fit", width=14)
        self.zoom_label.pack(side="left", padx=S(4))

        self.cropbar = ttk.Frame(bar)
        ttk.Separator(self.cropbar, orient="vertical").pack(side="left", fill="y", padx=S(6))
        ttk.Button(self.cropbar, text="OK", command=self._crop_ok).pack(side="left", padx=S(2))
        ttk.Button(self.cropbar, text="Cancel", command=self._crop_cancel).pack(side="left", padx=S(2))
        ttk.Button(self.cropbar, text="Max", command=self._crop_max).pack(side="left", padx=S(2))
        self.crop_info = ttk.Label(self.cropbar, text="")
        self.crop_info.pack(side="left", padx=S(8))

        self.status = ttk.Label(root, text="Open an image to start.", anchor="w", padding=(S(6), S(3)))
        self.status.pack(side="bottom", fill="x")

        main = tk.PanedWindow(root, orient="horizontal", sashwidth=S(6), sashrelief="raised",
                              bg="#6a6a6a", bd=0, opaqueresize=True)
        main.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0)
        main.add(self.canvas, minsize=S(300), stretch="always")

        side = ttk.Frame(main)
        main.add(side, minsize=S(280), width=S(380), stretch="never")
        self.side = side
        self.opt_canvas = tk.Canvas(side, highlightthickness=0)
        sb = ttk.Scrollbar(side, orient="vertical", command=self.opt_canvas.yview)
        self.opt_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.opt_canvas.pack(side="left", fill="both", expand=True)
        self.opt = ttk.Frame(self.opt_canvas, padding=S(6))
        self.opt_win = self.opt_canvas.create_window((0, 0), window=self.opt, anchor="nw")
        self.opt.bind("<Configure>", lambda e: self.opt_canvas.configure(
            scrollregion=self.opt_canvas.bbox("all")))
        self.opt_canvas.bind("<Configure>", lambda e: self.opt_canvas.itemconfigure(
            self.opt_win, width=e.width))
        root.bind_all("<MouseWheel>", self._wheel_dispatch)

        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<ButtonPress-1>", self._c_press)
        self.canvas.bind("<B1-Motion>", self._c_drag)
        self.canvas.bind("<ButtonRelease-1>", self._c_release)
        self.canvas.bind("<Motion>", self._c_motion)
        self.canvas.bind("<Double-Button-1>", self._c_double)
        self.canvas.bind("<ButtonPress-2>", self._pan_start)
        self.canvas.bind("<B2-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-2>", self._pan_end)
        self.canvas.bind("<ButtonPress-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-3>", self._pan_end)
        root.bind("<Return>", lambda e: self._crop_ok() if self.mode == "crop" else None)
        root.bind("<Escape>", lambda e: self._crop_cancel())

        self._build_options()

    def _wheel_dispatch(self, e):
        w = self.root.winfo_containing(e.x_root, e.y_root)
        if w is None:
            return
        if w is self.canvas:
            self._c_wheel(e)
            return "break"
        p = w
        while p is not None:
            if p is self.side:
                self._panel_wheel(e)
                return "break"
            p = p.master

    def _panel_wheel(self, e):
        self.opt_canvas.yview_scroll(int(-e.delta / 120), "units")
        return "break"

    def _section(self, title):
        f = ttk.LabelFrame(self.opt, text=title, padding=(S(6), S(4)))
        f.pack(fill="x", pady=S(4))
        f.columnconfigure(1, weight=1)
        f._row = 0
        return f

    def _slider(self, f, label, key, lo, hi, res=1):
        lab = ttk.Label(f, text=label)
        lab.grid(row=f._row, column=0, sticky="sw", padx=(0, S(6)))
        sc = tk.Scale(f, from_=lo, to=hi, resolution=res, orient="horizontal",
                      variable=self.v[key], showvalue=True, highlightthickness=0,
                      length=S(200), sliderlength=S(22), width=S(14), font=SMALL)
        sc.grid(row=f._row, column=1, sticky="ew")
        lab.bind("<Double-Button-1>", lambda e: self.v[key].set(self.defaults[key]))
        f._row += 1
        return sc

    def _combo(self, f, label, key, values):
        ttk.Label(f, text=label).grid(row=f._row, column=0, sticky="w", padx=(0, S(6)), pady=S(2))
        cb = ttk.Combobox(f, textvariable=self.v[key], values=values, state="readonly")
        cb.grid(row=f._row, column=1, sticky="ew", pady=S(2))
        cb.bind("<MouseWheel>", self._panel_wheel)
        f._row += 1
        return cb

    def _check(self, f, label, key):
        cb = ttk.Checkbutton(f, text="  " + label, variable=self.v[key], style="Big.TCheckbutton")
        cb.grid(row=f._row, column=0, columnspan=2, sticky="w", pady=S(2))
        f._row += 1
        return cb

    def _build_options(self):
        f = self._section("Resize")
        self._combo(f, "Filter", "filter", FILTERS)
        self._check(f, "Linear light (gamma-correct averaging)", "linear")
        ttk.Label(f, text="Output fixed at 426x200, crop locked to 426:240 "
                          "(16:9 once Doom stretches it by 1.2).",
                  foreground="#666", wraplength=S(320), font=SMALL).grid(
            row=f._row, column=0, columnspan=2, sticky="w", pady=(S(2), 0))
        f._row += 1

        f = self._section("Image tweaks")
        ttk.Button(f, text="Tweak Image...", command=self._tweak_window).grid(
            row=f._row, column=0, columnspan=2, sticky="ew", pady=S(2))
        f._row += 1
        self.tweak_summary = ttk.Label(f, text="", foreground="#246", wraplength=S(320))
        self.tweak_summary.grid(row=f._row, column=0, columnspan=2, sticky="w", pady=S(2))
        f._row += 1

        f = self._section("Sharpen (after downscale)")
        self._slider(f, "Amount", "sharpen", 0, 300)
        self._slider(f, "Radius", "radius", 0.3, 3.0, 0.05)
        ttk.Button(f, text="Reset sharpen", command=self._reset_sharpen).grid(
            row=f._row, column=0, columnspan=2, sticky="ew", pady=(S(4), S(2)))
        f._row += 1

        f = self._section("Palette")
        self._check(f, "Palette match (preview)", "pal_on")
        self.pal_label = ttk.Label(f, text=self.palette.name, foreground="#2a6")
        self.pal_label.grid(row=f._row, column=0, columnspan=2, sticky="w")
        f._row += 1
        bf = ttk.Frame(f)
        bf.grid(row=f._row, column=0, columnspan=2, sticky="ew", pady=S(2))
        ttk.Button(bf, text="Load...", command=self._palette_dialog).pack(side="left", padx=(0, S(4)))
        ttk.Button(bf, text="Doom 2", command=self._palette_doom2).pack(side="left")
        f._row += 1
        self.sw_cell = S(13)
        self.swatch = tk.Canvas(f, width=16 * self.sw_cell + 1, height=16 * self.sw_cell + 1,
                                bg="#000", highlightthickness=0)
        self.swatch.grid(row=f._row, column=0, columnspan=2, pady=S(4))
        self.swatch.bind("<Button-1>", self._swatch_click)
        self.swatch.bind("<Motion>", self._swatch_motion)
        f._row += 1
        ttk.Label(f, text="Exclude").grid(row=f._row, column=0, sticky="w")
        self.ex_entry = ttk.Entry(f, textvariable=self.v["exclude"])
        self.ex_entry.grid(row=f._row, column=1, sticky="ew", pady=S(2))
        f._row += 1
        self.pal_widgets = []
        self.pal_widgets.append(self._combo(f, "Metric", "metric", METRIC_NAMES))
        self.lab_widgets = [self._slider(f, "Lightness wt", "kL", 0.1, 3.0, 0.05),
                            self._slider(f, "Chroma protect", "protect", 0, 300)]
        self.pal_widgets += self.lab_widgets + [self.ex_entry]

        f = self._section("Dither")
        self.pal_widgets.append(self._combo(f, "Method", "dither", DITHER_MODES))
        self.dither_strength = self._slider(f, "Strength", "strength", 0, 100)
        self.dither_clamp = self._slider(f, "Error clamp", "clamp", 4, 255)
        self.dither_serp = self._check(f, "Serpentine scan", "serpentine")
        self.pal_widgets += [self.dither_strength, self.dither_clamp, self.dither_serp]

        f = self._section("Preview")
        self.raw_check = self._check(f, "Raw 426x200 pixels (no 1.2 aspect stretch)", "raw")

        ttk.Label(f, text="Mouse wheel zooms, drag pans, double-click or Fit to fit.",
                  foreground="#666", wraplength=S(320), font=SMALL).grid(
            row=f._row, column=0, columnspan=2, sticky="w")
        f._row += 1

        self._draw_swatch()
        self._update_states()
        self.update_tweak_summary()

    # ---------------- state ----------------
    def _set_state(self, w, on):
        try:
            if isinstance(w, tk.Scale):
                w.configure(state="normal" if on else "disabled", fg="#000" if on else "#999")
            elif isinstance(w, ttk.Combobox):
                w.configure(state="readonly" if on else "disabled")
            else:
                w.state(["!disabled"] if on else ["disabled"])
        except tk.TclError:
            pass

    def _update_states(self):
        self.btn_crop.state(["!disabled"] if self.src is not None and self.mode == "preview" else ["disabled"])
        on = self.v["pal_on"].get()
        for w in self.pal_widgets:
            self._set_state(w, on)
        if on:
            lab = METRIC_CODE[self.v["metric"].get()] in ("oklab", "cielab")
            for w in self.lab_widgets:
                self._set_state(w, lab)
            d = self.v["dither"].get()
            self._set_state(self.dither_strength, d != "None")
            self._set_state(self.dither_clamp, d in ED_KERNELS)
            self._set_state(self.dither_serp, d in ED_KERNELS)

    def _changed(self, key):
        if key in ("pal_on", "metric", "dither"):
            self._update_states()
        if key == "exclude":
            self._draw_swatch()
        self.schedule()

    def _out_sizes(self):
        """-> (true-colour size, lump size)."""
        return (OUT_W, DISP_H), (OUT_W, OUT_H)

    def _show(self, reset=False):
        """Feed the pipeline the source with its 426:240 crop."""
        img = self.raw_src
        if img is None:
            self._redraw()
            return
        keep = not reset and self.crop is not None and self.src is img
        if reset or self.src is None:
            self.preview_img = None          # new image: back to Fit
            self.zoom = None
            self.pan = [0.0, 0.0]
            self.ozoom = None
            self.opan = [0.0, 0.0]
        self.crop = self.crop if keep else max_crop(img.width, img.height, CROP_RATIO)
        self.src = img
        self.src_key += 1
        self.crop_disp = None
        self.status.configure(text=self._src_text())
        self._redraw()
        self.schedule(10)

    def _reset_sharpen(self):
        for k in ("sharpen", "radius"):
            self.v[k].set(self.defaults[k])

    def update_tweak_summary(self):
        n = len(self.tweaks)
        if n == 0:
            txt = "No tweaks applied."
        else:
            txt = f"{n} tweak{'s' if n != 1 else ''}: " + " \u2192 ".join(op["tool"] for op in self.tweaks)
        self.tweak_summary.configure(text=txt)

    def set_pending(self, op):
        self.pending = op
        self.schedule(60)

    def _excluded(self):
        try:
            return parse_indices(self.v["exclude"].get())
        except ValueError:
            return set()

    def _params(self, committed=False):
        V = self.v
        if self.tweak_win and not committed:
            tweaks, pending = [dict(op) for op in self.tweak_win.ops], self.pending
        else:
            tweaks, pending = [dict(op) for op in self.tweaks], None
        return {
            "crop": tuple(round(c, 3) for c in self.crop) if self.crop else None,
            "export": {k: V[k].get() for k in V if k.startswith("x_")},
            "filter": V["filter"].get(),
            "linear": V["linear"].get(),
            "tweaks": tweaks,
            "pending": pending,
            "sharpen": V["sharpen"].get(),
            "radius": round(V["radius"].get(), 3),
            "pal_on": V["pal_on"].get(),
            "palette": self.palette,
            "excluded": frozenset(self._excluded()),
            "metric": METRIC_CODE[V["metric"].get()],
            "kL": round(V["kL"].get(), 3),
            "protect": V["protect"].get() / 100.0,
            "dither": V["dither"].get(),
            "strength": V["strength"].get(),
            "clamp": V["clamp"].get(),
            "serpentine": V["serpentine"].get(),
            "raw": V["raw"].get(),
            "src": (self.src_key, self.src),
            "want_hist": bool(self.tweak_win and self.tweak_win.want_hist()),
        }

    # ---------------- worker ----------------
    def schedule(self, delay=120):
        if self.src is None or self.crop is None:
            return
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.after_id = self.root.after(delay, self._submit)

    def _submit(self):
        self.after_id = None
        self.gen += 1
        with self.cv:
            self.pending_preview = {"gen": self.gen, "params": self._params()}
            self.cv.notify()
        self.status.configure(text=self.status.cget("text").split("  |  ")[0] + "  |  rendering...")

    def _worker(self):
        while True:
            with self.cv:
                while self.pending_preview is None and self.pending_save is None and self.pending_batch is None:
                    self.cv.wait()
                if self.pending_save is not None:
                    req, kind = self.pending_save, "save"
                    self.pending_save = None
                elif self.pending_batch is not None:
                    req, kind = self.pending_batch, "batch"
                    self.pending_batch = None
                else:
                    req, kind = self.pending_preview, "preview"
                    self.pending_preview = None
            try:
                if kind == "batch":
                    self._do_batch(req)
                    continue
                p = req["params"]
                self.pipe.set_source(*p["src"])
                if kind == "preview":
                    self._do_preview(req)
                else:
                    self._do_save(req)
            except Exception:
                self.results.put(("error", traceback.format_exc()))

    def _do_preview(self, req):
        p = req["params"]
        t0 = time.perf_counter()
        cancel = lambda: self.pending_preview is not None  # noqa: E731
        hist = None
        if p["want_hist"]:
            _, (btc, _) = self.pipe.base(p)
            px = btc.reshape(-1, 3)
            u = to_u8(px)
            hist = [np.bincount(to_u8(luma(px)).ravel(), minlength=256)] + \
                   [np.bincount(u[..., c].ravel(), minlength=256) for c in range(3)]
        _, (tc, pl) = self.pipe.adjusted(p)
        if p["pal_on"]:
            idx = self.pipe.paletted(p, cancel)
            if idx is None:
                return
            im = Image.fromarray(p["palette"].rgb[idx], "RGB")
            info = f"paletted, {len(np.unique(idx))} colours"
            if not p["raw"]:
                im = im.resize((OUT_W, DISP_H), Image.Resampling.NEAREST)
        else:
            im = Image.fromarray(to_u8(pl if p["raw"] else tc), "RGB")
            info = "true colour"
        dt = (time.perf_counter() - t0) * 1000.0
        self.results.put(("preview", req["gen"], im, f"{info}  |  {dt:.0f} ms", hist, ""))

    def _do_save(self, req):
        p = req["params"]
        jobs = req["jobs"]                  # kind -> path
        _, (tc, pl) = self.pipe.adjusted(p)
        if "t_pal" in jobs:
            save_paletted(self.pipe.paletted(p, None), p["palette"], jobs["t_pal"])
        if "t_tc" in jobs:
            Image.fromarray(to_u8(tc), "RGB").save(jobs["t_tc"], optimize=True)
        if "t_tc200" in jobs:
            Image.fromarray(to_u8(pl), "RGB").save(jobs["t_tc200"], optimize=True)
        self.results.put(("saved",) + tuple(jobs.values()))

    def _do_batch(self, req):
        p = req["params"]
        _, matcher = self.pipe.matcher(p)
        res = process_folder(p, matcher, req["indir"], req["outdir"], req["tweaks"], req["sharpen"],
                             progress=lambda n, t, name: self.results.put(
                                 ("batch_progress", n, t, name)))
        self.results.put(("batch_done", req["indir"], req["outdir"]) + res)

    def _poll(self):
        try:
            while True:
                msg = self.results.get_nowait()
                kind = msg[0]
                if kind == "preview":
                    _, gen, im, info, hist, tag = msg
                    if gen == self.gen:
                        self.preview_img = im
                        self.preview_tag = tag
                        self.status.configure(text=self._src_text() + "  |  " + info)
                        if self.mode == "preview":
                            self._redraw()
                        if hist is not None and self.tweak_win:
                            self.tweak_win.set_hist(hist)
                elif kind == "saved":
                    self.root.configure(cursor="")
                    self.btn_export.state(["!disabled"])
                    self.status.configure(text="Exported " + ", ".join(os.path.basename(q) for q in msg[1:])
                                               + f"  ->  {os.path.dirname(msg[1])}")
                elif kind == "batch_progress":
                    if self.batch_dlg:
                        self.batch_dlg.progress(*msg[1:])
                elif kind == "batch_done":
                    if self.batch_dlg:
                        self.batch_dlg.done()
                    self._batch_report(*msg[1:])
                elif kind == "error":
                    self.root.configure(cursor="")
                    self.btn_export.state(["!disabled"])
                    if self.batch_dlg:
                        self.batch_dlg.done()
                    print(msg[1], file=sys.stderr)
                    messagebox.showerror("titlepic", msg[1].strip().splitlines()[-1])
        except queue.Empty:
            pass
        self.root.after(30, self._poll)

    def _src_text(self):
        if self.src is None:
            return ""
        t = (f"{os.path.basename(self.src_path)} {self.src.width}x{self.src.height}"
             + (" (alpha)" if self.src.mode == "RGBA" else ""))
        x0, y0, x1, y1 = self.crop
        t += f"  |  crop {x1 - x0:.0f}x{y1 - y0:.0f}"
        if (y1 - y0) < DISP_H - 0.5:
            t += " (UPSCALING)"
        return t

    # ---------------- file ops ----------------
    def _open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open source image",
            filetypes=[("Images", " ".join("*" + e for e in IMAGE_EXTS)), ("All files", "*.*")])
        if path:
            self._open(path)

    def _open(self, path):
        try:
            img = load_source(path)
        except Exception as e:
            messagebox.showerror("titlepic", f"Could not open image:\n{e}")
            return
        if self.mode == "crop":
            self._crop_cancel()
        self.raw_src = img
        self.src = None
        self.src_path = os.path.abspath(path)
        self.preview_img = None
        self._show(reset=True)
        self._update_states()

    def _palette_dialog(self):
        path = filedialog.askopenfilename(
            title="Load palette",
            filetypes=[("Palettes", "*.png *.wad *.pal *.lmp *.gpl *.act *.bmp *.gif"), ("All files", "*.*")])
        if path:
            self._load_palette(path)

    def _load_palette(self, path):
        try:
            self.palette = load_palette(path)
        except Exception as e:
            messagebox.showerror("titlepic", f"Could not load palette:\n{e}")
            return
        self._palette_changed()

    def _palette_doom2(self):
        self.palette = Palette.doom2()
        self._palette_changed()

    def _palette_changed(self):
        self.pal_label.configure(text=self.palette.name)
        self._draw_swatch()
        self.schedule()

    def _export(self):
        if self.src is None:
            return
        if self.mode == "crop":
            self._crop_ok()
        ExportDialog(self)

    def start_export(self, jobs):
        self.root.configure(cursor="watch")
        self.btn_export.state(["disabled"])
        self.status.configure(text="Exporting...")
        p = self._params(committed=True)     # unapplied tweak-window changes are not exported
        with self.cv:
            self.pending_save = {"params": p, "jobs": jobs}
            self.cv.notify()

    # ---------------- process folder ----------------
    def _batch_dialog(self):
        if self.batch_dlg:
            self.batch_dlg.top.lift()
            return
        self.batch_dlg = BatchDialog(self)

    def start_batch(self, indir, outdir, parent=None):
        p = self._params(committed=True)
        if not any(self.v[key].get() for _, key, _, _ in EXPORT_ITEMS):
            messagebox.showerror("Process Folder", "Nothing is ticked in the Export dialog.", parent=parent)
            return False
        with self.cv:
            self.pending_batch = {"params": p, "indir": indir, "outdir": outdir,
                                  "tweaks": self.v["b_tweaks"].get(),
                                  "sharpen": self.v["b_sharpen"].get()}
            self.cv.notify()
        return True

    def _batch_report(self, indir, outdir, processed, skipped, errors):
        lines = [f"Input:   {indir}", f"Output:  {outdir}", "",
                 f"Processed: {len(processed)}"]
        lines += [f"   {x}" for x in processed if "   (" in x]
        if skipped:
            lines += ["", f"Skipped (not 426x200 or 426x240): {len(skipped)}"]
            lines += [f"   {name}   ({w}x{h})" for name, (w, h) in skipped]
        if errors:
            lines += ["", f"Errors: {len(errors)}"]
            lines += [f"   {name}   {msg}" for name, msg in errors]
        if not processed and not skipped and not errors:
            lines += ["", "No images found."]
        text = "\n".join(lines)
        print("\n[titlepic] Process Folder report\n" + text + "\n")
        top = tk.Toplevel(self.root)
        top.title("Process Folder - report")
        top.transient(self.root)
        frm = ttk.Frame(top, padding=S(8))
        frm.pack(fill="both", expand=True)
        t = tk.Text(frm, width=80, height=min(30, len(lines) + 2), font=("Consolas", F(10)), wrap="none")
        sb = ttk.Scrollbar(frm, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        t.insert("1.0", text)
        t.configure(state="disabled")
        ttk.Button(top, text="Close", command=top.destroy).pack(pady=(0, S(8)))

    # ---------------- projects ----------------
    def _project_dict(self):
        V = self.v
        settings = {k: V[k].get() for k in V if not k.startswith("b_")}
        settings["metric"] = METRIC_CODE[V["metric"].get()]
        return {
            "titlepic_project": 1,
            "settings": settings,
            "tweaks": self.tweaks,
            "palette": {"name": self.palette.name, "rgb": self.palette.rgb.tobytes().hex()},
            "process_folder": {k[2:]: V[k].get() for k in V if k.startswith("b_")},
        }

    def _save_project_dialog(self):
        init = self.project_path or (os.path.splitext(self.src_path)[0] + PROJECT_EXT if self.src_path else None)
        path = filedialog.asksaveasfilename(
            title="Save project", defaultextension=PROJECT_EXT,
            initialdir=os.path.dirname(init) if init else None,
            initialfile=os.path.basename(init) if init else None,
            filetypes=[("titlepic project", "*" + PROJECT_EXT), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._project_dict(), fh, indent=2)
        except Exception as e:
            messagebox.showerror("titlepic", f"Could not save project:\n{e}")
            return
        self.project_path = os.path.abspath(path)
        self._title()
        self.status.configure(text=f"Project saved: {path}")

    def _load_project_dialog(self):
        path = filedialog.askopenfilename(
            title="Load project",
            filetypes=[("titlepic project", "*" + PROJECT_EXT), ("All files", "*.*")])
        if path:
            self._load_project(path)

    def _load_project(self, path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if "titlepic_project" not in data:
                raise ValueError("not a titlepic project file")
        except Exception as e:
            messagebox.showerror("titlepic", f"Could not load project:\n{e}")
            return
        V = self.v
        self._loading = True
        try:
            for k, val in data.get("settings", {}).items():
                if k == "metric":
                    val = METRIC_NAME.get(val, METRIC_NAMES[0])
                if k in V and not k.startswith("b_"):        # settings this tool doesn't have are ignored
                    try:
                        V[k].set(val)
                    except tk.TclError:
                        pass
            for k, val in data.get("process_folder", {}).items():
                if "b_" + k in V:
                    try:
                        V["b_" + k].set(val)
                    except tk.TclError:
                        pass
        finally:
            self._loading = False
        if self.mode == "crop":
            self._crop_cancel()
        pal = data.get("palette")
        if pal and pal.get("rgb"):
            try:
                self.palette = Palette(np.frombuffer(bytes.fromhex(pal["rgb"]), dtype=np.uint8)[:768],
                                       pal.get("name", "project palette"))
            except Exception:
                self.palette = Palette.doom2()
        self.tweaks = [op for op in data.get("tweaks", []) if op.get("tool") in TOOLS]
        if self.tweak_win:                    # an open session is replaced by the project's look
            self.tweak_win._finish()
        self.pending = None
        self.update_tweak_summary()
        self.project_path = os.path.abspath(path)
        self._title()
        self._palette_changed()
        self._update_states()
        self.status.configure(text=f"Project loaded: {path}")

    # ---------------- tweak window ----------------
    def _tweak_window(self):
        if self.tweak_win:
            self.tweak_win.top.lift()
            return
        self.tweak_win = TweakWindow(self)

    # ---------------- swatch ----------------
    def _draw_swatch(self):
        c = self.swatch
        c.delete("all")
        ex = self._excluded()
        s = self.sw_cell
        for i in range(256):
            x, y = (i % 16) * s, (i // 16) * s
            r, g, b = self.palette.rgb[i]
            c.create_rectangle(x, y, x + s, y + s, fill=f"#{r:02x}{g:02x}{b:02x}", outline="#000")
            if i in ex:
                c.create_line(x + 1, y + 1, x + s - 1, y + s - 1, fill="#f0f", width=max(1, s // 6))
                c.create_line(x + s - 1, y + 1, x + 1, y + s - 1, fill="#f0f", width=max(1, s // 6))

    def _swatch_index(self, e):
        gx, gy = e.x // self.sw_cell, e.y // self.sw_cell
        if 0 <= gx < 16 and 0 <= gy < 16:
            return gy * 16 + gx
        return None

    def _swatch_click(self, e):
        if not self.v["pal_on"].get():
            return
        i = self._swatch_index(e)
        if i is None:
            return
        ex = self._excluded()
        ex ^= {i}
        self.v["exclude"].set(format_indices(ex))

    def _swatch_motion(self, e):
        i = self._swatch_index(e)
        if i is not None:
            r, g, b = self.palette.rgb[i]
            tag = "  [excluded]" if i in self._excluded() else ""
            self.status.configure(text=f"index {i}: ({r}, {g}, {b})" + tag)

    # ---------------- canvas drawing ----------------
    def _redraw(self):
        c = self.canvas
        c.delete("all")
        cw, ch = max(1, c.winfo_width()), max(1, c.winfo_height())
        if self.src is None:
            c.create_text(cw // 2, ch // 2, text="Open an image  (any size)", fill="#888",
                          font=("Segoe UI", F(14)))
            return
        if self.mode == "crop":
            self._draw_crop(cw, ch)
            return
        im = self.preview_img
        if im is None:
            c.create_text(cw // 2, ch // 2, text="rendering...", fill="#888", font=("Segoe UI", F(12)))
            return
        if self._comparing():
            self._draw_compare(im, cw, ch)
            return
        self._cmp_photos = []
        k = self._zoom_k()
        w, h = im.width * k, im.height * k
        self._clamp_pan(w, h, cw, ch)
        X0 = cw / 2 + self.pan[0] - w / 2
        Y0 = ch / 2 + self.pan[1] - h / 2
        if k >= 1:
            u0 = max(0, int(math.floor(-X0 / k)))
            v0 = max(0, int(math.floor(-Y0 / k)))
            u1 = min(im.width, int(math.ceil((cw - X0) / k)))
            v1 = min(im.height, int(math.ceil((ch - Y0) / k)))
            if u1 <= u0 or v1 <= v0:
                return
            part = im.crop((u0, v0, u1, v1)).resize(((u1 - u0) * k, (v1 - v0) * k),
                                                    Image.Resampling.NEAREST)
            px, py = X0 + u0 * k, Y0 + v0 * k
        else:
            part = im.resize((max(1, int(w)), max(1, int(h))), Image.Resampling.NEAREST)
            px, py = X0, Y0
        if part.mode == "RGBA":
            part = self._on_checker(part)
        self.photo = ImageTk.PhotoImage(part)
        c.create_image(int(round(px)), int(round(py)), image=self.photo, anchor="nw")
        c.create_rectangle(int(X0) - 1, int(Y0) - 1, int(X0 + w), int(Y0 + h), outline="#444")
        self._readout(S(8), ch - S(8), "", im, k)
        if self.preview_tag:
            c.create_text(S(8), S(8), anchor="nw", fill="#ffd000", font=("Segoe UI", F(10)),
                          text=self.preview_tag)
        self.zoom_label.configure(text=f"Zoom: {k}x" if self.zoom else
                                  (f"Zoom: fit ({k}x)" if k >= 1 else "Zoom: fit"))

    def _on_checker(self, im):
        n = S(8)
        w, h = im.size
        yy, xx = np.mgrid[0:h, 0:w]
        chk = ((xx // n + yy // n) & 1).astype(bool)
        bg = np.where(chk[..., None], np.uint8(102), np.uint8(70))
        bg = np.repeat(bg, 3, axis=2).astype(np.uint8)
        base = Image.fromarray(bg, "RGB").convert("RGBA")
        return Image.alpha_composite(base, im).convert("RGB")

    # ---------------- zoom / pan ----------------
    def _fit_k(self):
        im = self.preview_img
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.compare and self.mode == "preview" and self.raw_src is not None:
            cw = max(1, (cw - S(12)) // 2)
        k = min(cw / im.width, ch / im.height)
        return max(1, int(k)) if k >= 1 else k

    def _zoom_k(self):
        return self.zoom if self.zoom else self._fit_k()

    def _clamp_pan(self, w, h, cw, ch):
        mx = max(0.0, (w - cw) / 2)
        my = max(0.0, (h - ch) / 2)
        self.pan[0] = min(max(self.pan[0], -mx), mx)
        self.pan[1] = min(max(self.pan[1], -my), my)

    def _zoom_fit(self):
        self.zoom = None
        self.pan = [0.0, 0.0]
        self.ozoom = None
        self.opan = [0.0, 0.0]
        self._redraw()

    def _zoom_step(self, e, up, steps=1):
        if self.preview_img is None:
            return
        old = self._zoom_k()
        if up:
            cap = max(MAX_ZOOM, int(old))          # tiny images can fit above MAX_ZOOM
            new = min(cap, int(old) + steps if old >= 1 else 1)
        else:
            new = int(old) - steps if old >= 1 else old
            if new < 1:
                return self._zoom_fit()
        if new == old:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        ux = (e.x - cw / 2 - self.pan[0]) / old
        uy = (e.y - ch / 2 - self.pan[1]) / old
        self.zoom = new
        self.pan = [e.x - cw / 2 - ux * new, e.y - ch / 2 - uy * new]
        self._redraw()

    def _c_double(self, e):
        if self.mode != "preview":
            return
        if self._comparing() and self._pane_at(e.x) == "orig":
            self.ozoom, self.opan = None, [0.0, 0.0]
            self._redraw()
        elif self._comparing():
            self.zoom, self.pan = None, [0.0, 0.0]
            self._redraw()
        else:
            self._zoom_fit()

    def _pan_start(self, e):
        if self.mode == "preview" and self.preview_img is not None:
            which = self._pane_at(e.x) if self._comparing() else "res"
            pan = self.opan if which == "orig" else self.pan
            self.pan_drag = (e.x, e.y, pan[0], pan[1], which)
            self.canvas.configure(cursor="fleur")

    def _pan_move(self, e):
        if self.pan_drag:
            sx, sy, px, py, which = self.pan_drag
            new = [px + e.x - sx, py + e.y - sy]
            if which == "orig":
                self.opan = new
            else:
                self.pan = new
            self._redraw()

    def _pan_end(self, e):
        self.pan_drag = None
        if self.mode == "preview":
            self.canvas.configure(cursor="")

    # ---------------- compare: original | result, each its own viewer ----------------
    def _comparing(self):
        return bool(self.compare and self.mode == "preview" and self.raw_src is not None
                    and self.preview_img is not None)

    def _toggle_compare(self):
        self.compare = not self.compare
        self.btn_compare.configure(text="Compare: On" if self.compare else "Compare: Off")
        self.zoom, self.pan = None, [0.0, 0.0]        # the result pane changes width: refit
        self.ozoom, self.opan = None, [0.0, 0.0]
        self._redraw()

    def _panes(self):
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        gap = S(12)
        half = (cw - gap) / 2
        return {"orig": (0.0, 0.0, half, float(ch)), "res": (half + gap, 0.0, float(cw), float(ch))}

    def _pane_at(self, x):
        return "orig" if x < self._panes()["res"][0] else "res"

    @staticmethod
    def _fit_for(img, pw, ph):
        k = min(pw / img.width, ph / img.height)
        return max(1, int(k)) if k >= 1 else k

    @staticmethod
    def _clamp(pan, w, h, pw, ph):
        mx, my = max(0.0, (w - pw) / 2), max(0.0, (h - ph) / 2)
        pan[0] = min(max(pan[0], -mx), mx)
        pan[1] = min(max(pan[1], -my), my)

    def _pane_view(self, which):
        """-> (image, zoom k, pan list, pane rect)."""
        rect = self._panes()[which]
        img = self._original_img() if which == "orig" else self.preview_img
        zoom, pan = (self.ozoom, self.opan) if which == "orig" else (self.zoom, self.pan)
        k = zoom if zoom else self._fit_for(img, rect[2] - rect[0], rect[3] - rect[1])
        return img, k, pan, rect

    def _zoom_pane(self, which, e, up, steps):
        img, old, pan, rect = self._pane_view(which)
        if up:
            new = min(max(MAX_ZOOM, int(old)), int(old) + steps if old >= 1 else 1)
        else:
            new = int(old) - steps if old >= 1 else old
            if new < 1:
                new = None
        if new == old:
            return
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        if new is None:
            npan = [0.0, 0.0]
        else:
            ux, uy = (e.x - cx - pan[0]) / old, (e.y - cy - pan[1]) / old
            npan = [e.x - cx - ux * new, e.y - cy - uy * new]
        if which == "orig":
            self.ozoom, self.opan = new, npan
        else:
            self.zoom, self.pan = new, npan
        self._redraw()

    @staticmethod
    def _kfmt(k):
        return f"{k:g}" if k >= 1 else f"{k:.2f}"

    def _readout(self, x, y, label, im, k):
        """Image size and zoom, bottom-left of a view."""
        if label == "Original":
            txt = f"{im.width} \u00d7 {im.height} px \u00b7 {self._kfmt(k)}\u00d7"
        else:
            txt = (f"{OUT_W} \u00d7 {OUT_H} px"
                   + ("" if im.size == (OUT_W, OUT_H) else f" (shown {im.width} \u00d7 {im.height})")
                   + f" \u00b7 {self._kfmt(k)}\u00d7")
        if label:
            txt = f"{label}   {txt}"
        c = self.canvas
        c.create_text(x + 1, y + 1, anchor="sw", fill="#000", font=("Segoe UI", F(10)), text=txt)
        c.create_text(x, y, anchor="sw", fill="#ffd000", font=("Segoe UI", F(10)), text=txt)

    def _original_box(self):
        """The part of the source the result shows: the title crop."""
        return self.crop

    def _original_img(self):
        box = tuple(int(round(v)) for v in self._original_box())
        key = (id(self.raw_src), box)
        if self._orig_cache is None or self._orig_cache[0] != key:
            self._orig_cache = (key, self.raw_src.crop(box))
        return self._orig_cache[1]

    def _blit(self, im, X0, Y0, w, h, clip, smooth):
        """Draw im scaled into the rect (X0, Y0, w, h), only the part inside clip."""
        cx0, cy0, cx1, cy1 = clip
        vx0, vy0 = max(X0, cx0), max(Y0, cy0)
        vx1, vy1 = min(X0 + w, cx1), min(Y0 + h, cy1)
        dw, dh = int(round(vx1 - vx0)), int(round(vy1 - vy0))
        if dw < 1 or dh < 1:
            return
        sx, sy = im.width / w, im.height / h
        box = ((vx0 - X0) * sx, (vy0 - Y0) * sy, (vx1 - X0) * sx, (vy1 - Y0) * sy)
        if smooth:
            part = im.resize((dw, dh), Image.Resampling.BILINEAR, box=box, reducing_gap=2.0)
        else:
            part = im.resize((dw, dh), Image.Resampling.NEAREST, box=box)
        if part.mode == "RGBA":
            part = self._on_checker(part)
        ph = ImageTk.PhotoImage(part)
        self._cmp_photos.append(ph)
        self.canvas.create_image(int(round(vx0)), int(round(vy0)), image=ph, anchor="nw")

    def _draw_compare(self, im, cw, ch):
        c = self.canvas
        self._cmp_photos = []
        for which, label in (("orig", "Original"), ("res", "Result")):
            img, k, pan, rect = self._pane_view(which)
            x0, y0, x1, y1 = rect
            pw, ph = x1 - x0, y1 - y0
            w, h = img.width * k, img.height * k
            self._clamp(pan, w, h, pw, ph)
            X0 = x0 + pw / 2 + pan[0] - w / 2
            Y0 = y0 + ph / 2 + pan[1] - h / 2
            self._blit(img, X0, Y0, w, h, rect, smooth=k < 1)
            c.create_rectangle(max(x0, int(X0) - 1), max(y0, int(Y0) - 1), min(x1, int(X0 + w)),
                               min(y1, int(Y0 + h)), outline="#444")
            if which == "res":
                self.zoom_label.configure(text=f"Zoom: {self._kfmt(k)}x" if self.zoom
                                          else f"Zoom: fit ({self._kfmt(k)}x)")
            c.create_text(x0 + S(8), y0 + S(8), anchor="nw", fill="#ffd000", font=("Segoe UI", F(10)),
                          text=label if which == "orig" else (self.preview_tag or label))
            self._readout(x0 + S(8), y1 - S(8), label, img, k)
        mid = self._panes()["res"][0] - S(6)
        c.create_line(mid, 0, mid, ch, fill="#555", width=2)

    # ---------------- crop mode ----------------
    def _crop_geom(self, cw, ch):
        sw, sh = self.src.size
        pad = S(16)
        s = min((cw - pad * 2) / sw, (ch - pad * 2) / sh)
        s = max(s, 0.01)
        dw, dh = int(sw * s), int(sh * s)
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        return s, ox, oy, dw, dh

    def _draw_crop(self, cw, ch):
        c = self.canvas
        s, ox, oy, dw, dh = self._crop_geom(cw, ch)
        if self.crop_disp is None or self.crop_disp[0] != (dw, dh):
            resample_f = Image.Resampling.LANCZOS if s < 1 else Image.Resampling.NEAREST
            dim = self.src.resize((max(1, dw), max(1, dh)), resample_f, reducing_gap=3.0 if s < 1 else None)
            self.crop_disp = ((dw, dh), ImageTk.PhotoImage(dim))
        c.create_image(ox, oy, image=self.crop_disp[1], anchor="nw")
        x0, y0, x1, y1 = self.tmp_crop
        X0, Y0, X1, Y1 = ox + x0 * s, oy + y0 * s, ox + x1 * s, oy + y1 * s
        for r in ((ox, oy, ox + dw, Y0), (ox, Y1, ox + dw, oy + dh), (ox, Y0, X0, Y1), (X1, Y0, ox + dw, Y1)):
            if r[2] > r[0] and r[3] > r[1]:
                c.create_rectangle(*r, fill="#000", stipple="gray50", outline="")
        for i in (1, 2):
            xx = X0 + (X1 - X0) * i / 3
            yy = Y0 + (Y1 - Y0) * i / 3
            c.create_line(xx, Y0, xx, Y1, fill="#ffffff", dash=(3, 4))
            c.create_line(X0, yy, X1, yy, fill="#ffffff", dash=(3, 4))
        c.create_rectangle(X0, Y0, X1, Y1, outline="#ffd000", width=S(2))
        Xm, Ym = (X0 + X1) / 2, (Y0 + Y1) / 2
        for hx, hy in ((X0, Y0), (X1, Y0), (X0, Y1), (X1, Y1)):
            c.create_rectangle(hx - HANDLE / 2, hy - HANDLE / 2, hx + HANDLE / 2, hy + HANDLE / 2,
                               fill="#ffd000", outline="#000")
        e = HANDLE * 0.4                      # smaller handles mid-edge
        for hx, hy in ((Xm, Y0), (Xm, Y1), (X0, Ym), (X1, Ym)):
            c.create_rectangle(hx - e, hy - e, hx + e, hy + e, fill="#ffd000", outline="#000")
        w, h = x1 - x0, y1 - y0
        txt = f"{w:.0f}x{h:.0f} at ({x0:.0f}, {y0:.0f})  ->  {OUT_W}x{OUT_H}  ({DISP_H / h:.3f}x)"
        if h < DISP_H:
            txt += "   UPSCALING"
        self.crop_info.configure(text=txt)

    def _enter_crop(self):
        if self.src is None or self.mode != "preview":
            return
        self.mode = "crop"
        self.tmp_crop = self.crop
        self.cropbar.pack(side="left")
        self.btn_crop.state(["disabled"])
        self._redraw()

    def _leave_crop(self):
        self.mode = "preview"
        self.cropbar.pack_forget()
        self.btn_crop.state(["!disabled"])
        self.canvas.configure(cursor="")
        self._redraw()

    def _crop_ok(self):
        if self.mode != "crop":
            return
        self.crop = self.tmp_crop
        self._leave_crop()
        self.status.configure(text=self._src_text())
        self.schedule(10)

    def _crop_cancel(self):
        if self.mode != "crop":
            return
        self._leave_crop()

    def _crop_max(self):
        if self.mode == "crop":
            self.tmp_crop = max_crop(*self.src.size, CROP_RATIO)
            self._redraw()

    def _to_src(self, e):
        s, ox, oy, _, _ = self._crop_geom(self.canvas.winfo_width(), self.canvas.winfo_height())
        return (e.x - ox) / s, (e.y - oy) / s, s

    def _hit(self, e):
        mx, my, s = self._to_src(e)
        x0, y0, x1, y1 = self.tmp_crop
        tol = (HANDLE + S(4)) / s
        for name, hx, hy in (("tl", x0, y0), ("tr", x1, y0), ("bl", x0, y1), ("br", x1, y1)):
            if abs(mx - hx) <= tol and abs(my - hy) <= tol:
                return name
        etol = S(6) / s                       # the whole length of each edge is grabbable
        inx, iny = x0 - etol <= mx <= x1 + etol, y0 - etol <= my <= y1 + etol
        if iny and abs(mx - x0) <= etol:
            return "l"
        if iny and abs(mx - x1) <= etol:
            return "r"
        if inx and abs(my - y0) <= etol:
            return "t"
        if inx and abs(my - y1) <= etol:
            return "b"
        if x0 <= mx <= x1 and y0 <= my <= y1:
            return "move"
        return None

    def _c_motion(self, e):
        if self.mode != "crop" or self.drag:
            return
        h = self._hit(e)
        cur = {"tl": "size_nw_se", "br": "size_nw_se", "tr": "size_ne_sw", "bl": "size_ne_sw",
               "l": "sb_h_double_arrow", "r": "sb_h_double_arrow",
               "t": "sb_v_double_arrow", "b": "sb_v_double_arrow",
               "move": "fleur"}.get(h, "")
        try:
            self.canvas.configure(cursor=cur)
        except tk.TclError:
            self.canvas.configure(cursor="sizing" if h and h != "move" else ("fleur" if h else ""))

    def _c_press(self, e):
        if self.mode != "crop":
            self._pan_start(e)
            return
        h = self._hit(e)
        if not h:
            self.drag = None
            return
        mx, my, _ = self._to_src(e)
        self.drag = (h, mx, my, self.tmp_crop)

    def _c_drag(self, e):
        if self.mode != "crop":
            self._pan_move(e)
            return
        if not self.drag:
            return
        h, sx, sy, (x0, y0, x1, y1) = self.drag
        mx, my, _ = self._to_src(e)
        sw, sh = self.src.size
        if h == "move":
            w, hh = x1 - x0, y1 - y0
            nx = min(max(0.0, x0 + mx - sx), sw - w)
            ny = min(max(0.0, y0 + my - sy), sh - hh)
            self.tmp_crop = (nx, ny, nx + w, ny + hh)
        elif h in ("l", "r", "t", "b"):
            # one side moves, the other axis follows to keep 426:240, centred
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if h in ("l", "r"):
                ax = x1 if h == "l" else x0
                w = max((ax - mx) if h == "l" else (mx - ax), 0.0)
                maxw = ax if h == "l" else sw - ax
                maxh = 2.0 * min(cy, sh - cy)
                w = min(w, maxw, maxh * CROP_RATIO)
                w = max(w, min(16.0, maxw, maxh * CROP_RATIO))
                hh = w / CROP_RATIO
                nx0 = ax - w if h == "l" else ax
                self.tmp_crop = (nx0, cy - hh / 2, nx0 + w, cy + hh / 2)
            else:
                ay = y1 if h == "t" else y0
                hh = max((ay - my) if h == "t" else (my - ay), 0.0)
                maxh = ay if h == "t" else sh - ay
                maxw = 2.0 * min(cx, sw - cx)
                hh = min(hh, maxh, maxw / CROP_RATIO)
                hh = max(hh, min(16.0 / CROP_RATIO, maxh, maxw / CROP_RATIO))
                w = hh * CROP_RATIO
                ny0 = ay - hh if h == "t" else ay
                self.tmp_crop = (cx - w / 2, ny0, cx + w / 2, ny0 + hh)
        else:
            ax = x1 if "l" in h else x0
            ay = y1 if "t" in h else y0
            dx = -1 if "l" in h else 1
            dy = -1 if "t" in h else 1
            w = max((mx - ax) * dx, 0.0)
            hh = max((my - ay) * dy, 0.0)
            w = max(w, hh * CROP_RATIO)
            maxw = ax if dx < 0 else sw - ax
            maxh = ay if dy < 0 else sh - ay
            w = min(w, maxw, maxh * CROP_RATIO)
            w = max(w, min(16.0, maxw, maxh * CROP_RATIO))
            hh = w / CROP_RATIO
            nx0 = ax if dx > 0 else ax - w
            ny0 = ay if dy > 0 else ay - hh
            self.tmp_crop = (nx0, ny0, nx0 + w, ny0 + hh)
        self._redraw()

    def _c_release(self, e):
        self.drag = None
        if self.mode != "crop":
            self._pan_end(e)

    def _c_wheel(self, e):
        if self.mode != "crop":
            steps = 1 if (e.state & 0x0001) else ZOOM_STEPS
            if self._comparing():
                self._zoom_pane(self._pane_at(e.x), e, e.delta > 0, steps)
            else:
                self._zoom_step(e, e.delta > 0, steps)
            return
        f = 0.95 if e.delta > 0 else 1.0 / 0.95
        x0, y0, x1, y1 = self.tmp_crop
        sw, sh = self.src.size
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w = (x1 - x0) * f
        w = min(max(w, 16.0), sw, sh * CROP_RATIO)
        h = w / CROP_RATIO
        nx = min(max(0.0, cx - w / 2), sw - w)
        ny = min(max(0.0, cy - h / 2), sh - h)
        self.tmp_crop = (nx, ny, nx + w, ny + h)
        self._redraw()


def run_gui(args):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    dpi_init(root)
    global HANDLE
    HANDLE = S(10)
    App(root, args)
    root.mainloop()


# ==========================================================================
#  Entry
# ==========================================================================
def main():
    args = parse_args(sys.argv[1:])
    check_deps(need_tk=True)
    run_gui(args)


if __name__ == "__main__":
    main()
