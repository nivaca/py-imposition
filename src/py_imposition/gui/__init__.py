"""Graphical interface for py-imposition (PySide6 / Qt 6).

Install with the ``gui`` extra (``pip install 'py-imposition[gui]'``) and
start with ``py-imposition-gui [file.pdf]``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..interface import tr


def app_icon():
    """The program's icon, in every size that ships with it."""
    from PySide6.QtGui import QIcon

    icon = QIcon()
    hicolor = Path(__file__).resolve().parent.parent / "icons" / "linux" / "hicolor"
    for png in sorted(hicolor.glob("*/apps/py-imposition.png")):
        icon.addFile(str(png))
    return icon


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    from .. import interface
    from .. import interface_option  # (--interface CODE: this run only)

    interface.use_configured(interface_option(argv))
    interface.translate_argparse()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(tr("The GUI needs PySide6. Install it with: pip install 'py-imposition[gui]'"), file=sys.stderr)
        return 1
    from .window import _WINDOWS, MainWindow, install_qt_translations

    app = QApplication.instance() or QApplication([sys.argv[0]] + argv)
    app.setApplicationName("py-imposition")
    app.setOrganizationName("py-imposition")
    # match the menu entry made by py-imposition-install (Wayland app id / WM class)
    app.setDesktopFileName("py-imposition")
    app.setWindowIcon(app_icon())
    install_qt_translations()
    win = MainWindow()
    _WINDOWS.append(win)
    files = [a for a in argv if a.lower().endswith(".pdf")]
    if files:
        win.open_path(Path(files[0]))
    win.show()
    return app.exec()
