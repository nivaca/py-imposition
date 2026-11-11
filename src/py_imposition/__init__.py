"""py-imposition: impose PDFs into 2-up booklets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .imposition import PAPER_SIZES, Margins, Settings, impose

__all__ = ["impose", "Settings", "Margins", "main"]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="py-imposition",
        description="Impose a PDF as a 2-up booklet (default: perfect binding, "
        "4 pages per fold, left binding, Legal landscape, no margins/gutters, auto scale).",
    )
    p.add_argument("input", type=Path, help="source PDF")
    p.add_argument("output", type=Path, nargs="?", help="output PDF (default: <input>-imposed.pdf)")
    p.add_argument("--binding", choices=["perfect", "saddle"], default="perfect",
                   help="perfect: stacked signatures; saddle: all sheets nested in one signature")
    p.add_argument("--pages-per-fold", type=int, default=4, metavar="N",
                   help="pages per signature for perfect binding, multiple of 4 (default: 4)")
    p.add_argument("--direction", choices=["left", "right"], default="left",
                   help="binding edge (default: left)")
    p.add_argument("--paper", choices=sorted(PAPER_SIZES), default="legal")
    p.add_argument("--orientation", choices=["landscape", "portrait"], default="landscape")
    p.add_argument("--margin", type=float, default=0.0, metavar="CM",
                   help="margin on all sides, in cm (default: 0)")
    for side in ("top", "bottom", "left", "right"):
        p.add_argument(f"--margin-{side}", type=float, metavar="CM",
                       help=f"{side} margin in cm (overrides --margin)")
    p.add_argument("--gutter", type=float, default=0.0, metavar="CM",
                   help="space between the two pages at the fold, in cm (default: 0)")
    p.add_argument("--no-auto-scale", dest="auto_scale", action="store_false",
                   help="only shrink pages that don't fit; never enlarge")
    p.add_argument("--align", choices=["center", "fold"], default="center",
                   help="center pages in their half of the sheet, or push them against the fold "
                   "(default: center)")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    if not a.input.is_file():
        print(f"error: {a.input} not found", file=sys.stderr)
        return 1
    out = a.output or a.input.with_name(f"{a.input.stem}-imposed.pdf")
    m = {s: getattr(a, f"margin_{s}") for s in ("top", "bottom", "left", "right")}
    settings = Settings(
        binding=a.binding,
        pages_per_fold=a.pages_per_fold,
        direction=a.direction,
        paper=a.paper,
        orientation=a.orientation,
        margins=Margins(**{k: a.margin if v is None else v for k, v in m.items()}),
        gutter=a.gutter,
        auto_scale=a.auto_scale,
        align=a.align,
    )
    try:
        n = impose(a.input, out, settings)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"Wrote {out} ({n} sheet sides, {n // 2} sheets; print duplex, flip on short edge)")
    return 0
