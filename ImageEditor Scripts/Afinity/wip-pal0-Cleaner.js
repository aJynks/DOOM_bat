'use strict';

// palDupes — Doom palette duplicate/similarity analyser (dual format, dialog)
// For Affinity by Canva (Scripts panel).
//
// Detects format by document size:
//   128x128 — SLADE pal0 export (16x16 grid of 8x8 blocks)
//   256xN   — DoomTools blank playpal (1px per entry, row 0 = pal0,
//             painted as full-height 1px columns)
//
// Dialog on launch: metric (CIE Lab dE76 default / weighted RGB legacy)
// and a decimal threshold (defaults: 2.3 Lab, 1.1 RGB).
//
// Output: new document from a snapshot (original untouched) with groups
// IDENTICAL, SIMILAR (redundant entries only, lowest index kept) and
// REPACK (kept colours packed from slot 0, cyan 00FFFF tail).

const { app } = require('/application');
const { Dialog, DialogResult, UnitType } = require('/dialog');
const { AddChildNodesCommandBuilder, DocumentCommand } = require('/commands');
const { ContainerNodeDefinition, ImageNodeDefinition, NodeChildType } = require('/nodes');
const { Bitmap, PixelBuffer, RasterFormat } = require('/rasterobject');
const { PixelReaderRGBA8 } = require('/pixelaccessor');

