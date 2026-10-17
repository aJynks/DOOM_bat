"""Right-click menus for text fields and colour swatches (App mixin)."""

from ..colour import hex_of, parse_colour


class MenusMixin:
    """Right-click menus for text fields and colour swatches."""

    def register_colour_widget(self, w, getter, setter):
        """Give a widget's right-click menu colour items. getter() -> rgb or
        None; setter(rgb) applies a pasted colour."""
        self._colour_ctx[str(w)] = (getter, setter)
        w.bind("<Destroy>", lambda e, k=str(w): self._colour_ctx.pop(k, None), add="+")

    def _clip_text(self, w):
        try:
            return w.clipboard_get()
        except self.tk.TclError:
            return ""

    def _copy_text(self, w, text, what):
        w.clipboard_clear()
        w.clipboard_append(text)
        self.status_var.set("Copied %s: %s" % (what, text))

    def _add_colour_items(self, menu, w, getter, setter):
        rgb = getter()
        st = "normal" if rgb is not None else "disabled"
        menu.add_command(label="Copy colour as hex", state=st,
                         command=lambda: self._copy_text(w, hex_of(rgb), "hex"))
        menu.add_command(label="Copy colour as R,G,B", state=st,
                         command=lambda: self._copy_text(w, "%d,%d,%d" % tuple(rgb),
                                                         "R,G,B"))
        clip = parse_colour(self._clip_text(w))
        menu.add_command(label="Paste colour" + (" (%s)" % hex_of(clip) if clip else ""),
                         state="normal" if clip and setter else "disabled",
                         command=lambda: setter(clip))

    def _popup(self, menu, ev):
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def colour_menu(self, ev, getter, setter):
        """Right-click menu for a colour swatch."""
        menu = self.tk.Menu(ev.widget, tearoff=0)
        self._add_colour_items(menu, ev.widget, getter, setter)
        self._popup(menu, ev)
        return "break"

    def _entry_menu(self, ev):
        w = ev.widget
        try:
            w.focus_set()
        except self.tk.TclError:
            pass
        try:
            has_sel = bool(w.tk.call(w._w, "selection", "present"))
        except self.tk.TclError:
            has_sel = False
        try:
            disabled = w.instate(["disabled"])
        except (AttributeError, self.tk.TclError):
            disabled = str(w.cget("state")) == "disabled"
        try:
            ro = w.instate(["readonly"])
        except (AttributeError, self.tk.TclError):
            ro = False
        editable = not disabled and not ro
        clip = self._clip_text(w)
        menu = self.tk.Menu(w, tearoff=0)

        def ev_(name):
            return lambda: w.event_generate(name)

        def delete():
            try:
                w.delete("sel.first", "sel.last")
            except self.tk.TclError:
                pass

        def select_all():
            try:
                w.selection_range(0, "end")
                w.icursor("end")
            except (AttributeError, self.tk.TclError):
                w.tk.call(w._w, "selection", "range", 0, "end")

        menu.add_command(label="Cut", accelerator="Ctrl+X", command=ev_("<<Cut>>"),
                         state="normal" if has_sel and editable else "disabled")
        menu.add_command(label="Copy", accelerator="Ctrl+C", command=ev_("<<Copy>>"),
                         state="normal" if has_sel else "disabled")
        menu.add_command(label="Paste", accelerator="Ctrl+V", command=ev_("<<Paste>>"),
                         state="normal" if clip and editable else "disabled")
        menu.add_command(label="Delete", command=delete,
                         state="normal" if has_sel and editable else "disabled")
        menu.add_separator()
        menu.add_command(label="Select all", accelerator="Ctrl+A", command=select_all)
        ctx = self._colour_ctx.get(str(w))
        if ctx:
            menu.add_separator()
            self._add_colour_items(menu, w, ctx[0], ctx[1])
        self._popup(menu, ev)
        return "break"

    def _entry_select_all(self, ev):
        w = ev.widget
        try:
            w.selection_range(0, "end")
            w.icursor("end")
        except (AttributeError, self.tk.TclError):
            pass
        return "break"
