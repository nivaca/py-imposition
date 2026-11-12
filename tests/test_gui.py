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
    monkeypatch.setenv("PY_IMPOSITION_CONFIG", str(tmp_path / "py-imposition-config"))
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "config"))
    from py_imposition.gui.window import MainWindow
    w = MainWindow()
    w.set_mode("advanced")  # (most tests drive the command forms)
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


# --------------------------------------------------------------------------- basic mode


def test_basic_mode_switch(app, window):
    window.set_mode("basic")
    assert window.current == "impose" and window.form("impose") is window.basic
    assert not window.tree.isVisibleTo(window) and not window.b_add.isVisibleTo(window)
    assert not window.units.isVisibleTo(window)  # (the form has its own Units)
    window.set_mode("advanced")
    assert window.current != "impose" or window.form("impose") is not window.basic
    assert window.tree.isVisibleTo(window)


def test_basic_form_round_trip_and_enabling(app, window):
    window.set_mode("basic")
    b = window.basic
    assert b.tokens() == ["impose"]  # the defaults: 2-up booklet, perfect, Legal landscape
    assert not b.cols.isEnabled() and not b.spread.isEnabled() and b.sheets.isEnabled()
    line = ["impose", "--layout", "8up-booklet", "--binding", "saddle", "--direction", "right", "--gutter-v",
            "1", "--spread", "2", "--creep", "0.1", "--media", "a3", "--orientation", "portrait", "--auto-rotate",
            "--margin-top", "1.5", "--trim-marks", "--registration-marks"]
    b.set_tokens(line)
    assert b.spread.isEnabled() and not b.sheets.isEnabled() and not b.cols.isEnabled()
    assert namespace(b.tokens()) == namespace(line)
    b.set_tokens(["impose", "--layout", "cut-stacks", "--cols", "3", "--rows", "2", "--single-sided",
                  "--media", "20x30cm"])
    assert b.cols.isEnabled() and not b.binding.isEnabled() and b.width.isEnabled()
    assert namespace(b.tokens())["media"] == "20x30cm"


def test_basic_units_convert(app, window):
    window.set_mode("basic")
    b = window.basic
    b.units.setCurrentText("cm")
    b.set_tokens(["impose", "--margin-top", "2.54"])
    b.units.setCurrentText("in")
    assert b.m_top.value() == pytest.approx(1.0)
    assert window.units.currentText() == "in"
    b.units.setCurrentText("cm")


def test_basic_profiles(app, window, monkeypatch):
    window.set_mode("basic")
    b = window.basic
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Cards", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    b.set_tokens(["impose", "--layout", "step-repeat", "--cols", "4", "--rows", "5", "--trim-marks"])
    b.save_profile(new_name=True)
    assert "Cards" in b.profiles() and b.profile.currentData() == "Cards"
    b.on_menu.setChecked(True)
    assert any(a.text() == "Cards" for a in window.m_profiles.actions())
    b.reset()
    assert b.tokens() == ["impose"]
    window._use_profile("Cards")
    assert namespace(b.tokens())["layout"] == "step-repeat" and namespace(b.tokens())["cols"] == 4
    b.delete_profile()
    assert "Cards" not in b.profiles()


def test_basic_preview(app, window, tmp_path):
    example = Path(__file__).resolve().parent.parent / "docs" / "example" / "numbers-100.pdf"
    window.auto.setChecked(False)
    window.open_path(example)
    window.set_mode("basic")
    window.basic.set_tokens(["impose", "--layout", "4up-booklet", "--binding", "saddle", "--media", "a3",
                             "--orientation", "portrait", "--trim-marks"])
    window.preview()
    wait(app, window)
    assert len(window.result_files) == 1
    assert window.res_pane.doc.pageCount() == 26  # 100 pages -> 104 -> 13 sheets, front and back


