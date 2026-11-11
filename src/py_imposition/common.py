"""Command framework: context, registry and option helpers."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pikepdf
from pikepdf import Pdf

from . import pdfutil as pu
from .units import PAPER_SIZES, orient, parse_length, parse_length_list, parse_paper


class ImpositionError(Exception):
    """A user-facing error (bad options, impossible layout...)."""


@dataclass
class Context:
    units: str = "cm"
    registration: str = "black"  # black | cmyk | all
    use_bleed: bool = True
    pdfx: bool = False
    input_path: Path | None = None
    quiet: bool = False
    warnings: list[str] = field(default_factory=list)

    def L(self, value) -> float:
        """Parse a length in the current units."""
        try:
            return parse_length(value, self.units)
        except ValueError as e:
            raise ImpositionError(str(e)) from None

    def LL(self, value) -> list[float]:
        try:
            return parse_length_list(value, self.units)
        except ValueError as e:
            raise ImpositionError(str(e)) from None

    def paper(self, spec: str, orientation: str = "as-is") -> tuple[float, float]:
        try:
            return orient(parse_paper(spec, self.units), orientation)
        except ValueError as e:
            raise ImpositionError(str(e)) from None

    def warn(self, msg: str):
        self.warnings.append(msg)
        if not self.quiet:
            print(f"warning: {msg}", file=sys.stderr)


# A command result is a single PDF, or several named PDFs (suffix -> Pdf).
Result = Pdf | dict[str, Pdf]


@dataclass
class Command:
    name: str
    help: str
    add_args: Callable[[argparse.ArgumentParser], None]
    run: Callable[[Pdf | None, argparse.Namespace, Context], Result]
    needs_input: bool = True
    description: str | None = None


COMMANDS: dict[str, Command] = {}


def command(name: str, help: str, args: Callable[[argparse.ArgumentParser], None], *,
            needs_input: bool = True, description: str | None = None):
    """Decorator registering a command's run function."""

    def deco(run):
        COMMANDS[name] = Command(name, help, args, run, needs_input, description)
        return run

    return deco


# --------------------------------------------------------------------------- option helpers


def add_page_args(p: argparse.ArgumentParser, what: str = "pages to process"):
    p.add_argument("--pages", default="all", metavar="RANGE",
                   help=f"{what}: e.g. 'all', '1-4,7', 'LAST-1..LAST' (default: all)")
    p.add_argument("--parity", choices=["all", "odd", "even"], default="all",
                   help="restrict to odd or even page numbers")


def add_margin_args(p: argparse.ArgumentParser, name: str = "margin", help_what: str = "margin"):
    p.add_argument(f"--{name}", default="0", metavar="LEN",
                   help=f"{help_what} on all four sides (default: 0)")
    for side in ("top", "bottom", "left", "right"):
        p.add_argument(f"--{name}-{side}", default=None, metavar="LEN",
                       help=f"{side} {help_what} (overrides --{name})")


def get_margins(args, ctx: Context, name: str = "margin") -> tuple[float, float, float, float]:
    """Return (left, bottom, right, top) in points."""
    base = getattr(args, name.replace("-", "_"))
    out = []
    for side in ("left", "bottom", "right", "top"):
        v = getattr(args, f"{name.replace('-', '_')}_{side}")
        out.append(ctx.L(base if v is None else v))
    return tuple(out)


def add_paper_args(p: argparse.ArgumentParser, default: str = "a4", default_orientation: str = "tall",
                   extra_choices: tuple[str, ...] = ()):
    p.add_argument("--paper", default=default, metavar="SIZE",
                   help=f"sheet size: {', '.join(sorted(PAPER_SIZES))}{''.join(', ' + c for c in extra_choices)}, "
                        f"or WxH such as 21x29.7cm (default: {default})")
    p.add_argument("--orientation", default=default_orientation,
                   choices=["tall", "wide", "portrait", "landscape", "best", "as-is"],
                   help=f"sheet orientation (default: {default_orientation})")


