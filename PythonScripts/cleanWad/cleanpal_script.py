#!/usr/bin/env python3
"""
cleanpal - Doom PLAYPAL / COLORMAP editor (GUI)

Loads pal0 from a WAD (PLAYPAL + COLORMAP), SLADE playpal.pal / pal0.pal, SLADE
pal0.png, DoomTools playpal.png or a .cleanpal project, and shows it as a SLADE
style 16x16 grid.

PLAYPAL mode: remove exact / similar colours, sort into ramps, build ramps with
the Ramp tool, colour picker and scratch palette, snapshots and projects.
COLORMAP mode: the 34 light tables generated live from the palette, with hand
overrides, bulk fade tools, diagnostics, "Create fade colours" and lit previews.

This file is only the launcher: the code lives in the cleanpal_lib folder,
which must sit next to this script (the folder does not need to be on PATH).
Run  cleanpal --help  for details.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if not os.path.isfile(os.path.join(_HERE, "cleanpal_lib", "__init__.py")):
    print("cleanpal_lib folder not found next to cleanpal_script.py.")
    print("Copy the whole cleanpal set together: cleanpal.bat, cleanpal_script.py")
    print("and the cleanpal_lib folder (with its gui subfolder).")
    sys.exit(1)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cleanpal_lib.main import main  # noqa: E402

if __name__ == "__main__":
    main()
