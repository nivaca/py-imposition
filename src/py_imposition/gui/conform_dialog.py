"""Settings ▸ pdf2iso: where the program that makes PDF/A and PDF/X is
(kept in the configuration file; empty to look for it, see conform.find)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from .. import conform
from ..interface import tr


class ConformDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("pdf2iso")
        self.pdfconform = QLineEdit()
        self.pdfconform.setMinimumWidth(380)
        self.pdfconform.setPlaceholderText(tr("Look for it on the PATH, in ~/bin and in ~/.local/bin"))
        self.pdfconform.setToolTip(tr("The script pdf2iso, which makes PDF/A and PDF/X (with or without "
                                      "the .py extension); empty to look for it"))
        self.pdfconform.textChanged.connect(self._show_pdfconform)
        choose = QPushButton(tr("Choose…"))
        choose.clicked.connect(self._choose_pdfconform)
        self.pdfconform_found = QLabel()
        self.pdfconform_found.setWordWrap(True)
        self.pdfconform_found.setStyleSheet("color: palette(placeholder-text);")
        row = QHBoxLayout()
        row.addWidget(self.pdfconform, 1)
        row.addWidget(choose)
        form = QFormLayout()
        form.addRow(tr("pdf2iso:"), row)
        form.addRow("", self.pdfconform_found)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.pdfconform.setText(path)
        self._show_pdfconform()

    def path(self) -> str:
        return self.pdfconform.text().strip()

    def _show_pdfconform(self, *_):
        """Which pdf2iso will be used (File > Save as > PDF/A, PDF/X)."""
        path = self.path()
        found = conform.find(path)
        if found is not None:
            self.pdfconform_found.setText(tr("It will be {path}", path=found))
        elif path:
            self.pdfconform_found.setText(tr("There is no such file"))
        else:
            self.pdfconform_found.setText(tr("Not found: PDF/A and PDF/X can't be made until it is given here"))

    def _choose_pdfconform(self):
        start = self.path() or str(Path.home() / "bin")
        name, _ = QFileDialog.getOpenFileName(self, tr("Where is pdf2iso?"), start,
                                              tr("pdf2iso (pdf2iso pdf2iso.py);;All files (*)"))
        if name:
            self.pdfconform.setText(name)
