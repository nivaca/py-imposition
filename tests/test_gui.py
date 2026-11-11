"""GUI tests (run headless with the Qt 'offscreen' platform)."""

from __future__ import annotations

import os
import shlex
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("PySide6.QtPdfWidgets")

from py_imposition import main  # noqa: E402
from py_imposition.common import COMMANDS  # noqa: E402
from py_imposition.runner import build_parser  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("py-imposition-tests")
    QCoreApplication.setApplicationName("py-imposition-tests")
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    QSettings("py-imposition", "py-imposition")  # touch
    yield a


@pytest.fixture()
def window(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "config"))
    from py_imposition.gui.window import MainWindow
    w = MainWindow()
    yield w
    try:
        w.runner.stop()
        w.close()
    except RuntimeError:  # (already deleted: the window was built again in another language)
        pass


def namespace(tokens):
    """Parse a step the way the CLI would (adding placeholder inputs where needed)."""
    cmd = COMMANDS[tokens[0]]
    argv = list(tokens)
    if cmd.needs_input is True:
        argv.insert(1, "in.pdf")
    if tokens[0] == "replay":
        argv.append("in.pdf")
    return vars(build_parser().parse_args(argv))


def test_every_command_has_a_form_with_clean_defaults(app):
    from py_imposition.gui.forms import CommandForm, subparsers
    parsers = subparsers()
    assert set(parsers) == set(COMMANDS)
    for name, parser in parsers.items():
        form = CommandForm(name, parser)
        assert form.tokens() == [name], f"{name} emits options at their defaults: {form.tokens()}"


ROUND_TRIP = [
    "booklet --binding saddle --paper a4 --margin 1cm --crop-marks --sides separate",
    "nup --cols 2 --rows 2 --scale fit --hspace '0 40' --align center --mirror h --background bg.pdf",
    "step-repeat --paper 9x14in --orientation tall --rotate --align-rows",
    "shuffle --rule '8 1 5* 4* 2 7 3* 6*' --repeat saddle",
    "trim-shift --trim left=1cm --trim top=5mm --shift right=2mm --parity odd",
    "resize --percent 50",
    "text --text 'Page [#] of [Doc:NumPages]' --start 007 --size 12.5 --rotation 90",
    "insert --blank 999 --after LAST-1 --until multiple:4",
    "mask --rect 0,0,3,2 --rect 5,5,1,1",
    "split --by equal --size 4 --part-steps '1=reverse' --merge",
    "run --sequence s.toml a.pdf b.pdf --out-dir out",
    "watch hot --sequence s.toml --interval 5",
    "replay --from done.pdf",
    "booklet --units mm --registration all",
]


@pytest.mark.parametrize("line", ROUND_TRIP)
def test_form_round_trip(app, line):
    from py_imposition.gui.forms import CommandForm, subparsers
    tokens = shlex.split(line)
    form = CommandForm(tokens[0], subparsers()[tokens[0]])
    form.set_tokens(tokens)
    assert namespace(form.tokens()) == namespace(tokens)


def wait(app, window, timeout=60):
    end = time.time() + timeout
    while (window.runner.busy() or window.timer.isActive()) and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()


def test_preview_apply_undo(app, window, tmp_path):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "6", "--paper", "a5", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("nup")
    window.form("nup").set_tokens(["nup", "--cols", "2", "--rows", "1", "--scale", "fit", "--paper", "a4",
                                   "--orientation", "wide"])
    window.preview()
    wait(app, window)
    assert len(window.result_files) == 1
    assert window.res_pane.doc.pageCount() == 3
    window.apply()
    wait(app, window)
    assert window.source != sample and window.undo_stack == [sample]
    assert window.src_pane.doc.pageCount() == 3
    window.undo()
    assert window.source == sample


def test_multiple_outputs_and_errors(app, window, tmp_path):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "4", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("evenodd")
    window.form("evenodd").set_tokens(["evenodd", "--mode", "split"])
    window.preview()
    wait(app, window)
    assert [window._suffix(f) for f in window.result_files] == ["even", "odd"]
    window.select_command("shuffle")
    window.form("shuffle").set_tokens(["shuffle", "--rule", "1 2 nonsense"])
    window.preview()
    wait(app, window)
    assert "invalid token" in window.statusBar().currentMessage()


def test_sequence_run_on_document(app, window, tmp_path):
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "8", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.seq.set_steps([["text", "--text", "N[#]"], ["booklet", "--binding", "saddle", "--paper", "a3"]])
    window.seq.run_on_document()
    wait(app, window)
    assert len(window.result_files) == 1
    assert window.res_pane.doc.pageCount() == 4
    window.apply()
    assert window.undo_stack == [sample]


def test_change_language_keeps_the_document(app, window, tmp_path, monkeypatch):
    from py_imposition import config, interface
    from py_imposition.gui import window as winmod
    monkeypatch.setenv(config.ENV, str(tmp_path / "cfg"))
    sample = tmp_path / "s.pdf"
    assert main(["sample", "--count", "4", "-o", str(sample), "-q"]) == 0
    window.auto.setChecked(False)
    window.open_path(sample)
    window.select_command("reverse")
    window.preview()
    wait(app, window)
    window.apply()
    applied = window.source
    try:
        window.change_language("es")
        new = winmod._WINDOWS[-1]
        assert new is not window
        assert interface.code() == "es" and config.get("interface") == "es"
        assert new.menuBar().actions()[0].text() == "&Archivo"
        assert new.b_preview.text() == "Vista previa"
        assert new.source == applied and new.undo_stack == [sample]
        assert new.src_pane.doc.pageCount() == 4
        # the commands run by the window speak its language, and their output is still understood
        new.auto.setChecked(False)
        new.select_command("reverse")
        new.preview()
        wait(app, new)
        assert len(new.result_files) == 1
        new.change_language("en")
        assert winmod._WINDOWS[-1].b_preview.text() == "Preview"
    finally:
        interface.use("en")
        interface.translate_argparse()
        for w in list(winmod._WINDOWS):
            w.runner.stop()
            w.close()
        winmod._WINDOWS.clear()