def add_mark_args(p: argparse.ArgumentParser, frames: bool = True):
    g = p.add_argument_group("marks")
    g.add_argument("--crop-marks", action="store_true", help="add smart crop marks")
    if frames:
        g.add_argument("--frames", action="store_true", help="draw a frame around each page")
    g.add_argument("--mark-offset", default="10pt", metavar="LEN",
                   help="gap between page edge and crop mark (default: 10pt)")
    g.add_argument("--mark-length", default="20pt", metavar="LEN", help="crop mark length (default: 20pt)")
    g.add_argument("--mark-width", default="0.5pt", metavar="LEN", help="crop mark line width (default: 0.5pt)")
    g.add_argument("--mark-white-background", action="store_true",
                   help="draw a near-white halo behind marks so they show on dark backgrounds")


def get_mark_style(args, ctx: Context) -> pu.MarkStyle:
    return pu.MarkStyle(
        offset=ctx.L(args.mark_offset),
        length=ctx.L(args.mark_length),
        width=ctx.L(args.mark_width),
        white_background=args.mark_white_background,
        registration=ctx.registration,
    )


def add_sides_args(p: argparse.ArgumentParser):
    p.add_argument("--sides", default="duplex",
                   choices=["duplex", "flip-backs", "fronts-then-backs", "separate"],
                   help="how to output fronts and backs: duplex (in order), flip-backs (backs upside down), "
                        "fronts-then-backs (one file, all fronts first), separate (two files) (default: duplex)")
    p.add_argument("--reverse-backs", action="store_true",
                   help="output the backs in reverse order (for manual double-sided printing)")


def arrange_sides(pdf: Pdf, mode: str, reverse_backs: bool = False) -> Result:
    """Rearrange alternating front/back sheets for single-sided printers."""
    if mode == "duplex" and not reverse_backs:
        return pdf
    n = len(pdf.pages)
    fronts = list(range(0, n, 2))
    backs = list(range(1, n, 2))
    if reverse_backs:
        backs.reverse()
    if mode == "flip-backs":
        for i in range(1, n, 2):
            page = pdf.pages[i]
            page.obj.Rotate = (pu.page_rotation(page.obj) + 180) % 360
        if not reverse_backs:
            return pdf
        mode = "duplex"
    if mode == "duplex":
        order = []
        for f, b in zip(fronts, backs + [None] * (len(fronts) - len(backs))):
            order.append(f)
            if b is not None:
                order.append(b)
        return reorder(pdf, order)
    if mode == "fronts-then-backs":
        return reorder(pdf, fronts + backs)
    if mode == "separate":
        return {"fronts": reorder(pdf, fronts), "backs": reorder(pdf, backs)}
    raise ImpositionError(f"unknown sides mode {mode!r}")


def reorder(pdf: Pdf, order: list[int | None], blank_size: tuple[float, float] | None = None) -> Pdf:
    """New document with pages of ``pdf`` in ``order`` (None = blank page)."""
    out = Pdf.new()
    pu.copy_docinfo(pdf, out)
    if blank_size is None and len(pdf.pages):
        blank_size = pu.visual_size(pdf.pages[0].obj, use_bleed=False)
    for idx in order:
        if idx is None:
            pg = out.add_blank_page(page_size=blank_size or (612, 792))
            if "/Contents" in pg.obj:
                del pg.obj["/Contents"]
        else:
            out.pages.append(pdf.pages[idx])
    return out


def max_page_size(pdf: Pdf, ctx: Context) -> tuple[float, float]:
    w = h = 0.0
    for page in pdf.pages:
        pw, ph = pu.geometry(page.obj, ctx.use_bleed).size()
        w, h = max(w, pw), max(h, ph)
    return w, h


ALIGN_H = {"left": 0.0, "center": 0.5, "centre": 0.5, "right": 1.0}
ALIGN_V = {"top": 1.0, "middle": 0.5, "center": 0.5, "centre": 0.5, "bottom": 0.0}
ALIGN_CHOICES = ["top-left", "top", "top-right", "left", "center", "right",
                 "bottom-left", "bottom", "bottom-right"]


def parse_align(spec: str) -> tuple[float, float]:
    """Map an alignment name to (horizontal, vertical) fractions (0=left/bottom)."""
    s = spec.lower().replace("centre", "center")
    if s == "center":
        return 0.5, 0.5
    parts = s.split("-")
    h, v = 0.5, 0.5
    for part in parts:
        if part in ("left", "right"):
            h = ALIGN_H[part]
        elif part in ("top", "bottom"):
            v = ALIGN_V[part]
        elif part in ("center", "middle"):
            pass
        else:
            raise ImpositionError(f"invalid alignment {spec!r}")
    return h, v
