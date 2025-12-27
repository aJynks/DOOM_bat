# -*- coding: utf-8 -*-
"""
Krita: 2048x8 strip (256 colours as 8x8 blocks) -> SlaDE palette PNG (128x128, 16x16 of 8x8 blocks)

Input: ACTIVE document must be 2048x8.
Output: <stripBase>_8x8-16x16.png saved next to source if possible, else Desktop.

Silent export (no dialog, overwrite) with:
  - compression = 0 (no compression)
  - indexed = True (save as indexed PNG, if possible)
  - interlaced = False
  - saveSRGBProfile = False
  - forceSRGB = False
  - alpha = False

Opens the saved PNG in Krita after export.
"""

from krita import Krita, InfoObject
import os

def _u8(v):
    if isinstance(v, int):
        return v
    if isinstance(v, (bytes, bytearray)):
        return v[0]
    return int(v)

def safe_basename(name):
    return "".join("_" if c in '\\/:*?"<>|' else c for c in name)

def main():
    app = Krita.instance()
    src = app.activeDocument()
    if src is None:
        print("No active document.")
        return

    src_w = src.width()
    src_h = src.height()

    if src_w != 2048 or src_h != 8:
        print("Expected a 2048x8 image (256 colours as 8x8 blocks). Got {}x{}.".format(src_w, src_h))
        return

    # Assume RGBA / U8
    bpp = 4

    # Read source pixels once
    src_bytes = src.pixelData(0, 0, src_w, src_h)

    def get_rgba_at(x, y):
        i = (y * src_w + x) * bpp
        return (
            _u8(src_bytes[i + 0]),
            _u8(src_bytes[i + 1]),
            _u8(src_bytes[i + 2]),
            _u8(src_bytes[i + 3]),
        )

    # Output is 128x128 (16x16 cells, each 8x8)
    grid = 16
    cell = 8
    out_w = grid * cell  # 128
    out_h = grid * cell  # 128

    src_path = src.fileName() or ""
    if src_path:
        src_base = os.path.splitext(os.path.basename(src_path))[0]
        folder = os.path.dirname(src_path)
    else:
        src_base = "strip_256x8x8"
        folder = os.path.expanduser("~/Desktop")

    # Remove common suffixes
    src_base = src_base.replace("_256x8x8", "").replace("_8x8strip", "")
    src_base = safe_basename(src_base)

    out_base = src_base + "_8x8-16x16"
    save_path = os.path.join(folder, out_base + ".png")

    # Create output document
    out_doc = app.createDocument(out_w, out_h, out_base + "_128x128", "RGBA", "U8", "", 72.0)
    if out_doc is None:
        print("Failed to create output document.")
        return

    out_root = out_doc.rootNode()
    out_layer = out_doc.createNode("slade_palette", "paintlayer")
    out_root.addChildNode(out_layer, None)

    out_buf = bytearray(out_w * out_h * 4)

    def set_pixel(x, y, rgba):
        j = (y * out_w + x) * 4
        out_buf[j + 0] = int(rgba[0]) & 0xFF
        out_buf[j + 1] = int(rgba[1]) & 0xFF
        out_buf[j + 2] = int(rgba[2]) & 0xFF
        out_buf[j + 3] = int(rgba[3]) & 0xFF

    # For each colour index i:
    # sample the centre of each 8x8 block in the strip at (i*8+4, 4)
    # then fill the corresponding 8x8 cell in the 16x16 output grid.
    for idx in range(256):
        sx = idx * cell + (cell // 2)  # idx*8 + 4
        sy = cell // 2                 # 4
        rgba = get_rgba_at(sx, sy)

        row = idx // grid
        col = idx % grid

        x0 = col * cell
        y0 = row * cell

        for yy in range(y0, y0 + cell):
            for xx in range(x0, x0 + cell):
                set_pixel(xx, yy, rgba)

    out_layer.setPixelData(bytes(out_buf), 0, 0, out_w, out_h)
    out_doc.refreshProjection()

    # --- Silent PNG export ---
    export = InfoObject()
    export.setProperty("compression", 0)          # no compression
    export.setProperty("indexed", True)           # indexed if possible
    export.setProperty("interlaced", False)
    export.setProperty("saveSRGBProfile", False)
    export.setProperty("forceSRGB", False)
    export.setProperty("alpha", False)

    out_doc.setBatchmode(True)
    ok = out_doc.exportImage(save_path, export)
    out_doc.setBatchmode(False)

    if not ok:
        print("Export failed:", save_path)
        return

    print("Saved:", save_path)

    # --- Open the saved file and show it in the active window ---
    try:
        opened = app.openDocument(save_path)
        if opened is None:
            print("Saved, but Krita returned no document from openDocument().")
            return

        win = app.activeWindow()
        if win is None:
            print("Saved, but no active window to show the document in.")
            return

        view = win.addView(opened)

        # Try to focus it (API differs between builds; safe attempts)
        try:
            win.setActiveView(view)
        except Exception:
            try:
                win.activateView(view)
            except Exception:
                pass

    except Exception as e:
        print("Saved, but failed to open/show file:", e)

main()
