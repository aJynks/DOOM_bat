"""Reorder tools window + preview / apply (App mixin).

Opened / closed through the tool host (tool_windows.py), which handles the
clean-snapshot gate. While open, culling is paused and Align is ignored.
"""

import json

from ..constants import ENTRIES, fmt_tol
from ..sorting import (
    OUTLIER_MODES, RAMP_ORDERS, SORT_KEY_NAMES, SORT_METHOD_INFO, SORT_METHOD_NAMES,
    ramp_sort,
)


class ReorderDialog:
    """The Reorder colours window. Settings live on the App (so presets,
    projects and remembered settings keep working); this only holds widgets."""

    def __init__(self, app):
        tk = app.tk
        from tkinter import ttk

        self.app = app
        self.win = win = tk.Toplevel(app.root)
        win.title("Reorder tools")
        win.transient(app.root)
        win.resizable(True, False)
        win.protocol("WM_DELETE_WINDOW", app.close_tool)
        win.bind("<Escape>", lambda e: self._on_escape())
        win.bind("<Control-z>", app._on_undo_key)
        win.bind("<Control-Z>", app._on_undo_key)

        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text="Culling is paused while this window is open.\n"
                          "Select colours in the grid to reorder just those.",
                  foreground="#666").grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(f, text="Method").grid(row=1, column=0, sticky="w", pady=(10, 0))
        cb = ttk.Combobox(f, textvariable=app.sort_method_var, values=SORT_METHOD_NAMES,
                          state="readonly", width=24)
        cb.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: app._on_sort_method())

        scf = ttk.Frame(f)
        scf.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(scf, text="Apply to:").pack(side="left")
        for text, val in (("Whole palette", "all"), ("Selected (gathered)", "selected")):
            ttk.Radiobutton(scf, text=text, value=val, variable=app.sort_scope_var,
                            command=app._on_sort_option).pack(side="left", padx=(6, 0))
        self.sel_var = tk.StringVar(value="")
        ttk.Label(scf, textvariable=self.sel_var, foreground="#888").pack(
            side="left", padx=(6, 0))

        # per-method options, rebuilt when the method changes
        app.sort_opt_frame = ttk.Frame(f)
        app.sort_opt_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        app.sort_opt_frame.columnconfigure(0, weight=1)

        # shared ordering options
        shf = ttk.Frame(f)
        shf.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        shf.columnconfigure(1, weight=1)
        app.sort_shared = {}
        ttk.Label(shf, text="Order colours by").grid(row=0, column=0, sticky="w")
        w = ttk.Combobox(shf, textvariable=app.sort_key_var, values=SORT_KEY_NAMES,
                         state="readonly", width=20)
        w.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        w.bind("<<ComboboxSelected>>", lambda e: app._on_sort_option())
        app.sort_shared["key"] = [w]
        dirf = ttk.Frame(shf)
        dirf.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        app.sort_shared["dir"] = [
            ttk.Radiobutton(dirf, text="Lightest / highest first", value=True,
                            variable=app.sort_high_var, command=app._on_sort_option),
            ttk.Radiobutton(dirf, text="Darkest / lowest first", value=False,
                            variable=app.sort_high_var, command=app._on_sort_option)]
        for rb in app.sort_shared["dir"]:
            rb.pack(side="left", padx=(0, 8))
        ttk.Label(shf, text="Ramp order").grid(row=2, column=0, sticky="w", pady=(4, 0))
        w = ttk.Combobox(shf, textvariable=app.sort_order_var, values=RAMP_ORDERS,
                         state="readonly", width=20)
        w.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: app._on_sort_option())
        app.sort_shared["ramps"] = [w]
        ttk.Label(shf, text="Outliers").grid(row=3, column=0, sticky="w", pady=(4, 0))
        w = ttk.Combobox(shf, textvariable=app.sort_outlier_var, values=OUTLIER_MODES,
                         state="readonly", width=20)
        w.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: app._on_sort_option())
        app.sort_shared["ramps"].append(w)
        ttk.Label(shf, text="Min ramp size").grid(row=4, column=0, sticky="w", pady=(4, 0))
        w = ttk.Spinbox(shf, textvariable=app.sort_min_text, from_=1, to=64,
                        increment=1, width=6, command=app._on_sort_min)
        w.grid(row=4, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        w.bind("<Return>", lambda e: app._on_sort_min())
        w.bind("<FocusOut>", lambda e: app._on_sort_min())
        app.sort_shared["ramps"].append(w)

        ttk.Separator(f).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        bf = ttk.Frame(f)
        bf.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        app.sort_prev_btn = tk.Button(bf, text="Preview: OFF", width=12, relief="raised",
                                      command=app._on_sort_preview)
        app._sort_btn_bg = app.sort_prev_btn.cget("background")
        app.sort_prev_btn.pack(side="left")
        ttk.Button(bf, text="Apply", command=app.sort_apply).pack(side="left", padx=(6, 0))
        app.sort_cancel_btn = ttk.Button(bf, text="Cancel", command=app.sort_cancel)
        app.sort_cancel_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bf, text="Close", command=app.close_tool).pack(side="right")

        app._build_sort_options()
        app._update_sort_btn()
        self._place()

    def _place(self):
        """Last position if known, else beside the main window's right edge."""
        app = self.app
        self.win.update_idletasks()
        pos = app.s.get("reorder_pos")
        if isinstance(pos, str) and pos.startswith("+"):
            try:
                self.win.geometry(pos)
                return
            except app.tk.TclError:
                pass
        r = app.root
        x = r.winfo_rootx() + max(0, r.winfo_width() - self.win.winfo_reqwidth() - 60)
        y = r.winfo_rooty() + 80
        self.win.geometry("+%d+%d" % (x, y))

    def _on_escape(self):
        if self.app._sort_backup is not None:
            self.app.sort_cancel()
        else:
            self.app.close_tool()

    def refresh(self):
        a = self.app
        if a.rgbs is None:
            self.sel_var.set("")
            return
        n = sum(1 for i in a.selection if a.rgbs[i] is not None)
        self.sel_var.set("(%d selected)" % n)

    def store_pos(self):
        try:
            self.app.s["reorder_pos"] = "+%d+%d" % (self.win.winfo_x(), self.win.winfo_y())
        except self.app.tk.TclError:
            pass

    def lift(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_set()


class SortMixin:
    """Reorder colours: gate, popup window, preview / apply."""

    # ---------------------------------------------------------- open / close
    def _reorder_open(self):
        """Called by open_tool('reorder')."""
        n = sum(1 for i in self.selection if self.rgbs[i] is not None)
        self.sort_scope_var.set("selected" if n >= 2 else "all")
        self.reorder = ReorderDialog(self)
        self.tool_win = self.reorder

    def _reorder_teardown(self):
        """Called by close_tool() after any preview was cancelled."""
        if self.reorder is None:
            return
        self.reorder.store_pos()
        try:
            self.reorder.win.destroy()
        except self.tk.TclError:
            pass
        self.reorder = None
        self.sort_opt_frame = None
        self.sort_prev_btn = None
        self.sort_cancel_btn = None
        self.sort_shared = {}
        self._sort_param_vars = {}

    def _reorder_sync_scope(self):
        """While the window is open (preview off), grid selection picks the scope."""
        if self.reorder is None or self._sort_backup is not None or self.rgbs is None:
            return
        n = sum(1 for i in self.selection if self.rgbs[i] is not None)
        self.sort_scope_var.set("selected" if n >= 2 else "all")

    # ---------------------------------------------------------- options
    def _build_sort_options(self):
        """(Re)build the option boxes for the current method (window open only)."""
        if self.reorder is None or self.sort_opt_frame is None:
            return
        from tkinter import ttk

        f = self.sort_opt_frame
        for ch in f.winfo_children():
            ch.destroy()
        m = self.sort_method_var.get()
        _name, kind, spec = SORT_METHOD_INFO[m]
        self._sort_param_vars = {}
        vals = self.sort_params.setdefault(m, {})
        for row, (name, label, dflt, lo, hi, step) in enumerate(spec):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=(0, 2))
            v = self.tk.StringVar(value=fmt_tol(vals.get(name, dflt)))
            sp = ttk.Spinbox(f, textvariable=v, from_=lo, to=hi, increment=step, width=7,
                             command=lambda n=name: self._on_sort_param(n))
            sp.grid(row=row, column=1, sticky="e", padx=(6, 0), pady=(0, 2))
            sp.bind("<Return>", lambda e, n=name: self._on_sort_param(n, tidy=True))
            sp.bind("<FocusOut>", lambda e, n=name: self._on_sort_param(n, tidy=True))
            v.trace_add("write", lambda *_a, n=name: self._on_sort_param(n))
            self._sort_param_vars[name] = (v, lo, hi)
        if not spec:
            hint = {"Gradient path": "One smooth nearest-colour chain (OKLab).",
                    "Single key": "Plain sort by 'Order colours by'.",
                    "Reverse": "Reverses the order."}.get(m, "")
            ttk.Label(f, text=hint, foreground="#666").grid(row=0, column=0, sticky="w")
        # shared options only where they mean something
        states = {"key": kind == "ramps" or m == "Single key",
                  "dir": m != "Reverse",
                  "ramps": kind == "ramps"}
        for grp, on in states.items():
            for w in self.sort_shared.get(grp, []):
                w.state(["!disabled"] if on else ["disabled"])
        try:
            self.reorder.win.update_idletasks()
        except self.tk.TclError:
            pass

    def _on_sort_method(self):
        self._build_sort_options()
        self._on_sort_option()

    def _on_sort_param(self, name, tidy=False):
        if name not in self._sort_param_vars:
            return
        v, lo, hi = self._sort_param_vars[name]
        m = self.sort_method_var.get()
        try:
            x = float(v.get())
        except ValueError:
            x = None
        if x is not None and x == x:
            x = min(max(x, lo), hi)
            if self.sort_params[m].get(name) != x:
                self.sort_params[m][name] = x
                self._on_sort_option()
        if tidy:
            v.set(fmt_tol(self.sort_params[m].get(name, lo)))

    def _on_sort_min(self):
        try:
            x = int(float(self.sort_min_text.get()))
        except ValueError:
            x = self.sort_min
        x = min(max(x, 1), 64)
        self.sort_min_text.set(str(x))
        if x != self.sort_min:
            self.sort_min = x
            self._on_sort_option()

    def _on_sort_option(self):
        """Any sort setting changed: re-sort the preview (debounced)."""
        if self._sort_backup is None:
            return
        if self._sort_after is not None:
            self.root.after_cancel(self._sort_after)
        self._sort_after = self.root.after(120, self._sort_refresh)

    # ---------------------------------------------------------- sorting
    def _sort_perm(self):
        """(perm, n_ramps, block) for the current settings, or a message."""
        rgbs = self.rgbs
        if self.sort_scope_var.get() == "selected":
            idxs = sorted(i for i in self.selection if rgbs[i] is not None)
            if len(idxs) < 2:
                return "Select at least two colours, or set Apply to: Whole palette."
        else:
            idxs = [i for i in range(ENTRIES) if rgbs[i] is not None]
            if len(idxs) < 2:
                return "Nothing to reorder."
        order, nr = ramp_sort(
            [rgbs[i] for i in idxs], self.sort_method_var.get(),
            self.sort_params.get(self.sort_method_var.get()),
            key=self.sort_key_var.get(), high_first=self.sort_high_var.get(),
            ramp_order=self.sort_order_var.get(), outliers=self.sort_outlier_var.get(),
            min_size=self.sort_min)
        block = [idxs[k] for k in order]
        if self.sort_scope_var.get() == "selected":
            bs = set(block)
            rest = [i for i in range(ENTRIES) if i not in bs]
            pos = idxs[0]                  # block starts at the first selected slot
            perm = rest[:pos] + block + rest[pos:]
        else:
            perm = block + [i for i in range(ENTRIES) if rgbs[i] is None]
        return perm, nr, block

    def _sort_refresh(self):
        """Preview: re-sort from the pre-preview state."""
        self._sort_after = None
        if self._sort_backup is None:
            return
        b = self._sort_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.selection = set(b[3]), set(b[4])
        self.cm = self._sort_cm.copy()
        self.cm_changed()
        self._busy(True)
        try:
            r = self._sort_perm()
        finally:
            self._busy(False)
        if isinstance(r, str):
            self._sort_block = set()
            self._sort_nramps = 0
            self.status_var.set(r)
        else:
            perm, nr, block = r
            n = len(block)
            newpos = self._permute(perm)
            self._sort_block = {newpos[o] for o in block}
            self._sort_nramps = nr
            self.status_var.set("Reorder preview: %s - %d colours%s. Apply keeps it, "
                                "Cancel restores." % (
                                    self.sort_method_var.get(), n,
                                    (", %d ramps" % nr) if nr else ""))
        self.recompute()

    def _update_sort_btn(self):
        if self.reorder is None or self.sort_prev_btn is None:
            return
        on = self._sort_backup is not None
        self.sort_prev_btn.configure(
            text="Preview: ON" if on else "Preview: OFF",
            relief="sunken" if on else "raised",
            background="#7fd4ff" if on else self._sort_btn_bg,
            activebackground="#a8e2ff" if on else self._sort_btn_bg)
        self.sort_cancel_btn.state(["!disabled"] if on else ["disabled"])

    def _sort_begin(self):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return False
        if self.reorder is None:
            return False
        if self._ramp_backup is not None:
            self.status_var.set("Ramp preview is open - Apply or Cancel it first.")
            return False
        self._sort_backup = (self.rgbs, self.labs, self.pairs,
                             set(self.deleted), set(self.selection))
        self._sort_cm = self.cm.copy()
        self._update_sort_btn()
        self._refresh_history()
        return True

    def _sort_end(self):
        if self._sort_after is not None:
            self.root.after_cancel(self._sort_after)
            self._sort_after = None
        self._sort_backup = None
        self._sort_block = set()
        self._sort_nramps = 0
        self._update_sort_btn()
        self._refresh_history()

    def _on_sort_preview(self):
        if self._sort_backup is not None:
            self.sort_cancel()
            return
        if self._sort_begin():
            self._sort_refresh()

    def sort_cancel(self):
        if self._sort_backup is None:
            return
        b = self._sort_backup
        self.rgbs, self.labs, self.pairs = b[0], b[1], b[2]
        self.deleted, self.selection = set(b[3]), set(b[4])
        self.cm = self._sort_cm.copy()
        self.cm_changed()
        self._sort_end()
        self.status_var.set("Reorder preview cancelled.")
        self.recompute()

    def sort_apply(self):
        """Commit the reorder (previewed or not) as a history entry. The
        window stays open so another selection can be reordered."""
        if self._sort_backup is None:
            if not self._sort_begin():
                return
        if self._sort_after is not None or not self._sort_block:
            if self._sort_after is not None:
                self.root.after_cancel(self._sort_after)
                self._sort_after = None
            self._sort_refresh()           # options changed since / never shown
        before = self._sort_backup[0]
        scope = self.sort_scope_var.get()
        n_sel = len([i for i in self._sort_backup[4] if before[i] is not None])
        nr = self._sort_nramps
        ok = bool(self._sort_block)
        self._sort_end()
        if not ok:
            self.recompute()
            return
        if self.rgbs == before:
            self.status_var.set("Already in that order - nothing changed.")
            self.recompute()
            return
        text = "Reorder %s%s%s - %d colours" % (
            self.sort_method_var.get(), (" (%d ramps)" % nr) if nr else "",
            (" on %d selected" % n_sel) if scope == "selected" else "",
            sum(1 for e in self.rgbs if e is not None))
        self._push_history(text)
        self.status_var.set("Reordered - recorded as #%d (Back / Ctrl+Z undoes it)."
                            % self.hist_pos)
        self.recompute()

    def current_sort_settings(self):
        return {"sort_method": self.sort_method_var.get(),
                "sort_params": json.loads(json.dumps(self.sort_params)),
                "sort_key": self.sort_key_var.get(), "sort_high": self.sort_high_var.get(),
                "sort_ramp_order": self.sort_order_var.get(),
                "sort_outliers": self.sort_outlier_var.get(), "sort_min": self.sort_min}
