"""Doom WAD graphics decoding (pictures, flats, PNG lumps)."""

import os
import struct


# ============================================================ WAD graphics
PNG_SIG = b"\x89PNG\r\n\x1a\n"
NON_GFX = {"PLAYPAL", "COLORMAP", "TEXTURE1", "TEXTURE2", "PNAMES", "ENDOOM", "GENMIDI",
           "DMXGUS", "DMXGUSC", "ANIMATED", "SWITCHES", "THINGS", "LINEDEFS", "SIDEDEFS",
           "VERTEXES", "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP",
           "BEHAVIOR", "TEXTMAP", "ZNODES", "DIALOGUE", "ENDMAP", "SCRIPTS", "DEHACKED",
           "MAPINFO", "UMAPINFO", "DECORATE", "ZMAPINFO", "SNDINFO", "LANGUAGE",
           "TEXTURES", "SNDSEQ", "GAMEINFO", "DMAPINFO", "SBARINFO", "MENUDEF"}
REGION_START = {"S_START": "sprite", "SS_START": "sprite", "F_START": "flat",
                "FF_START": "flat", "P_START": "patch", "PP_START": "patch"}
REGION_END = {"S_END", "SS_END", "F_END", "FF_END", "P_END", "PP_END"}
KIND_LABEL = {"flat": "Flats", "sprite": "Sprites", "patch": "Patches",
              "graphic": "Graphics", "texture1": "TEXTURE1", "texture2": "TEXTURE2",
              "loose": "Loose"}


def is_doom_picture(d):
    """Strict structural check for the Doom picture (patch) format."""
    n = len(d)
    if n < 12:
        return False
    w, h = struct.unpack_from("<HH", d, 0)
    if not (1 <= w <= 4096 and 1 <= h <= 4096) or n < 8 + 4 * w:
        return False
    lo = 8 + 4 * w
    for x in range(w):
        off = struct.unpack_from("<I", d, 8 + 4 * x)[0]
        if not lo <= off < n:
            return False
        p = off
        for _ in range(1024):
            if p >= n:
                return False
            top = d[p]
            if top == 0xFF:
                break
            if p + 1 >= n:
                return False
            ln = d[p + 1]
            p += 4 + ln
            if p > n:
                return False
        else:
            return False
    return True


def decode_doom_picture(d, pal):
    from PIL import Image

    w, h = struct.unpack_from("<HH", d, 0)
    buf = bytearray(w * h * 4)
    for x in range(w):
        p = struct.unpack_from("<I", d, 8 + 4 * x)[0]
        prev = -1
        while p < len(d) and d[p] != 0xFF:
            top = d[p]
            ln = d[p + 1]
            if top <= prev:          # DeePsea tall patches
                top += prev
            prev = top
            src = p + 3
            for k in range(ln):
                y = top + k
                if 0 <= y < h and src + k < len(d):
                    r, g, b = pal[d[src + k]]
                    i = (y * w + x) * 4
                    buf[i:i + 4] = bytes((r, g, b, 255))
            p += 4 + ln
    return Image.frombytes("RGBA", (w, h), bytes(buf))


def decode_flat(d, pal):
    from PIL import Image

    h = len(d) // 64
    return Image.frombytes("RGB", (64, h), bytes(c for i in d[:64 * h] for c in pal[i])
                           ).convert("RGBA")


def decode_png(d):
    import io
    from PIL import Image

    with Image.open(io.BytesIO(d)) as im:
        im.load()
        return im.convert("RGBA")


# ============================================================ archive + IWAD
IWAD_NAMES = ("doom2.wad", "plutonia.wad", "tnt.wad", "doom.wad", "freedoom2.wad",
              "freedoom1.wad")
_NS_START = {"S_START": "s", "SS_START": "s", "F_START": "f", "FF_START": "f",
             "C_START": "c"}
_NS_END = {"S_END", "SS_END", "F_END", "FF_END", "C_END"}


