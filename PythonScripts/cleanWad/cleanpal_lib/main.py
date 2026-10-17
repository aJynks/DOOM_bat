"""Command-line entry: argument handling and GUI start-up."""

import os
import sys

from .clihelp import print_help
from .deps import _dep_check, _dep_check_pil
from .sorting import ramp_test


def main():
    args = sys.argv[1:]
    if any(a.lower() in ("-h", "--help", "-help", "/?") for a in args):
        print_help()
        return
    if args and args[0].lower() == "--ramptest":
        if len(args) not in (2, 3):
            print("Usage: cleanpal --ramptest <palette> [output folder]")
            sys.exit(1)
        if not os.path.isfile(args[1]):
            print("Input file not found: %s" % args[1])
            sys.exit(1)
        _dep_check_pil()
        try:
            ramp_test(args[1], args[2] if len(args) == 3 else None)
        except (ValueError, OSError) as e:
            print("ramptest failed: %s" % e)
            sys.exit(1)
        return
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("Usage: cleanpal [input]   (cleanpal --help for details)")
        sys.exit(1)
    path = args[0] if args else None
    if path and not os.path.isfile(path):
        print("Input file not found: %s" % path)
        sys.exit(1)

    _dep_check()
    import tkinter as tk

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    from .gui.app import App

    root = tk.Tk()
    App(root, path)
    root.mainloop()
