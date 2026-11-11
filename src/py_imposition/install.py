"""Add the py-imposition window to the applications menu, or remove it.

    py-imposition-install [--uninstall]
    python -m py_imposition.install [--uninstall]

Adds an entry, with the program's icon, that starts the window
(py-imposition-gui) with the Python that runs this script:

* Linux and other freedesktop systems: a .desktop file and the icons in the
  user's data folder ($XDG_DATA_HOME, usually ~/.local/share). The entry
  also offers py-imposition in the "Open with" menu of PDF files;
* Windows: a shortcut in the user's Start menu (made with PowerShell);
* macOS: a small application in ~/Applications.

Everything goes in the user's own folders, so no administrator rights are
needed. Run it again if the Python environment moves or is rebuilt;
--uninstall removes everything it added, and nothing else.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shlex
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from . import __version__

APP_ID = "py-imposition"  # the names of the entry and the icons
BUNDLE_ID = "io.github.nivaca.py-imposition"
NAME = "py-imposition"
COMMENT = "Impose PDF pages: booklets, n-up, step and repeat and more"
ICON_DIR = Path(__file__).resolve().parent / "icons"
MODULE = "py_imposition.gui"  # what the entry runs: python -m MODULE


def gui_command() -> list[str]:
    """How the entry starts the window."""
    return [sys.executable, "-m", MODULE]


def check_gui():
    """The window needs PySide6 (the "gui" extra)."""
    try:
        import PySide6.QtPdfWidgets  # noqa: F401
    except ImportError:
        raise OSError("the window needs PySide6, which is not installed for "
                      f"{sys.executable}; install py-imposition with the gui extra: "
                      "pip install 'py-imposition[gui]' (or uv tool install 'py-imposition[gui]')") from None


# ---------------------------------------------------------------------------
#  Linux and other freedesktop systems

HICOLOR = ICON_DIR / "linux" / "hicolor"

ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name={name}
GenericName=PDF imposition
Comment={comment}
Keywords=imposition;booklet;n-up;PDF;printing;prepress;
Categories=Office;Publishing;
Icon={app_id}
Exec={exec} %f
MimeType=application/pdf;
Terminal=false
StartupNotify=true
StartupWMClass={app_id}
"""


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def entry_path() -> Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


def exec_arg(arg: str) -> str:
    """ARG quoted for an Exec line, as the desktop entry specification
    requires when it has spaces or special characters."""
    if arg and not any(c in arg for c in " \t\n\"'\\><~|&;$*?#()`%"):
        return arg
    for c in '\\"`$':
        arg = arg.replace(c, "\\" + c)
    return '"' + arg.replace("%", "%%") + '"'


def icon_files() -> list[tuple[Path, Path]]:
    """(source, path relative to the hicolor theme) for each icon."""
    if not HICOLOR.is_dir():
        return []
    found = []
    for size in sorted(p.name for p in HICOLOR.iterdir()):
        for name in (APP_ID + ".png", APP_ID + ".svg"):
            src = HICOLOR / size / "apps" / name
            if src.is_file():
                found.append((src, Path(size) / "apps" / name))
    return found


def refresh_linux():
    """Tell the desktop about the change (each tool only if present)."""
    for command in (["update-desktop-database", str(data_home() / "applications")],
                    ["gtk-update-icon-cache", "-f", "-t", "-q", str(data_home() / "icons" / "hicolor")],
                    ["kbuildsycoca6"], ["kbuildsycoca5"]):
        if shutil.which(command[0]):
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if command[0] == "kbuildsycoca6":
                break


def installed_icons() -> list[Path]:
    """Our icons in the user's hicolor theme: only <size>/apps/py-imposition.png
    and .svg, in any size."""
    theme = data_home() / "icons" / "hicolor"
    if not theme.is_dir():
        return []
    found = []
    for size in sorted(theme.iterdir()):
        for ext in (".png", ".svg"):
            path = size / "apps" / (APP_ID + ext)
            if path.is_file():
                found.append(path)
    return found


def entry_text() -> str:
    return ENTRY.format(name=NAME, comment=COMMENT, app_id=APP_ID,
                        exec=" ".join(exec_arg(a) for a in gui_command()))


def install_linux() -> list[Path]:
    theme = data_home() / "icons" / "hicolor"
    for source, rel in icon_files():
        dest = theme / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest.unlink()  # (it may be read-only)
        shutil.copyfile(source, dest)
    path = entry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry_text(), encoding="utf-8", newline="\n")
    path.chmod(0o755)
    refresh_linux()
    return [path]


def uninstall_linux() -> list[Path]:
    """Remove the .desktop entry and the icons, and nothing else (no folders,
    not even empty ones)."""
    removed = [p for p in [entry_path()] if p.is_file()] + installed_icons()
    for p in removed:
        p.unlink()
    refresh_linux()
    return removed


# ---------------------------------------------------------------------------
#  Windows

ICO = ICON_DIR / "windows" / f"{APP_ID}.ico"

#  Makes a shortcut with the Windows Script Host, from values in the
#  environment (which spares quoting them in the script).
SHORTCUT_SCRIPT = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:PYI_LNK);"
    " $s.TargetPath = $env:PYI_TARGET;"
    " $s.Arguments = $env:PYI_ARGS;"
    " $s.WorkingDirectory = $env:PYI_DIR;"
    " $s.Description = $env:PYI_COMMENT;"
    " if ($env:PYI_ICON) { $s.IconLocation = $env:PYI_ICON };"
    " $s.Save()")


