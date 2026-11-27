#!/usr/bin/env python3
"""Toma las capturas del README: la ventana con varias órdenes, y la línea
de órdenes.

    uv run python tools/screenshots.py [-o FOLDER] [--only booklet,nup,...]
                                       [--langs en,es] [--scale 2] [--dark]
                                       [--size 1500x940]

Escribe FOLDER/gui_<command>_<lang>.png y FOLDER/cli_<lang>.png, en cada idioma de la
interfaz (por omisión en docs/img/, de donde README.md toma las inglesas y README_es.md
las españolas), a SCALE veces el tamaño en pantalla (2 por omisión, nítidas en las
pantallas de alta resolución).

* La ventana corre en un proceso propio con la plataforma "offscreen" de Qt: nada
  aparece en la pantalla, el tamaño y la escala no dependen de ella, y solo se captura
  la ventana del programa (Qt la dibuja en la imagen). Cada captura tiene su propia
  configuración en una carpeta temporal, así que no se tocan los ajustes del usuario,
  sus opciones recientes ni su secuencia. El documento de ejemplo, el mismo en todas
  las capturas, es docs/example/numbers-100.pdf (100 páginas, cada una con su número).
* La línea de órdenes es una sesión real: las órdenes se corren de verdad y su salida
  se dibuja como en una terminal (los colores Breeze de Konsole, una fuente
  monoespaciada), también con Qt.

Necesita el extra gui (PySide6): uv sync --extra gui. Nada más; no hace falta pantalla.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCALE = 2
WINDOW = (1500, 940)  # pixels, before the scale

EXAMPLE = ROOT / "docs" / "example" / "numbers-100.pdf"

# Each shot: the command and its options in the form (on EXAMPLE), the
# window's mode, and an optional sequence shown in the panel.
SHOTS = {
    "basic": dict(
        tokens=["impose", "--layout", "4up-booklet", "--binding", "saddle", "--media", "a3", "--orientation",
                "portrait", "--margin", "1.5", "--gutter-v", "1.5", "--gutter-h", "1.5", "--trim-marks"],
        mode="basic",
    ),
    "booklet": dict(
        tokens=["booklet", "--binding", "perfect", "--signature", "16", "--paper", "a4", "--margin", "1.5cm",
                "--crop-marks"],
    ),
    "nup": dict(
        tokens=["nup", "--paper", "a3", "--orientation", "tall", "--cols", "2", "--rows", "2", "--scale", "fit",
                "--margin", "1.5cm", "--spacing", "1.5cm", "--align", "center", "--crop-marks"],
    ),
    "step-repeat": dict(
        tokens=["step-repeat", "--paper", "a4", "--orientation", "tall", "--scale", "fit", "--cols", "3",
                "--rows", "3", "--spacing", "0.6cm", "--margin", "1cm", "--align", "center", "--crop-marks"],
    ),
    "text": dict(
        tokens=["text", "--text", "Page [#] of [Doc:NumPages]", "--position", "bottom-center", "--size", "11",
                "--offset-y", "1.2cm", "--color", "#c0392b"],
        sequence=[["text", "--text", "Page [#] of [Doc:NumPages]", "--size", "11", "--offset-y", "1.2cm"],
                  ["creep", "--scope", "signatures", "--signature", "16", "--thickness", "0.1mm"],
                  ["booklet", "--binding", "perfect", "--signature", "16", "--paper", "a4", "--crop-marks",
                   "--margin", "1.5cm"]],
    ),
}
KINDS = list(SHOTS) + ["cli"]

# The user's own texts in the examples, in each language (the commands stay the same)
LOCAL = {"es": {"Page [#] of [Doc:NumPages]": "Página [#] de [Doc:NumPages]"}}


def localize(tokens: list[str], lang: str) -> list[str]:
    table = LOCAL.get(lang, {})
    return [table.get(t, t) for t in tokens]

# The command-line session (run in a temporary folder holding a copy of EXAMPLE)
SESSION = [
    ["info", "numbers-100.pdf"],
    ["text", "--text", "Page [#] of [Doc:NumPages]", "numbers-100.pdf", "-o", "numbered.pdf"],
    ["booklet", "--binding", "perfect", "--signature", "16", "--paper", "a4", "--crop-marks",
     "--margin", "1.5cm", "numbered.pdf", "-o", "booklet.pdf"],
    ["nup", "--cols", "2", "--rows", "2", "--scale", "fit", "--paper", "a3", "numbers-100.pdf"],
    ["info", "booklet.pdf"],
]

# The terminal: Konsole's Breeze scheme
BACKGROUND, FOREGROUND = "#232627", "#fcfcfc"
PROMPT, DIM = "#1cdc9a", "#bdc3c7"
FONTS = ("Hack", "DejaVu Sans Mono", "Liberation Mono", "Monospace")
FONT_SIZE, LINE_HEIGHT, MARGIN, COLUMNS = 15, 1.35, 16, 100


def say(text: str):
    print(text, flush=True)


def settings_folder(folder: Path, lang: str) -> Path:
    """A configuration folder of its own, with the interface in LANG."""
    cfg = folder / "py-imposition-config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.toml").write_text(f'[parameters]\ninterface = "{lang}"\n', encoding="utf-8")
    return cfg


def environment(folder: Path, scale: float) -> dict:
    env = dict(os.environ)
    env.update(QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=f"{scale:g}", XDG_CONFIG_HOME=str(folder / "config"),
               PY_IMPOSITION_CONFIG=str(folder / "py-imposition-config"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("QT_SCREEN_SCALE_FACTORS", None)
    env.pop("QT_AUTO_SCREEN_SCALE_FACTOR", None)
    return env


def cli_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run the command line with the settings of CWD (see settings_folder)."""
    return subprocess.run([sys.executable, "-m", "py_imposition", *args], cwd=cwd, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONPATH=str(ROOT / "src"),
                                   PY_IMPOSITION_CONFIG=str(cwd / "py-imposition-config")))


