"""Page tools: Trim And Shift, Creep, Adjust Page Sizes, Tile Pages, rotate/duplicate/delete/move."""

from __future__ import annotations

import math
import re

import pikepdf
from pikepdf import Dictionary, Name, Page, Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, add_page_args, command
from .pagesel import page_number, parse_pages, select

EDGES = ("left", "bottom", "right", "top")


# --------------------------------------------------------------------------- helpers


def normalized(pdf: Pdf, i: int, imp: pu.Importer | None = None) -> Dictionary:
    """Make page i unrotated with its MediaBox at the origin, replacing it in place."""
    page = pdf.pages[i].obj
    new = pu.normalize_page(pdf, page, imp)
    if new is not page:
        pdf.pages[i] = Page(new)
        return pdf.pages[i].obj
    return page


def wrap_content(pdf: Pdf, page: Dictionary, prefix: bytes, suffix: bytes = b"Q\n"):
    """Surround the page's content with prefix/suffix operators (prefix should start with 'q')."""
    c = pu.Canvas(pdf, page)
    existing = page.get("/Contents")
    items = []
    if existing is not None:
        items = list(existing) if isinstance(existing, pikepdf.Array) else [existing]
    page.Contents = pikepdf.Array([pdf.make_stream(prefix)] + items + [pdf.make_stream(b"\n" + suffix)])


def box_margins(page: Dictionary, ref: pu.Rect) -> dict[str, tuple[float, float, float, float]]:
    """Distances of trim/bleed/art boxes from ``ref`` (left, bottom, right, top)."""
    out = {}
    for key in ("/TrimBox", "/BleedBox", "/ArtBox"):
        if key in page:
            b = pu.norm_rect(page[key])
            out[key] = (ref[0] - b[0], ref[1] - b[1], b[2] - ref[2], b[3] - ref[3])
    return out


def restore_margins(page: Dictionary, ref: pu.Rect, margins: dict):
    for key, (l, b, r, t) in margins.items():
        page[key] = pu.rect_array(pu.expand(ref, l, b, r, t))


def drop_bleed(page: Dictionary, ctx: Context, new_crop: pu.Rect | None = None):
    for key in ("/TrimBox", "/BleedBox", "/ArtBox"):
        if key in page:
            del page[key]
    if ctx.pdfx and new_crop is not None:
        page.TrimBox = pu.rect_array(new_crop)


def parse_edge_amounts(values: list[str] | None, ctx: Context) -> dict[str, float]:
    out = {e: 0.0 for e in EDGES}
    for v in values or []:
        if "=" not in v:
            raise ImpositionError(f"expected EDGE=LENGTH, got {v!r}")
        edge, amount = v.split("=", 1)
        edge = edge.strip().lower()
        amt = ctx.L(amount)
        targets = EDGES if edge == "all" else (edge,)
        for e in targets:
            if e not in out:
                raise ImpositionError(f"unknown edge {edge!r} (left, right, top, bottom, all)")
            out[e] += amt
    return out


DIRS = {"left": (-1, 0), "right": (1, 0), "up": (0, 1), "down": (0, -1)}


def parse_shift(value: str, ctx: Context) -> tuple[float, float]:
    if "=" not in value:
        raise ImpositionError(f"expected DIRECTION=LENGTH, got {value!r}")
    d, amount = value.split("=", 1)
    d = d.strip().lower()
    if d not in DIRS:
        raise ImpositionError(f"unknown direction {d!r} (left, right, up, down)")
    a = ctx.L(amount)
    return DIRS[d][0] * a, DIRS[d][1] * a


# --------------------------------------------------------------------------- trim and shift


def _trim_args(p):
    add_page_args(p)
    p.add_argument("--trim", action="append", metavar="EDGE=LEN",
                   help="remove space from an edge (left/right/top/bottom/all); repeatable")
    p.add_argument("--add", action="append", metavar="EDGE=LEN",
                   help="add space around an edge (can make pages larger than the original); repeatable")
    p.add_argument("--same-size", metavar="SIZE",
                   help="make every page this size (paper name or WxH), centred, cropping or padding")
    p.add_argument("--shift", metavar="DIR=LEN", help="shift contents by a fixed amount: left/right/up/down")
    p.add_argument("--shift-variable", metavar="DIR=FIRST:LAST",
                   help="shift by an amount varying from FIRST (first page) to LAST (last page), e.g. right=0:3mm")
    p.add_argument("--mode", choices=["improved", "original"], default="improved",
                   help="improved: never uncover cropped content, move contents; original: move the page origin "
                        "and allow uncovering (default: improved)")
    p.add_argument("--keep-bleed", action="store_true", help="keep bleed/trim margins the same after trimming")