function main() {
    const srcDoc = app.documents.current;
    if (!srcDoc) {
        app.alert('No document is open.');
        return;
    }

    const ENTRIES = 256;
    const CLEAR_R = 0, CLEAR_G = 255, CLEAR_B = 255; // cyan cutout
    const SIM_EXCLUDE_EXACT = true;
    const SLADE_GRID = 16, SLADE_CELL = 8;
    const DEFAULT_THRESH_LAB = 2.3;
    const DEFAULT_THRESH_RGB = 1.1;

    const srcW = Math.round(srcDoc.widthPixels);
    const srcH = Math.round(srcDoc.heightPixels);

    let MODE = null;
    if (srcW === SLADE_GRID * SLADE_CELL && srcH === SLADE_GRID * SLADE_CELL) {
        MODE = {
            label: 'SLADE (128x128, 8x8 cells)',
            canvasW: srcW, canvasH: srcH,
            paintW: SLADE_CELL, paintH: SLADE_CELL,
            sampleXY(idx) {
                const gx = idx % SLADE_GRID, gy = Math.floor(idx / SLADE_GRID);
                return { x: gx * SLADE_CELL + Math.floor(SLADE_CELL / 2), y: gy * SLADE_CELL + Math.floor(SLADE_CELL / 2) };
            },
            paintXY(slot) {
                return { x: (slot % SLADE_GRID) * SLADE_CELL, y: Math.floor(slot / SLADE_GRID) * SLADE_CELL };
            }
        };
    } else if (srcW === ENTRIES && srcH >= 1) {
        MODE = {
            label: 'DoomTools playpal (256x' + srcH + ', row 0 = pal0)',
            canvasW: srcW, canvasH: srcH,
            paintW: 1, paintH: srcH,
            sampleXY(idx) { return { x: idx, y: 0 }; },
            paintXY(slot) { return { x: slot, y: 0 }; }
        };
    } else {
        const NL = String.fromCharCode(10);
        app.alert(
            'Unexpected document size: ' + srcW + 'x' + srcH + ' px' + NL + NL +
            'Expected one of:' + NL +
            '  128x128  - SLADE palette export (16x16 of 8x8 blocks)' + NL +
            '  256xN    - DoomTools blank playpal (1px per entry, row 0 = pal0)'
        );
        return;
    }

    // -------------------- DIALOG --------------------
    const dlg = Dialog.create('Doom Palette Analyser');
    const col = dlg.addColumn();

    const fmtGroup = col.addGroup('Format');
    fmtGroup.addStaticText('Detected', MODE.label);

    const metricGroup = col.addGroup('Similarity metric');
    const metricRadio = metricGroup.addRadioGroup('Metric', ['CIE Lab dE76 (recommended)', 'Weighted RGB (legacy)'], 0);

    const threshGroup = col.addGroup('Threshold');
    const threshEditor = threshGroup.addUnitValueEditor('Threshold', UnitType.Number, UnitType.Number, DEFAULT_THRESH_LAB, 0, null);
    threshEditor.setPrecision(2).setShowPopupSlider(true);

    metricRadio.onValueChangedHandler = () => {
        threshEditor.value = (metricRadio.selectedIndex === 0) ? DEFAULT_THRESH_LAB : DEFAULT_THRESH_RGB;
    };

    if (dlg.runModal() !== DialogResult.Ok) return;

    const USE_LAB = (metricRadio.selectedIndex === 0);
    const SIM_MAX_DIST = threshEditor.value;

    // ---- Duplicate via snapshot (original untouched) ----
    let workDoc;
    try {
        const beforeCount = srcDoc.snapshotCount;
        srcDoc.executeCommand(DocumentCommand.createAddDocumentSnapshot('palDupes analysis'));
        const snaps = srcDoc.snapshots;
        if (snaps.length <= beforeCount) {
            app.alert('Failed to create a document snapshot.');
            return;
        }
        workDoc = snaps[snaps.length - 1].createDocument();
    } catch (eDup) {
        app.alert('Failed to duplicate the document. ' + eDup);
        return;
    }
    if (!workDoc) {
        app.alert('Failed to create the working document.');
        return;
    }

    const spread = workDoc.currentSpread;

    function findRasterNode(node) {
        if (node.isImageNode || node.isRasterNode) return node;
        if (node.children) {
            for (const child of node.children) {
                const found = findRasterNode(child);
                if (found) return found;
            }
        }
        return null;
    }
    let srcNode = null;
    for (const layer of spread.layers) {
        srcNode = findRasterNode(layer);
        if (srcNode) break;
    }
    if (!srcNode) {
        app.alert('Could not find an image or raster layer in the document.');
        return;
    }

    function createGroup(name) {
        const builder = AddChildNodesCommandBuilder.create();
        builder.setInsertionTarget(spread, NodeChildType.Main);
        builder.addContainerNode(ContainerNodeDefinition.create(name));
        const cmd = builder.createCommand(false);
        workDoc.executeCommand(cmd);
        return cmd.newNodes[0];
    }

    function addImageLayer(groupNode, name, bitmap) {
        const builder = AddChildNodesCommandBuilder.create();
        builder.setInsertionTarget(groupNode, NodeChildType.Main);
        const def = ImageNodeDefinition.create(RasterFormat.RGBA8);
        def.setBitmap(bitmap);
        def.setUserDescription(name);
        builder.addImageNode(def);
        workDoc.executeCommand(builder.createCommand(true));
    }

    // paintList: [{slot, r, g, b}] -> full-canvas RGBA bitmap
    function buildBitmapForSlots(paintList) {
        const w = MODE.canvasW, h = MODE.canvasH;
        const buffer = PixelBuffer.create(w, h, RasterFormat.RGBA8);
        const arr = new Uint8Array(buffer.buffer);
        for (const item of paintList) {
            const p = MODE.paintXY(item.slot);
            for (let dy = 0; dy < MODE.paintH; dy++) {
                for (let dx = 0; dx < MODE.paintW; dx++) {
                    const i = ((p.y + dy) * w + (p.x + dx)) * 4;
                    arr[i] = item.r; arr[i + 1] = item.g; arr[i + 2] = item.b; arr[i + 3] = 255;
                }
            }
        }
        return buffer.createCompatibleBitmap(true);
    }

    function srgbToLab(r, g, b) {
        function lin(c) {
            c /= 255;
            return (c <= 0.04045) ? (c / 12.92) : Math.pow((c + 0.055) / 1.055, 2.4);
        }
        const R = lin(r), G = lin(g), B = lin(b);
        const X = R * 0.4124564 + G * 0.3575761 + B * 0.1804375;
        const Y = R * 0.2126729 + G * 0.7151522 + B * 0.0721750;
        const Z = R * 0.0193339 + G * 0.1191920 + B * 0.9503041;
        const Xn = 0.95047, Yn = 1.00000, Zn = 1.08883;
        function f(t) { return (t > 0.008856) ? Math.pow(t, 1 / 3) : (7.787 * t + 16 / 116); }
        const fx = f(X / Xn), fy = f(Y / Yn), fz = f(Z / Zn);
        return { L: 116 * fy - 16, a: 500 * (fx - fy), b: 200 * (fy - fz) };
    }

    function UF(n) {
        this.p = []; this.r = [];
        for (let i = 0; i < n; i++) { this.p[i] = i; this.r[i] = 0; }
    }
    UF.prototype.find = function (x) {
        let p = this.p[x];
        if (p !== x) this.p[x] = this.find(p);
        return this.p[x];
    };
    UF.prototype.union = function (a, b) {
        const ra = this.find(a), rb = this.find(b);
        if (ra === rb) return;
        if (this.r[ra] < this.r[rb]) this.p[ra] = rb;
        else if (this.r[ra] > this.r[rb]) this.p[rb] = ra;
        else { this.p[rb] = ra; this.r[ra]++; }
    };

    function isSimilar(a, b) {
        const dr = Math.abs(a.r - b.r), dg = Math.abs(a.g - b.g), db = Math.abs(a.b - b.b);
        if (SIM_EXCLUDE_EXACT && dr === 0 && dg === 0 && db === 0) return false;
        let d;
        if (USE_LAB) {
            const dL = a.lab.L - b.lab.L, da = a.lab.a - b.lab.a, dbb = a.lab.b - b.lab.b;
            d = Math.sqrt(dL * dL + da * da + dbb * dbb);
        } else {
            d = Math.sqrt(
                (0.299 * dr) * (0.299 * dr) +
                (0.587 * dg) * (0.587 * dg) +
                (0.114 * db) * (0.114 * db)
            );
        }
        return d <= SIM_MAX_DIST;
    }

    // ---- Sample the 256 entries ----
    const sampleBitmap = srcNode.rasterInterface.createCompatibleBitmap(true);
    const reader = PixelReaderRGBA8.create(sampleBitmap);
    const colors = new Array(ENTRIES);
    try {
        for (let i = 0; i < ENTRIES; i++) {
            const p = MODE.sampleXY(i);
            const px = reader.readPixel(p.x, p.y);
            colors[i] = {
                idx: i, r: px.r, g: px.g, b: px.b,
                key: px.r + ',' + px.g + ',' + px.b,
                lab: srgbToLab(px.r, px.g, px.b)
            };
        }
    } finally {
        reader.dispose();
    }

    const cleared = {};

    // ---- IDENTICAL ----
    const exactMap = {};
    for (const c of colors) {
        if (!exactMap[c.key]) exactMap[c.key] = [];
        exactMap[c.key].push(c.idx);
    }
    const identicalKeys = Object.keys(exactMap).filter(k => exactMap[k].length >= 2).sort();

    const grpIdentical = createGroup('IDENTICAL');
    for (const key of identicalKeys) {
        const members = exactMap[key].slice().sort((a, b) => a - b);
        const keepIdx = members[0];
        const dups = members.slice(1);
        const paintList = dups.map(idx => ({ slot: idx, r: colors[idx].r, g: colors[idx].g, b: colors[idx].b }));
        addImageLayer(grpIdentical, 'dup RGB(' + key + ') keep ' + keepIdx + ' dup ' + dups.join(','), buildBitmapForSlots(paintList));
        dups.forEach(idx => { cleared[idx] = true; });
    }

    // ---- SIMILAR ----
    const uf = new UF(colors.length);
    for (let a = 0; a < colors.length; a++) {
        for (let b = a + 1; b < colors.length; b++) {
            if (isSimilar(colors[a], colors[b])) uf.union(a, b);
        }
    }
    const clusters = {};
    for (let c = 0; c < colors.length; c++) {
        const root = uf.find(c);
        if (!clusters[root]) clusters[root] = [];
        clusters[root].push(c);
    }
    const clusterList = Object.values(clusters)
        .filter(m => m.length >= 2)
        .sort((x, y) => Math.min(...x) - Math.min(...y));

    const grpSimilar = createGroup('SIMILAR');
    for (const clusterMembers of clusterList) {
        const members = clusterMembers.slice().sort((a, b) => a - b);
        const keepIdx = members[0];
        const dups = members.slice(1);
        const rep = colors[keepIdx];
        const paintList = dups.map(idx => ({ slot: idx, r: colors[idx].r, g: colors[idx].g, b: colors[idx].b }));
        addImageLayer(grpSimilar, 'sim cluster keep ' + keepIdx + ' RGB(' + rep.r + ',' + rep.g + ',' + rep.b + ') dup ' + dups.join(','), buildBitmapForSlots(paintList));
        dups.forEach(idx => { cleared[idx] = true; });
    }

    // ---- REPACK ----
    let keptCount = 0;
    for (let i = 0; i < ENTRIES; i++) if (!cleared[i]) keptCount++;

    const repackPaint = [];
    let slot = 0;
    for (let i = 0; i < ENTRIES; i++) {
        if (cleared[i]) continue;
        repackPaint.push({ slot: slot, r: colors[i].r, g: colors[i].g, b: colors[i].b });
        slot++;
    }
    for (let t = slot; t < ENTRIES; t++) {
        repackPaint.push({ slot: t, r: CLEAR_R, g: CLEAR_G, b: CLEAR_B });
    }
    const grpRepack = createGroup('REPACK');
    addImageLayer(grpRepack, 'repack (' + keptCount + ' kept, ' + (ENTRIES - keptCount) + ' cleared)', buildBitmapForSlots(repackPaint));

    const NL = String.fromCharCode(10);
    app.alert(
        'Done.' + NL + NL +
        'Format: ' + MODE.label + NL +
        'Original document was NOT modified.' + NL +
        'Output is in the new document: ' + workDoc.title + NL + NL +
        'IDENTICAL sets: ' + identicalKeys.length + NL +
        'SIMILAR clusters: ' + clusterList.length + NL +
        'REPACK: ' + keptCount + ' kept, ' + (ENTRIES - keptCount) + ' cleared (cyan)' + NL + NL +
        'Metric: ' + (USE_LAB ? 'CIE Lab dE76' : 'Weighted RGB (legacy)') + ', threshold <= ' + SIM_MAX_DIST
    );
}

main();