def test_mode_survives_a_language_change(app, window, tmp_path, monkeypatch):
    from py_imposition import config, interface
    from py_imposition.gui import window as winmod
    monkeypatch.setenv(config.ENV, str(tmp_path / "cfg"))
    window.set_mode("basic")
    window.basic.set_tokens(["impose", "--layout", "sequential", "--cols", "3", "--rows", "3"])
    try:
        window.change_language("es")
        new = winmod._WINDOWS[-1]
        assert new.mode == "basic" and new.a_basic.isChecked()
        assert namespace(new.basic.tokens())["cols"] == 3
        assert new.basic.layout_type.currentText() == "Secuencial"
    finally:
        interface.use("en")
        interface.translate_argparse()
        for w in list(winmod._WINDOWS):
            w.runner.stop()
            w.close()
        winmod._WINDOWS.clear()


def test_show_document_option(app, window, tmp_path):
    from py_imposition import config
    from py_imposition.gui.window import MainWindow
    assert not window.a_show_document.isChecked()  # off by default
    assert not window.src_pane.isVisibleTo(window)
    window.a_show_document.setChecked(True)
    assert window.src_pane.isVisibleTo(window)
    assert config.get("show_document") is True
    assert "show_document = true" in config.config_path().read_text()
    other = MainWindow()  # (a new window reads the configuration file)
    try:
        assert other.a_show_document.isChecked() and other.src_pane.isVisibleTo(other)
        other.a_show_document.setChecked(False)
        assert config.get("show_document") is False
    finally:
        other.runner.stop()
        other.close()


def test_recent_files(app, window, tmp_path):
    from py_imposition.gui.window import RECENT, MainWindow
    assert window.recent_files() == []
    actions = [a for a in window.m_recent.actions() if not a.isSeparator()]
    assert len(actions) == 1 and not actions[0].isEnabled()  # only "Clear the list", disabled
    docs = []
    for i in range(RECENT + 2):
        doc = tmp_path / f"d{i} & co.pdf"
        assert main(["sample", "--count", "1", "-o", str(doc), "-q"]) == 0
        window.open_path(doc)
        docs.append(doc.resolve())
    window.open_path(docs[3])  # (again: it moves to the top)
    recent = window.recent_files()
    assert len(recent) == RECENT and recent[0] == docs[3] and recent[1] == docs[-1]
    items = [a for a in window.m_recent.actions() if not a.isSeparator()]
    assert items[0].text() == "&1 d3 && co.pdf" and items[0].toolTip() == str(docs[3])
    other = MainWindow()  # (the list is kept in the settings)
    try:
        assert other.recent_files() == recent
        items[1].trigger()
        assert window.original == docs[-1]
        window.clear_recent()
        assert window.recent_files() == []
    finally:
        other.close()


def test_basic_defaults_four_sheets_per_fold(app, window):
    from py_imposition.runner import build_parser
    assert build_parser().parse_args(["impose", "x.pdf"]).sheets_per_fold == 4
    window.basic.reset()
    assert window.basic.sheets.value() == 4 and window.basic.tokens() == ["impose"]
    window.basic.set_tokens(["impose", "--sheets-per-fold", "2"])
    assert window.basic.tokens() == ["impose", "--sheets-per-fold", "2"]


def test_basic_negative_margins_page_trim_enlarge(app, window):
    b = window.basic
    b.reset()
    b.m_left.setValue(-1)
    b.gutter_v.setValue(-0.5)
    b.t_top.setValue(1.5)
    b.enlarge.setChecked(True)
    t = b.tokens()
    assert "--margin-left=-1" in t and "--gutter-v=-0.5" in t and "--enlarge" in t
    assert t[t.index("--page-trim-top") + 1] == "1.5"
    b.reset()
    b.set_tokens(t)
    assert (b.m_left.value(), b.gutter_v.value(), b.t_top.value()) == (-1, -0.5, 1.5)
    assert b.enlarge.isChecked() and b.tokens() == t
    b.auto_scale.setChecked(False)
    assert not b.enlarge.isEnabled() and "--enlarge" not in b.tokens()
