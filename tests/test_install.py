"""Tests of py-imposition-install (the applications menu entry)."""

from __future__ import annotations

import plistlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from py_imposition import install


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Each test works in a temporary home folder."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setattr(install, "check_gui", lambda: None)
    monkeypatch.setattr(install, "refresh_linux", lambda: None)
    return tmp_path


def test_icons_ship_with_the_package():
    rels = {str(rel) for _, rel in install.icon_files()}
    assert "scalable/apps/py-imposition.svg" in rels
    for n in (16, 32, 48, 128, 256, 512):
        assert f"{n}x{n}/apps/py-imposition.png" in rels
    assert install.ICO.is_file()
    assert install.make_icns(install.ICONSET).startswith(b"icns")


def test_install_and_uninstall_linux(home):
    paths = install.install_linux()
    assert paths == [home / "share" / "applications" / "py-imposition.desktop"]
    entry = paths[0].read_text()
    python = install.exec_arg(sys.executable)
    assert f"Exec={python} -m py_imposition.gui %f\n" in entry
    assert "Terminal=false" in entry and "MimeType=application/pdf;" in entry
    assert "Icon=py-imposition" in entry and "StartupWMClass=py-imposition" in entry
    if shutil.which("desktop-file-validate"):
        result = subprocess.run(["desktop-file-validate", str(paths[0])], capture_output=True, text=True)
        assert result.stdout + result.stderr == ""
    icons = install.icon_files()
    for _, rel in icons:
        assert (home / "share" / "icons" / "hicolor" / rel).is_file()
    removed = install.uninstall_linux()
    assert len(removed) == len(icons) + 1
    assert not paths[0].exists()
    assert install.uninstall_linux() == []


def test_uninstall_removes_only_our_files(home):
    install.install_linux()
    share = home / "share"
    others = [share / "applications" / "other.desktop",
              share / "applications" / "py-imposition-extra.desktop",
              share / "icons" / "hicolor" / "48x48" / "apps" / "other.png",
              share / "icons" / "hicolor" / "48x48" / "apps" / "py-imposition.xpm",
              share / "icons" / "hicolor" / "1024x1024" / "apps" / "py-imposition.png"]
    for p in others:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    removed = install.uninstall_linux()
    assert share / "icons" / "hicolor" / "1024x1024" / "apps" / "py-imposition.png" in removed
    for p in others[:-1]:
        assert p.exists()
    assert (share / "icons" / "hicolor" / "48x48" / "apps").is_dir()  # folders stay


def test_exec_arg_quoting():
    assert install.exec_arg("/usr/bin/python3") == "/usr/bin/python3"
    assert install.exec_arg("/home/a b/python") == '"/home/a b/python"'
    assert install.exec_arg('/x/$y"z') == '"/x/\\$y\\"z"'
    assert install.exec_arg("/x/50%") == '"/x/50%%"'


def test_macos_app(home):
    [app] = install.install_macos()
    assert app == home / "Applications" / "py-imposition.app"
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == install.BUNDLE_ID
    assert info["CFBundleIconFile"] == "py-imposition"
    launcher = (app / "Contents" / "MacOS" / "py-imposition").read_text()
    assert "-m py_imposition.gui" in launcher and '"$@"' in launcher
    icns = (app / "Contents" / "Resources" / "py-imposition.icns").read_bytes()
    assert icns[:4] == b"icns" and struct.unpack(">I", icns[4:8])[0] == len(icns)
    install.install_macos()  # again: replaces its own app
    assert install.uninstall_macos() == [app] and not app.exists()


def test_macos_does_not_replace_other_apps(home):
    app = home / "Applications" / "py-imposition.app"
    app.mkdir(parents=True)
    with pytest.raises(OSError):
        install.install_macos()
    assert install.uninstall_macos() == [] and app.exists()


def test_windows_shortcut(home):
    s = install.windows_shortcut()
    assert s.path == Path(home / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                          / "py-imposition.lnk")
    assert s.arguments == "-m py_imposition.gui"
    assert s.icon.endswith("py-imposition.ico,0")


def test_main_messages(home, capsys):
    assert install.main([]) == 0
    out = capsys.readouterr().out
    assert "Added py-imposition to the applications menu" in out
    assert install.main(["--uninstall"]) == 0
    assert "Removed py-imposition" in capsys.readouterr().out
    assert install.main(["--uninstall"]) == 0
    assert "nothing to remove" in capsys.readouterr().out


def test_system_names():
    assert install.system("win32") == "windows"
    assert install.system("darwin") == "macos"
    assert install.system("linux") == "linux"
