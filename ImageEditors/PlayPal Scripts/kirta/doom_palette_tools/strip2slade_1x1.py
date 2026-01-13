# -*- coding: utf-8 -*-
"""
Krita: 256x1 palette strip -> SlaDE-style palette PNG (128x128, 16x16 of 8x8 blocks)
SILENT export (no dialog), overwrite, with:
  - compression = 0 (no compression)
  - indexed = True (save as indexed PNG, if possible)
  - interlaced = False
  - saveSRGBProfile = False
  - forceSRGB = False
  - alpha = False

Input: ACTIVE document must be 256x1.
Output: <stripBase>_8x8-16x16.png saved next to source if possible, else Desktop.
Opens the saved PNG in Krita after export.
"""

from krita import Krita, InfoObject
import os

def _u8(v):
    """Convert a byte/bytes/int channel value into an int 0..255."""
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
        print("No active document. Open your 256x1 palette strip first.")
        return

    src_w = src.width()
    src_h = src.height()

    if src_w != 256 or src_h != 1:
        print("Expected a 256x1 image. Got {}x{}.".format(src_w, src_h))
        return

    # Assumption: strip is RGBA/U8 in Krita (common for PNG).
    # If it isn't, convert it:
    # Image > Convert Image Color Space... -> RGBA, 8-bit integer (U8)
    bpp = 4  # RGBA/U8

    # Read strip pixels once
    src_bytes = src.pixelData(0, 0, src_w, src_h)

    def get_rgba_at(x):
        i = x * bpp
        r = _u8(src_bytes[i + 0])
        g = _u8(src_bytes[i + 1])
        b = _u8(src_bytes[i + 2])
        a = _u8(src_bytes[i + 3])
        return (r, g, b, a)

    # Output: 128x128 (16x16 cells, each 8x8)
    grid = 16
    cell = 8
    out_w = grid * cell   # 128
    out_h = grid * cell   # 128

    # Build output filename
    src_path = src.fileName() or ""
    if src_path:
        src_base = os.path.splitext(os.path.basename(src_path))[0]
        folder = os.path.dirname(src_path)
    else:
        src_base = "palette_strip"
        folder = os.path.expanduser("~/Desktop")

    # Remove common suffix if present
    src_base = src_base.replace("_256x1", "")
    src_base = safe_basename(src_base)

    out_base = src_base + "_8x8-16x16"
    out_name = out_base + "_128x128"
    save_path = os.path.join(folder, out_base + ".png")

    # Create output doc (RGBA/U8)
    out_doc = app.createDocument(out_w, out_h, out_name, "RGBA", "U8", "", 72.0)
    if out_doc is None:
        print("Failed to create output document.")
        return

    out_root = out_doc.rootNode()
    out_layer = out_doc.createNode("slade_palette", "paintlayer")
    out_root.addChildNode(out_layer, None)

    # Build output buffer (RGBA)
    out_buf = bytearray(out_w * out_h * 4)

    def set_pixel(px, py, rgba):
        j = (py * out_w + px) * 4
        out_buf[j + 0] = int(rgba[0]) & 0xFF
        out_buf[j + 1] = int(rgba[1]) & 0xFF
        out_buf[j + 2] = int(rgba[2]) & 0xFF
        out_buf[j + 3] = int(rgba[3]) & 0xFF

    # Fill each 8x8 cell from the strip, row-major order
    for idx in range(256):
        rgba = get_rgba_at(idx)
        row = idx // grid
        col = idx % grid

        x0 = col * cell
        y0 = row * cell

        for yy in range(y0, y0 + cell):
            for xx in range(x0, x0 + cell):
                set_pixel(xx, yy, rgba)

    # Write pixels to layer
    out_layer.setPixelData(bytes(out_buf), 0, 0, out_w, out_h)
    out_doc.refreshProjection()

    # --- SILENT EXPORT SETTINGS (no dialog) ---
    export_params = InfoObject()
    export_params.setProperty("compression", 0)          # no compression
    export_params.setProperty("indexed", True)           # indexed if possible
    export_params.setProperty("interlaced", False)       # no interlace
    export_params.setProperty("saveSRGBProfile", False)  # don't embed sRGB profile
    export_params.setProperty("forceSRGB", False)        # don't force convert to sRGB
    export_params.setProperty("alpha", False)            # don't store alpha

    out_doc.setBatchmode(True)                           # suppress export dialogs
    ok = out_doc.exportImage(save_path, export_params)   # overwrite silently
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
