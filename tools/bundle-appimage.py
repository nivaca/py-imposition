#!/usr/bin/env python3
"""Make an AppImage of py-imposition, for Linux:

    uv run python tools/bundle-appimage.py [-o FOLDER] [--python APPIMAGE]
                                          [--python-version 3.15] [--appimagetool APPIMAGE]

The AppImage is dist/py-imposition-VERSION-x86_64.AppImage (the version of
pyproject.toml; --output gives another folder). It holds a Python of its own
(a relocatable Python of the python-appimage project,
https://github.com/niess/python-appimage) with py-imposition and everything it
needs installed into it, including PySide6 for the window, so it runs on any
recent Linux (glibc 2.34 or later: Ubuntu 22.04, Debian 12, Fedora 35 and
later) without installing anything.

It starts the window; a command of the command line (booklet, nup...), an
option, or "cli" runs the command line instead:

    py-imposition.AppImage [file.pdf]                  the window
    py-imposition.AppImage booklet in.pdf -o out.pdf   the command line
    py-imposition.AppImage cli --help

and so does the name it is called by, if it is a link named py-imposition or
py-imposition-gui. "help" says so.

What it needs is downloaded the first time and kept in the user's cache
folder (~/.cache/py-imposition-build): the Python and appimagetool
(https://github.com/AppImage/appimagetool). The program's wheel is made with
"uv build", and its dependencies come from PyPI (so this needs the network).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP_ID = "py-imposition"
ARCH = "x86_64"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

# The Python put in the AppImage (python-appimage has one release per version,
# with an AppImage per manylinux; PySide6 needs glibc 2.34 anyway).
PYTHON = "3.15"
PYTHON_RELEASES = "https://api.github.com/repos/niess/python-appimage/releases/tags/python{version}"
MANYLINUX = ("manylinux_2_28", "manylinux2014")
APPIMAGETOOL = f"https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-{ARCH}.AppImage"

# Parts of PySide6/Qt the program doesn't use (QML/Quick, the designer and
# other tools, headers, type stubs), left out to make the AppImage smaller.
PRUNE = [
    "PySide6/Qt/qml", "PySide6/Qt/libexec", "PySide6/include", "PySide6/typesystems", "PySide6/glue",
    "PySide6/scripts", "PySide6/examples", "PySide6/doc",
    "PySide6/designer", "PySide6/assistant", "PySide6/linguist", "PySide6/lrelease", "PySide6/lupdate",
    "PySide6/qmlformat", "PySide6/qmllint", "PySide6/qmlls", "PySide6/qmlcachegen", "PySide6/qmlimportscanner",
    "PySide6/qmltyperegistrar", "PySide6/balsam", "PySide6/balsamui", "PySide6/svgtoqml", "PySide6/qsb",
    "PySide6/rcc", "PySide6/uic", "PySide6/Qt/plugins/designer", "PySide6/Qt/plugins/qmltooling",
    "PySide6/Qt/plugins/qmllint",
]
PRUNE_GLOBS = ["PySide6/*.pyi", "PySide6/Qt/lib/libQt6Designer*", "PySide6/Qt/lib/libQt6Qml*",
               "PySide6/Qt/lib/libQt6Quick*", "PySide6/Qt/lib/libQt6ShaderTools*", "PySide6/Qt/lib/libQt6Help*",
               "PySide6/QtQml*", "PySide6/QtQuick*", "PySide6/QtDesigner*", "PySide6/QtHelp*",
               "PySide6/Qt/translations/assistant_*", "PySide6/Qt/translations/designer_*",
               "PySide6/Qt/translations/linguist_*", "PySide6/Qt/translations/qtdeclarative_*",
               "PySide6/Qt/translations/qt_help_*"]

DESKTOP = f"""[Desktop Entry]
Type=Application
Name=py-imposition
GenericName=PDF imposition
GenericName[es]=Imposición de PDF
Comment=Impose PDF pages: booklets, n-up, step and repeat and more
Comment[es]=Imponer páginas PDF: folletos, n-up, paso y repetición y más
Keywords=imposition;booklet;n-up;PDF;printing;prepress;
Categories=Office;Publishing;
Icon={APP_ID}
Exec={APP_ID} %f
MimeType=application/pdf;
Terminal=false
StartupNotify=true
StartupWMClass={APP_ID}
"""

# %(python)s: the interpreter, relative to the AppDir; %(commands)s: the
# command line's commands, separated by |
APPRUN = r"""#!/bin/bash
#  Starts py-imposition in the AppImage (made by tools/bundle-appimage.py).
ROOT="$(dirname "$(readlink -f -- "$0")")"
export APPDIR="${APPDIR:-$ROOT}"
PYTHON="$APPDIR/%(python)s"
SELF="${ARGV0:-$0}"
for f in "$APPDIR"/opt/python*/lib/python*/site-packages/certifi/cacert.pem; do
    [ -f "$f" ] && export SSL_CERT_FILE="${SSL_CERT_FILE:-$f}"
