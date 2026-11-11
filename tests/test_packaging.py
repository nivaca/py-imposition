"""Tests of the packaging: the versions agree, and the files that make the
RPM and the AppImage are sound."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from py_imposition import __version__

ROOT = Path(__file__).resolve().parent.parent


def spec_field(name: str) -> str:
    m = re.search(rf"^{name}:\s*(\S+)", (ROOT / "packaging/py-imposition.spec").read_text(), re.M)
    return m.group(1) if m else ""


def test_versions_agree():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == __version__
    assert spec_field("Version") == __version__, "bump the spec: rpmdev-bumpspec -n VERSION"


def test_spec_changelog_has_this_version():
    changelog = (ROOT / "packaging/py-imposition.spec").read_text().split("%changelog", 1)[1]
    first = next(line for line in changelog.splitlines() if line.startswith("*"))
    assert first.rstrip().endswith(f"- {__version__}-{spec_field('Release').split('%')[0]}")


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils not installed")
def test_desktop_file():
    r = subprocess.run(["desktop-file-validate", str(ROOT / "packaging/py-imposition.desktop")],
                       capture_output=True, text=True)
    assert r.stdout + r.stderr == ""


def test_scripts_parse():
    assert subprocess.run(["bash", "-n", str(ROOT / "packaging/build-rpm.sh")]).returncode == 0
    for tool in ("release.py", "bundle-appimage.py", "icons.py", "screenshots.py"):
        compile((ROOT / "tools" / tool).read_text(), tool, "exec")


@pytest.mark.skipif(not shutil.which("rpmspec"), reason="rpm-build not installed")
def test_spec_parses():
    r = subprocess.run(["rpmspec", "-q", "--srpm", "--qf", "%{version}", str(ROOT / "packaging/py-imposition.spec")],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == __version__, r.stderr
