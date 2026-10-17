"""Ramp tool window."""

import json
import os

from ..colour import hex_of, parse_colour, rgb_round
from ..constants import PRESET_DIR, VERSION, fmt_tol
from ..ramps import (
    RAMP_EASES, RAMP_EASE_SCOPES, RAMP_SPACES, _ease, clean_ramp_state,
    default_ramp_state, ramp_colour_at, ramp_colours,
)


# ============================================================ ramp tool
class RampTool:
    """Gradient editor: nodes on a bar, blend space + easing. Fills the
    selected palette cells (blank or filled) in index order."""

    STATE_KEY = "ramp"
    TITLE = "Ramp tool"
    FADE = False
    GEOM_KEY = "ramp_geometry"
    GEOM_DEFAULT = "680x500"
    MIN_SIZE = (560, 420)

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        s = app.s
        ui = getattr(app, "ui", 1.0)
        self.ui = ui
        try:
            self.st = clean_ramp_state(s.get(self.STATE_KEY) or {})
        except ValueError:
            self.st = default_ramp_state()
        self.active = self.st["nodes"][0]
        self._drag = None
        self._img = None
        self._strip_cells = []
        self._after = None

        self.win = tk.Toplevel(app.root)
        self.win.title(self.TITLE)
        self.win.transient(app.root)
        self.win.minsize(*self.MIN_SIZE)
        try:
            self.win.geometry(s.get(self.GEOM_KEY) or self.GEOM_DEFAULT)
        except tk.TclError:
            pass
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(4, weight=1)

        self.bar = tk.Canvas(self.win, height=int(70 * ui), highlightthickness=0,
                             bg="#2a2a2a", cursor="hand2")
        self.bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        self.bar.bind("<Configure>", lambda e: self.draw_bar())
        self.bar.bind("<ButtonPress-1>", self._bar_press)
        self.bar.bind("<B1-Motion>", self._bar_motion)
        self.bar.bind("<ButtonRelease-1>", self._bar_release)
        self.bar.bind("<Double-Button-1>", self._bar_double)
        self.bar.bind("<ButtonPress-3>", self._bar_right)

        nf = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        nf.grid(row=1, column=0, sticky="ew")
        self.node_var = tk.StringVar()
        ttk.Label(nf, textvariable=self.node_var, width=20).pack(side="left")
        self.node_sw = tk.Canvas(nf, width=int(44 * ui), height=int(22 * ui),
                                 highlightthickness=1, highlightbackground="#888",
                                 cursor="hand2")
        self.node_sw.pack(side="left")
        self.node_sw.bind("<Button-1>", lambda e: self.open_picker())
        ttk.Label(nf, text="#").pack(side="left", padx=(8, 0))
        self.hex_var = tk.StringVar()
        he = ttk.Entry(nf, textvariable=self.hex_var, width=9)
        he.pack(side="left")
        he.bind("<Return>", lambda e: self._on_hex())
        he.bind("<FocusOut>", lambda e: self._on_hex())
        ttk.Label(nf, text="Pos %").pack(side="left", padx=(8, 0))
        self.pos_var = tk.StringVar()
        self.pos_sp = ttk.Spinbox(nf, textvariable=self.pos_var, from_=0, to=100,
                                  increment=1, width=6, command=self._on_pos)
        self.pos_sp.pack(side="left", padx=(4, 0))
        self.pos_sp.bind("<Return>", lambda e: self._on_pos())
        self.pos_sp.bind("<FocusOut>", lambda e: self._on_pos())
        ttk.Button(nf, text="Picker...", command=self.open_picker).pack(side="left",
                                                                        padx=(8, 0))
        self.del_btn = ttk.Button(nf, text="Delete node", command=self.delete_active)
        self.del_btn.pack(side="left", padx=(6, 0))

        of = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        of.grid(row=2, column=0, sticky="ew")
        self.space_var = tk.StringVar(value=self.st["space"])
        self.ease_var = tk.StringVar(value=self.st["ease"])
        self.str_var = tk.StringVar(value=fmt_tol(self.st["strength"]))
        self.scope_var = tk.StringVar(value=self.st["ease_scope"])
        ttk.Label(of, text="Blend").pack(side="left")
        w = ttk.Combobox(of, textvariable=self.space_var, values=RAMP_SPACES,
                         state="readonly", width=16)
        w.pack(side="left", padx=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_opts())
        ttk.Label(of, text="Ease").pack(side="left", padx=(10, 0))
        w = ttk.Combobox(of, textvariable=self.ease_var, values=RAMP_EASES,
                         state="readonly", width=11)
        w.pack(side="left", padx=(4, 0))
        w.bind("<<ComboboxSelected>>", lambda e: self._on_opts())
        ttk.Label(of, text="Strength").pack(side="left", padx=(10, 0))
        self.str_sp = ttk.Spinbox(of, textvariable=self.str_var, from_=1, to=6,
                                  increment=0.25, width=5, command=self._on_opts)
        self.str_sp.pack(side="left", padx=(4, 0))
        self.str_sp.bind("<Return>", lambda e: self._on_opts())
        self.str_sp.bind("<FocusOut>", lambda e: self._on_opts())
        of2 = ttk.Frame(self.win, padding=(8, 4, 8, 0))
        of2.grid(row=3, column=0, sticky="ew")
        ttk.Label(of2, text="Ease applies to:").pack(side="left")
        self.scope_rbs = []
        for v in RAMP_EASE_SCOPES:
            rb = ttk.Radiobutton(of2, text=v, value=v, variable=self.scope_var,
                                 command=self._on_opts)
            rb.pack(side="left", padx=(6, 0))
            self.scope_rbs.append(rb)
        ttk.Button(of2, text="Reverse", command=self.reverse).pack(side="right")
        ttk.Button(of2, text="Use selection ends",
                   command=self.use_selection_ends).pack(side="right", padx=(0, 6))

        sf = ttk.LabelFrame(self.win, text="Steps (one per selected cell, index order)",
                            padding=6)
        sf.grid(row=4, column=0, sticky="nsew", padx=8, pady=(8, 0))
        sf.columnconfigure(0, weight=1)
        sf.rowconfigure(0, weight=1)
        self.strip = tk.Canvas(sf, height=int(60 * ui), highlightthickness=0, bg="#2a2a2a")
        self.strip.grid(row=0, column=0, sticky="nsew")
        self.strip.bind("<Configure>", lambda e: self.draw_strip())
        self.strip.bind("<Motion>", self._strip_hover)
        self.strip.bind("<Leave>", lambda e: self.info_var.set(""))
        self.info_var = tk.StringVar()
        ttk.Label(sf, textvariable=self.info_var, font=("Consolas", 9)).grid(
            row=1, column=0, sticky="w", pady=(4, 0))

        ff = ttk.Frame(self.win, padding=(8, 8, 8, 0))
        ff.grid(row=5, column=0, sticky="ew")
        ttk.Button(ff, text="Load ramp...", command=self.load_ramp).pack(side="left")
        ttk.Button(ff, text="Save ramp...", command=self.save_ramp).pack(side="left",
                                                                         padx=(6, 0))
        ttk.Button(ff, text="Scratch palette...",
                   command=app.open_scratch).pack(side="right")
        bf = ttk.Frame(self.win, padding=8)
        bf.grid(row=6, column=0, sticky="ew")
        self.btn_frame = bf
        self.prev_btn = tk.Button(bf, text="Preview: OFF", width=12, relief="raised",
                                  command=self.toggle_preview)
        self._btn_bg = self.prev_btn.cget("background")
        self.prev_btn.pack(side="left")
        ttk.Button(bf, text="Apply", command=self.apply).pack(side="left", padx=(6, 0))
        self.cancel_btn = ttk.Button(bf, text="Cancel", command=self.cancel)
        self.cancel_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")

        def get():
            return tuple(self.active["rgb"])

        def put(rgb):
            self.set_node_colour(self.active, rgb)
            p = app.picker
            if p is not None and getattr(p, "owner", None) is self:
                self._target_picker(p)
        app.register_colour_widget(he, get, put)
        app.register_colour_widget(self.pos_sp, get, put)
        self.node_sw.bind("<Button-3>", lambda e: app.colour_menu(e, get, put))

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Delete>", self._on_del_key)
        self.win.bind("<Escape>", lambda e: self.cancel() if self.previewing() else None)
        self.sf = sf
        self.reverse_btn = [w for w in of2.winfo_children() if w.winfo_class() == "TButton"]

        self.setup()
        self.update_buttons()
        self.changed(store=False)
        app.recompute()

    # ---------------------------------------------------------- hooks (fade mode overrides)
    def setup(self):
        pass

    def previewing(self):
        return self.app._ramp_backup is not None

    # ---------------------------------------------------------- helpers
    def nodes(self):
        return self.st["nodes"]

    def idx(self, node):
        for k, n in enumerate(self.nodes()):
            if n is node:
                return k
        return 0

    def _bar_geom(self):
        W = max(self.bar.winfo_width(), 40)
        H = max(self.bar.winfo_height(), 40)
        m = int(12 * self.ui)
        return m, W - m, 4, H - int(24 * self.ui), H

    def _x(self, t):
        x0, x1, _y0, _y1, _H = self._bar_geom()
        return x0 + t * (x1 - x0)

    def _t(self, x):
        x0, x1, _y0, _y1, _H = self._bar_geom()
        return min(max((x - x0) / max(x1 - x0, 1), 0.0), 1.0)

    # node positions live in eased space when easing applies to the whole
    # ramp; the bar shows them where their colour actually appears
    def _whole(self):
        return self.st["ease_scope"] == "Whole ramp" and self.st["ease"] != "Linear"

    def _to_pos(self, t):
        return _ease(t, self.st["ease"], self.st["strength"]) if self._whole() else t

    def _to_bar(self, pos):
        if not self._whole():
            return pos
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2.0
            if _ease(mid, self.st["ease"], self.st["strength"]) < pos:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    def targets(self):
        a = self.app
        if a._ramp_backup is not None:
            return list(a._ramp_targets)
        return sorted(a.selection)

    def colours(self, n=None):
        return ramp_colours(self.st, len(self.targets()) if n is None else n)

    # ---------------------------------------------------------- drawing
    def draw_bar(self):
        from PIL import Image, ImageTk

        c = self.bar
        x0, x1, y0, y1, H = self._bar_geom()
        c.delete("all")
        w = int(x1 - x0)
        if w < 4:
            return
        strip = Image.new("RGB", (200, 1))
        strip.putdata([rgb_round(ramp_colour_at(self.st, i / 199.0)) for i in range(200)])
        self._img = ImageTk.PhotoImage(strip.resize((w, int(y1 - y0)), Image.BILINEAR))
        c.create_image(x0, y0, anchor="nw", image=self._img)
        c.create_rectangle(x0 - 1, y0 - 1, x1, y1, outline="#000000")
        sz = 9 * self.ui
        for n in self.nodes():
            x = self._x(self._to_bar(n["pos"]))
            act = n is self.active
            c.create_line(x, y0, x, y1, fill="#000000" if act else "", width=1)
            pts = (x, y1 + 2, x - sz, y1 + 2 + sz * 1.6, x + sz, y1 + 2 + sz * 1.6)
            c.create_polygon(*pts, fill=hex_of(n["rgb"]), outline="#000000",
                             width=3 if act else 1)
            if act:
                c.create_polygon(*pts, fill="", outline="#ffffff", width=1)

    def draw_strip(self):
        c = self.strip
        c.delete("all")
        tg = self.targets()
        n = len(tg)
        self._strip_cells = []
        W = max(c.winfo_width(), 40)
        if n == 0:
            c.create_text(10, 20, anchor="w", fill="#bbbbbb",
                          text="Select cells in the main grid (blank or filled) - "
                               "one ramp step per cell.")
            return
        cols = min(n, 32)
        cell = min(40 * self.ui, (W - 8) / cols)
        rows = (n + cols - 1) // cols
        need = int(rows * cell + 8)
        if int(c.cget("height")) < need:
            c.configure(height=need)
        cs = self.colours()
        base = self.app._ramp_backup[0] if self.app._ramp_backup else self.app.rgbs
        deleted = self.app._ramp_backup[3] if self.app._ramp_backup else self.app.deleted
        tset = set(tg)
        where = {}
        if base is not None:
            for i, col in enumerate(base):
                if col is not None and i not in tset and i not in deleted:
                    where.setdefault(tuple(col), i)
        seen = {}
        for k, col in enumerate(cs):
            x = 4 + (k % cols) * cell
            y = 4 + (k // cols) * cell
            c.create_rectangle(x, y, x + cell - 2, y + cell - 2, fill=hex_of(col),
                               outline="")
            fg = "#000000" if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] > 140 \
                else "#ffffff"
            dup = seen.get(col)
            ex = where.get(col)
            if dup is not None:
                r = max(2, cell / 9)
                c.create_oval(x + 3, y + 3, x + 3 + 2 * r, y + 3 + 2 * r, fill=fg,
                              outline="")
            if ex is not None:
                q = cell / 4
                c.create_polygon(x + cell - 2, y + cell - 2, x + cell - 2 - q, y + cell - 2,
                                 x + cell - 2, y + cell - 2 - q, fill=fg, outline="")
            seen.setdefault(col, k)
            self._strip_cells.append((x, y, cell, k, col, dup, ex, tg[k]))

    def _strip_hover(self, ev):
        for x, y, cell, k, col, dup, ex, slot in self._strip_cells:
            if x <= ev.x < x + cell and y <= ev.y < y + cell:
                t = "Step %d -> index %d   %s   %d,%d,%d" % ((k + 1, slot, hex_of(col))
                                                           + tuple(col))
                if dup is not None:
                    t += "   same as step %d" % (dup + 1)
                if ex is not None:
                    t += "   already in palette at %d" % ex
                self.info_var.set(t)
                return
        self.info_var.set("")

    def refresh_node_row(self):
        n = self.active
        k = self.idx(n)
        last = len(self.nodes()) - 1
        self.node_var.set("Node %d of %d" % (k + 1, last + 1) + (
            " (start)" if k == 0 else " (end)" if k == last else ""))
        self.node_sw.configure(background=hex_of(n["rgb"]))
        self.hex_var.set(hex_of(n["rgb"])[1:])
        self.pos_var.set(fmt_tol(round(self._to_bar(n["pos"]) * 100.0, 2)))
        end = k in (0, last)
        self.pos_sp.state(["disabled"] if end else ["!disabled"])
        self.del_btn.state(["disabled"] if end else ["!disabled"])

    def changed(self, store=True):
        self.draw_bar()
        self.refresh_node_row()
        self.draw_strip()
        if store:
            self.app.s[self.STATE_KEY] = json.loads(json.dumps(self.st))
        if self.previewing():
            if self._after is not None:
                self.win.after_cancel(self._after)
            self._after = self.win.after(50, self._push_preview)

    def _push_preview(self):
        self._after = None
        if self.app._ramp_backup is not None:
            self.app.ramp_preview_set(self.colours())

    # ---------------------------------------------------------- nodes
    def set_active(self, node):
        self.active = node
        self.changed(store=False)
        p = self.app.picker
        if p is not None and getattr(p, "owner", None) is self:
            self._target_picker(p)

    def _target_picker(self, p):
        node = self.active
        k = self.idx(node)
        p.owner = self
        p.set_target(lambda rgb, hsl, nd=node: self.set_node_colour(nd, rgb, hsl),
                     tuple(node["rgb"]), node.get("hsl"),
                     "ramp node %d of %d" % (k + 1, len(self.nodes())))

    def open_picker(self):
        p = self.app.open_picker()
        self._target_picker(p)

    def set_node_colour(self, node, rgb, hsl=None):
        if not any(n is node for n in self.nodes()):
            return
        node["rgb"] = list(rgb)
        node["hsl"] = list(hsl) if hsl else None
        self.changed()

    def _hit(self, x, y):
        x0, x1, y0, y1, H = self._bar_geom()
        best, bd = None, 10 * self.ui
        for n in self.nodes():
            d = abs(self._x(self._to_bar(n["pos"])) - x)
            if d <= bd and (y >= y1 - 2 or d <= 4 * self.ui):
                best, bd = n, d
        return best

    def _bar_press(self, ev):
        n = self._hit(ev.x, ev.y)
        if n is None:
            t = self._t(ev.x)
            col = rgb_round(ramp_colour_at(self.st, t))   # the colour shown there
            n = {"pos": min(max(self._to_pos(t), 0.001), 0.999), "rgb": list(col),
                 "hsl": None}
            nodes = self.nodes()
            nodes.append(n)
            nodes.sort(key=lambda q: q["pos"])
            self.set_active(n)
            self.changed()
        else:
            self.set_active(n)
        k = self.idx(n)
        if 0 < k < len(self.nodes()) - 1:
            self._drag = n

    def _bar_motion(self, ev):
        n = self._drag
        if n is None:
            return
        n["pos"] = min(max(self._to_pos(self._t(ev.x)), 0.001), 0.999)
        self.nodes().sort(key=lambda q: q["pos"])
        self.changed(store=False)

    def _bar_release(self, _ev):
        if self._drag is not None:
            self._drag = None
            self.changed()

    def _bar_double(self, ev):
        n = self._hit(ev.x, ev.y)
        if n is not None:
            self.set_active(n)
            self.open_picker()

    def _bar_right(self, ev):
        n = self._hit(ev.x, ev.y)
        if n is not None:
            self.delete_node(n)

    def delete_node(self, n):
        nodes = self.nodes()
        k = self.idx(n)
        if k in (0, len(nodes) - 1):
            return
        del nodes[k]
        if self.active is n:
            self.set_active(nodes[min(k, len(nodes) - 1)])
        self.changed()

    def delete_active(self):
        self.delete_node(self.active)

    def _on_del_key(self, ev):
        if ev.widget.winfo_class() in ("TEntry", "Entry", "TSpinbox", "Spinbox"):
            return
        self.delete_active()

    def _on_hex(self):
        c = parse_colour(self.hex_var.get())
        if c is None:
            self.refresh_node_row()
            return
        if tuple(self.active["rgb"]) != c:
            self.set_node_colour(self.active, c)
            p = self.app.picker
            if p is not None and getattr(p, "owner", None) is self:
                self._target_picker(p)

    def _on_pos(self):
        k = self.idx(self.active)
        if k in (0, len(self.nodes()) - 1):
            return
        try:
            v = float(self.pos_var.get())
        except ValueError:
            self.refresh_node_row()
            return
        self.active["pos"] = min(max(self._to_pos(min(max(v / 100.0, 0.0), 1.0)),
                                     0.001), 0.999)
        self.nodes().sort(key=lambda q: q["pos"])
        self.changed()

    def _on_opts(self):
        self.st["space"] = self.space_var.get()
        self.st["ease"] = self.ease_var.get()
        self.st["ease_scope"] = self.scope_var.get()
        try:
            v = float(self.str_var.get())
            self.st["strength"] = min(max(v, 1.0), 6.0)
        except ValueError:
            pass
        self.str_var.set(fmt_tol(self.st["strength"]))
        self.changed()

    def reverse(self):
        nodes = self.nodes()
        for n in nodes:
            n["pos"] = 1.0 - n["pos"]
        nodes.reverse()
        nodes[0]["pos"], nodes[-1]["pos"] = 0.0, 1.0
        self.set_active(self.active)
        self.changed()

    def use_selection_ends(self):
        a = self.app
        base = a._ramp_backup[0] if a._ramp_backup else a.rgbs
        tg = self.targets()
        if base is None or len(tg) < 2:
            a.status_var.set("Select at least two cells first.")
            return
        first, last = base[tg[0]], base[tg[-1]]
        if first is None or last is None:
            a.status_var.set("The first and last selected cells must hold colours.")
            return
        nodes = self.nodes()
        nodes[0]["rgb"], nodes[0]["hsl"] = list(first), None
        nodes[-1]["rgb"], nodes[-1]["hsl"] = list(last), None
        self.set_active(nodes[0])
        self.changed()

    def drop_colour(self, x_root, rgb):
        """A swatch dropped on the bar: recolour the node there, or add one."""
        x = x_root - self.bar.winfo_rootx()
        n = self._hit(x, 10 ** 6)
        if n is None:
            t = min(max(self._to_pos(self._t(x)), 0.001), 0.999)
            n = {"pos": t, "rgb": list(rgb), "hsl": None}
            self.nodes().append(n)
            self.nodes().sort(key=lambda q: q["pos"])
        else:
            n["rgb"], n["hsl"] = list(rgb), None
        self.set_active(n)
        self.changed()

    # ---------------------------------------------------------- preview / apply
    def update_buttons(self):
        on = self.previewing()
        self.prev_btn.configure(text="Preview: ON" if on else "Preview: OFF",
                                relief="sunken" if on else "raised",
                                background="#ffb36b" if on else self._btn_bg,
                                activebackground="#ffcb94" if on else self._btn_bg)
        self.cancel_btn.state(["!disabled"] if on else ["disabled"])

    def toggle_preview(self):
        if self.app._ramp_backup is not None:
            self.cancel()
        elif self.app.ramp_preview_start():
            self.app.ramp_preview_set(self.colours())
        self.update_buttons()
        self.draw_strip()

    def apply(self):
        a = self.app
        if a._ramp_backup is None:
            if not a.ramp_preview_start():
                self.update_buttons()
                return
        if self._after is not None:
            self.win.after_cancel(self._after)
            self._after = None
        cs = self.colours()
        a.ramp_preview_set(cs)
        a.ramp_apply(cs, [n["rgb"] for n in self.nodes()])
        self.update_buttons()
        self.draw_strip()

    def cancel(self):
        if self.app._ramp_backup is not None:
            self.app.ramp_cancel()
        self.update_buttons()
        self.draw_strip()

    def save_ramp(self):
        from tkinter import filedialog, messagebox

        initdir = self.app.s.get("ramp_dir") or PRESET_DIR
        try:
            os.makedirs(initdir, exist_ok=True)
        except OSError:
            initdir = None
        p = filedialog.asksaveasfilename(
            parent=self.win, title="Save ramp", initialdir=initdir,
            initialfile="ramp.json", defaultextension=".json",
            filetypes=[("cleanpal ramp", "*.json")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"cleanpal_ramp": 1, "version": VERSION, "ramp": self.st}, fh,
                          indent=2)
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not save ramp:\n%s" % e, parent=self.win)
            return
        self.app.s["ramp_dir"] = os.path.dirname(p)
        self.app.status_var.set("Saved ramp %s" % p)

    def load_ramp(self):
        from tkinter import filedialog, messagebox

        initdir = self.app.s.get("ramp_dir") or PRESET_DIR
        if not os.path.isdir(initdir):
            initdir = None
        p = filedialog.askopenfilename(
            parent=self.win, title="Load ramp", initialdir=initdir,
            filetypes=[("cleanpal ramp", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or data.get("cleanpal_ramp") != 1:
                raise ValueError("Not a cleanpal ramp file.")
            st = clean_ramp_state(data.get("ramp"))
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not load ramp:\n%s\n\n%s" % (p, e),
                                 parent=self.win)
            return
        self.app.s["ramp_dir"] = os.path.dirname(p)
        self.set_state(st)

    def set_state(self, st):
        self.st = st
        self.space_var.set(st["space"])
        self.ease_var.set(st["ease"])
        self.str_var.set(fmt_tol(st["strength"]))
        self.scope_var.set(st["ease_scope"])
        self.set_active(self.st["nodes"][0])
        self.changed()

    def teardown(self):
        """Store state, release the picker, destroy the window."""
        a = self.app
        if self._after is not None:
            self.win.after_cancel(self._after)
            self._after = None
        try:
            a.s[self.GEOM_KEY] = self.win.geometry()
        except a.tk.TclError:
            pass
        a.s[self.STATE_KEY] = json.loads(json.dumps(self.st))
        p = a.picker
        if p is not None and getattr(p, "owner", None) is self:
            p.owner = None
            p.set_target(None, p.rgb(), p.hsl(), "")
        self.win.destroy()

    def close(self):
        a = self.app
        if a._ramp_backup is not None:
            a.ramp_cancel()
        self.teardown()
        a.ramp = None
        a.recompute()

    # tool-host interface (Paint)
    def lift(self):
        self.win.deiconify()
        self.win.lift()

    def refresh(self):
        pass


# ============================================================ Paint tools
class PaintTool(RampTool):
    """PLAYPAL Paint tools: the palette ramp + a solid Fill section. Opened and
    closed by the tool host (needs a clean snapshot)."""

    TITLE = "Paint tools"
    GEOM_KEY = "paint_geometry"
    GEOM_DEFAULT = "720x760"
    MIN_SIZE = (580, 640)

    def setup(self):
        from tkinter import ttk

        a = self.app
        tk = a.tk
        ui = self.ui
        self.sf.configure(text="Ramp steps (one per selected cell, index order)")
        ff = ttk.LabelFrame(self.win, text="Fill (one colour into every selected cell)",
                            padding=6)
        ff.grid(row=6, column=0, sticky="ew", padx=8, pady=(8, 0))
        self.btn_frame.grid(row=9, column=0, sticky="ew")

        # clipboard: cut / copy / paste over / insert paste
        cf = ttk.LabelFrame(self.win, text="Clipboard  (Ctrl+X / Ctrl+C / Ctrl+V / "
                                           "Ctrl+Shift+V insert)", padding=6)
        cf.grid(row=7, column=0, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(cf, text="Cut", command=a.clip_cut).pack(side="left")
        ttk.Button(cf, text="Copy", command=a.clip_copy).pack(side="left", padx=(6, 0))
        ttk.Button(cf, text="Paste", command=a.clip_paste).pack(side="left", padx=(6, 0))
        ttk.Button(cf, text="Insert paste",
                   command=lambda: a.clip_paste(insert=True)).pack(side="left", padx=(6, 0))
        self.clip_var = tk.StringVar(value=a.clip_text())
        ttk.Label(cf, textvariable=self.clip_var, foreground="#666").pack(side="left",
                                                                           padx=(10, 0))
        a._bind_clip_keys(self.win)
        from .tool_windows import focus_on_click
        focus_on_click(self.win)

        # session: edits stay pending until Snapshot (one history entry)
        pf = ttk.LabelFrame(self.win, text="Paint session", padding=6)
        pf.grid(row=8, column=0, sticky="ew", padx=8, pady=(8, 0))
        ttk.Checkbutton(pf, text="Hide selection outline", variable=a.paint_hide_var,
                        command=a.redraw).pack(side="left")
        self.pend_var = tk.StringVar()
        ttk.Label(pf, textvariable=self.pend_var, foreground="#666").pack(
            side="left", padx=(12, 0))
        self.snap_btn = ttk.Button(pf, text="Snapshot", command=a.paint_snapshot)
        self.snap_btn.pack(side="right")
        ttk.Button(pf, text="Filters...", command=a.filter_open).pack(side="right",
                                                                      padx=(0, 12))
        self.revert_btn = ttk.Button(pf, text="Revert", command=a.paint_revert)
        self.revert_btn.pack(side="right", padx=(0, 6))
        self.cell_target = None
        self._picker_fill = False
        self.fill_rgb = parse_colour(a.s.get("paint_fill") or "") or (128, 128, 128)
        self.fill_sw = tk.Canvas(ff, width=int(44 * ui), height=int(22 * ui),
                                 highlightthickness=1, highlightbackground="#888",
                                 cursor="hand2")
        self.fill_sw.pack(side="left")
        self.fill_sw.bind("<Button-1>", lambda e: self.fill_picker())
        ttk.Label(ff, text="#").pack(side="left", padx=(8, 0))
        self.fill_hex = tk.StringVar()
        he = ttk.Entry(ff, textvariable=self.fill_hex, width=9)
        he.pack(side="left")
        he.bind("<Return>", lambda e: self._on_fill_hex())
        he.bind("<FocusOut>", lambda e: self._on_fill_hex())
        ttk.Button(ff, text="Picker...", command=self.fill_picker).pack(side="left",
                                                                        padx=(8, 0))
        ttk.Button(ff, text="From selection",
                   command=self.fill_from_selection).pack(side="left", padx=(6, 0))
        ttk.Button(ff, text="Fill selected", command=self.fill_selected).pack(side="right")
        a.register_colour_widget(he, lambda: tuple(self.fill_rgb), self.set_fill)
        self.fill_sw.bind("<Button-3>", lambda e: a.colour_menu(
            e, lambda: tuple(self.fill_rgb), self.set_fill))
        self.win.protocol("WM_DELETE_WINDOW", a.close_tool)
        for w in self.btn_frame.winfo_children():          # Close -> tool host
            if w.winfo_class() == "TButton" and w.cget("text") == "Close":
                w.configure(command=a.close_tool)
        self.win.bind("<Control-z>", a._on_undo_key)
        self.win.bind("<Control-Z>", a._on_undo_key)
        self._show_fill()
        self.refresh()

    def refresh(self):
        a = self.app
        try:
            if a.paint_pending():
                self.pend_var.set("Unsnapshotted: " + a.paint_summary())
                st = ["!disabled"]
            else:
                self.pend_var.set("No pending edits")
                st = ["disabled"]
            self.snap_btn.state(st)
            self.revert_btn.state(st)
            self.clip_var.set(a.clip_text())
        except a.tk.TclError:
            pass

    def target_cell(self, idx):
        """Picker edits one palette cell live (double-click in the grid)."""
        a = self.app
        p = a.open_picker()
        p.owner = self
        self._picker_fill = False
        self.cell_target = idx
        cur = a.rgbs[idx] if a.rgbs[idx] is not None else (128, 128, 128)
        p.set_target(lambda rgb, hsl, i=idx: a.paint_cell_live(i, rgb), tuple(cur), None,
                     "palette index %d" % idx)
        a.status_var.set("Picker on index %d - changes apply live; Snapshot records them."
                         % idx)

    def _show_fill(self):
        self.fill_sw.configure(background=hex_of(self.fill_rgb))
        self.fill_hex.set(hex_of(self.fill_rgb).lstrip("#"))

    def set_fill(self, rgb, hsl=None):
        self.fill_rgb = tuple(rgb)
        self.app.s["paint_fill"] = hex_of(self.fill_rgb)
        self._show_fill()

    def _on_fill_hex(self):
        c = parse_colour(self.fill_hex.get())
        if c is None:
            self._show_fill()
            return
        if c != tuple(self.fill_rgb):
            self.set_fill(c)
            p = self.app.picker
            if p is not None and getattr(p, "owner", None) is self \
                    and getattr(self, "_picker_fill", False):
                self.fill_picker()

    def fill_picker(self):
        p = self.app.open_picker()
        p.owner = self
        self._picker_fill = True
        self.cell_target = None
        self.app.redraw()
        p.set_target(lambda rgb, hsl: self.set_fill(rgb, hsl), tuple(self.fill_rgb),
                     None, "Paint fill colour")

    def _target_picker(self, p):
        self._picker_fill = False
        if self.cell_target is not None:
            self.cell_target = None
            self.app.redraw()
        super()._target_picker(p)

    def fill_from_selection(self):
        a = self.app
        cols = [a.rgbs[i] for i in sorted(a.selection) if a.rgbs[i] is not None]
        if not cols:
            a.status_var.set("Select a coloured cell to take the fill colour from.")
            return
        self.set_fill(cols[0])

    def fill_selected(self):
        a = self.app
        if not a.selection:
            a.status_var.set("Select the palette cells to fill first.")
            return
        a.set_cells_colour(sorted(a.selection), self.fill_rgb, what="Fill")

    def close(self):
        self.app.close_tool()
