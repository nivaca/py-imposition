"""Tests of PDF/A and PDF/X output through pdf2iso (conform.py, --conform)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf
import pytest

from py_imposition import config, conform, main
from py_imposition import pdfutil
from py_imposition.runner import build_parser, strip_io

HAVE_PDFCONFORM = shutil.which("pdf2iso") is not None


@pytest.fixture(autouse=True)
def own_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PY_IMPOSITION_CONFIG", str(tmp_path / "config"))


@pytest.fixture()
def sample(tmp_path) -> Path:
    out = tmp_path / "sample.pdf"
    assert main(["sample", "--count", "4", "--paper", "a5", "-o", str(out), "-q"]) == 0
    return out


def test_conform_missing(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(conform, "command", lambda path=None: None)
    with pytest.raises(conform.ConformError):
        conform.convert(sample, tmp_path / "x.pdf", "a-2b")


def test_finding_pdfconform(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # (as a session started from the desktop menu may have it)
    assert conform.find() is None and not conform.available()
    script = home / "bin" / "pdf2iso"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    assert conform.find() == script and conform.command() == [str(script)]
    other = tmp_path / "elsewhere.py"  # (a script that can't be run by itself: run with python3)
    other.write_text("print()\n")
    config.set("pdfconform", str(other))
    cmd = conform.command()
    assert cmd[-1] == str(other) and cmd[0].endswith("python3")
    config.set("pdfconform", str(tmp_path / "missing"))
    assert conform.command() is None


def test_finding_the_old_name(tmp_path, monkeypatch):
    """Before version 2.0, pdf2iso was called py-pdfconform: that name is
    still found, but pdf2iso comes first."""
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    old = home / "bin" / "py-pdfconform.py"
    old.write_text("#!/bin/sh\n")
    old.chmod(0o755)
    assert conform.find() == old
    new = home / "bin" / "pdf2iso"
    new.write_text("#!/bin/sh\n")
    new.chmod(0o755)
    assert conform.find() == new


def test_conform_is_not_part_of_a_step():
    argv = ["--conform", "x-4", "nup", "in.pdf", "--cols", "2", "--conform=a-2b", "-o", "out.pdf"]
    ns = build_parser().parse_args(argv)
    assert ns.conform == "a-2b"
    assert strip_io(argv, ns) == ["nup", "--cols", "2"]
    ns = build_parser().parse_args(["nup", "in.pdf", "--conform", "x-4"])
    assert strip_io(["nup", "in.pdf", "--conform", "x-4"], ns) == ["nup"]


def test_cli_conform_without_pdfconform(sample, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(conform, "command", lambda path=None: None)
    assert main(["reverse", str(sample), "--conform", "x-4", "-o", str(tmp_path / "out.pdf")]) == 1
    assert "pdf2iso" in capsys.readouterr().err


def test_cli_conform_with_a_fake_pdfconform(sample, tmp_path, monkeypatch, capsys):
    """The output is given to pdf2iso with the standard chosen (each file, if several)."""
    calls = []

    def fake(source, target, standard, password=""):
        calls.append((Path(source), Path(target), standard))
        return "veraPDF: PASS"

    monkeypatch.setattr(conform, "available", lambda path=None: True)
    monkeypatch.setattr(conform, "convert", fake)
    out = tmp_path / "out.pdf"
    assert main(["reverse", str(sample), "--conform", "a-2b", "-o", str(out)]) == 0
    assert calls == [(out, out, "a-2b")]
    assert "PDF/A-2b (veraPDF: PASS)" in capsys.readouterr().out
    # (the standard isn't recorded in the history: a replay doesn't convert)
    with pikepdf.open(out) as pdf:
        assert pdfutil.get_history(pdf)[-1] == ["reverse"]


@pytest.mark.skipif(not HAVE_PDFCONFORM, reason="pdf2iso not installed")
@pytest.mark.parametrize("standard", ["x-4", "a-2b"])
def test_cli_conform_for_real(sample, tmp_path, standard):
    out = tmp_path / "out.pdf"
    assert main(["booklet", str(sample), "--conform", standard, "-o", str(out), "-q"]) == 0
    with pikepdf.open(out) as pdf:
        assert "/OutputIntents" in pdf.Root and len(pdf.pages) == 2
        if standard == "x-4":
            assert all("/TrimBox" in p.obj for p in pdf.pages)


@pytest.mark.skipif(not HAVE_PDFCONFORM, reason="pdf2iso not installed")
def test_x4_keeps_the_boxes(tmp_path):
    pdf = pikepdf.Pdf.new()
    for _ in range(2):
        page = pdf.add_blank_page(page_size=(630, 810))
        page.obj.TrimBox = pikepdf.Array([9, 9, 621, 801])
        page.obj.BleedBox = pikepdf.Array([0, 0, 630, 810])
    src, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    pdf.save(src)
    assert main(["reverse", str(src), "--conform", "x-4", "-o", str(out), "-q"]) == 0
    with pikepdf.open(out) as pdf:
        page = pdf.pages[0].obj
        assert [float(x) for x in page.TrimBox] == [9, 9, 621, 801]
        assert [float(x) for x in page.BleedBox] == [0, 0, 630, 810]
