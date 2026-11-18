#!/usr/bin/env python3
"""doompal - Doom palette and colourmap tool (Standalone Version)"""
import sys
import os
import struct
import zlib
import base64
import operator
from pathlib import Path

__version__ = "1.3.0"

# ============================================================================
# DEPENDENCY CHECK
# ============================================================================

try:
    from PIL import Image
except ImportError:
    print("doompal: missing dependency 'Pillow'.", file=sys.stderr)
    print("Install it with:  python -m pip install pillow", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# CONSTANTS
# ============================================================================

COLORS = 256
BYTES_PER_COLOR = 3
BYTES_PER_PALETTE = COLORS * BYTES_PER_COLOR          # 768
PALETTES_PER_PLAYPAL = 14
PLAYPAL_SIZE_BYTES = PALETTES_PER_PLAYPAL * BYTES_PER_PALETTE  # 10752

COLORMAP_ROWS = 34
COLORMAP_SIZE_BYTES = COLORS * COLORMAP_ROWS          # 8704
COLORMAP_ROWS_OK = (32, 33, 34)                       # accepted raw lump heights
NUMLIGHTS = 32

GRID_SIZE = 16          # 16x16 = 256 colours
SLADE_DEFAULT_CELL = 8  # 128x128 grid

STRIP_ROWS = (1, 14, 32, 33, 34)   # 256-wide PNG heights read as strips (row 0 = pal0)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

GENERATE_BASE = "genDoom"

# Tint table for PLAYPAL rows 1-13: (tint colour, amount)
TINTS = [
    None,
    ((252, 2, 3), 0.11),
    ((255, 0, 0), 0.22),
    ((255, 0, 0), 0.33),
    ((255, 0, 0), 0.44),
    ((255, 0, 0), 0.55),
    ((255, 0, 0), 0.66),
    ((255, 0, 0), 0.77),
    ((255, 0, 0), 0.88),
    ((215, 185, 68), 0.12),
    ((215, 185, 68), 0.25),
    ((215, 185, 68), 0.375),
    ((215, 185, 68), 0.50),
    ((3, 253, 3), 0.125),
]


# ============================================================================
# EMBEDDED DOOM DATA (PLAYPAL 10752 bytes, COLORMAP 8704 bytes; zlib+base64)
# ============================================================================

_DOOM_PLAYPAL_Z = """
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
"""

_DOOM_COLORMAP_Z = """
eNrl2Gl0VOUZB/A7N8zcG0gmgiAgSwARwQxMpahFUdaQDWayT5bJNpnJnkw3rVtNIBCyEMgOyFbI
drrZxbWtPafVSqsInNZKraV6Wq1iyHIggVOtkD7P8y5zJ0Db770fNGHeufP+7v//vvdOFJMaMsls
0fTQyVPCwq0Rt0ydduv0GbfNnDX79jlz582PXLBw0R2L71xy19Jld0fZlq+wf+melV9ede99939l
9QMPrnno4bXr1m/YuCl6c0xsXHzClq0OZ2JSckpqWrorIzMr252Tm5df4Cn0+oqKS0rLyisqq/xf
/drXv/HNRx791mOPP/HkU99+urpm2/baHTvrdtU3NDbtbt6zt6W1rb2js2vf/gPPHDx0+MjR7xw7
3t3T29c/6bvf+/4Pfvjsj378k58+9/wLL7708s9+/otXfrnc/qtfv/rab14/8dvfvfHmybdOnT4z
6fd/ePuP75z907t/fu8v5/76/geT/vb3Dz/6x8efnP904MLg0PDImYuXRscuX1H++dnn//ri6rVx
ZYKf+DNmzpo1ew74IyMXSn8U+Tn/fsFft2Ej+GOkfwI/r6DA4/X6iotDbuJn/Lr6+kb07w2/uf8W
5gf+f/Tfs+q+1eAHPvg/OP8/+EsThX+Q/DNuFr9thR3994J/NfOvC4p/H/gZ34V8d05eIP6QsrIK
9Et+kF/GH17X1tjU3GndCnzwHz36Efcnrpw6Hf3G+F+BPJK5H/jkT1y56v4H3jn77nss/vOJ94D/
s48/+XRg4II1IuA/e0z6y5KEHwYY2g/+BQsWgX8J+W3kT4H4p05bHdT+6M2xzO9wOgPp8/Z7vD5f
UQmrf6Xfb4wf/YLf0IT+8PBdbe27OwfJj/GHIh/9SanTpt8GfuLL+FfYU159TfjfOnXq9MWk1HtX
P7jmLLb/HPA/TVq56sNjx9B/oR/9Fy9d7082+Kn94Ce+iH/J0qUUP/hT06ZCRW4V/PUbNrH4ef2d
wfx8j4i/tJzqb0a+0V9bu6NuF48f6o/+DvIfDPiB35+cNm3GzNncD3zhT4X4pf/0mYvJqVNXP/jQ
Wmo/+pNT3z6G/gHyO8E/Sv6Hj3/+xdWr1+oVVS1LMfoZX7Z/0WIWfxSrvz093VVTUzMd+ND+9Ruo
/Sz+Lqy/Sa59Sp+1v6g4JKSsvLxS+IHPlz/4Zfup/tb6xiZc/hEQf5A/Jf3WGbNuf/Y54vP6w/K3
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
"""


def _embedded(blob, expected):
    data = zlib.decompress(base64.b64decode("".join(blob.split())))
    if len(data) != expected:
        raise RuntimeError("Embedded Doom data is corrupt")
    return data


def doom_playpal_bytes():
    return _embedded(_DOOM_PLAYPAL_Z, PLAYPAL_SIZE_BYTES)


def doom_colormap_bytes():
    return _embedded(_DOOM_COLORMAP_Z, COLORMAP_SIZE_BYTES)


# ============================================================================
# ERRORS
# ============================================================================

class UsageError(Exception):
    """Bad command line - prints a pointer to the command's help."""


class InputError(Exception):
    """Input file can't be used."""


# ============================================================================
# COLOUR MATCHING
# ============================================================================

def best_color(r, g, b, palette):
    """Index of the nearest palette colour (Euclidean RGB, lowest index wins ties)."""
    best_dist = None
    best_index = 0
    for i, (pr, pg, pb) in enumerate(palette):
        dr = r - pr
        dg = g - pg
        db = b - pb
        dist = dr * dr + dg * dg + db * db
        if dist == 0:
            return i
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_index = i
    return best_index


# ============================================================================
# PALETTE GENERATION
# ============================================================================

def _clamp8(x):
    if x < 0:
        return 0
    if x > 255:
        return 255
    return int(round(x))


def _blend(src, tint, amount):
    sr, sg, sb = src
    tr, tg, tb = tint
    return (
        _clamp8(sr * (1.0 - amount) + tr * amount),
        _clamp8(sg * (1.0 - amount) + tg * amount),
        _clamp8(sb * (1.0 - amount) + tb * amount),
    )


def expand_palette_to_14(pal0):
    """
    Approximate the 14 Doom palettes from pal0:
      0 normal, 1-8 red (damage/berserk), 9-12 yellow (bonus), 13 green (radsuit)
    """
    if len(pal0) != COLORS:
        raise ValueError("pal0 must have 256 colours")
    palettes = [list(pal0)]
    for row in range(1, PALETTES_PER_PLAYPAL):
        tint, amount = TINTS[row]
        palettes.append([_blend(c, tint, amount) for c in pal0])
    return palettes


def palettes_from_bytes(data):
    """Split raw palette bytes (768 * n) into a list of palettes."""
    if len(data) % BYTES_PER_PALETTE != 0 or len(data) == 0:
        raise InputError(f"Invalid palette data size: {len(data)} bytes")
    out = []
    for p in range(len(data) // BYTES_PER_PALETTE):
        base = p * BYTES_PER_PALETTE
        out.append([tuple(data[base + i * 3: base + i * 3 + 3]) for i in range(COLORS)])
    return out


def palettes_to_bytes(palettes):
    return b"".join(bytes(c) for pal in palettes for c in pal)


# ============================================================================
# COLOURMAP GENERATION
# ============================================================================

def generate_colormap(palette, with_lighting=True):
    """
    34-row colourmap (list of rows of indices).
      rows 0-31 : lighting (identity rows when with_lighting=False)
      row 32    : invulnerability (inverse greyscale)
      row 33    : black
    """
    colormap = []
    if with_lighting:
        for level in range(NUMLIGHTS):
            row = []
            for r, g, b in palette:
                nr = (r * (NUMLIGHTS - level) + NUMLIGHTS // 2) // NUMLIGHTS
                ng = (g * (NUMLIGHTS - level) + NUMLIGHTS // 2) // NUMLIGHTS
                nb = (b * (NUMLIGHTS - level) + NUMLIGHTS // 2) // NUMLIGHTS
                row.append(best_color(nr, ng, nb, palette))
            colormap.append(row)
    else:
        for _ in range(NUMLIGHTS):
            colormap.append(list(range(COLORS)))

    invuln = []
    for r, g, b in palette:
        # 0.144 blue weight matches id's original dcolors.c
        gray = 1.0 - (r / 255.0 * 0.299 + g / 255.0 * 0.587 + b / 255.0 * 0.144)
        gv = int(gray * 255)
        invuln.append(best_color(gv, gv, gv, palette))
    colormap.append(invuln)

    colormap.append([best_color(0, 0, 0, palette)] * COLORS)
    return colormap


def colormap_rows_from_bytes(data):
    rows = len(data) // COLORS
    return [list(data[r * COLORS:(r + 1) * COLORS]) for r in range(rows)]


# ============================================================================
# IMAGE WRITERS
# ============================================================================

def save_palettes_png(palettes, path):
    """Write palettes as a 256 x N strip PNG (DoomTools style)."""
    img = Image.new("RGB", (COLORS, len(palettes)))
    img.putdata([c for pal in palettes for c in pal])
    img.save(path)


def save_colormap_png(colormap, palette, path):
    """Write colourmap index rows as an RGB PNG using palette."""
    img = Image.new("RGB", (COLORS, len(colormap)))
    img.putdata([palette[idx] for row in colormap for idx in row])
    img.save(path)


def save_slade_grid(pal, path, cell):
    """Write a SLADE-style 16x16 grid PNG."""
    size = GRID_SIZE * cell
    img = Image.new("RGB", (size, size))
    for i, colour in enumerate(pal):
        x0 = (i % GRID_SIZE) * cell
        y0 = (i // GRID_SIZE) * cell
        img.paste(colour, (x0, y0, x0 + cell, y0 + cell))
    img.save(path)


def save_split_png(path):
    """Write the 256x14 RGBA tint overlay (row 0 transparent)."""
    img = Image.new("RGBA", (COLORS, PALETTES_PER_PLAYPAL), (0, 0, 0, 0))
    for row in range(1, PALETTES_PER_PLAYPAL):
        (r, g, b), amount = TINTS[row]
        img.paste((r, g, b, int(amount * 255)), (0, row, COLORS, row + 1))
    img.save(path)


# ============================================================================
# CUBE LUT
# ============================================================================

def write_cube(palette, output_path, title=None, lut_size=64):
    """
    Write a .cube LUT: every point of a 64^3 RGB lattice snapped to its
    nearest palette colour. (Equivalent to remapping a HALD:8 identity
    CLUT and converting it - the lattice is computed directly.)
    """
    n = lut_size
    levels = [round(i * 255 / (n - 1)) for i in range(n)]

    dr = [[(lv - c[0]) ** 2 for c in palette] for lv in levels]
    dg = [[(lv - c[1]) ** 2 for c in palette] for lv in levels]
    db = [[(lv - c[2]) ** 2 for c in palette] for lv in levels]

    # channel value -> text, via float32 like the original numpy path
    f32 = ["%.6f" % struct.unpack("<f", struct.pack("<f", v / 255.0))[0]
           for v in range(256)]
    pal_str = [f"{f32[r]} {f32[g]} {f32[b]}" for (r, g, b) in palette]

    add = operator.add
    lines = []
    for bi in range(n):
        dbb = db[bi]
        for gi in range(n):
            s = list(map(add, dg[gi], dbb))
            for ri in range(n):
                d = list(map(add, dr[ri], s))
                lines.append(pal_str[d.index(min(d))])

    if title is None:
        title = Path(output_path).stem
    with open(output_path, "w", newline="\n") as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {n}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        f.write("\n".join(lines))
        f.write("\n")


# ============================================================================
# WAD READER
# ============================================================================

class WADFile:
    """Minimal WAD reader. Later lumps with the same name win (Doom rules)."""

    def __init__(self, path):
        self.path = Path(path)
        self.directory = []   # [(name, filepos, size)] in WAD order
        with open(self.path, "rb") as f:
            magic = f.read(4)
            if magic not in (b"IWAD", b"PWAD"):
                raise InputError(f"Not a valid WAD file: {path}")
            numlumps, diroffset = struct.unpack("<II", f.read(8))
            f.seek(diroffset)
            raw = f.read(16 * numlumps)
        if len(raw) < 16 * numlumps:
            raise InputError(f"Truncated WAD directory: {path}")
        for i in range(numlumps):
            filepos, size, name = struct.unpack_from("<II8s", raw, i * 16)
            name = name.split(b"\x00")[0].decode("ascii", errors="ignore").upper()
            self.directory.append((name, filepos, size))

    def _find(self, name):
        name = name.upper()
        for entry in reversed(self.directory):
            if entry[0] == name:
                return entry
        return None

    def has_lump(self, name):
        return self._find(name) is not None

    def read_lump(self, name):
        entry = self._find(name)
        if entry is None:
            return None
        return self._read(entry)

    def _read(self, entry):
        _, filepos, size = entry
        with open(self.path, "rb") as f:
            f.seek(filepos)
            return f.read(size)

    def boom_colormaps(self):
        """[(name, data)] for every lump between C_START and C_END."""
        out = []
        inside = False
        for entry in self.directory:
            name = entry[0]
            if name in ("C_START", "CC_START"):
                inside = True
                continue
            if name in ("C_END", "CC_END"):
                inside = False
                continue
            if inside and entry[2] > 0:
                out.append((name, self._read(entry)))
        return out


# ============================================================================
# INPUT LOADING (every command goes through load_source)
# ============================================================================

class Source:
    """Everything a command might need from one input."""

    def __init__(self, path, label, pal0, palettes=None,
                 colormap=None, colormap_pal=None, wad=None):
        self.path = path
        self.label = label                # human-readable input type
        self.pal0 = pal0                  # 256 (r,g,b)
        self.palettes = palettes          # 14 palettes if the input has them, else None
        self.colormap = colormap          # raw colourmap index bytes, if input carries one
        self.colormap_pal = colormap_pal  # palette those indices refer to
        self.wad = wad                    # WADFile, for WAD inputs


def classify(path):
    """Return (kind, info). Detection is by content, never by extension."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"File not found: {p}")
    with open(p, "rb") as f:
        head = f.read(8)

    if head == PNG_SIGNATURE:
        with Image.open(p) as im:
            w, h = im.size
        if w >= COLORS and w % COLORS == 0:
            scale = w // COLORS
            if h % scale == 0 and (h // scale) in STRIP_ROWS:
                return "strip", h // scale
        if w % GRID_SIZE == 0 and h % GRID_SIZE == 0:
            return "grid", (w, h)
        raise InputError(f"{p.name}: PNG {w}x{h} is not a recognised palette layout")

    if head[:4] in (b"IWAD", b"PWAD"):
        return "wad", None
    if head.startswith(b"JASC-PAL"):
        return "jasc", None

    size = p.stat().st_size
    if size == PLAYPAL_SIZE_BYTES:
        return "playpal", None
    if size == BYTES_PER_PALETTE:
        return "pal0", None
    if size % COLORS == 0 and (size // COLORS) in COLORMAP_ROWS_OK:
        return "cmap", size // COLORS
    raise InputError(f"{p.name}: unrecognised file ({size} bytes)")


def _png_rgb(path):
    with Image.open(path) as im:
        return im.convert("RGB")


def _read_strip(path):
    img = _png_rgb(path)
    w, h = img.size
    scale = w // COLORS
    rows = h // scale
    if scale != 1:
        img = img.resize((COLORS, rows), Image.NEAREST)
    raw = img.tobytes()
    data = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    return [data[r * COLORS:(r + 1) * COLORS] for r in range(rows)]


def _read_grid(path):
    img = _png_rgb(path)
    w, h = img.size
    cw, ch = w // GRID_SIZE, h // GRID_SIZE
    px = img.load()
    return [px[gx * cw + cw // 2, gy * ch + ch // 2]
            for gy in range(GRID_SIZE) for gx in range(GRID_SIZE)]


def _read_jasc(path):
    tokens = Path(path).read_text(errors="ignore").split()
    try:
        count = int(tokens[2])
        vals = [int(t) for t in tokens[3:3 + count * 3]]
    except (IndexError, ValueError):
        raise InputError(f"{Path(path).name}: malformed JASC-PAL file")
    pal = [tuple(vals[i:i + 3]) for i in range(0, len(vals) - 2, 3)][:COLORS]
    if len(pal) < COLORS:
        print(f"Warning: JASC palette has {len(pal)} colours, padding with black")
        pal += [(0, 0, 0)] * (COLORS - len(pal))
    return pal


def _cmap_needs_pal(name):
    return InputError(
        f"{name} is a raw colourmap (palette indices only, no colours).\n"
        f"       Supply the palette it belongs to:  -p <playpal/pal0 file>"
    )


def load_palette_only(pal_path):
    """Load the palette given with -p (anything but a raw colourmap)."""
    src = load_source(pal_path)
    return src.pal0


def load_source(path, pal_path=None):
    """Load any supported input. pal_path (-p) is used for raw colourmaps."""
    p = Path(path)
    kind, info = classify(p)

    if kind == "strip":
        rows = _read_strip(p)
        if info == PALETTES_PER_PLAYPAL:
            return Source(p, "256x14 PLAYPAL PNG", rows[0], palettes=rows)
        if info == 1:
            return Source(p, "256x1 pal0 PNG", rows[0])
        return Source(p, f"256x{info} colourmap PNG (row 0 = pal0)", rows[0])

    if kind == "grid":
        w, h = info
        return Source(p, f"SLADE grid PNG ({w}x{h})", _read_grid(p))

    if kind == "jasc":
        return Source(p, "JASC-PAL text palette", _read_jasc(p))

    if kind == "playpal":
        pals = palettes_from_bytes(p.read_bytes())
        return Source(p, "raw PLAYPAL (14 palettes)", pals[0], palettes=pals)

    if kind == "pal0":
        return Source(p, "raw single palette", palettes_from_bytes(p.read_bytes())[0])

    if kind == "cmap":
        if pal_path is None:
            raise _cmap_needs_pal(p.name)
        cpal = load_palette_only(pal_path)
        data = p.read_bytes()
        pal0 = [cpal[i] for i in data[:COLORS]]
        return Source(p, f"raw colourmap ({info} rows) via -p {Path(pal_path).name}",
                      pal0, colormap=data, colormap_pal=cpal)

    if kind == "wad":
        wad = WADFile(p)
        playpal = wad.read_lump("PLAYPAL")
        cmap = wad.read_lump("COLORMAP")
        if playpal:
            pals = palettes_from_bytes(playpal[:len(playpal) - len(playpal) % BYTES_PER_PALETTE])
            full = pals if len(pals) >= PALETTES_PER_PLAYPAL else None
            return Source(p, "WAD PLAYPAL", pals[0],
                          palettes=full[:PALETTES_PER_PLAYPAL] if full else None,
                          colormap=cmap, colormap_pal=pals[0], wad=wad)
        if cmap:
            if pal_path is None:
                raise InputError(
                    f"{p.name} has a COLORMAP but no PLAYPAL (indices only, no colours).\n"
                    f"       Supply the palette it belongs to:  -p <playpal/pal0 file>"
                )
            cpal = load_palette_only(pal_path)
            pal0 = [cpal[i] for i in cmap[:COLORS]]
            return Source(p, f"WAD COLORMAP via -p {Path(pal_path).name}", pal0,
                          colormap=cmap, colormap_pal=cpal, wad=wad)
        raise InputError(f"{p.name} contains neither PLAYPAL nor COLORMAP")

    raise InputError(f"Unsupported input: {p}")


# ============================================================================
# OUTPUT NAMING
# ============================================================================

def out_file(src_path, output, suffix, ext):
    """
    Single-file output.
      -o given : that name, ext added if missing
      no -o    : <input stem><suffix><ext> next to the input
    """
    if output:
        o = Path(output)
        if o.suffix.lower() != ext.lower():
            o = Path(str(o) + ext)
        return o
    sp = Path(src_path)
    return sp.parent / f"{sp.stem}{suffix}{ext}"


OUTPUT_EXTS = (".png", ".pal", ".cmp", ".cube", ".lmp")


def strip_output_ext(output):
    """Drop a known file extension from a -o base name (doom.png -> doom)."""
    o = Path(output)
    if o.suffix.lower() in OUTPUT_EXTS:
        o = o.with_suffix("")
    return str(o)


def out_base(src_path, output):
    """Base name for multi-file outputs (files are <base><suffix><ext>)."""
    if output:
        return strip_output_ext(output)
    sp = Path(src_path)
    return str(sp.parent / sp.stem)


def report(written, header="Wrote:"):
    print(header)
    for item in written:
        print(f"  {item}")


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_cube(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    out = out_file(src.path, o.output, "", ".cube")
    print("Building 64^3 LUT...")
    write_cube(src.pal0, out)
    report([out])
    return 0


def _playpal_rows(src):
    """Real 14 palettes if the input has them, otherwise tinted from pal0."""
    if src.palettes:
        return src.palettes, False
    return expand_palette_to_14(src.pal0), True


def cmd_batch(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    base = out_base(src.path, o.output)
    written = []

    print("Building .cube LUT...")
    p = Path(f"{base}.cube")
    write_cube(src.pal0, p)
    written.append(p)

    palettes, tinted = _playpal_rows(src)
    p = Path(f"{base}_playpal.png")
    save_palettes_png(palettes, p)
    written.append(f"{p}" + ("  (tints generated from pal0)" if tinted else "  (from input)"))

    p = Path(f"{base}_colormap.png")
    if src.colormap:
        save_colormap_png(colormap_rows_from_bytes(src.colormap), src.colormap_pal, p)
        written.append(f"{p}  (from input)")
    else:
        save_colormap_png(generate_colormap(src.pal0, True), src.pal0, p)
        written.append(f"{p}  (generated)")

    p = Path(f"{base}_playpal_blank.png")
    save_palettes_png([src.pal0] * PALETTES_PER_PLAYPAL, p)
    written.append(p)

    p = Path(f"{base}_colormap_blank.png")
    save_colormap_png(generate_colormap(src.pal0, False), src.pal0, p)
    written.append(p)

    p = Path(f"{base}_split.png")
    save_split_png(p)
    written.append(p)

    if src.wad is not None:
        for name, data in src.wad.boom_colormaps():
            if len(data) % COLORS:
                print(f"Warning: skipping Boom colourmap {name} (odd size {len(data)})")
                continue
            p = Path(f"{base}_{name}.png")
            save_colormap_png(colormap_rows_from_bytes(data), src.colormap_pal, p)
            written.append(f"{p}  (Boom colourmap)")

    report(written)
    return 0


def cmd_playpal(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    if o.blank:
        palettes = [src.pal0] * PALETTES_PER_PLAYPAL
        note = "blank: pal0 on every row"
    else:
        palettes, tinted = _playpal_rows(src)
        note = "tints generated from pal0" if tinted else "14 palettes from input"
    suffix = "_playpal_blank" if o.blank else "_playpal"
    if o.slade:
        out = out_file(src.path, o.output, suffix, ".pal")
        out.write_bytes(palettes_to_bytes(palettes))
    else:
        out = out_file(src.path, o.output, suffix, ".png")
        save_palettes_png(palettes, out)
    report([f"{out}  ({note})"])
    return 0


def cmd_colourmap(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    if o.blank:
        out = out_file(src.path, o.output, "_blank", ".png")
        cmap = generate_colormap(src.pal0, with_lighting=False)
    else:
        out = out_file(src.path, o.output, "_colormap", ".png")
        cmap = generate_colormap(src.pal0, with_lighting=True)
    save_colormap_png(cmap, src.pal0, out)
    report([out])
    return 0


def cmd_blank(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    base = out_base(src.path, o.output)
    p1 = Path(f"{base}_playpal_blank.png")
    save_palettes_png([src.pal0] * PALETTES_PER_PLAYPAL, p1)
    p2 = Path(f"{base}_colormap_blank.png")
    save_colormap_png(generate_colormap(src.pal0, False), src.pal0, p2)
    report([p1, p2])
    return 0


def cmd_slade(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    if o.playpal:
        palettes, tinted = _playpal_rows(src)
        out = out_file(src.path, o.output, "_playpal", ".pal")
        out.write_bytes(palettes_to_bytes(palettes))
        report([f"{out}  (" + ("tints generated from pal0" if tinted else "14 palettes from input") + ")"])
        return 0
    out = out_file(src.path, o.output, "_pal0", ".png")
    save_slade_grid(src.pal0, out, o.cell)
    size = GRID_SIZE * o.cell
    report([f"{out}  ({size}x{size})"])
    return 0


def cmd_extract(o):
    p = Path(o.input)
    kind, _ = classify(p)
    if kind != "wad":
        raise InputError(f"{p.name} is not a WAD - extract only reads WAD files")
    wad = WADFile(p)

    if o.boomlist:
        maps = wad.boom_colormaps()
        if maps:
            print("Boom colourmaps:")
            for name, data in maps:
                print(f"  {name:<8}  {len(data)} bytes ({len(data) // COLORS} rows)")
        else:
            print("No Boom colourmaps (no C_START/C_END markers)")
        return 0

    base = out_base(p, o.output)

    playpal = wad.read_lump("PLAYPAL")
    vis_pal = None
    if playpal and len(playpal) >= BYTES_PER_PALETTE:
        vis_pal = palettes_from_bytes(playpal[:len(playpal) - len(playpal) % BYTES_PER_PALETTE])[0]
    elif o.pal:
        vis_pal = load_palette_only(o.pal)

    if o.boom is None:            # default: everything
        want_main = True
        boom = wad.boom_colormaps()
    elif o.boom is True:          # --boom : all Boom maps only
        want_main = False
        boom = wad.boom_colormaps()
    else:                         # --boom NAME
        want_main = False
        boom = [(n, d) for n, d in wad.boom_colormaps() if n == o.boom.upper()]
        if not boom:
            data = wad.read_lump(o.boom)
            if data is None:
                raise InputError(f"Lump '{o.boom.upper()}' not found in {p.name}")
            boom = [(o.boom.upper(), data)]

    written = []
    skipped_png = False

    if want_main:
        if playpal:
            out = Path(f"{base}_playpal.pal")
            out.write_bytes(playpal)
            written.append(f"PLAYPAL  -> {out}")
            pals = palettes_from_bytes(playpal[:len(playpal) - len(playpal) % BYTES_PER_PALETTE])
            out = Path(f"{base}_playpal.png")
            save_palettes_png(pals, out)
            written.append(f"PLAYPAL  -> {out}")
        else:
            print("Warning: no PLAYPAL in WAD")

        cmap = wad.read_lump("COLORMAP")
        if cmap:
            out = Path(f"{base}_colormap.cmp")
            out.write_bytes(cmap)
            written.append(f"COLORMAP -> {out}")
            if vis_pal:
                out = Path(f"{base}_colormap.png")
                save_colormap_png(colormap_rows_from_bytes(cmap), vis_pal, out)
                written.append(f"COLORMAP -> {out}")
            else:
                skipped_png = True
        else:
            print("Warning: no COLORMAP in WAD")

    for name, data in boom:
        out = Path(f"{base}_{name}.cmp")
        out.write_bytes(data)
        written.append(f"{name:<8} -> {out}")
        if vis_pal and len(data) % COLORS == 0:
            out = Path(f"{base}_{name}.png")
            save_colormap_png(colormap_rows_from_bytes(data), vis_pal, out)
            written.append(f"{name:<8} -> {out}")
        elif not vis_pal:
            skipped_png = True

    if not written:
        print("Nothing extracted")
        return 1
    report(written, "Extracted:")
    if skipped_png:
        print("Note: colourmap PNGs skipped - WAD has no PLAYPAL (use -p <palette>)")
    return 0


def cmd_split(o):
    src = load_source(o.input, o.pal)
    print(f"Input : {src.path}  [{src.label}]")
    out = out_file(src.path, o.output, "_split", ".png")
    save_split_png(out)
    report([out])
    return 0


# generate output items: name -> filename suffix (appended to the base name)
GEN_ITEMS = [
    ("playpal",         "_playpal.png"),
    ("playpal-blank",   "_playpal_blank.png"),
    ("playpal-pal",     "_playpal.pal"),
    ("pal0",            "_pal0.png"),
    ("pal0-pal",        "_pal0.pal"),
    ("colourmap",       "_colormap.png"),
    ("colourmap-blank", "_colormap_blank.png"),
    ("colourmap-cmp",   "_colormap.cmp"),
    ("colourmap-cmp-blank", "_colormap_blank.cmp"),
    ("cube",            ".cube"),
]
GEN_ITEM_NAMES = [n for n, _ in GEN_ITEMS]


def normalise_gen_item(name):
    return name.lower().replace("colormap", "colourmap")


def cmd_generate(o):
    playpal = doom_playpal_bytes()
    cmap = doom_colormap_bytes()
    palettes = palettes_from_bytes(playpal)
    pal0 = palettes[0]
    wanted = set(o.items) if o.items else set(GEN_ITEM_NAMES)
    single = o.output and len(wanted) == 1   # -o is the full filename
    base = strip_output_ext(o.output) if o.output else GENERATE_BASE
    written = []

    for name, suffix in GEN_ITEMS:
        if name not in wanted:
            continue
        if single:
            ext = "." + suffix.rsplit(".", 1)[1]
            p = Path(o.output)
            if p.suffix.lower() != ext:
                p = Path(str(p) + ext)
        else:
            p = Path(f"{base}{suffix}")
        if name == "playpal":
            save_palettes_png(palettes, p)
        elif name == "playpal-blank":
            save_palettes_png([pal0] * PALETTES_PER_PLAYPAL, p)
        elif name == "playpal-pal":
            p.write_bytes(playpal)
        elif name == "pal0":
            save_slade_grid(pal0, p, SLADE_DEFAULT_CELL)
        elif name == "pal0-pal":
            p.write_bytes(playpal[:BYTES_PER_PALETTE])
        elif name == "colourmap":
            save_colormap_png(colormap_rows_from_bytes(cmap), pal0, p)
        elif name == "colourmap-blank":
            save_colormap_png(generate_colormap(pal0, False), pal0, p)
        elif name == "colourmap-cmp":
            p.write_bytes(cmap)
        elif name == "colourmap-cmp-blank":
            p.write_bytes(bytes(i for row in generate_colormap(pal0, False) for i in row))
        elif name == "cube":
            print("Building .cube LUT...")
            write_cube(pal0, p)
        written.append(p)

    report(written, "Generated Doom palette files:")
    return 0


# ============================================================================
# HELP
# ============================================================================

def _ansi_colors():
    """ANSI codes, or empty strings when output is piped/redirected."""
    if not sys.stdout.isatty():
        return {k: "" for k in ("TI", "HD", "CM", "FL", "DM", "R")}
    if os.name == "nt":
        os.system("")  # enable VT processing on Windows 10+ consoles
    return {
        "TI": "\033[1;96m",  # title    - bold bright cyan
        "HD": "\033[1;93m",  # headers  - bold bright yellow
        "CM": "\033[92m",    # commands - bright green
        "FL": "\033[96m",    # flags    - bright cyan
        "DM": "\033[90m",    # notes    - grey
        "R":  "\033[0m",
    }


INPUTS_HELP = """\
{HD}INPUTS:{R} {DM}(detected by contents, not extension){R}
  {FL}*.wad{R}                 PLAYPAL lump (COLORMAP-only WADs need {FL}-p{R})
  {FL}raw PLAYPAL{R}           10752 bytes - .lmp / SLADE playpal.pal (14 palettes)
  {FL}raw single palette{R}    768 bytes - .lmp / SLADE pal0.pal
  {FL}JASC-PAL text{R}         SLADE / PSP text .pal export
  {FL}256x1 / 256x14 PNG{R}    DoomTools pal0 / playpal (scaled strips ok)
  {FL}256x32-34 PNG{R}         colourmap PNG - row 0 read as pal0 (scaled ok)
  {FL}16x16 grid PNG{R}        SLADE palette export (any cell size)
  {FL}raw colourmap{R}         8192/8448/8704 bytes - .lmp / SLADE .cmp
                        {DM}indices only: needs -p <palette>, row 0 -> pal0{R}"""


MAIN_HELP = """\
{TI}doompal{R} - Doom palette and colourmap tool {DM}v{VER}{R}

{HD}USAGE:{R}
  doompal {FL}<input>{R} [{FL}-o{R} name]                Auto-batch (same as {CM}batch{R})
  doompal {CM}<command>{R} {FL}<input>{R} [options]
  doompal {CM}<command>{R} {FL}-h{R}                     Detailed help for one command

{HD}COMMANDS:{R}
  {CM}generate{R}, {CM}gen{R} {FL}[item ...]{R}                  Doom palette files from built-in data (no IWAD)
  {CM}batch{R}      {FL}<input>{R}                        cube + playpal + colourmap + blanks + split
  {CM}cube{R}       {FL}<input>{R}                        .cube LUT for image editors
  {CM}playpal{R}    {FL}<input> [--blank] [--slade]{R}    256x14 PLAYPAL PNG (or SLADE .pal)
  {CM}colourmap{R}  {FL}<input> [--blank]{R}              256x34 colourmap PNG with lighting
  {CM}blank{R}      {FL}<input>{R}                        Blank playpal + blank colourmap
  {CM}slade{R}      {FL}<input> [--playpal] [--cell N]{R}
                                            SLADE 16x16 grid PNG (or .pal)
  {CM}extract{R}    {FL}<wad> [--boom [NAME]] [--boomlist]{R}
                                            PLAYPAL / COLORMAP / Boom maps from a WAD
  {CM}split{R}      {FL}<input>{R}                        Transparent tint overlay PNG

{HD}COMMON OPTIONS:{R}
  {FL}-o, --output <name>{R}   Output file, or base name for multi-file commands
                        {DM}(a .png/.pal/.cmp/.cube ending is dropped from a base name){R}
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs
  {FL}-h, --help{R}            Help (after a command: help for that command)
  {FL}-v, --version{R}         Show version

""" + INPUTS_HELP + """

{HD}OUTPUT NAMING:{R}
  Without {FL}-o{R}: {DM}<input name>_<suffix>.<ext>{R} next to the input.
  {DM}See 'doompal <command> -h' for each command's exact filenames.{R}

{HD}EXAMPLES:{R}
  {CM}doompal gen{R}
      {DM}All Doom palette files as genDoom_* in the current folder{R}
  {CM}doompal gen colourmap-cmp{R}
      {DM}Just genDoom_colormap.cmp{R}
  {CM}doompal{R} mywad.wad
      {DM}Auto-batch from the WAD's PLAYPAL{R}
  {CM}doompal colourmap{R} COLORMAP.png {FL}--blank{R}
      {DM}-> COLORMAP_blank.png{R}
  {CM}doompal cube{R} COLORMAP.lmp {FL}-p{R} PLAYPAL.lmp
      {DM}LUT from a raw colourmap lump's first row{R}"""


CMD_HELP = {
"generate": """\
{TI}doompal generate{R} - Doom palette files from built-in data

{HD}EXAMPLES:{R}
  {CM}doompal gen{R}
      {DM}All 10 files in the current folder{R}
  {CM}doompal gen colourmap{R}
      {DM}-> genDoom_colormap.png{R}
  {CM}doompal gen colourmap-cmp cube{R}
      {DM}-> genDoom_colormap.cmp, genDoom.cube{R}
  {CM}doompal gen colourmap-blank{R} {FL}-o{R} colormap.png
      {DM}-> colormap.png{R}
  {CM}doompal gen playpal-pal pal0-pal{R} {FL}-o{R} palettes\\doom
      {DM}-> palettes\\doom_playpal.pal, palettes\\doom_pal0.pal{R}

{HD}USAGE:{R}
  doompal {CM}generate{R} [{FL}<item> ...{R}] [{FL}-o{R} name]
  doompal {CM}gen{R} [{FL}<item> ...{R}] [{FL}-o{R} name]          {DM}(gen = generate){R}

{HD}DESCRIPTION:{R}
  Writes Doom's palette set without needing an IWAD. The real Doom
  PLAYPAL and COLORMAP are built into doompal, so the playpal and
  colourmap outputs are exact copies of the IWAD lumps. Blank versions,
  the SLADE grid and the .cube LUT are made from pal0.
  With no items every file is written; name one or more items to write
  only those.
  {DM}Doom 1 and Doom 2 share the same palette data.{R}

{HD}ITEMS:{R}
  {CM}playpal{R}              genDoom_playpal.png         256x14 PLAYPAL PNG (exact)
  {CM}playpal-blank{R}        genDoom_playpal_blank.png   256x14, pal0 on every row
  {CM}playpal-pal{R}          genDoom_playpal.pal         SLADE binary, 14 palettes (exact)
  {CM}pal0{R}                 genDoom_pal0.png            SLADE 16x16 grid, 128x128
  {CM}pal0-pal{R}             genDoom_pal0.pal            SLADE binary, single palette
  {CM}colourmap{R}            genDoom_colormap.png        256x34 colourmap PNG (exact)
  {CM}colourmap-blank{R}      genDoom_colormap_blank.png  256x34, no lighting
  {CM}colourmap-cmp{R}        genDoom_colormap.cmp        raw COLORMAP lump (exact)
  {CM}colourmap-cmp-blank{R}  genDoom_colormap_blank.cmp  raw colourmap lump, no lighting
  {CM}cube{R}                 genDoom.cube                .cube LUT

{HD}OPTIONS:{R}
  {FL}-o, --output <name>{R}   One item: the output filename (extension added if missing)
                        Several/all: base name instead of 'genDoom'
                        {DM}(a .png/.pal/.cmp/.cube ending is dropped from a base name){R}""",

"batch": """\
{TI}doompal batch{R} - every output from one input

{HD}EXAMPLES:{R}
  {CM}doompal{R} doom2.wad
  {CM}doompal batch{R} pal0.png {FL}-o{R} mypal

{HD}USAGE:{R}
  doompal {CM}batch{R} {FL}<input>{R} [{FL}-o{R} name] [{FL}-p{R} palette]
  doompal {FL}<input>{R} [{FL}-o{R} name]          {DM}(no command = batch){R}

{HD}DESCRIPTION:{R}
  Writes the .cube LUT, PLAYPAL, colourmap, blank versions of both and
  the tint overlay.
  - PLAYPAL uses the input's own 14 palettes when it has them (WAD,
    raw PLAYPAL, 256x14 PNG); otherwise tints are generated from pal0.
  - The colourmap is the input's own when it carries one (WAD COLORMAP,
    raw colourmap lump); otherwise it is generated from pal0.
  - WAD inputs also get a PNG of every Boom colourmap (C_START/C_END).

{HD}OPTIONS:{R}
  {FL}-o, --output <name>{R}   Base name for all files
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

""" + INPUTS_HELP + """

{HD}OUTPUTS:{R} {DM}(<name> = input name, or -o){R}
  <name>.cube
  <name>_playpal.png
  <name>_colormap.png
  <name>_playpal_blank.png
  <name>_colormap_blank.png
  <name>_split.png
  <name>_<BOOMNAME>.png        {DM}WAD inputs with Boom colourmaps{R}""",

"cube": """\
{TI}doompal cube{R} - .cube LUT for image editors

{HD}EXAMPLES:{R}
  {CM}doompal cube{R} pal0.png
  {CM}doompal cube{R} doom2.wad {FL}-o{R} doom_lut

{HD}USAGE:{R}
  doompal {CM}cube{R} {FL}<input>{R} [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Builds a 64x64x64 .cube LUT where every colour snaps to its nearest
  pal0 colour. Load it as a LUT/adjustment layer in Photoshop, Affinity,
  Resolve etc. to preview art in the Doom palette.

{HD}OPTIONS:{R}
  {FL}-o, --output <name>{R}   Output file (.cube added if missing)
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

""" + INPUTS_HELP + """

{HD}OUTPUTS:{R}
  <name>.cube""",

"playpal": """\
{TI}doompal playpal{R} - 256x14 PLAYPAL

{HD}EXAMPLES:{R}
  {CM}doompal playpal{R} pal0.png
  {CM}doompal playpal{R} pal0.png {FL}--slade{R}
  {CM}doompal playpal{R} doom2.wad {FL}--blank -o{R} blank

{HD}USAGE:{R}
  doompal {CM}playpal{R} {FL}<input>{R} [{FL}--blank{R}] [{FL}--slade{R}] [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Writes all 14 palettes. Inputs that already hold 14 palettes are
  copied as-is; single palettes get Doom-style tints generated:
    1-8 red (damage/berserk), 9-12 yellow (pickups), 13 green (radsuit)

{HD}OPTIONS:{R}
  {FL}--blank{R}               pal0 on all 14 rows (no tints)
  {FL}--slade{R}               SLADE binary .pal (10752 bytes) instead of PNG
  {FL}-o, --output <name>{R}   Output file (extension added if missing)
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

""" + INPUTS_HELP + """

{HD}OUTPUTS:{R}
  <name>_playpal.png           {DM}--slade: <name>_playpal.pal{R}
  <name>_playpal_blank.png     {DM}with --blank (.pal with --slade){R}""",

"colourmap": """\
{TI}doompal colourmap{R} - 256x34 colourmap PNG

{HD}EXAMPLES:{R}
  {CM}doompal colourmap{R} pal0.png
  {CM}doompal colourmap{R} COLORMAP.png {FL}--blank{R}
      {DM}-> COLORMAP_blank.png{R}

{HD}USAGE:{R}
  doompal {CM}colourmap{R} {FL}<input>{R} [{FL}--blank{R}] [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Generates a colourmap from pal0:
    rows 0-31   light levels (bright -> dark)
    row  32     invulnerability (inverse greyscale)
    row  33     black
  Output is a PNG in pal0 colours (DoomTools style).

{HD}OPTIONS:{R}
  {FL}--blank{R}               No lighting: rows 0-31 full bright
                        {DM}(invulnerability and black rows kept){R}
  {FL}-o, --output <name>{R}   Output file (.png added if missing)
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

""" + INPUTS_HELP + """

{HD}OUTPUTS:{R}
  <name>_colormap.png
  <name>_blank.png             {DM}with --blank{R}""",

"blank": """\
{TI}doompal blank{R} - blank playpal + blank colourmap

{HD}EXAMPLES:{R}
  {CM}doompal blank{R} pal0.png

{HD}USAGE:{R}
  doompal {CM}blank{R} {FL}<input>{R} [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Writes a PLAYPAL with pal0 on all 14 rows (no tints) and a colourmap
  with no lighting (rows 0-31 full bright, invulnerability and black
  rows kept). Handy as a base for custom tint/lighting work.

{HD}OPTIONS:{R}
  {FL}-o, --output <name>{R}   Base name for both files
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

""" + INPUTS_HELP + """

{HD}OUTPUTS:{R}
  <name>_playpal_blank.png
  <name>_colormap_blank.png""",

"slade": """\
{TI}doompal slade{R} - SLADE-style palette files

{HD}EXAMPLES:{R}
  {CM}doompal slade{R} playpal.png
  {CM}doompal slade{R} playpal.png {FL}--cell 16{R}
      {DM}256x256 grid{R}

{HD}USAGE:{R}
  doompal {CM}slade{R} {FL}<input>{R} [{FL}--cell N{R}] [{FL}--playpal{R}] [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Writes pal0 as a 16x16 grid PNG like SLADE's palette export, or with
  --playpal a SLADE binary PLAYPAL (.pal, 14 palettes, tints generated
  if the input only has pal0).

{HD}OPTIONS:{R}
  {FL}--cell N{R}              Grid cell size in pixels (default 8 = 128x128)
  {FL}--playpal{R}             Binary playpal .pal instead of the grid PNG
  {FL}-o, --output <name>{R}   Output file (extension added if missing)
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

""" + INPUTS_HELP + """

{HD}OUTPUTS:{R}
  <name>_pal0.png              {DM}grid{R}
  <name>_playpal.pal           {DM}with --playpal{R}""",

"extract": """\
{TI}doompal extract{R} - pull palette lumps out of a WAD

{HD}EXAMPLES:{R}
  {CM}doompal extract{R} doom2.wad
  {CM}doompal extract{R} mymod.wad {FL}--boomlist{R}
  {CM}doompal extract{R} mymod.wad {FL}--boom{R} WATERMAP

{HD}USAGE:{R}
  doompal {CM}extract{R} {FL}<wad>{R} [{FL}--boom{R} [NAME]] [{FL}--boomlist{R}] [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Saves PLAYPAL, COLORMAP and every Boom colourmap (lumps between
  C_START and C_END) as raw lumps plus PNG previews. Colourmap PNGs
  use the WAD's PLAYPAL; if it has none, give one with -p or the PNGs
  are skipped.

{HD}OPTIONS:{R}
  {FL}--boom{R}                Only the Boom colourmaps
  {FL}--boom NAME{R}           Only one named colourmap lump
  {FL}--boomlist{R}            List Boom colourmaps and exit
  {FL}-o, --output <name>{R}   Base name for all files
  {FL}-p, --pal <file>{R}      Palette for PNG previews when the WAD has no PLAYPAL

{HD}OUTPUTS:{R} {DM}(<name> = WAD name, or -o){R}
  <name>_playpal.pal  +  <name>_playpal.png
  <name>_colormap.cmp +  <name>_colormap.png
  <name>_<BOOMNAME>.cmp + <name>_<BOOMNAME>.png""",

"split": """\
{TI}doompal split{R} - tint overlay PNG

{HD}EXAMPLES:{R}
  {CM}doompal split{R} pal0.png

{HD}USAGE:{R}
  doompal {CM}split{R} {FL}<input>{R} [{FL}-o{R} name] [{FL}-p{R} palette]

{HD}DESCRIPTION:{R}
  Writes a 256x14 RGBA PNG holding only the PLAYPAL tints: row 0
  transparent, rows 1-13 the damage / pickup / radsuit tint colour at
  its blend strength as alpha. Layer it over a blank playpal to rebuild
  the tinted rows in an image editor.

{HD}OPTIONS:{R}
  {FL}-o, --output <name>{R}   Output file (.png added if missing)
  {FL}-p, --pal <file>{R}      Palette for raw colourmap inputs

{HD}OUTPUTS:{R}
  <name>_split.png""",
}


def print_help(command=None):
    c = _ansi_colors()
    text = MAIN_HELP if command is None else CMD_HELP[command]
    print(text.format(VER=__version__, **c))


# ============================================================================
# ARGUMENT PARSING
# ============================================================================

COMMANDS = ["generate", "batch", "cube", "playpal", "colourmap",
            "blank", "slade", "extract", "split"]
ALIASES = {"colormap": "colourmap", "gen": "generate"}

FLAG_NAMES = {
    "-o": "output", "--output": "output",
    "-p": "pal", "--pal": "pal",
    "--cell": "cell",
    "--blank": "blank",
    "--slade": "slade",
    "--playpal": "playpal",
    "--boom": "boom",
    "--boomlist": "boomlist",
}
VALUE_FLAGS = {"output", "pal", "cell"}

CMD_FLAGS = {
    "generate":  {"output"},
    "batch":     {"output", "pal"},
    "cube":      {"output", "pal"},
    "playpal":   {"output", "pal", "blank", "slade"},
    "colourmap": {"output", "pal", "blank"},
    "blank":     {"output", "pal"},
    "slade":     {"output", "pal", "cell", "playpal"},
    "extract":   {"output", "pal", "boom", "boomlist"},
    "split":     {"output", "pal"},
}


class Opts:
    def __init__(self):
        self.input = None
        self.output = None
        self.pal = None
        self.cell = SLADE_DEFAULT_CELL
        self.blank = False
        self.slade = False
        self.playpal = False
        self.boom = None       # None / True (all) / "NAME"
        self.boomlist = False
        self.items = []        # generate: selected output items


def _looks_like_lump_name(tok):
    return (0 < len(tok) <= 8 and not tok.startswith("-")
            and "." not in tok and "/" not in tok and "\\" not in tok)


def parse_args(command, tokens):
    o = Opts()
    allowed = CMD_FLAGS[command]
    positionals = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-") and len(tok) > 1:
            flag, _, inline = tok.partition("=")
            name = FLAG_NAMES.get(flag.lower())
            if name is None:
                raise UsageError(f"Unknown option '{tok}'")
            if name not in allowed:
                raise UsageError(f"Option '{flag}' doesn't apply to '{command}'")
            if name in VALUE_FLAGS:
                if inline:
                    val = inline
                elif i + 1 < len(tokens):
                    i += 1
                    val = tokens[i]
                else:
                    raise UsageError(f"Option '{flag}' needs a value")
                if name == "cell":
                    try:
                        val = int(val)
                        if val < 1:
                            raise ValueError
                    except ValueError:
                        raise UsageError(f"--cell needs a whole number > 0, got '{val}'")
                setattr(o, name, val)
            elif name == "boom":
                if inline:
                    o.boom = inline
                elif i + 1 < len(tokens) and _looks_like_lump_name(tokens[i + 1]) \
                        and not Path(tokens[i + 1]).is_file():
                    i += 1
                    o.boom = tokens[i]
                else:
                    o.boom = True
            else:
                setattr(o, name, True)
        else:
            positionals.append(tok)
        i += 1

    if command == "generate":
        for tok in positionals:
            item = normalise_gen_item(tok)
            if item not in GEN_ITEM_NAMES:
                raise UsageError(
                    f"Unknown generate item '{tok}'. Valid items:\n       "
                    + ", ".join(GEN_ITEM_NAMES)
                )
            if item not in o.items:
                o.items.append(item)
    else:
        if not positionals:
            raise UsageError(f"'{command}' needs an input file")
        if len(positionals) > 1:
            raise UsageError(
                f"Unexpected argument '{positionals[1]}' - use -o to set the output name"
            )
        o.input = Path(positionals[0])
    return o


HANDLERS = {
    "generate": cmd_generate,
    "batch": cmd_batch,
    "cube": cmd_cube,
    "playpal": cmd_playpal,
    "colourmap": cmd_colourmap,
    "blank": cmd_blank,
    "slade": cmd_slade,
    "extract": cmd_extract,
    "split": cmd_split,
}


def main():
    argv = sys.argv[1:]

    if not argv or argv[0].lower() in ("-h", "--help"):
        print_help()
        return 0
    if argv[0].lower() in ("-v", "--version"):
        print(f"doompal version {__version__}")
        return 0

    first = argv[0].lower()
    first = ALIASES.get(first, first)
    if first in COMMANDS:
        command, rest = first, argv[1:]
    elif argv[0].startswith("-"):
        print(f"ERROR: Unknown option '{argv[0]}'  (see 'doompal -h')", file=sys.stderr)
        return 2
    else:
        command, rest = "batch", argv   # auto-batch

    if any(t.lower() in ("-h", "--help") for t in rest):
        print_help(command)
        return 0

    try:
        opts = parse_args(command, rest)
    except UsageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print(f"       See 'doompal {command} -h'", file=sys.stderr)
        return 2

    try:
        return HANDLERS[command](opts)
    except (InputError, FileNotFoundError, ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