@command("trim-shift", "trim, extend, resize or shift page contents", _trim_args,
         description="Trim And Shift: remove or add space at page edges, make pages the same size, "
                     "and shift contents (e.g. for binding offsets).")
def trim_shift(pdf: Pdf, a, ctx: Context):
    sel = select(a.pages, len(pdf.pages), a.parity)
    trims = parse_edge_amounts(a.trim, ctx)
    adds = parse_edge_amounts(a.add, ctx)
    same = ctx.paper(a.same_size) if a.same_size else None
    var = None
    if a.shift_variable:
        d, _, rng = a.shift_variable.partition("=")
        f, _, l = rng.partition(":")
        var = (d, ctx.L(f), ctx.L(l or f))
        if d.strip().lower() not in DIRS:
            raise ImpositionError(f"unknown direction {d!r}")
    fixed = parse_shift(a.shift, ctx) if a.shift else (0.0, 0.0)
    imp = pu.Importer(pdf)
    for k, i in enumerate(sel):
        page = normalized(pdf, i, imp)
        cb = pu.crop_box(page)
        margins = box_margins(page, cb) if a.keep_bleed else {}
        new = (cb[0] + trims["left"] - adds["left"], cb[1] + trims["bottom"] - adds["bottom"],
               cb[2] - trims["right"] + adds["right"], cb[3] - trims["top"] + adds["top"])
        if same:
            cx, cy = (new[0] + new[2]) / 2, (new[1] + new[3]) / 2
            new = (cx - same[0] / 2, cy - same[1] / 2, cx + same[0] / 2, cy + same[1] / 2)
        if new[2] - new[0] <= 1 or new[3] - new[1] <= 1:
            raise ImpositionError(f"page {i + 1} would have no area left")
        dx, dy = fixed
        if var:
            d, f, l = var
            amt = f + (l - f) * (k / (len(sel) - 1) if len(sel) > 1 else 0)
            dx += DIRS[d.strip().lower()][0] * amt
            dy += DIRS[d.strip().lower()][1] * amt
        if a.mode == "improved":
            prefix = b"q\n"
            if dx or dy:
                prefix += pu.cm_op(pu.translate(dx, dy))
            prefix += pu.re_op(cb) + b" W n\n"
            wrap_content(pdf, page, prefix)
            page.MediaBox = pu.rect_array(new)
            page.CropBox = pu.rect_array(new)
        else:
            mb = pu.media_box(page)
            new_s = (new[0] - dx, new[1] - dy, new[2] - dx, new[3] - dy)
            page.MediaBox = pu.rect_array((min(mb[0], new_s[0]), min(mb[1], new_s[1]),
                                           max(mb[2], new_s[2]), max(mb[3], new_s[3])))
            page.CropBox = pu.rect_array(new_s)
            new = new_s
        if margins:
            restore_margins(page, new, margins)
        else:
            drop_bleed(page, ctx, new)
    return pdf


# --------------------------------------------------------------------------- creep


def _creep_args(p):
    p.add_argument("--scope", choices=["document", "signatures"], default="document",
                   help="document: one folded booklet; signatures: separately folded signatures")
    p.add_argument("--signature", type=int, default=16, metavar="N",
                   help="pages per signature with --scope signatures (default: 16)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--thickness", metavar="LEN", help="paper thickness (e.g. 0.1mm)")
    g.add_argument("--total", metavar="LEN", help="total shift for the most-shifted pages")
    p.add_argument("--shift-most", choices=["inside", "outside"], default="inside",
                   help="inside: centre pages move most (toward the spine); outside: outer pages move most "
                        "(toward the fore-edge), e.g. for a centre spread (default: inside)")
    p.add_argument("--method", choices=["shift", "scale"], default="shift",
                   help="shift contents, or scale them horizontally (default: shift)")
    p.add_argument("--direction", choices=["left", "right"], default="left", help="binding edge (default: left)")


