"""Tests for py-imposition. Expected orders come from worked examples of standard impositions."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pikepdf
import pytest

from py_imposition import main
from py_imposition.impose import booklet_order
from py_imposition.pagesel import parse_pages
from py_imposition.shuffle import parse_rule, shuffle_order
from py_imposition.units import parse_length, parse_paper


def fmt(order):
    return " ".join("X" if i is None else str(i + 1) + {180: "*", 90: ">", 270: "<", 0: ""}[r] for i, r in order)


# --------------------------------------------------------------------------- pure logic


def test_units():
    assert parse_length("1in") == 72
    assert parse_length("2.54", "cm") == pytest.approx(72)
    assert parse_length("3/8in") == pytest.approx(27)
    assert parse_paper("a4") == pytest.approx((595.28, 841.89))
    assert parse_paper("5x2in") == (360, 144)


def test_page_ranges():
    assert parse_pages("1-3,LAST", 10) == [0, 1, 2, 9]
    assert parse_pages("LAST-2..LAST", 10) == [7, 8, 9]
    assert parse_pages("even", 5) == [1, 3]
    assert parse_pages("4..1", 5, keep_order=True) == [3, 2, 1, 0]


@pytest.mark.parametrize("count,rule,group,repeat,expected", [
    (8, "4 1 2 3", 4, "saddle", "8 1 2 7 6 3 4 5"),
    (12, "4 1 2 3", 4, "saddle", "12 1 2 11 10 3 4 9 8 5 6 7"),
    (12, "4 1 2 3", 4, "normal", "4 1 2 3 8 5 6 7 12 9 10 11"),
    (8, "1 2", 2, "cut-single", "1 5 2 6 3 7 4 8"),
    (8, "1 3 4 2", 4, "cut-double", "1 5 6 2 3 7 8 4"),
    (8, "4 3* 2 1*", 4, "normal", "4 3* 2 1* 8 7* 6 5*"),
    (4, "1..4 X", 4, "normal", "1 2 3 4 X"),
])
def test_shuffle_manual_examples(count, rule, group, repeat, expected):
    assert fmt(shuffle_order(count, parse_rule(rule), group, repeat)) == expected


def test_advanced_cut_stacks():
    order = shuffle_order(2000, parse_rule("1..5 6..10"), 10, "cut-single", 5, 100)
    assert fmt(order[:10]) == "1 2 3 4 5 501 502 503 504 505"
    assert fmt(order[1000:1005]) == "1001 1002 1003 1004 1005"


def test_booklet_orders():
    assert booklet_order(4) == [(3, 0), (1, 2)]
    assert booklet_order(8, "saddle") == [(7, 0), (1, 6), (5, 2), (3, 4)]
    assert booklet_order(6, "perfect", 4) == [(3, 0), (1, 2), (None, 4), (5, None)]
    assert booklet_order(4, direction="right") == [(0, 3), (2, 1)]
    assert booklet_order(8, "cut-stack") == [(0, 4), (5, 1), (2, 6), (7, 3)]


# --------------------------------------------------------------------------- end to end


@pytest.fixture()
def sample(tmp_path) -> Path:
    out = tmp_path / "sample.pdf"
    assert main(["sample", "--count", "10", "--paper", "a5", "-o", str(out), "-q"]) == 0
    return out


def page_texts(path: Path) -> list[str]:
    n = len(pikepdf.open(path).pages)
    out = []
    for i in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), str(path), "-"],
                           capture_output=True, text=True).stdout
        out.append(" ".join(t.split()))
    return out


def run(*args) -> int:
    return main([str(a) for a in args] + ["-q"])


def test_default_booklet(sample, tmp_path):
    out = tmp_path / "b.pdf"
    assert run(sample, "-o", out) == 0
    pdf = pikepdf.open(out)
    assert len(pdf.pages) == 6  # 10 pages -> 3 sheets, front and back
    assert [round(float(v)) for v in pdf.pages[0].mediabox] == [0, 0, 1008, 612]  # Legal landscape


@pytest.mark.parametrize("args", [
    ["booklet", "--binding", "saddle", "--crop-marks", "--margin", "1", "--sides", "fronts-then-backs"],
    ["nup", "--cols", "2", "--rows", "2", "--scale", "fit", "--crop-marks", "--frames", "--mirror", "h"],
    ["nup", "--trim", "--margin", "1", "--crop-marks", "--paper", "max"],
    ["nup", "--cols", "2", "--rows", "1", "--scale", "fit", "--flow", "double-flip"],
    ["step-repeat", "--paper", "a3", "--rotate", "--align", "center", "--align-rows", "--mirror", "hv"],
    ["shuffle", "--rule", "8 1 5* 4* 2 7 3* 6*", "--repeat", "saddle"],
    ["evenodd", "--mode", "odds-first", "--rotate-evens"],
    ["reverse"],
    ["trim-shift", "--trim", "all=5mm", "--shift", "right=3mm", "--parity", "odd"],
    ["trim-shift", "--same-size", "a4"],
    ["creep", "--thickness", "0.1mm", "--method", "scale"],
    ["resize", "--size", "letter", "--rotate-to-fit", "cw"],
    ["resize", "--percent", "50"],
    ["rotate", "--angle", "15"],
    ["rotate", "--angle", "90", "--parity", "even"],
    ["duplicate", "--copies", "1"],
    ["delete", "--pages", "1"],
    ["move", "--pages", "1", "--after", "LAST"],
    ["tile", "--grid", "2x2", "--overlap", "5mm", "--overlap-bleed"],
    ["bleed", "--mode", "except-fold", "--outside", "--generate", "mirror"],
    ["insert", "--blank", "9", "--until", "multiple:8"],
    ["text", "--text", "Page [#] of [Doc:NumPages]", "--start", "007", "--registration", "all",
     "--color", "registration"],
    ["mask", "--rect", "0,0,3,2"],
    ["join", "--all"],
])
def test_commands_run(sample, tmp_path, args):
    out = tmp_path / "o.pdf"
    assert run(*args, sample, "-o", out) == 0
    pdf = pikepdf.open(out)
    assert len(pdf.pages) > 0
    check = subprocess.run(["qpdf", "--check", str(out)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr


def test_text_and_peel(sample, tmp_path):
    stamped = tmp_path / "t.pdf"
    assert run("text", "--text", "STAMP[#]", sample, "-o", stamped) == 0
    imposed = tmp_path / "n.pdf"
    assert run("nup", "--cols", "2", "--rows", "1", "--scale", "fit", "--paper", "a4", "--orientation", "wide",
               stamped, "-o", imposed) == 0
    assert "STAMP1" in page_texts(imposed)[0]
    peeled = tmp_path / "p.pdf"
    assert run("peel", "--what", "text", imposed, "-o", peeled) == 0
    assert "STAMP" not in " ".join(page_texts(peeled))


def test_history_replay(sample, tmp_path):
    first = tmp_path / "first.pdf"
    assert run("text", "--text", "N[#]", sample, "-o", first) == 0
    second = tmp_path / "second.pdf"
    assert run("booklet", "--binding", "saddle", "--paper", "a4", first, "-o", second) == 0
    seq = tmp_path / "seq.toml"
    assert main(["replay", "--from", str(second), str(sample), "--export", str(seq)]) == 0
    assert "booklet --binding saddle" in seq.read_text()
    again = tmp_path / "again.pdf"
    assert main(["replay", "--from", str(second), str(sample), "-o", str(again)]) == 0
    assert page_texts(again) == page_texts(second)


def test_split_merge(sample, tmp_path):
    out = tmp_path / "s.pdf"
    assert run("split", "--by", "equal", "--size", "4", "--part-steps", "1=reverse", "--merge", sample,
               "-o", out) == 0
    texts = page_texts(out)
    assert len(texts) == 10
    assert "page 4 of" in texts[0] and "page 5 of" in texts[4]


EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "example" / "numbers-100.pdf"


@pytest.mark.skipif(not EXAMPLE.is_file(), reason="example document not present")
def test_example_document(tmp_path):
    """The example: 100 pages in 16-page signatures -> 7 signatures (112 pages), 28 sheets, 56 sides."""
    numbered = tmp_path / "numbered.pdf"
    assert run("text", "--text", "Page [#] of [Doc:NumPages]", EXAMPLE, "-o", numbered) == 0
    assert "Page 100 of 100" in subprocess.run(["pdftotext", "-f", "100", "-l", "100", str(numbered), "-"],
                                               capture_output=True, text=True).stdout
    out = tmp_path / "book.pdf"
    assert run("booklet", "--signature", "16", "--paper", "a4", "--crop-marks", "--margin", "1.5cm",
               numbered, "-o", out) == 0
    pdf = pikepdf.open(out)
    assert len(pdf.pages) == 56
    # the first sheet carries pages 16 and 1 of the first signature
    first = " ".join(subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(out), "-"],
                                    capture_output=True, text=True).stdout.split())
    assert "Page 16 of 100" in first and "Page 1 of 100" in first
    check = subprocess.run(["qpdf", "--check", str(out)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout
