"""The preview pane keeps its page when what it shows is made again."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("PySide6.QtPdfWidgets")

from py_imposition import main  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def sample(path, count):
    assert main(["sample", "--count", str(count), "-o", str(path), "-q"]) == 0
    return path


def test_a_new_result_stays_on_the_page_being_looked_at(app, tmp_path):
    from py_imposition.gui.preview import PdfPane
    results = tmp_path / "results"
    results.mkdir()
    pane = PdfPane("Result")
    pane.resize(400, 600)
    pane.show()
    pane.load(sample(results / "result-1.pdf", 8))
    pane.page.setValue(5)
    app.processEvents()
    assert pane.view.pageNavigator().currentPage() == 4
    pane.load(sample(results / "result-2.pdf", 8))  # (made again: same folder)
    app.processEvents()
    assert pane.page.value() == 5 and pane.view.pageNavigator().currentPage() == 4
    pane.load(sample(results / "result-3.pdf", 3))  # (fewer pages: the last one)
    assert pane.page.value() == 3
    other = tmp_path / "elsewhere"
    other.mkdir()
    pane.load(sample(other / "doc.pdf", 8))  # another document starts at page 1
    assert pane.page.value() == 1
    pane.clear("")
    pane.load(sample(results / "result-4.pdf", 8))  # (and after clearing, too)
    assert pane.page.value() == 1