done
#  (the AppImage cannot be written to)
export PYTHONDONTWRITEBYTECODE=1
#  Only what is inside the AppImage: not the user's site-packages, nor
#  another Python's settings
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP VIRTUAL_ENV

usage() {
    echo "Usage: ${SELF##*/} [file.pdf]            the window"
    echo "       ${SELF##*/} COMMAND [OPTIONS]      the command line (booklet, nup, ...)"
    echo "       ${SELF##*/} cli [ARGUMENTS]        the command line"
    echo
    echo "\"${SELF##*/} cli --help\" lists the commands; \"${SELF##*/} COMMAND --help\" tells"
    echo "what each one takes."
}

gui() { exec "$PYTHON" -m py_imposition.gui "$@"; }
cli() { exec "$PYTHON" -m py_imposition "$@"; }

name="$(basename -- "$SELF")"
case "$name" in
    py-imposition-gui) gui "$@" ;;
    py-imposition) cli "$@" ;;
esac
case "$1" in
    "") gui ;;
    help|--help|-h) usage; exit 0 ;;
    gui) shift; gui "$@" ;;
    cli) shift; cli "$@" ;;
    %(commands)s|-*) cli "$@" ;;
    *) gui "$@" ;;
esac
"""


def say(text: str):
    print(text, file=sys.stderr, flush=True)


def name() -> str:
    return f"{APP_ID}-{VERSION}-{ARCH}.AppImage"


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    path = base / "py-imposition-build"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download(url: str, path: Path) -> Path:
    """Download URL into PATH (unless it is there already)."""
    if not path.is_file():
        say(f"Downloading {url} ...")
        tmp = path.with_name(path.name + ".tmp")
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, path)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def python_appimage(version: str) -> Path:
    """The Python AppImage of VERSION, for the newest manylinux there is one for."""
    url = PYTHON_RELEASES.format(version=version)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as r:
        assets = json.load(r)["assets"]
    tag = "cp" + version.replace(".", "")
    for manylinux in MANYLINUX:
        end = f"-{tag}-{tag}-{manylinux}_{ARCH}.AppImage"  # (not the free-threaded cp3XXt)
        found = [a["browser_download_url"] for a in assets if a["name"].endswith(end)]
        if found:
            return download(found[0], cache_dir() / found[0].rsplit("/", 1)[1])
    raise OSError(f"there is no Python {version} AppImage at {url}")


def wheel(folder: Path) -> Path:
    """The program's wheel, made with uv build."""
    if not shutil.which("uv"):
        raise OSError("uv is needed to make the wheel (https://docs.astral.sh/uv/)")
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(folder)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    found = sorted(folder.glob(f"py_imposition-{VERSION}-*.whl"))
    if not found:
        raise OSError("uv build made no wheel")
    return found[0]


def commands() -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from py_imposition.common import COMMANDS  # noqa: PLC0415
    return sorted(COMMANDS)


def make_appdir(appdir: Path, whl: Path):
    """Turn the AppDir of the Python into that of py-imposition."""
    pythons = [p for p in sorted(appdir.glob("opt/python3*/bin/python3.*")) if not p.name.endswith("-config")]
    if not pythons:
        raise OSError(f"there is no Python in {appdir}")
    python = pythons[0]
    say(f"Installing py-imposition and its dependencies into {python.relative_to(appdir)} ...")
    # Everything must go inside: pip must not see packages of the user's
    # site-packages (or another environment) as already installed.
    env = clean_env()
    subprocess.run([str(python), "-s", "-m", "pip", "install", "--isolated", "--no-cache-dir",
                    "--no-warn-script-location", "--disable-pip-version-check", "--quiet", f"{whl}[gui]"],
                   check=True, env=env)
    site = next(appdir.glob("opt/python3*/lib/python3.*/site-packages"))
    for rel in PRUNE:
        path = site / rel
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    for pattern in PRUNE_GLOBS:
        for path in site.glob(pattern):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    # Out with what makes it the Python's AppImage
    for pattern in ("AppRun", "*.desktop", "*.png", "*.svg", ".DirIcon", "usr/share/applications",
                    "usr/share/metainfo"):
        for path in appdir.glob(pattern):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    apprun = appdir / "AppRun"
    apprun.write_text(APPRUN % {"python": python.relative_to(appdir), "commands": "|".join(commands())},
                      encoding="utf-8", newline="\n")
    apprun.chmod(0o755)
    (appdir / f"{APP_ID}.desktop").write_text(DESKTOP, encoding="utf-8", newline="\n")
    icons = ROOT / "src" / "py_imposition" / "icons" / "linux" / "hicolor"
    shutil.copy2(icons / "256x256" / "apps" / f"{APP_ID}.png", appdir / f"{APP_ID}.png")
    os.symlink(f"{APP_ID}.png", appdir / ".DirIcon")
    shutil.copytree(icons, appdir / "usr" / "share" / "icons" / "hicolor", dirs_exist_ok=True)


