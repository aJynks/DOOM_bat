/**  Photoshop ExtendScript (JSX)
 *  SLADE palette PNG export (expected 128x128, 16x16 grid, each cell 8x8).
 *
 *  DOES BOTH:
 *   1) IDENTICAL (exact RGB match)  -> group "IDENTICAL", one layer per exact colour, contains all matching 8x8 blocks
 *   2) SIMILAR   (perceptual-ish)   -> group "SIMILAR",  one layer per similar cluster, contains all member 8x8 blocks
 *
 *  Original document is NOT modified:
 *   - Creates a DUPLICATE document and converts THAT duplicate to RGB.
 *
 *  SIMILAR metric (fractional "between 3 and 4" tuning):
 *   - Uses a weighted RGB distance (luma-weighted) so SIM_MAX_DIST can be fractional.
 *   - Similar clustering is TRANSITIVE (union-find). With higher thresholds, ramps can chain together.
 *
 *  IMPORTANT: No ColorSamplers (avoids “Make is not currently available”).
 */

#target photoshop
app.bringToFront();

(function () {
    if (app.documents.length === 0) {
        alert("No document is open.");
        return;
    }

    // -------------------- USER TUNABLES --------------------
    // Perceptual-ish distance threshold (fractional). Try 3.6–4.2 for Doom palettes.
    var SIM_MAX_DIST = 1.1;

    // If true, SIMILAR excludes exact duplicates (so IDENTICAL handles those).
    var SIM_EXCLUDE_EXACT = true;

    // -------------------- CONSTANTS --------------------
    var GRID = 16;
    var CELL = 8;
    var GROUP_IDENTICAL = "IDENTICAL";
    var GROUP_SIMILAR   = "SIMILAR";

    var srcDoc = app.activeDocument;

    // ---- Duplicate doc (original untouched) ----
    var workDoc;
    try {
        workDoc = srcDoc.duplicate(srcDoc.name.replace(/\.[^\.]+$/, "") + "_DUP_ID_SIM", false);
        app.activeDocument = workDoc;
    } catch (eDup) {
        alert("Failed to duplicate the document.\n\n" + eDup);
        return;
    }

    // ---- Ensure RGB on the DUPLICATE ----
    try {
        if (workDoc.mode !== DocumentMode.RGB) {
            workDoc.changeMode(ChangeMode.RGB);
        }
    } catch (eMode) {
        alert("Failed to convert the DUPLICATE document to RGB.\n\n" + eMode);
        return;
    }

    // ---- Validate geometry ----
    var w = workDoc.width.as("px");
    var h = workDoc.height.as("px");
    if (w !== GRID * CELL || h !== GRID * CELL) {
        alert("Unexpected document size: " + w + "x" + h + " px\nExpected 128x128 (16x16 of 8x8 blocks).");
        return;
    }

    // ---- Helpers ----
    function setForegroundToRGB(r, g, b) {
        var c = new SolidColor();
        c.rgb.red = r;
        c.rgb.green = g;
        c.rgb.blue = b;
        app.foregroundColor = c;
    }

    function fillRectOnActiveLayer(doc, x, y, size) {
        doc.selection.select([
            [x, y],
            [x + size, y],
            [x + size, y + size],
            [x, y + size]
        ]);
        doc.selection.fill(app.foregroundColor, ColorBlendMode.NORMAL, 100, false);
        doc.selection.deselect();
    }

    function findHistogramValue(hist) {
        for (var i = 0; i < 256; i++) {
            if (hist[i] > 0) return i;
        }
        return 0;
    }

    function rgbKey(r, g, b) { return r + "," + g + "," + b; }

    function findLayerSetByName(doc, name) {
        for (var i = 0; i < doc.layerSets.length; i++) {
            if (doc.layerSets[i].name === name) return doc.layerSets[i];
        }
        return null;
    }

    function recreateGroup(doc, name) {
        var existing = findLayerSetByName(doc, name);
        if (existing) {
            try { existing.remove(); } catch (_) {}
        }
        var g = doc.layerSets.add();
        g.name = name;
        return g;
    }

    // ---- Union-Find (disjoint sets) for SIMILAR clustering ----
    function UF(n) {
        this.p = [];
        this.r = [];
        for (var i = 0; i < n; i++) { this.p[i] = i; this.r[i] = 0; }
    }
    UF.prototype.find = function (x) {
        var p = this.p[x];
        if (p !== x) this.p[x] = this.find(p);
        return this.p[x];
    };
    UF.prototype.union = function (a, b) {
        var ra = this.find(a), rb = this.find(b);
        if (ra === rb) return;
        if (this.r[ra] < this.r[rb]) this.p[ra] = rb;
        else if (this.r[ra] > this.r[rb]) this.p[rb] = ra;
        else { this.p[rb] = ra; this.r[ra]++; }
    };

    // ---- SIMILAR test (fractional threshold) ----
    function isSimilar(a, b) {
        var dr = Math.abs(a.r - b.r);
        var dg = Math.abs(a.g - b.g);
        var db = Math.abs(a.b - b.b);

        if (SIM_EXCLUDE_EXACT && dr === 0 && dg === 0 && db === 0) return false;

        // Weighted RGB distance (luma-ish weighting). Lets SIM_MAX_DIST be fractional.
        var d = Math.sqrt(
            (0.299 * dr) * (0.299 * dr) +
            (0.587 * dg) * (0.587 * dg) +
            (0.114 * db) * (0.114 * db)
        );

        return d <= SIM_MAX_DIST;
    }

    // ---- Sample RGB for each of the 256 cells (no Color Samplers) ----
    // colors[idx] = {idx,x,y,r,g,b,key}
    var colors = new Array(GRID * GRID);

    var oldDialogs = app.displayDialogs;
    app.displayDialogs = DialogModes.NO;

    var tmp = null;
    var oldRuler = app.preferences.rulerUnits;

    try {
        app.preferences.rulerUnits = Units.PIXELS;

        tmp = workDoc.duplicate("TMP_SAMPLE", true); // merged copy for fast crop/hist
        if (tmp.mode !== DocumentMode.RGB) tmp.changeMode(ChangeMode.RGB);

        var baseState = tmp.activeHistoryState;

        for (var gy = 0; gy < GRID; gy++) {
            for (var gx = 0; gx < GRID; gx++) {
                var x0 = gx * CELL;
                var y0 = gy * CELL;
                var sx = x0 + Math.floor(CELL / 2);
                var sy = y0 + Math.floor(CELL / 2);

                tmp.activeHistoryState = baseState;

                tmp.crop([
                    UnitValue(sx, "px"),
                    UnitValue(sy, "px"),
                    UnitValue(sx + 1, "px"),
                    UnitValue(sy + 1, "px")
                ]);

                var r = findHistogramValue(tmp.channels.getByName("Red").histogram);
                var g = findHistogramValue(tmp.channels.getByName("Green").histogram);
                var b = findHistogramValue(tmp.channels.getByName("Blue").histogram);

                var idx = (gy * GRID) + gx;

                colors[idx] = {
                    idx: idx,
                    x: x0, y: y0,
                    r: r, g: g, b: b,
                    key: rgbKey(r, g, b)
                };
            }
        }
    } catch (eSample) {
        alert("Sampling failed.\n\n" + eSample);
        try { if (tmp) tmp.close(SaveOptions.DONOTSAVECHANGES); } catch (_) {}
        app.displayDialogs = oldDialogs;
        app.preferences.rulerUnits = oldRuler;
        return;
    } finally {
        try { if (tmp) tmp.close(SaveOptions.DONOTSAVECHANGES); } catch (_) {}
        app.displayDialogs = oldDialogs;
        app.preferences.rulerUnits = oldRuler;
    }

    // =====================================================================
    // 1) IDENTICAL (exact RGB matches)
    // =====================================================================
    var exactMap = {}; // key -> array of indices
    for (var i = 0; i < colors.length; i++) {
        var k = colors[i].key;
        if (!exactMap[k]) exactMap[k] = [];
        exactMap[k].push(i);
    }

    var identicalKeys = [];
    for (var k2 in exactMap) {
        if (exactMap.hasOwnProperty(k2) && exactMap[k2].length >= 2) identicalKeys.push(k2);
    }
    identicalKeys.sort();

    var grpIdentical = recreateGroup(workDoc, GROUP_IDENTICAL);

    for (var ik = 0; ik < identicalKeys.length; ik++) {
        var key = identicalKeys[ik];
        var members = exactMap[key].slice(0).sort(function(a,b){return a-b;});

        var rep = colors[members[0]];

        var lyrI = workDoc.artLayers.add();
        lyrI.name = "dup RGB(" + key + ") idx " + members.join(",");
        lyrI.move(grpIdentical, ElementPlacement.INSIDE);

        setForegroundToRGB(rep.r, rep.g, rep.b);

        for (var mI = 0; mI < members.length; mI++) {
            var colI = colors[members[mI]];
            fillRectOnActiveLayer(workDoc, colI.x, colI.y, CELL);
        }
    }

    // =====================================================================
    // 2) SIMILAR (perceptual-ish, transitive clustering)
    // =====================================================================
    var uf = new UF(colors.length);

    for (var a = 0; a < colors.length; a++) {
        for (var b2 = a + 1; b2 < colors.length; b2++) {
            if (isSimilar(colors[a], colors[b2])) {
                uf.union(a, b2);
            }
        }
    }

    var clusters = {}; // root -> array of indices
    for (var c = 0; c < colors.length; c++) {
        var root = uf.find(c);
        if (!clusters[root]) clusters[root] = [];
        clusters[root].push(c);
    }

    var clusterList = [];
    for (var root2 in clusters) {
        if (clusters.hasOwnProperty(root2) && clusters[root2].length >= 2) {
            clusterList.push(clusters[root2]);
        }
    }

    clusterList.sort(function (x, y) {
        var xmin = Math.min.apply(null, x);
        var ymin = Math.min.apply(null, y);
        return xmin - ymin;
    });

    var grpSimilar = recreateGroup(workDoc, GROUP_SIMILAR);

    for (var cc = 0; cc < clusterList.length; cc++) {
        var membersS = clusterList[cc].slice(0).sort(function(a,b){return a-b;});
        var repS = colors[membersS[0]];

        var lyrS = workDoc.artLayers.add();
        lyrS.name = "sim RGB(" + repS.r + "," + repS.g + "," + repS.b + ") idx " + membersS.join(",");
        lyrS.move(grpSimilar, ElementPlacement.INSIDE);

        // Paint each block using its own colour (so you can see small differences)
        for (var ms = 0; ms < membersS.length; ms++) {
            var colS = colors[membersS[ms]];
            setForegroundToRGB(colS.r, colS.g, colS.b);
            fillRectOnActiveLayer(workDoc, colS.x, colS.y, CELL);
        }
    }

    // ---- Done ----
    alert(
        "Done.\n\n" +
        "Original document was NOT modified.\n" +
        "Output is in the DUPLICATE document:\n  " + workDoc.name + "\n\n" +
        "IDENTICAL sets: " + identicalKeys.length + " (group '" + GROUP_IDENTICAL + "')\n" +
        "SIMILAR clusters: " + clusterList.length + " (group '" + GROUP_SIMILAR + "')\n\n" +
        "SIMILAR threshold (weighted RGB distance) <= " + SIM_MAX_DIST +
        (SIM_EXCLUDE_EXACT ? "\nSIMILAR excludes exact matches." : "\nSIMILAR includes exact matches.")
    );

})();