# ---------------------------------------------------------------------------
#  The window


def gui(kind: str, lang: str, out: Path, scale: float, size: tuple[int, int], dark: bool):
    """The window, in a process of its own (offscreen, with its own settings)."""
    folder = Path(tempfile.mkdtemp(prefix=f"py-imposition-shot-{kind}-{lang}-"))
    try:
        settings_folder(folder, lang)
        doc = EXAMPLE
        cmd = [sys.executable, str(Path(__file__).resolve()), "--child", kind, str(doc), str(out),
               f"{size[0]}x{size[1]}"] + (["--dark"] if dark else [])
        subprocess.run(cmd, env=environment(folder, scale), check=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def dark_palette():
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    roles = QPalette.ColorRole
    for role, colour in ((roles.Window, "#2b2e31"), (roles.WindowText, "#e8e8e8"), (roles.Base, "#1f2124"),
                         (roles.AlternateBase, "#2b2e31"), (roles.ToolTipBase, "#2b2e31"),
                         (roles.ToolTipText, "#e8e8e8"), (roles.Text, "#e8e8e8"), (roles.Button, "#33373b"),
                         (roles.ButtonText, "#e8e8e8"), (roles.BrightText, "#ff6b6b"), (roles.Highlight, "#3a7bc8"),
                         (roles.HighlightedText, "#ffffff"), (roles.PlaceholderText, "#8a9099"),
                         (roles.Mid, "#45494e"), (roles.Dark, "#9aa3ad")):
        p.setColor(role, QColor(colour))
    return p


def gui_child(kind: str, doc: str, out: str, size: str, dark: bool):
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    from py_imposition import interface
    from py_imposition.gui import app_icon
    from py_imposition.gui.window import MainWindow, install_qt_translations

    interface.use_configured()  # (the language of this shot's settings)
    interface.translate_argparse()
    QCoreApplication.setOrganizationName("py-imposition-screenshots")
    app = QApplication([sys.argv[0]])
    install_qt_translations()
    app.setStyle("Fusion")
    if dark:
        app.setPalette(dark_palette())
    app.setWindowIcon(app_icon())
    shot = SHOTS[kind]
    w = MainWindow()
    width, height = (int(v) for v in size.split("x"))
    w.resize(width, height)
    w.show()
    w.auto.setChecked(False)
    w.open_path(Path(doc))
    w.set_mode(shot.get("mode", "advanced"))
    if shot.get("mode") != "basic":
        w.select_command(shot["tokens"][0])
    lang = interface.code()
    w.form(shot["tokens"][0]).set_tokens(localize(shot["tokens"], lang))
    w.seq.set_steps([localize(step, lang) for step in shot.get("sequence", [])])
    w.preview()

    def settle(seconds: float):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)

    if shot.get("sequence"):
        settle(0.2)  # (laid out first, so the dock can be resized)
        w.resizeDocks([w.docks[0]], [150], Qt.Orientation.Vertical)
    else:
        for dock in w.docks:  # (more room for the previews)
            dock.hide()

    end = time.time() + 120
    while w.runner.busy() and time.time() < end:
        settle(0.05)
    if not w.result_files:
        raise SystemExit(f"{kind}: no result ({w.statusBar().currentMessage()})")
    w.tree.setFocus()
    settle(1.5)  # (the PDF views render in the background)
    if not w.grab().save(out, "PNG"):
        raise SystemExit(f"could not write {out}")
    w.runner.stop()


# ---------------------------------------------------------------------------
#  The command line


