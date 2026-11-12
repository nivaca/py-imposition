"""The basic mode's single form: the "impose" command, laid out as a usual
imposition dialog (Layout, Profiles, General, Binding, Gutters, Paper,
Margins, Printer marks), with named profiles of settings.
"""

from __future__ import annotations

import json
import re
import shlex

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QMessageBox, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..interface import N_, tr
from ..units import PAPER_SIZES, UNITS, parse_length

LAYOUT_NAMES = [("2up-booklet", N_("2-Up Booklet")), ("4up-booklet", N_("4-Up Booklet")),
                ("8up-booklet", N_("8-Up Booklet")), ("cut-stacks", N_("Cut stacks")),
                ("sequential", N_("Sequential")), ("step-repeat", N_("Step and Repeat"))]
MEDIA = ["letter", "legal", "tabloid", "a2", "a3", "a4", "a5", "b4", "b5"]
NEW_PROFILE = N_("<new profile>")
BOOKLETS = {"2up-booklet", "4up-booklet", "8up-booklet"}
GRID = {"cut-stacks", "sequential", "step-repeat"}


class BasicPanel(QWidget):
    """Options of the "impose" command; tokens() gives its command line."""

    changed = Signal()
    profiles_changed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.name = "impose"
        self.by_option: dict = {}  # (the window asks forms for this)
        self._loading = False
        self._units = window.units.currentText()
        self.lengths: list[QDoubleSpinBox] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Layout
        box, form = self._group(tr("Layout"))
        self.layout_type = QComboBox()
        for value, label in LAYOUT_NAMES:
            self.layout_type.addItem(tr(label), value)
        self.cols = self._spin(1, 20, 2)
        self.rows = self._spin(1, 20, 2)
        form.addRow(tr("Type"), self.layout_type)
        form.addRow(tr("Columns"), self.cols)
        form.addRow(tr("Rows"), self.rows)
        outer.addWidget(box)

        # Profiles
        box = QGroupBox(tr("Profiles"))
        grid = QGridLayout(box)
        self.profile = QComboBox()
        self.b_save = QPushButton(tr("Save"))
        self.b_save_as = QPushButton(tr("Save As"))
        self.b_delete = QPushButton(tr("Delete"))
        self.on_menu = QCheckBox(tr("Show on Menu"))
        self.on_menu.setToolTip(tr("Show this profile in the Profiles menu, for faster access"))
        grid.addWidget(QLabel(tr("Name")), 0, 0)
        grid.addWidget(self.profile, 0, 1, 1, 3)
        grid.addWidget(self.b_save, 1, 1)
        grid.addWidget(self.b_save_as, 1, 2)
        grid.addWidget(self.b_delete, 1, 3)
        grid.addWidget(self.on_menu, 2, 1, 1, 3)
        self.b_save.clicked.connect(self.save_profile)
        self.b_save_as.clicked.connect(lambda: self.save_profile(new_name=True))
        self.b_delete.clicked.connect(self.delete_profile)
        self.profile.activated.connect(lambda _: self.load_profile(self.profile.currentData()))
        self.on_menu.toggled.connect(self._menu_toggled)
        outer.addWidget(box)

        # General
        box, form = self._group(tr("General"))
        self.units = QComboBox()
        self.units.addItems(["cm", "mm", "in", "pt"])
        self.units.setCurrentText(self._units)
        form.addRow(tr("Units"), self.units)
        outer.addWidget(box)

        # Binding
        box, form = self._group(tr("Binding"))
        self.binding = QComboBox()
        self.binding.addItem(tr("Saddle-Stitching"), "saddle")
        self.binding.addItem(tr("Perfect Binding"), "perfect")
        self.sheets = self._spin(1, 64, 4)
        self.direction = QComboBox()
        self.direction.addItem(tr("Left"), "left")
        self.direction.addItem(tr("Right"), "right")
        self.double = QCheckBox(tr("Double Sided"))
        form.addRow(tr("Type"), self.binding)
        form.addRow(tr("Sheets per fold"), self.sheets)
        form.addRow(tr("Binding"), self.direction)
        form.addRow(self.double)
        outer.addWidget(box)

        # Gutters
        box, form = self._group(tr("Gutters"))
        self.gutter_v = self._length(negative=True)
        self.gutter_h = self._length(negative=True)
        self.spread = self._length(negative=True)
        self.creep = self._length()
        form.addRow(tr("Vertical"), self.gutter_v)
        form.addRow(tr("Horizontal"), self.gutter_h)
        form.addRow(tr("Spread"), self.spread)
        form.addRow(tr("Creep"), self.creep)
        outer.addWidget(box)

        # Paper: media
        box = QGroupBox(tr("Paper"))
        pv = QVBoxLayout(box)
        self.autosize = QRadioButton(tr("Autosize Media"))
        self.fit = QRadioButton(tr("Fit to Media Size"))
        media_group = QButtonGroup(self)
        media_group.addButton(self.autosize)
        media_group.addButton(self.fit)
        pv.addWidget(self.autosize)
        pv.addWidget(self.fit)
        form = QFormLayout()
        self.media = QComboBox()
        for name in MEDIA:
            self.media.addItem(name.capitalize() if name.isalpha() else name.upper(), name)
        self.media.addItem(tr("Custom"), "custom")
        self.portrait = QRadioButton(tr("Portrait"))
        self.landscape = QRadioButton(tr("Landscape"))
        orient_group = QButtonGroup(self)
        orient_group.addButton(self.portrait)
        orient_group.addButton(self.landscape)
        orient = QHBoxLayout()
        orient.addWidget(self.portrait)
        orient.addWidget(self.landscape)
        orient.addStretch(1)
        self.width = self._length(maximum=5000)
        self.height = self._length(maximum=5000)
        form.addRow(tr("Size"), self.media)
        form.addRow("", self._wrap(orient))
        form.addRow(tr("Width"), self.width)
        form.addRow(tr("Height"), self.height)
        pv.addLayout(form)
        self.auto_rotate = QCheckBox(tr("Auto-rotate"))
        self.auto_rotate.setToolTip(tr("Turn each page 90° when that fits its place on the sheet better"))
        self.auto_scale = QCheckBox(tr("Auto Scale"))
        self.auto_scale.setToolTip(tr("Shrink pages that are larger than their place on the sheet"))
        self.enlarge = QCheckBox(tr("Enlarge"))
        self.enlarge.setToolTip(tr("Also enlarge pages that are smaller than their place on the sheet, to fill it"))
        pv.addWidget(self.auto_rotate)
        pv.addWidget(self.auto_scale)
        pv.addWidget(self.enlarge)
        outer.addWidget(box)

        # Margins
        box, form = self._group(tr("Margins"))
        box.setToolTip(tr("Negative margins let the pages run off the sheet's edges"))
        self.m_top, self.m_bottom, self.m_left, self.m_right = (self._length(negative=True) for _ in range(4))
        form.addRow(tr("Top"), self.m_top)
        form.addRow(tr("Bottom"), self.m_bottom)
        form.addRow(tr("Left"), self.m_left)
        form.addRow(tr("Right"), self.m_right)
        outer.addWidget(box)

        # Page trim
        box, form = self._group(tr("Page Trim"))
        box.setToolTip(tr("Cut this much off the edges of every page (its white margins), so that its content "
                          "fills more of the sheet; tick Enlarge to let the pages grow"))
        self.t_top, self.t_bottom, self.t_left, self.t_right = (self._length() for _ in range(4))
        form.addRow(tr("Top"), self.t_top)
        form.addRow(tr("Bottom"), self.t_bottom)
        form.addRow(tr("Left"), self.t_left)
        form.addRow(tr("Right"), self.t_right)
        outer.addWidget(box)

        # Printer marks
        box = QGroupBox(tr("Printer Marks"))
        mv = QVBoxLayout(box)
        self.trim_marks = QCheckBox(tr("Trim Marks"))
        self.bleed_marks = QCheckBox(tr("Bleed Marks"))
        self.reg_marks = QCheckBox(tr("Registration Marks"))
        self.page_info = QCheckBox(tr("Page Information"))
        for wdg, tip in ((self.trim_marks, N_("Marks where the pages are to be trimmed")),
                         (self.bleed_marks, N_("The outline of the bleed area of pages that have one")),
                         (self.reg_marks, N_("Targets at the sides of the sheet, for aligning plates")),
                         (self.page_info, N_("The document name, sheet number, date and time at the top left"))):
            wdg.setToolTip(tr(tip))
            mv.addWidget(wdg)
        outer.addWidget(box)
        outer.addStretch(1)

        self.reset(emit=False)
        signals = {QComboBox: "currentIndexChanged", QSpinBox: "valueChanged", QDoubleSpinBox: "valueChanged",
                   QCheckBox: "toggled", QRadioButton: "toggled"}
        for kind, sig in signals.items():
            for wdg in self.findChildren(kind):
                if wdg in (self.profile, self.on_menu, self.units) or type(wdg) is not kind:
                    continue
                getattr(wdg, sig).connect(lambda *_: self._changed())
        self.units.currentTextChanged.connect(self._units_changed)
        self.media.currentIndexChanged.connect(lambda _: self._show_media_size())
        self.portrait.toggled.connect(lambda _: self._show_media_size())
        self.refresh_profiles()

    # ----------------------------------------------------------------- building blocks

    def _group(self, title: str):
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return box, form

    @staticmethod
    def _wrap(layout) -> QWidget:
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    @staticmethod
    def _spin(lo: int, hi: int, value: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        return s

    def _length(self, maximum: float = 1000, negative: bool = False) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(-maximum if negative else 0, maximum)
        s.setDecimals(2)
        s.setSingleStep(0.1)
        s.setSuffix(f" {self._units}")
        self.lengths.append(s)
        return s

    # ----------------------------------------------------------------- state

    def reset(self, emit: bool = True):
        """The defaults: a 2-up booklet, perfect bound four sheets per fold, on Legal landscape."""
        self._loading = True
        self.layout_type.setCurrentIndex(0)
        self.cols.setValue(2)
        self.rows.setValue(2)
        self.binding.setCurrentIndex(1)
        self.sheets.setValue(4)
        self.direction.setCurrentIndex(0)
        self.double.setChecked(True)
        for s in self.lengths:
            s.setValue(0)
        self.fit.setChecked(True)
        self.media.setCurrentIndex(MEDIA.index("legal"))
        self.landscape.setChecked(True)
        self.auto_rotate.setChecked(False)
        self.auto_scale.setChecked(True)
        self.enlarge.setChecked(False)
        for c in (self.trim_marks, self.bleed_marks, self.reg_marks, self.page_info):
            c.setChecked(False)
        self._loading = False
        self._show_media_size()
        self._enable()
        if emit:
            self.changed.emit()

    def _changed(self):
        if self._loading:
            return
        self._enable()
        self.changed.emit()

    def _enable(self):
        """Grey out what doesn't apply to the chosen layout."""
        layout = self.layout_type.currentData()
        booklet = layout in BOOKLETS
        self.cols.setEnabled(layout in GRID)
        self.rows.setEnabled(layout in GRID)
        self.binding.setEnabled(booklet)
        self.sheets.setEnabled(booklet and self.binding.currentData() == "perfect")
        self.direction.setEnabled(layout not in ("cut-stacks", "step-repeat"))
        self.double.setEnabled(layout in BOOKLETS | {"cut-stacks"})
        self.spread.setEnabled(layout == "8up-booklet")
        self.creep.setEnabled(booklet)
        fit = self.fit.isChecked()
        custom = self.media.currentData() == "custom"
        self.media.setEnabled(fit)
        self.portrait.setEnabled(fit and not custom)
        self.landscape.setEnabled(fit and not custom)
        self.width.setEnabled(fit and custom)
        self.height.setEnabled(fit and custom)
        self.enlarge.setEnabled(self.auto_scale.isChecked())

    def _show_media_size(self):
        """A named size shows its dimensions (in the orientation chosen)."""
        name = self.media.currentData()
        if name in PAPER_SIZES:
            w, h = PAPER_SIZES[name]
            if self.landscape.isChecked():
                w, h = max(w, h), min(w, h)
            f = UNITS[self._units]
            self._loading, was = True, self._loading
            self.width.setValue(w / f)
            self.height.setValue(h / f)
            self._loading = was
        self._enable()

    def _units_changed(self, unit: str):
        old, self._units = self._units, unit
        factor = UNITS[old] / UNITS[unit]
        self._loading, was = True, self._loading
        for s in self.lengths:
            s.setSuffix(f" {unit}")
            s.setValue(s.value() * factor)
        self._loading = was
        self.w.units.setCurrentText(unit)
        self.changed.emit()

    @staticmethod
    def _num(v: float) -> str:
        return f"{v:.4g}"

    @classmethod
    def _length_opt(cls, opt: str, v: float) -> list[str]:
        """OPT and its value; a negative one joined with "=" (so it isn't taken for an option)."""
        return [f"{opt}={cls._num(v)}"] if v < 0 else [opt, cls._num(v)]

    def tokens(self) -> list[str]:
        """The "impose" command line for these settings (only what differs from the defaults)."""
        t = ["impose"]
        layout = self.layout_type.currentData()
        if layout != "2up-booklet":
            t += ["--layout", layout]
        if layout in GRID:
            t += ["--cols", str(self.cols.value()), "--rows", str(self.rows.value())]
        if layout in BOOKLETS:
            if self.binding.currentData() != "perfect":
                t += ["--binding", self.binding.currentData()]
            elif self.sheets.value() != 4:
                t += ["--sheets-per-fold", str(self.sheets.value())]
        if self.direction.isEnabled() and self.direction.currentData() != "left":
            t += ["--direction", "right"]
        if self.double.isEnabled() and not self.double.isChecked():
            t.append("--single-sided")
        for opt, s in (("--gutter-v", self.gutter_v), ("--gutter-h", self.gutter_h)):
            if s.value():
                t += self._length_opt(opt, s.value())
        if self.spread.isEnabled() and self.spread.value():
            t += self._length_opt("--spread", self.spread.value())
        if self.creep.isEnabled() and self.creep.value():
            t += self._length_opt("--creep", self.creep.value())
        if self.autosize.isChecked():
            t += ["--media", "auto"]
        elif self.media.currentData() == "custom":
            t += ["--media", f"{self._num(self.width.value())}x{self._num(self.height.value())}{self._units}"]
        else:
            if self.media.currentData() != "legal":
                t += ["--media", self.media.currentData()]
            if self.portrait.isChecked():
                t += ["--orientation", "portrait"]
        if self.auto_rotate.isChecked():
            t.append("--auto-rotate")
        if not self.auto_scale.isChecked():
            t.append("--no-auto-scale")
        elif self.enlarge.isChecked():
            t.append("--enlarge")
        for opt, s in (("--margin-top", self.m_top), ("--margin-bottom", self.m_bottom),
                       ("--margin-left", self.m_left), ("--margin-right", self.m_right),
                       ("--page-trim-top", self.t_top), ("--page-trim-bottom", self.t_bottom),
                       ("--page-trim-left", self.t_left), ("--page-trim-right", self.t_right)):
            if s.value():
                t += self._length_opt(opt, s.value())
        for opt, c in (("--trim-marks", self.trim_marks), ("--bleed-marks", self.bleed_marks),
                       ("--registration-marks", self.reg_marks), ("--page-info", self.page_info)):
            if c.isChecked():
                t.append(opt)
        if self.page_info.isChecked() and self.w.original is not None:
            t += ["--page-info-name", self.w.original.name]
        return t

    def missing_required(self) -> list[str]:
        return []

    def set_tokens(self, tokens: list[str]):
        """Fill the form from an "impose" command line."""
        parser = self.w.parsers["impose"]
        args = [t for t in tokens if t != "impose"]
        try:
            ns, _ = parser.parse_known_args(args + ["input.pdf"])
        except SystemExit:
            return
        f = UNITS[self._units]

        def length(value) -> float:
            try:
                return parse_length(value, self._units) / f
            except ValueError:
                return 0.0

        self._loading = True
        self.layout_type.setCurrentIndex(max(self.layout_type.findData(ns.layout), 0))
        self.cols.setValue(ns.cols)
        self.rows.setValue(ns.rows)
        self.binding.setCurrentIndex(max(self.binding.findData(ns.binding), 0))
        self.sheets.setValue(ns.sheets_per_fold)
        self.direction.setCurrentIndex(max(self.direction.findData(ns.direction), 0))
        self.double.setChecked(not ns.single_sided)
        self.gutter_v.setValue(length(ns.gutter_v))
        self.gutter_h.setValue(length(ns.gutter_h))
        self.spread.setValue(length(ns.spread) if ns.spread is not None else 0)
        self.creep.setValue(length(ns.creep))
        media = ns.media.lower()
        m = re.fullmatch(r"\s*([0-9./]+)\s*([a-z\"]*)\s*[x×*]\s*([0-9./]+)\s*([a-z\"]*)\s*", media)
        if media == "auto":
            self.autosize.setChecked(True)
        elif m:
            self.fit.setChecked(True)
            self.media.setCurrentIndex(self.media.findData("custom"))
            u = m.group(4) or m.group(2) or self._units
            self.width.setValue(length(m.group(1) + u))
            self.height.setValue(length(m.group(3) + u))
        else:
            self.fit.setChecked(True)
            self.media.setCurrentIndex(max(self.media.findData(media), 0))
        (self.portrait if ns.orientation == "portrait" else self.landscape).setChecked(True)
        self.auto_rotate.setChecked(ns.auto_rotate)
        self.auto_scale.setChecked(not ns.no_auto_scale)
        self.enlarge.setChecked(ns.enlarge)
        for base, fields in ((ns.margin, ((self.m_top, ns.margin_top), (self.m_bottom, ns.margin_bottom),
                                          (self.m_left, ns.margin_left), (self.m_right, ns.margin_right))),
                             (ns.page_trim, ((self.t_top, ns.page_trim_top), (self.t_bottom, ns.page_trim_bottom),
                                             (self.t_left, ns.page_trim_left), (self.t_right, ns.page_trim_right)))):
            for s, v in fields:
                s.setValue(length(v if v is not None else base))
        self.trim_marks.setChecked(ns.trim_marks)
        self.bleed_marks.setChecked(ns.bleed_marks)
        self.reg_marks.setChecked(ns.registration_marks)
        self.page_info.setChecked(ns.page_info)
        self._loading = False
        self._show_media_size()
        self.changed.emit()

    # ----------------------------------------------------------------- profiles

    def profiles(self) -> dict[str, dict]:
        try:
            data = json.loads(self.w.settings.value("profiles", "{}"))
        except (TypeError, ValueError):
            data = {}
        return data if isinstance(data, dict) else {}

    def _store(self, data: dict):
        self.w.settings.setValue("profiles", json.dumps(data))
        self.refresh_profiles()
        self.profiles_changed.emit()

    def refresh_profiles(self, select: str | None = None):
        current = select if select is not None else self.profile.currentData()
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItem(tr(NEW_PROFILE), None)
        for name in sorted(self.profiles(), key=str.lower):
            self.profile.addItem(name, name)
        i = self.profile.findData(current)
        self.profile.setCurrentIndex(i if i >= 0 else 0)
        self.profile.blockSignals(False)
        self._profile_buttons()

    def _profile_buttons(self):
        name = self.profile.currentData()
        self.b_delete.setEnabled(name is not None)
        self.on_menu.setEnabled(name is not None)
        self.on_menu.blockSignals(True)
        self.on_menu.setChecked(bool(name and self.profiles().get(name, {}).get("menu")))
        self.on_menu.blockSignals(False)

    def save_profile(self, new_name: bool = False):
        name = self.profile.currentData()
        if new_name or name is None:
            name, ok = QInputDialog.getText(self, tr("Save profile"), tr("Name of the profile:"))
            name = name.strip()
            if not ok or not name:
                return
        data = self.profiles()
        menu = data.get(name, {}).get("menu", False)
        data[name] = {"units": self._units, "tokens": self.tokens(), "menu": menu}
        self._store(data)
        self.refresh_profiles(select=name)
        self.w.status(tr("Saved the profile {name}", name=name))

    def delete_profile(self):
        name = self.profile.currentData()
        if name is None:
            return
        if QMessageBox.question(self, tr("Delete profile"), tr("Delete the profile {name}?", name=name)) \
                != QMessageBox.StandardButton.Yes:
            return
        data = self.profiles()
        data.pop(name, None)
        self._store(data)

    def _menu_toggled(self, on: bool):
        name = self.profile.currentData()
        data = self.profiles()
        if name in data:
            data[name]["menu"] = on
            self._store(data)

    def load_profile(self, name: str | None):
        self._profile_buttons()
        profile = self.profiles().get(name or "")
        if not profile:
            return
        units = profile.get("units", self._units)
        if units in UNITS and units != self._units:
            self.units.setCurrentText(units)
        tokens = [t for t in profile.get("tokens", []) if t]
        self.set_tokens(tokens)
        i = self.profile.findData(name)
        if i >= 0:
            self.profile.setCurrentIndex(i)
        self._profile_buttons()


def shell_line(tokens: list[str]) -> str:
    return "py-imposition " + shlex.join(tokens)


__all__ = ["BasicPanel", "Qt"]
