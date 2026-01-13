/** Strip256x1_To_SLADE_Grid_v2_SILENT.jsx
 *
 *  Reverse:
 *    256x1 strip  ->  16x16 (1px per entry)  ->  upsample to 128x128 (8x8 swatches)
 *
 *  Output filename:
 *    <stripBase>_8x8-16x16.png
 *    e.g. pal00_256x1.png -> pal00_8x8-16x16.png
 */

#target photoshop
app.bringToFront();

(function () {
    if (!app.documents.length) {
        alert("No document is open.\nOpen your 256x1 palette strip first, then run this script.");
        return;
    }

    var src = app.activeDocument;

    var oldRulerUnits = app.preferences.rulerUnits;
    var oldDialogs    = app.displayDialogs;
    app.preferences.rulerUnits = Units.PIXELS;

    try {
        // --- Validate source strip ---
        var srcW = src.width.as("px");
        var srcH = src.height.as("px");
        if (srcW !== 256 || srcH !== 1) {
            alert("Expected a 256x1 image.\nGot: " + srcW + "x" + srcH);
            return;
        }

        var grid = 16;
        var swatchSize = 8;
        var outSize = grid * swatchSize; // 128

        function stripExt(name) { return name.replace(/\.[^\.]+$/, ""); }
        function safeFileName(name) { return name.replace(/[\\\/:\*\?"<>\|]/g, "_"); }

        // Base name derived from STRIP doc name, with _256x1 removed if present
        var srcBase = stripExt(src.name).replace(/_256x1$/i, "");
        srcBase = safeFileName(srcBase);

        var outBaseName = srcBase + "_8x8-16x16";
        var outDocName  = outBaseName + "_" + outSize + "x" + outSize;
        var outFileName = outBaseName + ".png";

        // --- Create a 16x16 1px-per-entry doc ---
        var tmp = app.documents.add(
            16, 16,
            src.resolution,
            outDocName,
            NewDocumentMode.RGB,
            DocumentFill.TRANSPARENT
        );

        function snapLayerTopLeftToOrigin(layer) {
            var b = layer.bounds;
            layer.translate(-b[0].as("px"), -b[1].as("px"));
        }

        // --- Copy 16 pixels at a time from strip into tmp rows ---
        for (var row = 0; row < 16; row++) {
            app.activeDocument = src;

            var x0 = row * 16;
            var x1 = x0 + 16;

            src.selection.select([
                [x0, 0],
                [x1, 0],
                [x1, 1],
                [x0, 1]
            ]);

            src.selection.copy();
            src.selection.deselect();

            app.activeDocument = tmp;
            tmp.paste();

            var layer = tmp.activeLayer;
            snapLayerTopLeftToOrigin(layer);
            layer.translate(0, row);
        }

        // Merge to one layer
        app.activeDocument = tmp;
        try { tmp.mergeVisibleLayers(); } catch (e0) {}

        // Upscale to 128x128 using Nearest Neighbor
        tmp.resizeImage(
            UnitValue(outSize, "px"),
            UnitValue(outSize, "px"),
            tmp.resolution,
            ResampleMethod.NEARESTNEIGHBOR
        );

        // --- SILENT SAVE (no prompts, overwrite allowed) ---
        app.displayDialogs = DialogModes.NO;

        // Determine destination folder:
        // Prefer the folder of the opened file (src.fullName.parent).
        // Fall back to src.path, and finally Desktop.
        var destFolder = null;

        try {
            // Works when the doc was opened from disk
            destFolder = src.fullName.parent;
        } catch (e1) {}

        if (!destFolder) {
            try {
                destFolder = src.path; // sometimes available
            } catch (e2) {}
        }

        if (!destFolder) {
            destFolder = Folder.desktop; // last resort, still silent
        }

        var saveFile = new File(destFolder.fsName + "/" + outFileName);
        var pngOpts = new PNGSaveOptions();

        app.activeDocument = tmp;
        tmp.saveAs(saveFile, pngOpts, true, Extension.LOWERCASE);

    } catch (err) {
        alert("Error:\n" + err);
    } finally {
        app.displayDialogs = oldDialogs;
        app.preferences.rulerUnits = oldRulerUnits;
    }
})();
