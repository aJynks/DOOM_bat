/** SladePaletteToStrip_FAST_v2_SAVE.jsx
 *  FAST + correct placement + optional auto-save
 *
 *  - Takes the active document (SlaDE palette PNG: 16x16 swatches)
 *  - Duplicates it and resizes to 16x16 using Nearest Neighbor
 *  - Copies each 16px row and pastes into a 256x1 output image
 *  - Snaps pasted rows to (0,0) (Photoshop paste is centered), then positions them
 *  - Optionally auto-saves the output PNG next to the source file
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
        // --- Validate source ---
        var srcW = src.width.as("px");
        var srcH = src.height.as("px");

        if ((srcW % 16) !== 0 || (srcH % 16) !== 0) {
            alert("Source image dimensions must be divisible by 16.\nWidth: " + srcW + " Height: " + srcH);
            return;
        }

        // --- Duplicate and downsample to 16x16 (Nearest Neighbor) ---
        var baseName = src.name.replace(/\.[^\.]+$/, "");
        var tmpName = baseName + "_tmp16x16";
        var tmp = src.duplicate(tmpName, false);
        app.activeDocument = tmp;

        tmp.resizeImage(
            UnitValue(16, "px"),
            UnitValue(16, "px"),
            tmp.resolution,
            ResampleMethod.NEARESTNEIGHBOR
        );

        // Flatten to simplify copy ops
        try { tmp.flatten(); } catch (e0) {}

        // --- Create output document 256x1 ---
        var outName = baseName + "_256x1";
        var out = app.documents.add(
            256, 1,
            src.resolution,
            outName,
            NewDocumentMode.RGB,
            DocumentFill.TRANSPARENT
        );

        // Helper: after paste, snap the pasted layer’s top-left to (0,0)
        // because Photoshop paste is centred by default.
        function snapLayerTopLeftToOrigin(layer) {
            var b = layer.bounds; // [left, top, right, bottom]
            var left = b[0].as("px");
            var top  = b[1].as("px");
            layer.translate(-left, -top);
        }

        // --- Copy each row from 16x16 and paste into 256x1 ---
        for (var row = 0; row < 16; row++) {
            app.activeDocument = tmp;

            // Select row: x 0..16, y row..row+1 (16x1 pixels)
            tmp.selection.select([
                [0, row],
                [16, row],
                [16, row + 1],
                [0, row + 1]
            ]);

            tmp.selection.copy();
            tmp.selection.deselect();

            app.activeDocument = out;
            out.paste(); // new layer

            var layer = out.activeLayer;

            // Snap to origin, then place at correct offset
            snapLayerTopLeftToOrigin(layer);
            layer.translate(row * 16, 0);
        }

        // Merge into one layer
        app.activeDocument = out;
        try { out.mergeVisibleLayers(); } catch (e1) {}

        // Close temp doc without saving
        app.activeDocument = tmp;
        tmp.close(SaveOptions.DONOTSAVECHANGES);

        // Leave output active
        app.activeDocument = out;

        // --- OPTIONAL AUTO-SAVE (uncomment to enable) ---
        /**/
        if (src.path) {
            var saveFile = new File(src.path + "/" + outName + ".png");
            var pngOpts = new PNGSaveOptions();
            out.saveAs(saveFile, pngOpts, true, Extension.LOWERCASE);
        } else {
            // If the source was never saved to disk, src.path won't exist.
            // Uncomment this alert if you want a message in that case.
            // alert("Source document has no path (was not opened from disk), so auto-save was skipped.");
        }
        

    } catch (err) {
        alert("Error:\n" + err);
    } finally {
        app.preferences.rulerUnits = oldRulerUnits;
    }
})();
