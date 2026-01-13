/** SladePaletteToStrip_FAST_8x8.jsx
 *  FAST method:
 *  - Takes the active document (a SlaDE palette PNG: 16x16 swatches, usually 128x128)
 *  - Duplicates it and resizes duplicate to 16x16 (Nearest Neighbor) so each swatch becomes 1 pixel
 *  - Copies each row (16x1) and pastes into a 256x1 output strip
 *  - Then upscales the strip to 2048x8 (each colour becomes an 8x8 block) using Nearest Neighbor
 *
 *  Output order: row-major (left->right across top row, then next row), index 0..255.
 */

#target photoshop
app.bringToFront();

(function () {
    if (!app.documents.length) {
        alert("No document is open.\nOpen your SlaDE palette PNG first, then run this script.");
        return;
    }

    var src = app.activeDocument;

    // --- Save/restore prefs ---
    var oldRulerUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;

    try {
        var srcW = src.width.as("px");
        var srcH = src.height.as("px");

        // Validate that this is a 16x16 swatch grid (dimensions divisible by 16)
        if ((srcW % 16) !== 0 || (srcH % 16) !== 0) {
            alert("Source image dimensions must be divisible by 16.\nWidth: " + srcW + " Height: " + srcH);
            return;
        }

        var baseName = src.name.replace(/\.[^\.]+$/, "");

        // 1) Duplicate source and downsample to 16x16 using nearest neighbour
        var tmp = src.duplicate(baseName + "_tmp16x16", false);
        app.activeDocument = tmp;

        tmp.resizeImage(UnitValue(16, "px"), UnitValue(16, "px"), tmp.resolution, ResampleMethod.NEARESTNEIGHBOR);

        // Flatten to simplify copy
        try { tmp.flatten(); } catch (e0) {}

        // 2) Create output document 256x1 (then upscale to 2048x8)
        var outName = baseName + "_256x1_8x8strip";
        var out = app.documents.add(
            256, 1,
            src.resolution,
            outName,
            NewDocumentMode.RGB,
            DocumentFill.TRANSPARENT
        );

        function snapLayerTopLeftToOrigin(layer) {
            var b = layer.bounds; // [left, top, right, bottom]
            var left = b[0].as("px");
            var top  = b[1].as("px");
            layer.translate(-left, -top);
        }

        // 3) Copy each row (16 pixels) and paste into output at x = row*16
        for (var row = 0; row < 16; row++) {
            app.activeDocument = tmp;

            tmp.selection.select([
                [0, row],
                [16, row],
                [16, row + 1],
                [0, row + 1]
            ]);

            tmp.selection.copy();
            tmp.selection.deselect();

            app.activeDocument = out;
            out.paste();

            var layer = out.activeLayer;
            snapLayerTopLeftToOrigin(layer);
            layer.translate(row * 16, 0);
        }

        // Merge pasted rows into one layer
        app.activeDocument = out;
        try { out.mergeVisibleLayers(); } catch (e1) {}

        // Close temp doc without saving
        app.activeDocument = tmp;
        tmp.close(SaveOptions.DONOTSAVECHANGES);

        // 4) Upscale 256x1 -> 2048x8 (each colour becomes 8x8)
        app.activeDocument = out;
        out.resizeImage(UnitValue(2048, "px"), UnitValue(8, "px"), out.resolution, ResampleMethod.NEARESTNEIGHBOR);

        // Leave output active
        app.activeDocument = out;

        // Optional auto-save (uncomment to enable)
        /*
        if (src.path) {
            var saveFile = new File(src.path.fsName + "/" + baseName + "_256x8x8.png");
            var pngOpts = new PNGSaveOptions();
            out.saveAs(saveFile, pngOpts, true, Extension.LOWERCASE);
        }
        */

    } catch (err) {
        alert("Error:\n" + err);
    } finally {
        app.preferences.rulerUnits = oldRulerUnits;
    }
})();