def clean_env(**extra) -> dict:
    """The environment without anything that would make a Python look outside its own folders."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTHON", "PIP_", "VIRTUAL_ENV", "UV_", "CONDA"))}
    env.update(PYTHONNOUSERSITE="1", **extra)
    return env


def check_imports(appdir: Path):
    """Stop if the bundled Python can't import what the program needs, on its own."""
    python = next(p for p in sorted(appdir.glob("opt/python3*/bin/python3.*")) if not p.name.endswith("-config"))
    code = ("import pikepdf, reportlab, PIL, PySide6.QtPdfWidgets, py_imposition.gui.window; "
            "print(pikepdf.__version__, reportlab.Version, PySide6.__version__)")
    r = subprocess.run([str(python), "-s", "-c", code], capture_output=True, text=True,
                       env=clean_env(QT_QPA_PLATFORM="offscreen", APPDIR=str(appdir)))
    if r.returncode != 0:
        raise OSError(f"the bundled Python cannot run the program:\n{r.stderr.strip()}")
    say(f"Bundled pikepdf, reportlab, PySide6: {r.stdout.strip()}")


def smoke_test(appimage: Path):
    """Run the AppImage as a user with nothing installed would: an empty home folder."""
    with tempfile.TemporaryDirectory() as home:
        env = clean_env(HOME=home, XDG_CONFIG_HOME=f"{home}/.config", XDG_CACHE_HOME=f"{home}/.cache",
                        XDG_DATA_HOME=f"{home}/.local/share", APPIMAGE_EXTRACT_AND_RUN="1")
        for args in (["--version"], ["sample", "--count", "4", "-o", f"{home}/s.pdf"],
                     ["booklet", "--paper", "a4", f"{home}/s.pdf", "-o", f"{home}/b.pdf"]):
            r = subprocess.run([str(appimage), *args], capture_output=True, text=True, env=env, cwd=home)
            if r.returncode != 0:
                raise OSError(f"the AppImage failed ({' '.join(args)}):\n{(r.stderr or r.stdout).strip()}")
    say("The AppImage runs on its own (empty home folder): --version, sample, booklet.")


def open_to_all(appdir: Path):
    """Let everyone read the AppDir: folders 0755, files 0644, or 0755 if they can be run."""
    for folder, dirs, names in os.walk(appdir):
        for d in dirs:
            p = Path(folder, d)
            if not p.is_symlink():
                p.chmod(0o755)
        for n in names:
            p = Path(folder, n)
            if not p.is_symlink():
                p.chmod(0o755 if p.stat().st_mode & stat.S_IXUSR else 0o644)
    appdir.chmod(0o755)


def bundle(output: Path, python: Path | None = None, appimagetool: Path | None = None,
           version: str = PYTHON) -> Path:
    python = python or python_appimage(version)
    appimagetool = appimagetool or download(APPIMAGETOOL, cache_dir() / Path(APPIMAGETOOL).name)
    path = output / name()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run([str(python.resolve()), "--appimage-extract"], cwd=tmp, check=True,
                       stdout=subprocess.DEVNULL)
        appdir = tmp / "squashfs-root"
        make_appdir(appdir, wheel(tmp / "wheel"))
        check_imports(appdir)
        open_to_all(appdir)
        # (without FUSE, as in a container, the tool runs extracted)
        env = dict(os.environ, ARCH=ARCH, APPIMAGE_EXTRACT_AND_RUN="1")
        tmp_out = path.with_name(path.name + ".tmp")
        subprocess.run([str(appimagetool.resolve()), "--no-appstream", "--comp", "zstd", str(appdir),
                        str(tmp_out)], check=True, env=env, stdout=subprocess.DEVNULL)
    os.replace(tmp_out, path)
    smoke_test(path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools/bundle-appimage.py",
                                     description=f"Make an AppImage of py-imposition: {name()}, with a Python of "
                                                 "its own.")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="the folder to write it in (default: dist/)")
    parser.add_argument("--python", type=Path, metavar="APPIMAGE",
                        help="the Python AppImage to use (default: one of python-appimage, downloaded)")
    parser.add_argument("--python-version", default=PYTHON, metavar="VERSION",
                        help=f"the version of Python to download (default: {PYTHON})")
    parser.add_argument("--appimagetool", type=Path, metavar="APPIMAGE",
                        help="the appimagetool to use (default: downloaded)")
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        sys.exit("bundle-appimage.py: AppImages are made on Linux")
    output = args.output or DIST
    output.mkdir(parents=True, exist_ok=True)
    try:
        path = bundle(output, args.python, args.appimagetool, args.python_version)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, StopIteration) as e:
        sys.exit(f"bundle-appimage.py: {e}")
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB).")


if __name__ == "__main__":
    main()
