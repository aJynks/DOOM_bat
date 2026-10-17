"""Scratch palette window."""

import os

from ..colour import hex_of, parse_colour, parse_colour_list
from ..palette_io import read_colour_file
from .picker import EyeDropper


# ============================================================ scratch palette
class ScratchPalette:
    """Temporary swatches in named sets. Click = send to the picker; drag
    onto the grid / a ramp node / the picker; drag to reorder."""

    def __init__(self, app):
        from tkinter import ttk

        tk = app.tk
        self.app = app
        s = app.s
        ui = getattr(app, "ui", 1.0)
        self.ui = ui
        sets = s.get("scratch_sets")
        if not isinstance(sets, dict) or not sets:
            sets = {"Scratch": []}
        s["scratch_sets"] = sets
        if s.get("scratch_current") not in sets:
            s["scratch_current"] = next(iter(sets))
        self.sel = set()
        self._anchor = None
        self._drag = None
        self._cells = []

        self.win = tk.Toplevel(app.root)
        self.win.title("Scratch palette")
        self.win.minsize(330, 240)
        try:
            self.win.geometry(s.get("scratch_geometry") or "420x320")
        except tk.TclError:
            pass
        self.pin_var = tk.BooleanVar(value=bool(s.get("scratch_pin", True)))
        self._apply_pin()
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(2, weight=1)

        tf = ttk.Frame(self.win, padding=(8, 8, 8, 0))
        tf.grid(row=0, column=0, sticky="ew")
        self.set_var = tk.StringVar(value=s["scratch_current"])
        self.set_cb = ttk.Combobox(tf, textvariable=self.set_var, state="readonly",
                                   width=18, values=list(sets))
        self.set_cb.pack(side="left")
        self.set_cb.bind("<<ComboboxSelected>>", lambda e: self._on_set())
        ttk.Button(tf, text="New", width=6, command=self.new_set).pack(side="left",
                                                                      padx=(6, 0))
        ttk.Button(tf, text="Rename", width=7, command=self.rename_set).pack(side="left",
                                                                            padx=(4, 0))
        ttk.Button(tf, text="Delete", width=7, command=self.delete_set).pack(side="left",
                                                                            padx=(4, 0))
        bf = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        bf.grid(row=1, column=0, sticky="ew")
        ttk.Button(bf, text="+ Picker", command=self.add_picker).pack(side="left")
        ttk.Button(bf, text="+ Selected", command=self.add_selected).pack(side="left",
                                                                         padx=(4, 0))
        ttk.Button(bf, text="Eyedropper", command=self.eyedropper).pack(side="left",
                                                                       padx=(4, 0))
        ttk.Button(bf, text="Fill selected", command=self.fill_selected).pack(
            side="left", padx=(4, 0))
        self.cv = tk.Canvas(self.win, highlightthickness=1, highlightbackground="#888",
                            bg="#2a2a2a")
        self.cv.grid(row=2, column=0, sticky="nsew", padx=8, pady=(6, 0))
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<ButtonPress-3>", self._right)
        self.cv.bind("<Motion>", self._hover)
        self.info_var = tk.StringVar(value="")
        ttk.Label(self.win, textvariable=self.info_var, font=("Consolas", 9)).grid(
            row=3, column=0, sticky="w", padx=8)
        ff = ttk.Frame(self.win, padding=8)
        ff.grid(row=4, column=0, sticky="ew")
        ttk.Button(ff, text="Import...", command=self.import_file).pack(side="left")
        ttk.Button(ff, text="Export...", command=self.export_file).pack(side="left",
                                                                       padx=(4, 0))
        ttk.Checkbutton(ff, text="On top", variable=self.pin_var,
                        command=self._apply_pin).pack(side="left", padx=(8, 0))
        ttk.Button(ff, text="Close", command=self.close).pack(side="right")

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Delete>", lambda e: self.delete_selected())
        self.win.bind("<BackSpace>", lambda e: self.delete_selected())
        self.win.bind("<Control-c>", lambda e: self.copy())
        self.win.bind("<Control-C>", lambda e: self.copy())
        self.win.bind("<Control-v>", lambda e: self.paste())
        self.win.bind("<Control-V>", lambda e: self.paste())
        self.win.bind("<Control-a>", lambda e: self._select_all())
        self.win.bind("<Escape>", lambda e: self.close())

    # ---------------------------------------------------------- data
    def _apply_pin(self):
        try:
            self.win.attributes("-topmost", bool(self.pin_var.get()))
        except self.app.tk.TclError:
            pass

    def swatches(self):
        return self.app.s["scratch_sets"][self.app.s["scratch_current"]]

    def colours(self):
        out = []
        for hx in self.swatches():
            c = parse_colour(hx)
            out.append(c if c else (0, 0, 0))
        return out

    def add_colours(self, cols):
        sw = self.swatches()
        for c in cols:
            sw.append(hex_of(c))
        self.sel = set(range(len(sw) - len(cols), len(sw)))
        self.draw()
        self.app.status_var.set("Scratch: added %d colour(s)." % len(cols))

    # ---------------------------------------------------------- sets
    def _sets(self):
        return self.app.s["scratch_sets"]

    def _refresh_sets(self):
        self.set_cb.configure(values=list(self._sets()))
        self.set_var.set(self.app.s["scratch_current"])
        self.sel = set()
        self.draw()

    def _on_set(self):
        self.app.s["scratch_current"] = self.set_var.get()
        self._refresh_sets()

    def _ask_name(self, title, initial=""):
        from tkinter import simpledialog
        name = simpledialog.askstring("cleanpal", title, initialvalue=initial,
                                      parent=self.win)
        if name is None:
            return None
        name = name.strip()
        return name or None

    def _unique(self, name):
        base, k = name, 2
        while name in self._sets():
            name = "%s %d" % (base, k)
            k += 1
        return name

    def new_set(self):
        name = self._ask_name("Name for the new set:")
        if not name:
            return
        name = self._unique(name)
        self._sets()[name] = []
        self.app.s["scratch_current"] = name
        self._refresh_sets()

    def rename_set(self):
        old = self.app.s["scratch_current"]
        name = self._ask_name("Rename set:", old)
        if not name or name == old:
            return
        name = self._unique(name)
        sets = self._sets()
        self.app.s["scratch_sets"] = {(name if k == old else k): v for k, v in sets.items()}
        self.app.s["scratch_current"] = name
        self._refresh_sets()

    def delete_set(self):
        from tkinter import messagebox
        cur = self.app.s["scratch_current"]
        if not messagebox.askyesno("cleanpal", "Delete the set '%s'?" % cur,
                                   parent=self.win):
            return
        sets = self._sets()
        del sets[cur]
        if not sets:
            sets["Scratch"] = []
        self.app.s["scratch_current"] = next(iter(sets))
        self._refresh_sets()

    # ---------------------------------------------------------- drawing
    def _cell(self):
        return int(26 * self.ui), 3

    def draw(self):
        c = self.cv
        c.delete("all")
        sz, gap = self._cell()
        W = max(c.winfo_width(), sz + 10)
        cols = max(1, (W - 6) // (sz + gap))
        pal = set()
        if self.app.rgbs is not None:
            pal = {tuple(x) for x in self.app.rgbs if x is not None}
        self._cells = []
        cs = self.colours()
        for k, col in enumerate(cs):
            x = 4 + (k % cols) * (sz + gap)
            y = 4 + (k // cols) * (sz + gap)
            c.create_rectangle(x, y, x + sz, y + sz, fill=hex_of(col), outline="#000000")
            fg = "#000000" if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] > 140 \
                else "#ffffff"
            if col in pal:
                r = max(2, sz // 8)
                c.create_oval(x + sz - 3 - 2 * r, y + 3, x + sz - 3, y + 3 + 2 * r,
                              fill=fg, outline="")
            if k in self.sel:
                c.create_rectangle(x - 1, y - 1, x + sz + 1, y + sz + 1, outline="#00ffff",
                                   width=2)
            self._cells.append((x, y, sz, k))
        if not cs:
            c.create_text(10, 16, anchor="w", fill="#bbbbbb",
                          text="Empty - + Picker, + Selected, Eyedropper, Ctrl+V,\n"
                               "or drag cells here from the main grid.")
        self._cols = cols

    def _at(self, x, y):
        for cx, cy, sz, k in self._cells:
            if cx <= x < cx + sz and cy <= y < cy + sz:
                return k
        return None

    def _insert_at(self, x, y):
        sz, gap = self._cell()
        col = int(max(0, x - 4 + (sz + gap) / 2) // (sz + gap))
        row = int(max(0, y - 4) // (sz + gap))
        return min(row * self._cols + min(col, self._cols), len(self.swatches()))

    # ---------------------------------------------------------- mouse
    def _hover(self, ev):
        k = self._at(ev.x, ev.y)
        if k is None:
            self.info_var.set("")
            return
        col = self.colours()[k]
        t = "%s   %d,%d,%d" % ((hex_of(col),) + tuple(col))
        if self.app.rgbs is not None:
            hits = [i for i, x in enumerate(self.app.rgbs) if x is not None
                    and tuple(x) == col]
            if hits:
                t += "   in palette at %s" % ", ".join(str(i) for i in hits[:6])
        self.info_var.set(t)

    def _press(self, ev):
        self.win.focus_set()
        k = self._at(ev.x, ev.y)
        shift, ctrl = ev.state & 0x0001, ev.state & 0x0004
        if k is None:
            if not (shift or ctrl):
                self.sel = set()
                self.draw()
            self._drag = None
            return
        if shift and self._anchor is not None:
            a, b = sorted((self._anchor, k))
            self.sel |= set(range(a, b + 1))
        elif ctrl:
            self.sel ^= {k}
            self._anchor = k
        elif k not in self.sel:
            self.sel = {k}
            self._anchor = k
        self._drag = {"k": k, "x": ev.x, "y": ev.y, "moved": False,
                      "plain": not (shift or ctrl)}
        self.draw()

    def _motion(self, ev):
        d = self._drag
        if d and abs(ev.x - d["x"]) + abs(ev.y - d["y"]) > 4:
            d["moved"] = True
            self.cv.configure(cursor="fleur")

    def _release(self, ev):
        d = self._drag
        self._drag = None
        self.cv.configure(cursor="")
        if not d:
            return
        cols = self.colours()
        rgb = cols[d["k"]]
        if not d["moved"]:
            if d["plain"]:
                self.sel = {d["k"]}
                self._anchor = d["k"]
                self.draw()
                self.send_to_picker(rgb)
            return
        w = self.win.winfo_containing(ev.x_root, ev.y_root)
        a = self.app
        if w is self.cv:
            self._reorder(self._insert_at(ev.x, ev.y))
        elif w is a.canvas:
            a.drop_colour_on_grid(ev.x_root, ev.y_root, rgb)
            self.draw()
        elif a.ramp is not None and w is a.ramp.bar:
            a.ramp.drop_colour(ev.x_root, rgb)
        elif a.picker is not None and w is not None and \
                str(w).startswith(str(a.picker.win)):
            a.picker.set_rgb(rgb)
            a.picker._commit()

    def _reorder(self, pos):
        sw = self.swatches()
        moving = sorted(self.sel) if self.sel else []
        if not moving:
            return
        items = [sw[k] for k in moving]
        before = sum(1 for k in moving if k < pos)
        rest = [x for k, x in enumerate(sw) if k not in self.sel]
        pos -= before
        sw[:] = rest[:pos] + items + rest[pos:]
        self.sel = set(range(pos, pos + len(items)))
        self.draw()

    def _right(self, ev):
        a = self.app
        k = self._at(ev.x, ev.y)
        menu = a.tk.Menu(self.cv, tearoff=0)
        clip = parse_colour_list(a._clip_text(self.win))
        if k is not None:
            if k not in self.sel:
                self.sel = {k}
                self._anchor = k
                self.draw()
            col = self.colours()[k]
            menu.add_command(label="Copy hex  (%s)" % hex_of(col),
                             command=lambda: a._copy_text(self.win, hex_of(col), "hex"))
            menu.add_command(label="Copy R,G,B",
                             command=lambda: a._copy_text(self.win, "%d,%d,%d" % col,
                                                          "R,G,B"))
            if len(self.sel) > 1:
                menu.add_command(label="Copy %d selected as hex" % len(self.sel),
                                 command=self.copy)
            menu.add_separator()
        menu.add_command(
            label=("Paste %d colour(s) here" % len(clip)) if clip else "Paste colour(s)",
            state="normal" if clip else "disabled",
            command=lambda: self._paste_at(clip, k + 1 if k is not None else None))
        if k is not None:
            menu.add_command(label="Send to picker", command=lambda: self.send_to_picker(
                self.colours()[k]))
            menu.add_separator()
            n = len(self.sel)
            menu.add_command(label="Remove" if n <= 1 else "Remove %d selected" % n,
                             command=self.delete_selected)
        a._popup(menu, ev)

    def _paste_at(self, cols, pos):
        if not cols:
            return
        sw = self.swatches()
        if pos is None:
            pos = len(sw)
        sw[pos:pos] = [hex_of(c) for c in cols]
        self.sel = set(range(pos, pos + len(cols)))
        self.draw()
        self.app.status_var.set("Scratch: pasted %d colour(s)." % len(cols))

    def _select_all(self):
        self.sel = set(range(len(self.swatches())))
        self.draw()

    def delete_selected(self):
        if not self.sel:
            return
        sw = self.swatches()
        sw[:] = [x for k, x in enumerate(sw) if k not in self.sel]
        self.sel = set()
        self.draw()

    # ---------------------------------------------------------- actions
    def send_to_picker(self, rgb):
        a = self.app
        p = a.picker
        if p is None:
            if a.ramp is not None:
                a.ramp.open_picker()
            else:
                a.open_picker()
            p = a.picker
        p.set_rgb(rgb)
        p._commit()

    def add_picker(self):
        if self.app.picker is None:
            self.app.status_var.set("Open the colour picker first (Picker... in the "
                                    "Paint tools, or click a swatch).")
            return
        self.add_colours([self.app.picker.rgb()])

    def add_selected(self):
        a = self.app
        if a.rgbs is None:
            return
        cols = [a.rgbs[i] for i in sorted(a.selection) if a.rgbs[i] is not None]
        if not cols:
            a.status_var.set("Select coloured cells in the main grid first.")
            return
        self.add_colours(cols)

    def eyedropper(self):
        EyeDropper(self.app, lambda rgb: self.add_colours([rgb]))

    def fill_selected(self):
        a = self.app
        if not self.sel:
            a.status_var.set("Pick a scratch swatch first.")
            return
        rgb = self.colours()[min(self.sel)]
        if not a.selection:
            a.status_var.set("Select the palette cells to fill first.")
            return
        a.set_cells_colour(sorted(a.selection), rgb)
        self.draw()

    def copy(self):
        cols = self.colours()
        pick = sorted(self.sel) if self.sel else range(len(cols))
        txt = "\n".join(hex_of(cols[k]) for k in pick)
        if txt:
            self.win.clipboard_clear()
            self.win.clipboard_append(txt)
            self.app.status_var.set("Copied %d colour(s)." % len(list(pick)))

    def paste(self):
        try:
            txt = self.win.clipboard_get()
        except self.app.tk.TclError:
            return
        cols = parse_colour_list(txt)
        if cols:
            self.add_colours(cols)

    def import_file(self):
        from tkinter import filedialog, messagebox

        p = filedialog.askopenfilename(
            parent=self.win, title="Import colours",
            initialdir=self.app.s.get("scratch_dir") or None,
            filetypes=[("Colour lists", "*.txt *.hex *.gpl *.pal"),
                       ("Hex text", "*.txt *.hex"), ("GIMP palette", "*.gpl"),
                       ("Palette", "*.pal"), ("All files", "*.*")])
        if not p:
            return
        try:
            cols = read_colour_file(p)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not import:\n%s\n\n%s" % (p, e),
                                 parent=self.win)
            return
        name = self._unique(os.path.splitext(os.path.basename(p))[0] or "Imported")
        self._sets()[name] = [hex_of(c) for c in cols]
        self.app.s["scratch_current"] = name
        self.app.s["scratch_dir"] = os.path.dirname(p)
        self._refresh_sets()
        self.app.status_var.set("Imported %d colours as set '%s'." % (len(cols), name))

    def export_file(self):
        from tkinter import filedialog, messagebox

        p = filedialog.asksaveasfilename(
            parent=self.win, title="Export set",
            initialdir=self.app.s.get("scratch_dir") or None,
            initialfile=self.app.s["scratch_current"] + ".gpl",
            defaultextension=".gpl",
            filetypes=[("GIMP palette", "*.gpl"), ("Hex text", "*.txt")])
        if not p:
            return
        cols = self.colours()
        try:
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                if p.lower().endswith(".gpl"):
                    fh.write("GIMP Palette\nName: %s\nColumns: 16\n#\n"
                             % self.app.s["scratch_current"])
                    for c in cols:
                        fh.write("%3d %3d %3d\t%s\n" % (c + (hex_of(c),)))
                else:
                    fh.write("\n".join(hex_of(c) for c in cols) + "\n")
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not export:\n%s" % e, parent=self.win)
            return
        self.app.s["scratch_dir"] = os.path.dirname(p)
        self.app.status_var.set("Exported %d colours to %s" % (len(cols), p))

    def close(self):
        try:
            self.app.s["scratch_geometry"] = self.win.geometry()
        except self.app.tk.TclError:
            pass
        self.app.s["scratch_pin"] = bool(self.pin_var.get())
        self.app.scratch = None
        self.win.destroy()
