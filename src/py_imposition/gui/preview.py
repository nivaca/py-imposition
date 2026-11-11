"""PDF preview pane built on QtPdf."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMenu, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)


class PdfPane(QWidget):
    """A titled PDF viewer with page navigation and zoom controls."""

    output_selected = Signal(int)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.doc = QPdfDocument(self)
        self.path: Path | None = None

        self.title = QLabel(f"<b>{title}</b>")
        self.info = QLabel("")
        # may shrink (the full text is in the tooltip), so the window fits small screens
        self.info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.info.setMinimumWidth(40)
        self.outputs = QComboBox()
        self.outputs.setVisible(False)
        self.outputs.currentIndexChanged.connect(self.output_selected.emit)

        self.page = QSpinBox()
        self.page.setMinimum(1)
        self.page.setPrefix("page ")
        self.page.setEnabled(False)
        self.page.valueChanged.connect(self._jump)

        self.view = QPdfView(self)
        self.view.setDocument(self.doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setPageSpacing(12)
        self.view.pageNavigator().currentPageChanged.connect(self._page_changed)

        zoom = QToolButton()
        zoom.setText("Zoom")
        zoom.setToolTip("Fit the page or its width, or zoom in and out (also Ctrl+wheel)")
        zoom.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(zoom)
        menu.addAction("Fit page", lambda: self.set_zoom("page"))
        menu.addAction("Fit width", lambda: self.set_zoom("width"))
        menu.addSeparator()
        menu.addAction("Zoom in", lambda: self.zoom_by(1.25))
        menu.addAction("Zoom out", lambda: self.zoom_by(1 / 1.25))
        zoom.setMenu(menu)

        top = QHBoxLayout()
        top.addWidget(self.title)
        top.addWidget(self.outputs)
        top.addWidget(self.info, 1)
        top.addWidget(self.page)
        top.addWidget(zoom)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(top)
        lay.addWidget(self.view, 1)
        self.clear("")

    # ----------------------------------------------------------------- loading

    def load(self, path: Path | None, note: str = ""):
        self.doc.close()
        self.path = path
        if path is None:
            self.clear(note)
            return
        self.doc.load(str(path))
        n = self.doc.pageCount()
        self.page.blockSignals(True)
        self.page.setMaximum(max(n, 1))
        self.page.setValue(1)
        self.page.setSuffix(f" / {n}")
        self.page.setEnabled(n > 1)
        self.page.blockSignals(False)
        size = self.doc.pagePointSize(0) if n else None
        dims = f"{size.width() / 72 * 2.54:.1f} × {size.height() / 72 * 2.54:.1f} cm" if size else ""
        self.info.setText(f"{path.name} — {n} page{'s' if n != 1 else ''}{', ' + dims if dims else ''}"
                          + (f" — {note}" if note else ""))
        self.info.setToolTip(self.info.text())
        self.view.setZoomMode(self.view.zoomMode())

    def clear(self, note: str):
        self.doc.close()
        self.path = None
        self.page.setEnabled(False)
        self.page.setSuffix("")
        self.info.setText(note)

    def set_outputs(self, names: list[str]):
        self.outputs.blockSignals(True)
        self.outputs.clear()
        self.outputs.addItems(names)
        self.outputs.setVisible(len(names) > 1)
        self.outputs.blockSignals(False)

    # ----------------------------------------------------------------- navigation

    def _jump(self, value: int):
        self.view.pageNavigator().jump(value - 1, QPointF(), self.view.pageNavigator().currentZoom())

    def _page_changed(self, page: int):
        self.page.blockSignals(True)
        self.page.setValue(page + 1)
        self.page.blockSignals(False)

    def set_zoom(self, mode: str):
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView if mode == "page" else QPdfView.ZoomMode.FitToWidth)

    def zoom_by(self, factor: float):
        z = self.view.zoomFactor()
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(max(0.05, min(z * factor, 20)))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_PageDown, Qt.Key.Key_Right):
            self.page.setValue(min(self.page.value() + 1, self.page.maximum()))
        elif event.key() in (Qt.Key.Key_PageUp, Qt.Key.Key_Left):
            self.page.setValue(max(self.page.value() - 1, 1))
        else:
            super().keyPressEvent(event)
