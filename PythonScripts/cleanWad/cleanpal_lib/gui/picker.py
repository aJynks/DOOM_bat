"""Colour picker popup and screen eyedropper."""

import math
import os

from ..colour import hex_of, hsl_to_rgb, parse_colour, rgb_round, rgb_to_hsl
from ..constants import PICKER_MODES


# ============================================================ eyedropper
class EyeDropper:
    """Full-screen screenshot overlay: click a pixel to pick it, with a
    magnifier loupe. Esc / right-click cancels."""
    LOUPE_SRC = 15
    LOUPE_PX = 9

    def __init__(self, app, callback):
        from PIL import Image, ImageGrab, ImageTk

        tk = app.tk
        self.app = app
        self.cb = callback
        x0 = y0 = 0
        try:
            if os.name == "nt":
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                x0, y0 = gm(76), gm(77)
                shot = ImageGrab.grab(all_screens=True)
            else:
                shot = ImageGrab.grab()
        except Exception as e:  # noqa: BLE001 - any grab failure
            from tkinter import messagebox
            messagebox.showerror("cleanpal", "Screen capture failed:\n%s" % e)
            self.win = None
            return
        self.shot = shot.convert("RGB")
        self.px = self.shot.load()
        w, h = self.shot.size
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.geometry("%dx%d%+d%+d" % (w, h, x0, y0))
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self.win, width=w, height=h, highlightthickness=0,
                            cursor="crosshair")
        self.cv.pack()
        self._img = ImageTk.PhotoImage(self.shot)
        self.cv.create_image(0, 0, anchor="nw", image=self._img)
        self._loupe = None
        self._Image = Image
        self._ImageTk = ImageTk
        self.cv.bind("<Motion>", self._motion)
        self.cv.bind("<ButtonPress-1>", self._pick)
        self.cv.bind("<ButtonPress-3>", lambda e: self.close())
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()
        self.win.grab_set()

    def _motion(self, ev):
        cv = self.cv
        cv.delete("loupe")
        x, y = ev.x, ev.y
        w, h = self.shot.size
        if not (0 <= x < w and 0 <= y < h):
            return
        n = self.LOUPE_SRC
        half = n // 2
        crop = self.shot.crop((x - half, y - half, x - half + n, y - half + n))
        size = n * self.LOUPE_PX
        big = crop.resize((size, size), self._Image.NEAREST)
        self._loupe = self._ImageTk.PhotoImage(big)
        lx = x + 24 if x + 24 + size < w else x - 24 - size
        ly = y + 24 if y + 24 + size + 22 < h else y - 24 - size - 22
        cv.create_rectangle(lx - 2, ly - 2, lx + size + 2, ly + size + 24,
                            fill="#202020", outline="#ffffff", tags="loupe")
        cv.create_image(lx, ly, anchor="nw", image=self._loupe, tags="loupe")
        c0 = lx + half * self.LOUPE_PX
        r0 = ly + half * self.LOUPE_PX
        cv.create_rectangle(c0, r0, c0 + self.LOUPE_PX, r0 + self.LOUPE_PX,
                            outline="#000000", width=3, tags="loupe")
        cv.create_rectangle(c0, r0, c0 + self.LOUPE_PX, r0 + self.LOUPE_PX,
                            outline="#ffffff", width=1, tags="loupe")
        rgb = self.px[x, y]
        cv.create_text(lx + 4, ly + size + 11, anchor="w", fill="#ffffff",
                       font=("Consolas", 10),
                       text="%s  %d,%d,%d" % ((hex_of(rgb),) + tuple(rgb)), tags="loupe")

    def _pick(self, ev):
        w, h = self.shot.size
        if 0 <= ev.x < w and 0 <= ev.y < h:
            rgb = tuple(self.px[ev.x, ev.y])
            self.close()
            self.cb(rgb)
        else:
            self.close()

    def close(self):
        if self.win is not None:
            try:
                self.win.grab_release()
            except self.app.tk.TclError:
                pass
            self.win.destroy()
            self.win = None


# ============================================================ colour picker
_PICKER_CACHE = {}


