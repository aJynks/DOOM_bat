"""Tool windows, ramp preview and direct colour writes (App mixin)."""

from ..analysis import update_pairs
from ..filters import apply_filter
from ..colour import hex_of, parse_colour_list
from ..constants import ENTRIES
from .picker import ColourPicker
from .scratch import ScratchPalette


class ToolsMixin:
    """Tool windows, ramp preview and direct colour writes."""

    def open_picker(self):
        if self.picker is not None:
            self.picker.win.deiconify()
            self.picker.win.lift()
            return self.picker
        self.picker = ColourPicker(self)
        self.picker.owner = None
        self.picker.set_target(None, (128, 128, 128), None, "")
        return self.picker

    def open_scratch(self):
        if self.scratch is not None:
            self.scratch.win.deiconify()
            self.scratch.win.lift()
            return self.scratch
        self.scratch = ScratchPalette(self)
        return self.scratch

    def add_recent(self, rgb):
        hx = hex_of(rgb)
        rec = [x for x in self.s.get("recent_colours", []) if isinstance(x, str) and x != hx]
        self.s["recent_colours"] = [hx] + rec[:15]

    def _tools_refresh(self):
        """Palette changed: let the open tool windows redraw their markers."""
        if self.ramp is not None:
            self.ramp.draw_strip()
        if self.scratch is not None:
            self.scratch.draw()

    def ramp_preview_start(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return False
        if self.tool != "paint":
            self.status_var.set("Palette ramps are in the Paint tools.")
            return False
        if self._ramp_backup is not None:
            return True
        if self._filt_backup is not None:
            self.status_var.set("Filter preview is open - Apply or Cancel it first.")
            return False
        tg = sorted(self.selection)
        if not tg:
            self.status_var.set("Select the cells to fill (blank or filled) first.")
            return False
        self._ramp_backup = (self.rgbs, self.labs, self.pairs,
                             set(self.deleted), set(self.selection))
        self._ramp_cm = self.cm.copy()
        self._ramp_targets = tg
        self._refresh_history()
        return True

    def ramp_preview_set(self, colours):
        if self._ramp_backup is None:
            return
        b = self._ramp_backup
        tg = self._ramp_targets
        new = list(b[0])
        for i, c in zip(tg, colours):
            new[i] = tuple(c)
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, b[1], b[2], tg)
        self.deleted = set(b[3]) - set(tg)
        self.selection = set(b[4])
        self.cm = self._ramp_cm.copy()
        self.cm.invalidate(tg)
        self.cm_changed()
        self.status_var.set("Ramp preview: %d cells. Apply keeps it, Cancel restores."
                            % len(tg))
        self.recompute()

    def _ramp_end(self):
        self._ramp_backup = None
        self._ramp_targets = []
        if self.ramp is not None:
            self.ramp.update_buttons()
        self._refresh_history()

    def ramp_cancel(self):
        if self._ramp_backup is None:
            return
        b = self._ramp_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.selection = set(b[3]), set(b[4])
        self.cm = self._ramp_cm.copy()
        self.cm_changed()
        self._ramp_end()
        self.status_var.set("Ramp cancelled.")
        self.recompute()

    def ramp_apply(self, colours, node_rgbs):
        if self._ramp_backup is None:
            return
        before = self._ramp_backup[0]
        n = len(self._ramp_targets)
        self._ramp_end()
        if self.rgbs == before:
            self.status_var.set("The cells already hold that ramp - nothing changed.")
            self.recompute()
            return
        self._paint_ramps += 1
        self.status_var.set("Ramp applied to %d cells (%s) - Snapshot in the Paint tools "
                            "records it." % (n, " > ".join(hex_of(c) for c in node_rgbs)))
        self.recompute()

    def set_cells_colour(self, indices, rgb, what="Set colour"):
        """Write one colour into palette cells (blank or filled)."""
        if self.rgbs is None or self._preview_busy_msg():
            return
        if self.tool != "paint":
            self.status_var.set("Palette colours can only be changed in the Paint tools "
                                "(PLAYPAL mode).")
            return
        indices = sorted(set(indices))
        if not indices:
            return
        rgb = tuple(rgb)
        new = list(self.rgbs)
        for i in indices:
            new[i] = rgb
        if new == self.rgbs:
            self.status_var.set("Those cells already hold %s." % hex_of(rgb))
            return
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, indices)
        self.deleted -= set(indices)
        self.cm.invalidate(indices)
        self.cm_changed()
        if what == "Fill" or len(indices) > 1:
            self._paint_fills += 1
        else:
            self._paint_cells.update(indices)
        self.status_var.set("%s %d cell(s) with %s - Snapshot in the Paint tools records it."
                            % ("Filled" if len(indices) > 1 else "Set", len(indices),
                               hex_of(rgb)))
        self.recompute()

    # ---------------------------------------------------------- Paint session
    def _paint_reset(self):
        self._paint_start = (self.rgbs, self.labs, self.pairs, set(self.deleted),
                             self.cm.copy())
        self._paint_ramps = 0
        self._paint_fills = 0
        self._paint_filters = 0
        self._paint_cuts = 0
        self._paint_pastes = 0
        self._paint_cells = set()

    def paint_pending(self):
        return (self.tool == "paint" and self._paint_start is not None
                and self.rgbs != self._paint_start[0])

    def paint_summary(self):
        parts = []
        for n, one in ((self._paint_ramps, "ramp"), (self._paint_fills, "fill"),
                       (self._paint_filters, "filter"), (self._paint_cuts, "cut"),
                       (self._paint_pastes, "paste"), (len(self._paint_cells), "cell")):
            if n:
                parts.append("%d %s%s" % (n, one, "" if n == 1 else "s"))
        return ", ".join(parts) or "edits"

    def paint_snapshot(self):
        if self._preview_busy_msg():
            return
        if not self.paint_pending():
            self.status_var.set("No paint edits to snapshot.")
            return
        self._push_history("Painted: %s - %d colours" % (
            self.paint_summary(), sum(1 for e in self.rgbs if e is not None)))
        self._paint_reset()
        self.status_var.set("Paint edits recorded as #%d (Back undoes them)." % self.hist_pos)
        self.recompute()

    def paint_revert(self):
        if self._paint_start is None or self._preview_busy_msg():
            return
        self.rgbs, self.labs, self.pairs, d, cm = self._paint_start
        self.deleted, self.cm = set(d), cm.copy()
        self.cm_changed()
        self._paint_ramps = 0
        self._paint_fills = 0
        self._paint_filters = 0
        self._paint_cuts = 0
        self._paint_pastes = 0
        self._paint_cells = set()
        self.status_var.set("Paint edits reverted.")
        if self.filter_win is not None:
            self.filter_win.refresh()
        self.recompute()

    def paint_cell_live(self, idx, rgb):
        """Picker on a single cell (Paint double-click): live pending edit."""
        if self.tool != "paint" or self.rgbs is None or self._preview_busy_msg():
            return
        rgb = tuple(rgb)
        if self.rgbs[idx] == rgb:
            return
        new = list(self.rgbs)
        new[idx] = rgb
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, [idx])
        self.deleted.discard(idx)
        self.cm.invalidate([idx])
        self.cm_changed()
        self._paint_cells.add(idx)
        self.recompute()

    # ---------------------------------------------------------- clipboard
    # Ctrl+C copy (anywhere), Ctrl+X cut, Ctrl+V paste over, Ctrl+Shift+V
    # insert paste (Paint; Move: cut + insert only). One gap-free block,
    # index order, no sorting.
    def clip_text(self):
        n = len(self.clip)
        return "Clipboard: %d colour%s" % (n, "" if n == 1 else "s") if n \
            else "Clipboard: empty"

    def _clip_selected(self):
        return sorted(i for i in self.selection if self.rgbs[i] is not None)

    def _clip_busy(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return True
        return self._preview_busy_msg()

    def clip_copy(self):
        if self._clip_busy():
            return False
        idx = self._clip_selected()
        if not idx:
            self.status_var.set("Select colours to copy first.")
            return False
        self.clip = [self.rgbs[i] for i in idx]
        self._clip_sys = "\n".join(hex_of(c) for c in self.clip)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._clip_sys)
        except self.tk.TclError:
            pass
        self.status_var.set("Copied %d colour(s)." % len(self.clip))
        self._tool_refresh_win()
        return True

    def _clip_source(self):
        """Colours to paste: cleanpal's clipboard, or a hex list someone put on
        the system clipboard since our last copy."""
        try:
            sys_text = self.root.clipboard_get()
        except self.tk.TclError:
            sys_text = None
        if sys_text and sys_text != getattr(self, "_clip_sys", None):
            cols = parse_colour_list(sys_text)
            if cols:
                return [tuple(c) for c in cols], "system clipboard"
        return list(self.clip), "clipboard"

    def _clip_target(self):
        """First selected cell, else the cell under the mouse, else None."""
        if self.selection:
            return min(self.selection)
        slot = self.hover_slot
        ent = self._view_entry(slot) if slot is not None else None
        return ent[0] if ent else None

    def _clip_tool_ok(self, what):
        if self.tool in ("paint", "move"):
            return True
        self.status_var.set("%s is in the Paint and Move tools." % what)
        return False

    def clip_cut(self):
        if self._clip_busy() or not self._clip_tool_ok("Cut"):
            return
        idx = self._clip_selected()
        if not idx or not self.clip_copy():
            return
        n = len(idx)
        if self.tool == "paint":
            new = list(self.rgbs)
            for i in idx:
                new[i] = None
            self.rgbs = new
            self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, idx)
            self.deleted -= set(idx)
            self.cm.invalidate(idx)
            self.cm_changed()
            self.selection = set()
            self._paint_cuts += 1
            self.status_var.set("Cut %d colour(s) - the cells are now empty. Snapshot "
                                "records it." % n)
        else:                                  # Move: take out, close the gap
            self._move_push_undo()
            cut = set(idx)
            perm = [i for i in range(ENTRIES) if i not in cut] + idx
            self._permute(perm)
            new = list(self.rgbs)
            gone = list(range(ENTRIES - n, ENTRIES))
            for i in gone:
                new[i] = None
            self.rgbs = new
            self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, gone)
            self.deleted -= set(gone)
            self.cm.invalidate(gone)
            self.cm_changed()
            self.selection = set()
            self.status_var.set("Cut %d colour(s) - the rest closed up; Ctrl+Shift+V "
                                "inserts them somewhere else." % n)
        self.recompute()

    def clip_paste(self, insert=False):
        if self._clip_busy() or not self._clip_tool_ok("Paste"):
            return
        if self.tool == "move" and not insert:
            self.status_var.set("Overwrite paste is in the Paint tools - use Ctrl+Shift+V "
                                "to insert.")
            return
        cols, src = self._clip_source()
        if not cols:
            self.status_var.set("The clipboard is empty - copy some colours first.")
            return
        t = self._clip_target()
        if t is None:
            self.status_var.set("Select a cell (or point at one) to paste at.")
            return
        n = len(cols)
        if insert:
            # the block goes in front of the colour at t. Colours from t are
            # pushed right into the empty slots after t; if those run out, the
            # nearest empty slots before t are used (the colours between them
            # and t shift left). Refused only if the palette lacks n empties.
            after = [i for i in range(t, ENTRIES) if self.rgbs[i] is None]
            before = [i for i in range(t - 1, -1, -1) if self.rgbs[i] is None]
            if len(after) + len(before) < n:
                free = len(after) + len(before)
                self._clip_refuse(
                    "No room to insert",
                    "Inserting %d colour%s needs %d empty slot%s in the palette - there "
                    "%s only %d." % (n, "" if n == 1 else "s", n, "" if n == 1 else "s",
                                     "is" if free == 1 else "are", free))
                return
            use_after = after[:n]
            use_before = sorted(before[:n - len(use_after)])
        elif t + n > ENTRIES:
            self._clip_refuse(
                "No room to paste",
                "Pasting %d colour%s at index %d needs %d slots, but only %d are left "
                "before the end of the palette (index %d)." % (
                    n, "" if n == 1 else "s", t, n, ENTRIES - t, ENTRIES - 1))
            return
        if self.tool == "move":
            self._move_push_undo()
        start = t
        if insert:
            # chosen empties become the gap; everything else keeps its order
            ub, ua = set(use_before), set(use_after)
            perm = ([i for i in range(t) if i not in ub] + use_before + use_after
                    + [i for i in range(t, ENTRIES) if i not in ua])
            self._permute(perm)
            start = t - len(use_before)
        tg = list(range(start, start + n))
        new = list(self.rgbs)
        for i, c in zip(tg, cols):
            new[i] = tuple(c)
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, tg)
        self.deleted -= set(tg)
        self.cm.invalidate(tg)
        self.cm_changed()
        self.selection = set(tg)
        if self.tool == "paint":
            self._paint_pastes += 1
        self.status_var.set("%s %d colour(s) at index %d (from the %s)%s." % (
            "Inserted" if insert else "Pasted", n, start, src,
            " - Snapshot records it" if self.tool == "paint" else ""))
        self.recompute()

    def _clip_refuse(self, title, text):
        from tkinter import messagebox

        self.status_var.set("Not pasted: " + text)
        parent = self.tool_win.win if self.tool_win is not None else self.root
        try:
            messagebox.showwarning(title, text, parent=parent)
        except self.tk.TclError:
            pass

    def _on_clip_key(self, ev, what):
        if self._typing(ev) or self.rgbs is None:
            return
        if what == "copy":
            self.clip_copy()
        elif what == "cut":
            self.clip_cut()
        else:
            self.clip_paste(insert=(what == "insert"))
        return "break"

    def _bind_clip_keys(self, w):
        for seq, what in (("<Control-c>", "copy"), ("<Control-x>", "cut"),
                          ("<Control-v>", "paste"), ("<Control-V>", "insert"),
                          ("<Control-Shift-V>", "insert"), ("<Control-Shift-v>", "insert")):
            w.bind(seq, lambda e, k=what: self._on_clip_key(e, k))

    # ---------------------------------------------------------- Paint filters
    def filter_open(self):
        if self.tool != "paint":
            self.status_var.set("Filters are in the Paint tools.")
            return
        if self.filter_win is not None:
            self.filter_win.win.deiconify()
            self.filter_win.win.lift()
            return
        from .filter_tool import FilterWindow
        self.filter_win = FilterWindow(self)

    def _filter_base(self):
        """(rgbs, labs, pairs, deleted, cm) the filter reads from: the
        pre-preview palette while previewing, else the working palette."""
        if self._filt_backup is not None:
            return self._filt_backup
        return (self.rgbs, self.labs, self.pairs, self.deleted, self.cm)

    def _filter_ctx(self):
        w = self.tool_win if self.tool == "paint" else None
        return {"ramp": w.st if w is not None else None,
                "fill": tuple(w.fill_rgb) if w is not None else None}

    def filter_compute(self):
        """(targets, before colours, after colours) for the current selection."""
        if self.rgbs is None or self.filter_win is None:
            return [], [], []
        base = self._filter_base()[0]
        targets = sorted(i for i in self.selection if base[i] is not None)
        before = [base[i] for i in targets]
        name, params = self.filter_win.settings()
        return targets, before, apply_filter(name, params, before, self._filter_ctx())

    def filter_preview_start(self):
        if self.rgbs is None or self.tool != "paint":
            return False
        if self._filt_backup is not None:
            return True
        if self._ramp_backup is not None:
            self.status_var.set("Ramp preview is open - Apply or Cancel it first.")
            return False
        self._filt_backup = (self.rgbs, self.labs, self.pairs, set(self.deleted),
                             self.cm.copy())
        self._refresh_history()
        return True

    def _filter_write(self, base, targets, after):
        new = list(base[0])
        for i, c in zip(targets, after):
            new[i] = tuple(c)
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, base[1], base[2], targets)
        self.deleted = set(base[3]) - set(targets)
        self.cm = base[4].copy()
        self.cm.invalidate(targets)
        self.cm_changed()

    def filter_preview_refresh(self):
        """Re-run the filter on the CURRENT selection from the pre-preview
        palette (so the selection can change while previewing)."""
        if self._filt_backup is None:
            return
        base = self._filt_backup
        targets, _before, after = self.filter_compute()
        self._filter_write(base, targets, after)
        name = self.filter_win.current if self.filter_win is not None else "Filter"
        self.status_var.set("Filter preview: %s on %d colours. Apply keeps it, Cancel "
                            "restores." % (name, len(targets)))
        self.recompute()

    def filter_cancel(self):
        if self._filt_backup is None:
            return
        b = self._filt_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.cm = set(b[3]), b[4].copy()
        self.cm_changed()
        self._filt_backup = None
        self._refresh_history()
        if self.filter_win is not None:
            self.filter_win.update_buttons()
        self.status_var.set("Filter preview cancelled.")
        self.recompute()

    def filter_apply(self):
        """Write the filter into the selection (a pending Paint edit)."""
        if self.rgbs is None or self.tool != "paint" or self.filter_win is None:
            return
        if self._ramp_backup is not None:
            self.status_var.set("Ramp preview is open - Apply or Cancel it first.")
            return
        base = self._filter_base()
        before_all = base[0]
        targets, _before, after = self.filter_compute()
        if not targets:
            self.status_var.set("Select the palette colours to filter first.")
            return
        self._filter_write(base, targets, after)
        self._filt_backup = None
        self._refresh_history()
        if self.rgbs == before_all:
            self.status_var.set("The filter changes nothing on those colours.")
        else:
            self._paint_filters += 1
            self.status_var.set("%s applied to %d colours - Snapshot in the Paint tools "
                                "records it." % (self.filter_win.current, len(targets)))
        self.recompute()

    def _filter_sel_changed(self):
        if self.filter_win is not None:
            self.filter_win.schedule()

    def _paint_cell_target(self):
        """Cell the picker is editing (Paint double-click), or None."""
        w = self.tool_win if self.tool == "paint" else None
        p = self.picker
        if w is None or p is None or getattr(p, "owner", None) is not w:
            return None
        return getattr(w, "cell_target", None)

    def _on_b1_double(self, ev):
        """Paint tools: double-click a cell = colour picker on that cell. The
        selection is put back to what it was before the double-click."""
        if self.tool != "paint" or self.res is None:
            return
        slot = self._slot_at(ev.x, ev.y)
        ent = self._view_entry(slot) if slot is not None else None
        if ent is None:
            return
        self.selection = set(self._sel_before_click)
        if self._ramp_backup is not None or self._filt_backup is not None:
            self.status_var.set("A preview is open - Apply or Cancel it first.")
            self.recompute()
            return
        self.tool_win.target_cell(ent[0])
        self.recompute()
        return "break"

    def drop_colour_on_grid(self, x_root, y_root, rgb):
        if self.rgbs is None:
            return
        slot = self._slot_at(x_root - self.canvas.winfo_rootx(),
                             y_root - self.canvas.winfo_rooty())
        ent = self._view_entry(slot) if slot is not None else None
        if ent is None:
            self.status_var.set("Drop onto a palette cell.")
            return
        self.set_cells_colour([ent[0]], rgb)
