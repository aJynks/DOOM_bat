# -*- coding: utf-8 -*-
"""
Krita: SlaDE palette PNG (16x16 swatches) -> 256x1 strip (1px per colour)

- Input: ACTIVE document is a SlaDE palette export (dimensions divisible by 16)
- Samples the centre pixel of each swatch in row-major order
- Output: 256x1 PNG named <source>_256x1.png
- Silent export (no dialogs), overwrite allowed:
    compression=0, indexed=True, interlaced=False,
    saveSRGBProfile=False, forceSRGB=False, alpha=False
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
        print("No active document. Open your SlaDE palette PNG first.")
        return

    src_w = src.width()
    src_h = src.height()

    if (src_w % 16) != 0 or (src_h % 16) != 0:
        print("Source dimensions must be divisible by 16. Got {}x{}.".format(src_w, src_h))
        return

    bpp = 4  # assume RGBA/U8

    sw = src_w // 16
    sh = src_h // 16
    cx = sw // 2
    cy = sh // 2

    src_bytes = src.pixelData(0, 0, src_w, src_h)

    def get_rgba_at(x, y):
        i = (y * src_w + x) * bpp
        return (
            _u8(src_bytes[i + 0]),
            _u8(src_bytes[i + 1]),
            _u8(src_bytes[i + 2]),
            _u8(src_bytes[i + 3]),
        )

    out_w, out_h = 256, 1

    src_path = src.fileName() or ""
    if src_path:
        src_base = os.path.splitext(os.path.basename(src_path))[0]
        folder = os.path.dirname(src_path)
    else:
        src_base = "palette"
        folder = os.path.expanduser("~/Desktop")

    src_base = safe_basename(src_base)
    out_base = src_base + "_256x1"
    save_path = os.path.join(folder, out_base + ".png")

    out_doc = app.createDocument(out_w, out_h, out_base, "RGBA", "U8", "", 72.0)
    if out_doc is None:
        print("Failed to create output document.")
        return

    out_root = out_doc.rootNode()
    out_layer = out_doc.createNode("strip_256x1", "paintlayer")
    out_root.addChildNode(out_layer, None)

    out_buf = bytearray(out_w * out_h * 4)

    def set_out_pixel(x, rgba):
        j = x * 4
        out_buf[j + 0] = int(rgba[0]) & 0xFF
        out_buf[j + 1] = int(rgba[1]) & 0xFF
        out_buf[j + 2] = int(rgba[2]) & 0xFF
        out_buf[j + 3] = int(rgba[3]) & 0xFF

    # Row-major order: top row left->right, then next row...
    for idx in range(256):
        row = idx // 16
        col = idx % 16
        rgba = get_rgba_at(col * sw + cx, row * sh + cy)
        set_out_pixel(idx, rgba)

    out_layer.setPixelData(bytes(out_buf), 0, 0, out_w, out_h)
    out_doc.refreshProjection()

    export_params = InfoObject()
    export_params.setProperty("compression", 0)
    export_params.setProperty("indexed", True)
    export_params.setProperty("interlaced", False)
    export_params.setProperty("saveSRGBProfile", False)
    export_params.setProperty("forceSRGB", False)
    export_params.setProperty("alpha", False)

    out_doc.setBatchmode(True)
    ok = out_doc.exportImage(save_path, export_params)
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

        # addView creates a visible tab/view for the document
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

# Krita menu calls main(); keep this so it also runs if executed directly
main()
