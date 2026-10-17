"""COLORMAP mode (App mixin): fade strips / matrix view, hand edits, bulk
tools, create fade colours, diagnostics, COLORMAP files."""

import os

from ..analysis import update_pairs
from ..colormap import (
    CMAP_EXPORTS, CMAP_METHODS, DARK_ROW, DIAG_TYPES, INVUL_MODES, INVUL_ROW, LIGHT_ROWS,
    CmapState, apply_shape, clean_cmap_settings, default_cmap_settings, diagnose,
    fade_shape, fade_within, generate, import_overrides, load_colormap,
    propose_fade_colours, read_wad_lump, rows_from_bytes, write_colormap,
)
from ..colour import hex_of, parse_colour
from ..constants import ENTRIES, fmt_tol

MODES = ["PLAYPAL", "COLORMAP"]


class CmapMixin:
    """COLORMAP mode for the main window."""

    # ---------------------------------------------------------- state
    def _cmap_init(self):
        tk = self.tk
        s = self.s
        self.cm = CmapState()
        self.cmap_loaded = None          # {"rows", "pal", "name"}
        self.cmap_set = default_cmap_settings()
        try:
            self.cmap_set.update(clean_cmap_settings(s))
        except ValueError:
            pass
        self._cm_ver = 0
        self._cmap_cache = (None, None, None)     # (signature, result, flags)
        self.mode_var = tk.StringVar(value=MODES[0])
        self.cmap_tool = tk.StringVar(value="Paint")
        self.cmap_view = tk.StringVar(value="Fades")
        self.cmap_diag_on = tk.BooleanVar(value=True)
        self.cmap_brush = None
        self.cmap_target_set = set()
        self._cmap_shape = None
        self._fade_scroll = 0
        self._fade_cells = []
        self._fade_drag = None
        self._fade_after = None
        self._sort_cm = None
        self._ramp_cm = None
        self.cmap_show_extra = tk.BooleanVar(value=bool(s.get("cmap_show_extra", False)))
        self.cmap_markers = tk.BooleanVar(value=bool(s.get("cmap_markers", True)))
        self.fstrips = {}              # Ramp tool: src slot -> start row
        self.fref = None               # reference strip for the fade Ramp tool
        self._framp_backup = None      # CmapState before the fade-ramp preview
        self._framp_base = None        # COLORMAP result before the preview
        self._fade_labels = []
        self._pane_min = None          # None / "palette" / "fades"
        self._sash_prev = None

    def cm_changed(self):
        self._cm_ver += 1

    def cmap_signature(self):
        rg = tuple(self.rgbs) if self.rgbs is not None else None
        return (rg, frozenset(self.deleted), self._cm_ver,
                tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                             for k, v in self.cmap_set.items())),
                id(self.cmap_loaded))

    def cmap_result(self, base=False):
        """Generated COLORMAP (+ diagnostics) for the working palette, cached.
        base=True: the result from before an open fade-ramp preview."""
        if self.rgbs is None:
            return None, {}
        if base and self._framp_base is not None:
            return self._framp_base, {}
        sig = self.cmap_signature()
        if self._cmap_cache[0] == sig:
            return self._cmap_cache[1], self._cmap_cache[2]
        res = generate(self.rgbs, self.deleted, self.cmap_set, self.cm, self.cmap_loaded)
        flags = diagnose(self.rgbs, res, self.cm)
        self._cmap_cache = (sig, res, flags)
        return res, flags

    def cmap_mode(self):
        return self.mode_var.get() == MODES[1]

    # ---------------------------------------------------------- UI build
    def _build_cmap_panel(self, side):
        """COLORMAP side-panel frames (shown only in COLORMAP mode)."""
        from tkinter import ttk

        tk = self.tk
        ui = getattr(self, "ui", 1.0)
        frames = []

        # --- file + generation
        gf = ttk.LabelFrame(side, text="COLORMAP", padding=8)
        frames.append(gf)
        self.cmap_status = tk.StringVar(value="Generated from the palette")
        ttk.Label(gf, textvariable=self.cmap_status, foreground="#666",
                  wraplength=int(300 * ui)).pack(anchor="w")
        r = ttk.Frame(gf)
        r.pack(fill="x", pady=(6, 0))
        ttk.Button(r, text="Open COLORMAP...", command=self.cmap_open).pack(side="left")
        self.cmap_import_btn = ttk.Button(r, text="Import as hand edits",
                                          command=self.cmap_import)
        self.cmap_import_btn.pack(side="left", padx=(6, 0))
        g = ttk.Frame(gf)
        g.pack(fill="x", pady=(8, 0))
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="Matching").grid(row=0, column=0, sticky="w")
        self.cmap_method_var = tk.StringVar(value=self.cmap_set["cmap_method"])
        w = ttk.Combobox(g, textvariable=self.cmap_method_var, values=CMAP_METHODS,
                         state="readonly", width=28)
        w.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._cmap_set_opt())
        ttk.Label(g, text="Fade curve").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.cmap_curve_var = tk.StringVar(value=fmt_tol(self.cmap_set["cmap_curve"]))
        sp = ttk.Spinbox(g, textvariable=self.cmap_curve_var, from_=0.25, to=4.0,
                         increment=0.05, width=7, command=self._cmap_set_opt)
        sp.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        sp.bind("<Return>", lambda e: self._cmap_set_opt())
        sp.bind("<FocusOut>", lambda e: self._cmap_set_opt())
        ttk.Label(g, text="Fade toward").grid(row=2, column=0, sticky="w", pady=(4, 0))
        tf = ttk.Frame(g)
        tf.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        self.cmap_target_sw = tk.Canvas(tf, width=int(24 * ui), height=int(18 * ui),
                                        highlightthickness=1, highlightbackground="#888")
        self.cmap_target_sw.pack(side="left")
        self.cmap_target_var = tk.StringVar(value=hex_of(self.cmap_set["cmap_target"])[1:])
        te = ttk.Entry(tf, textvariable=self.cmap_target_var, width=9)
        te.pack(side="left", padx=(4, 0))
        te.bind("<Return>", lambda e: self._cmap_set_opt())
        te.bind("<FocusOut>", lambda e: self._cmap_set_opt())
        self.register_colour_widget(
            te, lambda: tuple(self.cmap_set["cmap_target"]),
            lambda rgb: (self.cmap_target_var.set(hex_of(rgb)[1:]), self._cmap_set_opt()))
        il = ttk.Label(g, text="Invulnerability")
        il.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.cmap_invul_var = tk.StringVar(value=self.cmap_set["cmap_invul"])
        w = ttk.Combobox(g, textvariable=self.cmap_invul_var, values=INVUL_MODES,
                         state="readonly", width=28)
        w.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._cmap_set_opt())
        self._invul_widgets = (il, w)
        self.cmap_smooth_var = tk.BooleanVar(value=bool(self.cmap_set["cmap_smooth"]))
        ttk.Checkbutton(gf, text="Auto-fill smoothly between hand-set steps",
                        variable=self.cmap_smooth_var,
                        command=self._cmap_set_opt).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(gf, text="Show invulnerability + dark rows",
                        variable=self.cmap_show_extra,
                        command=self._on_show_extra).pack(anchor="w", pady=(2, 0))
        x = ttk.Frame(gf)
        x.pack(fill="x", pady=(8, 0))
        self.cmap_export_var = tk.StringVar(value=CMAP_EXPORTS[0][0])
        ttk.Combobox(x, textvariable=self.cmap_export_var,
                     values=[e[0] for e in CMAP_EXPORTS], state="readonly",
                     width=26).pack(side="left")
        ttk.Button(x, text="Export...", command=self.cmap_export).pack(side="right")

        # --- bulk edits on the selection
        ef = ttk.LabelFrame(side, text="Edit fades of selected colours", padding=8)
        frames.append(ef)
        r = ttk.Frame(ef)
        r.pack(fill="x")
        ttk.Button(r, text="Full bright", command=lambda: self.cmap_fullbright(True)).pack(
            side="left")
        ttk.Button(r, text="Normal", command=lambda: self.cmap_fullbright(False)).pack(
            side="left", padx=(4, 0))
        ttk.Button(r, text="Clear hand edits", command=self.cmap_clear).pack(side="right")

        ttk.Label(ef, text="Fade down through the selection itself:").pack(
            anchor="w", pady=(8, 0))
        r = ttk.Frame(ef)
        r.pack(fill="x", pady=(2, 0))
        self.fw_order = tk.StringVar(value="Lightness")
        ttk.Combobox(r, textvariable=self.fw_order, values=["Lightness", "Index"],
                     state="readonly", width=9).pack(side="left")
        ttk.Label(r, text="steps/level").pack(side="left", padx=(6, 0))
        self.fw_spl = tk.StringVar(value="0.5")
        ttk.Spinbox(r, textvariable=self.fw_spl, from_=0.05, to=4, increment=0.05,
                    width=5).pack(side="left", padx=(4, 0))
        self.fw_end = tk.StringVar(value="Black")
        ttk.Combobox(r, textvariable=self.fw_end, values=["Black", "Auto"],
                     state="readonly", width=6).pack(side="left", padx=(6, 0))
        ttk.Button(r, text="Apply", command=self.cmap_fade_within).pack(side="right")

        ttk.Label(ef, text="Limit which colours their fades may use:").pack(
            anchor="w", pady=(8, 0))
        r = ttk.Frame(ef)
        r.pack(fill="x", pady=(2, 0))
        ttk.Button(r, text="Store selection as targets",
                   command=self.cmap_store_targets).pack(side="left")
        self.cmap_tset_var = tk.StringVar(value="(none)")
        ttk.Label(r, textvariable=self.cmap_tset_var, foreground="#666").pack(
            side="left", padx=(6, 0))
        r = ttk.Frame(ef)
        r.pack(fill="x", pady=(2, 0))
        ttk.Button(r, text="Limit to targets (+ fade colour)",
                   command=lambda: self.cmap_limit(True)).pack(side="left")
        ttk.Button(r, text="Remove limit",
                   command=lambda: self.cmap_limit(False)).pack(side="left", padx=(4, 0))

        r = ttk.Frame(ef)
        r.pack(fill="x", pady=(8, 0))
        ttk.Label(r, text="Fade curve").pack(side="left")
        self.cmap_scurve = tk.StringVar(value="1.0")
        ttk.Spinbox(r, textvariable=self.cmap_scurve, from_=0.25, to=4.0, increment=0.05,
                    width=6).pack(side="left", padx=(4, 0))
        ttk.Button(r, text="Set", width=5, command=lambda: self.cmap_curve(True)).pack(
            side="left", padx=(4, 0))
        ttk.Button(r, text="Clear", width=6, command=lambda: self.cmap_curve(False)).pack(
            side="left", padx=(4, 0))
        r = ttk.Frame(ef)
        r.pack(fill="x", pady=(8, 0))
        ttk.Button(r, text="Copy fade shape", command=self.cmap_copy_shape).pack(side="left")
        self.paste_shape_btn = ttk.Button(r, text="Paste shape to selected",
                                          command=self.cmap_paste_shape)
        self.paste_shape_btn.pack(side="left", padx=(4, 0))
        self.paste_shape_btn.state(["disabled"])

        # --- create fade colours
        cf = ttk.LabelFrame(side, text="Create fade colours", padding=8)
        frames.append(cf)
        r = ttk.Frame(cf)
        r.pack(fill="x")
        self.cf_scope = tk.StringVar(value="all")
        ttk.Radiobutton(r, text="Whole palette", value="all",
                        variable=self.cf_scope).pack(side="left")
        ttk.Radiobutton(r, text="Selected", value="selected",
                        variable=self.cf_scope).pack(side="left", padx=(6, 0))
        r = ttk.Frame(cf)
        r.pack(fill="x", pady=(4, 0))
        ttk.Label(r, text="Budget (new colours)").pack(side="left")
        self.cf_budget = tk.StringVar(value="8")
        ttk.Spinbox(r, textvariable=self.cf_budget, from_=1, to=128, increment=1,
                    width=5).pack(side="left", padx=(4, 0))
        ttk.Button(r, text="Find...", command=self.cmap_find_colours).pack(side="right")
        self.cf_free_var = tk.StringVar(value="")
        ttk.Label(cf, textvariable=self.cf_free_var, foreground="#666").pack(anchor="w",
                                                                           pady=(4, 0))

        # --- diagnostics
        df = ttk.LabelFrame(side, text="Diagnostics", padding=8)
        frames.append(df)
        ttk.Checkbutton(df, text="Highlight problem steps", variable=self.cmap_diag_on,
                        command=self._fade_schedule).pack(anchor="w")
        self.diag_vars = {}
        dr = ttk.Frame(df)
        dr.pack(fill="x", pady=(4, 0))
        for k, (label, col) in DIAG_TYPES.items():
            f = ttk.Frame(dr)
            f.pack(anchor="w")
            c = tk.Canvas(f, width=12, height=12, highlightthickness=0)
            c.create_rectangle(1, 1, 11, 11, outline=col, width=2)
            c.pack(side="left")
            v = tk.StringVar(value=label)
            ttk.Label(f, textvariable=v).pack(side="left", padx=(4, 0))
            self.diag_vars[k] = (v, label)
        lf = ttk.Frame(df)
        lf.pack(fill="x", pady=(6, 0))
        self.diag_list = tk.Listbox(lf, height=6, activestyle="none", exportselection=False,
                                    font=("Consolas", 9))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.diag_list.yview)
        self.diag_list.configure(yscrollcommand=sb.set)
        self.diag_list.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.diag_list.bind("<<ListboxSelect>>", self._on_diag_pick)
        self._diag_rows = []
        self._cmap_frames = frames
        self._cmap_target_swatch()
        self._sync_extra_widgets()

    def _build_fade_frame(self, parent):
        """Toolbar + fade/matrix canvas under the palette grid."""
        from tkinter import ttk

        tk = self.tk
        ui = getattr(self, "ui", 1.0)
        f = ttk.Frame(parent)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 4))
        for v in ("Fades", "Matrix"):
            ttk.Radiobutton(bar, text=v, value=v, variable=self.cmap_view,
                            command=self._fade_schedule).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(bar, text="Markers (H)", variable=self.cmap_markers,
                        command=self._on_markers).pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        for v in ("Paint", "Erase", "Pick", "Ramp"):
            ttk.Radiobutton(bar, text=v, value=v, variable=self.cmap_tool,
                            command=self._fade_schedule).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Ramp tool...", command=self.open_fade_ramp).pack(
            side="left", padx=(0, 6))
        ttk.Label(bar, text="Brush").pack(side="left", padx=(10, 4))
        self.brush_sw = tk.Canvas(bar, width=int(28 * ui), height=int(18 * ui),
                                  highlightthickness=1, highlightbackground="#888")
        self.brush_sw.pack(side="left")
        self.brush_var = tk.StringVar(value="right-click a palette cell")
        ttk.Label(bar, textvariable=self.brush_var, foreground="#666").pack(side="left",
                                                                          padx=(4, 0))
        self.min_fades_btn = ttk.Button(bar, text="\u25bc Fades", width=9,
                                        command=lambda: self.pane_minimise("fades"))
        self.min_fades_btn.pack(side="right")
        self.min_pal_btn = ttk.Button(bar, text="\u25b2 Palette", width=10,
                                      command=lambda: self.pane_minimise("palette"))
        self.min_pal_btn.pack(side="right", padx=(0, 4))
        bar.bind("<Double-Button-1>", lambda e: self.pane_restore())
        self.fade_bar = bar
        self.root.bind("<Key-h>", self._on_markers_key, add="+")
        self.root.bind("<Key-H>", self._on_markers_key, add="+")
        self.fade_cv = tk.Canvas(f, bg="#262626", highlightthickness=0,
                                 height=int(220 * ui))
        self.fade_cv.pack(fill="both", expand=True)
        cv = self.fade_cv
        cv.bind("<Configure>", lambda e: self._fade_schedule())
        cv.bind("<ButtonPress-1>", self._fade_press)
        cv.bind("<B1-Motion>", self._fade_motion)
        cv.bind("<ButtonRelease-1>", self._fade_release)
        cv.bind("<Motion>", self._fade_hover)
        cv.bind("<Leave>", lambda e: self.info_var.set(""))
        cv.bind("<MouseWheel>", lambda e: self._fade_wheel(-1 if e.delta > 0 else 1))
        cv.bind("<Button-4>", lambda e: self._fade_wheel(-1))
        cv.bind("<Button-5>", lambda e: self._fade_wheel(1))
        self.fade_frame = f
        return f

    # ---------------------------------------------------------- mode switch
    def set_mode(self, mode=None):
        if mode:
            self.mode_var.set(mode)
        cm = self.cmap_mode()
        if cm:
            self._cancel_previews()
            if self.tool is not None:              # PLAYPAL tools close first
                self.mode_var.set(MODES[0])
                ok = self.close_tool(quiet=True)
                self.mode_var.set(MODES[1])
                if not ok:
                    self.mode_var.set(MODES[0])
                    return
            for fr in self._pp_frames:
                fr.pack_forget()
            for fr in self._cmap_frames:
                fr.pack(fill="x", pady=(8, 0), before=self.snap_frame)
            if str(self.fade_frame) not in [str(p) for p in self.main_pane.panes()]:
                self.root.update_idletasks()
                self.main_pane.add(self.fade_frame, stretch="always",
                                   minsize=self._bar_height())
                self._pane_min = None
                self.root.after_idle(self._sash_restore_saved)
        else:
            if self.ramp is not None and getattr(self.ramp, "FADE", False):
                self.ramp.close()
            for fr in self._cmap_frames:
                fr.pack_forget()
            for fr in self._pp_frames_before:
                fr.pack(fill="x", pady=(8, 0), before=self.snap_frame)
            for fr in self._pp_frames_after:
                fr.pack(fill="x", pady=(8, 0), before=self.btn_frame)
            if str(self.fade_frame) in [str(p) for p in self.main_pane.panes()]:
                self.main_pane.forget(self.fade_frame)
            self._pane_min = None
        self._pp_frames[0].pack_configure(pady=(0, 0)) if not cm else None
        if cm and self._cmap_frames:
            self._cmap_frames[0].pack_configure(pady=(0, 0))
        self.root.update_idletasks()
        self._side_layout()
        self.fit_view()
        self.recompute()

    # ---------------------------------------------------------- split / minimise
    def _bar_height(self):
        return self.fade_bar.winfo_reqheight() + 6

    def _pane_total(self):
        return max(self.main_pane.winfo_height(), 1)

    def _sash_y(self):
        try:
            return self.main_pane.sash_coord(0)[1]
        except self.tk.TclError:
            return None

    def _sash_place(self, y):
        try:
            self.main_pane.sash_place(0, 0, int(max(0, min(y, self._pane_total()))))
        except self.tk.TclError:
            pass

    def _sash_restore_saved(self):
        frac = self.s.get("cmap_sash_frac", 0.42)
        if not isinstance(frac, (int, float)) or not 0.0 <= frac <= 1.0:
            frac = 0.42
        self._sash_place(self._pane_total() * frac)
        self._update_min_btns()

    def _sash_dragged(self):
        """Sash released after a drag: remember the split."""
        if not self.cmap_mode():
            return
        y = self._sash_y()
        if y is None:
            return
        self._pane_min = None
        self._update_min_btns()
        self.s["cmap_sash_frac"] = round(y / float(self._pane_total()), 4)

    def pane_minimise(self, which):
        """Minimise the palette or the fade view; again = restore."""
        if not self.cmap_mode():
            return
        if self._pane_min == which:
            self.pane_restore()
            return
        if self._pane_min is None:
            self._sash_prev = self._sash_y()
        self._pane_min = which
        if which == "palette":
            self._sash_place(0)
        else:
            self._sash_place(self._pane_total() - self._bar_height())
        self._update_min_btns()

    def pane_restore(self):
        if self._pane_min is None:
            return
        self._pane_min = None
        if self._sash_prev is not None:
            self._sash_place(self._sash_prev)
        else:
            self._sash_restore_saved()
        self._update_min_btns()

    def _update_min_btns(self):
        self.min_pal_btn.configure(text="\u25bc Palette" if self._pane_min == "palette"
                                   else "\u25b2 Palette")
        self.min_fades_btn.configure(text="\u25b2 Fades" if self._pane_min == "fades"
                                     else "\u25bc Fades")

    # ---------------------------------------------------------- markers
    def _on_markers(self):
        self.s["cmap_markers"] = bool(self.cmap_markers.get())
        self._fade_schedule()

    def _on_markers_key(self, ev):
        if not self.cmap_mode() or self._typing(ev):
            return
        self.cmap_markers.set(not self.cmap_markers.get())
        self._on_markers()

    # ---------------------------------------------------------- invul / dark rows
    def _fade_cols(self):
        """Strip columns: light rows 0-31, plus I (invulnerability) when shown."""
        return INVUL_ROW + 1 if self.cmap_show_extra.get() else LIGHT_ROWS

    def _matrix_rows(self):
        """Light rows 0-31, plus the invulnerability row when shown (never row 33)."""
        return INVUL_ROW + 1 if self.cmap_show_extra.get() else LIGHT_ROWS

    def _on_show_extra(self):
        self.s["cmap_show_extra"] = bool(self.cmap_show_extra.get())
        self._sync_extra_widgets()
        if self.preview is not None and hasattr(self.preview, "sync_extra"):
            self.preview.sync_extra()
        self._fade_schedule()

    def _sync_extra_widgets(self):
        for w in self._invul_widgets:
            if self.cmap_show_extra.get():
                w.grid()
            else:
                w.grid_remove()

    # ---------------------------------------------------------- options
    def _cmap_set_opt(self):
        s = dict(self.cmap_set)
        s["cmap_method"] = self.cmap_method_var.get()
        s["cmap_invul"] = self.cmap_invul_var.get()
        s["cmap_smooth"] = bool(self.cmap_smooth_var.get())
        try:
            s["cmap_curve"] = min(max(float(self.cmap_curve_var.get()), 0.25), 4.0)
        except ValueError:
            pass
        self.cmap_curve_var.set(fmt_tol(s["cmap_curve"]))
        c = parse_colour(self.cmap_target_var.get())
        if c is not None:
            s["cmap_target"] = list(c)
        self.cmap_target_var.set(hex_of(s["cmap_target"])[1:])
        if s != self.cmap_set:
            self.cmap_set = s
            self.s.update(s)
            self._cmap_target_swatch()
            self.recompute()

    def apply_cmap_settings(self, d):
        s = dict(self.cmap_set)
        s.update({k: v for k, v in d.items() if k.startswith("cmap_")})
        self.cmap_set = s
        self.cmap_method_var.set(s["cmap_method"])
        self.cmap_invul_var.set(s["cmap_invul"])
        self.cmap_smooth_var.set(bool(s["cmap_smooth"]))
        self.cmap_curve_var.set(fmt_tol(s["cmap_curve"]))
        self.cmap_target_var.set(hex_of(s["cmap_target"])[1:])
        self._cmap_target_swatch()

    def _cmap_target_swatch(self):
        self.cmap_target_sw.configure(background=hex_of(self.cmap_set["cmap_target"]))

    # ---------------------------------------------------------- history helpers
    def _cmap_commit(self, text):
        """Hand edits changed: new history entry (same palette)."""
        self.cm_changed()
        self._push_history("COLORMAP: %s" % text)
        self.status_var.set("COLORMAP: %s - recorded as #%d." % (text, self.hist_pos))
        self.recompute()

    def _sel_colours(self):
        return [i for i in sorted(self.selection)
                if self.rgbs is not None and self.rgbs[i] is not None]

    def _need_sel(self, n=1):
        sel = self._sel_colours()
        if len(sel) < n:
            self.status_var.set("Select %s in the palette grid first." % (
                "a colour" if n == 1 else "at least %d colours" % n))
            return None
        return sel

    # ---------------------------------------------------------- bulk edits
    def cmap_fullbright(self, on):
        sel = self._need_sel()
        if not sel:
            return
        before = set(self.cm.fullbright)
        if on:
            self.cm.fullbright |= set(sel)
        else:
            self.cm.fullbright -= set(sel)
        if self.cm.fullbright != before:
            self._cmap_commit("%s %d colour(s)" % ("full bright" if on else "normal", len(sel)))

    def cmap_clear(self):
        sel = self._need_sel()
        if not sel:
            return
        old = self.cm.copy()
        ss = set(sel)
        self.cm.overrides = {k: t for k, t in self.cm.overrides.items()
                             if not (k[1] in ss and k[0] < LIGHT_ROWS)}
        for s in sel:
            self.cm.limits.pop(s, None)
            self.cm.curves.pop(s, None)
        self.cm.fullbright -= ss
        if self.cm != old:
            self._cmap_commit("cleared hand edits on %d colour(s)" % len(sel))

    def cmap_fade_within(self):
        sel = self._need_sel(2)
        if not sel:
            return
        try:
            spl = min(max(float(self.fw_spl.get()), 0.01), 32.0)
        except ValueError:
            self.status_var.set("Steps per level must be a number.")
            return
        res, _f = self.cmap_result()
        dark = res.rows[DARK_ROW][0] if res else None
        ov = fade_within(self.rgbs, sel, spl, self.fw_order.get(), self.fw_end.get(), dark)
        ss = set(sel)
        self.cm.overrides = {k: t for k, t in self.cm.overrides.items()
                             if not (k[1] in ss and k[0] < LIGHT_ROWS)}
        self.cm.overrides.update(ov)
        self._cmap_commit("fade within %d selected (%s steps/level)" % (len(sel), fmt_tol(spl)))

    def cmap_store_targets(self):
        sel = self._need_sel()
        if not sel:
            return
        self.cmap_target_set = set(sel)
        self.cmap_tset_var.set("%d colour(s) stored" % len(sel))
        self.recompute()

    def cmap_limit(self, on):
        sel = self._need_sel()
        if not sel:
            return
        if on:
            if not self.cmap_target_set:
                self.status_var.set("Store a target set first (select colours, then "
                                    "'Store selection as targets').")
                return
            res, _f = self.cmap_result()
            allowed = set(self.cmap_target_set)
            if res is not None:
                allowed.add(res.rows[DARK_ROW][0])
            for s in sel:
                self.cm.limits[s] = frozenset(allowed | {s})
            self._cmap_commit("limited %d colour(s) to %d targets" % (len(sel), len(allowed)))
        else:
            n = sum(1 for s in sel if self.cm.limits.pop(s, None) is not None)
            if n:
                self._cmap_commit("removed target limit from %d colour(s)" % n)

    def cmap_curve(self, on):
        sel = self._need_sel()
        if not sel:
            return
        if on:
            try:
                v = min(max(float(self.cmap_scurve.get()), 0.25), 4.0)
            except ValueError:
                self.status_var.set("Fade curve must be a number.")
                return
            for s in sel:
                self.cm.curves[s] = v
            self._cmap_commit("fade curve %s on %d colour(s)" % (fmt_tol(v), len(sel)))
        else:
            n = sum(1 for s in sel if self.cm.curves.pop(s, None) is not None)
            if n:
                self._cmap_commit("cleared fade curve on %d colour(s)" % n)

    def cmap_copy_shape(self):
        sel = self._need_sel()
        if not sel:
            return
        res, _f = self.cmap_result()
        self._cmap_shape = fade_shape(self.rgbs, res, sel[0])
        self.paste_shape_btn.state(["!disabled"])
        self.status_var.set("Copied the fade shape of colour %d." % sel[0])

    def cmap_paste_shape(self):
        sel = self._need_sel()
        if not sel or not self._cmap_shape:
            return
        res, _f = self.cmap_result()
        for s in sel:
            ov = apply_shape(self.rgbs, res.matcher, self._cmap_shape, s)
            self.cm.overrides.update({k: t for k, t in ov.items() if t is not None})
        self._cmap_commit("pasted fade shape to %d colour(s)" % len(sel))

    # ---------------------------------------------------------- brush
    def set_brush(self, idx):
        if self.rgbs is None or idx is None or self.rgbs[idx] is None:
            return
        self.cmap_brush = idx
        self.brush_sw.configure(background=hex_of(self.rgbs[idx]))
        self.brush_var.set("index %d  %s" % (idx, hex_of(self.rgbs[idx])))
        self.redraw()

    def _on_grid_right(self, ev):
        """COLORMAP mode: right-click a palette cell = brush colour."""
        if not self.cmap_mode() or self.res is None:
            return
        slot = self._slot_at(ev.x, ev.y)
        ent = self._view_entry(slot) if slot is not None else None
        if ent and self.rgbs[ent[0]] is not None:
            self.set_brush(ent[0])
            self.cmap_tool.set("Paint")

    # ---------------------------------------------------------- fade view drawing
    def _fade_schedule(self):
        if not self.cmap_mode():
            return
        if self._fade_after is not None:
            self.root.after_cancel(self._fade_after)
        self._fade_after = self.root.after(15, self.draw_fades)

    def _fade_wheel(self, n):
        self._fade_scroll = max(0, self._fade_scroll + n)
        self.draw_fades()

    def _fade_geom(self, nrows):
        cv = self.fade_cv
        W, H = max(cv.winfo_width(), 100), max(cv.winfo_height(), 60)
        lw = int(64 * getattr(self, "ui", 1.0))
        cell = max(6.0, min(28.0 * getattr(self, "ui", 1.0),
                            (W - lw - 8) / float(self._fade_cols())))
        top = 16
        vis = max(1, int((H - top - 4) // cell))
        return W, H, lw, cell, top, vis

    def draw_fades(self):
        self._fade_after = None
        cv = self.fade_cv
        cv.delete("all")
        self._fade_cells = []
        if not self.cmap_mode() or self.rgbs is None:
            return
        if self._framp_backup is None:
            self._prune_strips()
        res, flags = self.cmap_result()
        self._update_diag(flags)
        if self.cmap_view.get() == "Matrix":
            self._draw_matrix(res, flags)
            return
        sel = self._sel_colours()
        W, H, lw, cell, top, vis = self._fade_geom(len(sel))
        if not sel:
            cv.create_text(12, 20, anchor="nw", fill="#bbbbbb",
                           text="Select colours in the palette grid to see and edit their "
                                "fades (rows 0-31 = light levels, 0 = full bright).\n"
                                "Right-click a palette cell to choose the brush; Paint / "
                                "Erase / Pick act on the cells here.\n"
                                "Ctrl + paint = same step for every selected colour.  "
                                "Matrix shows the whole COLORMAP.")
            return
        self._fade_scroll = min(self._fade_scroll, max(0, len(sel) - vis))
        ncol = self._fade_cols()
        every = 1 if cell >= 14 else 2 if cell >= 8 else 4     # keep numbers readable
        for c in range(ncol):
            if c % every and c != INVUL_ROW:
                continue
            cv.create_text(lw + c * cell + cell / 2, top / 2,
                           fill="#ffcc66" if c == INVUL_ROW else "#bbbbbb",
                           font=("Consolas", 8 if cell >= 16 else 7),
                           text="I" if c == INVUL_ROW else str(c))
        if ncol > LIGHT_ROWS:                     # separate the view-only I column
            xs = lw + LIGHT_ROWS * cell - 1
            cv.create_line(xs, top, xs, top + vis * cell, fill="#ffcc66")
        marks = self.cmap_markers.get()
        diag_on = self.cmap_diag_on.get() and marks
        self._fade_labels = []
        ramp_mode = self.cmap_tool.get() == "Ramp"
        for k, s in enumerate(sel[self._fade_scroll:self._fade_scroll + vis]):
            y = top + k * cell
            src = self.rgbs[s]
            self._fade_labels.append((y, cell, s, lw))
            cv.create_rectangle(2, y + 1, 2 + cell - 2, y + cell - 1, fill=hex_of(src),
                                outline="")
            lab = "%3d%s" % (s, " FB" if s in self.cm.fullbright else
                             " L" if s in self.cm.limits else "")
            cv.create_text(cell + 4, y + cell / 2, anchor="w", fill="#dddddd",
                           font=("Consolas", 8), text=lab)
            for r in range(ncol):
                x = lw + r * cell
                t = res.rows[r][s]
                col = self.rgbs[t] if self.rgbs[t] is not None else (0, 0, 0)
                cv.create_rectangle(x, y, x + cell - 1, y + cell - 1, fill=hex_of(col),
                                    outline="")
                how = res.source.get((r, s))
                fg = "#000000" if sum(col) > 380 else "#ffffff"
                if not marks or r >= LIGHT_ROWS:
                    pass
                elif how == "override":
                    q = cell * 0.35
                    cv.create_polygon(x, y, x + q, y, x, y + q, fill=fg, outline="")
                elif how == "bad":
                    cv.create_line(x + 2, y + 2, x + cell - 3, y + cell - 3, fill="#ff3030")
                if diag_on and (r, s) in flags:
                    cv.create_rectangle(x + 1, y + 1, x + cell - 2, y + cell - 2,
                                        outline=DIAG_TYPES[flags[(r, s)]][1], width=2)
                self._fade_cells.append((x, y, cell, r, s))
            if ramp_mode and s in self.fstrips:
                r0 = self.fstrips[s]
                if r0 > 0:                        # untouched rows dimmed
                    cv.create_rectangle(lw, y, lw + r0 * cell - 1, y + cell - 1,
                                        fill="#000000", stipple="gray50", outline="")
                col = "#ffcc33" if s == self.fref else "#00e5ff"
                cv.create_rectangle(lw + r0 * cell, y, lw + LIGHT_ROWS * cell - 1,
                                    y + cell - 1, outline=col, width=2)
                cv.create_rectangle(1, y, lw - 3, y + cell - 1, outline=col, width=2)
        if len(sel) > vis:
            cv.create_text(W - 4, H - 2, anchor="se", fill="#999999", font=("Consolas", 8),
                           text="colours %d-%d of %d (wheel scrolls)" % (
                               self._fade_scroll + 1, min(len(sel), self._fade_scroll + vis),
                               len(sel)))

    def _draw_matrix(self, res, flags):
        from PIL import Image, ImageDraw, ImageTk

        cv = self.fade_cv
        W, H = max(cv.winfo_width(), 100), max(cv.winfo_height(), 60)
        nrows = self._matrix_rows()
        img = Image.new("RGB", (ENTRIES, nrows))
        px = img.load()
        for r in range(nrows):
            row = res.rows[r]
            for s in range(ENTRIES):
                c = self.rgbs[row[s]] if self.rgbs[s] is not None else None
                px[s, r] = tuple(c) if c is not None else (38, 38, 38)
        BW, BH = max(ENTRIES, W - 8), max(nrows, H - 8)
        cw = BW / float(ENTRIES)
        ch = BH / float(nrows)
        big = img.resize((BW, BH), Image.NEAREST)
        dr = ImageDraw.Draw(big)
        marks = self.cmap_markers.get()
        diag_on = self.cmap_diag_on.get() and marks
        for (r, s), how in res.source.items():
            if marks and how in ("override", "bad") and r < min(nrows, LIGHT_ROWS):
                x, y = s * cw, r * ch
                col = (255, 255, 255) if how == "override" else (255, 48, 48)
                dr.rectangle([x, y, x + max(0.0, cw / 2 - 1), y + max(0.0, ch / 2 - 1)],
                             fill=col)
        if diag_on:
            for (r, s), f in flags.items():
                x, y = s * cw, r * ch
                dr.rectangle([x, y + ch - max(1.0, ch / 3), x + max(cw - 1, 0.5),
                              y + ch - 1], fill=DIAG_TYPES[f][1])
        self._matrix_img = ImageTk.PhotoImage(big)
        cv.create_image(4, 4, anchor="nw", image=self._matrix_img)
        self._matrix_geom = (4, 4, cw, ch)
        for s in self._sel_colours():
            x = 4 + s * cw
            cv.create_rectangle(x, 3, x + cw, 4 + BH, outline="#00ffff")

    def _fade_at(self, x, y):
        if self.cmap_view.get() == "Matrix":
            g = getattr(self, "_matrix_geom", None)
            if not g:
                return None
            ox, oy, cw, ch = g
            s = int((x - ox) // cw)
            r = int((y - oy) // ch)
            if 0 <= s < ENTRIES and 0 <= r < min(self._matrix_rows(), INVUL_ROW + 1) \
                    and self.rgbs[s] is not None:
                return r, s
            return None
        for cx, cy, cell, r, s in self._fade_cells:
            if cx <= x < cx + cell and cy <= y < cy + cell:
                return r, s
        return None

    def _fade_hover(self, ev):
        hit = self._fade_at(ev.x, ev.y)
        if hit is None or self.rgbs is None:
            self.info_var.set("")
            return
        r, s = hit
        res, flags = self.cmap_result()
        t = res.rows[r][s]
        how = res.source.get((r, s), "auto")
        txt = "colour %d %s  %s %s -> %d %s  (%s)" % (
            s, hex_of(self.rgbs[s]),
            "I (invulnerability, view-only)" if r == INVUL_ROW else "row %d" % r,
            "", t, hex_of(self.rgbs[t]) if self.rgbs[t] else "?",
            {"override": "hand-set", "bad": "hand-set target gone - auto",
             "bright": "full bright"}.get(how, "auto"))
        ideal = res.ideal.get((r, s))
        if ideal:
            txt += "  ideal %s" % hex_of(tuple(int(round(v)) for v in ideal))
        if (r, s) in flags:
            txt += "  ! " + DIAG_TYPES[flags[(r, s)]][0]
        self.info_var.set(txt)

    # ---------------------------------------------------------- fade view editing
    def _fade_press(self, ev):
        if self.cmap_tool.get() == "Ramp" and self.cmap_view.get() == "Fades":
            self._ramp_pick(ev)
            return
        hit = self._fade_at(ev.x, ev.y)
        if hit is None:
            return
        if hit[0] >= LIGHT_ROWS:
            self.status_var.set("The invulnerability row is view-only here - the COLORMAP "
                                "tools only edit light rows 0-31.")
            return
        tool = self.cmap_tool.get()
        if tool == "Pick":
            res, _f = self.cmap_result()
            self.set_brush(res.rows[hit[0]][hit[1]])
            return
        if tool == "Paint" and self.cmap_brush is None:
            self.status_var.set("Right-click a palette cell to choose the brush colour.")
            return
        self._fade_drag = {"before": self.cm.copy(), "done": set(),
                           "all": bool(ev.state & 0x0004)}
        self._fade_apply(hit)

    # ---------------------------------------------------------- Ramp tool strips
    def _ramp_pick(self, ev):
        """Ramp tool: index = whole strip, cell = from that row. Ctrl adds /
        removes, Shift on an index = range of whole strips."""
        if self._framp_backup is not None:
            self.status_var.set("Fade ramp preview is open - Apply or Cancel it first.")
            return
        ctrl, shift = ev.state & 0x0004, ev.state & 0x0001
        target = None
        for y, cell, s, lw in self._fade_labels:
            if y <= ev.y < y + cell and ev.x < lw:
                target = (s, 0, True)
        if target is None:
            hit = self._fade_at(ev.x, ev.y)
            if hit is None or hit[0] >= LIGHT_ROWS:
                return
            target = (hit[1], hit[0], False)
        s, r0, label = target
        if label and shift and self.fref is not None:
            sel = self._sel_colours()
            if self.fref in sel and s in sel:
                a, b = sorted((sel.index(self.fref), sel.index(s)))
                if not ctrl:
                    self.fstrips = {}
                for t in sel[a:b + 1]:
                    self.fstrips[t] = 0
        elif ctrl:
            if label and s in self.fstrips:
                del self.fstrips[s]
            else:
                self.fstrips[s] = r0
        else:
            self.fstrips = {s: r0}
        if s in self.fstrips:
            self.fref = s
        elif self.fref not in self.fstrips:
            self.fref = next(iter(self.fstrips), None)
        self.draw_fades()
        self.status_var.set("Ramp strips: " + ", ".join(
            "%d%s" % (t, "" if r == 0 else " from row %d" % r)
            for t, r in sorted(self.fstrips.items())) if self.fstrips else "No strips chosen.")
        if self.ramp is not None and getattr(self.ramp, "FADE", False):
            self.ramp.sync_reference()

    def _prune_strips(self):
        if not self.fstrips:
            return
        sel = set(self._sel_colours())
        self.fstrips = {s: r for s, r in self.fstrips.items() if s in sel}
        if self.fref not in self.fstrips:
            self.fref = next(iter(self.fstrips), None)

    def open_fade_ramp(self):
        from .fade_ramp import FadeRampTool

        if not self.cmap_mode():
            return
        self._prune_strips()
        if not self.fstrips:
            self.cmap_tool.set("Ramp")
            self.status_var.set("Ramp tool: click an index number (whole strip) or a cell "
                                "(from that row) in the fade view, then open the Ramp tool.")
            self.draw_fades()
            return
        if self.ramp is not None:
            if getattr(self.ramp, "FADE", False):
                self.ramp.win.deiconify()
                self.ramp.win.lift()
                self.ramp.sync_reference()
                return
            self.ramp.close()
        self.ramp = FadeRampTool(self)

    def cm_base(self):
        return self._framp_backup if self._framp_backup is not None else self.cm

    def framp_anchor(self, s):
        """Colour the fade continues from: the colour itself (start row 0) or
        what row start-1 shows now (before any preview)."""
        r0 = self.fstrips.get(s, 0)
        if r0 == 0:
            return tuple(self.rgbs[s])
        res, _f = self.cmap_result(base=True)
        return tuple(self.rgbs[res.rows[r0 - 1][s]])

    def framp_preview_start(self):
        if self._previewing():
            return self._framp_backup is not None
        if not self.fstrips:
            self.status_var.set("Choose strips first (Ramp tool in the fade view).")
            return False
        res, _f = self.cmap_result()
        self._framp_base = res
        self._framp_backup = self.cm.copy()
        self._refresh_history()
        return True

    def framp_preview_set(self, results):
        if self._framp_backup is None:
            return
        self.cm = self._framp_backup.copy()
        for s, rows in results.items():
            for row, _ideal, slot, _d in rows:
                if slot is not None:
                    self.cm.overrides[(row, s)] = slot
        self.cm_changed()
        self.status_var.set("Fade ramp preview on %d strip(s) - Apply keeps it, Cancel "
                            "restores." % len(results))
        self.recompute()

    def _framp_end(self):
        self._framp_backup = None
        self._framp_base = None
        if self.ramp is not None and getattr(self.ramp, "FADE", False):
            self.ramp.update_buttons()
        self._refresh_history()

    def framp_cancel(self):
        if self._framp_backup is None:
            return
        self.cm = self._framp_backup
        self.cm_changed()
        self._framp_end()
        self.status_var.set("Fade ramp cancelled.")
        self.recompute()

    def framp_apply(self):
        if self._framp_backup is None:
            return
        before = self._framp_backup
        n = len(self.fstrips)
        self._framp_end()
        if self.cm == before:
            self.status_var.set("Those fades already match the ramp - nothing changed.")
            self.recompute()
            return
        self._cmap_commit("ramp on %d strip%s" % (n, "" if n == 1 else "s"))

    def _fade_motion(self, ev):
        if self._fade_drag is None:
            return
        hit = self._fade_at(ev.x, ev.y)
        if hit is not None and hit[0] < LIGHT_ROWS:
            self._fade_apply(hit)

    def _fade_apply(self, hit):
        d = self._fade_drag
        r, s = hit
        cols = self._sel_colours() if d["all"] and self.cmap_view.get() == "Fades" else [s]
        for src in cols:
            if (r, src) in d["done"]:
                continue
            d["done"].add((r, src))
            if self.cmap_tool.get() == "Paint":
                self.cm.overrides[(r, src)] = self.cmap_brush
            else:
                self.cm.overrides.pop((r, src), None)
        # quick visual update without regenerating
        if self.cmap_view.get() == "Fades":
            for cx, cy, cell, rr, ss in self._fade_cells:
                if rr == r and ss in cols:
                    c = (self.rgbs[self.cmap_brush] if self.cmap_tool.get() == "Paint"
                         else (60, 60, 60))
                    self.fade_cv.create_rectangle(cx, cy, cx + cell - 1, cy + cell - 1,
                                                  fill=hex_of(c), outline="#ffffff")

    def _fade_release(self, _ev):
        d = self._fade_drag
        self._fade_drag = None
        if d is None:
            return
        if self.cm != d["before"]:
            n = len(d["done"])
            self._cmap_commit("%s %d cell%s" % (
                "painted" if self.cmap_tool.get() == "Paint" else "erased", n,
                "" if n == 1 else "s"))
        else:
            self.draw_fades()

    # ---------------------------------------------------------- diagnostics list
    def _update_diag(self, flags):
        counts = {k: 0 for k in DIAG_TYPES}
        per = {}
        for (r, s), f in flags.items():
            counts[f] += 1
            per.setdefault(s, []).append(f)
        for k, (v, label) in self.diag_vars.items():
            v.set("%s: %d" % (label, counts[k]))
        worst = sorted(per.items(), key=lambda kv: -len(kv[1]))[:60]
        rows = []
        for s, fl in worst:
            parts = ", ".join("%d %s" % (fl.count(k), DIAG_TYPES[k][0].lower())
                              for k in DIAG_TYPES if k in fl)
            rows.append(("%3d %s  %s" % (s, hex_of(self.rgbs[s]), parts), s))
        if [r[0] for r in rows] != [r[0] for r in self._diag_rows]:
            self.diag_list.delete(0, "end")
            for txt, _s in rows:
                self.diag_list.insert("end", txt)
            self._diag_rows = rows
        free = sum(1 for c in self.rgbs if c is None)
        self.cf_free_var.set("Free (empty) slots: %d" % free)

    def _on_diag_pick(self, _ev):
        sel = self.diag_list.curselection()
        if not sel or sel[0] >= len(self._diag_rows):
            return
        s = self._diag_rows[sel[0]][1]
        self.selection = {s}
        self.cmap_view.set("Fades")
        self._fade_scroll = 0
        self.recompute()

    # ---------------------------------------------------------- create fade colours
    def _usage_weights(self):
        p = getattr(self, "preview", None)
        if p is None or not hasattr(p, "usage_counts"):
            return None
        counts = p.usage_counts()
        if not counts:
            return None
        first = {}
        for i, c in enumerate(self.rgbs):
            if c is not None:
                first.setdefault(tuple(c), i)
        out = {}
        for c, n in counts.items():
            i = first.get(tuple(c))
            if i is not None:
                out[i] = out.get(i, 0) + n
        return out

    def cmap_find_colours(self):
        if self.rgbs is None:
            return
        try:
            budget = max(1, min(128, int(float(self.cf_budget.get()))))
        except ValueError:
            self.status_var.set("Budget must be a number.")
            return
        scope = self._sel_colours() if self.cf_scope.get() == "selected" else \
            [i for i, c in enumerate(self.rgbs) if c is not None]
        if not scope:
            self.status_var.set("Select colours first (or choose Whole palette).")
            return
        res, _f = self.cmap_result()
        weights = self._usage_weights()
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            props, before, after = propose_fade_colours(self.rgbs, res, scope, self.cm,
                                                        budget, weights)
        finally:
            self.root.configure(cursor="")
        if not props:
            self.status_var.set("No useful fade colours to add - the fades already land "
                                "close to their ideal colours.")
            return
        FadeProposals(self, props, before, after, weights is not None)

    def add_fade_colours(self, cols):
        free = [i for i, c in enumerate(self.rgbs) if c is None]
        if len(free) < len(cols):
            from tkinter import messagebox
            messagebox.showwarning(
                "cleanpal", "Only %d empty slot(s) free for %d colour(s).\n\nCull colours "
                            "and take a snapshot (empty slots appear at the end with Align), "
                            "or untick some proposals." % (len(free), len(cols)))
            return False
        slots = free[:len(cols)]
        new = list(self.rgbs)
        for i, c in zip(slots, cols):
            new[i] = tuple(c)
        self.rgbs = new
        self.labs, self.pairs = update_pairs(new, self.labs, self.pairs, slots)
        self.cm.invalidate(slots)
        self.cm_changed()
        self._push_history("Create fade colours (%d) - %d colours"
                           % (len(cols), sum(1 for e in self.rgbs if e is not None)))
        self.status_var.set("Added %d fade colour(s) at %s - recorded as #%d." % (
            len(cols), ", ".join(str(i) for i in slots[:8]) + ("..." if len(slots) > 8
                                                               else ""), self.hist_pos))
        self.recompute()
        return True

    # ---------------------------------------------------------- files
    def _loaded_from_wad(self, path, rgbs):
        try:
            raw = read_wad_lump(path, "COLORMAP")
            if raw is None:
                return None
            return {"rows": rows_from_bytes(raw), "pal": list(rgbs),
                    "name": "%s COLORMAP" % os.path.basename(path)}
        except (OSError, ValueError):
            return None

    def _cmap_status_text(self):
        if self.cmap_loaded:
            self.cmap_status.set("Loaded for compare / import: %s.\nThe working COLORMAP is "
                                 "generated from the palette plus your hand edits."
                                 % self.cmap_loaded["name"])
            self.cmap_import_btn.state(["!disabled"])
        else:
            self.cmap_status.set("Generated from the palette plus your hand edits "
                                 "(no COLORMAP loaded).")
            self.cmap_import_btn.state(["disabled"])

    def cmap_open(self):
        from tkinter import filedialog, messagebox

        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return
        p = filedialog.askopenfilename(
            title="Open COLORMAP", initialdir=self.s.get("last_dir") or None,
            filetypes=[("COLORMAP sources", "*.wad *.lmp *.png *.raw *.cmp"),
                       ("WAD", "*.wad"), ("Raw lump", "*.lmp *.raw *.cmp"),
                       ("COLORMAP image", "*.png"), ("All files", "*.*")])
        if not p:
            return
        try:
            rows = load_colormap(p, self.rgbs)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not open COLORMAP:\n%s\n\n%s" % (p, e))
            return
        self.cmap_loaded = {"rows": rows, "pal": list(self.rgbs),
                            "name": os.path.basename(p)}
        self._cmap_status_text()
        self.status_var.set("Loaded COLORMAP %s (%d rows) - its indices are read against "
                            "the current palette." % (os.path.basename(p), len(rows)))
        self.recompute()

    def cmap_import(self):
        if not self.cmap_loaded or self.rgbs is None:
            return
        res, _f = self.cmap_result()
        ov = import_overrides(self.rgbs, res, self.cmap_loaded)
        if not ov:
            self.status_var.set("The loaded COLORMAP already matches the generated one.")
            return
        self.cm.overrides.update(ov)
        self._cmap_commit("imported %d hand-set cells from %s" % (len(ov),
                                                                  self.cmap_loaded["name"]))

    def export_mapping(self):
        """(entries, mapping old->new, owner) for what an export writes now."""
        r = self.res
        align = self._align_on()
        entries = [None] * ENTRIES
        mapping = {}
        if align:
            for new, old in enumerate(r["kept"]):
                mapping[old] = new
        else:
            for i in r["kept"]:
                mapping[i] = i
        for old, new in mapping.items():
            entries[new] = self.rgbs[old]
        owner = {i: r["owner"][i] for i in range(ENTRIES)
                 if r["status"][i] in ("exact", "similar")}
        return entries, mapping, owner

    def export_colormap_rows(self):
        entries, mapping, owner = self.export_mapping()
        cm2 = self.cm.copy()
        cm2.remap(mapping, owner)
        res = generate(entries, set(), self.cmap_set, cm2, self.cmap_loaded)
        return entries, res.rows

    def cmap_export(self):
        from tkinter import filedialog, messagebox

        if self.res is None:
            self.status_var.set("Open a palette first.")
            return
        label = self.cmap_export_var.get()
        ext = dict(CMAP_EXPORTS)[label]
        stem = os.path.splitext(os.path.basename(self.src_path or "palette"))[0]
        p = filedialog.asksaveasfilename(
            title="Export COLORMAP", initialdir=self.s.get("last_dir") or None,
            initialfile="%s-COLORMAP%s" % (stem, ext), defaultextension=ext,
            filetypes=[(label, "*" + ext)])
        if not p:
            return
        try:
            entries, rows = self.export_colormap_rows()
            write_colormap(p, rows, entries)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "COLORMAP export failed:\n%s" % e)
            return
        self.s["last_dir"] = os.path.dirname(p)
        self.exported = True
        self.status_var.set("Wrote %s (for the current palette)." % p)

    # ---------------------------------------------------------- preview lighting
    def light_palette(self, row, cols, compare=False):
        """Lit colours for a list of preview colours at COLORMAP row `row`."""
        if compare and self.cmap_loaded:
            pal = self.cmap_loaded["pal"]
            rows = self.cmap_loaded["rows"]
        else:
            res, _f = self.cmap_result()
            if res is None:
                return list(cols)
            pal = self.rgbs
            rows = res.rows
        if row >= len(rows):
            return list(cols)
        first = {}
        for i, c in enumerate(pal):
            if c is not None:
                first.setdefault(tuple(c), i)
        out = []
        for c in cols:
            i = first.get(tuple(c))
            if i is None:
                out.append(tuple(c))
                continue
            t = rows[row][i]
            tc = pal[t] if 0 <= t < len(pal) else None
            out.append(tuple(tc) if tc is not None else (0, 0, 0))
        return out

    def compare_palette(self):
        if not self.cmap_loaded:
            return None
        return list(dict.fromkeys(tuple(c) for c in self.cmap_loaded["pal"] if c is not None))


# ============================================================ proposals window
class FadeProposals:
    """Ghost swatches for 'Create fade colours': tick / untick, then accept."""

    def __init__(self, app, props, before, after, weighted):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        self.props = props
        self.win = tk.Toplevel(app.root)
        self.win.title("Create fade colours")
        self.win.transient(app.root)
        self.win.minsize(460, 300)
        pct = 100.0 * (before - after) / before if before else 0.0
        ttk.Label(self.win, padding=(10, 10, 10, 4), wraplength=520, text=(
            "Fade error (weighted%s): %.1f -> %.1f  (-%.0f%%) with all %d.\n"
            "Untick any you don't want; accepted colours go into empty slots and the "
            "COLORMAP immediately starts using them." % (
                " by pixel use in the preview" if weighted else "", before, after, pct,
                len(props)))).pack(anchor="w")
        frame = ttk.Frame(self.win, padding=(10, 0, 10, 0))
        frame.pack(fill="both", expand=True)
        cv = tk.Canvas(frame, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=cv.yview)
        inner = ttk.Frame(cv)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window(0, 0, window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.vars = []
        for k, p in enumerate(props):
            v = tk.BooleanVar(value=True)
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=1)
            ttk.Checkbutton(row, variable=v, command=self._count).pack(side="left")
            sw = tk.Canvas(row, width=40, height=20, highlightthickness=1,
                           highlightbackground="#888", background=hex_of(p["rgb"]))
            sw.pack(side="left", padx=(2, 6))
            ttk.Label(row, font=("Consolas", 9), text="%s  serves %d colour%s, rows %d-%d" % (
                hex_of(p["rgb"]), p["serves"], "" if p["serves"] == 1 else "s",
                p["rows"][0], p["rows"][1])).pack(side="left")
            self.vars.append(v)
        bf = ttk.Frame(self.win, padding=10)
        bf.pack(fill="x")
        self.count_var = tk.StringVar()
        ttk.Label(bf, textvariable=self.count_var).pack(side="left")
        ttk.Button(bf, text="Cancel", command=self.win.destroy).pack(side="right")
        ttk.Button(bf, text="Add to palette", command=self.accept).pack(side="right",
                                                                         padx=(0, 6))
        self._count()

    def _count(self):
        n = sum(1 for v in self.vars if v.get())
        free = sum(1 for c in self.app.rgbs if c is None)
        self.count_var.set("%d selected, %d empty slot(s) free" % (n, free))

    def accept(self):
        cols = [p["rgb"] for p, v in zip(self.props, self.vars) if v.get()]
        if not cols:
            self.win.destroy()
            return
        if self.app.add_fade_colours(cols):
            self.win.destroy()
