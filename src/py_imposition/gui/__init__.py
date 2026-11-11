"""Graphical interface for py-imposition (PySide6 / Qt 6).

Install with the ``gui`` extra (``pip install 'py-imposition[gui]'``) and
start with ``py-imposition-gui [file.pdf]``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("The GUI needs PySide6. Install it with: pip install 'py-imposition[gui]'", file=sys.stderr)
        return 1
    from .window import MainWindow

    app = QApplication.instance() or QApplication([sys.argv[0]] + argv)
    app.setApplicationName("py-imposition")
    app.setOrganizationName("py-imposition")
    win = MainWindow()
    files = [a for a in argv if a.lower().endswith(".pdf")]
    if files:
        win.open_path(Path(files[0]))
    win.show()
    return app.exec()
