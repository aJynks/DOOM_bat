from krita import Krita, Extension
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QAction

class DoomPaletteToolsExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

    def setup(self):
        pass

    def createActions(self, window):
        # Create the parent entry in Tools -> Scripts
        parent_action = window.createAction(
            "doom_palette_tools_menu",
            "Doom Palette Tools",
            "tools/scripts"
        )

        # Attach a submenu to that parent action
        menu = QtWidgets.QMenu("Doom Palette Tools", window.qwindow())
        parent_action.setMenu(menu)

        # Import functions (do it here so plugin loads even if a script is missing)
        from .slade2strip_1x1 import main as slade2strip_1x1
        from .slade2strip_8x8 import main as slade2strip_8x8
        from .strip2slade_1x1 import main as strip2slade_1x1
        from .strip2slade_8x8 import main as strip2slade_8x8

        def add_item(label, fn):
            act = QAction(label, window.qwindow())
            act.triggered.connect(fn)
            menu.addAction(act)

        # Optional: a ping item so you can confirm it runs
        add_item("Ping (prints to Scripter console)", lambda: print("Doom Palette Tools: ping"))

        menu.addSeparator()

        add_item("SLADE → Strip (1x1)", slade2strip_1x1)
        add_item("SLADE → Strip (8x8)", slade2strip_8x8)
        add_item("Strip → SLADE (1x1)", strip2slade_1x1)
        add_item("Strip → SLADE (8x8)", strip2slade_8x8)

Krita.instance().addExtension(DoomPaletteToolsExtension(Krita.instance()))
