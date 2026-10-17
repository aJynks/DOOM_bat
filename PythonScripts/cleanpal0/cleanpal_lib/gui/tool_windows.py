"""PLAYPAL tool windows (App mixin): Cull, Move, Reorder and Paint.

Only one tool is open at a time. With no tool open the grid shows the
current snapshot with no markers.

  Cull     culling (exact / similar / manual delete) runs only while this
           window is open. Snapshot applies the marks.
  Move     drag colours to new slots.        } need a clean snapshot: if
  Reorder  sort into ramps (app_sort.py).    } culls are pending they offer
  Paint    ramp tool + solid fill.           } to take one first.

While Move, Reorder or Paint is open culling is paused, Align is ignored and
Back only steps through that session's history entries.
"""

from ..constants import ENTRIES, METRICS, METRIC_LABEL

TOOLS = ("cull", "move", "reorder", "paint")
GATED = ("move", "reorder", "paint")       # need a clean snapshot
TOOL_NAME = {"cull": "Cull", "move": "Move", "reorder": "Reorder", "paint": "Paint"}
TOOL_VERB = {"move": "Moving", "reorder": "Reordering", "paint": "Painting"}
TOOL_COLOUR = {"cull": "#ff7a7a", "move": "#ffd24a", "reorder": "#7fd4ff",
               "paint": "#ffb36b"}
TOOL_HINT = {"cull": "remove exact / similar colours, delete",
             "move": "drag colours to new slots",
             "reorder": "sort colours into ramps",
             "paint": "colour ramps and fills on the palette"}


TEXT_CLASSES = ("TEntry", "Entry", "TSpinbox", "Spinbox", "Text", "TCombobox")


def focus_on_click(win, target=None):
    """Clicking anything in `win` that isn't a text box / dropdown moves the
    keyboard focus to `target` (default: the window itself), so the palette
    shortcuts (Ctrl+C / X / V, Del, M ...) reach the palette instead of the
    last text box that had focus."""
    def on_click(ev):
        try:
            if ev.widget.winfo_class() not in TEXT_CLASSES and \
                    ev.widget.winfo_toplevel() is win:
                (target or win).focus_set()
        except Exception:
            pass
    win.bind("<Button-1>", on_click, add="+")