class WadArchive:
    """A WAD's directory + data. Lookups by name return the LAST lump with
    that name, like the engine. `global_lump` skips the sprite / flat /
    colormap namespaces (where patch names are looked up, as in dsda-doom)."""

    def __init__(self, path):
        with open(path, "rb") as fh:
            data = fh.read()
        if len(data) < 12 or data[0:4] not in (b"IWAD", b"PWAD"):
            raise ValueError("Not a valid WAD file (bad header).")
        self.is_iwad = data[0:4] == b"IWAD"
        num, ofs = struct.unpack_from("<ii", data, 4)
        lumps = []
        for i in range(num):
            o = ofs + i * 16
            if o + 16 > len(data):
                break
            pos, size = struct.unpack_from("<ii", data, o)
            name = data[o + 8:o + 16].split(b"\x00")[0].decode("ascii", "replace").upper()
            lumps.append((name, pos, size))
        self.data = data
        self.path = path
        self.lumps = lumps
        self.last = {}
        self.glob = {}
        ns = None
        for i, (name, pos, size) in enumerate(lumps):
            self.last[name] = i
            if name in _NS_START:
                ns = _NS_START[name]
                continue
            if name in _NS_END:
                ns = None
                continue
            if ns is None and size > 0:
                self.glob[name] = i

    def lump_at(self, i):
        name, pos, size = self.lumps[i]
        return self.data[pos:pos + size]

    def lump(self, name):
        i = self.last.get(name)
        return self.lump_at(i) if i is not None else None

    def global_lump(self, name):
        i = self.glob.get(name)
        return self.lump_at(i) if i is not None else None

    def playpal(self):
        raw = self.lump("PLAYPAL")
        if raw is None or len(raw) < 768:
            return None
        return [tuple(raw[i * 3:i * 3 + 3]) for i in range(256)]


def iwad_search_dirs(near=()):
    """Folders to look for an IWAD in: beside the given files, then
    DOOMWADDIR and DOOMWADPATH (what dsda-doom reads)."""
    import os

    dirs = []
    for p in near:
        if p:
            dirs.append(os.path.dirname(os.path.abspath(p)))
    for var in ("DOOMWADDIR", "DOOMWADPATH"):
        for d in (os.environ.get(var) or "").split(os.pathsep):
            if d.strip():
                dirs.append(d.strip())
    out = []
    for d in dirs:
        if d not in out and os.path.isdir(d):
            out.append(d)
    return out


def guess_iwad(near=()):
    import os

    for d in iwad_search_dirs(near):
        try:
            files = {f.lower(): f for f in os.listdir(d)}
        except OSError:
            continue
        for n in IWAD_NAMES:
            if n in files:
                return os.path.join(d, files[n])
    return None


