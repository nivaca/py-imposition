"""Core 2-up booklet imposition logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pikepdf import Rectangle

CM = 72 / 2.54  # PostScript points per centimetre

# Portrait dimensions (width, height) in points.
PAPER_SIZES: dict[str, tuple[float, float]] = {
    "letter": (612, 792),
    "legal": (612, 1008),
    "tabloid": (792, 1224),
    "a3": (841.89, 1190.55),
    "a4": (595.28, 841.89),
    "a5": (419.53, 595.28),
}


@dataclass
class Margins:
    """Margins in centimetres."""

    top: float = 0.0
    bottom: float = 0.0
    left: float = 0.0
    right: float = 0.0


@dataclass
class Settings:
    binding: str = "perfect"  # "perfect" (stacked signatures) or "saddle" (one nested signature)
    pages_per_fold: int = 4  # pages per signature; multiple of 4 (4 = one sheet folded once)
    direction: str = "left"  # binding edge: "left" (LTR books) or "right" (RTL books)
    paper: str = "legal"
    orientation: str = "landscape"
    margins: Margins = field(default_factory=Margins)
    gutter: float = 0.0  # cm between the two page cells (at the fold)
    auto_scale: bool = True  # scale pages up/down to fit their cell, keeping aspect ratio
    align: str = "center"  # horizontal placement in each cell: "center" or "fold"


def sheet_size(s: Settings) -> tuple[float, float]:
    w, h = PAPER_SIZES[s.paper]
    if s.orientation == "landscape":
        w, h = h, w
    return w, h


def signature_order(n: int, direction: str = "left") -> list[tuple[int | None, int | None]]:
    """Return the (left, right) page indices of each sheet side for a signature of n pages.

    Indices are 0-based within the signature. Sides alternate front, back, front, back...
    Sheets are nested: the outermost sheet carries the first and last pages.
    """
    if n % 4:
        raise ValueError("signature size must be a multiple of 4")
    sides = []
    for i in range(n // 4):
        front = (n - 1 - 2 * i, 2 * i)
        back = (2 * i + 1, n - 2 - 2 * i)
        sides += [front, back]
    if direction == "right":
        sides = [(r, l) for l, r in sides]
    return sides


def impose_order(page_count: int, s: Settings) -> list[tuple[int | None, int | None]]:
    """Map the document's pages onto sheet sides. None marks a blank cell."""
    if s.binding == "saddle":
        sig = -(-page_count // 4) * 4  # whole document in one signature
    else:
        if s.pages_per_fold < 4 or s.pages_per_fold % 4:
            raise ValueError("pages per fold must be a positive multiple of 4")
        sig = s.pages_per_fold
    total = -(-page_count // sig) * sig
    order = []
    for start in range(0, total, sig):
        for l, r in signature_order(sig, s.direction):
            order.append(tuple(
                start + p if start + p < page_count else None for p in (l, r)
            ))
    return order


def cells(s: Settings) -> tuple[Rectangle, Rectangle]:
    """Left and right placement rectangles on the sheet, in points."""
    w, h = sheet_size(s)
    m = s.margins
    x0, x1 = m.left * CM, w - m.right * CM
    y0, y1 = m.bottom * CM, h - m.top * CM
    g = s.gutter * CM
    cw = (x1 - x0 - g) / 2
    if cw <= 0 or y1 <= y0:
        raise ValueError("margins/gutter leave no room for pages")
    return (
        Rectangle(x0, y0, x0 + cw, y1),
        Rectangle(x0 + cw + g, y0, x1, y1),
    )


def _form_size(formx: pikepdf.Object) -> tuple[float, float]:
    """Displayed width/height of a form XObject (its BBox mapped through /Matrix)."""
    x0, y0, x1, y1 = (float(v) for v in formx.BBox)
    a, b, c, d, e, f = (float(v) for v in formx.get("/Matrix", [1, 0, 0, 1, 0, 0]))
    pts = [(a * x + c * y + e, b * x + d * y + f) for x in (x0, x1) for y in (y0, y1)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def _fold_rect(cell: Rectangle, formx: pikepdf.Object, fold_on_right: bool, expand: bool) -> Rectangle:
    """Narrow a cell to the page's scaled width, flush against the fold."""
    w, h = _form_size(formx)
    scale = min(cell.width / w, cell.height / h)
    if not expand:
        scale = min(scale, 1.0)
    pw = w * scale
    if fold_on_right:
        return Rectangle(cell.urx - pw, cell.lly, cell.urx, cell.ury)
    return Rectangle(cell.llx, cell.lly, cell.llx + pw, cell.ury)


def impose(src: Path, dst: Path, s: Settings | None = None) -> int:
    """Impose src into dst. Returns the number of output sheet sides."""
    s = s or Settings()
    w, h = sheet_size(s)
    left_cell, right_cell = cells(s)

    with pikepdf.open(src) as pdf_in, pikepdf.new() as pdf_out:
        pages = pdf_in.pages
        order = impose_order(len(pages), s)
        for left, right in order:
            sheet = pdf_out.add_blank_page(page_size=(w, h))
            for idx, rect, fold_on_right in ((left, left_cell, True), (right, right_cell, False)):
                if idx is None:
                    continue
                src_page = pdf_out.copy_foreign(pages[idx].obj)
                formx = pikepdf.Page(src_page).as_form_xobject()
                if s.align == "fold":
                    rect = _fold_rect(rect, formx, fold_on_right, s.auto_scale)
                sheet.add_overlay(
                    formx,
                    rect,
                    shrink=True,
                    expand=s.auto_scale,
                )
        pdf_out.save(dst)
        return len(order)