def _full_box_image():
    """Hue (x) x lightness (y, 100 top -> 0 bottom) at full saturation."""
    if "box" not in _PICKER_CACHE:
        from PIL import Image
        W, H = 360, 200
        im = Image.new("RGB", (W, H))
        px = im.load()
        for x in range(W):
            for y in range(H):
                px[x, y] = rgb_round(hsl_to_rgb(x * 360.0 / W, 100.0,
                                                100.0 - y * 100.0 / (H - 1)))
        grey = Image.new("RGB", (W, H))
        gp = grey.load()
        for y in range(H):
            v = int(round(255 * (1.0 - y / (H - 1.0))))
            for x in range(W):
                gp[x, y] = (v, v, v)
        _PICKER_CACHE["box"] = im
        _PICKER_CACHE["grey"] = grey
    return _PICKER_CACHE["box"], _PICKER_CACHE["grey"]


def _ring_image():
    """Hue ring (RGBA) at base size; hue runs clockwise from red at 3 o'clock."""
    if "ring" not in _PICKER_CACHE:
        from PIL import Image
        S = 320
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        px = im.load()
        c = (S - 1) / 2.0
        ro, ri = S / 2.0 - 1, S / 2.0 * 0.80
        for y in range(S):
            for x in range(S):
                dx, dy = x - c, y - c
                r = math.hypot(dx, dy)
                if ri - 1 <= r <= ro + 1:
                    a = 255
                    if r > ro:
                        a = int(255 * max(0.0, 1.0 - (r - ro)))
                    elif r < ri:
                        a = int(255 * max(0.0, 1.0 - (ri - r)))
                    h = math.degrees(math.atan2(dy, dx)) % 360.0
                    px[x, y] = rgb_round(hsl_to_rgb(h, 100.0, 50.0)) + (a,)
        _PICKER_CACHE["ring"] = im
    return _PICKER_CACHE["ring"]


def _tri_vertices(cx, cy, r):
    """tip (pure hue, right), black (top-left), white (bottom-left)."""
    return ((cx + r, cy),
            (cx + r * math.cos(math.radians(240)), cy + r * math.sin(math.radians(240))),
            (cx + r * math.cos(math.radians(120)), cy + r * math.sin(math.radians(120))))


def _bary(p, a, b, c):
    """Barycentric weights of p in triangle abc."""
    (x, y), (x1, y1), (x2, y2), (x3, y3) = p, a, b, c
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    w1 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / det
    w2 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / det
    return w1, w2, 1.0 - w1 - w2


def _tri_masks():
    """Tip weight, white weight and inside mask for the triangle at base size."""
    if "tri" not in _PICKER_CACHE:
        from PIL import Image
        S = 256
        c = (S - 1) / 2.0
        A, B, C = _tri_vertices(c, c, S / 2.0 - 1)
        tip = Image.new("L", (S, S))
        wht = Image.new("L", (S, S))
        msk = Image.new("L", (S, S))
        tp, wp, mp = tip.load(), wht.load(), msk.load()
        for y in range(S):
            for x in range(S):
                wt, wk, ww = _bary((x, y), A, B, C)
                inside = min(wt, wk, ww) >= -0.004
                wt, ww = max(wt, 0.0), max(ww, 0.0)
                tp[x, y] = int(round(min(wt, 1.0) * 255))
                wp[x, y] = int(round(min(ww, 1.0) * 255))
                mp[x, y] = 255 if inside else 0
        _PICKER_CACHE["tri"] = (tip, wht, msk)
    return _PICKER_CACHE["tri"]