# ============================================================ shared window bits
class _ToolWin:
    """Small helper base: remembered position, lift, destroy."""

    POS_KEY = ""

    def _make_win(self, app, title):
        tk = app.tk
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(title)
        self.win.transient(app.root)
        self.win.resizable(True, False)
        self.win.protocol("WM_DELETE_WINDOW", app.close_tool)
        self.win.bind("<Control-z>", app._on_undo_key)
        self.win.bind("<Control-Z>", app._on_undo_key)
        return self.win

    def _place(self):
        app = self.app
        self.win.update_idletasks()
        pos = app.s.get(self.POS_KEY)
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

    def store_pos(self):
        try:
            self.app.s[self.POS_KEY] = "+%d+%d" % (self.win.winfo_x(), self.win.winfo_y())
        except self.app.tk.TclError:
            pass

    def lift(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_set()

    def refresh(self):
        pass

    def teardown(self):
        self.store_pos()
        try:
            self.win.destroy()
        except self.app.tk.TclError:
            pass


# ============================================================ Cull
class CullTool(_ToolWin):
    """Matching, Align, delete and Snapshot. Builds the matching widgets onto
    the App (sim_chk, scale, tol_spin ...) and clears them on close."""

    POS_KEY = "cull_pos"

    def __init__(self, app):
        tk = app.tk
        from tkinter import ttk

        win = self._make_win(app, "Cull tools")
        win.bind("<Delete>", app._on_delete_key)
        win.bind("<BackSpace>", app._on_delete_key)
        win.bind("<Escape>", lambda e: app.close_tool())
        ui = getattr(app, "ui", 1.0)

        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)

        mf = ttk.LabelFrame(f, text="Matching (runs in order)", padding=8)
        mf.pack(fill="x")
        ttk.Checkbutton(mf, text="1. Remove exact colours", variable=app.exact_var,
                        command=app._on_toggle).pack(anchor="w")
        app.sim_chk = ttk.Checkbutton(mf, text="2. Remove similar colours",
                                      variable=app.similar_var, command=app._on_toggle)
        app.sim_chk.pack(anchor="w", pady=(4, 0))

        sub = ttk.Frame(mf, padding=(18, 4, 0, 0))
        sub.pack(fill="x")
        sub.columnconfigure(0, weight=1)
        app.metric_rbs = []
        for row, m in enumerate(METRICS):
            text = METRIC_LABEL[m] + ("  (default)" if m == "de2000" else "")
            rb = ttk.Radiobutton(sub, text=text, value=m, variable=app.metric_var,
                                 command=app._on_metric)
            rb.grid(row=row, column=0, sticky="w")
            app.metric_rbs.append(rb)
        r0 = len(METRICS)
        hdr = ttk.Frame(sub)
        hdr.grid(row=r0, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(hdr, text="Tolerance").pack(side="left")
        ttk.Label(hdr, textvariable=app.range_var, foreground="#888").pack(side="right")
        app.scale = tk.Scale(sub, from_=0, to=10, resolution=0.05, orient="horizontal",
                             showvalue=0, length=int(200 * ui),
                             sliderlength=int(36 * ui), width=int(22 * ui),
                             command=app._on_scale)
        app.scale.grid(row=r0 + 1, column=0, sticky="ew")
        app.scale.bind("<Button-1>", app._on_scale_click)
        app.scale.bind("<MouseWheel>", lambda e: app._step_tol(1 if e.delta > 0 else -1))
        app.scale.bind("<Button-4>", lambda e: app._step_tol(1))
        app.scale.bind("<Button-5>", lambda e: app._step_tol(-1))
        app.tol_spin = ttk.Spinbox(sub, textvariable=app.tol_text, from_=0, to=1000,
                                   increment=0.05, width=9, command=app._on_spin_arrow)
        app.tol_spin.grid(row=r0 + 2, column=0, sticky="w", pady=(4, 0))
        sp = app.tol_spin
        sp.bind("<Up>", lambda e: app._step_tol(1))
        sp.bind("<Down>", lambda e: app._step_tol(-1))
        sp.bind("<Shift-Up>", lambda e: app._step_tol(10))
        sp.bind("<Shift-Down>", lambda e: app._step_tol(-10))
        sp.bind("<MouseWheel>", lambda e: app._step_tol(1 if e.delta > 0 else -1))
        sp.bind("<Button-4>", lambda e: app._step_tol(1))
        sp.bind("<Button-5>", lambda e: app._step_tol(-1))
        sp.bind("<Return>", app._on_tol_commit)
        sp.bind("<FocusOut>", app._on_tol_commit)
        scf = ttk.Frame(sub)
        scf.grid(row=r0 + 3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(scf, text="Cull:").pack(side="left")
        app.scope_rbs = [
            ttk.Radiobutton(scf, text="Whole palette", value="all",
                            variable=app.scope_var, command=app.recompute),
            ttk.Radiobutton(scf, text="Selected only", value="selected",
                            variable=app.scope_var, command=app.recompute),
        ]
        for rb in app.scope_rbs:
            rb.pack(side="left", padx=(6, 0))

        af = ttk.Frame(f)
        af.pack(fill="x", pady=(8, 0))
        app.align_chk = ttk.Checkbutton(af, text="Align (pack kept colours toward index 0)",
                                        variable=app.align_var, command=app._on_toggle)
        app.align_chk.pack(anchor="w")

        df = ttk.Frame(f)
        df.pack(fill="x", pady=(8, 0))
        ttk.Button(df, text="Delete / restore selected",
                   command=app.delete_selected).pack(side="left")
        ttk.Label(df, text="Del / Backspace", foreground="#888").pack(side="left",
                                                                      padx=(6, 0))
        ttk.Label(f, text="X = exact removed   O = similar removed   - = deleted\n"
                          "Snapshot applies the marks and makes the result the\n"
                          "working palette (a new history entry).",
                  foreground="#666").pack(anchor="w", pady=(8, 0))

        ttk.Separator(f).pack(fill="x", pady=(10, 0))
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(8, 0))
        self.snap_btn = ttk.Button(bf, text="Snapshot", command=app.take_snapshot)
        self.snap_btn.pack(side="left")
        ttk.Button(bf, text="Close", command=app.close_tool).pack(side="right")
        self._place()

    def teardown(self):
        a = self.app
        a.sim_chk = None
        a.metric_rbs = []
        a.scale = None
        a.tol_spin = None
        a.scope_rbs = []
        a.align_chk = None
        super().teardown()


# ============================================================ Move
class MoveTool(_ToolWin):
    POS_KEY = "move_pos"

    def __init__(self, app):
        tk = app.tk
        from tkinter import ttk

        win = self._make_win(app, "Move tools")
        win.bind("<Escape>", lambda e: app.close_tool())
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Click to select. Drag a SELECTED colour to move it\n"
                          "(a multi-selection moves as one block). Drag anywhere\n"
                          "else = selection box. Alt+drag = swap one colour.",
                  foreground="#666").pack(anchor="w")
        ttk.Checkbutton(f, text="Swap instead of insert (single colour)",
                        variable=app.move_swap_var).pack(anchor="w", pady=(8, 0))
        self.count_var = tk.StringVar()
        ttk.Label(f, textvariable=self.count_var).pack(anchor="w", pady=(8, 0))
        cf = ttk.LabelFrame(f, text="Clipboard", padding=6)
        cf.pack(fill="x", pady=(8, 0))
        ttk.Button(cf, text="Cut", command=app.clip_cut).pack(side="left")
        ttk.Button(cf, text="Copy", command=app.clip_copy).pack(side="left", padx=(6, 0))
        ttk.Button(cf, text="Insert paste",
                   command=lambda: app.clip_paste(insert=True)).pack(side="left", padx=(6, 0))
        self.clip_var = tk.StringVar()
        ttk.Label(cf, textvariable=self.clip_var, foreground="#666").pack(side="left",
                                                                           padx=(10, 0))
        ttk.Label(f, text="Ctrl+X cut (the rest closes up)   Ctrl+C copy\n"
                          "Ctrl+Shift+V insert paste at the first selected cell",
                  foreground="#888").pack(anchor="w", pady=(4, 0))
        app._bind_clip_keys(win)
        focus_on_click(win)
        ttk.Separator(f).pack(fill="x", pady=(10, 0))
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(8, 0))
        self.undo_btn = ttk.Button(bf, text="Undo move", command=app._undo_move)
        self.undo_btn.pack(side="left")
        self.revert_btn = ttk.Button(bf, text="Revert", command=app.move_revert)
        self.revert_btn.pack(side="left", padx=(6, 0))
        self.apply_btn = ttk.Button(bf, text="Apply", command=app.move_apply)
        self.apply_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bf, text="Close", command=app.close_tool).pack(side="right")
        self.refresh()
        self._place()

    def refresh(self):
        a = self.app
        n = len(a._move_undo)
        pend = a.move_pending()
        self.count_var.set("Moves: %d%s" % (n, " (not applied yet)" if pend else
                                            ("" if n == 0 else " - same as start")))
        self.undo_btn.state(["!disabled"] if n else ["disabled"])
        self.clip_var.set(a.clip_text())
        for b in (self.revert_btn, self.apply_btn):
            b.state(["!disabled"] if pend else ["disabled"])