def cli(lang: str, out: Path, scale: float):
    """Run SESSION in a temporary folder and draw it like a terminal."""
    folder = Path(tempfile.mkdtemp(prefix=f"py-imposition-shot-cli-{lang}-"))
    try:
        settings_folder(folder, lang)
        shutil.copyfile(EXAMPLE, folder / EXAMPLE.name)
        lines: list[tuple[str, str]] = []  # (kind, text): prompt or output
        for args in SESSION:
            args = localize(args, lang)
            lines.append(("prompt", "py-imposition " + shlex.join(args)))
            result = cli_run(args, folder)
            if result.returncode:
                raise SystemExit(f"'{shlex.join(args)}' failed: {result.stderr}")
            text = (result.stdout + result.stderr).replace(str(folder) + os.sep, "")
            lines += [("output", ln) for ln in text.rstrip("\n").splitlines()]
        lines.append(("prompt", ""))
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child-cli", str(out)],
                       input="\n".join(f"{k}\t{t}" for k, t in lines), text=True,
                       env=environment(folder, scale), check=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def cli_child(out: str):
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter

    app = QGuiApplication([sys.argv[0]])
    scale = app.devicePixelRatio()
    family = next((f for f in FONTS if f in QFontDatabase.families()), "Monospace")
    font = QFont(family)
    font.setPixelSize(FONT_SIZE)
    font.setStyleHint(QFont.StyleHint.Monospace)
    bold = QFont(font)
    bold.setBold(True)
    metrics = QFontMetricsF(font)
    entries = [ln.split("\t", 1) for ln in sys.stdin.read().splitlines()]
    # wrap long lines at COLUMNS
    rows: list[tuple[str, str]] = []
    for kind, text in entries:
        text = ("$ " + text) if kind == "prompt" else text
        while len(text) > COLUMNS:
            cut = text.rfind(" ", 0, COLUMNS)
            cut = cut if cut > COLUMNS // 2 else COLUMNS
            rows.append((kind, text[:cut]))
            text = "    " + text[cut:].lstrip()
            kind = kind if kind == "output" else "cont"
        rows.append((kind, text))
    line_h = FONT_SIZE * LINE_HEIGHT
    width = MARGIN * 2 + metrics.horizontalAdvance("M" * COLUMNS)
    height = MARGIN * 2 + line_h * len(rows)
    image = QImage(round(width * scale), round(height * scale), QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(scale)
    image.fill(QColor(BACKGROUND))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    y = MARGIN + metrics.ascent() + (line_h - FONT_SIZE) / 2
    for kind, text in rows:
        x = MARGIN
        if kind == "prompt":
            p.setFont(bold)
            p.setPen(QColor(PROMPT))
            p.drawText(QPointF(x, y), "$")
            x += metrics.horizontalAdvance("$ ")
            text = text[2:]
            p.setFont(font)
            p.setPen(QColor(FOREGROUND))
        elif kind == "cont":
            p.setFont(font)
            p.setPen(QColor(FOREGROUND))
        else:
            p.setFont(font)
            p.setPen(QColor(DIM if not text.startswith(("warning", "error")) else "#fdbc4b"))
        p.drawText(QPointF(x, y), text)
        if kind == "prompt" and not text:  # the cursor of the last prompt
            p.fillRect(QRectF(x, y - metrics.ascent(), metrics.horizontalAdvance("M"), metrics.height()),
                       QColor(FOREGROUND))
        y += line_h
    p.end()
    if not image.save(out, "PNG"):
        raise SystemExit(f"could not write {out}")


# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description="Take the screenshots of the window and the command line "
                                                 "(for the README).")
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "docs" / "img",
                        help="the folder of the images (default: docs/img)")
    parser.add_argument("--only", default=",".join(KINDS), help=f"which shots: {','.join(KINDS)}")
    parser.add_argument("--langs", default="en,es", help="which languages of the interface (default: en,es)")
    parser.add_argument("--scale", type=float, default=SCALE, help="times the size on the screen (default: 2)")
    parser.add_argument("--size", default=f"{WINDOW[0]}x{WINDOW[1]}",
                        help=f"window size before the scale (default: {WINDOW[0]}x{WINDOW[1]})")
    parser.add_argument("--dark", action="store_true", help="draw the window in dark colours")
    parser.add_argument("--child", nargs=4, help=argparse.SUPPRESS)
    parser.add_argument("--child-cli", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        gui_child(*args.child, dark=args.dark)
        return
    if args.child_cli:
        cli_child(args.child_cli)
        return
    try:
        import PySide6.QtPdfWidgets  # noqa: F401
    except ImportError:
        raise SystemExit("PySide6 is needed: uv sync --extra gui") from None
    if not EXAMPLE.is_file():
        raise SystemExit(f"the example document {EXAMPLE} is missing")
    kinds = [k for k in args.only.split(",") if k]
    for k in kinds:
        if k not in KINDS:
            raise SystemExit(f"unknown shot: {k} (choose from {', '.join(KINDS)})")
    if args.scale <= 0:
        raise SystemExit("the scale must be more than 0")
    try:
        size = tuple(int(v) for v in args.size.lower().split("x"))
        assert len(size) == 2 and min(size) > 200
    except (ValueError, AssertionError):
        raise SystemExit("--size must look like 1500x940") from None
    from py_imposition import interface
    langs = [lang for lang in args.langs.split(",") if lang]
    for lang in langs:
        if lang not in interface.names():
            raise SystemExit(f"unknown language: {lang} (choose from {', '.join(interface.names())})")
    args.output.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        for kind in kinds:
            out = args.output / (f"cli_{lang}.png" if kind == "cli" else f"gui_{kind}_{lang}.png")
            say(f"{kind} ({lang}) -> {out}")
            if kind == "cli":
                cli(lang, out, args.scale)
            else:
                gui(kind, lang, out, args.scale, size, args.dark)


if __name__ == "__main__":
    main()
