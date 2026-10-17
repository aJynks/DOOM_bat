"""Main window: grid, selection, history, matching and export."""

import math
import os

from .colormap_mode import MODES, CmapMixin
from ..colormap import CmapState
from ..analysis import analyse, build_pairs, result_entries
from ..colour import metric_dist
from ..constants import (
    DEFAULT_TOL, ENTRIES, EXPORTS, EXPORT_LABELS, GREEN, METRICS, METRIC_HOVER,
    METRIC_LABEL, METRIC_TOKEN, TOL_RANGE, VERSION, fmt_tol,
)
from ..palette_io import load_palette, write_analysis, write_export
from ..settings import PROJECT_EXT, load_settings, save_settings
from .app_project import ProjectMixin
from .app_sort import SortMixin
from .app_tools import ToolsMixin
from .tool_windows import TOOL_NAME, ToolHostMixin
from .help import HELP_TEXT
from .preview import PreviewWindow
from .widgets import MenusMixin


class App(ToolHostMixin, SortMixin, MenusMixin, ToolsMixin, ProjectMixin, CmapMixin):
    CELL = 30          # world units per cell
    GAP = 2            # world units between cells
    PAD = 10           # screen px margin when fitting
    ZOOM_MIN = 0.25    # relative to fit scale
    ZOOM_MAX = 16.0
    ZOOM_STEP = 1.2
    MARKER_MIN_PX = 10

    def __init__(self, root, path=None):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.s = load_settings()

        self._cmap_init()
        self.rgbs = None
        self.labs = None
        self.pairs = {m: [] for m in METRICS}
        self.res = None
        self.src_path = None
        self.preset_name = None
        self.hover_slot = None
        self.selection = set()
        self.deleted = set()
        self.preview = None
        self._move_undo = []
        self._move_start = None
        self.tool = None              # open PLAYPAL tool: cull / move / reorder / paint
        self.tool_win = None
        self._tool_floor = 0          # history entry the tool session started on
        self.tool_btns = {}
        self.sim_chk = None           # Cull tools widgets (None while closed)
        self.metric_rbs = []
        self.scale = None
        self.tol_spin = None
        self.scope_rbs = []
        self.align_chk = None
        self.history = []
        self.hist_pos = 0
        self.exported = True
        self._drag = None
        self._scale_lock = False
        self.view_scale = 1.0
        self.off_x = 0.0
        self.off_y = 0.0
        self.auto_fit = True
        self._pan_start = None

        self.exact_var = tk.BooleanVar(value=bool(self.s["exact"]))
        self.similar_var = tk.BooleanVar(value=bool(self.s["similar"]))
        self.metric_var = tk.StringVar(value=self.s["metric"])
        self.align_var = tk.BooleanVar(value=bool(self.s["align"]))
        self.split_var = tk.BooleanVar(value=bool(self.s["split"]))
        self.export_var = tk.StringVar(value=self.s["export"])
        self.scope_var = tk.StringVar(value="all")
        self.move_var = tk.BooleanVar(value=False)     # Move tools open
        self.move_swap_var = tk.BooleanVar(value=False)
        self.paint_hide_var = tk.BooleanVar(value=bool(self.s.get("paint_hide_sel", False)))
        self._paint_start = None      # Paint: state at the last snapshot / opening
        self._paint_ramps = 0         # Paint: edits since then
        self._paint_fills = 0
        self._paint_filters = 0
        self._paint_cells = set()
        self._sel_before_click = set()
        self._filt_backup = None      # Paint filter preview
        self.filter_win = None
        self.clip = []                # copied colours (Ctrl+C / Ctrl+X)
        self._clip_sys = None         # text we last put on the system clipboard
        self.range_var = tk.StringVar()
        self.tol = {m: float(self.s.get("tol_" + m, DEFAULT_TOL[m])) for m in METRICS}
        self.tol_text = tk.StringVar()
        self._text_lock = False
        self.sort_method_var = tk.StringVar(value=self.s["sort_method"])
        self.sort_scope_var = tk.StringVar(value="all")
        self.sort_key_var = tk.StringVar(value=self.s["sort_key"])
        self.sort_high_var = tk.BooleanVar(value=bool(self.s["sort_high"]))
        self.sort_order_var = tk.StringVar(value=self.s["sort_ramp_order"])
        self.sort_outlier_var = tk.StringVar(value=self.s["sort_outliers"])
        self.sort_min_text = tk.StringVar(value=str(self.s["sort_min"]))
        self.sort_min = int(self.s["sort_min"])
        self.sort_params = self.s["sort_params"]
        self._sort_backup = None      # state before the sort preview
        self._sort_block = set()      # indices placed by the sort (preview outline)
        self._sort_nramps = 0
        self._sort_after = None
        self._sort_param_vars = {}
        self.reorder = None           # ReorderDialog (when the Reorder tools are open)
        self.sort_opt_frame = None    # reorder window widgets (None while closed)
        self.sort_prev_btn = None
        self.sort_cancel_btn = None
        self.sort_shared = {}
        self.ramp = None              # RampTool window
        self.picker = None            # ColourPicker window
        self.scratch = None           # ScratchPalette window
        self._ramp_backup = None      # state before the ramp preview
        self._ramp_targets = []
        self.project_path = None
        self.file_var = tk.StringVar(value="No palette loaded")
        self.stats_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self._build_ui()
        if self.s.get("geometry"):
            try:
                root.geometry(self.s["geometry"])
            except tk.TclError:
                pass
        if self.s.get("zoomed") and os.name == "nt":
            try:
                root.state("zoomed")
            except tk.TclError:
                pass
        self._sync_tol_widgets()
        self._update_states()
        self._update_sort_btn()
        self._refresh_history()
        self._refresh_tools()
        self.recompute()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if path:
            self.src_path = os.path.abspath(path)   # lets the IWAD guess look beside it
        self._startup_iwad()
        if path:
            self.load(path)

    def _build_ui(self):
        tk = self.tk
        from tkinter import ttk

        self.root.title("cleanpal v%s" % VERSION)
        self.root.resizable(True, True)
        self._colour_ctx = {}
        for cls in ("TEntry", "TSpinbox", "Entry", "Spinbox"):
            self.root.bind_class(cls, "<Button-3>", self._entry_menu, add="+")
            self.root.bind_class(cls, "<Control-a>", self._entry_select_all)
            self.root.bind_class(cls, "<Control-A>", self._entry_select_all)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        try:
            self.ui = max(1.0, self.root.winfo_fpixels("1i") / 96.0)  # monitor scale
        except tk.TclError:
            self.ui = 1.0

        top = ttk.Frame(self.root, padding=(8, 8, 8, 0))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(top, text="Open...", command=self.open_dialog).pack(side="left")
        ttk.Button(top, text="Load project...",
                   command=self.load_project_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Save project",
                   command=self.save_project).pack(side="left", padx=(4, 0))
        ttk.Button(top, text="Save project as...",
                   command=lambda: self.save_project(ask=True)).pack(side="left", padx=(4, 0))
        ttk.Label(top, text="Mode").pack(side="left", padx=(14, 4))
        mcb = ttk.Combobox(top, textvariable=self.mode_var, values=MODES, state="readonly",
                           width=10)
        mcb.pack(side="left")
        mcb.bind("<<ComboboxSelected>>", lambda e: self.set_mode())
        ttk.Button(top, text="Palettised preview...",
                   command=self.open_preview).pack(side="right")
        self.iwad_btn = ttk.Button(top, text="IWAD: not set!", command=self.choose_iwad)
        self.iwad_btn.pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Scratch palette...",
                   command=self.open_scratch).pack(side="right", padx=(0, 6))
        ttk.Label(top, textvariable=self.file_var).pack(side="left", padx=8)

        size = self.PAD * 2 + self._grid_world()
        # palette grid on top, COLORMAP fade view below (COLORMAP mode only),
        # split by a draggable sash
        self.main_pane = tk.PanedWindow(self.root, orient="vertical", sashwidth=8,
                                        sashrelief="raised", bd=0, opaqueresize=True,
                                        showhandle=False)
        self.main_pane.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        self.grid_pane = ttk.Frame(self.main_pane)
        self.grid_pane.columnconfigure(0, weight=1)
        self.grid_pane.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.grid_pane, width=size, height=size, bg="#262626",
                                highlightthickness=3, highlightbackground="#262626",
                                highlightcolor="#262626")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.main_pane.add(self.grid_pane, stretch="always", minsize=0)
        self._build_fade_frame(self.main_pane)
        self.main_pane.bind("<ButtonRelease-1>", lambda e: self._sash_dragged(), add="+")
        cv = self.canvas
        cv.bind("<Motion>", self._on_motion)
        cv.bind("<Leave>", self._on_leave)
        cv.bind("<Configure>", self._on_canvas_resize)
        cv.bind("<MouseWheel>", self._on_wheel)                       # Windows / macOS
        cv.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, self.ZOOM_STEP))  # X11
        cv.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / self.ZOOM_STEP))
        cv.bind("<ButtonPress-2>", self._on_pan_start)
        cv.bind("<B2-Motion>", self._on_pan_move)
        cv.bind("<ButtonRelease-2>", self._on_pan_end)
        cv.bind("<Double-Button-2>", lambda e: self.fit_view())
        cv.bind("<ButtonPress-1>", self._on_b1_press)
        cv.bind("<B1-Motion>", self._on_b1_move)
        cv.bind("<ButtonRelease-1>", self._on_b1_release)
        cv.bind("<Double-Button-1>", self._on_b1_double)
        cv.bind("<ButtonPress-3>", self._on_grid_right)
        self.root.bind("<Escape>", lambda e: self.clear_selection())
        self.root.bind("<Control-z>", self._on_undo_key)
        self.root.bind("<Control-Z>", self._on_undo_key)
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<BackSpace>", self._on_delete_key)
        self.root.bind("<Control-a>", self._on_select_all)
        self.root.bind("<Control-A>", self._on_select_all)
        self.root.bind("<Key-m>", self._on_move_key)
        self.root.bind("<Key-M>", self._on_move_key)
        self._bind_clip_keys(self.root)
        # clicks on the grid / buttons / panel give the keys back to the grid
        from .tool_windows import focus_on_click
        focus_on_click(self.root, self.canvas)
        self.root.bind("<Key-f>", self._on_fit_key)
        self.root.bind("<Key-F>", self._on_fit_key)

        # side panel lives in a scrollable canvas so it fits small screens
        wrap = ttk.Frame(self.root)
        wrap.grid(row=1, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        bg = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        self.side_cv = tk.Canvas(wrap, highlightthickness=0, bg=bg, yscrollincrement=20)
        self.side_cv.grid(row=0, column=0, sticky="ns")
        self.side_sb = ttk.Scrollbar(wrap, orient="vertical", command=self.side_cv.yview)
        self.side_cv.configure(yscrollcommand=self.side_sb.set)
        side = ttk.Frame(self.side_cv, padding=(0, 8, 8, 8))
        self.side_cv.create_window(0, 0, window=side, anchor="nw")
        self.side = side
        side.bind("<Configure>", lambda e: self._side_layout())
        self.side_cv.bind("<Configure>", lambda e: self._side_layout())

        # tools (PLAYPAL) - Cull / Move / Reorder / Paint windows
        tf = self._build_tools_panel(side)
        clf = self._build_clip_panel(side)

        # view
        vf = ttk.LabelFrame(side, text="View", padding=8)
        vf.pack(fill="x", pady=(8, 0))
        ttk.Label(vf, text="wheel = zoom   middle drag = pan   F = fit\n"
                           "checker = empty slot",
                  foreground="#666").pack(anchor="w")
        ttk.Button(vf, text="Fit", command=self.fit_view).pack(anchor="e", pady=(6, 0))

        # selection + history (both modes)
        sf = ttk.LabelFrame(side, text="Selection & history", padding=8)
        sf.pack(fill="x", pady=(8, 0))
        ttk.Label(sf, text="click / drag = select   shift = add   ctrl = toggle\n"
                           "Ctrl+A = all   Esc = clear   Ctrl+Z = back",
                  foreground="#666").pack(anchor="w")
        sbf = ttk.Frame(sf)
        sbf.pack(fill="x", pady=(6, 0))
        self.back_btn = ttk.Button(sbf, text="Back", command=self.step_back)
        self.back_btn.pack(side="left")
        self.remove_btn = ttk.Button(sbf, text="Remove", command=self.remove_snapshot)
        self.remove_btn.pack(side="left", padx=(6, 0))
        self.collapse_btn = ttk.Button(sbf, text="Collapse", command=self.collapse_history)
        self.collapse_btn.pack(side="left", padx=(6, 0))
        ttk.Button(sbf, text="Clear selection",
                   command=self.clear_selection).pack(side="right")
        lf = ttk.Frame(sf)
        lf.pack(fill="x", pady=(6, 0))
        self.hist_list = tk.Listbox(lf, height=6, activestyle="none",
                                    exportselection=False, font=("Consolas", 9))
        hsb = ttk.Scrollbar(lf, orient="vertical", command=self.hist_list.yview)
        self.hist_list.configure(yscrollcommand=hsb.set)
        self.hist_list.pack(side="left", fill="x", expand=True)
        hsb.pack(side="right", fill="y")
        self.hist_list.bind("<<ListboxSelect>>", self._on_hist_select)

        # export
        ef = ttk.LabelFrame(side, text="Export", padding=8)
        ef.pack(fill="x", pady=(8, 0))
        ttk.Combobox(ef, textvariable=self.export_var, values=EXPORT_LABELS,
                     state="readonly", width=40).pack(fill="x")
        ttk.Checkbutton(ef, text="Split per set / cluster (analysis PNGs)",
                        variable=self.split_var).pack(anchor="w", pady=(6, 0))
        ttk.Label(ef, text="Writes what the grid shows: culled (with Align)\n"
                           "while the Cull tools are open, else the palette as is.",
                  foreground="#666").pack(anchor="w", pady=(6, 0))
        ttk.Button(ef, text="Export...", command=self.do_export).pack(anchor="e", pady=(6, 0))

        bf = ttk.Frame(side)
        bf.pack(fill="x", pady=(8, 0))
        self.snap_frame = sf
        self.btn_frame = bf
        self._pp_frames_before = [tf, clf, vf]
        self._pp_frames_after = [ef]
        self._pp_frames = self._pp_frames_before + self._pp_frames_after
        self._build_cmap_panel(side)
        ttk.Button(bf, text="Help", command=self.show_help).pack(side="right")
        ttk.Button(bf, text="Load preset...", command=self.load_preset).pack(side="left")
        ttk.Button(bf, text="Save preset...",
                   command=self.save_preset).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(bottom, textvariable=self.stats_var,
                  font=("Consolas", 10, "bold")).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.info_var,
                  font=("Consolas", 10)).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.status_var,
                  foreground="#2a6").pack(anchor="w")

        # wheel over the panel scrolls it (sliders / spinbox / lists keep theirs)
        def bind_tree(w):
            if w.winfo_class() not in ("Scale", "TSpinbox", "Spinbox", "TCombobox",
                                       "Listbox", "TScrollbar"):
                w.bind("<MouseWheel>", self._side_wheel, add="+")
                w.bind("<Button-4>", lambda e: self._side_scroll(-1), add="+")
                w.bind("<Button-5>", lambda e: self._side_scroll(1), add="+")
            for ch in w.winfo_children():
                bind_tree(ch)
        bind_tree(side)
        self.side_cv.bind("<MouseWheel>", self._side_wheel)

        # minimum size: panel width + a usable preview; height no longer
        # depends on the panel (it scrolls)
        self.root.update_idletasks()
        self._side_layout()
        min_w = side.winfo_reqwidth() + 30 + 260
        min_h = top.winfo_reqheight() + bottom.winfo_reqheight() + 320
        self.root.minsize(min_w, min_h)

    def _permute(self, perm):
        """Reorder the working palette: perm[new_slot] = old_slot. Deleted
        marks and the selection follow their colours."""
        newpos = [0] * ENTRIES
        for new, old in enumerate(perm):
            newpos[old] = new
        self.rgbs = [self.rgbs[o] for o in perm]
        self.labs = [self.labs[o] for o in perm]
        self.pairs = {m: [(d, newpos[a], newpos[b]) for d, a, b in v]
                      for m, v in self.pairs.items()}
        self.deleted = {newpos[i] for i in self.deleted}
        self.selection = {newpos[i] for i in self.selection}
        self.cm.permute(newpos)
        self.cm_changed()
        if self.cmap_brush is not None:
            self.cmap_brush = newpos[self.cmap_brush]
        return newpos

    def _busy(self, on):
        try:
            self.root.configure(cursor="watch" if on else "")
            self.canvas.configure(cursor="watch" if on else "")
            if on:
                self.root.update_idletasks()
        except self.tk.TclError:
            pass

    def _previewing(self):
        return (self._sort_backup is not None or self._ramp_backup is not None
                or self._framp_backup is not None or self._filt_backup is not None)

    def _preview_busy_msg(self, allow_filter=False):
        """True (with a status message) while a preview is open. allow_filter:
        a filter preview doesn't block (selection changes re-run it)."""
        if self._filt_backup is not None and not allow_filter:
            self.status_var.set("Filter preview is open - Apply or Cancel it first.")
            return True
        if self._sort_backup is not None:
            self.status_var.set("Reorder preview is open - Apply or Cancel it first.")
            return True
        if self._ramp_backup is not None:
            self.status_var.set("Ramp preview is open - Apply or Cancel it first.")
            return True
        if self._framp_backup is not None:
            self.status_var.set("Fade ramp preview is open - Apply or Cancel it first.")
            return True
        return False

    def _update_states(self, clear=True):
        exact = self.exact_var.get()
        if not exact:
            self.similar_var.set(False)
            if clear:
                self.selection.clear()  # selecting needs exact removal
        if not self._cull_ui():
            return
        self.sim_chk.state(["!disabled"] if exact else ["disabled"])
        sim_on = exact and self.similar_var.get()
        for w in self.metric_rbs + [self.tol_spin] + self.scope_rbs:
            w.state(["!disabled"] if sim_on else ["disabled"])
        self.scale.configure(state="normal" if sim_on else "disabled")

    def _cancel_previews(self):
        if self._sort_backup is not None:
            self.sort_cancel()
        if self._ramp_backup is not None:
            self.ramp_cancel()
        if self._framp_backup is not None:
            self.framp_cancel()
        if self._filt_backup is not None:
            self.filter_cancel()

    def _scale_value(self, t):
        hi, res = TOL_RANGE[self.metric_var.get()]
        return round(min(max(t, 0.0), hi) / res) * res

    def _set_tol_text(self, v):
        self._text_lock = True
        self.tol_text.set(fmt_tol(v))
        self._text_lock = False

    def _sync_scale(self):
        if not self._cull_ui():
            return
        m = self.metric_var.get()
        hi, res = TOL_RANGE[m]
        self._scale_lock = True
        state = str(self.scale.cget("state"))
        self.scale.configure(state="normal", from_=0, to=hi, resolution=res)
        self.scale.set(self._scale_value(self.tol[m]))
        self.scale.configure(state=state)
        # Scale fires its command at idle time; release the lock after that
        self.root.after_idle(self._release_scale_lock)

    def _sync_tol_widgets(self):
        m = self.metric_var.get()
        hi, res = TOL_RANGE[m]
        self.range_var.set("0 - %s   (default %s)" % (fmt_tol(hi), fmt_tol(DEFAULT_TOL[m])))
        if self._cull_ui():
            self.tol_spin.configure(increment=res)
        self._sync_scale()
        self._set_tol_text(self.tol[m])

    def _on_scale_click(self, ev):
        """Click on the bar: jump the handle there, then let Tk start the drag."""
        if not self._cull_ui() or str(self.scale.cget("state")) == "disabled":
            return "break"
        if self.scale.identify(ev.x, ev.y) in ("trough1", "trough2"):
            v = float(self.scale.tk.call(self.scale._w, "get", ev.x, ev.y))
            self.scale.set(v)  # handle is now under the cursor

    def _release_scale_lock(self):
        self._scale_lock = False

    def _on_scale(self, val):
        if self._scale_lock:
            return
        m = self.metric_var.get()
        v = float(val)
        _, res = TOL_RANGE[m]
        if abs(v - self._scale_value(self.tol[m])) < res / 2:
            return  # programmatic set or no change
        self.tol[m] = v
        self._set_tol_text(v)
        self.recompute()

    def _apply_tol(self, v, update_text):
        m = self.metric_var.get()
        v = max(0.0, v)
        if abs(v - self.tol[m]) < 1e-12:
            if update_text:
                self._set_tol_text(v)
            return
        self.tol[m] = v
        self._sync_scale()
        if update_text:
            self._set_tol_text(v)
        self.recompute()

    def _on_tol_typed(self, *_):
        """Live: apply whenever the box holds a valid number."""
        if self._text_lock:
            return
        try:
            v = float(self.tol_text.get())
        except ValueError:
            return  # partial input like "" or "1." - wait for more
        if v < 0 or v != v:
            return
        self._apply_tol(v, update_text=False)

    def _on_tol_commit(self, *_):
        """Enter / focus out: tidy the box to the value actually in use."""
        self._set_tol_text(self.tol[self.metric_var.get()])

    def _step_tol(self, n):
        if not self._cull_ui() or self.tol_spin.instate(["disabled"]):
            return "break"
        m = self.metric_var.get()
        _, res = TOL_RANGE[m]
        v = round((self.tol[m] + n * res) / res) * res
        self._apply_tol(round(v, 6), update_text=True)
        return "break"

    def _on_spin_arrow(self):
        """Spinbox arrow buttons: snap to the step grid and apply."""
        m = self.metric_var.get()
        _, res = TOL_RANGE[m]
        try:
            v = float(self.tol_text.get())
        except ValueError:
            v = self.tol[m]
        self._apply_tol(round(round(v / res) * res, 6), update_text=True)

    def _on_metric(self):
        self._sync_tol_widgets()
        self.recompute()

    def _on_toggle(self):
        self._update_states()
        self.recompute()

    def _confirm_discard(self):
        """Ask before replacing unsaved work. True = go ahead."""
        if len(self.history) > 1 and not self.exported:
            from tkinter import messagebox
            return messagebox.askyesno(
                "cleanpal", "You have changes that haven't been exported or saved as a "
                            "project.\n\nDiscard them and continue?")
        return True

    def load_project_dialog(self):
        from tkinter import filedialog

        if not self._confirm_discard():
            return
        p = filedialog.askopenfilename(
            title="Load project",
            initialdir=self.s.get("project_dir") or self.s.get("last_dir") or None,
            filetypes=[("cleanpal project", "*" + PROJECT_EXT)])
        if p:
            self.load_project(p)

    def open_dialog(self):
        from tkinter import filedialog

        if not self._confirm_discard():
            return
        p = filedialog.askopenfilename(
            title="Open palette",
            initialdir=self.s.get("last_dir") or None,
            filetypes=[("Palette sources / projects", "*.wad *.pal *.png *" + PROJECT_EXT),
                       ("WAD", "*.wad"), ("Palette", "*.pal"), ("PNG", "*.png"),
                       ("cleanpal project", "*" + PROJECT_EXT), ("All files", "*.*")])
        if p:
            self.load(p)

    def load(self, path):
        from tkinter import messagebox

        if path.lower().endswith(PROJECT_EXT):
            self.load_project(path)
            return
        try:
            rgbs, label = load_palette(path)
        except (ValueError, OSError) as e:
            messagebox.showerror("cleanpal", "Could not load:\n%s\n\n%s" % (path, e))
            return
        self.close_tool(quiet=True, force=True)
        if self._ramp_backup is not None:
            self._ramp_end()
        self.project_path = None
        self.rgbs = list(rgbs)
        self.labs, self.pairs = build_pairs(self.rgbs)
        self.selection = set()
        self.deleted = set()
        self.cm = CmapState()
        self.cm_changed()
        self.cmap_brush = None
        self.cmap_loaded = ((self._loaded_from_wad(path, self.rgbs)
                             if path.lower().endswith(".wad") else None)
                            or self._iwad_colormap())
        self._cmap_status_text()
        self.history = [{"text": "Original - %d colours" % ENTRIES,
                         "palette": self.rgbs, "labs": self.labs, "pairs": self.pairs,
                         "cmap": CmapState()}]
        self.hist_pos = 0
        self.exported = True
        self._refresh_history()
        self.src_path = os.path.abspath(path)
        self.s["last_dir"] = os.path.dirname(self.src_path)
        self.file_var.set("%s   [%s]" % (os.path.basename(path), label))
        self._update_title()
        self.status_var.set("")
        self.recompute()

    def recompute(self):
        if self.rgbs is None:
            self.res = None
            self.stats_var.set("Open a palette to begin.")
        else:
            m = self.metric_var.get()
            cull = self._culling()         # culling only runs in the Cull tools
            self.res = analyse(self.rgbs, self.pairs[m], cull and self.exact_var.get(),
                               cull and self.similar_var.get(), self.tol[m],
                               self.selection if cull and self.scope_var.get() == "selected"
                               else None,
                               self.deleted if cull else set())
            r = self.res
            pre = (TOOL_NAME[self.tool].upper() + "  |  ") if self.tool else ""
            if self.hist_pos:
                pre += "Snapshot #%d  |  " % self.hist_pos
            if self._sort_backup is not None:
                pre = ("REORDER PREVIEW%s  |  " % ((" (%d ramps)" % self._sort_nramps)
                                                 if self._sort_nramps else "")) + pre
            if self._ramp_backup is not None:
                pre = "RAMP PREVIEW (%d cells)  |  " % len(self._ramp_targets) + pre
            if self._framp_backup is not None:
                pre = "FADE RAMP PREVIEW (%d strips)  |  " % len(self.fstrips) + pre
            post = ("  |  Selected: %d" % len(self.selection)) if self.selection else ""
            if cull:
                n_ex = sum(len(g) - 1 for g in r["exact_all"])
                n_si = sum(len(g) - 1 for g in r["similar_all"])
                n_del = r["status"].count("deleted")
                if n_del:
                    pre += "Deleted: %d  |  " % n_del
                self.stats_var.set(
                    pre + "Exact: %d removed (%d sets)  |  Similar: %d removed (%d clusters)"
                    "  |  Kept: %d  |  Empty: %d"
                    % (n_ex, len(r["exact_all"]), n_si, len(r["similar_all"]),
                       len(r["kept"]), ENTRIES - len(r["kept"])) + post
                    + ("  |  Cull: selected only" if self.similar_var.get()
                       and self.scope_var.get() == "selected" else ""))
            else:
                self.stats_var.set(pre + "Colours: %d  |  Empty: %d" % (
                    len(r["kept"]), ENTRIES - len(r["kept"])) + post)
        self._tool_refresh_win()
        self.redraw()
        if self.preview is not None:
            self.preview.schedule()
        self._tools_refresh()
        if self.cmap_mode():
            self._fade_schedule()

    def token(self):
        if not self.exact_var.get():
            return "(NONE)"
        if not self.similar_var.get():
            return "(EXACT)"
        m = self.metric_var.get()
        return "(%s-%s)" % (METRIC_TOKEN[m], fmt_tol(self.tol[m]))

    def _grid_world(self):
        return 16 * self.CELL + 15 * self.GAP

    def _cell_xy(self, slot):
        """Screen top-left of a cell plus its screen size."""
        step = self.CELL + self.GAP
        sc = self.view_scale
        x = self.off_x + (slot % 16) * step * sc
        y = self.off_y + (slot // 16) * step * sc
        return x, y, self.CELL * sc

    def _fit_scale(self):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        g = self._grid_world()
        return max(min((cw - 2 * self.PAD) / g, (ch - 2 * self.PAD) / g), 0.05)

    def fit_view(self):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        g = self._grid_world()
        self.view_scale = self._fit_scale()
        self.off_x = (cw - g * self.view_scale) / 2
        self.off_y = (ch - g * self.view_scale) / 2
        self.auto_fit = True
        self.redraw()

    def _on_canvas_resize(self, _ev):
        if self.auto_fit:
            self.fit_view()
        else:
            self.redraw()

    def _zoom_at(self, x, y, factor):
        fit = self._fit_scale()
        new = min(max(self.view_scale * factor, fit * self.ZOOM_MIN), fit * self.ZOOM_MAX)
        if new == self.view_scale:
            return
        wx = (x - self.off_x) / self.view_scale
        wy = (y - self.off_y) / self.view_scale
        self.view_scale = new
        self.off_x = x - wx * new
        self.off_y = y - wy * new
        self.auto_fit = False
        self.redraw()

    def _on_wheel(self, ev):
        if ev.delta:
            self._zoom_at(ev.x, ev.y, self.ZOOM_STEP ** (ev.delta / 120.0))

    def _on_pan_start(self, ev):
        self._pan_start = (ev.x, ev.y, self.off_x, self.off_y)
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, ev):
        if self._pan_start is None:
            return
        x0, y0, ox, oy = self._pan_start
        self.off_x = ox + (ev.x - x0)
        self.off_y = oy + (ev.y - y0)
        self.auto_fit = False
        self.redraw()

    def _on_pan_end(self, _ev):
        self._pan_start = None
        self.canvas.configure(cursor="")

    def _on_fit_key(self, ev):
        if ev.widget.winfo_class() in ("TEntry", "Entry", "TCombobox", "Text"):
            return
        self.fit_view()

    def _view_entry(self, slot):
        """(index, status) shown at slot, or None for empty."""
        if self.res is None:
            return None
        if self._align_on():
            kept = self.res["kept"]
            return (kept[slot], "kept") if slot < len(kept) else None
        return slot, self.res["status"][slot]

    @staticmethod
    def _hex(c):
        return "#%02x%02x%02x" % c

    @staticmethod
    def _contrast(c):
        return "#000000" if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 140 else "#ffffff"

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        cw = cv.winfo_width()
        ch = cv.winfo_height()
        for slot in range(ENTRIES):
            x, y, C = self._cell_xy(slot)
            if x > cw or y > ch or x + C < 0 or y + C < 0:
                continue  # off-screen
            ent = self._view_entry(slot)
            if ent is None or ent[1] == "empty":
                h = C / 2
                cv.create_rectangle(x, y, x + C, y + C, fill="#5a5a5a", outline="")
                cv.create_rectangle(x, y, x + h, y + h, fill="#7a7a7a", outline="")
                cv.create_rectangle(x + h, y + h, x + C, y + C, fill="#7a7a7a", outline="")
                continue
            idx, st = ent
            rgb = self.rgbs[idx]
            cv.create_rectangle(x, y, x + C, y + C, fill=self._hex(rgb), outline="")
            if C < self.MARKER_MIN_PX or st == "kept":
                continue
            fg = self._contrast(rgb)
            w = max(1, min(6, round(C / 14)))
            if st == "exact":
                i = C * 0.23
                cv.create_line(x + i, y + i, x + C - i, y + C - i, fill=fg, width=w)
                cv.create_line(x + C - i, y + i, x + i, y + C - i, fill=fg, width=w)
            elif st == "similar":
                i = C * 0.27
                cv.create_oval(x + i, y + i, x + C - i, y + C - i, outline=fg, width=w)
            elif st == "deleted":
                i = C * 0.16
                bw = max(2, round(C / 7))
                cv.create_line(x + i, y + C / 2, x + C - i, y + C / 2, fill=fg, width=bw)
        hide = self.tool == "paint" and self.paint_hide_var.get()
        if self.selection and self.res is not None and not hide:
            for slot in range(ENTRIES):
                ent = self._view_entry(slot)
                if ent and ent[0] in self.selection:
                    x, y, C = self._cell_xy(slot)
                    w = max(2, min(5, round(C / 10)))
                    # black under, bright cyan over: readable on any colour
                    cv.create_rectangle(x + w, y + w, x + C - w, y + C - w,
                                        outline="#000000", width=w + 3)
                    cv.create_rectangle(x + w, y + w, x + C - w, y + C - w,
                                        outline="#00ffff", width=w)
        cell = self._paint_cell_target()
        if cell is not None and not hide and self.res is not None:
            x, y, C = self._cell_xy(cell)
            cv.create_rectangle(x + 1, y + 1, x + C - 1, y + C - 1,
                                outline="#000000", width=4)
            cv.create_rectangle(x + 1, y + 1, x + C - 1, y + C - 1,
                                outline="#ffffff", width=2, dash=(4, 3))
        if self._ramp_backup is not None and self.res is not None and not hide:
            tg = set(self._ramp_targets)
            for slot in range(ENTRIES):
                ent = self._view_entry(slot)
                if ent and ent[0] in tg:
                    x, y, C = self._cell_xy(slot)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#000000", width=3)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#ffb36b", width=2, dash=(4, 2))
        if self._sort_backup is not None and self._sort_block and self.res is not None \
                and self.sort_scope_var.get() == "selected":
            for slot in range(ENTRIES):
                ent = self._view_entry(slot)
                if ent and ent[1] != "empty" and ent[0] in self._sort_block:
                    x, y, C = self._cell_xy(slot)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#000000", width=3)
                    cv.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                        outline="#7fd4ff", width=2, dash=(4, 2))
        if self.cmap_mode() and self.res is not None:
            marks = []
            if self.cmap_brush is not None:
                marks.append((self.cmap_brush, "#ffe100", (6, 3)))
            for t in self.cmap_target_set:
                marks.append((t, "#ff9a00", (2, 2)))
            for idx, col, dash in marks:
                for slot in range(ENTRIES):
                    ent = self._view_entry(slot)
                    if ent and ent[0] == idx:
                        x, y, C = self._cell_xy(slot)
                        cv.create_rectangle(x + 2, y + 2, x + C - 2, y + C - 2,
                                            outline=col, width=2, dash=dash)
        self._draw_hover()

    def _outline(self, slot, colour, dash=None):
        x, y, C = self._cell_xy(slot)
        self.canvas.create_rectangle(x - 1, y - 1, x + C + 1, y + C + 1,
                                     outline=colour, width=2, dash=dash, tags="hover")

    def _draw_hover(self):
        self.canvas.delete("hover")
        slot = self.hover_slot
        if slot is None or self.res is None:
            self.info_var.set("")
            return
        ent = self._view_entry(slot)
        self._outline(slot, "#ffcc00")
        if ent is None or ent[1] == "empty":
            self.info_var.set("Slot %3d   empty" % slot)
            return

        idx, st = ent
        r = self.res
        rgb = self.rgbs[idx]
        lab = self.labs[idx]
        where = ("Slot %3d <- Index %3d" % (slot, idx)) if self._align_on() \
            else ("Index %3d" % idx)
        base = "%s   RGB(%3d,%3d,%3d)   Lab(%.1f, %.1f, %.1f)" % (
            (where,) + tuple(rgb) + tuple(lab))

        if not self._align_on():
            own = r["owner"][idx]
            group = [j for j in range(ENTRIES) if r["owner"][j] == own]
            for j in group:
                if j != slot:
                    self._outline(j, "#ffcc00", dash=(3, 2))
            if st == "deleted":
                tail = "deleted (manual) - Del again to restore"
            elif st == "exact":
                tail = "removed - exact copy of %d" % own
            elif st == "similar":
                m = self.metric_var.get()
                d = "%s %.2f" % (METRIC_HOVER[m], metric_dist(
                    m, rgb, self.rgbs[own], lab, self.labs[own]))
                tail = "removed - similar to %d (%s)" % (own, d)
            else:
                others = [j for j in group if j != idx]
                if others:
                    shown = ", ".join(str(j) for j in others[:8])
                    if len(others) > 8:
                        shown += ", ..."
                    tail = "kept - absorbs %d: %s" % (len(others), shown)
                else:
                    tail = "kept"
        else:
            tail = "kept"
        self.info_var.set(base + "   " + tail)

    def _slot_at(self, x, y):
        step = self.CELL + self.GAP
        wx = (x - self.off_x) / self.view_scale
        wy = (y - self.off_y) / self.view_scale
        gx, gy = math.floor(wx / step), math.floor(wy / step)
        if 0 <= gx < 16 and 0 <= gy < 16:
            return int(gy * 16 + gx)
        return None

    def _on_motion(self, ev):
        slot = self._slot_at(ev.x, ev.y)
        if slot != self.hover_slot:
            self.hover_slot = slot
            self._draw_hover()

    def _on_leave(self, _ev):
        self.hover_slot = None
        self._draw_hover()

    def _side_layout(self):
        cv = self.side_cv
        rw, rh = self.side.winfo_reqwidth(), self.side.winfo_reqheight()
        if int(cv.cget("width")) != rw:
            cv.configure(width=rw)
        cv.configure(scrollregion=(0, 0, rw, rh))
        if rh > cv.winfo_height() > 1:
            if not self.side_sb.winfo_ismapped():
                self.side_sb.grid(row=0, column=1, sticky="ns")
        else:
            if self.side_sb.winfo_ismapped():
                self.side_sb.grid_remove()
            cv.yview_moveto(0)

    def _side_scroll(self, units):
        if self.side.winfo_reqheight() > self.side_cv.winfo_height():
            self.side_cv.yview_scroll(units, "units")

    def _side_wheel(self, ev):
        if ev.delta:
            self._side_scroll(-1 if ev.delta > 0 else 1)
        return "break"

    def _selectable(self, idx):
        # any slot - blank and exact-removed cells too (ramp targets)
        return self.res is not None and 0 <= idx < ENTRIES

    @staticmethod
    def _alt_down(ev):
        return bool(ev.state & (0x20000 if os.name == "nt" else 0x0008))

    def _on_b1_press(self, ev):
        if self.res is None or self._preview_busy_msg(allow_filter=True):
            self._drag = None
            return
        if ev.state & 0x0004:
            mode = "toggle"
        elif ev.state & 0x0001:
            mode = "add"
        else:
            mode = "replace"
        d = {"x0": ev.x, "y0": ev.y, "mode": mode, "moved": False, "move": False}
        if self.move_var.get():
            # drag from a SELECTED colour = move the selection;
            # drag from anything else = selection box
            slot = self._slot_at(ev.x, ev.y)
            if slot is not None and slot in self.selection and mode == "replace":
                blk = sorted(self.selection) if len(self.selection) > 1 else [slot]
                d.update(move=True, slot=slot, block=blk,
                         swap=self._alt_down(ev) or self.move_swap_var.get())
        self._drag = d

    def _on_b1_move(self, ev):
        d = self._drag
        if not d:
            return
        if abs(ev.x - d["x0"]) + abs(ev.y - d["y0"]) > 4:
            d["moved"] = True
        if not d["moved"]:
            return
        cv = self.canvas
        if d["move"]:
            cv.delete("moveind")
            swap = d["swap"] or self._alt_down(ev)
            for b in d["block"]:
                x, y, C = self._cell_xy(b)
                cv.create_rectangle(x, y, x + C, y + C, outline="#ffffff", width=2,
                                    dash=(4, 3), tags="moveind")
            t = self._slot_at(ev.x, ev.y)
            if t is not None:
                x, y, C = self._cell_xy(t)
                w = max(3, round(4 * getattr(self, "ui", 1.0)))
                cv.create_rectangle(x, y, x + C, y + C, outline="#000000", width=w + 3,
                                    tags="moveind")
                cv.create_rectangle(x, y, x + C, y + C,
                                    outline="#ff40ff" if swap else "#ffff00",
                                    width=w, tags="moveind")
            return
        cv.delete("marquee")
        w = max(2, round(3 * getattr(self, "ui", 1.0)))
        cv.create_rectangle(d["x0"], d["y0"], ev.x, ev.y, outline="#000000",
                            width=w + 3, tags="marquee")
        cv.create_rectangle(d["x0"], d["y0"], ev.x, ev.y, outline="#00ffff",
                            width=w, tags="marquee")

    def _on_b1_release(self, ev):
        d = self._drag
        self._drag = None
        if not d:
            return
        self.canvas.delete("marquee")
        self.canvas.delete("moveind")
        if d["moved"] and self.scratch is not None and \
                self.root.winfo_containing(ev.x_root, ev.y_root) is self.scratch.cv:
            slot = self._slot_at(d["x0"], d["y0"])
            ent = self._view_entry(slot) if slot is not None else None
            if ent and self.rgbs[ent[0]] is not None:
                i = ent[0]
                if i in self.selection and len(self.selection) > 1:
                    cols = [self.rgbs[j] for j in sorted(self.selection)
                            if self.rgbs[j] is not None]
                else:
                    cols = [self.rgbs[i]]
                self.scratch.add_colours(cols)
            return
        if d["move"] and d["moved"]:
            t = self._slot_at(ev.x, ev.y)
            if t is not None and t != d["slot"]:
                self._do_move(d["block"], d["slot"], t, d["swap"] or self._alt_down(ev))
            return
        hits = []
        if d["moved"]:
            x0, x1 = sorted((d["x0"], ev.x))
            y0, y1 = sorted((d["y0"], ev.y))
            for slot in range(ENTRIES):
                x, y, C = self._cell_xy(slot)
                if x < x1 and x + C > x0 and y < y1 and y + C > y0:
                    ent = self._view_entry(slot)
                    if ent and self._selectable(ent[0]):
                        hits.append(ent[0])
        else:
            slot = self._slot_at(ev.x, ev.y)
            ent = self._view_entry(slot) if slot is not None else None
            if ent and self._selectable(ent[0]):
                hits.append(ent[0])
        self._sel_before_click = set(self.selection)
        self._apply_selection(hits, d["mode"])

    def _apply_selection(self, hits, mode):
        if self._culling() and (hits or mode == "replace"):
            self.scope_var.set("selected")     # culling only - reorder has its own scope
        if mode == "replace":
            self.selection = set(hits)
        elif mode == "add":
            self.selection |= set(hits)
        else:
            self.selection ^= set(hits)
        self._reorder_sync_scope()
        self.recompute()
        self._filter_sel_changed()

    @staticmethod
    def _typing(ev):
        return ev.widget.winfo_class() in ("TEntry", "Entry", "TSpinbox", "Spinbox",
                                           "Text", "TCombobox")

    def _on_select_all(self, ev):
        if self._typing(ev) or self.res is None or self._preview_busy_msg(allow_filter=True):
            return
        self._apply_selection([i for i in range(ENTRIES) if self._selectable(i)], "replace")
        return "break"

    def _on_delete_key(self, ev):
        if self._typing(ev):
            return
        self.delete_selected()
        return "break"

    def delete_selected(self):
        """Del / Backspace / button: delete the selection, or restore it if
        every selected colour is already deleted. Cull tools only."""
        if self._preview_busy_msg() or self.res is None:
            return
        if not self._culling():
            self.status_var.set("Deleting colours is in the Cull tools.")
            return
        sel = {i for i in self.selection if self.rgbs[i] is not None}
        if not sel:
            self.status_var.set("Select colours first, then press Delete.")
            return
        if sel <= self.deleted:
            self.deleted -= sel
            self.status_var.set("Restored %d colour(s)." % len(sel))
        else:
            n = len(sel - self.deleted)
            self.deleted |= sel
            self.status_var.set("Deleted %d colour(s) - Delete again to restore." % n)
        self.recompute()

    def clear_selection(self):
        if self._previewing():
            self._cancel_previews()        # Esc also closes a sort / ramp preview
            return
        if self.selection:
            self.selection = set()
            self._reorder_sync_scope()
            self.recompute()
            self._filter_sel_changed()

    def _load_entry(self, i):
        h = self.history[i]
        if h.get("labs") is None or h.get("pairs") is None:
            h["labs"], h["pairs"] = build_pairs(h["palette"])
        self.hist_pos = i
        same = self.rgbs is not None and list(h["palette"]) == list(self.rgbs)
        self.rgbs = h["palette"]
        self.labs = h["labs"]
        self.pairs = h["pairs"]
        self.cm = (h.get("cmap") or CmapState()).copy()
        self.cm_changed()
        if not same:                       # a pure COLORMAP step keeps the selection
            self.selection = set()
            self.deleted = set()
        self._refresh_history()
        self.recompute()

    def take_snapshot(self):
        """Cull tools: the current result becomes the working palette."""
        if self._preview_busy_msg() or self.res is None:
            return
        if not self._culling():
            self.status_var.set("Snapshot applies culls - it is in the Cull tools.")
            return
        r = self.res
        new = result_entries(self.rgbs, r, self.align_var.get())
        if new == self.rgbs:
            self.status_var.set("Nothing would change - no snapshot taken.")
            return
        n_ex = sum(1 for st in r["status"] if st == "exact")
        n_si = sum(1 for st in r["status"] if st == "similar")
        parts = []
        n_del = r["status"].count("deleted")
        if n_del:
            parts.append("Deleted -%d" % n_del)
        if n_ex:
            parts.append("Exact -%d" % n_ex)
        if n_si:
            m = self.metric_var.get()
            scope = ("on %d selected" % len(self.selection)) \
                if self.scope_var.get() == "selected" else "on all"
            parts.append("Similar %s %s %s -%d" % (METRIC_TOKEN[m], fmt_tol(self.tol[m]),
                                                  scope, n_si))
        if self.align_var.get():
            parts.append("packed")
        kept = sum(1 for e in new if e is not None)
        labs, pairs = build_pairs(new)
        _e, mapping, owner = self.export_mapping()
        cm2 = self.cm.copy()
        dropped = cm2.remap(mapping, owner)
        self.history = self.history[:self.hist_pos + 1]
        self.history.append({"text": "%s - %d colours" % (", ".join(parts), kept),
                             "palette": new, "labs": labs, "pairs": pairs, "cmap": cm2})
        self.exported = False
        self._load_entry(len(self.history) - 1)
        self.status_var.set("Snapshot #%d taken - now working on it.%s" % (
            self.hist_pos, ("  %d COLORMAP hand edit(s) pointed at removed colours and went "
                            "back to auto." % dropped) if dropped else ""))

    def _hist_ok(self, i):
        """History moves allowed? Move / Reorder / Paint can only step through
        their own session's entries (older ones may have pending culls)."""
        if self._preview_busy_msg():
            return False
        if self.move_pending():
            self.status_var.set("Apply or Revert the moves first.")
            self._refresh_history()
            return False
        if self.paint_pending():
            self.status_var.set("Snapshot or Revert the paint edits first.")
            self._refresh_history()
            return False
        if self._gated() and i < self._tool_floor:
            self.status_var.set("#%d is from before this %s session - close the %s tools "
                                "to go back further." % (i, TOOL_NAME[self.tool].lower(),
                                                         TOOL_NAME[self.tool]))
            self._refresh_history()
            return False
        return True

    def jump_to(self, i):
        if not self.history or not 0 <= i < len(self.history):
            return
        if not self._hist_ok(i):
            return
        self._load_entry(i)
        if self.tool == "move":
            self._move_reset()
        elif self.tool == "paint":
            self._paint_reset()
        self._tool_refresh_win()
        self.status_var.set("Loaded #%d." % i)

    def step_back(self):
        if self.hist_pos > 0:
            self.jump_to(self.hist_pos - 1)

    def remove_snapshot(self):
        if self.hist_pos == 0:
            self.status_var.set("#0 Original can't be removed.")
            return
        if not self._hist_ok(self.hist_pos - 1):
            return
        if self._gated() and self.hist_pos == self._tool_floor:
            self.status_var.set("Can't remove the entry this session started on.")
            return
        gone = self.hist_pos
        del self.history[gone]
        self._load_entry(gone - 1)
        if self.tool == "move":
            self._move_reset()
        elif self.tool == "paint":
            self._paint_reset()
        self.status_var.set("Removed snapshot #%d - loaded #%d." % (gone, self.hist_pos))

    def _on_undo_key(self, ev):
        if self._typing(ev):
            return
        if self._previewing():
            self._cancel_previews()
        elif self.move_var.get():
            self._undo_move()
        else:
            self.step_back()

    def _on_hist_select(self, _ev):
        if self._previewing():
            return
        sel = self.hist_list.curselection()
        if sel and sel[0] != self.hist_pos:
            self.jump_to(sel[0])
            if self.hist_list.curselection() != (self.hist_pos,):
                self._refresh_history()

    def _refresh_history(self):
        lb = self.hist_list
        lb.configure(state="normal")
        lb.delete(0, "end")
        for k, h in enumerate(self.history):
            lb.insert("end", "%s#%d  %s" % ("> " if k == self.hist_pos else "  ", k, h["text"]))
        if self.history:
            lb.selection_clear(0, "end")
            lb.selection_set(self.hist_pos)
            lb.see(self.hist_pos)
        busy = self._previewing() or self.move_pending() or self.paint_pending()
        floor = self._tool_floor if self._gated() else 0
        on = ["!disabled"] if self.hist_pos > floor and not busy else ["disabled"]
        self.back_btn.state(on)
        self.remove_btn.state(on)
        self.collapse_btn.state(["!disabled"] if len(self.history) > 1 and not busy
                                and not self._gated() else ["disabled"])
        lb.configure(state="disabled" if busy else "normal")

    def _push_history(self, text):
        self.history = self.history[:self.hist_pos + 1]
        self.history.append({"text": text, "palette": self.rgbs,
                             "labs": self.labs, "pairs": self.pairs, "cmap": self.cm.copy()})
        self.hist_pos = len(self.history) - 1
        self.exported = False
        self._refresh_history()

    def collapse_history(self):
        from tkinter import messagebox

        if self._previewing() or self._gated() or len(self.history) < 2:
            return
        if not messagebox.askyesno(
                "cleanpal", "Collapse the history to the current entry (#%d)?\n\n"
                            "All other entries are discarded - this can't be undone."
                            % self.hist_pos):
            return
        h = self.history[self.hist_pos]
        kept = sum(1 for e in h["palette"] if e is not None)
        self.history = [{"text": "Collapsed - %d colours" % kept, "palette": h["palette"],
                         "labs": h["labs"], "pairs": h["pairs"],
                         "cmap": (h.get("cmap") or CmapState()).copy()}]
        self.hist_pos = 0
        self.exported = False
        self._refresh_history()
        self.status_var.set("History collapsed to a single entry.")
        self.recompute()

    def open_preview(self):
        if self.preview is not None:
            self.preview.win.deiconify()
            self.preview.win.lift()
            self.preview.win.focus_set()
            return
        self.preview = PreviewWindow(self)

    def preview_palette(self):
        """Colours an export would write right now (unique, in order)."""
        if self.res is None:
            return None
        entries = result_entries(self.rgbs, self.res, False)
        return list(dict.fromkeys(e for e in entries if e is not None))

    def do_export(self):
        from tkinter import filedialog, messagebox

        if self.res is None:
            messagebox.showinfo("cleanpal", "Open a palette first.")
            return
        if self._gated():
            messagebox.showinfo("cleanpal", "Close the %s tools before exporting."
                                % TOOL_NAME[self.tool])
            return
        label = self.export_var.get()
        stem = os.path.splitext(os.path.basename(self.src_path))[0]
        outdir = self.s.get("last_dir") or os.path.dirname(self.src_path)
        token = self.token()
        suffix, ext = next((e[1], e[2]) for e in EXPORTS if e[0] == label)

        try:
            if suffix is None:
                d = filedialog.askdirectory(title="Folder for analysis PNGs",
                                            initialdir=outdir)
                if not d:
                    return
                files = write_analysis(d, stem, token, self.rgbs, self.res,
                                       self.exact_var.get(), self.similar_var.get(),
                                       self.split_var.get())
                self.status_var.set("Wrote %d file(s) to %s" % (len(files), d))
                self.exported = True
                return

            ftypes = [("PNG image", "*.png")] if ext == ".png" else [("Palette", "*.pal")]
            p = filedialog.asksaveasfilename(
                title="Export " + label, initialdir=outdir,
                initialfile="%s%s-%s%s" % (stem, suffix, token, ext),
                defaultextension=ext, filetypes=ftypes)
            if not p:
                return
            entries = result_entries(self.rgbs, self.res, self._align_on())
            write_export(label, p, entries)
            self.s["last_dir"] = os.path.dirname(p)
            self.status_var.set("Wrote %s" % p)
            self.exported = True
            if ext == ".pal" and any(e == GREEN for e in entries):
                messagebox.showwarning(
                    "cleanpal",
                    "A kept colour is exactly (0,255,0) - in the .pal it can't be "
                    "told apart from the green empty-slot fill.")
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Export failed:\n%s" % e)

    def show_help(self):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title("cleanpal help")
        txt = tk.Text(win, width=78, height=40, wrap="none", font=("Consolas", 10))
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)

    def _update_title(self):
        t = "cleanpal v%s" % VERSION
        if self.project_path:
            t += " - %s" % os.path.basename(self.project_path)
        elif self.src_path:
            t += " - %s" % os.path.basename(self.src_path)
        if self.preset_name:
            t += "  [preset: %s]" % self.preset_name
        self.root.title(t)

    def on_close(self):
        if self.move_pending():
            self.move_apply()              # unapplied moves count as changes
        if self.paint_pending():
            self.paint_snapshot()          # so do unsnapshotted paint edits
        if len(self.history) > 1 and not self.exported:
            from tkinter import messagebox
            if not messagebox.askyesno(
                    "cleanpal", "You have changes that haven't been exported or saved "
                                "as a project.\n\nClose anyway?"):
                return
        self._cancel_previews()
        self.close_tool(quiet=True, force=True)
        if self.preview is not None:
            self.preview.store_state()
        for w in (self.ramp, self.picker, self.scratch):
            if w is not None:
                w.close()
        self.s.update({
            "exact": self.exact_var.get(), "similar": self.similar_var.get(),
            "metric": self.metric_var.get(),
            "tol_de2000": self.tol["de2000"],
            "tol_lab": self.tol["lab"], "tol_rgb": self.tol["rgb"],
            "align": self.align_var.get(), "split": self.split_var.get(),
            "export": self.export_var.get(), "paint_hide_sel": self.paint_hide_var.get(),
        })
        self.s.update(self.current_sort_settings())
        self.s.update(self.cmap_set)
        try:
            zoomed = self.root.state() == "zoomed"
            self.s["zoomed"] = zoomed
            if not zoomed:
                self.s["geometry"] = self.root.geometry()
        except Exception:
            pass
        err = save_settings(self.s)
        if err:
            from tkinter import messagebox
            messagebox.showwarning("cleanpal", "Settings could not be saved:\n" + err)
        self.root.destroy()
