"""Paint tools -> Filters window: classic colour filters on the selection."""

from ..colour import hex_of
from ..filters import FILTER_NAMES, FILTERS, clean_params, defaults
from ..constants import fmt_tol


class FilterWindow:
    STRIP_MAX = 64          # swatches shown in the before / after strip

    def __init__(self, app):
        tk = app.tk
        from tkinter import ttk

        self.app = app
        s = app.s
        self.ui = ui = getattr(app, "ui", 1.0)          # monitor scale, like the main window
        self.win = tk.Toplevel(app.root)
        self.win.title("Paint filters")
        self.win.transient(app.root)
        self.win.minsize(int(560 * ui), int(420 * ui))
        try:
            self.win.geometry(s.get("filter_geometry") or "%dx%d" % (640 * ui, 520 * ui))
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self._on_escape())
        self.win.columnconfigure(1, weight=1)
        self.win.rowconfigure(0, weight=1)

        store = s.get("filter_params")
        self.params = {n: clean_params(n, (store or {}).get(n)) if isinstance(store, dict)
                       else defaults(n) for n in FILTER_NAMES}
        cur = s.get("filter_current")
        self.current = cur if cur in FILTERS else FILTER_NAMES[0]
        self._vars = {}
        self._after = None
        self._building = False

        # left: filter list
        lf = ttk.Frame(self.win, padding=(8, 8, 4, 8))
        lf.grid(row=0, column=0, sticky="ns")
        self.lb = tk.Listbox(lf, height=len(FILTER_NAMES), exportselection=False,
                             activestyle="none", width=26)
        for n in FILTER_NAMES:
            self.lb.insert("end", n)
        self.lb.pack(fill="y", expand=True)
        self.lb.bind("<<ListboxSelect>>", self._on_pick)

        # right: description + options
        rf = ttk.Frame(self.win, padding=(4, 8, 8, 8))
        rf.grid(row=0, column=1, sticky="nsew")
        rf.columnconfigure(0, weight=1)
        self.desc_var = tk.StringVar()
        self.desc_lbl = ttk.Label(rf, textvariable=self.desc_var, foreground="#666",
                                  justify="left")
        self.desc_lbl.grid(row=0, column=0, sticky="ew")
        # wrap to the real width of the options area (re-wraps on resize)
        rf.bind("<Configure>", lambda e: self.desc_lbl.configure(
            wraplength=max(100, e.width - int(12 * ui))))
        self.opt = ttk.Frame(rf)
        self.opt.grid(row=1, column=0, sticky="new", pady=(8, 0))
        self.opt.columnconfigure(1, weight=1)

        # before / after strip
        sf = ttk.LabelFrame(self.win, text="Selection: before (top) / after (bottom)",
                            padding=6)
        sf.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8)
        self.strip = tk.Canvas(sf, height=int(60 * ui), bg="#262626", highlightthickness=0)
        self.strip.pack(fill="x")
        self.strip.bind("<Configure>", lambda e: self.refresh())
        self.count_var = tk.StringVar()
        ttk.Label(sf, textvariable=self.count_var, foreground="#666").pack(anchor="w")

        # buttons
        bf = ttk.Frame(self.win, padding=8)
        bf.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.prev_btn = tk.Button(bf, text="Preview: OFF", width=12, relief="raised",
                                  command=self.toggle_preview)
        self._btn_bg = self.prev_btn.cget("background")
        self.prev_btn.pack(side="left")
        ttk.Button(bf, text="Apply", command=self.apply).pack(side="left", padx=(6, 0))
        self.cancel_btn = ttk.Button(bf, text="Cancel", command=app.filter_cancel)
        self.cancel_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bf, text="Reset", command=self.reset).pack(side="left", padx=(12, 0))
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")

        self.lb.selection_set(FILTER_NAMES.index(self.current))
        self._build_options()
        self.update_buttons()
        self.refresh()

    # ---------------------------------------------------------- options
    def _build_options(self):
        tk = self.app.tk
        from tkinter import ttk

        self._building = True
        for ch in self.opt.winfo_children():
            ch.destroy()
        self._vars = {}
        spec = FILTERS[self.current]
        self.desc_var.set(spec["desc"])
        vals = self.params[self.current]
        for row, p in enumerate(spec["params"]):
            key, label, kind = p[0], p[1], p[2]
            if kind == "bool":
                v = tk.BooleanVar(value=bool(vals[key]))
                ttk.Checkbutton(self.opt, text=label, variable=v,
                                command=lambda k=key: self._changed(k)).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=2)
            elif kind == "choice":
                ttk.Label(self.opt, text=label).grid(row=row, column=0, sticky="w", pady=2)
                v = tk.StringVar(value=vals[key])
                cb = ttk.Combobox(self.opt, textvariable=v, values=p[3], state="readonly",
                                  width=30)
                cb.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2)
                cb.bind("<<ComboboxSelected>>", lambda e, k=key: self._changed(k))
            else:
                lo, hi, step = p[3], p[4], p[5]
                ttk.Label(self.opt, text=label).grid(row=row, column=0, sticky="w", pady=2)
                v = tk.StringVar(value=fmt_tol(vals[key]))
                ui = self.ui
                sc = tk.Scale(self.opt, from_=lo, to=hi, resolution=step, orient="horizontal",
                              showvalue=0, length=int(200 * ui), sliderlength=int(36 * ui),
                              width=int(22 * ui),
                              command=lambda x, k=key: self._scale(k, x))
                sc.set(vals[key])
                sc.grid(row=row, column=1, sticky="ew", padx=(8, 4), pady=2)
                sp = ttk.Spinbox(self.opt, textvariable=v, from_=lo, to=hi, increment=step,
                                 width=7, command=lambda k=key: self._changed(k))
                sp.grid(row=row, column=2, sticky="e", pady=2)
                sp.bind("<Return>", lambda e, k=key: self._changed(k, tidy=True))
                sp.bind("<FocusOut>", lambda e, k=key: self._changed(k, tidy=True))
                self._vars[key + ".scale"] = sc
            self._vars[key] = v
        self._building = False

    def _scale(self, key, x):
        if self._building:
            return
        v = self._vars[key]
        if v.get() != fmt_tol(float(x)):
            v.set(fmt_tol(float(x)))
            self._changed(key)

    def _changed(self, key, tidy=False):
        if self._building:
            return
        p = next(q for q in FILTERS[self.current]["params"] if q[0] == key)
        v = self._vars[key]
        vals = self.params[self.current]
        if p[2] == "num":
            try:
                x = float(v.get())
            except ValueError:
                x = None
            if x is not None and x == x:
                vals[key] = min(max(x, p[3]), p[4])
                sc = self._vars.get(key + ".scale")
                if sc is not None and abs(float(sc.get()) - vals[key]) > 1e-9:
                    self._building = True
                    sc.set(vals[key])
                    self._building = False
            if tidy:
                v.set(fmt_tol(vals[key]))
        else:
            vals[key] = v.get()
        self._store()
        self.schedule()

    def _on_pick(self, _ev):
        sel = self.lb.curselection()
        if not sel or FILTER_NAMES[sel[0]] == self.current:
            return
        self.current = FILTER_NAMES[sel[0]]
        self._build_options()
        self._store()
        self.schedule()

    def reset(self):
        self.params[self.current] = defaults(self.current)
        self._build_options()
        self._store()
        self.schedule()

    def _store(self):
        self.app.s["filter_params"] = {n: dict(v) for n, v in self.params.items()}
        self.app.s["filter_current"] = self.current

    # ---------------------------------------------------------- run
    def settings(self):
        return self.current, dict(self.params[self.current])

    def schedule(self):
        if self._after is not None:
            self.win.after_cancel(self._after)
        self._after = self.win.after(60, self._run)

    def _run(self):
        self._after = None
        if self.app._filt_backup is not None:
            self.app.filter_preview_refresh()     # recompute -> refresh()
        else:
            self.refresh()

    def toggle_preview(self):
        a = self.app
        if a._filt_backup is not None:
            a.filter_cancel()
        elif a.filter_preview_start():
            a.filter_preview_refresh()
        self.update_buttons()

    def apply(self):
        self.app.filter_apply()
        self.update_buttons()

    def update_buttons(self):
        on = self.app._filt_backup is not None
        try:
            self.prev_btn.configure(text="Preview: ON" if on else "Preview: OFF",
                                    relief="sunken" if on else "raised",
                                    background="#ffb36b" if on else self._btn_bg,
                                    activebackground="#ffc68f" if on else self._btn_bg)
            self.cancel_btn.state(["!disabled"] if on else ["disabled"])
        except self.app.tk.TclError:
            pass

    def refresh(self):
        """Redraw the before / after strip for the current selection."""
        a = self.app
        try:
            cv = self.strip
            cv.delete("all")
        except a.tk.TclError:
            return
        targets, before, after = a.filter_compute()
        n = len(targets)
        self.count_var.set("%d selected colour%s%s" % (
            n, "" if n == 1 else "s",
            "" if n <= self.STRIP_MAX else " (first %d shown)" % self.STRIP_MAX)
            if n else "Select palette colours to filter (blank cells are skipped).")
        if not n:
            return
        before, after = before[:self.STRIP_MAX], after[:self.STRIP_MAX]
        ui = self.ui
        w = max(cv.winfo_width(), 100)
        cell = max(4, min(int(28 * ui), (w - 4) // len(before)))
        half = int(29 * ui)                     # each row's height (strip is 60 * ui)
        others = set(c for i, c in enumerate(a._filter_base()[0]) if c is not None
                     and i not in set(targets))
        for k, (b, c) in enumerate(zip(before, after)):
            x = 2 + k * cell
            cv.create_rectangle(x, 2, x + cell - 1, half - 1, fill=hex_of(b), outline="")
            cv.create_rectangle(x, half + 2, x + cell - 1, 2 * half, fill=hex_of(c),
                                outline="")
            t = int(7 * ui)
            if tuple(c) in others and cell >= 2 * t:      # already in the palette
                cv.create_polygon(x, half + 2, x + t, half + 2, x, half + 2 + t,
                                  fill="#ffffff", outline="#000")

    def _on_escape(self):
        if self.app._filt_backup is not None:
            self.app.filter_cancel()
            self.update_buttons()
        else:
            self.close()

    def close(self):
        a = self.app
        if a._filt_backup is not None:
            a.filter_cancel()
        if self._after is not None:
            self.win.after_cancel(self._after)
        try:
            a.s["filter_geometry"] = self.win.geometry()
        except a.tk.TclError:
            pass
        self._store()
        a.filter_win = None
        try:
            self.win.destroy()
        except a.tk.TclError:
            pass
