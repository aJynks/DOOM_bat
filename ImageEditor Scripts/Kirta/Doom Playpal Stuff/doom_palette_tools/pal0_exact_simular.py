# -*- coding: utf-8 -*-
"""
Krita (Python): SLADE palette PNG export (expected 128x128, 16x16 grid, each cell 8x8)

DOES BOTH (in a DUPLICATE document; original untouched):
  1) IDENTICAL (exact RGB match) -> group "IDENTICAL"
     - one paint layer per exact colour that appears 2+ times
     - layer contains all matching 8x8 blocks (filled with that colour)

  2) SIMILAR (perceptual-ish, transitive clustering) -> group "SIMILAR"
     - one paint layer per similar cluster (2+ members)
     - each member block is painted in its own colour (so differences are visible)

SIMILAR metric:
  - Weighted RGB distance (luma-ish weighting), SIM_MAX_DIST can be fractional
  - Clustering is transitive using Union-Find

To use:
1. Open your 128x128 palette image in Krita
2. Run this script from Tools > Scripts > Scripter
"""

from krita import Krita
import os
import math

# -------------------- USER TUNABLES --------------------
SIM_MAX_DIST = 1.1            # try 3.6–4.2 for Doom ramps; default 1.1
SIM_EXCLUDE_EXACT = True      # if True, SIMILAR ignores exact duplicates (IDENTICAL handles them)

# -------------------- CONSTANTS --------------------
GRID = 16
CELL = 8
GROUP_IDENTICAL = "IDENTICAL"
GROUP_SIMILAR   = "SIMILAR"
BPP = 4  # assume RGBA/U8

def _u8(v):
    """Convert a byte/bytes/int channel value into an int 0..255."""
    if isinstance(v, int):
        return v
    if isinstance(v, (bytes, bytearray)):
        return v[0]
    return int(v)

def rgb_key(r, g, b):
    return f"{r},{g},{b}"

def safe_basename(name):
    return "".join("_" if c in '\\/:*?"<>|' else c for c in name)

