"""Ramp tool in COLORMAP fade mode: one Relative ramp drives the fades of the
selected strips, each over its own row range, snapped to palette colours."""

from ..colormap import LIGHT_ROWS, fade_ramp_rows, greedy_new_colours
from ..colour import hex_of, oklab
from .ramp_tool import RampTool

BAD_SNAP = 0.05          # OKLab distance that counts as a poor snap


class FadeRampTool(RampTool):
    STATE_KEY = "ramp_fade"
    TITLE = "Ramp tool - COLORMAP fades"
    FADE = True

    # ---------------------------------------------------------- setup
    def setup(self):
        from tkinter import ttk

        tk = self.app.tk
        self.sf.configure(text="Fade steps (reference strip: smooth ramp / snapped palette "
                               "colour)")
        for b in self.reverse_btn:                # Reverse / Use selection ends
            b.state(["disabled"])
        af = ttk.Frame(self.sf)
        af.grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(af, text="Add missing colours, budget").pack(side="left")
        self.add_budget = tk.StringVar(value="4")
        ttk.Spinbox(af, textvariable=self.add_budget, from_=1, to=64, increment=1,
                    width=4).pack(side="left", padx=(4, 0))
        ttk.Button(af, text="Add", command=self.add_missing).pack(side="left", padx=(4, 0))
        self.add_info = tk.StringVar(value="")
        ttk.Label(af, textvariable=self.add_info, foreground="#666").pack(side="left",
                                                                         padx=(8, 0))
        self.sync_reference()

    def previewing(self):
        return self.app._framp_backup is not None

    def sync_reference(self):
        """Node 0 = the reference strip's anchor (locked)."""
        a = self.app
        anc = a.framp_anchor(a.fref) if a.fref is not None else None
        if anc is not None:
            self.nodes()[0]["rgb"] = list(anc)
            self.nodes()[0]["hsl"] = None
        r0 = a.fstrips.get(a.fref, 0)
        self.win.title("%s - reference: index %s from row %d   (%d strip%s)" % (
            self.TITLE, a.fref, r0, len(a.fstrips), "" if len(a.fstrips) == 1 else "s"))
        self.changed(store=False)

    # ---------------------------------------------------------- locked start node
    def refresh_node_row(self):
        super().refresh_node_row()
        if self.idx(self.active) == 0:
            self.node_var.set("Start (locked)")

    def open_picker(self):
        if self.idx(self.active) == 0:
            self.app.status_var.set("The start colour is locked - it is the colour the "
                                    "fade continues from.")
            return
        super().open_picker()

    def set_node_colour(self, node, rgb, hsl=None):
        if self.nodes() and node is self.nodes()[0]:
            return
        super().set_node_colour(node, rgb, hsl)

    def _on_hex(self):
        if self.idx(self.active) == 0:
            self.refresh_node_row()
            return
        super()._on_hex()

    def drop_colour(self, x_root, rgb):
        super().drop_colour(x_root, rgb)
        self.sync_reference()

    def reverse(self):
        pass

    def use_selection_ends(self):
        pass

    # ---------------------------------------------------------- results
    def results(self):
        a = self.app
        res, _f = a.cmap_result(base=True)
        if res is None or not a.fstrips:
            return {}
        anchors = {s: a.framp_anchor(s) for s in a.fstrips}
        ref = a.fref if a.fref in a.fstrips else next(iter(a.fstrips))
        return fade_ramp_rows(self.st, anchors[ref], a.fstrips, anchors, res.matcher,
                              a.cm_base().limits)

    def targets(self):
        a = self.app
        return list(range(a.fstrips.get(a.fref, 0), LIGHT_ROWS)) if a.fstrips else []

    def colours(self, n=None):
        out = self.results().get(self.app.fref, [])
        return [tuple(int(round(v)) for v in r[1]) for r in out]

    def draw_strip(self):
        c = self.strip
        c.delete("all")
        self._strip_cells = []
        a = self.app
        W = max(c.winfo_width(), 40)
        if not a.fstrips:
            c.create_text(10, 20, anchor="w", fill="#bbbbbb",
                          text="Choose strips in the fade view with the Ramp tool "
                               "(click an index = whole strip, click a cell = from that row).")
            return
        rows = self.results().get(a.fref, [])
        n = max(len(rows), 1)
        cell = min(36 * self.ui, (W - 8) / float(n))
        need = int(2 * cell + 26)
        if int(c.cget("height")) < need:
            c.configure(height=need)
        bad = 0
        for k, (row, ideal, slot, dist) in enumerate(rows):
            x = 4 + k * cell
            ic = tuple(int(round(v)) for v in ideal)
            sc = a.rgbs[slot] if slot is not None else (0, 0, 0)
            c.create_rectangle(x, 4, x + cell - 2, 4 + cell - 2, fill=hex_of(ic), outline="")
            c.create_rectangle(x, 6 + cell, x + cell - 2, 4 + 2 * cell, fill=hex_of(sc),
                               outline="")
            if dist > BAD_SNAP:
                bad += 1
                c.create_line(x, 8 + 2 * cell, x + cell - 2, 8 + 2 * cell, fill="#ff3030",
                              width=3)
            if k % 4 == 0 or cell >= 22:
                c.create_text(x + cell / 2, 18 + 2 * cell, fill="#999999",
                              font=("Consolas", 7), text=str(row))
            self._strip_cells.append((x, 4, cell, k, ic, slot, dist, row))
        self.add_info.set("%d poor snap%s on the reference strip" % (bad, "" if bad == 1
                                                                    else "s"))

    def _strip_hover(self, ev):
        for x, y, cell, k, ic, slot, dist, row in self._strip_cells:
            if x <= ev.x < x + cell:
                sc = self.app.rgbs[slot] if slot is not None else None
                self.info_var.set("row %d   ramp %s   -> index %s %s   (distance %.3f%s)" % (
                    row, hex_of(ic), slot, hex_of(sc) if sc else "?", dist,
                    "  POOR" if dist > BAD_SNAP else ""))
                return
        self.info_var.set("")

    # ---------------------------------------------------------- preview / apply
    def _push_preview(self):
        self._after = None
        if self.previewing():
            self.app.framp_preview_set(self.results())

    def toggle_preview(self):
        if self.previewing():
            self.cancel()
        elif self.app.framp_preview_start():
            self.app.framp_preview_set(self.results())
        self.update_buttons()
        self.draw_strip()

    def apply(self):
        a = self.app
        if not a.fstrips:
            a.status_var.set("Choose strips first (Ramp tool in the fade view).")
            return
        if not self.previewing() and not a.framp_preview_start():
            return
        if self._after is not None:
            self.win.after_cancel(self._after)
            self._after = None
        a.framp_preview_set(self.results())
        a.framp_apply()
        self.update_buttons()
        self.draw_strip()

    def cancel(self):
        if self.previewing():
            self.app.framp_cancel()
        self.update_buttons()
        self.draw_strip()

    def add_missing(self):
        """New palette colours (into empty slots) for the worst snaps of all strips."""
        a = self.app
        try:
            budget = max(1, int(float(self.add_budget.get())))
        except ValueError:
            return
        misses = []
        for s, rows in self.results().items():
            for row, ideal, slot, dist in rows:
                if row and dist > 0.015:
                    il = oklab(tuple(int(round(v)) for v in ideal))
                    misses.append((il, tuple(int(round(v)) for v in ideal), dist,
                                   0.35 + il[0], s, row))
        props, before, after = greedy_new_colours(misses, budget)
        if not props:
            a.status_var.set("The snapped fades already follow the ramp closely.")
            return
        was = self.previewing()
        if was:
            a.framp_cancel()
        if a.add_fade_colours([p["rgb"] for p in props]):
            a.status_var.set("Added %d colour(s) for the ramp - snapping error %.1f -> %.1f."
                             % (len(props), before, after))
        if was and a.framp_preview_start():
            a.framp_preview_set(self.results())
        self.update_buttons()
        self.changed(store=False)

    def close(self):
        if self.previewing():
            self.app.framp_cancel()
        super().close()
