"""Projects, presets and settings application (App mixin)."""

import json
import os

from ..colour import hex_of
from ..constants import METRICS, PICKER_MODES, PRESET_DIR, PRESET_MARKER, VERSION
from ..ramps import clean_ramp_state
from ..settings import PROJECT_EXT, PROJECT_MARKER, validate_preset, validate_project
from ..colormap import rows_from_bytes
from ..wadgfx import WadArchive, guess_iwad


class ProjectMixin:
    """Projects, presets, settings application and the IWAD."""

    # ---------------------------------------------------------- IWAD
    def iwad_path(self):
        p = self.s.get("iwad")
        return p if isinstance(p, str) and os.path.isfile(p) else None

    def iwad_archive(self, prompt=False, parent=None):
        """The IWAD as a WadArchive (cached), or None. prompt=True asks for
        one first when none is set."""
        p = self.iwad_path()
        if p is None and prompt:
            self.ensure_iwad(parent=parent)
            p = self.iwad_path()
        if p is None:
            return None
        try:
            key = (p, os.path.getmtime(p))
        except OSError:
            return None
        if getattr(self, "_iwad_key", None) != key:
            try:
                self._iwad = WadArchive(p)
            except (OSError, ValueError):
                self._iwad = None
            self._iwad_key = key
        return self._iwad

    def _iwad_btn_text(self):
        p = self.iwad_path()
        self.iwad_btn.configure(text="IWAD: %s" % os.path.basename(p) if p
                                else "IWAD: not set!")

    def ensure_iwad(self, parent=None):
        """Ask for the IWAD (offering a found one). True if one is set."""
        if self.iwad_path():
            return True
        guess = guess_iwad([self.src_path, self.s.get("preview_wad")])
        text = ("cleanpal needs an IWAD (doom2.wad, doom.wad, ...). It supplies "
                "textures and patches for the Palettised preview, and the fallback "
                "PLAYPAL / COLORMAP when a file has none.")
        if guess:
            k = self._ask_buttons("Choose the IWAD", text + "\n\nFound: %s" % guess,
                                  [("use", "Use this one"), ("browse", "Browse..."),
                                   ("later", "Later")])
        else:
            k = self._ask_buttons("Choose the IWAD", text + "\n\nNo IWAD found beside the "
                                  "file or in DOOMWADDIR / DOOMWADPATH.",
                                  [("browse", "Browse..."), ("later", "Later")])
        if k == "use":
            self.set_iwad(guess)
        elif k == "browse":
            self.choose_iwad(parent=parent)
        else:
            self.status_var.set("No IWAD set - click the IWAD button in the top bar.")
        return bool(self.iwad_path())

    def choose_iwad(self, parent=None):
        from tkinter import filedialog

        cur = self.iwad_path() or guess_iwad([self.src_path])
        p = filedialog.askopenfilename(
            parent=parent or self.root, title="Choose the IWAD",
            initialdir=os.path.dirname(cur) if cur else None,
            filetypes=[("WAD", "*.wad"), ("All files", "*.*")])
        if p:
            self.set_iwad(p)

    def set_iwad(self, path):
        from tkinter import messagebox

        try:
            arch = WadArchive(path)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Not a usable WAD:\n%s\n\n%s" % (path, e))
            return
        lacks = [n for n in ("PLAYPAL", "COLORMAP", "PNAMES", "TEXTURE1")
                 if arch.lump(n) is None]
        if lacks and not messagebox.askyesno(
                "cleanpal", "%s has no %s lump%s - it doesn't look like an IWAD.\n\n"
                            "Use it anyway?" % (os.path.basename(path), " / ".join(lacks),
                                                "" if len(lacks) == 1 else "s")):
            return
        self.s["iwad"] = os.path.abspath(path)
        self._iwad_key = None
        self._iwad_btn_text()
        if self.cmap_loaded is None or self.cmap_loaded.get("iwad"):
            self.cmap_loaded = self._iwad_colormap()
            self._cmap_status_text()
        if self.preview is not None:
            self.preview.reload()
        self.status_var.set("IWAD: %s" % self.s["iwad"])
        self.recompute()

    def _iwad_colormap(self):
        """The IWAD's COLORMAP (with its PLAYPAL) for compare / import, or None."""
        arch = self.iwad_archive()
        if arch is None:
            return None
        raw, pal = arch.lump("COLORMAP"), arch.playpal()
        if raw is None or pal is None:
            return None
        try:
            rows = rows_from_bytes(raw)
        except ValueError:
            return None
        return {"rows": rows, "pal": pal, "iwad": True,
                "name": "IWAD %s COLORMAP" % os.path.basename(arch.path)}

    def _startup_iwad(self):
        self._iwad_btn_text()
        if not self.iwad_path():
            self.ensure_iwad()

    def save_project(self, ask=False):
        from tkinter import filedialog, messagebox

        if self.rgbs is None:
            self.status_var.set("Open a palette first.")
            return
        if self._preview_busy_msg():
            return
        if self.move_pending():
            self.status_var.set("Apply or Revert the moves before saving the project.")
            return
        if self.paint_pending():
            self.status_var.set("Snapshot or Revert the paint edits before saving the "
                                "project.")
            return
        p = self.project_path
        if ask or not p:
            if self.project_path:
                d0, f0 = os.path.split(self.project_path)
            else:
                d0 = self.s.get("project_dir") or (os.path.dirname(self.src_path)
                                                   if self.src_path else None)
                f0 = (os.path.splitext(os.path.basename(self.src_path))[0]
                      if self.src_path else "palette") + PROJECT_EXT
            p = filedialog.asksaveasfilename(
                title="Save project", initialdir=d0 or None, initialfile=f0,
                defaultextension=PROJECT_EXT,
                filetypes=[("cleanpal project", "*" + PROJECT_EXT)])
            if not p:
                return
        data = self.project_data()
        try:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, p)
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not save project:\n%s" % e)
            return
        self.project_path = os.path.abspath(p)
        self.s["project_dir"] = os.path.dirname(self.project_path)
        self.exported = True
        self._update_title()
        self.status_var.set("Saved project %s" % self.project_path)

    def project_data(self):
        def pal(entries):
            return [hex_of(c) if c is not None else None for c in entries]

        paint = self.ramp is not None and not getattr(self.ramp, "FADE", False)
        ramp = self.ramp.st if paint else self.s.get("ramp")
        settings = self.current_preset()
        return {
            PROJECT_MARKER: 1, "version": VERSION,
            "source": self.src_path or "",
            "history": [dict({"text": h["text"], "palette": pal(h["palette"])},
                             **({"cmap": h["cmap"].to_json()} if h.get("cmap") is not None
                                and not h["cmap"].empty() else {}))
                        for h in self.history],
            "mode": self.mode_var.get(),
            "cmap_loaded": ({"name": self.cmap_loaded["name"],
                             "rows": [list(r) for r in self.cmap_loaded["rows"]],
                             "pal": pal(self.cmap_loaded["pal"])}
                            if self.cmap_loaded else None),
            "hist_pos": self.hist_pos,
            "deleted": sorted(self.deleted), "selection": sorted(self.selection),
            "settings": settings,
            "ramp": json.loads(json.dumps(ramp)) if ramp else None,
            "scratch_sets": self.s.get("scratch_sets") or {},
            "scratch_current": self.s.get("scratch_current"),
            "recent_colours": self.s.get("recent_colours", []),
            "picker_mode": self.s.get("picker_mode", PICKER_MODES[0]),
        }

    def load_project(self, path):
        from tkinter import messagebox

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            proj = validate_project(data)
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not open project:\n%s\n\n%s"
                                 % (path, e))
            return
        self.close_tool(quiet=True, force=True)
        if self._ramp_backup is not None:
            self._ramp_end()
        if proj["settings"]:
            self.apply_settings(proj["settings"])
        if proj["ramp"] is not None:
            self.s["ramp"] = proj["ramp"]
            if self.ramp is not None and not getattr(self.ramp, "FADE", False):
                self.ramp.set_state(clean_ramp_state(proj["ramp"]))
        if proj["scratch_sets"]:
            sets = self.s.get("scratch_sets")
            if not isinstance(sets, dict):
                sets = {}
            sets.update(proj["scratch_sets"])
            self.s["scratch_sets"] = sets
            if proj["scratch_current"] in sets:
                self.s["scratch_current"] = proj["scratch_current"]
            if self.scratch is not None:
                self.scratch._refresh_sets()
        if proj["recent_colours"]:
            self.s["recent_colours"] = proj["recent_colours"][:16]
        if proj["picker_mode"]:
            self.s["picker_mode"] = proj["picker_mode"]
        self.history = [{"text": h["text"], "palette": h["palette"],
                         "labs": None, "pairs": None, "cmap": h["cmap"]}
                        for h in proj["history"]]
        self.cmap_loaded = proj["cmap_loaded"] or self._iwad_colormap()
        self._cmap_status_text()
        self.rgbs = None                   # force a full entry load below
        self.src_path = proj["source"] or os.path.abspath(path)
        self.project_path = os.path.abspath(path)
        self.s["project_dir"] = os.path.dirname(self.project_path)
        self.s["last_dir"] = os.path.dirname(self.project_path)
        self._load_entry(proj["hist_pos"])
        self.deleted = {i for i in proj["deleted"] if self.rgbs[i] is not None}
        self.selection = set(proj["selection"])
        self.exported = True
        self.file_var.set("%s   [cleanpal project, %d entries]"
                          % (os.path.basename(path), len(self.history)))
        self._update_title()
        self.status_var.set("Opened project %s" % path)
        if proj["mode"] and proj["mode"] != self.mode_var.get():
            self.set_mode(proj["mode"])
        self.recompute()

    def current_preset(self):
        d = {"exact": self.exact_var.get(), "similar": self.similar_var.get(),
             "metric": self.metric_var.get(),
             "align": self.align_var.get(), "split": self.split_var.get(),
             "export": self.export_var.get()}
        for m in METRICS:
            d["tol_" + m] = self.tol[m]
        d.update(self.current_sort_settings())
        d.update({k: (list(v) if isinstance(v, (list, tuple)) else v)
                  for k, v in self.cmap_set.items()})
        return d

    def save_preset(self):
        from tkinter import filedialog, messagebox

        initdir = self.s.get("preset_dir") or PRESET_DIR
        try:
            os.makedirs(initdir, exist_ok=True)
        except OSError:
            initdir = None
        p = filedialog.asksaveasfilename(
            title="Save preset", initialdir=initdir,
            initialfile=(self.preset_name or "cleanpal-preset") + ".json",
            defaultextension=".json", filetypes=[("cleanpal preset", "*.json")])
        if not p:
            return
        data = {PRESET_MARKER: 1, "version": VERSION, "settings": self.current_preset()}
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as e:
            messagebox.showerror("cleanpal", "Could not save preset:\n%s" % e)
            return
        self.s["preset_dir"] = os.path.dirname(p)
        self.preset_name = os.path.splitext(os.path.basename(p))[0]
        self._update_title()
        self.status_var.set("Saved preset %s" % p)

    def load_preset(self):
        from tkinter import filedialog, messagebox

        initdir = self.s.get("preset_dir") or PRESET_DIR
        if not os.path.isdir(initdir):
            initdir = None
        p = filedialog.askopenfilename(
            title="Load preset", initialdir=initdir,
            filetypes=[("cleanpal preset", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                d = validate_preset(json.load(fh))
        except (OSError, ValueError) as e:
            messagebox.showerror("cleanpal", "Could not load preset:\n%s\n\n%s" % (p, e))
            return
        self.apply_settings(d)
        self.s["preset_dir"] = os.path.dirname(p)
        self.preset_name = os.path.splitext(os.path.basename(p))[0]
        self._update_title()
        self.status_var.set("Loaded preset %s" % p)

    def apply_settings(self, d):
        """Apply a validated preset-style settings dict."""
        if any(k.startswith("cmap_") for k in d):
            self.apply_cmap_settings(d)
        for k, var in (("exact", self.exact_var), ("similar", self.similar_var),
                       ("align", self.align_var), ("split", self.split_var),
                       ("metric", self.metric_var), ("export", self.export_var)):
            if k in d:
                var.set(d[k])
        for m in METRICS:
            if "tol_" + m in d:
                self.tol[m] = d["tol_" + m]
        if self.similar_var.get() and not self.exact_var.get():
            self.similar_var.set(False)  # similar needs exact
        for k, var in (("sort_method", self.sort_method_var), ("sort_key", self.sort_key_var),
                       ("sort_high", self.sort_high_var),
                       ("sort_ramp_order", self.sort_order_var),
                       ("sort_outliers", self.sort_outlier_var)):
            if k in d:
                var.set(d[k])
        if "sort_min" in d:
            self.sort_min = d["sort_min"]
            self.sort_min_text.set(str(self.sort_min))
        if "sort_params" in d:
            self.sort_params = d["sort_params"]
        self._build_sort_options()
        self._on_sort_option()
        self._update_states()
        self._sync_tol_widgets()
        self.recompute()
