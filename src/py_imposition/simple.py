"""The "impose" command: all the usual impositions in one command, with the
options of a common imposition dialog (layout, binding, gutters, paper,
margins and printer marks). It is what the window's basic mode runs.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import math
import re

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, add_margin_args, command, get_margins
from .impose import booklet_order
from .interface import N_, tr
from .shuffle import parse_rule, shuffle_order

LAYOUTS = ["2up-booklet", "4up-booklet", "8up-booklet", "cut-stacks", "sequential", "step-repeat"]
BOOKLETS = {"2up-booklet", "4up-booklet", "8up-booklet"}

# The folding layouts of the first sheet (front, then back; row by row from the
# top left). * = upside down. They stretch to any length with the saddle repeat.
RULE_4UP = "8 1 5* 4* 2 7 3* 6*"
RULE_8UP = "5* 12* 9* 8* 4 13 16 1 7* 10* 11* 6* 2 15 14 3"

Slot = tuple  # (page index or None, rotation clockwise)


def _args(p):
    g = p.add_argument_group(tr("layout"))
    g.add_argument("--layout", choices=LAYOUTS, default="2up-booklet",
                   help=tr("2up-booklet: 2 pages side by side; 4up-booklet: 2 rows of 2; 8up-booklet: 2 rows of "
                           "4; cut-stacks: cut the sheets and stack the piles; sequential: pages in order; "
                           "step-repeat: copies of each page (default: 2up-booklet)"))
    g.add_argument("--cols", type=int, default=2, help=tr("columns, for cut-stacks, sequential and step-repeat "
                                                          "(default: 2)"))
    g.add_argument("--rows", type=int, default=2, help=tr("rows, for cut-stacks, sequential and step-repeat "
                                                          "(default: 2)"))
    g = p.add_argument_group(tr("binding"))
    g.add_argument("--binding", choices=["saddle", "perfect"], default="perfect",
                   help=tr("saddle: all sheets folded together and stapled; perfect: stacks of folded sheets, "
                           "glued at the spine (default: perfect)"))
    g.add_argument("--sheets-per-fold", type=int, default=1, metavar="N",
                   help=tr("perfect binding: sheets in each folded stack (default: 1)"))
    g.add_argument("--direction", choices=["left", "right"], default="left",
                   help=tr("binding edge (default: left)"))
    g.add_argument("--single-sided", action="store_true",
                   help=tr("print on one side only: fronts, then backs (booklets), or single-sided stacks"))
    g = p.add_argument_group(tr("gutters"))
    g.add_argument("--gutter-v", default="0", metavar="LEN", help=tr("space between columns (default: 0)"))
    g.add_argument("--gutter-h", default="0", metavar="LEN", help=tr("space between rows (default: 0)"))
    g.add_argument("--spread", default=None, metavar="LEN",
                   help=tr("8up-booklet: space between the 2nd and 3rd columns (default: as --gutter-v)"))
    g.add_argument("--creep", default="0", metavar="LEN",
                   help=tr("booklets: how far the innermost pages move toward the spine, for the paper's "
                           "thickness (default: 0)"))
    g = p.add_argument_group(tr("paper"))
    g.add_argument("--media", default="legal", metavar="SIZE",
                   help=tr("sheet size: a paper name or WxH, or 'auto' to fit the pages exactly (default: legal)"))
    g.add_argument("--orientation", choices=["portrait", "landscape"], default="landscape",
                   help=tr("orientation of a named sheet size (default: landscape)"))
    g.add_argument("--auto-rotate", action="store_true",
                   help=tr("turn pages 90° when that fits their cell better"))
    g.add_argument("--no-auto-scale", action="store_true",
                   help=tr("don't shrink pages that are larger than their cell"))
    add_margin_args(p, "margin", tr("margin"))
    g = p.add_argument_group(tr("printer marks"))
    g.add_argument("--trim-marks", action="store_true", help=tr("marks where the pages are to be trimmed"))
    g.add_argument("--bleed-marks", action="store_true", help=tr("outline of the bleed area of pages that have one"))
    g.add_argument("--registration-marks", action="store_true",
                   help=tr("targets at the sides of the sheet, for aligning plates"))
    g.add_argument("--page-info", action="store_true",
                   help=tr("the document name, sheet number, date and time at the top left of each sheet"))
    g.add_argument("--page-info-name", default=None, metavar="NAME", help=argparse.SUPPRESS)


# --------------------------------------------------------------------------- page order


def _chunks(slots: list[Slot], size: int) -> list[list[Slot]]:
    return [slots[i:i + size] for i in range(0, len(slots), size)]


def _mirror_rows(side: list[Slot], cols: int) -> list[Slot]:
    return [s for r in range(0, len(side), cols) for s in reversed(side[r:r + cols])]


def _folded(count: int, rule: str, group: int, binding: str, sheets: int) -> list[Slot]:
    """Pages for a folded booklet layout: one saddle-stitched run, or stacks of SHEETS sheets."""
    parsed = parse_rule(rule)
    if binding == "saddle":
        return shuffle_order(count, parsed, group, "saddle")
    size = group * max(sheets, 1)
    out: list[Slot] = []
    for start in range(0, max(count, 1), size):
        for idx, rot in shuffle_order(size, parsed, group, "saddle"):
            page = start + idx if idx is not None and start + idx < count else None
            out.append((page, rot))
    return out


def plan(layout: str, count: int, cols: int, rows: int, binding: str, sheets: int, direction: str,
         double: bool) -> tuple[int, int, list[list[Slot]]]:
    """(columns, rows, sides): what goes in each cell of each sheet side."""
    if layout == "2up-booklet":
        cols, rows = 2, 1
        sides = [[(l, 0), (r, 0)] for l, r in booklet_order(count, binding, 4 * max(sheets, 1), "full", direction)]
    elif layout in ("4up-booklet", "8up-booklet"):
        cols, rows, rule, group = (2, 2, RULE_4UP, 8) if layout == "4up-booklet" else (4, 2, RULE_8UP, 16)
        sides = _chunks(_folded(count, rule, group, binding, sheets), cols * rows)
        if direction == "right":
            sides = [_mirror_rows(s, cols) for s in sides]
    else:
        if cols < 1 or rows < 1:
            raise ImpositionError(tr("columns and rows must be at least 1"))
        n = cols * rows
        if layout == "step-repeat":
            sides = [[(i, 0)] * n for i in range(count)]
        elif layout == "sequential":
            slots = [(i, 0) for i in range(count)]
            slots += [(None, 0)] * (-len(slots) % n)
            sides = _chunks(slots, n)
            if direction == "right":
                sides = [_mirror_rows(s, cols) for s in sides]
        else:  # cut stacks
            if double:
                mirror = [r * cols + (cols - 1 - c) for r in range(rows) for c in range(cols)]
                rule = [2 * p + 1 for p in range(n)] + [2 * mirror[p] + 2 for p in range(n)]
                order = shuffle_order(count, parse_rule(" ".join(map(str, rule))), 2 * n, "cut-double")
            else:
                order = shuffle_order(count, parse_rule(" ".join(map(str, range(1, n + 1)))), n, "cut-single")
            sides = _chunks(order, n)
    if layout in BOOKLETS and not double:
        sides = sides[0::2] + sides[1::2]  # all the fronts, then all the backs
    return cols, rows, sides


# --------------------------------------------------------------------------- marks


def registration_target(canvas: pu.Canvas, x: float, y: float, colour: bytes):
    r, arm = 5.0, 9.0
    k = 0.5523 * r  # (a circle from four Bézier curves)
    path = (f"{pu.fmt(x - arm)} {pu.fmt(y)} m {pu.fmt(x + arm)} {pu.fmt(y)} l "
            f"{pu.fmt(x)} {pu.fmt(y - arm)} m {pu.fmt(x)} {pu.fmt(y + arm)} l "
            f"{pu.fmt(x + r)} {pu.fmt(y)} m "
            f"{pu.fmt(x + r)} {pu.fmt(y + k)} {pu.fmt(x + k)} {pu.fmt(y + r)} {pu.fmt(x)} {pu.fmt(y + r)} c "
            f"{pu.fmt(x - k)} {pu.fmt(y + r)} {pu.fmt(x - r)} {pu.fmt(y + k)} {pu.fmt(x - r)} {pu.fmt(y)} c "
            f"{pu.fmt(x - r)} {pu.fmt(y - k)} {pu.fmt(x - k)} {pu.fmt(y - r)} {pu.fmt(x)} {pu.fmt(y - r)} c "
            f"{pu.fmt(x + k)} {pu.fmt(y - r)} {pu.fmt(x + r)} {pu.fmt(y - k)} {pu.fmt(x + r)} {pu.fmt(y)} c S\n")
    canvas.raw(b"q 0.4 w\n" + colour + path.encode() + b"Q\n", pu.TAG_MARKS)


def page_info(canvas: pu.Canvas, text: str, H: float, colour: bytes):
    from pikepdf import Dictionary, Name
    fonts = canvas.res.get("/Font") or Dictionary()
    fonts["/PyImpInfo"] = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
                                     Encoding=Name.WinAnsiEncoding)
    canvas.res.Font = fonts
    data = text.encode("cp1252", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    fill = colour.replace(b" K", b" k").replace(b" G", b" g").replace(b"CS", b"cs").replace(b"SCN", b"scn")
    canvas.raw(b"q " + fill + b"BT /PyImpInfo 7 Tf 8 " + pu.fmt(H - 12).encode() + b" Td (" + data
               + b") Tj ET Q\n", pu.TAG_MARKS)


# --------------------------------------------------------------------------- the command


@command("impose", "impose in one step: booklets, cut stacks, sequential or step and repeat", _args,
         description=N_("Impose a document in one step, with the usual layouts (2-, 4- and 8-up booklets, cut "
                        "stacks, sequential, step and repeat), binding, gutters, paper, margins and printer "
                        "marks. The window's basic mode runs this command."))
def impose(pdf: Pdf, a, ctx: Context):
    count = len(pdf.pages)
    if count == 0:
        raise ImpositionError(tr("document has no pages"))
    if a.sheets_per_fold < 1:
        raise ImpositionError(tr("sheets per fold must be at least 1"))
    double = not a.single_sided
    creep = ctx.L(a.creep)
    if creep > 0 and a.layout in BOOKLETS:
        from .pagetools import creep as creep_pages
        group = {"2up-booklet": 4, "4up-booklet": 8, "8up-booklet": 16}[a.layout]
        ns = argparse.Namespace(scope="document" if a.binding == "saddle" else "signatures",
                                signature=group * a.sheets_per_fold, thickness=None, total=a.creep,
                                shift_most="inside", method="shift", direction=a.direction)
        pdf = creep_pages(pdf, ns, ctx)
    cols, rows, sides = plan(a.layout, count, a.cols, a.rows, a.binding, a.sheets_per_fold, a.direction, double)
    gv, gh = ctx.L(a.gutter_v), ctx.L(a.gutter_h)
    spread = ctx.L(a.spread) if a.spread is not None else gv
    vgaps = [spread if a.layout == "8up-booklet" and k == 1 else gv for k in range(cols - 1)]
    hgaps = [gh] * (rows - 1)
    ml, mb, mr, mt = get_margins(a, ctx)

    geoms = [pu.geometry(p.obj, ctx.use_bleed) for p in pdf.pages]
    sizes = [g.size() for g in geoms]
    maxw = max(w for w, _ in sizes)
    maxh = max(h for _, h in sizes)
    if a.media.lower() == "auto":
        cw, ch = maxw, maxh
        W = cols * cw + sum(vgaps) + ml + mr
        H = rows * ch + sum(hgaps) + mb + mt
    else:
        named = not re.search(r"\d\s*[x×*]\s*\d", a.media)
        W, H = ctx.paper(a.media, a.orientation if named else "as-is")
        cw = (W - ml - mr - sum(vgaps)) / cols
        ch = (H - mb - mt - sum(hgaps)) / rows
    if cw <= 0 or ch <= 0:
        raise ImpositionError(tr("margins and gutters leave no room for pages"))

    def turn(i: int) -> int:
        """Auto-rotate: 90° when the page's shape doesn't match its cell's."""
        if not a.auto_rotate:
            return 0
        w, h = sizes[i]
        return 90 if abs(w - h) > 1 and (w > h) != (cw > ch) else 0

    # one scale for the whole document, from the largest page (as turned)
    dims = [(sizes[i][1], sizes[i][0]) if turn(i) else sizes[i] for i in range(count)]
    s = min(cw / max(d[0] for d in dims), ch / max(d[1] for d in dims))
    s = 1.0 if a.no_auto_scale else min(s, 1.0)

    # cell rectangles, row by row from the top left
    xs, x = [], ml
    for c in range(cols):
        xs.append(x)
        x += cw + (vgaps[c] if c < cols - 1 else 0)
    ys, y = [], H - mt
    for r in range(rows):
        ys.append(y - ch)
        y -= ch + (hgaps[r] if r < rows - 1 else 0)
    cells = [(xs[c], ys[r], xs[c] + cw, ys[r] + ch) for r in range(rows) for c in range(cols)]

    def clip_for(cell: pu.Rect, c: int, r: int) -> pu.Rect:
        left = cell[0] - (vgaps[c - 1] / 2 if c > 0 else cell[0])
        right = cell[2] + (vgaps[c] / 2 if c < cols - 1 else W - cell[2])
        bottom = cell[1] - (hgaps[r] / 2 if r < rows - 1 else cell[1])
        top = cell[3] + (hgaps[r - 1] / 2 if r > 0 else H - cell[3])
        return (left, bottom, right, top)

    style = pu.MarkStyle(registration=ctx.registration)
    name = a.page_info_name or (ctx.input_path.name if ctx.input_path else "")
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = Pdf.new()
    imp = pu.Importer(out)
    for n, side in enumerate(sides):
        canvas = pu.new_sheet(out, W, H)
        trims, bleeds = [], []
        for k, (idx, rot) in enumerate(side):
            if idx is None:
                continue
            page, geom = pdf.pages[idx].obj, geoms[idx]
            total = (rot + turn(idx)) % 360
            pw, ph = geom.size(total)
            pw, ph = pw * s, ph * s
            cell = cells[k]
            x0 = cell[0] + (cw - pw) / 2
            y0 = cell[1] + (ch - ph) / 2
            clip = clip_for(cell, k % cols, k // cols)
            rect = pu.place_page(canvas, imp, page, geom, x0, y0, s, rotate_cw=total, clip=clip)
            trims.append(rect)
            l, b, r, t = (m * s for m in geom.bleed_margins(total))
            if l or b or r or t:
                bleeds.append(pu.intersect(pu.expand(rect, l, b, r, t), clip))
        colour = canvas.reg_color(ctx.registration)
        if a.trim_marks and trims:
            pu.smart_crop_marks(canvas, trims, style, sheet=(0, 0, W, H))
        if a.bleed_marks and bleeds:
            canvas.raw(b"q 0.3 w [3 2] 0 d\n" + colour + b"".join(pu.re_op(r) + b"\n" for r in bleeds)
                       + b"S\nQ\n", pu.TAG_MARKS)
        if a.registration_marks:
            for x, y in ((W / 2, 12), (W / 2, H - 12), (12, H / 2), (W - 12, H / 2)):
                registration_target(canvas, x, y, colour)
        if a.page_info:
            page_info(canvas, f"{name}   {n + 1}/{len(sides)}   {stamp}".strip(), H, colour)
        canvas.finish()
    return out


def sheet_count(layout: str, count: int, cols: int, rows: int, binding: str, sheets: int, double: bool) -> int:
    """How many sheet sides the layout makes (for the window's summary)."""
    return len(plan(layout, count, cols, rows, binding, sheets, "left", double)[2])


__all__ = ["impose", "plan", "LAYOUTS", "math"]
