"""cpscan_iwad.py v2 - palette-index pixel counts + checksum per graphic lump
(for cleanpal's built-in scans). Usage: py cpscan_iwad.py DOOM2.WAD [DOOM.WAD ...]"""
import gzip, hashlib, json, os, struct, sys, zlib

NON_GFX = {"PLAYPAL", "COLORMAP", "TEXTURE1", "TEXTURE2", "PNAMES", "ENDOOM", "GENMIDI",
           "DMXGUS", "DMXGUSC", "ANIMATED", "SWITCHES", "THINGS", "LINEDEFS", "SIDEDEFS",
           "VERTEXES", "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP"}
START = {"S_START": "sprite", "SS_START": "sprite", "F_START": "flat", "FF_START": "flat",
         "P_START": "patch", "PP_START": "patch"}
END = {"S_END", "SS_END", "F_END", "FF_END", "P_END", "PP_END"}

def picture_counts(d):
    n = len(d)
    if n < 12:
        return None
    w, h = struct.unpack_from("<HH", d, 0)
    if not (1 <= w <= 4096 and 1 <= h <= 4096) or n < 8 + 4 * w:
        return None
    counts = [0] * 256
    for x in range(w):
        p = struct.unpack_from("<I", d, 8 + 4 * x)[0]
        if not 8 + 4 * w <= p < n:
            return None
        for _ in range(1024):
            if p >= n:
                return None
            if d[p] == 0xFF:
                break
            if p + 1 >= n:
                return None
            ln = d[p + 1]
            if p + 4 + ln > n:
                return None
            for v in d[p + 3:p + 3 + ln]:
                counts[v] += 1
            p += 4 + ln
        else:
            return None
    return counts

def scan(path):
    data = open(path, "rb").read()
    if data[:4] not in (b"IWAD", b"PWAD"):
        raise SystemExit("%s: not a WAD" % path)
    num, ofs = struct.unpack_from("<ii", data, 4)
    lumps, region, pal = {}, None, None
    for i in range(num):
        pos, size = struct.unpack_from("<ii", data, ofs + i * 16)
        name = data[ofs + i * 16 + 8:ofs + i * 16 + 16].split(b"\0")[0].decode("ascii", "replace").upper()
        if name in START:
            region = START[name]; continue
        if name in END:
            region = None; continue
        d = data[pos:pos + size]
        if name == "PLAYPAL" and size >= 768:
            pal = [list(d[k:k + 3]) for k in range(0, 768, 3)]
        if size <= 0:
            continue
        if region == "flat":
            if size not in (4096, 8192):
                continue
            c = [0] * 256
            for v in d[:4096]:
                c[v] += 1
            kind = "flat"
        elif region in ("sprite", "patch"):
            c = picture_counts(d); kind = region
        elif name not in NON_GFX and not name.startswith(("D_", "DS", "DP", "DEMO")):
            c = picture_counts(d); kind = "graphic"
        else:
            continue
        if c is None:
            continue
        lumps["%s/%s" % (kind, name)] = {"crc": zlib.crc32(d) & 0xFFFFFFFF, "n": len(d),
                                          "c": {str(k): v for k, v in enumerate(c) if v}}
    out = {"cleanpal_scan": 2, "source": os.path.basename(path), "size": len(data),
           "md5": hashlib.md5(data).hexdigest(), "indexed": True, "playpal": pal,
           "lumps": lumps}
    dst = os.path.splitext(os.path.basename(path))[0].upper() + ".cpscan"
    with gzip.open(dst, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("%s: %d graphic lumps -> %s" % (path, len(lumps), dst))

for p in sys.argv[1:]:
    scan(p)