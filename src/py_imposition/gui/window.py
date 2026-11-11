"""Main window of the py-imposition GUI."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QProcess, QProcessEnvironment, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSplitter, QStackedWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import __version__
from ..common import COMMANDS
from .. import config, interface
from ..interface import N_, ntr, tr
from .forms import CommandForm, file_filter, subparsers
from .preview import PdfPane

CATEGORIES = [
    (N_("Impose"), ["booklet", "nup", "step-repeat", "join", "manual"]),
    (N_("Arrange pages"), ["shuffle", "evenodd", "reverse", "duplicate", "delete", "move", "insert", "split"]),
    (N_("Change pages"), ["trim-shift", "creep", "resize", "rotate", "tile", "bleed"]),
    (N_("Stick on / peel off"), ["text", "stick-pdf", "mask", "peel", "merge-data", "sample"]),
    (N_("Information & automation"), ["info", "run", "replay", "watch"]),
]

TITLES = {
    "booklet": N_("Create booklet"), "nup": N_("n-Up pages"), "step-repeat": N_("Step and repeat"), "join": N_("Join two pages"),
    "manual": N_("Manual imposition"), "shuffle": N_("Shuffle pages"), "evenodd": N_("Even/odd pages"),
    "reverse": N_("Reverse pages"), "duplicate": N_("Duplicate pages"), "delete": N_("Delete pages"), "move": N_("Move pages"),
    "insert": N_("Insert pages"), "split": N_("Split / merge (partials)"), "trim-shift": N_("Trim and shift"),
    "creep": N_("Creep"), "resize": N_("Adjust page sizes"), "rotate": N_("Rotate pages"), "tile": N_("Tile pages"),
    "bleed": N_("Define bleeds"), "text": N_("Text and numbers"), "stick-pdf": N_("Stick on PDF pages"),
    "mask": N_("Masking tape"), "peel": N_("Peel off"), "merge-data": N_("Variable data merge"),
    "sample": N_("Sample document"), "info": N_("Imposition info"), "run": N_("Run sequence on files"),
    "replay": N_("Replay (imposition by example)"), "watch": N_("Hot folder"),
}

NO_PREVIEW = {"info", "run", "watch"}
NOT_IN_WINDOW = {"interface"}  # (the window has Settings ▸ Language of the interface)
def wrote_paths(output: str) -> list[Path]:
    """The files a command says it wrote ("Wrote PATH (N pages)"), in the language in use."""
    patterns = []
    for template in (tr("Wrote {path} ({count} page)"), tr("Wrote {path} ({count} pages)"), tr("Wrote {path}")):
        rx = re.escape(template).replace(re.escape("{path}"), "(?P<path>.+?)")
        patterns.append(re.compile("^" + rx.replace(re.escape("{count}"), r"\d+") + "$"))
    found = []
    for line in output.splitlines():
        for rx in patterns:
            m = rx.match(line.strip())
            if m:
                found.append(Path(m.group("path")))
                break
    return found


def warning_prefix() -> str:
    return tr("warning: {msg}").split("{msg}")[0]


_WINDOWS: list = []  # (windows built again in another language must stay referenced)


def install_qt_translations():
    """Qt's own texts (file dialogs, standard buttons) in the language in use."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    app = QApplication.instance()
    for old in getattr(app, "_py_imposition_translators", []):
        app.removeTranslator(old)
    app._py_imposition_translators = []
    code = interface.code()
    QLocale.setDefault(QLocale(code))
    if code == "en":
        return
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase", "qt"):
        t = QTranslator(app)
        if t.load(f"{name}_{code}", folder):
            app.installTranslator(t)
            app._py_imposition_translators.append(t)
            break


def python_command() -> list[str]:
    """How to start the CLI in a child process."""
    return [sys.executable, "-m", "py_imposition"]


# =========================================================================== process runner