# ---- Union-Find (Disjoint Sets) ----
class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            self.p[ra] = rb
        elif self.r[ra] > self.r[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.r[ra] += 1

def is_similar(a, b):
    dr = abs(a["r"] - b["r"])
    dg = abs(a["g"] - b["g"])
    db = abs(a["b"] - b["b"])

    if SIM_EXCLUDE_EXACT and dr == 0 and dg == 0 and db == 0:
        return False

    # Weighted RGB distance (luma-ish weighting)
    d = math.sqrt(
        (0.299 * dr) * (0.299 * dr) +
        (0.587 * dg) * (0.587 * dg) +
        (0.114 * db) * (0.114 * db)
    )
    return d <= SIM_MAX_DIST

def _make_group(doc, name):
    root = doc.rootNode()
    grp = doc.createNode(name, "grouplayer")
    root.addChildNode(grp, None)
    return grp

def _make_paint_layer(doc, parent, name):
    lyr = doc.createNode(name, "paintlayer")
    parent.addChildNode(lyr, None)
    return lyr

def _blank_rgba_buffer(w, h):
    # Transparent RGBA
    return bytearray(w * h * 4)

def _set_block(buf, w, x0, y0, size, rgba):
    r, g, b, a = rgba
    r &= 0xFF; g &= 0xFF; b &= 0xFF; a &= 0xFF
    # Krita uses BGRA order
    for yy in range(y0, y0 + size):
        row_base = (yy * w + x0) * 4
        for xx in range(size):
            j = row_base + xx * 4
            buf[j + 0] = b  # B at index 0
            buf[j + 1] = g  # G at index 1
            buf[j + 2] = r  # R at index 2
            buf[j + 3] = a  # A at index 3

def _show_done_message(text):
    # Optional: show a QMessageBox if available; otherwise print.
    try:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(None, "Palette Duplicate Finder", text)
    except Exception:
        print(text)

def _get_similarity_threshold():
    """Ask user for similarity threshold, default to 1.1"""
    try:
        from PyQt5.QtWidgets import QInputDialog
        value, ok = QInputDialog.getDouble(
            None,
            "Similarity Threshold",
            "Enter similarity threshold:\n\n"
            "Lower values (1.1) = stricter matching\n"
            "Higher values (3.6-4.2) = finds color ramps\n\n"
            "Threshold:",
            1.1,  # default value
            0.0,  # minimum
            100.0,  # maximum
            1  # decimals
        )
        if ok:
            return value
        else:
            return None  # User cancelled
    except Exception:
        # Fallback if dialog fails
        print("Using default similarity threshold: 1.1")
        return 1.1

def main():
    app = Krita.instance()
    src = app.activeDocument()
    if src is None:
        print("No active document is open.")
        return

    # Ask user for similarity threshold
    sim_threshold = _get_similarity_threshold()
    if sim_threshold is None:
        print("Operation cancelled by user.")
        return
    
    # Update the global threshold
    global SIM_MAX_DIST
    SIM_MAX_DIST = sim_threshold

    w = src.width()
    h = src.height()

    # Match the Photoshop version: expect 128x128 exactly (16x16 of 8x8)
    if w != GRID * CELL or h != GRID * CELL:
        print(f"Unexpected document size: {w}x{h}. Expected 128x128 (16x16 of 8x8 blocks).")
        return

    # Read all pixels once from the source document
    src_bytes = src.pixelData(0, 0, w, h)

    def get_rgba_at(px, py):
        """Get RGBA values at a specific pixel position"""
        i = (py * w + px) * BPP
        # Krita stores pixels in BGRA order (not RGBA)
        return (
            _u8(src_bytes[i + 2]),  # R is at index 2
            _u8(src_bytes[i + 1]),  # G is at index 1
            _u8(src_bytes[i + 0]),  # B is at index 0
            _u8(src_bytes[i + 3]),  # A is at index 3
        )

    # Sample the centre pixel of each cell
    colors = [None] * (GRID * GRID)  # dicts: {idx,x,y,r,g,b,key}
    for gy in range(GRID):
        for gx in range(GRID):
            x0 = gx * CELL
            y0 = gy * CELL
            sx = x0 + (CELL // 2)
            sy = y0 + (CELL // 2)

            r, g, b, a = get_rgba_at(sx, sy)
            idx = gy * GRID + gx
            colors[idx] = {
                "idx": idx,
                "x": x0, "y": y0,
                "r": r, "g": g, "b": b, "a": a,
                "key": rgb_key(r, g, b)
            }

    # ---------------------------------------------------------------------
    # Create DUPLICATE document (original untouched)
    # ---------------------------------------------------------------------
    src_path = src.fileName() or ""
    if src_path:
        base = os.path.splitext(os.path.basename(src_path))[0]
    else:
        base = safe_basename(src.name() or "palette")

    dup_name = f"{base}_DUP_ID_SIM"
    dup_doc = app.createDocument(w, h, dup_name, "RGBA", "U8", "", 72.0)
    if dup_doc is None:
        print("Failed to create duplicate document.")
        return

    # Put original pixels into the duplicate (single base layer)
    dup_root = dup_doc.rootNode()
    base_layer = dup_doc.createNode("BASE", "paintlayer")
    dup_root.addChildNode(base_layer, None)
    base_layer.setPixelData(bytes(src_bytes), 0, 0, w, h)
    dup_doc.refreshProjection()

    # Show duplicate as a tab
    try:
        win = app.activeWindow()
        if win:
            view = win.addView(dup_doc)
            try:
                win.setActiveView(view)
            except Exception:
                try:
                    win.activateView(view)
                except Exception:
                    pass
    except Exception:
        pass

    # ---------------------------------------------------------------------
    # 1) IDENTICAL (exact RGB matches, 2+)
    # ---------------------------------------------------------------------
    exact_map = {}  # key -> list of indices
    for c in colors:
        exact_map.setdefault(c["key"], []).append(c["idx"])

    identical_keys = [k for k, members in exact_map.items() if len(members) >= 2]
    identical_keys.sort()

    grp_identical = _make_group(dup_doc, GROUP_IDENTICAL)

    for key in identical_keys:
        members = sorted(exact_map[key])
        rep = colors[members[0]]
        rgba = (rep["r"], rep["g"], rep["b"], 255)

        layer_name = f"dup RGB({key}) idx {','.join(str(i) for i in members)}"
        lyr = _make_paint_layer(dup_doc, grp_identical, layer_name)

        buf = _blank_rgba_buffer(w, h)
        for midx in members:
            c = colors[midx]
            _set_block(buf, w, c["x"], c["y"], CELL, rgba)

        lyr.setPixelData(bytes(buf), 0, 0, w, h)

    # ---------------------------------------------------------------------
    # 2) SIMILAR (transitive clustering, 2+)
    # ---------------------------------------------------------------------
    uf = UnionFind(len(colors))
    for a in range(len(colors)):
        for b in range(a + 1, len(colors)):
            if is_similar(colors[a], colors[b]):
                uf.union(a, b)

    clusters = {}  # root -> list of indices
    for i in range(len(colors)):
        root = uf.find(i)
        clusters.setdefault(root, []).append(i)

    cluster_list = [sorted(v) for v in clusters.values() if len(v) >= 2]
    cluster_list.sort(key=lambda lst: min(lst))

    grp_similar = _make_group(dup_doc, GROUP_SIMILAR)

    for members in cluster_list:
        rep = colors[members[0]]
        layer_name = f"sim RGB({rep['r']},{rep['g']},{rep['b']}) idx {','.join(str(i) for i in members)}"
        lyr = _make_paint_layer(dup_doc, grp_similar, layer_name)

        buf = _blank_rgba_buffer(w, h)

        # Paint each block using its own colour
        for midx in members:
            c = colors[midx]
            rgba = (c["r"], c["g"], c["b"], 255)
            _set_block(buf, w, c["x"], c["y"], CELL, rgba)

        lyr.setPixelData(bytes(buf), 0, 0, w, h)

    dup_doc.refreshProjection()

    # ---------------------------------------------------------------------
    # Done message
    # ---------------------------------------------------------------------
    msg = (
        "Done.\n\n"
        "Original document was NOT modified.\n"
        f"Output is in the DUPLICATE document:\n  {dup_name}\n\n"
        f"IDENTICAL sets: {len(identical_keys)} (group '{GROUP_IDENTICAL}')\n"
        f"SIMILAR clusters: {len(cluster_list)} (group '{GROUP_SIMILAR}')\n\n"
        f"SIMILAR threshold (weighted RGB distance) <= {SIM_MAX_DIST}\n"
        + ("SIMILAR excludes exact matches." if SIM_EXCLUDE_EXACT else "SIMILAR includes exact matches.")
    )
    _show_done_message(msg)

# Run the script
main()