/**  Photoshop ExtendScript (JSX)
 *  Doom palette duplicate / similarity analyser — UNIFIED, auto-detecting.
 *
 *  SUPPORTED INPUT FORMATS (detected by document dimensions):
 *   A) SLADE palette PNG export:  128x128 px
 *        16x16 grid, each entry an 8x8 solid block. Index order is
 *        left-to-right, top-to-bottom.
 *   B) DoomTools "blank" PLAYPAL PNG:  256 px wide, any height (typically 14)
 *        One pixel per entry. Each ROW is a palette; ROW 0 is pal0 and is
 *        the only row analysed. All painting is done as full-height 1px
 *        columns so results are visible and the REPACK layer can be
 *        flattened straight into a new blank playpal.
 *
 *  DOES THREE THINGS:
 *   1) IDENTICAL (exact RGB match)  -> group "IDENTICAL"
 *        One layer per exact colour. Contains ONLY the redundant copies —
 *        the lowest-index occurrence is KEPT in the palette and is NOT
 *        painted into the group.
 *   2) SIMILAR   (perceptual)       -> group "SIMILAR"
 *        One layer per similar cluster. Contains ONLY the redundant members —
 *        the lowest-index member of each cluster is KEPT and NOT painted.
 *   3) REPACK                        -> group "REPACK"
 *        A single layer showing the palette reorganised: all KEPT colours
 *        packed from slot 0 in their original relative order, and every
 *        cleared slot at the tail filled with cyan (0,255,255).
 *        The cyan is purely a visual marker — those slots are free.
 *
 *  Original document is NOT modified:
 *   - Creates a DUPLICATE document and converts THAT duplicate to RGB.
 *   - Re-running on an existing duplicate REPLACES the three groups.
 *
 *  SIMILARITY METRICS (chosen in the dialog):
 *   - CIE Lab dE76 (default): perceptual distance in L*a*b* space.
 *       Threshold is a Delta-E value. ~1.0 = just-noticeable difference,
 *       2-3 = close colours, 5+ = starts chaining ramps together.
 *   - Weighted RGB (legacy): the original luma-weighted RGB distance.
 *       Old threshold values (1.1 strict, 3.6-4.2 ramps) apply here.
 *   - Similar clustering is TRANSITIVE (union-find). Higher thresholds
 *     can chain ramps together regardless of metric.
 *
 *  IMPORTANT: No ColorSamplers (avoids "Make is not currently available").
 */

#target photoshop
app.bringToFront();

