/** Strip2048x8_To_SLADE_Grid_SILENT.jsx
 *
 *  Reverse (for the 8x8 “pixel strip” version):
 *    2048x8 strip (256 colours, each 8x8) ->
 *    downsample to 256x1 (Nearest Neighbor) ->
 *    build 16x16 (1px per entry) ->
 *    upsample to 128x128 (8x8 swatches, SlaDE-style)
 *
 *  Output filename:
 *    <stripBase>_8x8-16x16.png
 *    e.g. pal00_256x8x8.png -> pal00_8x8-16x16.png
 */

#target photoshop
app.bringToFront();

(function () {
    if (!app.documents.length) {
        alert("No document is open.\nOpen your 2048x8 palette strip first, then run this script.");
        return;
    }

    var src = app.activeDocument;

    var oldRulerUnits = app.preferences.rulerUnits;
    var oldDialogs    = app.displayDialogs;
    app.preferences.rulerUnits = Units.PIXELS;

    try {
        // --- Validate source strip (8x8 blocks): 2048x8 ---
        var srcW = src.width.as("px");
        var srcH = src.height.as("px");
        if (srcW !== 2048 || srcH !== 8) {
            alert("Expected a 2048x8 image (256 colours as 8x8 blocks).\nGot: " + srcW + "x" + srcH);
            return;
        }

        var grid = 16;
        var swatchSize = 8;
        var outSize = grid * swatchSize; // 128

        function stripExt(name) { return name.replace(/\.[^\.]+$/, ""); }
        function safeFileName(name) { return name.replace(/[\\\/:\*\?"<>\|]/g, "_"); }

        // Base name from strip doc name, remove common suffixes if present
        var srcBase = stripExt(src.name)
            .replace(/_256x1$/i, "")
            .replace(/_256x8x8$/i, "")
            .replace(/_8x8strip$/i, "")
            .replace(/_256x1_8x8strip$/i, "")
            .replace(/_256x8x8strip$/i, "");

        srcBase = safeFileName(srcBase);

        var outBaseName = srcBase + "_8x8-16x16";
        var outDocName  = outBaseName + "_" + outSize + "x" + outSize;
        var outFileName = outBaseName + ".png";

        // --- Step 1: Duplicate and downsample 2048x8 -> 256x1 (Nearest Neighbor) ---
        var tmpStrip = src.duplicate(srcBase + "_tmp256x1", false);
        app.activeDocument = tmpStrip;

        tmpStrip.resizeImage(
            UnitValue(256, "px"),
            UnitValue(1, "px"),
            tmpStrip.resolution,
            ResampleMethod.NEARESTNEIGHBOR
        );

        // Flatten for clean copy
        try { tmpStrip.flatten(); } catch (eS) {}

        // --- Step 2: Create a 16x16 1px-per-entry doc ---
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

        // --- Copy 16 pixels at a time from 256x1 into tmp rows ---
        for (var row = 0; row < 16; row++) {
            app.activeDocument = tmpStrip;

            var x0 = row * 16;
            var x1 = x0 + 16;

            tmpStrip.selection.select([
                [x0, 0],
                [x1, 0],
                [x1, 1],
                [x0, 1]
            ]);

            tmpStrip.selection.copy();
            tmpStrip.selection.deselect();

            app.activeDocument = tmp;
            tmp.paste();

            var layer = tmp.activeLayer;
            snapLayerTopLeftToOrigin(layer);
            layer.translate(0, row);
        }

        // Merge 16 pasted rows into one layer
        app.activeDocument = tmp;
        try { tmp.mergeVisibleLayers(); } catch (e0) {}

        // --- Upscale 16x16 -> 128x128 using Nearest Neighbor (SlaDE-style 8x8 blocks) ---
        tmp.resizeImage(
            UnitValue(outSize, "px"),
            UnitValue(outSize, "px"),
            tmp.resolution,
            ResampleMethod.NEARESTNEIGHBOR
        );

        // Close the temporary downsampled strip without saving
        app.activeDocument = tmpStrip;
        tmpStrip.close(SaveOptions.DONOTSAVECHANGES);

        // --- SILENT SAVE (no prompts, overwrite allowed) ---
        app.displayDialogs = DialogModes.NO;

        // Determine destination folder:
        // Prefer the folder of the opened file (src.fullName.parent).
        // Fall back to src.path, and finally Desktop.
        var destFolder = null;

        try { destFolder = src.fullName.parent; } catch (e1) {}
        if (!destFolder) {
            try { destFolder = src.path; } catch (e2) {}
        }
        if (!destFolder) destFolder = Folder.desktop;

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