class Shortcut(NamedTuple):
    path: Path  # the .lnk file
    target: str  # the Python that runs the window
    arguments: str
    folder: str  # where it runs
    icon: str  # "file,index", or ''


def start_menu() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def windows_shortcut() -> Shortcut:
    """The window runs with pythonw.exe, which opens no console."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    target = str(pythonw) if pythonw.is_file() else sys.executable
    icon = f"{ICO},0" if ICO.is_file() else ""
    return Shortcut(start_menu() / f"{NAME}.lnk", target, f"-m {MODULE}", str(Path.home()), icon)


def install_windows() -> list[Path]:
    s = windows_shortcut()
    s.path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYI_LNK=str(s.path), PYI_TARGET=s.target, PYI_ARGS=s.arguments,
               PYI_DIR=s.folder, PYI_ICON=s.icon, PYI_COMMENT=COMMENT)
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SHORTCUT_SCRIPT],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0 or not s.path.is_file():
        output = result.stdout.decode(errors="replace").strip()
        raise OSError(f"could not make the shortcut {s.path}: {output}")
    return [s.path]


def uninstall_windows() -> list[Path]:
    path = windows_shortcut().path
    if path.is_file():
        path.unlink()
        return [path]
    return []


# ---------------------------------------------------------------------------
#  macOS

ICONSET = ICON_DIR / "macos" / f"{APP_ID}.iconset"

#  The icon types of an .icns file, by the name of the iconset image
ICNS_TYPES = (("icp4", "16x16"), ("ic11", "16x16@2x"),
              ("icp5", "32x32"), ("ic12", "32x32@2x"),
              ("ic07", "128x128"), ("ic13", "128x128@2x"),
              ("ic08", "256x256"), ("ic14", "256x256@2x"),
              ("ic09", "512x512"), ("ic10", "512x512@2x"))


def make_icns(iconset: Path) -> bytes:
    """An .icns file holding the PNG images of ICONSET (a folder of
    icon_16x16.png, icon_16x16@2x.png ...), as iconutil would make it;
    b'' if there are none."""
    chunks = b""
    for kind, size in ICNS_TYPES:
        path = Path(iconset) / f"icon_{size}.png"
        if path.is_file():
            png = path.read_bytes()
            chunks += kind.encode("ascii") + struct.pack(">I", len(png) + 8) + png
    if not chunks:
        return b""
    return b"icns" + struct.pack(">I", len(chunks) + 8) + chunks


def applications_dir() -> Path:
    return Path.home() / "Applications"


def app_path() -> Path:
    return applications_dir() / f"{NAME}.app"


def is_ours(app: Path) -> bool:
    """Whether APP is an application this script made."""
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return False
    return str(info.get("CFBundleIdentifier", "")).startswith(BUNDLE_ID)


def write_script(path: Path, text: str):
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def install_macos() -> list[Path]:
    """APP.app/Contents/{Info.plist, MacOS/<launcher>, Resources/<icon>}."""
    app = app_path()
    if app.exists():
        if not is_ours(app):
            raise OSError(f"{app} exists and was not made by py-imposition-install; move it away first")
        shutil.rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir(parents=True)
    run = " ".join(shlex.quote(a) for a in gui_command())
    write_script(contents / "MacOS" / APP_ID, f'#!/bin/sh\ncd "$HOME"\nexec {run} "$@"\n')
    info = {
        "CFBundleName": NAME,
        "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": APP_ID,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "PDF document",
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": ["com.adobe.pdf"],
        }],
    }
    icns = make_icns(ICONSET)
    if icns:
        (contents / "Resources" / f"{APP_ID}.icns").write_bytes(icns)
        info["CFBundleIconFile"] = APP_ID
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    applications_dir().mkdir(parents=True, exist_ok=True)
    os.utime(app)  # (so that Finder shows the icon)
    return [app]


def uninstall_macos() -> list[Path]:
    app = app_path()
    if app.is_dir() and is_ours(app):
        shutil.rmtree(app)
        return [app]
    return []


# ---------------------------------------------------------------------------


def system(platform: str | None = None) -> str:
    platform = platform or sys.platform
    if platform == "win32":
        return "windows"
    if platform == "darwin":
        return "macos"
    return "linux"


def install() -> list[Path]:
    check_gui()
    return {"linux": install_linux, "windows": install_windows, "macos": install_macos}[system()]()


def uninstall() -> list[Path]:
    return {"linux": uninstall_linux, "windows": uninstall_windows, "macos": uninstall_macos}[system()]()


WHERE = {"linux": "the applications menu", "windows": "the Start menu",
         "macos": "Applications (in your home folder)"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="py-imposition-install",
        description="Add the py-imposition window to the applications menu, or remove it. "
                    "Everything goes in your own folders; no administrator rights are needed.")
    parser.add_argument("--uninstall", action="store_true", help="remove what was added")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    where = WHERE[system()]
    try:
        if args.uninstall:
            removed = uninstall()
            print(f"Removed py-imposition from {where}." if removed else "There was nothing to remove.")
            return 0
        paths = install()
    except OSError as e:
        print(f"py-imposition-install: {e}", file=sys.stderr)
        return 1
    print(f"Added py-imposition to {where}:")
    for path in paths:
        print(f"  {path}")
    print("It starts the window with:")
    print("  " + " ".join(shlex.quote(a) for a in gui_command()))
    print("If that Python environment moves or is rebuilt, run this again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
