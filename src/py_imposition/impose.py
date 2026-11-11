"""Imposition onto sheets: Create booklet, n-Up Pages, Step And Repeat, Join Two Pages."""

from __future__ import annotations

from dataclasses import dataclass

import pikepdf
from pikepdf import Dictionary, Pdf

from . import pdfutil as pu
from .common import (
    ALIGN_CHOICES, Context, ImpositionError, add_margin_args, add_mark_args, add_paper_args,
    add_sides_args, arrange_sides, command, get_margins, get_mark_style, max_page_size, parse_align,
)
from .units import PAPER_SIZES
from .interface import N_, tr

EPS = 1e-6


# =========================================================================== booklet


def signature_sides(n: int, direction: str = "left") -> list[tuple[int, int]]:
    """(left, right) page indices of each sheet side for a nested signature of n pages."""
    sides = []
    for i in range(n // 4):
        sides.append((n - 1 - 2 * i, 2 * i))  # front
        sides.append((2 * i + 1, n - 2 - 2 * i))  # back
    if direction == "right":
        sides = [(r, l) for l, r in sides]
    return sides


def booklet_order(count: int, binding: str = "perfect", signature: int = 4, pad_last: str = "full",
                  direction: str = "left", single_sided: bool = False) -> list[tuple[int | None, int | None]]:
    """Map document pages onto (left, right) cells of each sheet side. None = blank."""

    def ceil(a, b):
        return -(-a // b)

    sides: list[tuple[int | None, int | None]] = []
    if binding == "saddle":
        total = ceil(count, 4) * 4
        sigs = [(0, total)]
    elif binding == "perfect":
        if signature < 4 or signature % 4:
            raise ImpositionError(tr("signature size (pages per fold) must be a positive multiple of 4"))
        sigs = []
        start = 0
        while start < count:
            remaining = count - start
            size = signature
            if remaining < signature and pad_last == "multiple-of-4":
                size = ceil(remaining, 4) * 4
            sigs.append((start, size))
            start += size
        if not sigs:
            sigs = [(0, 4)]
    elif binding == "continuous":
        total = ceil(count, 2) * 2
        for i in range(0, total, 2):
            sides.append((i, i + 1) if direction == "left" else (i + 1, i))
        return [tuple(p if p is not None and p < count else None for p in s) for s in sides]
    elif binding == "cut-stack":
        if single_sided:
            s = ceil(count, 2)
            for j in range(s):
                sides.append((j, s + j) if direction == "left" else (s + j, j))
        else:
            s = ceil(count, 4)
            for j in range(s):
                front = (2 * j, 2 * s + 2 * j)
                back = (2 * s + 2 * j + 1, 2 * j + 1)
                if direction == "right":
                    front, back = front[::-1], back[::-1]
                sides += [front, back]
        return [tuple(p if p is not None and p < count else None for p in side) for side in sides]
    else:
        raise ImpositionError(tr('unknown binding {binding!r}', binding=binding))

    for start, size in sigs:
        for l, r in signature_sides(size, direction):
            sides.append((start + l, start + r))
    return [tuple(p if p < count else None for p in side) for side in sides]


def _booklet_args(p):
    p.add_argument("--binding", choices=["perfect", "saddle", "continuous", "cut-stack"], default="perfect",
                   help=tr("perfect: separate folded signatures, stacked; saddle: all sheets nested and folded "
                        "together; continuous: pages in order 1,2 | 3,4 (not folded); cut-stack: sheets are "
                        "cut in half and the stacks placed one on the other (default: perfect)"))
    p.add_argument("--signature", "--pages-per-fold", dest="signature", type=int, default=4, metavar="N",
                   help=tr("pages per signature for perfect binding; multiple of 4 (default: 4)"))
    p.add_argument("--pad-last", choices=["full", "multiple-of-4"], default="full",
                   help=tr("perfect binding: pad a short last signature to full length or just to a multiple of 4"))
    p.add_argument("--single-sided", action="store_true", help=tr("cut-stack: single-sided stacks"))
    p.add_argument("--direction", choices=["left", "right"], default="left",
                   help=tr("binding edge: left (left-to-right books) or right (right-to-left) (default: left)"))
    add_paper_args(p, default="legal", default_orientation="wide", extra_choices=("auto",))
    add_margin_args(p, "margin", "space at the edge of the sheet")
    p.add_argument("--gutter", default="0", metavar="LEN", help=tr("space between the two pages (default: 0)"))
    sc = p.add_mutually_exclusive_group()
    sc.add_argument("--no-auto-scale", action="store_true", help=tr("shrink pages that don't fit, never enlarge"))
    sc.add_argument("--no-scale", action="store_true",
                    help=tr("place pages at 100%%; fail if they don't fit"))
    p.add_argument("--align", choices=["center", "fold", "spine"], default="center",
                   help=tr("center pages in their half of the sheet, or pull them to the fold/spine (default: center)"))
    add_sides_args(p)
    add_mark_args(p, frames=False)


@command("booklet", "create a 2-up booklet", _booklet_args,
         description=N_("Reorder pages and place them two per sheet side for folding into a booklet."))
def booklet(pdf: Pdf, a, ctx: Context):
    count = len(pdf.pages)
    if count == 0:
        raise ImpositionError(tr("document has no pages"))
    order = booklet_order(count, a.binding, a.signature, a.pad_last, a.direction, a.single_sided)
    maxw, maxh = max_page_size(pdf, ctx)
    ml, mb, mr, mt = get_margins(a, ctx)
    gutter = ctx.L(a.gutter)
    if a.paper.lower() == "auto":
        W, H = 2 * maxw + gutter + ml + mr, maxh + mb + mt
    else:
        W, H = ctx.paper(a.paper, a.orientation)
    cw = (W - ml - mr - gutter) / 2
    ch = H - mb - mt
    if cw <= 0 or ch <= 0:
        raise ImpositionError(tr("margins and gutter leave no room for pages"))
    s = min(cw / maxw, ch / maxh)
    if a.no_scale:
        if s < 1 - 1e-4:
            raise ImpositionError(
                tr("pages ({maxw:.1f}x{maxh:.1f}pt) don't fit at 100% in {cw:.1f}x{ch:.1f}pt cells; choose a larger paper or allow scaling", maxw=maxw, maxh=maxh, cw=cw, ch=ch))
        s = 1.0
    elif a.no_auto_scale:
        s = min(s, 1.0)
    cells = [(ml, mb, ml + cw, mb + ch), (ml + cw + gutter, mb, W - mr, mb + ch)]
    # clip areas: each cell extended to the sheet edge on the outside and to mid-gutter at the fold
    clips = [(0, 0, ml + cw + gutter / 2, H), (ml + cw + gutter / 2, 0, W, H)]
    fold_pull = a.align in ("fold", "spine")

    out = Pdf.new()
    imp = pu.Importer(out)
    style = get_mark_style(a, ctx)
    for side in order:
        canvas = pu.new_sheet(out, W, H)
        for k, idx in enumerate(side):
            if idx is None:
                continue
            page = pdf.pages[idx].obj
            geom = pu.geometry(page, ctx.use_bleed)
            pw, ph = geom.size()
            pw, ph = pw * s, ph * s
            cell = cells[k]
            if fold_pull:
                x = cell[2] - pw if k == 0 else cell[0]
            else:
                x = cell[0] + (cw - pw) / 2
            y = cell[1] + (ch - ph) / 2
            clip = pu.intersect(clips[k], pu.expand((x, y, x + pw, y + ph), *[m * s for m in geom.bleed_margins()]))
            pu.place_page(canvas, imp, page, geom, x, y, s, clip=clip)
        if a.crop_marks:
            pu.smart_crop_marks(canvas, cells, style, sheet=(0, 0, W, H))
        canvas.finish()
    return arrange_sides(out, a.sides, a.reverse_backs)


# =========================================================================== n-up engine


@dataclass
class Item:
    page: Dictionary | None
    geom: pu.PageGeom | None
    rot: float = 0.0  # extra clockwise rotation
    s: float = 1.0
    w: float = 0.0
    h: float = 0.0

    @classmethod
    def make(cls, page, geom, s, rot=0.0):
        w, h = geom.size(rot)
        return cls(page, geom, rot, s, w * s, h * s)


def _gap(lst: list[float], i: int) -> float:
    return lst[i % len(lst)] if lst else 0.0


def row_width(row: list[Item], hspace) -> float:
    return sum(i.w for i in row) + sum(_gap(hspace, k) for k in range(len(row) - 1))


def rows_height(rows: list[list[Item]], vspace) -> float:
    return sum(max(i.h for i in r) for r in rows) + sum(_gap(vspace, k) for k in range(len(rows) - 1))


def pack(items: list[Item], AW: float, AH: float, max_cols: int | None, max_rows: int | None,
         hspace: list[float], vspace: list[float]) -> list[list[list[Item]]]:
    """Greedy left-to-right, top-to-bottom packing into sheets of rows."""
    sheets: list[list[list[Item]]] = []
    rows: list[list[Item]] = []
    row: list[Item] = []

    def close_row():
        nonlocal rows, row
        if not row:
            return
        candidate = rows + [row]
        if rows and ((max_rows and len(candidate) > max_rows) or rows_height(candidate, vspace) > AH + EPS):
            sheets.append(rows)
            rows = [row]
        else:
            rows = candidate
        row = []

    for it in items:
        if row and ((max_cols and len(row) >= max_cols) or row_width(row + [it], hspace) > AW + EPS):
            close_row()
        row.append(it)
    close_row()
    if rows:
        sheets.append(rows)
    return sheets


@dataclass
class SheetSpec:
    W: float
    H: float
    margins: tuple[float, float, float, float]  # l b r t
    align: tuple[float, float]
    row_align: bool
    hspace: list[float]
    vspace: list[float]


def layout_sheet(rows: list[list[Item]], spec: SheetSpec, box: tuple[float, float],
                 mirror_h: bool, mirror_v: bool) -> list[tuple[Item, pu.Rect]]:
    l, b, r, t = spec.margins
    ah, av = spec.align
    if mirror_h:
        l, r, ah = r, l, 1 - ah
    if mirror_v:
        b, t, av = t, b, 1 - av
    AW, AH = spec.W - l - r, spec.H - b - t
    bw, bh = box
    bx = l + (AW - bw) * ah
    by = b + (AH - bh) * av
    top = by + bh
    placed = []
    for j, row in enumerate(rows):
        rh = max(i.h for i in row)
        rw = row_width(row, spec.hspace)
        x = bx + (bw - rw) * ah if spec.row_align else bx
        for k, it in enumerate(row):
            y = top - rh + (rh - it.h) * av
            placed.append((it, (x, y, x + it.w, y + it.h)))
            x += it.w + _gap(spec.hspace, k)
        top -= rh + _gap(spec.vspace, j)
    return placed


def bleed_clips(placed: list[tuple[Item, pu.Rect]], sheet: pu.Rect) -> list[pu.Rect]:
    """Clip rectangles letting each page's bleed show without overlapping neighbours."""
    rects = [r for _, r in placed]
    clips = []
    for idx, (it, r) in enumerate(placed):
        bl, bb, br, bt = (m * it.s for m in it.geom.bleed_margins(it.rot)) if it.geom else (0, 0, 0, 0)
        lim_l, lim_b = r[0] - sheet[0], r[1] - sheet[1]
        lim_r, lim_t = sheet[2] - r[2], sheet[3] - r[3]
        for j, o in enumerate(rects):
            if j == idx:
                continue
            v_overlap = o[1] < r[3] - EPS and o[3] > r[1] + EPS
            h_overlap = o[0] < r[2] - EPS and o[2] > r[0] + EPS
            if v_overlap and o[2] <= r[0] + EPS:
                lim_l = min(lim_l, (r[0] - o[2]) / 2)
            if v_overlap and o[0] >= r[2] - EPS:
                lim_r = min(lim_r, (o[0] - r[2]) / 2)
            if h_overlap and o[3] <= r[1] + EPS:
                lim_b = min(lim_b, (r[1] - o[3]) / 2)
            if h_overlap and o[1] >= r[3] - EPS:
                lim_t = min(lim_t, (o[1] - r[3]) / 2)
        clips.append(pu.expand(r, min(bl, max(lim_l, 0)), min(bb, max(lim_b, 0)),
                               min(br, max(lim_r, 0)), min(bt, max(lim_t, 0))))
    return clips


class Backgrounds:
    """Background sheets taken from a PDF, used in sequence."""

    def __init__(self, path: str, pages: str | None, mode: str, repeat_last: int, ctx: Context):
        from .pagesel import parse_pages
        self.pdf = pu.open_source(path)
        idx = parse_pages(pages, len(self.pdf.pages), keep_order=True)
        if not idx:
            raise ImpositionError(tr("background selection is empty"))
        self.idx = idx
        self.mode = mode
        self.repeat_last = repeat_last or len(idx)

    def page_for(self, n: int) -> Dictionary | None:
        idx = self.idx
        if n < len(idx):
            return self.pdf.pages[idx[n]].obj
        if self.mode == "once":
            return None
        if self.mode == "repeat-last":
            tail = idx[-self.repeat_last:]
            return self.pdf.pages[tail[(n - len(idx)) % len(tail)]].obj
        return self.pdf.pages[idx[n % len(idx)]].obj

    def size(self, n: int = 0) -> tuple[float, float]:
        page = self.page_for(n) or self.pdf.pages[self.idx[0]].obj
        return pu.geometry(page, use_bleed=False).size()


def draw_background(canvas: pu.Canvas, imp: pu.Importer, bg: Dictionary, W: float, H: float):
    geom = pu.geometry(bg, use_bleed=False)
    bw, bh = geom.size()
    pu.place_page(canvas, imp, bg, geom, (W - bw) / 2, (H - bh) / 2, 1.0)


def _add_bg_args(p):
    g = p.add_argument_group(tr("background"))
    g.add_argument("--background", metavar="PDF", help=tr("impose onto pages of this PDF instead of blank sheets "
                                                       "(sets the sheet size)"))
    g.add_argument("--background-pages", default="all", metavar="RANGE", help=tr("background pages to use"))
    g.add_argument("--background-mode", choices=["repeat", "once", "repeat-last"], default="repeat",
                   help=tr("repeat the backgrounds, use them once, or repeat only the last N (default: repeat)"))
    g.add_argument("--background-repeat-last", type=int, default=1, metavar="N",
                   help=tr("with --background-mode repeat-last: how many pages to repeat"))


def _add_layout_args(p, nup: bool):
    add_paper_args(p, default="a4" if not nup else "a4", default_orientation="best" if nup else "best")
    p.add_argument("--cols", type=int, default=None, help=tr("columns per sheet (maximum, or exact with --scale fit)"))
    p.add_argument("--rows", type=int, default=None, help=tr("rows per sheet (maximum, or exact with --scale fit)"))
    p.add_argument("--scale", default="none", metavar="MODE",
                   help=tr("'none' (100%%), 'fit' (scale so exactly --cols x --rows fit, based on the first page) "
                        "or a percentage like 50 (default: none)"))
    p.add_argument("--trim", action="store_true",
                   help=tr("remove unused space at the edge of each sheet (sheet shrinks to the pages plus margins)"))
    add_margin_args(p, "margin", "margin")
    p.add_argument("--spacing", default="0", metavar="LEN",
                   help=tr("space between rows and columns (default: 0)"))
    p.add_argument("--hspace", default=None, metavar="LIST",
                   help=tr("horizontal spacing between columns; a list like '0 40' repeats (overrides --spacing)"))
    p.add_argument("--vspace", default=None, metavar="LIST",
                   help=tr("vertical spacing between rows; a list repeats (overrides --spacing)"))
    p.add_argument("--align", choices=ALIGN_CHOICES, default="top-left",
                   help=tr("where pages sit on sheets that aren't full (default: top-left)"))
    p.add_argument("--align-sheets-independently", action="store_true",
                   help=tr("align each sheet on its own instead of matching all sheets"))
    p.add_argument("--align-rows", action="store_true", help=tr("also align each row horizontally (short rows)"))
    p.add_argument("--mirror", choices=["none", "h", "v", "hv"], default="none",
                   help=tr("mirror margins and alignment on even (back) sheets: horizontally, vertically or both"))
    add_mark_args(p)
    _add_bg_args(p)


def _scale_value(a, items_geom, AW, AH, hspace, vspace) -> float:
    mode = str(a.scale).lower()
    if mode in ("none", "100", "100%"):
        return 1.0
    if mode == "fit":
        if not (a.cols and a.rows):
            raise ImpositionError(tr("--scale fit needs both --cols and --rows"))
        w, h = items_geom.size()
        gw = sum(_gap(hspace, k) for k in range(a.cols - 1))
        gh = sum(_gap(vspace, k) for k in range(a.rows - 1))
        s = min((AW - gw) / (a.cols * w), (AH - gh) / (a.rows * h))
        if s <= 0:
            raise ImpositionError(tr("margins/spacing leave no room for pages"))
        return s
    try:
        return float(mode.rstrip("%")) / 100
    except ValueError:
        raise ImpositionError(tr('invalid --scale {scale!r}', scale=a.scale)) from None


def _spacing(a, ctx):
    hs = ctx.LL(a.hspace) if a.hspace is not None else [ctx.L(a.spacing)]
    vs = ctx.LL(a.vspace) if a.vspace is not None else [ctx.L(a.spacing)]
    return hs, vs


def _sheet_sizes(a, ctx, bg: Backgrounds | None):
    if bg is not None:
        return [bg.size()]
    if a.orientation == "best":
        w, h = ctx.paper(a.paper, "tall")
        return [(w, h), (h, w)] if abs(w - h) > EPS else [(w, h)]
    return [ctx.paper(a.paper, a.orientation)]


def render(out: Pdf, imp: pu.Importer, sheets_rows, spec: SheetSpec, a, ctx: Context,
           bg: Backgrounds | None, mirror: str, independent: bool, trim: bool,
           flip_back_sheets: set[int] | None = None, mirrored_slots: dict | None = None,
           sheet_numbers: list[int] | None = None):
    """Draw packed sheets, appending them to ``out``.

    ``sheet_numbers`` gives each sheet's logical number (for back-sheet
    mirroring and background selection); by default 0, 1, 2...
    """
    hspace, vspace = spec.hspace, spec.vspace
    boxes = [(max(row_width(r, hspace) for r in rows), rows_height(rows, vspace)) for rows in sheets_rows]
    doc_box = (max(b[0] for b in boxes), max(b[1] for b in boxes)) if boxes else (0, 0)
    style = get_mark_style(a, ctx) if hasattr(a, "mark_offset") else None
    for i, rows in enumerate(sheets_rows):
        n = sheet_numbers[i] if sheet_numbers else i
        box = boxes[i] if independent else doc_box
        back = n % 2 == 1
        mh = back and mirror in ("h", "hv")
        mv = back and mirror in ("v", "hv")
        W, H = spec.W, spec.H
        if trim:
            l, b, r, t = spec.margins
            W, H = box[0] + l + r, box[1] + b + t
        sspec = SheetSpec(W, H, spec.margins, spec.align, spec.row_align, hspace, vspace)
        placed = layout_sheet(rows, sspec, box, mh, mv)
        if mirrored_slots is not None and n in mirrored_slots:
            placed = mirrored_slots[n](placed, W, H)
        canvas = pu.new_sheet(out, W, H)
        if bg is not None:
            bgp = bg.page_for(n)
            if bgp is not None:
                draw_background(canvas, imp, bgp, W, H)
        real = [(it, r) for it, r in placed if it.page is not None]
        clips = bleed_clips(real, (0, 0, W, H))
        for (it, r), clip in zip(real, clips):
            pu.place_page(canvas, imp, it.page, it.geom, r[0], r[1], it.s, rotate_cw=it.rot, clip=clip)
        rects = [r for _, r in real]
        if style and getattr(a, "frames", False):
            pu.frame_rects(canvas, rects, style)
        if style and a.crop_marks:
            pu.smart_crop_marks(canvas, rects, style, sheet=(0, 0, W, H))
        if flip_back_sheets and n in flip_back_sheets:
            canvas.ops = [f"q -1 0 0 -1 {pu.fmt(W)} {pu.fmt(H)} cm\n".encode()] + canvas.ops + [b"Q\n"]
        canvas.finish()


def _nup_args(p):
    _add_layout_args(p, nup=True)
    p.add_argument("--flow", choices=["normal", "double", "double-flip"], default="normal",
                   help=tr("normal: fill each sheet in turn; double: alternate front/back sheets with backs "
                        "mirrored; double-flip: as double, with backs upside down (default: normal)"))


@command("nup", "place several pages on each sheet (n-up)", _nup_args,
         description=N_("Combine pages onto larger sheets in rows and columns, with margins, spacing, "
                     "alignment, crop marks and backgrounds."))
def nup(pdf: Pdf, a, ctx: Context):
    if not len(pdf.pages):
        raise ImpositionError(tr("document has no pages"))
    bg = Backgrounds(a.background, a.background_pages, a.background_mode, a.background_repeat_last, ctx) \
        if a.background else None
    hspace, vspace = _spacing(a, ctx)
    margins = get_margins(a, ctx)
    l, b, r, t = margins
    geoms = [pu.geometry(p.obj, ctx.use_bleed) for p in pdf.pages]
    trim = a.trim
    best = None
    for W, H in _sheet_sizes(a, ctx, bg):
        AW, AH = W - l - r, H - b - t
        if AW <= 0 or AH <= 0:
            raise ImpositionError(tr("margins leave no room on the sheet"))
        s = _scale_value(a, geoms[0], AW, AH, hspace, vspace)
        items = [Item.make(p.obj, g, s) for p, g in zip(pdf.pages, geoms)]
        need_w = max(i.w for i in items)
        need_h = max(i.h for i in items)
        if need_w > AW + EPS or need_h > AH + EPS:
            ctx.warn(tr('some pages are larger than the sheet; enlarging sheet to fit'))
            W, H = max(W, need_w + l + r), max(H, need_h + b + t)
            AW, AH = W - l - r, H - b - t
        if a.flow == "normal":
            sheets = pack(items, AW, AH, a.cols, a.rows, hspace, vspace)
            key = len(sheets)
        else:
            fronts = items[0::2]
            sheets = pack(fronts, AW, AH, a.cols, a.rows, hspace, vspace)
            key = 2 * len(sheets)
        cand = (key, -len(sheets[0][0]) if sheets else 0, W, H, items, sheets)
        if best is None or cand[:2] < best[:2]:
            best = cand
    _, _, W, H, items, sheets = best
    spec = SheetSpec(W, H, margins, parse_align(a.align), a.align_rows, hspace, vspace)
    out = Pdf.new()
    imp = pu.Importer(out)
    if a.flow == "normal":
        render(out, imp, sheets, spec, a, ctx, bg, a.mirror, a.align_sheets_independently, trim)
        return out
    # double flow: fronts on odd sheets, the following page on the matching back position
    backs = items[1::2]
    all_rows = []
    mirrored = {}
    flips = set()
    k = 0
    for rows in sheets:
        all_rows.append(rows)
        back_rows = []
        for row in rows:
            br = []
            for _ in row:
                br.append(backs[k] if k < len(backs) else Item(None, None, w=row[0].w, h=row[0].h))
                k += 1
            back_rows.append(br)
        n = len(all_rows)
        all_rows.append(back_rows)
        front_rows = rows

        def mirror_slots(placed, W_, H_, front_rows=front_rows, spec=spec):
            # put each back page in the mirror image of its front slot
            fplaced = layout_sheet(front_rows, SheetSpec(W_, H_, spec.margins, spec.align, spec.row_align,
                                                         spec.hspace, spec.vspace), box_for[id(front_rows)],
                                   False, False)
            out_ = []
            for (it, _), (_, fr) in zip(placed, fplaced):
                cx = W_ - (fr[0] + fr[2]) / 2
                cy = (fr[1] + fr[3]) / 2
                out_.append((it, (cx - it.w / 2, cy - it.h / 2, cx + it.w / 2, cy + it.h / 2)))
            return out_

        mirrored[n] = mirror_slots
        if a.flow == "double-flip":
            flips.add(n)
    # alignment boxes of the front sheets (shared with their backs)
    hs = spec.hspace
    fboxes = [(max(row_width(r, hs) for r in rows), rows_height(rows, spec.vspace)) for rows in sheets]
    doc_box = (max(bx[0] for bx in fboxes), max(bx[1] for bx in fboxes))
    box_for = {id(rows): (fboxes[i] if a.align_sheets_independently else doc_box) for i, rows in enumerate(sheets)}
    render(out, imp, all_rows, spec, a, ctx, bg, "none", a.align_sheets_independently, trim,
           flip_back_sheets=flips, mirrored_slots=mirrored)
    return out


# =========================================================================== step and repeat


def _max_count(size: float, avail: float, gaps: list[float], limit: int | None) -> int:
    n = 0
    total = 0.0
    while True:
        nxt = total + (_gap(gaps, n - 1) if n else 0) + size
        if nxt > avail + EPS or (limit and n >= limit):
            return n
        total = nxt
        n += 1


def step_rows(page, geom, s, AW, AH, a, hspace, vspace, allow_rotate: bool, back: bool, mirror: str):
    """Rows of copies of one page filling a sheet, optionally adding rows of rotated copies."""
    w, h = geom.size()
    w, h = w * s, h * s
    c1 = _max_count(w, AW, hspace, a.cols)
    c2 = _max_count(h, AW, hspace, a.cols) if allow_rotate else 0
    best = (0, 0, 0)
    max_r1 = _max_count(h, AH, vspace, a.rows) if c1 else 0
    for r1 in range(max_r1 + 1):
        heights = [h] * r1
        r2 = 0
        if allow_rotate and c2:
            while True:
                trial = heights + [w] * (r2 + 1)
                th = sum(trial) + sum(_gap(vspace, k) for k in range(len(trial) - 1))
                if th > AH + EPS or (a.rows and len(trial) > a.rows):
                    break
                r2 += 1
        total = r1 * c1 + r2 * c2
        if total > best[0] or (total == best[0] and r2 < best[2] and total):
            best = (total, r1, r2)
    total, r1, r2 = best
    if not allow_rotate:
        r1, r2 = max_r1, 0
    rot_rot = 90.0
    plain_rot = 0.0
    rotated_first = False
    if back and allow_rotate:
        if mirror in ("h", "hv"):
            rot_rot = 270.0
        if mirror in ("v", "hv"):
            plain_rot = 180.0
            rotated_first = True
    plain = [[Item.make(page, geom, s, plain_rot) for _ in range(c1)] for _ in range(r1)] if c1 else []
    rotated = [[Item.make(page, geom, s, rot_rot) for _ in range(c2)] for _ in range(r2)] if c2 else []
    return rotated + plain if rotated_first else plain + rotated


def _step_args(p):
    _add_layout_args(p, nup=False)
    p.add_argument("--rotate", action="store_true",
                   help=tr("allow rows of rotated copies when that fits more on a sheet (not with scaling)"))


@command("step-repeat", "fill sheets with copies of each page", _step_args,
         description=N_("Step And Repeat: each output sheet holds as many copies of one source page as fit."))
def step_repeat(pdf: Pdf, a, ctx: Context):
    if not len(pdf.pages):
        raise ImpositionError(tr("document has no pages"))
    bg = Backgrounds(a.background, a.background_pages, a.background_mode, a.background_repeat_last, ctx) \
        if a.background else None
    hspace, vspace = _spacing(a, ctx)
    margins = get_margins(a, ctx)
    l, b, r, t = margins
    allow_rotate = a.rotate
    if allow_rotate and str(a.scale).lower() not in ("none", "100", "100%"):
        ctx.warn(tr("--rotate is ignored when pages are scaled"))
        allow_rotate = False
    out = Pdf.new()
    imp = pu.Importer(out)
    sheets_rows = []
    chosen = None
    for n, page in enumerate(pdf.pages):
        geom = pu.geometry(page.obj, ctx.use_bleed)
        best = None
        for W, H in _sheet_sizes(a, ctx, bg):
            AW, AH = W - l - r, H - b - t
            s = _scale_value(a, geom, AW, AH, hspace, vspace)
            rows = step_rows(page.obj, geom, s, AW, AH, a, hspace, vspace, allow_rotate, n % 2 == 1, a.mirror)
            cnt = sum(len(rw) for rw in rows)
            if best is None or cnt > best[0]:
                best = (cnt, W, H, rows)
        cnt, W, H, rows = best
        if cnt == 0:
            raise ImpositionError(tr('page {number} does not fit on the sheet', number=n + 1))
        if chosen is None:
            chosen = (W, H)
        elif (W, H) != chosen and not a.trim:
            ctx.warn(tr("pages of different sizes chose different sheet orientations"))
        spec = SheetSpec(W, H, margins, parse_align(a.align), a.align_rows, hspace, vspace)
        render(out, imp, [rows], spec, a, ctx, bg, a.mirror, True, a.trim, sheet_numbers=[n])
    return out


# =========================================================================== join two pages


def _join_args(p):
    g = p.add_mutually_exclusive_group()
    g.add_argument("--first", default="1", metavar="PAGE",
                   help=tr("join this page with the next one (default: 1)"))
    g.add_argument("--all", action="store_true", help=tr("join every pair of pages (1+2, 3+4, ...)"))
    p.add_argument("--valign", choices=["top", "middle", "bottom"], default="bottom",
                   help=tr("vertical alignment when heights differ (default: bottom)"))


@command("join", "join two pages side by side into one", _join_args,
         description=N_("Join Two Pages: make a spread from two pages, with no change to margins."))
def join(pdf: Pdf, a, ctx: Context):
    from .pagesel import page_number
    n = len(pdf.pages)
    if a.all:
        pairs = [(i, i + 1) for i in range(0, n - 1, 2)]
    else:
        f = page_number(a.first, n) - 1
        if not 0 <= f < n - 1:
            raise ImpositionError(tr("--first must leave a following page to join"))
        pairs = [(f, f + 1)]
    joined = {p[0]: p for p in pairs}
    skip = {p[1] for p in pairs}
    out = Pdf.new()
    pu.copy_docinfo(pdf, out)
    imp = pu.Importer(out)
    av = {"top": 1.0, "middle": 0.5, "bottom": 0.0}[a.valign]
    for i in range(n):
        if i in skip:
            continue
        if i not in joined:
            out.pages.append(pdf.pages[i])
            continue
        p1, p2 = pdf.pages[i].obj, pdf.pages[i + 1].obj
        g1, g2 = pu.geometry(p1, False), pu.geometry(p2, False)
        (w1, h1), (w2, h2) = g1.size(), g2.size()
        W, H = w1 + w2, max(h1, h2)
        if W > 14400:
            raise ImpositionError(tr("joined page would exceed the 200 inch PDF limit"))
        c = pu.new_sheet(out, W, H)
        pu.place_page(c, imp, p1, g1, 0, (H - h1) * av, 1.0)
        pu.place_page(c, imp, p2, g2, w1, (H - h2) * av, 1.0)
        c.finish()
    return out