@command("creep", "compensate for creep in folded booklets", _creep_args,
         description="Creep pages for binding: shift (or squeeze) page contents so they line up "
                     "after folding and trimming. Run before 'booklet'.")
def creep(pdf: Pdf, a, ctx: Context):
    n = len(pdf.pages)
    sig = (-(-n // 4) * 4) if a.scope == "document" else a.signature
    if sig % 4:
        raise ImpositionError("signature size must be a multiple of 4")
    sheets = sig // 4
    if a.thickness:
        per = ctx.L(a.thickness)
    else:
        per = ctx.L(a.total) / (sheets - 1) if sheets > 1 else 0.0
    imp = pu.Importer(pdf)
    for i in range(n):
        j = i % sig  # position in signature
        k = min(j, sig - 1 - j) // 2  # sheet, 0 = outermost
        d = (k if a.shift_most == "inside" else sheets - 1 - k) * per
        if d <= 0:
            continue
        recto = (j % 2 == 0)  # odd page numbers are rectos in left binding
        spine_left = recto if a.direction == "left" else not recto
        toward_spine = -1 if spine_left else 1
        sign = toward_spine if a.shift_most == "inside" else -toward_spine
        page = normalized(pdf, i, imp)
        cb = pu.crop_box(page)
        if a.method == "shift":
            m = pu.translate(sign * d, 0)
        else:
            w = pu.rect_w(cb)
            f = max(w - d, 1) / w
            # anchor: the edge content moves away from
            anchor = cb[0] if sign < 0 else cb[2]
            m = pu.chain(pu.translate(-anchor, 0), pu.scale(f, 1), pu.translate(anchor, 0))
        wrap_content(pdf, page, b"q\n" + pu.re_op(cb) + b" W n\n" + pu.cm_op(m))
    return pdf


# --------------------------------------------------------------------------- adjust page sizes


def _resize_args(p):
    add_page_args(p)
    t = p.add_mutually_exclusive_group(required=True)
    t.add_argument("--size", metavar="SIZE", help="target size: paper name or WxH")
    t.add_argument("--percent", type=float, help="scale by a percentage, e.g. 200")
    t.add_argument("--same-as", metavar="PAGE", help="make pages the size of this page")
    p.add_argument("--orientation", choices=["as-is", "tall", "wide"], default="as-is",
                   help="orientation of --size (default: as-is)")
    p.add_argument("--method", choices=["anamorphic", "proportional", "none"], default="proportional",
                   help="anamorphic: stretch to fit; proportional: same scale both ways, then pad; "
                        "none: no scaling, pad or crop (default: proportional)")
    p.add_argument("--rotate-to-fit", choices=["no", "cw", "ccw"], default="no",
                   help="rotate pages 90° when that matches the target shape better")
    p.add_argument("--only", choices=["both", "enlarge", "shrink"], default="both",
                   help="only enlarge or only shrink pages (default: both)")
    p.add_argument("--similar", metavar="LEN",
                   help="only adjust pages whose size is within this distance of the target")
    p.add_argument("--verify", action="store_true", help="don't change anything; fail if pages differ")
    p.add_argument("--keep-bleed", action="store_true",
                   help="anamorphic: size the trim area and keep bleed margins the same")
    p.add_argument("--no-uncover", action="store_true",
                   help="never reveal content previously cropped when adding space")


@command("resize", "adjust page sizes (scale, pad or crop to a size)", _resize_args,
         description="Adjust Page Sizes: scale pages to a size or percentage, rotate to fit, verify sizes.")
def resize(pdf: Pdf, a, ctx: Context):
    n = len(pdf.pages)
    sel = select(a.pages, n, a.parity)
    target = None
    if a.size:
        from .units import orient
        target = orient(ctx.paper(a.size), a.orientation)
    elif a.same_as:
        target = pu.visual_size(pdf.pages[page_number(a.same_as, n) - 1].obj, use_bleed=False)
    tol = ctx.L(a.similar) if a.similar else None
    if a.verify:
        if target is None:
            raise ImpositionError("--verify needs --size or --same-as")
        bad = []
        for i in sel:
            w, h = pu.visual_size(pdf.pages[i].obj, use_bleed=False)
            if abs(w - target[0]) > 0.5 or abs(h - target[1]) > 0.5:
                bad.append(f"page {i + 1}: {w:.1f}x{h:.1f}pt")
        if bad:
            raise ImpositionError("pages not the required size: " + "; ".join(bad))
        return pdf
    imp = pu.Importer(pdf)
    for i in sel:
        page = pdf.pages[i].obj
        if target is not None:
            vw, vh = pu.visual_size(page, use_bleed=False)
            if tol is not None and (abs(vw - target[0]) > tol or abs(vh - target[1]) > tol):
                continue
            if a.rotate_to_fit != "no" and abs(vw - vh) > 1 and (vw > vh) != (target[0] > target[1]):
                page.Rotate = (pu.page_rotation(page) + (90 if a.rotate_to_fit == "cw" else 270)) % 360
        page = normalized(pdf, i, imp)
        use_trim = a.keep_bleed and a.method == "anamorphic" and pu.has_bleed(page)
        cb = pu.trim_box(page) if use_trim else pu.crop_box(page)
        margins = box_margins(page, cb) if use_trim else {}
        w, h = pu.rect_w(cb), pu.rect_h(cb)
        if a.percent is not None:
            sx = sy = a.percent / 100
            NW, NH = w * sx, h * sy
        else:
            W, H = target
            if a.method == "anamorphic":
                sx, sy = W / w, H / h
            elif a.method == "proportional":
                sx = sy = min(W / w, H / h)
            else:
                sx = sy = 1.0
            NW, NH = W, H
            if a.only == "enlarge":
                sx, sy = max(sx, 1.0), max(sy, 1.0)
                NW, NH = max(W, w * sx), max(H, h * sy)
                if sx == 1.0 and sy == 1.0 and a.method != "none":
                    NW, NH = max(W, w), max(H, h)
            elif a.only == "shrink":
                sx, sy = min(sx, 1.0), min(sy, 1.0)
                NW, NH = min(W, max(w * sx, W if sx < 1 else w)), min(H, max(h * sy, H if sy < 1 else h))
                if sx == 1.0 and sy == 1.0:
                    NW, NH = min(W, w) if a.method == "none" else w, min(H, h) if a.method == "none" else h
        ox = (NW - w * sx) / 2
        oy = (NH - h * sy) / 2
        m = pu.chain(pu.translate(-cb[0], -cb[1]), pu.scale(sx, sy), pu.translate(ox, oy))
        prefix = b"q\n" + pu.cm_op(m)
        if a.no_uncover or a.method != "anamorphic":
            prefix += pu.re_op(pu.crop_box(page) if not use_trim else cb) + b" W n\n"
        wrap_content(pdf, page, prefix)
        new = (0, 0, NW, NH)
        if margins:
            l, b, r, t = (max(v, 0) for v in (margins.get("/BleedBox") or (0, 0, 0, 0)))
            full = (0, 0, NW + l + r, NH + b + t)
            # shift so the trim area starts at the bleed margin
            wrap_content(pdf, page, b"q\n" + pu.cm_op(pu.translate(l, b)))
            trim = (l, b, l + NW, b + NH)
            page.MediaBox = pu.rect_array(full)
            page.CropBox = pu.rect_array(full)
            page.TrimBox = pu.rect_array(trim)
            page.BleedBox = pu.rect_array(full)
            if "/ArtBox" in page:
                del page["/ArtBox"]
        else:
            if pu.has_bleed(page):
                ctx.warn(f"page {i + 1}: bleed removed by resizing")
            page.MediaBox = pu.rect_array(new)
            page.CropBox = pu.rect_array(new)
            drop_bleed(page, ctx, new)
    return pdf


# --------------------------------------------------------------------------- rotate / duplicate / delete / move


def _rotate_args(p):
    add_page_args(p)
    p.add_argument("--angle", type=float, required=True,
                   help="clockwise angle in degrees; 90/180/270 set the page rotation, other values rotate "
                        "the contents freely")
    p.add_argument("--only", choices=["all", "tall", "wide"], default="all",
                   help="rotate only tall or only wide pages")
    p.add_argument("--keep-size", action="store_true",
                   help="free rotation: keep the original page size and bleed instead of enlarging")
    p.add_argument("--crop-first", action="store_true",
                   help="free rotation: crop to the visible page first so only blank background appears")


@command("rotate", "rotate pages by any angle", _rotate_args)
def rotate_pages(pdf: Pdf, a, ctx: Context):
    sel = select(a.pages, len(pdf.pages), a.parity)
    ang = a.angle % 360
    imp = pu.Importer(pdf)
    for i in sel:
        page = pdf.pages[i].obj
        w, h = pu.visual_size(page, use_bleed=False)
        if a.only == "tall" and not h > w or a.only == "wide" and not w > h:
            continue
        if abs(ang - round(ang / 90) * 90) < 1e-9:
            page.Rotate = (pu.page_rotation(page) + int(round(ang))) % 360
            continue
        page = normalized(pdf, i, imp)
        cb = pu.crop_box(page)
        cx, cy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
        m = pu.chain(pu.translate(-cx, -cy), pu.rotate(-ang), pu.translate(cx, cy))
        prefix = b"q\n" + pu.cm_op(m)
        if a.crop_first:
            prefix += pu.re_op(cb) + b" W n\n"
        if a.keep_size:
            wrap_content(pdf, page, prefix)
            continue
        new = pu.transform_rect(m, cb)
        wrap_content(pdf, page, prefix)
        page.MediaBox = pu.rect_array(new)
        page.CropBox = pu.rect_array(new)
        drop_bleed(page, ctx, new)
    return pdf


def _dup_args(p):
    p.add_argument("--pages", default="all", metavar="RANGE", help="pages to duplicate (default: all)")
    p.add_argument("--copies", type=int, required=True, help="number of extra copies")
    p.add_argument("--no-collate", action="store_true", help="1 1 1 2 2 2 instead of 1 2 1 2 1 2")


@command("duplicate", "duplicate pages", _dup_args)
def duplicate(pdf: Pdf, a, ctx: Context):
    n = len(pdf.pages)
    sel = parse_pages(a.pages, n)
    if a.copies < 0:
        raise ImpositionError("--copies must be zero or more")
    if a.no_collate:
        block = [i for i in sel for _ in range(a.copies + 1)]
    else:
        block = sel * (a.copies + 1)
    first = sel[0] if sel else n
    order = [i for i in range(n) if i not in sel and i < first] + block + \
            [i for i in range(n) if i not in sel and i > first]
    from .common import reorder
    return reorder(pdf, order)


def _del_args(p):
    p.add_argument("--pages", required=True, metavar="RANGE", help="pages to delete")
    p.add_argument("--parity", choices=["all", "odd", "even"], default="all")


@command("delete", "delete pages", _del_args)
def delete(pdf: Pdf, a, ctx: Context):
    sel = set(select(a.pages, len(pdf.pages), a.parity))
    if len(sel) >= len(pdf.pages):
        raise ImpositionError("cannot delete every page")
    from .common import reorder
    return reorder(pdf, [i for i in range(len(pdf.pages)) if i not in sel])


def _move_args(p):
    p.add_argument("--pages", required=True, metavar="RANGE", help="pages to move")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--before", metavar="PAGE", help="move before this page (original numbering)")
    g.add_argument("--after", metavar="PAGE", help="move after this page (original numbering)")


@command("move", "move pages within the document", _move_args)
def move(pdf: Pdf, a, ctx: Context):
    n = len(pdf.pages)
    sel = parse_pages(a.pages, n)
    target = page_number(a.before or a.after, n) - 1
    if target in sel:
        raise ImpositionError("the target page is one of the pages being moved")
    rest = [i for i in range(n) if i not in sel]
    pos = rest.index(target) + (1 if a.after else 0)
    from .common import reorder
    return reorder(pdf, rest[:pos] + sel + rest[pos:])


# --------------------------------------------------------------------------- tile


def _tile_args(p):
    g = p.add_mutually_exclusive_group()
    g.add_argument("--grid", metavar="COLSxROWS", help="split each page into a grid, e.g. 2x1")
    g.add_argument("--sizes", metavar="WIDTHS/HEIGHTS",
                   help="exact tile sizes: a width list and a height list separated by '/', "
                        "e.g. '4in 4.5in / 4in 3in' (lists repeat)")
    g.add_argument("--undo-booklet", choices=["saddle", "perfect"],
                   help="cut a 2-up booklet back into single pages in reading order")
    p.add_argument("--signature", type=int, default=4, help="--undo-booklet perfect: pages per signature")
    p.add_argument("--direction", choices=["left", "right"], default="left", help="--undo-booklet binding edge")
    p.add_argument("--overlap", default="0", metavar="LEN", help="overlap between tiles")
    p.add_argument("--overlap-bleed", action="store_true", help="make the overlap into bleed (trim/bleed boxes)")
    p.add_argument("--only-wide", action="store_true", help="split only wide pages (e.g. reader's spreads)")


def _spans(total: float, sizes: list[float]) -> list[tuple[float, float]]:
    seq, acc, k = [], 0.0, 0
    while acc < total - 1e-6:
        s = sizes[k % len(sizes)]
        if s <= 0:
            raise ImpositionError("tile sizes must be positive")
        seq.append(s)
        acc += s
        k += 1
    over = (acc - total) / (len(seq) - 1) if len(seq) > 1 else 0.0
    out, x = [], 0.0
    for s in seq:
        out.append((x, x + s))
        x += s - over
    return out


@command("tile", "split pages into tiles (or undo a 2-up booklet)", _tile_args,
         description="Tile Pages: split each page into smaller pages, optionally overlapping.")
def tile(pdf: Pdf, a, ctx: Context):
    ov = ctx.L(a.overlap)
    if a.undo_booklet:
        a.grid, ov = "2x1", 0.0
    if not (a.grid or a.sizes):
        raise ImpositionError("give --grid, --sizes or --undo-booklet")
    imp = pu.Importer(pdf)
    out_pages: list[Dictionary] = []
    for i in range(len(pdf.pages)):
        page = normalized(pdf, i, imp)
        cb = pu.crop_box(page)
        w, h = pu.rect_w(cb), pu.rect_h(cb)
        if a.only_wide and not w > h:
            out_pages.append(page)
            continue
        if a.grid:
            m = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(\d+)\s*", a.grid)
            if not m:
                raise ImpositionError("--grid must look like 2x1")
            cols, rows = int(m.group(1)), int(m.group(2))
            if a.overlap_bleed and ov:
                xs = [(w * c / cols, w * (c + 1) / cols) for c in range(cols)]
                ys = [(h * r / rows, h * (r + 1) / rows) for r in range(rows)]
            else:
                tw, th = (w + (cols - 1) * ov) / cols, (h + (rows - 1) * ov) / rows
                xs = [(c * (tw - ov), c * (tw - ov) + tw) for c in range(cols)]
                ys = [(r * (th - ov), r * (th - ov) + th) for r in range(rows)]
        else:
            wl, _, hl = a.sizes.partition("/")
            xs = _spans(w, ctx.LL(wl))
            ys = _spans(h, ctx.LL(hl or wl))
        for ri, (y0, y1) in enumerate(reversed(ys)):  # top row first
            for ci, (x0, x1) in enumerate(xs):
                trim = (cb[0] + x0, cb[1] + y0, cb[0] + x1, cb[1] + y1)
                new = Dictionary({k: v for k, v in page.items() if k not in ("/Parent",)})
                new.Type = Name.Page
                if a.overlap_bleed and ov and a.grid:
                    rr = len(ys) - 1 - ri
                    bl = ov if ci > 0 else 0
                    br = ov if ci < len(xs) - 1 else 0
                    bb = ov if rr > 0 else 0
                    bt = ov if rr < len(ys) - 1 else 0
                    full = pu.intersect(pu.expand(trim, bl, bb, br, bt), cb)
                    new.CropBox = pu.rect_array(full)
                    new.BleedBox = pu.rect_array(full)
                    new.TrimBox = pu.rect_array(trim)
                else:
                    new.CropBox = pu.rect_array(trim)
                    for key in ("/TrimBox", "/BleedBox", "/ArtBox"):
                        if key in new:
                            del new[key]
                out_pages.append(pdf.make_indirect(new))
    out = Pdf.new()
    pu.copy_docinfo(pdf, out)
    for pg in out_pages:
        out.pages.append(Page(pg))
    if a.undo_booklet:
        from .impose import booklet_order
        total = len(out.pages)
        sides = booklet_order(total, a.undo_booklet, a.signature, "full", a.direction)
        mapping = {}
        for s_idx, side in enumerate(sides):
            for k, p in enumerate(side):
                if p is not None and 2 * s_idx + k < total:
                    mapping[p] = 2 * s_idx + k
        from .common import reorder
        return reorder(out, [mapping[p] for p in sorted(mapping)])
    return out
