"""Palettised preview window."""

import math
import os

from ..lighting import SURFACES, WALL_ORIENTATIONS, flat_row, surface_row, wall_row
from ..palette_io import _pil_const, palettise, palettise_p, relight
from ..wadgfx import KIND_LABEL, WadSource


# ============================================================ preview window
class PreviewWindow:
    PAD = 10
    ZOOM_STEP = 1.2
    GAP = 8                 # page pixels between grid cells
    MAX_CACHE = 400
    TYPES = ["All", "Patches", "Sprites", "Flats", "Graphics"]   # + TEXTURE1 / TEXTURE2
    FOLDER_TYPES = ["Loose"]

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Palettised preview")
        self.win.minsize(480, 340)
        try:
            self.win.geometry(app.s.get("preview_geometry") or "820x700")
        except tk.TclError:
            pass
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(2, weight=1)

        self.mode = None          # "folder" / "wad"
        self.folder = None
        self.wad = None
        self.items = []
        self.view = []
        self.idx = 0
        self.orig_cache = {}
        self.conv_cache = {}
        self.conv_cache_key = None
        self.errors = {}
        self.content = None
        self.content_key = None
        self.cells = []           # grid: (view index, x, y, w, h) in page pixels
        self._used = 0
        self._native_checkers = {}
        self.view_scale = 1.0
        self.off_x = self.off_y = 0.0
        self.auto_fit = True
        self._pan = None
        self._after = None
        self._tkimg = None
        self._checker = (None, None)

        s = app.s
        self.view_var = tk.StringVar(value="pal")
        self.dither_var = tk.BooleanVar(value=bool(s.get("preview_dither", False)))
        self.type_var = tk.StringVar(value=s.get("preview_type", "All"))
        if self.type_var.get() not in self.TYPES + ["TEXTURE1", "TEXTURE2"]:
            self.type_var.set("All")
        self.filter_var = tk.StringVar(value=s.get("preview_filter", ""))
        self.layout_var = tk.StringVar(value=s.get("preview_layout", "single"))
        if self.layout_var.get() not in ("single", "grid"):
            self.layout_var.set("single")
        self.cols = self._clamp(s.get("preview_cols", 4))
        self.rows = self._clamp(s.get("preview_rows", 4))
        self.names_var = tk.BooleanVar(value=bool(s.get("preview_names", True)))
        self.cols_var = tk.StringVar(value=str(self.cols))
        self.rows_var = tk.StringVar(value=str(self.rows))
        self.name_var = tk.StringVar(value="Open a folder of PNGs or a WAD")
        self.light_on = tk.BooleanVar(value=bool(s.get("preview_light_on", False)))
        self.light_val = tk.IntVar(value=int(s.get("preview_light", 160)))
        self.dist_pos = tk.DoubleVar(value=float(s.get("preview_dist", 40.0)))
        self.surface_var = tk.StringVar(value=s.get("preview_surface", SURFACES[0]))
        if self.surface_var.get() not in SURFACES:
            self.surface_var.set(SURFACES[0])
        self.orient_var = tk.StringVar(value=s.get("preview_orient", WALL_ORIENTATIONS[0]))
        if self.orient_var.get() not in WALL_ORIENTATIONS:
            self.orient_var.set(WALL_ORIENTATIONS[0])
        self.corridor_var = tk.BooleanVar(value=bool(s.get("preview_corridor", False)))
        self.invul_var = tk.BooleanVar(value=False)
        self.compare_var = tk.BooleanVar(value=False)
        self._flip_cmp = False
        self.p_cache = {}
        self.p_cache_key = None
        self.lit_text = ""
        self.info_var = tk.StringVar(value="")
        self.hover_var = tk.StringVar(value="")

        # row 1: sources + navigation
        top = ttk.Frame(self.win, padding=(8, 8, 8, 2))
        top.grid(row=0, column=0, sticky="ew")
        ttk.Button(top, text="Open folder...", command=self.open_folder_dialog).pack(side="left")
        ttk.Button(top, text="Open WAD...", command=self.open_wad_dialog).pack(
            side="left", padx=(6, 0))
        ttk.Button(top, text="\u25b2", width=3, command=lambda: self.step(-1)).pack(
            side="left", padx=(10, 0))
        ttk.Button(top, text="\u25bc", width=3, command=lambda: self.step(1)).pack(
            side="left", padx=(2, 0))
        ttk.Label(top, textvariable=self.name_var).pack(side="left", padx=8)

        # row 2: filters, layout, view
        row2 = ttk.Frame(self.win, padding=(8, 2, 8, 4))
        row2.grid(row=1, column=0, sticky="ew")
        ttk.Label(row2, text="Type").pack(side="left")
        self.type_cb = ttk.Combobox(row2, textvariable=self.type_var, values=self.TYPES,
                                    state="readonly", width=10)
        self.type_cb.pack(side="left", padx=(4, 8))
        self.type_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        ttk.Label(row2, text="Name").pack(side="left")
        self.filter_entry = ttk.Entry(row2, textvariable=self.filter_var, width=11)
        self.filter_entry.pack(side="left", padx=(4, 10))
        self.filter_var.trace_add("write", lambda *a: self.apply_filter())

        ttk.Radiobutton(row2, text="Single", value="single", variable=self.layout_var,
                        command=self._on_layout).pack(side="left")
        ttk.Radiobutton(row2, text="Grid", value="grid", variable=self.layout_var,
                        command=self._on_layout).pack(side="left", padx=(4, 4))
        self.cols_sb = ttk.Spinbox(row2, from_=1, to=16, width=3, textvariable=self.cols_var)
        self.cols_sb.pack(side="left")
        ttk.Label(row2, text="x").pack(side="left", padx=2)
        self.rows_sb = ttk.Spinbox(row2, from_=1, to=16, width=3, textvariable=self.rows_var)
        self.rows_sb.pack(side="left")
        ttk.Checkbutton(row2, text="Names", variable=self.names_var,
                        command=self.redraw).pack(side="left", padx=(8, 0))
        for sb, var in ((self.cols_sb, self.cols_var), (self.rows_sb, self.rows_var)):
            sb.bind("<Up>", lambda e, v=var: self._spin(v, 1))
            sb.bind("<Down>", lambda e, v=var: self._spin(v, -1))
            sb.bind("<MouseWheel>", lambda e, v=var: self._spin(v, 1 if e.delta > 0 else -1))
            var.trace_add("write", lambda *a: self._on_grid_size())

        ttk.Checkbutton(row2, text="Dither", variable=self.dither_var,
                        command=self.schedule).pack(side="right")
        ttk.Radiobutton(row2, text="Original", value="orig", variable=self.view_var,
                        command=self.redraw).pack(side="right", padx=(0, 8))
        ttk.Radiobutton(row2, text="Palettised", value="pal", variable=self.view_var,
                        command=self.redraw).pack(side="right", padx=(0, 4))

        self.canvas = tk.Canvas(self.win, bg="#262626", highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=8)
        cv = self.canvas
        cv.bind("<Configure>", lambda e: self.redraw())
        cv.bind("<MouseWheel>", self._on_wheel)
        cv.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, self.ZOOM_STEP))
        cv.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / self.ZOOM_STEP))
        cv.bind("<ButtonPress-2>", self._pan_start)
        cv.bind("<B2-Motion>", self._pan_move)
        cv.bind("<ButtonRelease-2>", self._pan_end)
        cv.bind("<Double-Button-2>", lambda e: self.fit())
        cv.bind("<Button-1>", lambda e: cv.focus_set())
        cv.bind("<Double-Button-1>", self._on_double_click)
        cv.bind("<Motion>", self._on_motion)
        cv.bind("<Leave>", lambda e: self.hover_var.set(""))

        self._build_light_row()
        bottom = ttk.Frame(self.win, padding=(8, 4, 8, 8))
        bottom.grid(row=4, column=0, sticky="ew")
        ttk.Label(bottom, textvariable=self.info_var, font=("Consolas", 10)).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.hover_var, font=("Consolas", 10)).pack(anchor="w")

        w = self.win
        w.bind("<Up>", lambda e: self.step(-1))
        w.bind("<Down>", lambda e: self.step(1))
        w.bind("<Prior>", lambda e: self.step(-1))
        w.bind("<Next>", lambda e: self.step(1))
        w.bind("<space>", self._key_flip)
        w.bind("<Key-f>", self._key_fit)
        w.bind("<Key-F>", self._key_fit)
        w.bind("<Key-n>", self._key_names)
        w.bind("<Key-N>", self._key_names)
        w.protocol("WM_DELETE_WINDOW", self.close)
        w.focus_set()

        st = s.get("preview_mode")
        sel = s.get("preview_item")
        if st == "wad" and s.get("preview_wad") and os.path.isfile(s["preview_wad"]):
            self.open_wad(s["preview_wad"], sel)
        elif s.get("preview_dir") and os.path.isdir(s["preview_dir"]):
            self.open_folder(s["preview_dir"], sel)
        else:
            self.redraw()

    # ---------------- COLORMAP lighting
    def _build_light_row(self):
        from tkinter import ttk

        tk = self.app.tk
        lf = ttk.Frame(self.win, padding=(8, 4, 8, 0))
        lf.grid(row=3, column=0, sticky="ew")
        ttk.Checkbutton(lf, text="Apply COLORMAP lighting", variable=self.light_on,
                        command=self._light_changed).grid(row=0, column=0, sticky="w")
        self.light_widgets = []
        ttk.Label(lf, text="Sector light").grid(row=0, column=1, sticky="e", padx=(12, 4))
        sc = tk.Scale(lf, from_=0, to=255, orient="horizontal", showvalue=1, length=160,
                      variable=self.light_val, command=lambda v: self._light_changed())
        sc.grid(row=0, column=2, sticky="w")
        ttk.Label(lf, text="Distance").grid(row=0, column=3, sticky="e", padx=(12, 4))
        sd = tk.Scale(lf, from_=0, to=100, orient="horizontal", showvalue=0, length=140,
                      variable=self.dist_pos, command=lambda v: self._light_changed())
        sd.grid(row=0, column=4, sticky="w")
        self.dist_lbl = tk.StringVar()
        ttk.Label(lf, textvariable=self.dist_lbl, width=11).grid(row=0, column=5, sticky="w")
        r2 = ttk.Frame(lf)
        r2.grid(row=1, column=0, columnspan=6, sticky="w", pady=(2, 0))
        cb1 = ttk.Combobox(r2, textvariable=self.surface_var, values=SURFACES,
                           state="readonly", width=15)
        cb1.pack(side="left")
        cb1.bind("<<ComboboxSelected>>", lambda e: self._light_changed())
        cb2 = ttk.Combobox(r2, textvariable=self.orient_var, values=WALL_ORIENTATIONS,
                           state="readonly", width=22)
        cb2.pack(side="left", padx=(6, 0))
        cb2.bind("<<ComboboxSelected>>", lambda e: self._light_changed())
        c1 = ttk.Checkbutton(r2, text="Corridor (single view)", variable=self.corridor_var,
                             command=self._light_changed)
        c1.pack(side="left", padx=(10, 0))
        c2 = ttk.Checkbutton(r2, text="Invulnerability", variable=self.invul_var,
                             command=self._light_changed)
        c2.pack(side="left", padx=(10, 0))
        self.invul_chk = c2
        self.cmp_chk = ttk.Checkbutton(r2, text="Space compares with loaded COLORMAP",
                                       variable=self.compare_var,
                                       command=self._light_changed)
        self.cmp_chk.pack(side="left", padx=(10, 0))
        self.light_widgets = [sc, sd, cb1, cb2, c1, c2, self.cmp_chk]
        self._light_states()
        self.sync_extra()

    def sync_extra(self):
        """Invulnerability tick box only when the COLORMAP view shows those rows."""
        show = bool(getattr(self.app, "cmap_show_extra", None) and
                    self.app.cmap_show_extra.get())
        if show:
            if not self.invul_chk.winfo_manager():
                self.invul_chk.pack(side="left", padx=(10, 0), before=self.cmp_chk)
        else:
            self.invul_chk.pack_forget()
            if self.invul_var.get():
                self.invul_var.set(False)
                self.schedule()

    def _dist(self):
        return int(round(16 * (128.0 ** (self.dist_pos.get() / 100.0))))

    def _orientation(self):
        return WALL_ORIENTATIONS.index(self.orient_var.get())

    def _light_row(self):
        if self.invul_var.get():
            return 32
        return surface_row(self.surface_var.get(), self.light_val.get(), self._dist(),
                           self._orientation())

    def _light_states(self):
        on = self.light_on.get()
        for w in self.light_widgets:
            try:
                if w.winfo_class() in ("Scale",):
                    w.configure(state="normal" if on else "disabled")
                else:
                    w.state(["!disabled"] if on else ["disabled"])
            except Exception:
                pass
        if on and not self.app.cmap_loaded:
            self.cmp_chk.state(["disabled"])
        self.dist_lbl.set("%d units" % self._dist())

    def _light_changed(self):
        self._light_states()
        if not (self.light_on.get() and self.compare_var.get()):
            self._flip_cmp = False
        self.schedule()

    def _lighting(self):
        return self.light_on.get() and self.view_var.get() == "pal"

    def _p(self, it, img, pal):
        ck = (tuple(pal), self.dither_var.get())
        if ck != self.p_cache_key:
            self.p_cache.clear()
            self.p_cache_key = ck
        k = it["key"]
        if k not in self.p_cache:
            if len(self.p_cache) > self.MAX_CACHE:
                self.p_cache.clear()
            self.p_cache[k] = palettise_p(img, pal, self.dither_var.get())
        return self.p_cache[k]

    def _lit(self, it, img):
        """The image relit through a COLORMAP row (or as a corridor)."""
        from PIL import Image

        compare = bool(self._flip_cmp and self.app.cmap_loaded)
        pal = self.app.compare_palette() if compare else self.app.preview_palette()
        if not pal:
            return img
        if compare:
            ck = (tuple(pal), self.dither_var.get())
            if ck != self.p_cache_key:
                self.p_cache.clear()
                self.p_cache_key = ck
        p, alpha = self._p(it, img, pal)
        if not (self.corridor_var.get() and not self._grid()):
            row = self._light_row()
            self.lit_text = "row %d" % row
            return relight(p, alpha, self.app.light_palette(row, pal, compare))
        # corridor: a wall receding from near (left) to far (right)
        w, h = p.size
        near, far = 48.0, 2048.0
        Wc = max(480, min(1400, w * 5))
        Hc = max(h, 64) * 2
        out = Image.new("RGBA", (Wc, Hc), (24, 24, 24, 255))
        lit_rows = {}
        flat = self.surface_var.get() == SURFACES[1]
        lo_r, hi_r = 99, -1
        for x in range(Wc):
            # true perspective: screen x and column height both go as 1/distance
            t = x / float(Wc - 1)
            d = 1.0 / (1.0 / near + t * (1.0 / far - 1.0 / near))
            if self.invul_var.get():
                r = 32
            elif flat:
                r = flat_row(self.light_val.get(), d)
            else:
                r = wall_row(self.light_val.get(), d, self._orientation())
            lo_r, hi_r = min(lo_r, r), max(hi_r, r)
            if r not in lit_rows:
                lit_rows[r] = relight(p, alpha, self.app.light_palette(r, pal, compare))
            hc = max(1, int(round(Hc * near / d)))
            u = int(d) % w
            col = lit_rows[r].crop((u, 0, u + 1, h)).resize((1, hc), Image.NEAREST)
            out.alpha_composite(col, (x, (Hc - hc) // 2))
        self.lit_text = "corridor %d-%d units, rows %d-%d" % (near, far, lo_r, hi_r)
        return out

    def usage_counts(self):
        """Pixel count per palettised colour over the converted images."""
        counts = {}
        for img in list(self.conv_cache.values()):
            if img is None:
                continue
            for n, c in img.getcolors(1 << 16) or []:
                if c[3]:
                    counts[c[:3]] = counts.get(c[:3], 0) + n
        if not counts and self.p_cache_key is not None:
            pal = list(self.p_cache_key[0])
            for p, alpha in list(self.p_cache.values()):
                for n, i in p.getcolors(256) or []:
                    if i < len(pal):
                        counts[pal[i]] = counts.get(pal[i], 0) + n
        return counts

    # ---------------- helpers
    @staticmethod
    def _clamp(v):
        try:
            return max(1, min(16, int(v)))
        except (TypeError, ValueError):
            return 4

    @staticmethod
    def _typing(ev):
        return ev.widget.winfo_class() in ("TEntry", "Entry", "TCombobox", "TSpinbox")

    def _key_flip(self, ev):
        if self._typing(ev):
            return
        return self.flip()

    def _key_fit(self, ev):
        if self._typing(ev):
            return
        return self.fit()

    def _key_names(self, ev):
        if self._typing(ev):
            return
        self.names_var.set(not self.names_var.get())
        self.redraw()
        return "break"

    def _grid(self):
        return self.layout_var.get() == "grid"

    def _per_page(self):
        return self.cols * self.rows

    # ---------------- layout controls
    def _spin(self, var, n):
        var.set(str(self._clamp(self._clamp(var.get()) + n)))
        return "break"

    def _on_grid_size(self):
        try:
            c, r = int(self.cols_var.get()), int(self.rows_var.get())
        except ValueError:
            return                      # partial typing - wait
        if not (1 <= c <= 16 and 1 <= r <= 16):
            return
        if (c, r) != (self.cols, self.rows):
            self.cols, self.rows = c, r
            if self._grid():
                self.show(refit=True)

    def _on_layout(self):
        self.show(refit=True)

    # ---------------- sources
    def open_folder_dialog(self):
        from tkinter import filedialog

        d = filedialog.askdirectory(parent=self.win, title="Folder of PNGs",
                                    initialdir=self.folder or self.app.s.get("preview_dir")
                                    or None)
        if d:
            self.open_folder(d)

    def open_wad_dialog(self):
        from tkinter import filedialog

        last = self.app.s.get("preview_wad")
        p = filedialog.askopenfilename(
            parent=self.win, title="Open WAD",
            initialdir=os.path.dirname(last) if last else None,
            filetypes=[("WAD", "*.wad"), ("All files", "*.*")])
        if p:
            self.open_wad(p)

    def _reset_caches(self):
        self.orig_cache.clear()
        self.conv_cache.clear()
        self.errors.clear()
        self.content_key = None

    def open_folder(self, folder, select=None):
        """Every PNG in the folder and its subfolders (type "Loose")."""
        if not os.path.isdir(folder):
            self.name_var.set("Can't read folder: %s" % folder)
            return
        names = []
        for root, dirs, files in os.walk(folder):
            dirs.sort(key=str.lower)
            for f in files:
                if f.lower().endswith(".png"):
                    names.append(os.path.relpath(os.path.join(root, f), folder))
        names.sort(key=lambda n: n.lower())
        self.mode, self.folder, self.wad = "folder", folder, None
        self.items = [{"name": n, "kind": "loose", "fmt": "file",
                       "path": os.path.join(folder, n),
                       "key": ("file", os.path.join(folder, n))} for n in names]
        self._reset_caches()
        self.app.s.update(preview_mode="folder", preview_dir=folder)
        self.type_cb.configure(values=self.FOLDER_TYPES)
        self.type_var.set("Loose")
        self.type_cb.state(["!disabled"])
        self.apply_filter(select)

    def open_wad(self, path, select=None):
        from tkinter import messagebox

        fallback = None
        if self.app.history:
            fallback = [c if c is not None else (0, 0, 0)
                        for c in self.app.history[0]["palette"]]
        if fallback is None:
            fallback = [(i, i, i) for i in range(256)]
        iwad = self.app.iwad_archive(prompt=True, parent=self.win)
        try:
            wad = WadSource(path, fallback, iwad)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not open WAD:\n%s\n\n%s" % (path, e),
                                 parent=self.win)
            return
        self.mode, self.wad, self.folder = "wad", wad, None
        self.items = wad.items
        self._reset_caches()
        self.app.s.update(preview_mode="wad", preview_wad=path)
        types = self.TYPES + [KIND_LABEL[k] for k in ("texture1", "texture2")
                              if k in wad.tex_src]
        self.type_cb.configure(values=types)
        want = self.app.s.get("preview_type", "All")
        self.type_var.set(want if want in types else "All")
        self.type_cb.state(["!disabled"])
        self.apply_filter(select)

    def reload(self):
        """IWAD changed: re-open the current WAD (folders don't use it)."""
        if self.mode == "wad" and self.wad is not None:
            sel = self.view[self.idx]["name"] if self.view else None
            self.open_wad(self.wad.path, sel)

    def apply_filter(self, select=None):
        if select is None and self.view and 0 <= self.idx < len(self.view):
            select = self.view[self.idx]["name"]
        kind = self.type_var.get()
        text = self.filter_var.get().strip().upper()
        self.app.s.update(preview_filter=self.filter_var.get())
        if self.mode == "wad":
            self.app.s.update(preview_type=kind)

        def keep(it):
            if self.mode != "wad":
                return True
            if kind == "All":       # this WAD's own graphics + textures it defines
                return it.get("tex_src", "WAD") == "WAD"
            return KIND_LABEL.get(it["kind"]) == kind

        self.view = [it for it in self.items
                     if keep(it) and (not text or text in it["name"].upper())]
        names = [it["name"] for it in self.view]
        self.idx = names.index(select) if select in names else 0
        self.show(refit=True)

    # ---------------- images
    def _orig(self, it):
        from PIL import Image

        k = it["key"]
        if k in self.orig_cache:
            return self.orig_cache[k]
        if len(self.orig_cache) > self.MAX_CACHE:
            self.orig_cache.clear()
        try:
            if it["fmt"] == "file":
                with Image.open(it["path"]) as im:   # read only
                    im.load()
                    img = im.convert("RGBA")
            else:
                img = self.wad.image(it)
        except Exception as e:      # bad data: report, keep browsing
            img = None
            self.errors[k] = str(e)
        self.orig_cache[k] = img
        return img

    def _conv(self, it, img, pal):
        ck = (tuple(pal), self.dither_var.get())
        if ck != self.conv_cache_key:
            self.conv_cache.clear()
            self.conv_cache_key = ck
        k = it["key"]
        if k not in self.conv_cache:
            if len(self.conv_cache) > self.MAX_CACHE:
                self.conv_cache.clear()
            self.conv_cache[k] = palettise(img, pal, self.dither_var.get())
        return self.conv_cache[k]

    def _native_checker(self, size):
        from PIL import Image

        if size in self._native_checkers:
            return self._native_checkers[size]
        w, h = size
        cell = 4
        img = Image.new("RGBA", size)
        img.putdata([(90, 90, 90, 255) if ((x // cell) + (y // cell)) % 2
                     else (122, 122, 122, 255) for y in range(h) for x in range(w)])
        if len(self._native_checkers) > 64:
            self._native_checkers.clear()
        self._native_checkers[size] = img
        return img

    def _page_range(self):
        per = self._per_page()
        start = (self.idx // per) * per
        return start, min(start + per, len(self.view))

    def _content(self):
        """The image to display (single image or a whole grid page)."""
        from PIL import Image

        if not self.view:
            return None
        pal = self.app.preview_palette()
        pal_on = self.view_var.get() == "pal" and bool(pal)
        palkey = (tuple(pal), self.dither_var.get()) if pal_on else None
        lit_on = pal_on and self.light_on.get()
        if lit_on:
            palkey = palkey + (self.light_val.get(), self._dist(), self.surface_var.get(),
                               self.orient_var.get(), self.corridor_var.get(),
                               self.invul_var.get(), self._flip_cmp,
                               self.app.cmap_signature())
        if self._grid():
            a, b = self._page_range()
            key = ("grid", tuple(it["key"] for it in self.view[a:b]), self.cols, palkey)
        else:
            key = ("single", self.view[self.idx]["key"], palkey)
        if key == self.content_key:
            return self.content

        used = set()

        def get(it):
            img = self._orig(it)
            if img is not None and lit_on:
                img = self._lit(it, img)
            elif img is not None and pal_on:
                img = self._conv(it, img, pal)
                cols = img.getcolors(1 << 16)
                if cols:
                    used.update(c[:3] for _, c in cols if c[3])
            return img

        self.cells = []
        if not self._grid():
            img = get(self.view[self.idx])
        else:
            a, b = self._page_range()
            ims = [(i, get(self.view[i])) for i in range(a, b)]
            sizes = [im.size for _, im in ims if im is not None] or [(64, 64)]
            cw = max(s[0] for s in sizes)
            ch = max(s[1] for s in sizes)
            G = self.GAP
            nrows = -(-len(ims) // self.cols)
            W = self.cols * cw + (self.cols + 1) * G
            H = nrows * ch + (nrows + 1) * G
            img = Image.new("RGBA", (W, H), (30, 30, 30, 255))
            for k, (i, im) in enumerate(ims):
                cx = G + (k % self.cols) * (cw + G)
                cy = G + (k // self.cols) * (ch + G)
                self.cells.append((i, cx, cy, cw, ch))
                if im is None:
                    continue
                ox, oy = cx + (cw - im.size[0]) // 2, cy + (ch - im.size[1]) // 2
                img.paste(self._native_checker(im.size), (ox, oy))
                img.alpha_composite(im, (ox, oy))
        self._used = len(used)
        self.content = img
        self.content_key = key
        return img

    # ---------------- navigation
    def show(self, refit=False):
        prev = self.content.size if self.content is not None else None
        self.content_key = None
        if not self.view:
            self.content = None
            what = "PNGs" if self.mode == "folder" else "matching graphics"
            self.name_var.set("No %s" % what if self.mode else
                              "Open a folder of PNGs or a WAD")
            self.info_var.set("")
            self.redraw()
            return
        img = self._content()
        if self._grid():
            per = self._per_page()
            a, b = self._page_range()
            pages = -(-len(self.view) // per)
            self.name_var.set("Page %d/%d  (%d-%d of %d)" % (
                a // per + 1, pages, a + 1, b, len(self.view)))
            refit = True                       # every page change refits
        else:
            it = self.view[self.idx]
            self.app.s["preview_item"] = it["name"]
            if img is None:
                self.name_var.set("%d/%d  %s  (can't decode: %s)" % (
                    self.idx + 1, len(self.view), it["name"],
                    self.errors.get(it["key"], "?")))
            else:
                self.name_var.set("%d/%d  %s  [%s]" % (
                    self.idx + 1, len(self.view), it["name"], self._describe(it, img)))
            if img is not None and prev != img.size:
                refit = True
        if refit:
            self.auto_fit = True
        self.redraw()

    def step(self, n):
        if self.view:
            if self._grid():
                per = self._per_page()
                pages = -(-len(self.view) // per)
                page = (self.idx // per + n) % pages
                self.idx = page * per
            else:
                self.idx = (self.idx + n) % len(self.view)
            self.show()
        return "break"

    def flip(self):
        if self.light_on.get() and self.compare_var.get() and self.app.cmap_loaded \
                and self.view_var.get() == "pal":
            self._flip_cmp = not self._flip_cmp
            self.schedule()
            return "break"
        self.view_var.set("orig" if self.view_var.get() == "pal" else "pal")
        self.redraw()
        return "break"

    def _cell_at(self, x, y):
        if not self._grid() or self.content is None:
            return None
        px = (x - self.off_x) / self.view_scale
        py = (y - self.off_y) / self.view_scale
        for c in self.cells:
            i, cx, cy, cw, ch = c
            if cx <= px < cx + cw and cy <= py < cy + ch:
                return c
        return None

    def _on_motion(self, ev):
        c = self._cell_at(ev.x, ev.y)
        if c is None:
            self.hover_var.set("")
            return
        it = self.view[c[0]]
        im = self.orig_cache.get(it["key"])
        desc = self._describe(it, im) if im is not None else "can't decode"
        self.hover_var.set("%s  [%s]   double-click = open single" % (it["name"], desc))

    @staticmethod
    def _describe(it, img):
        size = "%dx%d" % img.size
        if it["fmt"] == "file":
            return size
        if it["fmt"] == "tex":
            t = it["tex"]
            n = len(t["patches"])
            txt = "%s (%s) %s, %d patch%s" % (KIND_LABEL[it["kind"]], it["tex_src"], size,
                                              n, "" if n == 1 else "es")
            miss = it.get("missing")
            if miss:
                txt += ", MISSING: " + " ".join(miss[:6]) + (" ..." if len(miss) > 6 else "")
            return txt
        return "%s %s" % (it["kind"], size)

    def _on_double_click(self, ev):
        c = self._cell_at(ev.x, ev.y)
        if c is None:
            return
        self.idx = c[0]
        self.layout_var.set("single")
        self.show(refit=True)

    # ---------------- conversion
    def schedule(self):
        if self._after is not None:
            self.win.after_cancel(self._after)
        self._after = self.win.after(100, self._refresh)

    def _refresh(self):
        self._after = None
        self.redraw()

    # ---------------- view transform
    def _fit_scale(self, size):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        return max(min((cw - 2 * self.PAD) / size[0], (ch - 2 * self.PAD) / size[1]), 0.01)

    def fit(self):
        self.auto_fit = True
        self.redraw()
        return "break"

    def _zoom_at(self, x, y, factor):
        if self.content is None:
            return
        fit = self._fit_scale(self.content.size)
        new = min(max(self.view_scale * factor, fit * 0.25), max(fit * 8, 32.0))
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

    def _pan_start(self, ev):
        self._pan = (ev.x, ev.y, self.off_x, self.off_y)
        self.canvas.configure(cursor="fleur")

    def _pan_move(self, ev):
        if self._pan is None:
            return
        x0, y0, ox, oy = self._pan
        self.off_x = ox + ev.x - x0
        self.off_y = oy + ev.y - y0
        self.auto_fit = False
        self.redraw()

    def _pan_end(self, _ev):
        self._pan = None
        self.canvas.configure(cursor="")

    # ---------------- drawing
    def _checker_img(self, size):
        from PIL import Image

        if self._checker[0] == size:
            return self._checker[1]
        cell = 8
        cw, ch = -(-size[0] // cell), -(-size[1] // cell)
        small = Image.new("RGBA", (cw, ch))
        small.putdata([(90, 90, 90, 255) if (x + y) % 2 else (122, 122, 122, 255)
                       for y in range(ch) for x in range(cw)])
        big = small.resize((cw * cell, ch * cell), _pil_const("Resampling", "NEAREST"))
        img = big.crop((0, 0, size[0], size[1]))
        self._checker = (size, img)
        return img

    def redraw(self):
        from PIL import ImageTk

        cv = self.canvas
        cv.delete("all")
        im = self._content()
        if im is None:
            msg = "Open a folder of PNGs or a WAD" if not self.mode else "Nothing to show"
            cv.create_text(cv.winfo_width() / 2, cv.winfo_height() / 2, text=msg,
                           fill="#888")
            return
        cw, ch = cv.winfo_width(), cv.winfo_height()
        w, h = im.size
        if self.auto_fit:
            self.view_scale = self._fit_scale(im.size)
            self.off_x = (cw - w * self.view_scale) / 2
            self.off_y = (ch - h * self.view_scale) / 2
        sc = self.view_scale
        sx0 = max(0, math.floor(-self.off_x / sc))
        sy0 = max(0, math.floor(-self.off_y / sc))
        sx1 = min(w, math.ceil((cw - self.off_x) / sc))
        sy1 = min(h, math.ceil((ch - self.off_y) / sc))
        if sx1 > sx0 and sy1 > sy0:
            dw = max(1, round((sx1 - sx0) * sc))
            dh = max(1, round((sy1 - sy0) * sc))
            disp = im.crop((sx0, sy0, sx1, sy1)).resize(
                (dw, dh), _pil_const("Resampling", "NEAREST"))
            out = self._checker_img((dw, dh)).copy()
            out.alpha_composite(disp)
            self._tkimg = ImageTk.PhotoImage(out)
            cv.create_image(round(self.off_x + sx0 * sc), round(self.off_y + sy0 * sc),
                            image=self._tkimg, anchor="nw")
        # names on grid cells when big enough to read
        for i, cx, cy, cwid, chei in (self.cells if self.names_var.get() else ()):
            if cwid * sc < 70:
                break
            x = self.off_x + cx * sc
            y = self.off_y + cy * sc
            if x > cw or y > ch or x + cwid * sc < 0 or y + chei * sc < 0:
                continue
            t = cv.create_text(x + 4, y + 3, text=self.view[i]["name"], anchor="nw",
                               fill="#ff6060" if self.view[i].get("missing") else "#ffffff",
                               font=("Consolas", 9))
            bx = cv.bbox(t)
            r = cv.create_rectangle(bx[0] - 2, bx[1] - 1, bx[2] + 2, bx[3] + 1,
                                    fill="#000000", outline="")
            cv.tag_lower(r, t)

        src = ""
        if self.mode == "wad":
            src = "   source pal: %s" % self.wad.pal_src
            k = {"TEXTURE1": "texture1", "TEXTURE2": "texture2"}.get(self.type_var.get())
            if k in self.wad.tex_src:
                src += "   %s" % self.wad.tex_src[k]
            ip = self.app.iwad_path()
            src += "   IWAD: %s" % (os.path.basename(ip) if ip else "not set")
        pal = self.app.preview_palette() or []
        if self.view_var.get() == "pal" and pal and self.light_on.get():
            who = "LOADED PLAYPAL + COLORMAP" if self._flip_cmp else "CURRENT"
            self.info_var.set("LIT (%s)   light %d  %s   %s   zoom %.0f%%   (Space = %s)" % (
                who, self.light_val.get(), self.lit_text,
                "invulnerability" if self.invul_var.get() else self.surface_var.get(),
                sc * 100, "current" if self._flip_cmp else
                ("loaded" if self.compare_var.get() and self.app.cmap_loaded else
                 "original")))
        elif self.view_var.get() == "pal" and pal:
            self.info_var.set("PALETTISED   palette: %d colours   used: %d   dither: %s   "
                              "zoom %.0f%%%s   (Space = original)" % (
                                  len(pal), self._used,
                                  "on" if self.dither_var.get() else "off", sc * 100, src))
        else:
            self.info_var.set("ORIGINAL   zoom %.0f%%%s   (Space = palettised)" % (
                sc * 100, src))

    # ---------------- close
    def store_state(self):
        try:
            self.app.s["preview_geometry"] = self.win.geometry()
        except Exception:
            pass
        self.app.s.update(preview_light_on=self.light_on.get(),
                          preview_light=self.light_val.get(),
                          preview_dist=self.dist_pos.get(),
                          preview_surface=self.surface_var.get(),
                          preview_orient=self.orient_var.get(),
                          preview_corridor=self.corridor_var.get())
        self.app.s.update(preview_dither=self.dither_var.get(),
                          preview_layout=self.layout_var.get(),
                          preview_names=self.names_var.get(),
                          preview_cols=self.cols, preview_rows=self.rows)

    def close(self):
        self.store_state()
        if self._after is not None:
            self.win.after_cancel(self._after)
        self.app.preview = None
        self.win.destroy()
