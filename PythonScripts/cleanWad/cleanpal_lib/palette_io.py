"""Palette loading, exports, palettising and colour-list files."""

import os
import struct

from .colour import parse_colour_list, tint
from .constants import ENTRIES, GREEN, TINTS


# ============================================================ loaders
def _wad_playpal(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
        raise ValueError("Not a valid WAD file (bad header).")
    numlumps, infotableofs = struct.unpack_from("<ii", data, 4)
    for i in range(numlumps):
        off = infotableofs + i * 16
        if off + 16 > len(data):
            break
        filepos, size = struct.unpack_from("<ii", data, off)
        name = data[off + 8: off + 16].split(b"\x00")[0].decode("ascii", "replace")
        if name.upper() == "PLAYPAL":
            if size < 768:
                raise ValueError("PLAYPAL lump is smaller than 768 bytes.")
            return data[filepos: filepos + size]
    raise ValueError("No PLAYPAL lump found in WAD.")


def _triples(raw):
    return [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i in range(ENTRIES)]


def _looks_like_grid(px, w):
    """True if a square image is made of uniform 16x16 cells (SLADE style)."""
    cell = w // 16
    if cell < 2:
        return True
    uniform = 0
    for idx in range(ENTRIES):
        gx, gy = idx % 16, idx // 16
        y = gy * cell + cell // 2
        x0 = gx * cell
        row = [px[x0 + dx, y] for dx in range(1, cell - 1)] or [px[x0, y]]
        if all(p == row[0] for p in row):
            uniform += 1
    return uniform >= ENTRIES * 0.9


def load_palette(path):
    """Returns (list of 256 RGB tuples, source label)."""
    from PIL import Image

    ext = os.path.splitext(path)[1].lower()

    if ext == ".wad":
        raw = _wad_playpal(path)
        return _triples(raw), "WAD PLAYPAL (%d palettes)" % (len(raw) // 768)

    if ext == ".pal":
        with open(path, "rb") as fh:
            raw = fh.read()
        if len(raw) < 768 or len(raw) % 768:
            raise ValueError("PAL size (%d bytes) is not a multiple of 768." % len(raw))
        n = len(raw) // 768
        label = "SLADE pal0.pal (single palette)" if n == 1 \
            else "SLADE playpal.pal (%d palettes)" % n
        return _triples(raw), label

    if ext == ".png":
        im = Image.open(path).convert("RGB")
        w, h = im.size
        px = im.load()
        is_grid = (w == h and w % 16 == 0 and w >= 16
                   and (w != 256 or _looks_like_grid(px, w)))
        if is_grid:
            cell = w // 16
            rgbs = [px[(i % 16) * cell + cell // 2, (i // 16) * cell + cell // 2]
                    for i in range(ENTRIES)]
            return rgbs, "SLADE pal0.png (%dx%d grid, %dpx cells)" % (w, h, cell)
        if w == 256:
            rgbs = [px[i, 0] for i in range(ENTRIES)]
            if h == 14:
                label = "DoomTools playpal.png (14 palettes)"
            elif h in (32, 33, 34):
                label = "COLORMAP image (256x%d, line 0)" % h
            elif h == 1:
                label = "256x1 palette strip"
            else:
                label = "256x%d palette image (row 0)" % h
            return rgbs, label
        raise ValueError("Unexpected PNG size %dx%d. Expected a 16x16 grid "
                         "(SLADE) or 256 wide (DoomTools / COLORMAP)." % (w, h))

    raise ValueError("Unsupported input: %s (use .wad, .pal or .png)" % ext)



# ============================================================ writers
def rows_image(rows, force_rgba=False):
    from PIL import Image

    rgba = force_rgba or any(e is None for r in rows for e in r)
    im = Image.new("RGBA" if rgba else "RGB", (ENTRIES, len(rows)),
                   (0, 0, 0, 0) if rgba else (0, 0, 0))
    px = im.load()
    for y, row in enumerate(rows):
        for x, e in enumerate(row):
            if e is not None:
                px[x, y] = (e + (255,)) if rgba else e
    return im


def slade_image(entries, force_rgba=False, cell=8):
    from PIL import Image, ImageDraw

    rgba = force_rgba or any(e is None for e in entries)
    size = cell * 16
    im = Image.new("RGBA" if rgba else "RGB", (size, size),
                   (0, 0, 0, 0) if rgba else (0, 0, 0))
    dr = ImageDraw.Draw(im)
    for i, e in enumerate(entries):
        if e is None:
            continue
        x0, y0 = (i % 16) * cell, (i // 16) * cell
        dr.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1],
                     fill=(e + (255,)) if rgba else e)
    return im


def palette_rows(entries, tinted):
    return [[tint(e, spec) if tinted else e for e in entries] for spec in TINTS]


def pal_bytes(rows):
    out = bytearray()
    for row in rows:
        for e in row:
            out += bytes(e if e is not None else GREEN)
    return bytes(out)


def write_export(label, path, entries):
    if label == "DoomTools playpal.png":
        rows_image(palette_rows(entries, True)).save(path)
    elif label == "DoomTools blank playpal.png":
        rows_image(palette_rows(entries, False)).save(path)
    elif label == "SLADE pal0.png":
        slade_image(entries).save(path)
    elif label == "SLADE pal0.pal":
        with open(path, "wb") as fh:
            fh.write(pal_bytes([entries]))
    elif label == "SLADE playpal.pal":
        with open(path, "wb") as fh:
            fh.write(pal_bytes(palette_rows(entries, True)))
    else:
        raise ValueError("Unknown export: %s" % label)


def write_analysis(outdir, stem, token, rgbs, res, exact_on, similar_on, split):
    written = []

    def ents(idxs):
        e = [None] * ENTRIES
        for i in idxs:
            e[i] = rgbs[i]
        return e

    def save(entries, name):
        p = os.path.join(outdir, name)
        slade_image(entries, force_rgba=True).save(p)
        written.append(p)

    exact_on = exact_on or bool(res["exact_all"])        # include snapshot removals
    similar_on = similar_on or bool(res["similar_all"])
    if exact_on:
        save(ents(i for g in res["exact_all"] for i in g[1:]),
             "%s-identical-%s.png" % (stem, token))
    if similar_on:
        save(ents(i for g in res["similar_all"] for i in g[1:]),
             "%s-similar-%s.png" % (stem, token))
    packed = [rgbs[i] for i in res["kept"]]
    save(packed + [None] * (ENTRIES - len(packed)),
         "%s-aligned-%s.png" % (stem, token))

    if split:
        if exact_on:
            for g in res["exact_all"]:
                save(ents(g[1:]), "%s-identical-%s-keep%03d.png" % (stem, token, g[0]))
        if similar_on:
            for g in res["similar_all"]:
                save(ents(g[1:]), "%s-similar-%s-keep%03d.png" % (stem, token, g[0]))
    return written


# ============================================================ palettise preview
def _pil_const(group, name):
    from PIL import Image
    return getattr(getattr(Image, group, Image), name)


def palettise_p(src_rgba, colours, dither):
    """Like palettise, but returns (P image indexing `colours`, alpha mask)
    so a COLORMAP row can relight it by swapping the palette."""
    from PIL import Image

    cols = list(colours)[:256]
    flat = []
    for c in cols:
        flat.extend(c)
    flat.extend(list(cols[0]) * (256 - len(cols)))
    palimg = Image.new("P", (1, 1))
    palimg.putpalette(flat)
    mode = _pil_const("Dither", "FLOYDSTEINBERG" if dither else "NONE")
    p = src_rgba.convert("RGB").quantize(palette=palimg, dither=mode)
    alpha = src_rgba.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    return p, alpha


def relight(p, alpha, lit_cols):
    """P image + alpha -> RGBA using lit_cols as the palette."""
    q = p.copy()
    flat = []
    for c in lit_cols[:256]:
        flat.extend(c)
    flat.extend(list(lit_cols[0]) * (256 - min(len(lit_cols), 256)))
    q.putpalette(flat)
    out = q.convert("RGBA")
    out.putalpha(alpha)
    return out


def palettise(src_rgba, colours, dither):
    """Map an RGBA image to the given colours (nearest RGB, Pillow in C).
    Pixels with alpha < 128 become transparent. Source is not modified."""
    from PIL import Image

    if not colours:
        return src_rgba
    cols = list(colours)[:256]
    flat = []
    for c in cols:
        flat.extend(c)
    flat.extend(list(cols[0]) * (256 - len(cols)))  # pad with a real colour
    palimg = Image.new("P", (1, 1))
    palimg.putpalette(flat)
    mode = _pil_const("Dither", "FLOYDSTEINBERG" if dither else "NONE")
    out = src_rgba.convert("RGB").quantize(palette=palimg, dither=mode).convert("RGBA")
    out.putalpha(src_rgba.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    return out



def read_colour_file(path):
    """Colours from hex text, GIMP .gpl, JASC .pal or raw .pal (pal0)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    ext = os.path.splitext(path)[1].lower()
    head = raw[:16]
    if ext == ".pal" and not head.startswith(b"JASC-PAL"):
        if len(raw) < 3 or len(raw) % 3:
            raise ValueError("Raw .pal size is not a multiple of 3 bytes.")
        n = min(len(raw) // 3, ENTRIES)
        return [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i in range(n)]
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    cols = []
    if head.startswith(b"GIMP Palette") or ext == ".gpl":
        for ln in lines[1:]:
            t = ln.strip()
            if not t or t.startswith("#") or t.split(":")[0] in ("Name", "Columns"):
                continue
            parts = t.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                v = tuple(int(p) for p in parts[:3])
                if all(0 <= x <= 255 for x in v):
                    cols.append(v)
    elif head.startswith(b"JASC-PAL"):
        for ln in lines[3:]:
            parts = ln.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                cols.append(tuple(min(int(p), 255) for p in parts[:3]))
    else:
        cols = parse_colour_list(text)
    if not cols:
        raise ValueError("No colours found.")
    return cols
