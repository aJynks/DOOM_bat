"""Startup dependency checks."""

import sys


# ============================================================ dependency check
def _dep_check():
    missing = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter is missing - reinstall Python with the 'tcl/tk and IDLE' option.")
        sys.exit(1)
    if not missing:
        try:
            from PIL import ImageTk  # noqa: F401
        except ImportError:
            print("Pillow's ImageTk is missing - reinstall with: "
                  "pip install --force-reinstall Pillow")
            sys.exit(1)
    if missing:
        print("Missing dependencies: " + ", ".join(missing))
        print("Install with: pip install " + " ".join(missing))
        sys.exit(1)



def _dep_check_pil():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Missing dependencies: Pillow")
        print("Install with: pip install Pillow")
        sys.exit(1)