class ColourPicker:
    """Non-modal picker. One colour (kept as HSL floats + RGB floats), shown
    by three interchangeable modes. Hue / saturation survive greys."""
    FINE = 0.25

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        s = app.s
        self.win = tk.Toplevel(app.root)
        self.win.title("Colour picker")
        self.win.minsize(560, 380)
        try:
            self.win.geometry(s.get("picker_geometry") or "760x470")
        except tk.TclError:
            pass
        self.pin_var = tk.BooleanVar(value=bool(s.get("picker_pin", True)))
        self._apply_pin()
        self.mode_var = tk.StringVar(value=s.get("picker_mode", PICKER_MODES[0]))
        if self.mode_var.get() not in PICKER_MODES:
            self.mode_var.set(PICKER_MODES[0])
        self.h, self.s, self.l = 0.0, 0.0, 50.0
        self.rgbf = (127.5, 127.5, 127.5)
        self.old = (128, 128, 128)
        self.target = None             # callable(rgb, hsl) or None
        self.target_label = ""
        self._drag = None
        self.active = None             # control taking arrow keys
        self._lock = False
        self._imgs = {}
        self._dropper = None
        ui = getattr(app, "ui", 1.0)
        self.ui = ui

        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        self.left = ttk.Frame(self.win, padding=8)
        self.left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(self.win, padding=(0, 8, 8, 8))
        right.grid(row=0, column=1, sticky="ns")

        top = ttk.Frame(right)
        top.pack(fill="x")
        cb = ttk.Combobox(top, textvariable=self.mode_var, values=PICKER_MODES,
                          state="readonly", width=18)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._build_mode())
        self.sw = tk.Canvas(top, width=int(76 * ui), height=int(30 * ui),
                            highlightthickness=1, highlightbackground="#888")
        self.sw.pack(side="left", padx=(8, 0))
        self.sw.bind("<Button-1>", self._on_swatch)
        self.target_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.target_var, foreground="#666").pack(anchor="w",
                                                                               pady=(4, 0))

        ff = ttk.Frame(right)
        ff.pack(fill="x", pady=(8, 0))
        self.fvars = {}
        self.fwidgets = {}
        for row, (k, hi) in enumerate((("R", 255), ("G", 255), ("B", 255))):
            self._field(ff, k, hi, row, 0)
        for row, (k, hi) in enumerate((("H", 360), ("S", 100), ("L", 100))):
            self._field(ff, k, hi, row, 2)
        hf = ttk.Frame(right)
        hf.pack(fill="x", pady=(10, 0))
        self.hvars = {}
        for row, k in enumerate(("R#", "G#", "B#")):
            ttk.Label(hf, text=k).grid(row=row, column=0, sticky="e", pady=1)
            v = tk.StringVar()
            e = ttk.Entry(hf, textvariable=v, width=5)
            e.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=1)
            e.bind("<Return>", lambda ev, kk=k: self._on_hexpart(kk))
            e.bind("<FocusOut>", lambda ev, kk=k: self._on_hexpart(kk))
            self.hvars[k] = v
        ttk.Label(hf, text="#").grid(row=3, column=0, sticky="e", pady=(4, 1))
        self.hex_var = tk.StringVar()
        self.hex_entry = ttk.Entry(hf, textvariable=self.hex_var, width=12)
        self.hex_entry.grid(row=3, column=1, columnspan=2, sticky="w", padx=(4, 0),
                            pady=(4, 1))
        self.hex_entry.bind("<Return>", lambda e: self._on_hex())
        self.hex_entry.bind("<FocusOut>", lambda e: self._on_hex(quiet=True))
        self.hex_entry.bind("<<Paste>>", lambda e: self.win.after(1, self._on_hex))
        self.hex_var.trace_add("write", lambda *a: self._on_hex(live=True))

        ef = ttk.Frame(right)
        ef.pack(fill="x", pady=(10, 0))
        ttk.Button(ef, text="Eyedropper", command=self.eyedropper).pack(side="left")
        self.last_cv = tk.Canvas(ef, width=int(22 * ui), height=int(22 * ui),
                                 highlightthickness=1, highlightbackground="#888")
        self.last_cv.pack(side="left", padx=(6, 0))
        self.last_cv.bind("<Button-1>", lambda e: self._use_last())
        self._last_pick = None
        ttk.Label(right, text="Recent").pack(anchor="w", pady=(10, 0))
        self.recent_cv = tk.Canvas(right, height=int(40 * ui), width=int(200 * ui),
                                   highlightthickness=0)
        self.recent_cv.pack(fill="x")
        self.recent_cv.bind("<Button-1>", self._on_recent)
        bf = ttk.Frame(right)
        bf.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Checkbutton(bf, text="On top", variable=self.pin_var,
                        command=self._apply_pin).pack(side="left")
        ttk.Button(bf, text="Close", command=self.close).pack(side="right")

        get = self.rgb

        def put(rgb):
            self.set_rgb(rgb)
            self._commit()
        for w in list(self.fwidgets.values()) + [self.hex_entry]:
            app.register_colour_widget(w, get, put)
        for w in hf.winfo_children():
            if w.winfo_class() == "TEntry":
                app.register_colour_widget(w, get, put)
        self.sw.bind("<Button-3>", lambda e: app.colour_menu(e, get, put))

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        for k in ("Left", "Right", "Up", "Down"):
            self.win.bind("<%s>" % k, lambda e, kk=k: self._on_arrow(e, kk, 1))
            self.win.bind("<Shift-%s>" % k, lambda e, kk=k: self._on_arrow(e, kk, 10))
        self._build_mode()
        self._draw_recent()

    # ---------------------------------------------------------- setup helpers
    def _apply_pin(self):
        try:
            self.win.attributes("-topmost", bool(self.pin_var.get()))
        except self.app.tk.TclError:
            pass

    def _field(self, parent, k, hi, row, col):
        from tkinter import ttk
        ttk.Label(parent, text=k + ":").grid(row=row, column=col, sticky="e", pady=1,
                                             padx=(8 if col else 0, 0))
        v = self.app.tk.StringVar()
        sp = ttk.Spinbox(parent, textvariable=v, from_=0, to=hi, increment=1, width=5,
                         command=lambda kk=k: self._on_field(kk))
        sp.grid(row=row, column=col + 1, sticky="w", padx=(4, 0), pady=1)
        v.trace_add("write", lambda *a, kk=k: self._on_field(kk))
        sp.bind("<Return>", lambda e: self.refresh())
        sp.bind("<FocusOut>", lambda e: (self.refresh(), self._commit()))
        sp.bind("<MouseWheel>", lambda e, kk=k: self._wheel_field(kk, e))
        sp.bind("<Shift-MouseWheel>", lambda e, kk=k: self._wheel_field(kk, e, 10))
        self.fvars[k] = v
        self.fwidgets[k] = sp

    def _build_mode(self):
        from tkinter import ttk

        for ch in self.left.winfo_children():
            ch.destroy()
        self.sliders = {}
        self.box = None
        self.wheel = None
        mode = self.mode_var.get()
        L = self.left
        L.columnconfigure(1, weight=1)
        if mode == "HSL Colour Wheel":
            L.rowconfigure(0, weight=1)
            for r in range(1, 4):
                L.rowconfigure(r, weight=0)
            self.wheel = self.app.tk.Canvas(L, highlightthickness=0, cursor="crosshair")
            self.wheel.grid(row=0, column=0, columnspan=3, sticky="nsew")
            self._bind_drag(self.wheel, "wheel")
            self.wheel.bind("<Configure>", lambda e: self._draw_wheel(full=True))
        else:
            keys = "RGB" if mode == "RGB Sliders" else "HSL"
            for r, k in enumerate(keys):
                L.rowconfigure(r, weight=0)
                ttk.Label(L, text=k + ":").grid(row=r, column=0, sticky="w")
                c = self.app.tk.Canvas(L, height=int(26 * self.ui), highlightthickness=0,
                                       cursor="hand2")
                c.grid(row=r, column=1, sticky="ew", padx=(6, 0), pady=3)
                c.bind("<Configure>", lambda e, kk=k: self._draw_slider(kk))
                self._bind_drag(c, k)
                c.bind("<MouseWheel>", lambda e, kk=k: self._wheel_slider(kk, e, 1))
                c.bind("<Shift-MouseWheel>", lambda e, kk=k: self._wheel_slider(kk, e, 10))
                self.sliders[k] = c
            L.rowconfigure(3, weight=1)
            self.box = self.app.tk.Canvas(L, highlightthickness=1,
                                          highlightbackground="#555", cursor="crosshair")
            self.box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
            self.box.bind("<Configure>", lambda e: self._draw_box(full=True))
            self._bind_drag(self.box, "box")
        self.s_app_mode()
        self.refresh()

    def s_app_mode(self):
        self.app.s["picker_mode"] = self.mode_var.get()

    # ---------------------------------------------------------- state
    def rgb(self):
        return rgb_round(self.rgbf)

    def hsl(self):
        return [self.h, self.s, self.l]

    def _set_hsl(self, h, s, l, emit=True):
        self.h = h % 360.0
        self.s = min(max(s, 0.0), 100.0)
        self.l = min(max(l, 0.0), 100.0)
        self.rgbf = hsl_to_rgb(self.h, self.s, self.l)
        self.refresh()
        if emit:
            self._emit()

    def set_rgb(self, rgb, emit=True, keep_hue=False):
        """New colour from RGB. Hue (and saturation for black / white) are
        kept when the colour can't define them."""
        r, g, b = (float(v) for v in rgb)
        h, s, l = rgb_to_hsl(r, g, b)
        if max(r, g, b) - min(r, g, b) < 1e-9 or keep_hue:
            h = self.h
        if l <= 1e-9 or l >= 100.0 - 1e-9:
            s = self.s
        self.h, self.s, self.l = h, s, l
        self.rgbf = (r, g, b)
        self.refresh()
        if emit:
            self._emit()

    def set_target(self, cb, rgb, hsl=None, label=""):
        """Edit another colour (a ramp node etc.) - no change is sent."""
        self.target = cb
        self.target_label = label
        self.target_var.set(("Editing: " + label) if label else "No target - pick freely")
        rgb = tuple(rgb)
        self.old = rgb
        if hsl and rgb_round(hsl_to_rgb(*hsl)) == rgb:
            self.h, self.s, self.l = hsl[0] % 360.0, hsl[1], hsl[2]
            self.rgbf = hsl_to_rgb(*hsl)
        else:
            self.set_rgb(rgb, emit=False)
        self.refresh()

    def _emit(self):
        if self.target is not None:
            self.target(self.rgb(), self.hsl())

    def _commit(self):
        """End of a gesture: remember the colour in Recent."""
        self.app.add_recent(self.rgb())
        self._draw_recent()

    # ---------------------------------------------------------- drawing
    def refresh(self):
        self._lock = True
        try:
            r, g, b = self.rgb()
            vals = {"R": r, "G": g, "B": b, "H": int(round(self.h)) % 360,
                    "S": int(round(self.s)), "L": int(round(self.l))}
            for k, v in vals.items():
                w = self.fwidgets[k]
                if self.win.focus_get() is not w or not self._typed_ok(k):
                    self.fvars[k].set(str(v))
            for k, v in (("R#", r), ("G#", g), ("B#", b)):
                self.hvars[k].set("%02X" % v)
            if self.win.focus_get() is not self.hex_entry \
                    or parse_colour(self.hex_var.get()) != self.rgb():
                self.hex_var.set(hex_of(self.rgb())[1:])
        finally:
            self._lock = False
        sw = self.sw
        sw.delete("all")
        W, H = int(sw.cget("width")), int(sw.cget("height"))
        sw.create_rectangle(0, 0, W // 2, H, fill=hex_of(self.rgb()), outline="")
        sw.create_rectangle(W // 2, 0, W, H, fill=hex_of(self.old), outline="")
        for k in self.sliders:
            self._draw_slider(k)
        if self.box is not None:
            self._draw_box(full=self.mode_var.get() == "HSL Sliders")
        if self.wheel is not None:
            self._draw_wheel()

    def _typed_ok(self, k):
        try:
            return int(float(self.fvars[k].get())) == int(round(
                {"R": self.rgbf[0], "G": self.rgbf[1], "B": self.rgbf[2],
                 "H": self.h, "S": self.s, "L": self.l}[k]))
        except ValueError:
            return False

    def _track(self, k):
        """(function t -> rgb float, value 0..1) for slider k."""
        r, g, b = self.rgbf
        h, s, l = self.h, self.s, self.l
        if k == "R":
            return (lambda t: (t * 255, g, b)), r / 255.0
        if k == "G":
            return (lambda t: (r, t * 255, b)), g / 255.0
        if k == "B":
            return (lambda t: (r, g, t * 255)), b / 255.0
        if k == "H":
            return (lambda t: hsl_to_rgb(t * 360, 100, 50)), h / 360.0
        if k == "S":
            return (lambda t: hsl_to_rgb(h, t * 100, l)), s / 100.0
        return (lambda t: hsl_to_rgb(h, s, t * 100)), l / 100.0

    def _slider_geom(self, c):
        W, H = max(c.winfo_width(), 20), max(c.winfo_height(), 10)
        pad = H // 2
        return pad, W - pad, H

    def _draw_slider(self, k):
        from PIL import Image, ImageTk

        c = self.sliders.get(k)
        if c is None:
            return
        x0, x1, H = self._slider_geom(c)
        if x1 - x0 < 4:
            return
        f, v = self._track(k)
        strip = Image.new("RGB", (128, 1))
        strip.putdata([rgb_round(f(i / 127.0)) for i in range(128)])
        th = max(6, H // 3)
        img = strip.resize((int(x1 - x0), th), Image.BILINEAR)
        tki = ImageTk.PhotoImage(img)
        self._imgs["sl" + k] = tki
        c.delete("all")
        c.create_image(x0, (H - th) // 2, anchor="nw", image=tki)
        x = x0 + v * (x1 - x0)
        rad = H / 2.0 - 2
        c.create_oval(x - rad, H / 2 - rad, x + rad, H / 2 + rad, outline="#000000",
                      width=3)
        c.create_oval(x - rad, H / 2 - rad, x + rad, H / 2 + rad, outline="#ffffff",
                      width=2, fill=hex_of(self.rgb()))

    def _draw_box(self, full=False):
        from PIL import Image, ImageTk

        c = self.box
        W, H = c.winfo_width(), c.winfo_height()
        if W < 10 or H < 10:
            return
        hsl_mode = self.mode_var.get() == "HSL Sliders"
        key = ("box", W, H, round(self.s, 1) if hsl_mode else None)
        if full or self._imgs.get("boxkey") != key:
            fb, grey = _full_box_image()
            base = Image.blend(grey, fb, self.s / 100.0) if hsl_mode else fb
            self._imgs["box"] = ImageTk.PhotoImage(base.resize((W, H), Image.BILINEAR))
            self._imgs["boxkey"] = key
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._imgs["box"])
        x = self.h / 360.0 * (W - 1)
        y = (1.0 - self.l / 100.0) * (H - 1)
        self._crosshair(c, x, y)

    def _crosshair(self, c, x, y):
        g, n = 4, 10
        for col, w in (("#000000", 3), ("#ffffff", 1)):
            c.create_line(x - g - n, y, x - g, y, fill=col, width=w)
            c.create_line(x + g, y, x + g + n, y, fill=col, width=w)
            c.create_line(x, y - g - n, x, y - g, fill=col, width=w)
            c.create_line(x, y + g, x, y + g + n, fill=col, width=w)

    def _wheel_geom(self):
        c = self.wheel
        W, H = c.winfo_width(), c.winfo_height()
        S = max(min(W, H) - 8, 40)
        cx, cy = W / 2.0, H / 2.0
        ro = S / 2.0
        ri = ro * 0.80
        rt = ri * 0.96
        return cx, cy, ro, ri, rt, S

    def _draw_wheel(self, full=False):
        from PIL import Image, ImageChops, ImageTk

        c = self.wheel
        if c is None or c.winfo_width() < 50:
            return
        cx, cy, ro, ri, rt, S = self._wheel_geom()
        key = ("ring", S)
        if full or self._imgs.get("ringkey") != key:
            self._imgs["ring"] = ImageTk.PhotoImage(
                _ring_image().resize((int(S), int(S)), Image.BILINEAR))
            self._imgs["ringkey"] = key
        tkey = ("tri", int(2 * rt), round(self.h, 1))
        if full or self._imgs.get("trikey") != tkey:
            tip, wht, msk = _tri_masks()
            pr, pg, pb = hsl_to_rgb(self.h, 100, 50)
            bands = [ImageChops.add(tip.point(lambda v, p=p: v * p / 255.0), wht)
                     for p in (pr, pg, pb)]
            im = Image.merge("RGB", bands)
            im.putalpha(msk)
            sz = max(int(2 * rt), 8)
            self._imgs["tri"] = ImageTk.PhotoImage(im.resize((sz, sz), Image.BILINEAR))
            self._imgs["trikey"] = tkey
        c.delete("all")
        c.create_image(cx, cy, image=self._imgs["ring"])
        c.create_image(cx, cy, image=self._imgs["tri"])
        # ring marker
        a = math.radians(self.h)
        rm = (ro + ri) / 2.0
        mx, my = cx + rm * math.cos(a), cy + rm * math.sin(a)
        rr = (ro - ri) / 2.0 - 1
        c.create_oval(mx - rr, my - rr, mx + rr, my + rr, outline="#000000", width=3)
        c.create_oval(mx - rr, my - rr, mx + rr, my + rr, outline="#ffffff", width=2)
        # triangle marker
        px, py = self._tri_point()
        self._crosshair(c, px, py)
        c.create_text(8, c.winfo_height() - 8, anchor="sw", fill="#888",
                      font=("Consolas", 10),
                      text="H: %d\nS: %d\nL: %d" % (round(self.h) % 360, round(self.s),
                                                    round(self.l)))

    def _tri_weights(self):
        r, g, b = self.rgbf
        mx, mn = max(r, g, b), min(r, g, b)
        wc = (mx - mn) / 255.0
        ww = mn / 255.0
        return wc, ww, max(0.0, 1.0 - wc - ww)

    def _tri_point(self):
        cx, cy, ro, ri, rt, S = self._wheel_geom()
        A, B, C = _tri_vertices(cx, cy, rt)
        wc, ww, wk = self._tri_weights()
        return (wc * A[0] + wk * B[0] + ww * C[0], wc * A[1] + wk * B[1] + ww * C[1])

    # ---------------------------------------------------------- dragging
    def _bind_drag(self, c, ctl):
        c.bind("<ButtonPress-1>", lambda e: self._press(e, ctl))
        c.bind("<B1-Motion>", lambda e: self._motion(e, ctl))
        c.bind("<ButtonRelease-1>", lambda e: self._release(e, ctl))

    def _press(self, ev, ctl):
        self.win.focus_set()
        if ctl == "wheel":
            cx, cy, ro, ri, rt, S = self._wheel_geom()
            r = math.hypot(ev.x - cx, ev.y - cy)
            ctl = "ring" if r >= ri - 2 else "tri"
        self.active = ctl
        self._drag = {"ctl": ctl, "vx": float(ev.x), "vy": float(ev.y),
                      "lx": ev.x, "ly": ev.y, "ax": float(ev.x), "ay": float(ev.y),
                      "axis": None}
        self._apply_point(ctl, ev.x, ev.y, ev.widget)

    def _motion(self, ev, ctl):
        d = self._drag
        if not d:
            return
        f = self.FINE if ev.state & 0x0001 else 1.0
        d["vx"] += (ev.x - d["lx"]) * f
        d["vy"] += (ev.y - d["ly"]) * f
        d["lx"], d["ly"] = ev.x, ev.y
        x, y = d["vx"], d["vy"]
        if ev.state & 0x0004:                      # Ctrl: lock to one axis
            if d["axis"] is None and abs(x - d["ax"]) + abs(y - d["ay"]) > 3:
                d["axis"] = "x" if abs(x - d["ax"]) >= abs(y - d["ay"]) else "y"
            if d["axis"] == "x":
                y = d["ay"]
            elif d["axis"] == "y":
                x = d["ax"]
        else:
            d["axis"] = None
            d["ax"], d["ay"] = x, y
        self._apply_point(d["ctl"], x, y, ev.widget)

    def _release(self, _ev, _ctl):
        if self._drag:
            self._drag = None
            self._commit()

    def _apply_point(self, ctl, x, y, widget):
        if ctl in ("R", "G", "B", "H", "S", "L"):
            x0, x1, _H = self._slider_geom(widget)
            t = min(max((x - x0) / max(x1 - x0, 1), 0.0), 1.0)
            self._set_channel(ctl, t)
        elif ctl == "box":
            W, H = widget.winfo_width(), widget.winfo_height()
            hh = min(max(x / max(W - 1, 1), 0.0), 1.0) * 360.0
            ll = (1.0 - min(max(y / max(H - 1, 1), 0.0), 1.0)) * 100.0
            if hh >= 360.0:
                hh = 359.999
            if self.mode_var.get() == "RGB Sliders":
                self._set_hsl(hh, 100.0, ll)
            else:
                self._set_hsl(hh, self.s, ll)
        elif ctl == "ring":
            cx, cy, ro, ri, rt, S = self._wheel_geom()
            hh = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
            wc, ww, wk = self._tri_weights()
            pr = hsl_to_rgb(hh, 100, 50)
            self.h = hh
            self.set_rgb(tuple(wc * p + ww * 255.0 for p in pr), keep_hue=True)
        elif ctl == "tri":
            cx, cy, ro, ri, rt, S = self._wheel_geom()
            A, B, C = _tri_vertices(cx, cy, rt)
            wc, wk, ww = _bary((x, y), A, B, C)
            wc, wk, ww = max(wc, 0.0), max(wk, 0.0), max(ww, 0.0)
            tot = wc + wk + ww or 1.0
            wc, ww = wc / tot, ww / tot
            pr = hsl_to_rgb(self.h, 100, 50)
            self.set_rgb(tuple(min(255.0, wc * p + ww * 255.0) for p in pr), keep_hue=True)

    def _set_channel(self, k, t):
        if k in "RGB":
            v = list(self.rgbf)
            v["RGB".index(k)] = t * 255.0
            self.set_rgb(v)
        elif k == "H":
            self._set_hsl(min(t, 0.99999) * 360.0, self.s, self.l)
        elif k == "S":
            self._set_hsl(self.h, t * 100.0, self.l)
        else:
            self._set_hsl(self.h, self.s, t * 100.0)

    def _channel_value(self, k):
        return {"R": self.rgbf[0], "G": self.rgbf[1], "B": self.rgbf[2],
                "H": self.h, "S": self.s, "L": self.l}[k]

    def _step_channel(self, k, n):
        hi = {"R": 255.0, "G": 255.0, "B": 255.0, "H": 360.0, "S": 100.0, "L": 100.0}[k]
        v = round(self._channel_value(k)) + n
        if k == "H":
            v %= 360
        v = min(max(v, 0.0), hi)
        self._set_channel(k, v / hi if k != "H" else (v % 360) / 360.0)

    def _wheel_slider(self, k, ev, n):
        self.active = k
        self._step_channel(k, n if ev.delta > 0 else -n)
        self._commit()
        return "break"

    def _on_arrow(self, ev, key, n):
        cls = ev.widget.winfo_class() if hasattr(ev.widget, "winfo_class") else ""
        if cls in ("TEntry", "Entry", "TSpinbox", "Spinbox", "TCombobox"):
            return
        ctl = self.active
        if ctl is None:
            return
        sign = 1 if key in ("Right", "Up") else -1
        if ctl in ("R", "G", "B", "H", "S", "L"):
            self._step_channel(ctl, sign * n)
        elif ctl in ("box", "tri"):
            if key in ("Left", "Right"):
                if ctl == "box":
                    self._step_channel("H", sign * n)
                else:
                    self._step_channel("S", sign * n)
            else:
                self._step_channel("L", sign * n)
        elif ctl == "ring":
            self._step_channel("H", sign * n)
        self._commit()
        return "break"

    # ---------------------------------------------------------- fields
    def _on_field(self, k):
        if self._lock:
            return
        try:
            v = float(self.fvars[k].get())
        except ValueError:
            return
        hi = {"R": 255, "G": 255, "B": 255, "H": 360, "S": 100, "L": 100}[k]
        if not 0 <= v <= hi or abs(v - round(self._channel_value(k))) < 1e-9:
            return
        if k == "H":
            self._set_hsl(v % 360.0, self.s, self.l)
        else:
            self._set_channel(k, v / hi)

    def _wheel_field(self, k, ev, n=1):
        self._step_channel(k, n if ev.delta > 0 else -n)
        self._commit()
        return "break"

    def _on_hexpart(self, k):
        try:
            v = int(self.hvars[k].get().strip().lstrip("#"), 16)
        except ValueError:
            self.refresh()
            return
        if 0 <= v <= 255:
            rgb = list(self.rgb())
            rgb[("R#", "G#", "B#").index(k)] = v
            self.set_rgb(rgb)
            self._commit()
        else:
            self.refresh()

    def _on_hex(self, live=False, quiet=False):
        if self._lock:
            return
        txt = self.hex_var.get().strip()
        if live and not (len(txt.lstrip("#")) == 6 or "," in txt):
            return                                 # wait for a full value
        c = parse_colour(txt)
        if c is None:
            if not live and not quiet:
                self.refresh()
            return
        if c != self.rgb():
            self.set_rgb(c)
        if not live:
            self._commit()

    # ---------------------------------------------------------- swatches
    def _on_swatch(self, ev):
        W = int(self.sw.cget("width"))
        if ev.x >= W // 2:                         # old half: revert
            self.set_rgb(self.old)
            self._commit()

    def _draw_recent(self):
        c = self.recent_cv
        c.delete("all")
        sz = int(18 * self.ui)
        for k, hx in enumerate(self.app.s.get("recent_colours", [])[:16]):
            x = (k % 8) * (sz + 3)
            y = (k // 8) * (sz + 3)
            c.create_rectangle(x, y, x + sz, y + sz, fill=hx, outline="#777")

    def _on_recent(self, ev):
        sz = int(18 * self.ui) + 3
        k = (ev.y // sz) * 8 + ev.x // sz
        rec = self.app.s.get("recent_colours", [])
        if ev.x // sz < 8 and 0 <= k < len(rec):
            c = parse_colour(rec[k])
            if c:
                self.set_rgb(c)

    def eyedropper(self):
        self._dropper = EyeDropper(self.app, self._picked)

    def _picked(self, rgb):
        self._last_pick = rgb
        self.last_cv.configure(background=hex_of(rgb))
        self.set_rgb(rgb)
        self._commit()

    def _use_last(self):
        if self._last_pick:
            self.set_rgb(self._last_pick)
            self._commit()

    def close(self):
        try:
            self.app.s["picker_geometry"] = self.win.geometry()
        except self.app.tk.TclError:
            pass
        self.app.s["picker_pin"] = bool(self.pin_var.get())
        self.app.s["picker_mode"] = self.mode_var.get()
        self.app.picker = None
        self.win.destroy()