# ============================================================ host mixin
class ToolHostMixin:
    """Opens / closes the PLAYPAL tool windows and holds Move's logic."""

    # ---------------------------------------------------------- state helpers
    def _culling(self):
        return self.tool == "cull"

    def _gated(self):
        return self.tool in GATED

    def _align_on(self):
        """Align only means something while culling."""
        return self.tool == "cull" and self.align_var.get()

    def _cull_ui(self):
        return self.tool == "cull" and self.scale is not None

    # ---------------------------------------------------------- side panel
    def _build_tools_panel(self, side):
        tk = self.tk
        from tkinter import ttk

        tf = ttk.LabelFrame(side, text="Tools", padding=8)
        tf.pack(fill="x")
        tf.columnconfigure(1, weight=1)
        self.tool_btns = {}
        for row, t in enumerate(TOOLS):
            b = tk.Button(tf, text=TOOL_NAME[t], width=9, relief="raised",
                          command=lambda t=t: self.toggle_tool(t))
            b.grid(row=row, column=0, sticky="w", pady=(0 if row == 0 else 4, 0))
            self.tool_btns[t] = b
            ttk.Label(tf, text=TOOL_HINT[t], foreground="#666").grid(
                row=row, column=1, sticky="w", padx=(8, 0), pady=(0 if row == 0 else 4, 0))
        self._tool_btn_bg = self.tool_btns["cull"].cget("background")
        ttk.Label(tf, text="Move, Reorder and Paint need a clean snapshot\n"
                           "(no pending culls). M = Move tools.",
                  foreground="#888").grid(row=len(TOOLS), column=0, columnspan=2,
                                          sticky="w", pady=(8, 0))
        return tf

    def _build_clip_panel(self, side):
        from tkinter import ttk

        cf = ttk.LabelFrame(side, text="Clipboard", padding=8)
        cf.pack(fill="x", pady=(8, 0))
        bf = ttk.Frame(cf)
        bf.pack(fill="x")
        ttk.Button(bf, text="Cut", width=6, command=self.clip_cut).pack(side="left")
        ttk.Button(bf, text="Copy", width=6, command=self.clip_copy).pack(
            side="left", padx=(4, 0))
        ttk.Button(bf, text="Paste", width=6, command=self.clip_paste).pack(
            side="left", padx=(4, 0))
        ttk.Button(bf, text="Insert paste",
                   command=lambda: self.clip_paste(insert=True)).pack(side="left", padx=(4, 0))
        self.side_clip_var = self.tk.StringVar(value=self.clip_text())
        ttk.Label(cf, textvariable=self.side_clip_var).pack(anchor="w", pady=(6, 0))
        ttk.Label(cf, text="Ctrl+C copy (any tool)   Ctrl+X cut\n"
                           "Ctrl+V paste over (Paint)   Ctrl+Shift+V insert\n"
                           "Pastes at the first selected cell.",
                  foreground="#888").pack(anchor="w", pady=(4, 0))
        return cf

    def _refresh_tools(self):
        for t, b in self.tool_btns.items():
            on = self.tool == t
            b.configure(relief="sunken" if on else "raised",
                        background=TOOL_COLOUR[t] if on else self._tool_btn_bg,
                        activebackground=TOOL_COLOUR[t] if on else self._tool_btn_bg)
        col = TOOL_COLOUR.get(self.tool, "#262626")
        self.canvas.configure(highlightbackground=col, highlightcolor=col)

    # ---------------------------------------------------------- prompts
    def _ask_buttons(self, heading, text, buttons, default=0):
        """Modal prompt. buttons = [(key, label), ...] left to right; the last
        one is what Esc / the window's X return. Returns the chosen key."""
        tk = self.tk
        from tkinter import font as tkfont
        from tkinter import ttk

        win = tk.Toplevel(self.root)
        win.title("cleanpal")
        win.transient(self.root)
        win.resizable(False, False)
        cancel_key = buttons[-1][0]
        result = {"key": cancel_key}

        def done(key):
            result["key"] = key
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()

        f = ttk.Frame(win, padding=14)
        f.pack(fill="both", expand=True)
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        ttk.Label(f, text=heading, font=bold).pack(anchor="w")
        ttk.Label(f, text=text, justify="left", wraplength=440).pack(anchor="w", pady=(8, 0))
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(14, 0))
        btns = []
        for key, label in reversed(buttons):
            b = ttk.Button(bf, text=label, command=lambda k=key: done(k))
            b.pack(side="right", padx=(6, 0))
            btns.insert(0, b)
        win.bind("<Return>", lambda e: done(buttons[default][0]))
        win.bind("<Escape>", lambda e: done(cancel_key))
        win.protocol("WM_DELETE_WINDOW", lambda: done(cancel_key))
        win.update_idletasks()
        r = self.root
        x = r.winfo_rootx() + (r.winfo_width() - win.winfo_reqwidth()) // 2
        y = r.winfo_rooty() + (r.winfo_height() - win.winfo_reqheight()) // 3
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        try:
            win.grab_set()
        except tk.TclError:
            pass
        btns[default].focus_set()
        self.root.wait_window(win)
        return result["key"]

    def _pending_changes(self):
        """Pending culls / deletes (only while culling) as text parts."""
        r = self.res
        if r is None or not self._culling():
            return []
        st = r["status"]
        parts = []
        for key, label in (("exact", "Exact"), ("similar", "Similar"),
                           ("deleted", "Deleted")):
            n = st.count(key)
            if n:
                parts.append("%s -%d" % (label, n))
        return parts

    def _align_text(self):
        return ("pack the kept colours toward index 0 (Align is on)"
                if self.align_var.get() else
                "leave the removed slots empty (Align is off)")

    def _ask_snapshot(self, parts, name):
        return self._ask_buttons(
            "%s needs a clean snapshot first." % TOOL_VERB[name],
            "Pending changes: %s.\n\n"
            "Culling keeps the first colour of each group, so changing the palette now "
            "would change which colours get kept. Take a snapshot to apply the culls, "
            "then continue.\n\nThe snapshot will %s." % (", ".join(parts),
                                                         self._align_text()),
            [("snap", "Take snapshot and continue"), ("cancel", "Cancel")]) == "snap"

    # ---------------------------------------------------------- open / close
    def toggle_tool(self, name):
        if self.tool == name:
            self.close_tool()
        else:
            self.open_tool(name)

    def open_tool(self, name):
        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return False
        if self.cmap_mode():
            self.status_var.set("The PLAYPAL tools are in PLAYPAL mode.")
            return False
        if self.tool == name:
            self.tool_win.lift()
            return True
        if self._preview_busy_msg():
            return False
        if self.tool == "cull" and name in GATED:
            parts = self._pending_changes()
            if parts:
                if not self._ask_snapshot(parts, name):
                    self.status_var.set("%s tools not opened - a clean snapshot is needed "
                                        "first." % TOOL_NAME[name])
                    return False
                self.take_snapshot()
                if self._pending_changes():
                    self.status_var.set("The snapshot didn't clear the pending changes.")
                    return False
        if self.tool is not None and not self.close_tool(quiet=True):
            return False
        self.tool = name
        self._tool_floor = self.hist_pos
        if name == "cull":
            self.tool_win = CullTool(self)
            self._sync_tol_widgets()
            self._update_states(clear=False)
            msg = "Cull tools: culling is live. Snapshot applies the marks."
        elif name == "move":
            self.move_var.set(True)
            self._move_reset()
            self.tool_win = MoveTool(self)
            msg = ("Move tools: drag a selected colour to move it. Apply records the "
                   "moves.")
        elif name == "reorder":
            self._reorder_open()
            msg = ("Reorder tools: choose a method, Preview, Apply. Select colours to "
                   "reorder just those.")
        else:
            from .ramp_tool import PaintTool
            self._paint_reset()
            self.tool_win = PaintTool(self)
            self.ramp = self.tool_win
            msg = ("Paint tools: select cells, then ramp or fill them; double-click a cell "
                   "to colour just it. Snapshot records the edits.")
        self._refresh_tools()
        self._refresh_history()
        self.status_var.set(msg)
        self.recompute()
        return True

    def close_tool(self, quiet=False, force=False):
        """Close the open tool. Prompts (unless force) when culls are pending
        or moves aren't applied. Returns False if the user cancelled."""
        t = self.tool
        if t is None:
            return True
        if t == "cull" and not force:
            parts = self._pending_changes()
            if parts:
                k = self._ask_buttons(
                    "Culls are pending.",
                    "Pending changes: %s.\n\nTake a snapshot to apply them, or close "
                    "without applying - the marks come back when you reopen the Cull "
                    "tools.\n\nThe snapshot will %s." % (", ".join(parts),
                                                         self._align_text()),
                    [("snap", "Take snapshot"), ("close", "Close without applying"),
                     ("cancel", "Cancel")])
                if k == "cancel":
                    return False
                if k == "snap":
                    self.take_snapshot()
        elif t == "move" and self.move_pending():
            if force:
                self.move_apply()
            else:
                k = self._ask_buttons(
                    "Moves not applied.",
                    "You have moved colours since the last Apply.",
                    [("apply", "Apply"), ("discard", "Discard"), ("cancel", "Cancel")])
                if k == "cancel":
                    return False
                if k == "apply":
                    self.move_apply()
                else:
                    self.move_revert()
        elif t == "reorder":
            if self._sort_backup is not None:
                self.sort_cancel()
        elif t == "paint":
            if self.filter_win is not None:
                self.filter_win.close()            # cancels its preview
            if self._ramp_backup is not None:
                self.ramp_cancel()
            if self.paint_pending():
                if force:
                    self.paint_snapshot()
                else:
                    k = self._ask_buttons(
                        "Paint edits not snapshotted.",
                        "Unsnapshotted: %s." % self.paint_summary(),
                        [("snap", "Snapshot"), ("discard", "Discard"), ("cancel", "Cancel")])
                    if k == "cancel":
                        return False
                    if k == "snap":
                        self.paint_snapshot()
                    else:
                        self.paint_revert()
        w = self.tool_win
        if t == "reorder":
            self._reorder_teardown()
        else:
            w.teardown()
        if t == "move":
            self.move_var.set(False)
            self._move_start = None
            self._move_undo = []
        if t == "paint":
            self.ramp = None
            self._paint_start = None
        self.tool = None
        self.tool_win = None
        self._refresh_tools()
        self._refresh_history()
        if not quiet:
            self.status_var.set("%s tools closed." % TOOL_NAME[t])
        self.recompute()
        return True

    def _tool_refresh_win(self):
        if getattr(self, "side_clip_var", None) is not None:
            self.side_clip_var.set(self.clip_text())
        if self.tool_win is not None:
            self.tool_win.refresh()
        if getattr(self, "filter_win", None) is not None:
            self.filter_win.refresh()

    # ---------------------------------------------------------- Move logic
    def _move_reset(self):
        self._move_start = (self.rgbs, self.labs, self.pairs, set(self.deleted),
                            set(self.selection), self.cm.copy())
        self._move_undo = []

    def move_pending(self):
        return (self.tool == "move" and self._move_start is not None
                and self.rgbs != self._move_start[0])

    def move_apply(self):
        if not self.move_pending():
            return
        n_moves = len(self._move_undo)
        self._push_history("Moved colours (%d move%s) - %d colours" % (
            n_moves, "" if n_moves == 1 else "s", sum(1 for e in self.rgbs if e)))
        self._move_reset()
        self.status_var.set("Moves recorded as #%d (Back undoes them)." % self.hist_pos)
        self.recompute()

    def move_revert(self):
        if self._move_start is None:
            return
        (self.rgbs, self.labs, self.pairs, d, s, cm) = self._move_start
        self.deleted, self.selection, self.cm = set(d), set(s), cm.copy()
        self.cm_changed()
        self._move_undo = []
        self.status_var.set("Moves reverted.")
        self.recompute()

    def _on_move_key(self, ev):
        if self._typing(ev) or self.rgbs is None:
            return
        self.toggle_tool("move")

    def _move_push_undo(self):
        self._move_undo.append((self.rgbs, self.labs, self.pairs,
                                set(self.deleted), set(self.selection), self.cm.copy()))

    def _do_move(self, block, src, target, swap):
        n = ENTRIES
        if swap and len(block) == 1:
            perm = list(range(n))           # perm[new_slot] = old_slot
            perm[src], perm[target] = target, src
        else:
            bs = set(block)
            rest = [i for i in range(n) if i not in bs]
            pos = min(target, n - len(block))
            perm = rest[:pos] + list(block) + rest[pos:]
        if perm == list(range(n)):
            return
        self._move_undo.append((self.rgbs, self.labs, self.pairs,
                                set(self.deleted), set(self.selection), self.cm.copy()))
        self._permute(perm)
        self.recompute()

    def _undo_move(self):
        if not self._move_undo:
            self.status_var.set("No moves to undo.")
            return
        (self.rgbs, self.labs, self.pairs, self.deleted, self.selection,
         self.cm) = self._move_undo.pop()
        self.cm_changed()
        self.recompute()
