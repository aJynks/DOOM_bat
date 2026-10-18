"""Playpals window: browse other palettes and copy colours from them.

A reference viewer (not one of the exclusive tools): load pal0s from the
usual sources, cycle with Up / Down or tile several at once, select colours
and copy them to the shared clipboard. Pasting into the working palette goes
through the normal paste (Paint tools). A single colour can also be dragged
straight onto a main-grid cell while Paint is open.
"""

import json
import os

from ..colour import hex_of
from ..constants import ENTRIES
from ..palette_io import load_palette
from ..settings import PROJECT_EXT, validate_project


def read_pal0(path):
    """(256 colours, label) from any palette source, or ValueError."""
    if path.lower().endswith(PROJECT_EXT):
        with open(path, "r", encoding="utf-8") as fh:
            proj = validate_project(json.load(fh))
        pal = proj["history"][proj["hist_pos"]]["palette"]
        return [tuple(c) if c is not None else None for c in pal], "cleanpal project"
    rgbs, label = load_palette(path)
    return [tuple(c) for c in rgbs[:ENTRIES]], label


class PlaypalsWindow:
    def __init__(self, app):
        tk = app.tk
        from tkinter import ttk

        self.app = app
        s = app.s
        self.ui = ui = getattr(app, "ui", 1.0)
        self.win = tk.Toplevel(app.root)
        self.win.title("Playpals")
        self.win.transient(app.root)
        self.win.minsize(int(460 * ui), int(420 * ui))
        try:
            self.win.geometry(s.get("playpals_geometry") or "%dx%d" % (640 * ui, 640 * ui))
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self.entries = []          # {"name", "path", "rgbs", "label", "iwad"}
        self.idx = 0               # current (single) / active entry
        self.sel = set()           # selected indices in the active entry
        self.page = 0
        self._drag = None
        self._tiles = []           # (entry index, x0, y0, cell) for hit tests
        self._areas = []           # (entry index, x0, y0, x1, y1) whole tile areas

        mode = s.get("playpals_mode")
        self.mode_var = tk.StringVar(value=mode if mode in ("single", "tile") else "single")
        self.cols_var = tk.StringVar(value=str(int(s.get("playpals_cols", 2) or 2)))
        self.rows_var = tk.StringVar(value=str(int(s.get("playpals_rows", 2) or 2)))
        self.mark_var = tk.BooleanVar(value=bool(s.get("playpals_mark", True)))
        self.title_var = tk.StringVar()
        self.hover_var = tk.StringVar()
        self.sel_var = tk.StringVar()

        top = ttk.Frame(self.win, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Button(top, text="Add...", command=self.add_dialog).pack(side="left")
        ttk.Button(top, text="Remove", command=self.remove_current).pack(side="left",
                                                                         padx=(4, 0))
        ttk.Button(top, text="Clear", command=self.clear).pack(side="left", padx=(4, 0))
        ttk.Button(top, text="\u25b2", width=3, command=lambda: self.step(-1)).pack(
            side="left", padx=(12, 0))
        ttk.Button(top, text="\u25bc", width=3, command=lambda: self.step(1)).pack(
            side="left", padx=(2, 0))
        ttk.Label(top, textvariable=self.title_var).pack(side="left", padx=(8, 0))

        row2 = ttk.Frame(self.win, padding=(8, 4, 8, 0))
        row2.pack(fill="x")
        ttk.Radiobutton(row2, text="Single", value="single", variable=self.mode_var,
                        command=self._on_mode).pack(side="left")
        ttk.Radiobutton(row2, text="Tile", value="tile", variable=self.mode_var,
                        command=self._on_mode).pack(side="left", padx=(6, 0))
        for var in (self.cols_var, self.rows_var):
            sb = ttk.Spinbox(row2, from_=1, to=6, width=3, textvariable=var,
                             command=self._on_mode)
            sb.pack(side="left", padx=(6 if var is self.cols_var else 0, 0))
            sb.bind("<Return>", lambda e: self._on_mode())
            sb.bind("<FocusOut>", lambda e: self._on_mode())
            if var is self.cols_var:
                ttk.Label(row2, text="x").pack(side="left", padx=(2, 2))
        ttk.Checkbutton(row2, text="Mark colours already in my palette",
                        variable=self.mark_var, command=self.draw).pack(side="left",
                                                                        padx=(12, 0))

        self.cv = tk.Canvas(self.win, bg="#262626", highlightthickness=0)
        self.cv.pack(fill="both", expand=True, padx=8, pady=6)
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Motion>", self._hover)
        self.cv.bind("<Leave>", lambda e: self.hover_var.set(""))
        self.cv.bind("<MouseWheel>", lambda e: self.step(-1 if e.delta > 0 else 1))
        self.cv.bind("<Button-4>", lambda e: self.step(-1))
        self.cv.bind("<Button-5>", lambda e: self.step(1))

        bot = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        bot.pack(fill="x")
        ttk.Label(bot, textvariable=self.hover_var, font=("Consolas", 10)).pack(anchor="w")
        bf = ttk.Frame(bot)
        bf.pack(fill="x", pady=(4, 0))
        ttk.Label(bf, textvariable=self.sel_var, foreground="#666").pack(side="left")
        ttk.Button(bf, text="Insert into Paint",
                   command=lambda: self.copy_paste(insert=True)).pack(side="right")
        ttk.Button(bf, text="Paste into Paint", command=self.copy_paste).pack(
            side="right", padx=(0, 4))
        ttk.Button(bf, text="Copy", command=self.copy).pack(side="right", padx=(0, 4))
        ttk.Label(bot, text="click / drag = select   Shift add   Ctrl toggle   Ctrl+A all\n"
                            "Up / Down = next palette   Ctrl+C copy\n"
                            "Ctrl+V insert / Ctrl+Shift+V paste over, into the working palette\n"
                            "drag one colour onto a main-grid cell = set it (Paint)",
                  foreground="#888").pack(anchor="w", pady=(4, 0))

        w = self.win
        w.bind("<Up>", lambda e: self.step(-1))
        w.bind("<Down>", lambda e: self.step(1))
        w.bind("<Prior>", lambda e: self.step(-self._per_page()))
        w.bind("<Next>", lambda e: self.step(self._per_page()))
        w.bind("<Escape>", lambda e: self._set_sel(set()))
        for seq in ("<Control-a>", "<Control-A>"):
            w.bind(seq, lambda e: self._select_all())
        w.bind("<Control-c>", lambda e: self._key(e, self.copy))
        w.bind("<Control-v>", lambda e: self._key(e, lambda: app.clip_paste(insert=True)))
        for seq in ("<Control-V>", "<Control-Shift-V>"):
            w.bind(seq, lambda e: self._key(e, lambda: app.clip_paste()))
        from .tool_windows import focus_on_click
        focus_on_click(w)

        self._load_entries()
        try:
            self.idx = min(max(int(s.get("playpals_idx", 0)), 0), max(len(self.entries) - 1, 0))
        except (TypeError, ValueError):
            self.idx = 0
        self.page = self.idx // self._per_page()
        self.draw()

    # ---------------------------------------------------------- entries
    def _load_entries(self):
        self.entries = []
        arch = self.app.iwad_archive()
        if arch is not None and arch.playpal() is not None:
            self.entries.append({"name": "IWAD: %s" % os.path.basename(arch.path),
                                 "path": arch.path, "rgbs": arch.playpal(),
                                 "label": "IWAD PLAYPAL", "iwad": True})
        bad = []
        for p in self.app.s.get("playpals_files") or []:
            if isinstance(p, str) and not self._add_path(p, quiet=True):
                bad.append(p)
        if bad:
            self.app.status_var.set("Playpals: %d saved file(s) couldn't be read and were "
                                    "dropped." % len(bad))
            self._store_files()

    def _add_path(self, path, quiet=False):
        path = os.path.abspath(path)
        if any(e["path"] == path and not e.get("iwad") for e in self.entries):
            return True
        try:
            rgbs, label = read_pal0(path)
        except (OSError, ValueError) as e:
            if not quiet:
                from tkinter import messagebox
                messagebox.showerror("cleanpal", "Could not read a palette from:\n%s\n\n%s"
                                     % (path, e), parent=self.win)
            return False
        self.entries.append({"name": os.path.basename(path), "path": path, "rgbs": rgbs,
                             "label": label, "iwad": False})
        return True

    def _store_files(self):
        self.app.s["playpals_files"] = [e["path"] for e in self.entries if not e.get("iwad")]

    def add_dialog(self):
        from tkinter import filedialog

        paths = filedialog.askopenfilenames(
            parent=self.win, title="Add palettes",
            initialdir=self.app.s.get("playpals_dir") or self.app.s.get("last_dir") or None,
            filetypes=[("Palette sources", "*.wad *.pal *.png *" + PROJECT_EXT),
                       ("WAD", "*.wad"), ("Palette", "*.pal"), ("PNG", "*.png"),
                       ("cleanpal project", "*" + PROJECT_EXT), ("All files", "*.*")])
        if not paths:
            return
        first_new = len(self.entries)
        for p in paths:
            self._add_path(p)
        self.app.s["playpals_dir"] = os.path.dirname(paths[0])
        self._store_files()
        if len(self.entries) > first_new:
            self._go(first_new)
        self.draw()

    def remove_current(self):
        if not self.entries:
            return
        e = self.entries[self.idx]
        if e.get("iwad"):
            self.app.status_var.set("The IWAD palette is always listed.")
            return
        del self.entries[self.idx]
        self.idx = min(self.idx, max(len(self.entries) - 1, 0))
        self.sel = set()
        self._store_files()
        self.draw()

    def clear(self):
        self.entries = [e for e in self.entries if e.get("iwad")]
        self.idx, self.page, self.sel = 0, 0, set()
        self._store_files()
        self.draw()

    # ---------------------------------------------------------- navigation
    def _per_page(self):
        if self.mode_var.get() != "tile":
            return 1
        try:
            c = min(max(int(self.cols_var.get()), 1), 6)
            r = min(max(int(self.rows_var.get()), 1), 6)
        except ValueError:
            c, r = 2, 2
        return c * r

    def _on_mode(self):
        s = self.app.s
        s["playpals_mode"] = self.mode_var.get()
        try:
            s["playpals_cols"] = min(max(int(self.cols_var.get()), 1), 6)
            s["playpals_rows"] = min(max(int(self.rows_var.get()), 1), 6)
        except ValueError:
            pass
        self.page = self.idx // self._per_page()
        self.draw()

    def _go(self, i):
        if not self.entries:
            return
        i = min(max(i, 0), len(self.entries) - 1)
        if i != self.idx:
            self.sel = set()
        self.idx = i
        self.page = self.idx // self._per_page()
        self.app.s["playpals_idx"] = self.idx

    def step(self, n):
        self._go(self.idx + n)
        self.draw()
        return "break"

    # ---------------------------------------------------------- drawing
    def draw(self):
        cv = self.cv
        try:
            cv.delete("all")
        except self.app.tk.TclError:
            return
        self._tiles = []
        self._areas = []
        n = len(self.entries)
        if not n:
            self.title_var.set("No palettes - Add... some (WAD, .pal, pal0.png, playpal.png, "
                               "project)")
            self._sel_text()
            return
        e = self.entries[self.idx]
        self.title_var.set("%d/%d  %s  [%s]" % (self.idx + 1, n, e["name"], e["label"]))
        W, H = max(cv.winfo_width(), 50), max(cv.winfo_height(), 50)
        working = set(c for c in (self.app.rgbs or []) if c is not None) \
            if self.mark_var.get() else set()
        if self.mode_var.get() != "tile":
            self._draw_pal(self.idx, 0, 0, W, H, working, label=False)
        else:
            per = self._per_page()
            cols = min(max(int(self.cols_var.get() or 2), 1), 6)
            rows = max(1, per // cols)
            tw, th = W / cols, H / rows
            start = self.page * per
            for k in range(per):
                i = start + k
                if i >= n:
                    break
                c, r = k % cols, k // cols
                self._draw_pal(i, c * tw, r * th, tw, th, working, label=True)
        self._sel_text()

    def _draw_pal(self, i, x, y, w, h, working, label):
        cv = self.cv
        ui = self.ui
        pad = int(6 * ui)
        lab_h = int(18 * ui) if label else 0
        size = min(w - 2 * pad, h - 2 * pad - lab_h)
        cell = max(2, int(size // 16))
        gx = x + (w - cell * 16) / 2
        gy = y + lab_h + pad + (h - lab_h - 2 * pad - cell * 16) / 2
        active = i == self.idx
        if label:
            cv.create_text(x + w / 2, y + pad, text=self.entries[i]["name"], anchor="n",
                           fill="#ffd24a" if active else "#dddddd",
                           font=("Segoe UI", max(8, int(9 * ui)), "bold" if active else ""))
        rgbs = self.entries[i]["rgbs"]
        t = max(3, cell // 4)
        for k in range(ENTRIES):
            c = rgbs[k] if k < len(rgbs) else None
            cx, cy = gx + (k % 16) * cell, gy + (k // 16) * cell
            if c is None:
                cv.create_rectangle(cx, cy, cx + cell - 1, cy + cell - 1, fill="#3a3a3a",
                                    outline="#202020")
                continue
            cv.create_rectangle(cx, cy, cx + cell - 1, cy + cell - 1, fill=hex_of(c),
                                outline="#202020")
            if c in working and cell >= 8:
                cv.create_polygon(cx + 1, cy + 1, cx + t + 1, cy + 1, cx + 1, cy + t + 1,
                                  fill="#ffffff", outline="#000000")
        if active:
            ow = max(1, min(5, round(cell / 10)))
            for k in self.sel:
                cx, cy = gx + (k % 16) * cell, gy + (k // 16) * cell
                cv.create_rectangle(cx + ow, cy + ow, cx + cell - 1 - ow, cy + cell - 1 - ow,
                                    outline="#000000", width=ow + 3)
                cv.create_rectangle(cx + ow, cy + ow, cx + cell - 1 - ow, cy + cell - 1 - ow,
                                    outline="#00ffff", width=ow)
            if label:
                cv.create_rectangle(gx - 3, gy - 3, gx + cell * 16 + 2, gy + cell * 16 + 2,
                                    outline="#ffd24a", width=2)
        self._tiles.append((i, gx, gy, cell))
        self._areas.append((i, x, y, x + w, y + h))

    def _sel_text(self):
        n = len(self._sel_colours())
        self.sel_var.set("%d colour%s selected   |   %s" % (n, "" if n == 1 else "s",
                                                          self.app.clip_text()))

    # ---------------------------------------------------------- hit tests / selection
    def _hit(self, x, y):
        """(entry index, palette index) under x, y, or (entry, None) / (None, None)."""
        for i, gx, gy, cell in self._tiles:
            if gx - 6 <= x < gx + cell * 16 + 6 and gy - 6 <= y < gy + cell * 16 + 6:
                cx, cy = int((x - gx) // cell), int((y - gy) // cell)
                if 0 <= cx < 16 and 0 <= cy < 16:
                    return i, cy * 16 + cx
                return i, None
        return None, None

    def _tile_at(self, x, y):
        """Entry whose tile area contains x, y (margins included), or None."""
        for i, x0, y0, x1, y1 in self._areas:
            if x0 <= x < x1 and y0 <= y < y1:
                return i
        return None

    def _cells_in_box(self, x0, y0, x1, y1):
        for i, gx, gy, cell in self._tiles:
            if i != self.idx:
                continue
            lo_x, hi_x = sorted((x0, x1))
            lo_y, hi_y = sorted((y0, y1))
            out = []
            for k in range(ENTRIES):
                cx, cy = gx + (k % 16) * cell, gy + (k // 16) * cell
                if cx + cell > lo_x and cx < hi_x and cy + cell > lo_y and cy < hi_y:
                    out.append(k)
            return out
        return []

    def _set_sel(self, sel):
        self.sel = set(sel)
        self.draw()

    def _select_all(self):
        if self.entries:
            rgbs = self.entries[self.idx]["rgbs"]
            self._set_sel(k for k in range(ENTRIES) if rgbs[k] is not None)
        return "break"

    def _press(self, ev):
        self.cv.focus_set()
        if not self.entries:
            self._drag = None
            return
        i, k = self._hit(ev.x, ev.y)
        if i is None:                 # outside a palette: its tile, else the active one
            i = self._tile_at(ev.x, ev.y)
            if i is None:
                i = self.idx
            k = None
        if i != self.idx:
            self.idx, self.sel = i, set()
            self.app.s["playpals_idx"] = i
        mode = "toggle" if ev.state & 0x0004 else "add" if ev.state & 0x0001 else "replace"
        self._drag = {"x0": ev.x, "y0": ev.y, "k": k, "mode": mode, "moved": False,
                      "out": False}
        self.draw()

    def _motion(self, ev):
        d = self._drag
        if d is None:
            return
        if abs(ev.x - d["x0"]) + abs(ev.y - d["y0"]) > 4:
            d["moved"] = True
        inside = self.win.winfo_containing(ev.x_root, ev.y_root) is self.cv
        d["out"] = not inside
        self.cv.delete("box")
        if inside or d["k"] is None:
            d["out"] = False                       # boxes never drop onto the grid
            self.cv.configure(cursor="")
            w = max(2, round(3 * self.ui))
            self.cv.create_rectangle(d["x0"], d["y0"], ev.x, ev.y, outline="#000000",
                                     width=w + 3, tags="box")
            self.cv.create_rectangle(d["x0"], d["y0"], ev.x, ev.y, outline="#00ffff",
                                     width=w, tags="box")
        else:
            self.cv.configure(cursor="hand2")      # dragging a colour out

    def _release(self, ev):
        d, self._drag = self._drag, None
        self.cv.delete("box")
        self.cv.configure(cursor="")
        if d is None:
            return
        rgbs = self.entries[self.idx]["rgbs"]
        if d["out"]:
            if d["k"] is not None and rgbs[d["k"]] is not None:
                w = self.win.winfo_containing(ev.x_root, ev.y_root)
                if w is self.app.canvas:
                    self.app.drop_colour_on_grid(ev.x_root, ev.y_root, rgbs[d["k"]])
            return
        hits = (self._cells_in_box(d["x0"], d["y0"], ev.x, ev.y) if d["moved"]
                else ([d["k"]] if d["k"] is not None else []))
        if d["mode"] == "replace":
            sel = set(hits)
        elif d["mode"] == "add":
            sel = self.sel | set(hits)
        else:
            sel = self.sel ^ set(hits)
        self._set_sel(sel)

    def _hover(self, ev):
        i, k = self._hit(ev.x, ev.y)
        if i is None or k is None:
            self.hover_var.set("")
            return
        c = self.entries[i]["rgbs"][k]
        if c is None:
            self.hover_var.set("%s  index %3d  (empty)" % (self.entries[i]["name"], k))
            return
        txt = "%s  index %3d  RGB(%3d,%3d,%3d)  %s" % (self.entries[i]["name"], k, c[0], c[1],
                                                     c[2], hex_of(c))
        work = self.app.rgbs or []
        if c in work:
            txt += "   also in working palette at #%d" % work.index(c)
        self.hover_var.set(txt)

    # ---------------------------------------------------------- copy / paste
    def _sel_colours(self):
        if not self.entries:
            return []
        rgbs = self.entries[self.idx]["rgbs"]
        return [rgbs[k] for k in sorted(self.sel) if rgbs[k] is not None]

    def copy(self):
        cols = self._sel_colours()
        if not cols:
            self.app.status_var.set("Select colours in the Playpals window first.")
            return False
        self.app.clip_set(cols, "%s" % self.entries[self.idx]["name"])
        self._sel_text()
        return True

    def copy_paste(self, insert=False):
        if self.copy():
            self.app.clip_paste(insert=insert)
            self._sel_text()

    def _key(self, ev, fn):
        if self.app._typing(ev):
            return
        fn()
        return "break"

    def refresh(self):
        self._sel_text()
        if self.mark_var.get():
            self.draw()

    def close(self):
        try:
            self.app.s["playpals_geometry"] = self.win.geometry()
        except self.app.tk.TclError:
            pass
        self.app.s["playpals_mark"] = self.mark_var.get()
        self.app.playpals = None
        try:
            self.win.destroy()
        except self.app.tk.TclError:
            pass