class Runner(QObject):
    """Runs one CLI command at a time in a child process."""

    output = Signal(str, bool)  # text, is_error
    finished = Signal(str, int, str, str)  # purpose, exit code, stdout, stderr

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self.purpose = ""
        self._out: list[str] = []
        self._err: list[str] = []

    def busy(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def stop(self):
        if self.busy():
            p = self.proc
            p.finished.disconnect()
            p.kill()
            p.waitForFinished(2000)
            self.proc = None

    def start(self, args: list[str], purpose: str):
        self.stop()
        self.purpose = purpose
        self._out, self._err = [], []
        p = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        p.setProcessEnvironment(env)
        cmd = python_command()
        p.setProgram(cmd[0])
        p.setArguments(cmd[1:] + args)
        p.readyReadStandardOutput.connect(self._read_out)
        p.readyReadStandardError.connect(self._read_err)
        p.finished.connect(self._finished)
        self.proc = p
        self.output.emit("$ py-imposition " + shlex.join(args), False)
        p.start()

    def _read_out(self):
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        self._out.append(text)
        self.output.emit(text.rstrip("\n"), False)

    def _read_err(self):
        text = bytes(self.proc.readAllStandardError()).decode(errors="replace")
        self._err.append(text)
        self.output.emit(text.rstrip("\n"), True)

    def _finished(self, code, _status):
        self.proc = None
        self.finished.emit(self.purpose, code, "".join(self._out), "".join(self._err))


# =========================================================================== sequence panel


class SequencePanel(QWidget):
    """Build, load, save and run sequences of commands."""

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.w = window
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.itemDoubleClicked.connect(lambda _: self.edit_selected())
        self.list.setFont(QFont("monospace"))

        def btn(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        left = QVBoxLayout()
        for b in (
            btn(tr("Add current"), tr("Add the command and options in the form as a step"), self.add_current),
            btn(tr("Replace"), tr("Replace the selected step with the form"), self.replace_selected),
            btn(tr("Edit"), tr("Load the selected step into the form (or double-click)"), self.edit_selected),
            btn(tr("Remove"), tr("Remove the selected step"), self.remove_selected),
            btn(tr("Clear"), tr("Remove all steps"), self.list.clear),
        ):
            left.addWidget(b)
        left.addStretch(1)
        right = QVBoxLayout()
        for b in (
            btn(tr("From document"), tr("Add the commands recorded in the current document (imposition by example)"),
                self.from_document),
            btn(tr("Load…"), tr("Load a sequence file"), self.load),
            btn(tr("Save…"), tr("Save the steps as a sequence file"), self.save),
            btn(tr("Run on document"), tr("Run all steps on the current document and preview the result"),
                self.run_on_document),
            btn(tr("Run on files…"), tr("Run all steps on several PDF files"), self.run_on_files),
        ):
            right.addWidget(b)
        right.addStretch(1)
        lay = QHBoxLayout(self)
        lay.addLayout(left)
        lay.addWidget(self.list, 1)
        lay.addLayout(right)

    def steps(self) -> list[list[str]]:
        return [shlex.split(self.list.item(i).text()) for i in range(self.list.count())]

    def set_steps(self, steps: list[list[str]]):
        self.list.clear()
        for s in steps:
            self.list.addItem(shlex.join(s))

    def add_current(self):
        tokens = self.w.current_tokens(check=True)
        if tokens:
            self.list.addItem(shlex.join(tokens))
            self.list.setCurrentRow(self.list.count() - 1)

    def replace_selected(self):
        item = self.list.currentItem()
        tokens = self.w.current_tokens(check=True)
        if item and tokens:
            item.setText(shlex.join(tokens))

    def edit_selected(self):
        item = self.list.currentItem()
        if item:
            tokens = shlex.split(item.text())
            if tokens and tokens[0] in COMMANDS:
                self.w.select_command(tokens[0])
                self.w.form(tokens[0]).set_tokens(tokens)

    def remove_selected(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)

    def from_document(self):
        if not self.w.source:
            self.w.status(tr("Open a PDF first"), error=True)
            return
        import pikepdf

        from ..pdfutil import get_history
        with pikepdf.open(self.w.source) as pdf:
            hist = get_history(pdf)
        if not hist:
            self.w.status(tr("The current document has no recorded commands"), error=True)
            return
        for s in hist:
            self.list.addItem(shlex.join(s))
        self.w.status(tr('Added {count} recorded step(s)', count=len(hist)))

    def write_toml(self, path: Path, name: str):
        from ..sequence import write_sequence
        text = write_sequence(self.steps(), name)
        prefs = self.w.prefs()
        extra = [f'units = "{prefs["units"]}"']
        if prefs["registration"] != "black":
            extra.append(f'registration = "{prefs["registration"]}"')
        if prefs["bleed"] != "use":
            extra.append(f'bleed = "{prefs["bleed"]}"')
        if prefs["pdfx"]:
            extra.append("pdfx = true")
        lines = text.splitlines()
        path.write_text("\n".join(lines[:1] + extra + lines[1:]) + "\n")

    def load(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Load sequence"), self.w.last_dir(),
                                              file_filter("toml"))
        if not path:
            return
        from ..common import ImpositionError
        from ..sequence import load_sequence
        try:
            steps, prefs = load_sequence(Path(path))
        except ImpositionError as e:
            QMessageBox.warning(self, tr("Load sequence"), str(e))
            return
        self.set_steps(steps)
        self.w.apply_prefs(prefs)
        self.w.status(tr('Loaded {count} step(s) from {name}', count=len(steps), name=Path(path).name))

    def save(self):
        if not self.list.count():
            self.w.status(tr("The sequence is empty"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Save sequence"), self.w.last_dir(),
                                              file_filter("toml"))
        if not path:
            return
        p = Path(path)
        if p.suffix != ".toml":
            p = p.with_suffix(".toml")
        self.write_toml(p, p.stem)
        self.w.status(tr('Saved {page}', page=p))

    def _temp_sequence(self) -> Path | None:
        if not self.list.count():
            self.w.status(tr("The sequence is empty"), error=True)
            return None
        p = self.w.tmp / f"sequence-{self.w.next_id()}.toml"
        self.write_toml(p, "sequence")
        return p

    def run_on_document(self):
        if not self.w.source:
            self.w.status(tr("Open a PDF first"), error=True)
            return
        seq = self._temp_sequence()
        if seq:
            self.w._pending_key = ("sequence", str(self.w.source))
            self.w.run_tokens(["run", "--sequence", str(seq), str(self.w.source)], purpose="preview",
                              with_input=False, label="sequence")

    def run_on_files(self):
        seq = self._temp_sequence()
        if not seq:
            return
        files, _ = QFileDialog.getOpenFileNames(self, tr("PDF files to process"), self.w.last_dir(),
                                                file_filter("pdf"))
        if not files:
            return
        out = QFileDialog.getExistingDirectory(self, tr("Output folder"), str(Path(files[0]).parent))
        if not out:
            return
        self.w.run_tokens(["run", "--sequence", str(seq), "--out-dir", out, "--suffix", "imposed", *files],
                          purpose="batch", with_input=False, add_output=False)


# =========================================================================== main window


class MainWindow(QMainWindow):
    def __init__(self, state: dict | None = None):
        """STATE (from export_state) carries the document over when the window is
        built again, for instance in another language."""
        super().__init__()
        self.setWindowTitle("py-imposition")
        self.setAcceptDrops(True)
        self.settings = QSettings("py-imposition", "py-imposition")
        if state:
            self._tmpdir = state["tmpdir"]
        else:
            self._tmpdir = tempfile.TemporaryDirectory(prefix="py-imposition-")
        self.tmp = Path(self._tmpdir.name)
        self._id = state["id"] if state else 0
        self.original: Path | None = None
        self.source: Path | None = None
        self.undo_stack: list[Path] = []
        self.result_files: list[Path] = []
        self.result_key = None
        self._pending_key = None
        self._apply_after = False
        self.parsers = subparsers()
        self.forms: dict[str, CommandForm] = {}
        self.current = ""

        self.runner = Runner(self)
        self.runner.output.connect(self.log)
        self.runner.finished.connect(self.job_finished)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.auto_preview)

        self._build_toolbar()
        self._build_central()
        self._build_docks()
        self._build_menus()
        self._restore()

    # ----------------------------------------------------------------- construction

    def _build_toolbar(self):
        tb = QToolBar(tr("Preferences"))
        tb.setObjectName("prefs")
        self.addToolBar(tb)
        self.a_open = QAction(tr("Open…"), self, shortcut=QKeySequence.StandardKey.Open, triggered=self.open_dialog)
        tb.addAction(self.a_open)
        self.a_save = QAction(tr("Save document…"), self, shortcut=QKeySequence.StandardKey.Save,
                              triggered=self.save_document)
        tb.addAction(self.a_save)
        self.a_undo = QAction(tr("Undo apply"), self, shortcut=QKeySequence.StandardKey.Undo, triggered=self.undo)
        tb.addAction(self.a_undo)
        tb.addSeparator()
        tb.addWidget(QLabel(tr(" Units ")))
        self.units = QComboBox()
        self.units.addItems(["cm", "mm", "in", "pt"])
        tb.addWidget(self.units)
        tb.addWidget(QLabel(tr("  Registration ")))
        self.registration = QComboBox()
        self.registration.addItems(["black", "cmyk", "all"])
        self.registration.setToolTip(tr("Colour of crop marks and registration-coloured text"))
        tb.addWidget(self.registration)
        tb.addWidget(QLabel(tr("  Bleeds ")))
        self.bleed = QComboBox()
        self.bleed.addItems(["use", "ignore"])
        self.bleed.setToolTip(tr("Use page bleed boxes when imposing, or impose the visible page only"))
        tb.addWidget(self.bleed)
        self.pdfx = QCheckBox(tr("PDF/X"))
        self.pdfx.setToolTip(tr("Keep a TrimBox when bleeds are removed"))
        tb.addWidget(self.pdfx)
        for w in (self.units, self.registration, self.bleed):
            w.currentIndexChanged.connect(lambda _: self.schedule())
        self.pdfx.toggled.connect(lambda _: self.schedule())

    def _build_central(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(190)
        listed = set()
        for cat, names in CATEGORIES:
            top = QTreeWidgetItem([tr(cat)])
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            for n in names:
                if n in COMMANDS:
                    it = QTreeWidgetItem([tr(TITLES.get(n, n))])
                    it.setData(0, Qt.ItemDataRole.UserRole, n)
                    it.setToolTip(0, f"{n}: {tr(COMMANDS[n].help)}")
                    top.addChild(it)
                    listed.add(n)
            self.tree.addTopLevelItem(top)
        others = sorted(set(COMMANDS) - listed - NOT_IN_WINDOW)
        if others:
            top = QTreeWidgetItem([tr("Other")])
            for n in others:
                it = QTreeWidgetItem([n])
                it.setData(0, Qt.ItemDataRole.UserRole, n)
                top.addChild(it)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self._tree_changed)

        # centre: title, form, actions
        self.cmd_title = QLabel()
        self.cmd_title.setStyleSheet("font-size: 15pt; font-weight: bold;")
        self.cmd_line = QLabel()
        self.cmd_line.setWordWrap(True)
        self.cmd_line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # (the theme's own text colour: readable in light and dark themes)
        self.cmd_line.setStyleSheet("font-family: monospace;")
        self.stack = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.stack)

        self.b_preview = QPushButton(tr("Preview"))
        self.b_preview.setToolTip(tr("Run the command on the current document and show the result (F5)"))
        self.b_preview.clicked.connect(self.preview)
        self.b_apply = QPushButton(tr("Apply"))
        self.b_apply.setToolTip(tr("Make the result the current document, to continue with another command "
                                "(Ctrl+Enter)"))
        self.b_apply.clicked.connect(self.apply)
        self.b_save_result = QPushButton(tr("Save result…"))
        self.b_save_result.clicked.connect(self.save_result)
        self.b_reset = QPushButton(tr("Defaults"))
        self.b_reset.setToolTip(tr("Reset this command's options"))
        self.b_reset.clicked.connect(lambda: self.form(self.current).reset())
        self.b_add = QPushButton(tr("Add to sequence"))
        self.b_add.clicked.connect(lambda: self.seq.add_current())
        self.auto = QCheckBox(tr("Auto preview"))
        self.auto.setChecked(True)
        self.auto.setToolTip(tr("Preview automatically after changing options"))
        self.b_stop = QPushButton(tr("Stop"))
        self.b_stop.clicked.connect(self.stop)
        self.b_stop.setEnabled(False)

        actions = QVBoxLayout()
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for b in (self.b_preview, self.b_apply, self.b_save_result):
            row1.addWidget(b)
        row1.addStretch(1)
        row1.addWidget(self.b_stop)
        for b in (self.b_add, self.b_reset):
            row2.addWidget(b)
        row2.addStretch(1)
        row2.addWidget(self.auto)
        actions.addLayout(row1)
        actions.addLayout(row2)

        middle = QWidget()
        ml = QVBoxLayout(middle)
        ml.addWidget(self.cmd_title)
        ml.addWidget(self.cmd_line)
        ml.addWidget(scroll, 1)
        ml.addLayout(actions)

        # previews
        self.src_pane = PdfPane(tr("Document"))
        self.res_pane = PdfPane(tr("Result"))
        self.res_pane.output_selected.connect(self._show_output)
        previews = QSplitter(Qt.Orientation.Horizontal)
        previews.addWidget(self.src_pane)
        previews.addWidget(self.res_pane)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(self.tree)
        self.split.addWidget(middle)
        self.split.addWidget(previews)
        self.split.setStretchFactor(1, 2)
        self.split.setStretchFactor(2, 5)
        self.split.setSizes([210, 520, 900])
        self.setCentralWidget(self.split)

    def _build_docks(self):
        self.seq = SequencePanel(self)
        d1 = QDockWidget(tr("Sequence"), self)
        d1.setObjectName("sequence")
        d1.setWidget(self.seq)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, d1)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setFont(QFont("monospace"))
        self.logbox.setMaximumBlockCount(5000)
        d2 = QDockWidget(tr("Log"), self)
        d2.setObjectName("log")
        d2.setWidget(self.logbox)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, d2)
        self.tabifyDockWidget(d1, d2)
        d1.raise_()
        self.docks = (d1, d2)

    def _build_menus(self):
        m = self.menuBar().addMenu(tr("&File"))
        m.addAction(self.a_open)
        m.addAction(self.a_save)
        m.addAction(QAction(tr("Save result…"), self, shortcut="Ctrl+Shift+S", triggered=self.save_result))
        m.addAction(QAction(tr("Revert to original"), self, triggered=self.revert))
        m.addSeparator()
        m.addAction(QAction(tr("Quit"), self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close))
        m = self.menuBar().addMenu(tr("&Run"))
        m.addAction(QAction(tr("Preview"), self, shortcut="F5", triggered=self.preview))
        m.addAction(QAction(tr("Apply"), self, shortcut="Ctrl+Return", triggered=self.apply))
        m.addAction(self.a_undo)
        m.addAction(QAction(tr("Stop"), self, shortcut="Esc", triggered=self.stop))
        m.addSeparator()
        m.addAction(QAction(tr("Copy command line"), self, triggered=self.copy_command_line))
        m = self.menuBar().addMenu(tr("&View"))
        for d in self.docks:
            m.addAction(d.toggleViewAction())
        m = self.menuBar().addMenu(tr("&Settings"))
        lang = m.addMenu(tr("Language of the interface"))
        group = QActionGroup(self)
        for code, name in interface.names().items():
            act = QAction(name, self, checkable=True)
            act.setChecked(code == interface.code())
            act.triggered.connect(lambda _=False, c=code: self.change_language(c))
            group.addAction(act)
            lang.addAction(act)
        m = self.menuBar().addMenu(tr("&Help"))
        m.addAction(QAction(tr("Command-line help for this command"), self, triggered=self.show_cli_help))
        m.addAction(QAction(tr("About"), self, triggered=self.about))

    # ----------------------------------------------------------------- settings

    def _restore(self):
        geo = self.settings.value("geometry")
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)
        else:
            self.resize(1500, 950)
        state = self.settings.value("state")
        if isinstance(state, QByteArray):
            self.restoreState(state)
        else:
            QTimer.singleShot(0, lambda: self.resizeDocks([self.docks[0]], [190], Qt.Orientation.Vertical))
        self.apply_prefs({k: self.settings.value(f"prefs/{k}") for k in ("units", "registration", "bleed")
                          if self.settings.value(f"prefs/{k}")})
        self.pdfx.setChecked(self.settings.value("prefs/pdfx", "false") == "true")
        self.auto.setChecked(self.settings.value("auto_preview", "true") != "false")
        try:
            steps = json.loads(self.settings.value("sequence", "[]"))
            self.seq.set_steps(steps)
        except (TypeError, ValueError):
            pass
        last = self.settings.value("command", "booklet")
        self.select_command(last if last in COMMANDS else "booklet")

    def closeEvent(self, event):
        self.runner.stop()
        self.save_settings()
        super().closeEvent(event)

    def save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        for k, v in self.prefs().items():
            self.settings.setValue(f"prefs/{k}", "true" if v is True else "false" if v is False else v)
        self.settings.setValue("auto_preview", "true" if self.auto.isChecked() else "false")
        self.settings.setValue("command", self.current)
        self.settings.setValue("sequence", json.dumps(self.seq.steps()))
        for name, form in self.forms.items():
            self.settings.setValue(f"forms/{name}", json.dumps(form.tokens()))
        self.settings.sync()

    def export_state(self) -> dict:
        """What a new window needs to carry on with the same document."""
        return {"tmpdir": self._tmpdir, "id": self._id, "original": self.original, "source": self.source,
                "undo": list(self.undo_stack)}

    def adopt_state(self, state: dict):
        self.original = state["original"]
        self.undo_stack = state["undo"]
        if state["source"]:
            self.set_source(state["source"])

    # ----------------------------------------------------------------- language

    def change_language(self, code: str):
        """Use CODE for the interface, keep it in the configuration file, and
        build the window again in that language."""
        if code == interface.code():
            return
        if not interface.use(code):
            QMessageBox.warning(self, tr("Language of the interface"),
                                tr("The language of the interface could not be changed: {error}",
                                   error=interface.error()))
            interface.use(config.get("interface"))
            return
        try:
            config.set("interface", code)
        except OSError as e:
            self.status(tr("Could not keep the setting: {error}", error=e), error=True)
        interface.translate_argparse()
        install_qt_translations()
        self.runner.stop()
        self.save_settings()
        state = self.export_state()
        self._tmpdir = None  # (the new window keeps the temporary files)
        new = MainWindow(state)
        new.adopt_state(state)
        new.restoreGeometry(self.saveGeometry())
        new.show()
        app = QApplication.instance()
        app.setProperty("main_window_id", id(new))
        _WINDOWS.append(new)
        self.hide()
        self.deleteLater()
        if self in _WINDOWS:
            _WINDOWS.remove(self)

    def last_dir(self) -> str:
        return self.settings.value("last_dir", str(Path.home()))

    def prefs(self) -> dict:
        return {"units": self.units.currentText(), "registration": self.registration.currentText(),
                "bleed": self.bleed.currentText(), "pdfx": self.pdfx.isChecked()}

    def apply_prefs(self, prefs: dict):
        for key, combo in (("units", self.units), ("registration", self.registration), ("bleed", self.bleed)):
            if key in prefs and combo.findText(str(prefs[key])) >= 0:
                combo.setCurrentText(str(prefs[key]))
        if "pdfx" in prefs:
            self.pdfx.setChecked(bool(prefs["pdfx"]))

    def pref_tokens(self) -> list[str]:
        p = self.prefs()
        out = ["--interface", interface.code(), "--units", p["units"]]
        if p["registration"] != "black":
            out += ["--registration", p["registration"]]
        if p["bleed"] != "use":
            out += ["--bleed", p["bleed"]]
        if p["pdfx"]:
            out.append("--pdfx")
        return out

    # ----------------------------------------------------------------- commands and forms

    def form(self, name: str) -> CommandForm:
        if name not in self.forms:
            f = CommandForm(name, self.parsers[name])
            saved = self.settings.value(f"forms/{name}")
            if saved:
                try:
                    f.set_tokens(json.loads(saved))
                except (TypeError, ValueError):
                    pass
            f.changed.connect(self._form_changed)
            self.forms[name] = f
            self.stack.addWidget(f)
        return self.forms[name]

    def select_command(self, name: str):
        it = self._find_item(name)
        if it is not None and self.tree.currentItem() is not it:
            self.tree.setCurrentItem(it)
        else:
            self._activate(name)

    def _find_item(self, name):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                if top.child(j).data(0, Qt.ItemDataRole.UserRole) == name:
                    return top.child(j)
        return None

    def _tree_changed(self, item, _prev):
        name = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if name:
            self._activate(name)

    def _activate(self, name: str):
        self.current = name
        f = self.form(name)
        self.stack.setCurrentWidget(f)
        self.cmd_title.setText(tr(TITLES.get(name, name)))
        previewable = name not in NO_PREVIEW
        self.b_preview.setText(tr({"info": N_("Show info"), "run": N_("Run"),
                                   "watch": N_("Start watching")}.get(name, N_("Preview"))))
        self.b_apply.setEnabled(previewable)
        self.b_save_result.setEnabled(previewable)
        self._form_changed()

    def current_tokens(self, check: bool = False) -> list[str] | None:
        f = self.form(self.current)
        if check:
            missing = f.missing_required()
            if missing:
                self.status("Required: " + ", ".join(missing), error=True)
                return None
        return f.tokens()

    def _form_changed(self):
        tokens = self.form(self.current).tokens()
        cmd = COMMANDS[self.current]
        shown = list(tokens)
        if cmd.needs_input is True or (cmd.needs_input == "optional" and self.source):
            shown.append(self.source.name if self.source else "INPUT.pdf")
        self.cmd_line.setText("py-imposition " + shlex.join(shown))
        self.schedule()

    def schedule(self):
        if self.auto.isChecked() and self.current not in NO_PREVIEW:
            self.timer.start()

    def auto_preview(self):
        f = self.form(self.current)
        if f.missing_required():
            return
        if COMMANDS[self.current].needs_input is True and not self.source:
            return
        if self.current == "replay" and f.by_option.get("--export") and f.by_option["--export"].has_value():
            return
        self.preview(quiet=True)

    # ----------------------------------------------------------------- running

    def next_id(self) -> int:
        self._id += 1
        return self._id

    def run_tokens(self, tokens: list[str], purpose: str, with_input: bool = True, add_output: bool = True,
                   label: str | None = None, quiet: bool = False):
        name = tokens[0]
        cmd = COMMANDS[name]
        args = list(tokens[:1]) + self.pref_tokens() + list(tokens[1:])
        if with_input:
            if cmd.needs_input is True:
                if not self.source:
                    self.status(tr("Open a PDF first (File ▸ Open, or drop a file on the window)"), error=True)
                    return
                args.append(str(self.source))
            elif cmd.needs_input == "optional" and self.source:
                args.append(str(self.source))
            elif name == "replay":
                if not self.source:
                    self.status(tr("Open a PDF first"), error=True)
                    return
                args.append(str(self.source))
        self._out_base = None
        if add_output and name not in ("info", "watch", "run") or (name == "run" and label == "sequence"):
            self._out_base = self.tmp / f"result-{self.next_id()}.pdf"
            args += ["-o", str(self._out_base)]
        self._job_label = label or name
        self._job_key = self._pending_key
        self.b_stop.setEnabled(True)
        if not quiet:
            self.status(tr('Running {job_label}…', job_label=self._job_label))
        else:
            self.statusBar().showMessage(tr('Previewing {job_label}…', job_label=self._job_label))
        self.runner.start(args, purpose)

    def key(self):
        return (tuple(self.form(self.current).tokens()), tuple(self.pref_tokens()), str(self.source))

    def preview(self, quiet: bool = False):
        if self.current == "watch" and self.runner.busy() and self.runner.purpose == "watch":
            self.stop()
            return
        tokens = self.current_tokens(check=True)
        if not tokens:
            return
        purpose = {"info": "info", "run": "batch", "watch": "watch"}.get(self.current, "preview")
        self._pending_key = self.key()
        self._apply_after = False
        self.run_tokens(tokens, purpose, quiet=quiet)
        if purpose == "watch" and self.runner.busy():
            self.b_preview.setText(tr("Stop watching"))

    def apply(self):
        if self.current in NO_PREVIEW:
            return
        fresh = self.result_key in (self.key(), ("sequence", str(self.source)))
        if self.result_files and fresh and not self.runner.busy():
            self._apply_result()
            return
        tokens = self.current_tokens(check=True)
        if not tokens:
            return
        self._pending_key = self.key()
        self._apply_after = True
        self.run_tokens(tokens, "preview")

    def stop(self):
        was = self.runner.purpose
        self.runner.stop()
        self.b_stop.setEnabled(False)
        if was == "watch":
            self.b_preview.setText(tr("Start watching"))
        self.status(tr("Stopped"))

    def job_finished(self, purpose: str, code: int, out: str, err: str):
        self.b_stop.setEnabled(False)
        if purpose == "watch":
            self.b_preview.setText(tr("Start watching"))
        if code != 0:
            lines = [ln for ln in err.strip().splitlines() if ln.strip()]
            msg = lines[-1] if lines else f"failed (exit code {code})"
            self.status(f"{self._job_label}: {msg}", error=True)
            self._apply_after = False
            return
        if purpose == "info":
            self.show_text(tr("Imposition info"), out)
            self.status(tr("Done"))
            return
        if purpose == "batch":
            n = len(wrote_paths(out))
            self.status(tr('Processed: {number} file(s) written', number=n))
            return
        files = []
        if self._out_base is not None:
            if self._out_base.exists():
                files = [self._out_base]
            else:
                files = sorted(self._out_base.parent.glob(self._out_base.stem + "-*.pdf"))
        if not files:
            files = [f for f in wrote_paths(out) if f.suffix == ".pdf"]
        if not files:
            self.status(tr('{job_label}: done (no PDF produced)', job_label=self._job_label))
            return
        self.result_files = files
        self.result_key = self._job_key
        names = [self._suffix(f) or "result" for f in files]
        self.res_pane.set_outputs(names)
        self.res_pane.load(files[0])
        warn = [ln for ln in err.splitlines() if ln.startswith(warning_prefix())]
        self.status(ntr("{label}: done — {count} warning, see Log", "{label}: done — {count} warnings, see Log",
                        len(warn), label=self._job_label) if warn else tr("{label}: done", label=self._job_label),
                    error=False)
        if self._apply_after:
            self._apply_after = False
            self._apply_result()

    def _suffix(self, f: Path) -> str:
        if self._out_base is not None and f.stem.startswith(self._out_base.stem + "-"):
            return f.stem[len(self._out_base.stem) + 1:]
        return ""

    def _show_output(self, index: int):
        if 0 <= index < len(self.result_files):
            self.res_pane.load(self.result_files[index])

    def _apply_result(self):
        if len(self.result_files) != 1:
            QMessageBox.information(self, tr("Apply"),
                                    tr("This command produced several documents. Use “Save result…” to save them."))
            return
        new = self.tmp / f"document-{self.next_id()}.pdf"
        shutil.copyfile(self.result_files[0], new)
        if self.source:
            self.undo_stack.append(self.source)
        self.set_source(new)
        self.status(tr('Applied {current}. The result is now the current document.', current=self.current))

    # ----------------------------------------------------------------- documents

    def set_source(self, path: Path | None):
        self.source = path
        self.result_files = []
        self.result_key = None
        self.res_pane.set_outputs([])
        self.res_pane.clear("")
        steps = len(self.undo_stack)
        note = ntr("{count} command applied", "{count} commands applied", steps) if steps else ""
        self.src_pane.load(path, note)
        name = self.original.name if self.original else (path.name if path else "")
        if name:
            self.setWindowTitle(tr("py-imposition — {name} (modified)", name=name) if steps
                                else f"py-imposition — {name}")
        else:
            self.setWindowTitle("py-imposition")
        self._form_changed()

    def open_path(self, path: Path):
        if not path.is_file():
            self.status(tr('{path} not found', path=path), error=True)
            return
        self.settings.setValue("last_dir", str(path.parent))
        self.original = path
        self.undo_stack = []
        self.set_source(path)
        self.status(tr('Opened {path}', path=path))

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Open PDF"), self.last_dir(), file_filter("pdf"))
        if path:
            self.open_path(Path(path))

    def undo(self):
        if not self.undo_stack:
            self.status(tr("Nothing to undo"), error=True)
            return
        self.set_source(self.undo_stack.pop())
        self.status(tr("Undone"))

    def revert(self):
        if self.original:
            self.undo_stack = []
            self.set_source(self.original)
            self.status(tr("Reverted to the original document"))

    def _save_target(self, title: str, suggested: str) -> Path | None:
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path(self.last_dir()) / suggested),
                                              tr("PDF files (*.pdf)"))
        if not path:
            return None
        p = Path(path)
        if p.suffix.lower() != ".pdf":
            p = p.with_suffix(".pdf")
        self.settings.setValue("last_dir", str(p.parent))
        return p

    def save_document(self):
        if not self.source:
            self.status(tr("Nothing to save"), error=True)
            return
        stem = self.original.stem if self.original else "document"
        p = self._save_target("Save document", f"{stem}-imposed.pdf")
        if p:
            if p.resolve() == self.source.resolve():
                self.status(tr("That is the file currently open"), error=True)
                return
            shutil.copyfile(self.source, p)
            self.status(tr('Saved {page}', page=p))

    def save_result(self):
        if not self.result_files:
            self.status(tr("No result yet: click Preview first"), error=True)
            return
        stem = self.original.stem if self.original else "document"
        p = self._save_target("Save result", f"{stem}-{self.current}.pdf")
        if not p:
            return
        written = []
        for f in self.result_files:
            suffix = self._suffix(f)
            target = p.with_name(f"{p.stem}-{suffix}.pdf") if suffix and len(self.result_files) > 1 else p
            shutil.copyfile(f, target)
            written.append(target.name)
        self.status("Saved " + ", ".join(written))

    # ----------------------------------------------------------------- drag and drop

    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for u in event.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"):
                self.open_path(Path(u.toLocalFile()))
                break

    # ----------------------------------------------------------------- messages

    def status(self, text: str, error: bool = False):
        self.statusBar().setStyleSheet("color: #c0392b;" if error else "")
        self.statusBar().showMessage(text, 0 if error else 8000)
        if error:
            self.log(text, True)

    def log(self, text: str, is_error: bool = False):
        if text:
            self.logbox.appendPlainText(text)

    def show_text(self, title: str, text: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(760, 520)
        box = QPlainTextEdit(text)
        box.setReadOnly(True)
        box.setFont(QFont("monospace"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addWidget(box)
        lay.addWidget(bb)
        dlg.exec()

    def show_cli_help(self):
        self.show_text(tr('py-imposition {current} --help', current=self.current), self.parsers[self.current].format_help())

    def copy_command_line(self):
        QApplication.clipboard().setText(self.cmd_line.text())
        self.status(tr("Command line copied"))

    def about(self):
        QMessageBox.about(self, tr("About py-imposition"),
                          tr('<b>py-imposition {version}</b><p>A PDF imposition toolkit.</p><p>Licensed under the GNU General Public License, version 3 or later.</p>', version=__version__))