# ============================================================ TEXTUREx / PNAMES
def parse_pnames(d):
    if not d or len(d) < 4:
        return []
    n = struct.unpack_from("<i", d, 0)[0]
    n = max(0, min(n, (len(d) - 4) // 8))
    return [d[4 + 8 * k:12 + 8 * k].split(b"\x00")[0].decode("ascii", "replace").upper()
            for k in range(n)]


def parse_texturex(d):
    """Doom-format TEXTURE1 / TEXTURE2 -> [{"name", "w", "h", "patches":
    [(x, y, pnames_index), ...]}, ...]."""
    out = []
    if not d or len(d) < 4:
        return out
    n = struct.unpack_from("<i", d, 0)[0]
    n = max(0, min(n, (len(d) - 4) // 4))
    for k in range(n):
        o = struct.unpack_from("<i", d, 4 + 4 * k)[0]
        if o < 0 or o + 22 > len(d):
            continue
        name = d[o:o + 8].split(b"\x00")[0].decode("ascii", "replace").upper()
        w, h = struct.unpack_from("<hh", d, o + 12)
        pc = struct.unpack_from("<h", d, o + 20)[0]
        patches = []
        for j in range(max(0, pc)):
            q = o + 22 + 10 * j
            if q + 6 > len(d):
                break
            x, y, pi = struct.unpack_from("<hhh", d, q)
            patches.append((x, y, pi))
        if w > 0 and h > 0:
            out.append({"name": name, "w": w, "h": h, "patches": patches})
    return out


def decode_patch(d, pal):
    """A patch lump (Doom picture or PNG) -> RGBA image, or None."""
    if d is None:
        return None
    if d[:8] == PNG_SIG:
        return decode_png(d)
    if is_doom_picture(d):
        return decode_doom_picture(d, pal)
    return None


def compose_texture(tex, pnames, find_patch):
    """Composite a texture. find_patch(name) -> RGBA image or None.
    Returns (image, missing patch names)."""
    from PIL import Image

    img = Image.new("RGBA", (tex["w"], tex["h"]), (0, 0, 0, 0))
    missing = []
    for x, y, pi in tex["patches"]:
        pname = pnames[pi] if 0 <= pi < len(pnames) else "#%d" % pi
        pim = find_patch(pname) if 0 <= pi < len(pnames) else None
        if pim is None:
            if pname not in missing:
                missing.append(pname)
            continue
        img.paste(pim, (x, y), pim)            # clips negative / overhanging offsets
    return img, missing


# ============================================================ WAD browsing source
class WadSource:
    """Read-only index of the graphics in a WAD, plus TEXTURE1 / TEXTURE2
    (from the WAD, else the IWAD). Images decode on demand."""

    def __init__(self, path, fallback_pal, iwad=None):
        arch = WadArchive(path)
        self.arch = arch
        if iwad is not None and os.path.abspath(iwad.path) == os.path.abspath(path):
            iwad = None                          # the WAD is the IWAD
        self.iwad = iwad
        self.data = arch.data
        self.path = path
        self.lumps = arch.lumps

        pal = arch.playpal()
        ipal = iwad.playpal() if iwad is not None else None
        if pal is not None:
            self.pal, self.pal_src = pal, "WAD PLAYPAL"
        elif ipal is not None:
            self.pal, self.pal_src = ipal, "IWAD PLAYPAL"
        else:
            self.pal, self.pal_src = fallback_pal, "loaded palette"
        self.ipal = ipal or self.pal

        items = []
        region = None
        for i, (name, pos, size) in enumerate(arch.lumps):
            if name in REGION_START:
                region = REGION_START[name]
                continue
            if name in REGION_END:
                region = None
                continue
            if size <= 0:
                continue
            d = arch.lump_at(i)
            if d[:8] == PNG_SIG:
                items.append({"name": name, "kind": region or "graphic", "lump": i,
                              "fmt": "png"})
            elif region == "flat":
                if size in (4096, 8192):
                    items.append({"name": name, "kind": "flat", "lump": i, "fmt": "flat"})
            elif region in ("sprite", "patch"):
                if is_doom_picture(d):
                    items.append({"name": name, "kind": region, "lump": i, "fmt": "doom"})
            elif name not in NON_GFX and not name.startswith(("D_", "DS", "DP", "DEMO")) \
                    and is_doom_picture(d):
                items.append({"name": name, "kind": "graphic", "lump": i, "fmt": "doom"})

        # textures: each TEXTUREx from the WAD if it has it, else the IWAD;
        # WAD lists use the WAD's PNAMES (else the IWAD's), IWAD lists the IWAD's
        ipn = parse_pnames(iwad.lump("PNAMES")) if iwad is not None else []
        wpn_raw = arch.lump("PNAMES")
        wpn = parse_pnames(wpn_raw) if wpn_raw is not None else None
        self.tex_src = {}
        self._pnames = {}
        for lname, kind in (("TEXTURE1", "texture1"), ("TEXTURE2", "texture2")):
            d = arch.lump(lname)
            if d is not None:
                src, pn = "WAD", (wpn if wpn is not None else ipn)
                pn_src = "WAD PNAMES" if wpn is not None else "IWAD PNAMES"
            elif iwad is not None and iwad.lump(lname) is not None:
                d, src, pn, pn_src = iwad.lump(lname), "IWAD", ipn, "IWAD PNAMES"
            else:
                continue
            self.tex_src[kind] = "%s %s + %s" % (src, lname, pn_src)
            self._pnames[kind] = pn
            for k, t in enumerate(parse_texturex(d)):
                items.append({"name": t["name"], "kind": kind, "fmt": "tex", "tex": t,
                              "tex_src": src, "lump": k})
        for it in items:
            it["key"] = (path, it["kind"], it["name"], it.get("lump"))
        self.items = items
        self._patch_cache = {}

    def _lump(self, i):
        return self.arch.lump_at(i)

    def find_patch(self, name):
        """Patch by name: the WAD's global namespace first, then the IWAD's."""
        if name in self._patch_cache:
            return self._patch_cache[name]
        img = None
        d = self.arch.global_lump(name)
        if d is not None:
            img = decode_patch(d, self.pal)
        if img is None and self.iwad is not None:
            d = self.iwad.global_lump(name)
            if d is not None:
                img = decode_patch(d, self.ipal)
        if len(self._patch_cache) > 2000:
            self._patch_cache.clear()
        self._patch_cache[name] = img
        return img

    def image(self, it):
        f = it["fmt"]
        if f == "tex":
            img, missing = compose_texture(it["tex"], self._pnames[it["kind"]],
                                           self.find_patch)
            it["missing"] = missing
            return img
        d = self._lump(it["lump"])
        if f == "png":
            return decode_png(d)
        if f == "flat":
            return decode_flat(d, self.pal)
        return decode_doom_picture(d, self.pal)