(function () {
    if (app.documents.length === 0) {
        alert("No document is open.");
        return;
    }

    // -------------------- CONSTANTS --------------------
    var ENTRIES = 256;
    var GROUP_IDENTICAL = "IDENTICAL";
    var GROUP_SIMILAR   = "SIMILAR";
    var GROUP_REPACK    = "REPACK";

    // Cyan marker for cleared slots in the REPACK layer.
    // Deliberately synthetic — never appears in a Doom palette.
    var CLEAR_R = 0, CLEAR_G = 255, CLEAR_B = 255;

    // If true, SIMILAR's pairwise test excludes exact duplicates
    // (IDENTICAL handles those). Note: exact dups can still end up in a
    // SIMILAR cluster transitively via a third colour.
    var SIM_EXCLUDE_EXACT = true;

    var DEFAULT_THRESH_LAB = "2.0";
    var DEFAULT_THRESH_RGB = "1.1";

    // SLADE geometry
    var SLADE_GRID = 16;
    var SLADE_CELL = 8;

    // -------------------- SETTINGS DIALOG (ScriptUI) --------------------
    // Returns { useLab: bool, threshold: number } or null on cancel.
    function showSettingsDialog(formatLabel) {
        var dlg = new Window("dialog", "Doom Palette Analyser");
        dlg.orientation = "column";
        dlg.alignChildren = "fill";
        dlg.margins = 16;
        dlg.spacing = 10;

        var fmt = dlg.add("statictext", undefined, "Detected format: " + formatLabel);

        var metricPanel = dlg.add("panel", undefined, "Similarity metric");
        metricPanel.orientation = "column";
        metricPanel.alignChildren = "left";
        metricPanel.margins = 12;

        var rbLab = metricPanel.add("radiobutton", undefined, "CIE Lab \u0394E76 (perceptual, recommended)");
        var rbRgb = metricPanel.add("radiobutton", undefined, "Weighted RGB (legacy)");
        rbLab.value = true;

        var threshPanel = dlg.add("panel", undefined, "Threshold");
        threshPanel.orientation = "column";
        threshPanel.alignChildren = "left";
        threshPanel.margins = 12;

        var hint = threshPanel.add("statictext", undefined, "", { multiline: true });
        hint.preferredSize = [300, 40];

        var threshInput = threshPanel.add("edittext", undefined, DEFAULT_THRESH_LAB);
        threshInput.characters = 8;

        function updateHint() {
            if (rbLab.value) {
                hint.text = "\u0394E: ~1.0 = just noticeable, 2-3 = close,\n5+ = chains ramps together.";
                threshInput.text = DEFAULT_THRESH_LAB;
            } else {
                hint.text = "Weighted RGB: 1.1 = strict,\n3.6-4.2 = finds colour ramps.";
                threshInput.text = DEFAULT_THRESH_RGB;
            }
        }
        rbLab.onClick = updateHint;
        rbRgb.onClick = updateHint;
        updateHint();

        var btnRow = dlg.add("group");
        btnRow.alignment = "right";
        var okBtn = btnRow.add("button", undefined, "OK", { name: "ok" });
        btnRow.add("button", undefined, "Cancel", { name: "cancel" });

        okBtn.onClick = function () {
            var v = parseFloat(threshInput.text);
            if (isNaN(v) || v < 0) {
                alert("Invalid threshold value. Enter a number >= 0.");
                return; // keep dialog open
            }
            dlg.close(1);
        };

        if (dlg.show() !== 1) return null;

        var t = parseFloat(threshInput.text);
        return { useLab: rbLab.value, threshold: t };
    }

    // -------------------- FORMAT DETECTION --------------------
    var srcDoc = app.activeDocument;

    var oldRulerDetect = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;
    var srcW = srcDoc.width.as("px");
    var srcH = srcDoc.height.as("px");
    app.preferences.rulerUnits = oldRulerDetect;

    // MODE holds everything format-specific:
    //   sampleXY(idx) -> {x,y}   pixel to read the entry colour from
    //   paintXY(slot) -> {x,y}   top-left of the paint rectangle for a slot
    //   paintW, paintH           paint rectangle size
    var MODE = null;

    if (srcW === SLADE_GRID * SLADE_CELL && srcH === SLADE_GRID * SLADE_CELL) {
        // ---- SLADE 128x128, 16x16 grid of 8x8 cells ----
        MODE = {
            label: "SLADE (128x128, 8x8 cells)",
            paintW: SLADE_CELL,
            paintH: SLADE_CELL,
            sampleXY: function (idx) {
                var gx = idx % SLADE_GRID;
                var gy = Math.floor(idx / SLADE_GRID);
                return {
                    x: gx * SLADE_CELL + Math.floor(SLADE_CELL / 2),
                    y: gy * SLADE_CELL + Math.floor(SLADE_CELL / 2)
                };
            },
            paintXY: function (slot) {
                return {
                    x: (slot % SLADE_GRID) * SLADE_CELL,
                    y: Math.floor(slot / SLADE_GRID) * SLADE_CELL
                };
            }
        };
    } else if (srcW === ENTRIES && srcH >= 1) {
        // ---- DoomTools blank playpal: 256 wide, one pixel per entry ----
        // Row 0 is pal0 (the only row sampled). Painting is full-height
        // 1px columns so results are visible and REPACK flattens straight
        // into a new blank playpal.
        MODE = {
            label: "DoomTools playpal (256x" + srcH + ", row 0 = pal0)",
            paintW: 1,
            paintH: srcH,
            sampleXY: function (idx) {
                return { x: idx, y: 0 };
            },
            paintXY: function (slot) {
                return { x: slot, y: 0 };
            }
        };
    } else {
        alert(
            "Unexpected document size: " + srcW + "x" + srcH + " px\n\n" +
            "Expected one of:\n" +
            "  128x128  — SLADE palette export (16x16 of 8x8 blocks)\n" +
            "  256xN    — DoomTools blank playpal (1px per entry, row 0 = pal0)"
        );
        return;
    }

    // -------------------- DIALOG --------------------
    var settings = showSettingsDialog(MODE.label);
    if (settings === null) return; // user cancelled

    var USE_LAB      = settings.useLab;
    var SIM_MAX_DIST = settings.threshold;

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

    // ---- Helpers ----
    function setForegroundToRGB(r, g, b) {
        var c = new SolidColor();
        c.rgb.red = r;
        c.rgb.green = g;
        c.rgb.blue = b;
        app.foregroundColor = c;
    }

    function fillRectOnActiveLayer(doc, x, y, w, h) {
        doc.selection.select([
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h]
        ]);
        doc.selection.fill(app.foregroundColor, ColorBlendMode.NORMAL, 100, false);
        doc.selection.deselect();
    }

    function paintEntry(doc, slot) {
        var p = MODE.paintXY(slot);
        fillRectOnActiveLayer(doc, p.x, p.y, MODE.paintW, MODE.paintH);
    }

    // Input is always a solid-colour 1x1 crop, so the single populated
    // histogram bin IS the value. (Do not reuse for multi-colour crops.)
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

    // ---- sRGB -> CIE Lab (D65) ----
    function srgbToLab(r, g, b) {
        function lin(c) {
            c /= 255;
            return (c <= 0.04045) ? (c / 12.92) : Math.pow((c + 0.055) / 1.055, 2.4);
        }
        var R = lin(r), G = lin(g), B = lin(b);

        // sRGB -> XYZ (D65)
        var X = R * 0.4124564 + G * 0.3575761 + B * 0.1804375;
        var Y = R * 0.2126729 + G * 0.7151522 + B * 0.0721750;
        var Z = R * 0.0193339 + G * 0.1191920 + B * 0.9503041;

        // Normalise by D65 white point
        var Xn = 0.95047, Yn = 1.00000, Zn = 1.08883;

        function f(t) {
            return (t > 0.008856) ? Math.pow(t, 1 / 3) : (7.787 * t + 16 / 116);
        }
        var fx = f(X / Xn), fy = f(Y / Yn), fz = f(Z / Zn);

        return {
            L: 116 * fy - 16,
            a: 500 * (fx - fy),
            b: 200 * (fy - fz)
        };
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

    // ---- SIMILAR test (metric chosen in dialog) ----
    function isSimilar(colA, colB) {
        var dr = Math.abs(colA.r - colB.r);
        var dg = Math.abs(colA.g - colB.g);
        var db = Math.abs(colA.b - colB.b);

        if (SIM_EXCLUDE_EXACT && dr === 0 && dg === 0 && db === 0) return false;

        var d;
        if (USE_LAB) {
            // CIE Lab Delta-E 1976: Euclidean distance in Lab space.
            var dL = colA.lab.L - colB.lab.L;
            var da = colA.lab.a - colB.lab.a;
            var dbb = colA.lab.b - colB.lab.b;
            d = Math.sqrt(dL * dL + da * da + dbb * dbb);
        } else {
            // Legacy: weighted RGB distance (luma-ish weighting).
            d = Math.sqrt(
                (0.299 * dr) * (0.299 * dr) +
                (0.587 * dg) * (0.587 * dg) +
                (0.114 * db) * (0.114 * db)
            );
        }

        return d <= SIM_MAX_DIST;
    }

    // ---- Sample RGB for each of the 256 entries (no Color Samplers) ----
    // colors[idx] = {idx,r,g,b,key,lab}
    var colors = new Array(ENTRIES);

    var oldDialogs = app.displayDialogs;
    app.displayDialogs = DialogModes.NO;

    var tmp = null;
    var oldRuler = app.preferences.rulerUnits;

    try {
        app.preferences.rulerUnits = Units.PIXELS;

        tmp = workDoc.duplicate("TMP_SAMPLE", true); // merged copy for fast crop/hist
        if (tmp.mode !== DocumentMode.RGB) tmp.changeMode(ChangeMode.RGB);

        var baseState = tmp.activeHistoryState;

        for (var si = 0; si < ENTRIES; si++) {
            var sp = MODE.sampleXY(si);

            tmp.activeHistoryState = baseState;

            tmp.crop([
                UnitValue(sp.x, "px"),
                UnitValue(sp.y, "px"),
                UnitValue(sp.x + 1, "px"),
                UnitValue(sp.y + 1, "px")
            ]);

            var r = findHistogramValue(tmp.channels.getByName("Red").histogram);
            var g = findHistogramValue(tmp.channels.getByName("Green").histogram);
            var b = findHistogramValue(tmp.channels.getByName("Blue").histogram);

            colors[si] = {
                idx: si,
                r: r, g: g, b: b,
                key: rgbKey(r, g, b),
                lab: srgbToLab(r, g, b)
            };
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

    // Master set of cleared palette indices (redundant copies from both
    // IDENTICAL and SIMILAR). Representatives (lowest index of each
    // set/cluster) are never cleared.
    var cleared = {}; // idx -> true

    // =====================================================================
    // 1) IDENTICAL (exact RGB matches)
    //    Layer contains ONLY the redundant copies; the lowest-index
    //    occurrence is kept in the palette and NOT painted here.
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
        var members = exactMap[key].slice(0).sort(function (a, b) { return a - b; });

        var keepIdx = members[0];          // representative — stays in palette
        var dups = members.slice(1);       // redundant copies — go in the group

        var rep = colors[keepIdx];

        var lyrI = workDoc.artLayers.add();
        lyrI.name = "dup RGB(" + key + ") keep " + keepIdx + " dup " + dups.join(",");
        lyrI.move(grpIdentical, ElementPlacement.INSIDE);

        setForegroundToRGB(rep.r, rep.g, rep.b);

        for (var mI = 0; mI < dups.length; mI++) {
            paintEntry(workDoc, dups[mI]);
            cleared[dups[mI]] = true;
        }
    }

    // =====================================================================
    // 2) SIMILAR (perceptual, transitive clustering)
    //    Layer contains ONLY the redundant members; the lowest-index
    //    member of each cluster is kept in the palette and NOT painted.
    // =====================================================================
    var uf = new UF(colors.length);

    for (var ai = 0; ai < colors.length; ai++) {
        for (var bi = ai + 1; bi < colors.length; bi++) {
            if (isSimilar(colors[ai], colors[bi])) {
                uf.union(ai, bi);
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
        var membersS = clusterList[cc].slice(0).sort(function (a, b) { return a - b; });

        var keepIdxS = membersS[0];        // representative — stays in palette
        var dupsS = membersS.slice(1);     // redundant members — go in the group

        var repS = colors[keepIdxS];

        var lyrS = workDoc.artLayers.add();
        lyrS.name = "sim cluster keep " + keepIdxS +
                    " RGB(" + repS.r + "," + repS.g + "," + repS.b + ")" +
                    " dup " + dupsS.join(",");
        lyrS.move(grpSimilar, ElementPlacement.INSIDE);

        // Paint each redundant block using its own colour
        // (so you can see the small differences).
        for (var ms = 0; ms < dupsS.length; ms++) {
            var colS = colors[dupsS[ms]];
            setForegroundToRGB(colS.r, colS.g, colS.b);
            paintEntry(workDoc, dupsS[ms]);
            cleared[dupsS[ms]] = true;
        }
    }

    // =====================================================================
    // 3) REPACK
    //    One layer: all KEPT colours packed from slot 0 in their original
    //    relative order; every cleared slot at the tail filled cyan.
    //    In DoomTools mode this is a full 256xH image of columns that can
    //    be flattened/exported straight as a new blank playpal.
    // =====================================================================
    var grpRepack = recreateGroup(workDoc, GROUP_REPACK);

    var keptCount = 0;
    for (var kc = 0; kc < colors.length; kc++) {
        if (!cleared[kc]) keptCount++;
    }

    var lyrR = workDoc.artLayers.add();
    lyrR.name = "repack (" + keptCount + " kept, " + (colors.length - keptCount) + " cleared)";
    lyrR.move(grpRepack, ElementPlacement.INSIDE);

    var slot = 0;
    for (var ri = 0; ri < colors.length; ri++) {
        if (cleared[ri]) continue;
        var colR = colors[ri];
        setForegroundToRGB(colR.r, colR.g, colR.b);
        paintEntry(workDoc, slot);
        slot++;
    }

    // Fill the tail with the cyan marker.
    setForegroundToRGB(CLEAR_R, CLEAR_G, CLEAR_B);
    for (var ti = slot; ti < colors.length; ti++) {
        paintEntry(workDoc, ti);
    }

    // ---- Done ----
    alert(
        "Done.\n\n" +
        "Format: " + MODE.label + "\n" +
        "Original document was NOT modified.\n" +
        "Output is in the DUPLICATE document:\n  " + workDoc.name + "\n\n" +
        "IDENTICAL sets: " + identicalKeys.length + " (group '" + GROUP_IDENTICAL + "')\n" +
        "SIMILAR clusters: " + clusterList.length + " (group '" + GROUP_SIMILAR + "')\n" +
        "REPACK: " + keptCount + " colours kept, " + (colors.length - keptCount) + " cleared (group '" + GROUP_REPACK + "')\n\n" +
        "Metric: " + (USE_LAB ? "CIE Lab \u0394E76" : "Weighted RGB (legacy)") +
        ", threshold <= " + SIM_MAX_DIST +
        (SIM_EXCLUDE_EXACT ? "\nSIMILAR pairwise test excludes exact matches." : "\nSIMILAR includes exact matches.")
    );

})();
