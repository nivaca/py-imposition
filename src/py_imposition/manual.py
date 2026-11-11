"""Manual Imposition driven by a layout file (TOML), with double-sided mirroring and repeat."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, command, get_mark_style
from .impose import Backgrounds, draw_background

LAYOUT_HELP = """\
Layout file (TOML) example:

    sheet = "a3"              # paper name or WxH; omit when using a background
    orientation = "wide"      # tall | wide | as-is
    background = "plate.pdf"  # optional background PDF (sets the sheet size)
    sides = "double-h"        # single | double-h (backs mirrored left-right) | double-v (top-bottom)
    sheets = 1                # sheets (single) or front/back pairs (double) in one cycle
    repeat = true             # repeat the cycle until all pages are placed
    crop_marks = true         # default for every placement

    [[place]]                 # one entry per page, taken from the source in order
    side = "front"            # front | back | both (front, then the next page on the back)
    sheet = 1                 # which sheet / pair of the cycle
    corner = "top-left"       # corner of the sheet and page the offsets are measured between
    x = "1cm"                 # horizontal offset (natural direction from the corner)
    y = "1cm"                 # vertical offset
    scale = 100               # percent
    rotate = 0                # clockwise: 0, 90, 180, 270
    page = 3                  # optional: a fixed source page instead of the next one
"""


def _manual_args(p):
    p.add_argument("--layout", required=True, type=Path, help="layout file (TOML); see the description")
    p.add_argument("--mark-offset", default="10pt", metavar="LEN")
    p.add_argument("--mark-length", default="20pt", metavar="LEN")
    p.add_argument("--mark-width", default="0.5pt", metavar="LEN")
    p.add_argument("--mark-white-background", action="store_true")
    p.add_argument("--smart-marks", action="store_true",
                   help="drop crop mark segments that would overlap pages")


def mirror_corner(corner: str, sides: str) -> str:
    if sides == "double-h":
        return corner.replace("left", "@").replace("right", "left").replace("@", "right")
    if sides == "double-v":
        return corner.replace("top", "@").replace("bottom", "top").replace("@", "bottom")
    return corner


def mirror_rotation(rot: int, sides: str) -> int:
    if sides == "double-h":
        return (-rot) % 360
    if sides == "double-v":
        return (180 - rot) % 360
    return rot


@command("manual", "impose pages at exact positions described in a layout file", _manual_args,
         description="Manual Imposition: place each page at a chosen corner offset, scale and rotation on "
                     "sheets, optionally double-sided with automatically mirrored backs, repeating the "
                     "layout over the whole document.\n\n" + LAYOUT_HELP)
def manual(pdf: Pdf, a, ctx: Context):
    try:
        spec = tomllib.loads(a.layout.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ImpositionError(f"cannot read layout {a.layout}: {e}") from None
    places = spec.get("place") or []
    if not places:
        raise ImpositionError("layout has no [[place]] entries")
    sides = spec.get("sides", "single")
    if sides not in ("single", "double-h", "double-v"):
        raise ImpositionError("sides must be single, double-h or double-v")
    bg = None
    if spec.get("background"):
        bgpath = Path(spec["background"])
        if not bgpath.is_absolute():
            bgpath = a.layout.parent / bgpath
        bg = Backgrounds(str(bgpath), spec.get("background_pages"), spec.get("background_mode", "repeat"),
                         spec.get("background_repeat_last", 1), ctx)
        W, H = bg.size()
    else:
        W, H = ctx.paper(str(spec.get("sheet", "a4")), spec.get("orientation", "as-is"))
    per_cycle_sheets = int(spec.get("sheets", max(int(p.get("sheet", 1)) for p in places)))
    double = sides != "single"
    sheets_per_cycle = per_cycle_sheets * (2 if double else 1)
    repeat = bool(spec.get("repeat", True))
    default_marks = bool(spec.get("crop_marks", False))
    style = get_mark_style(a, ctx)

    # expand placements into (sheet index in cycle, corner, x, y, scale, rotate, marks, fixed page)
    slots = []
    for p in places:
        side = p.get("side", "front")
        sheet = int(p.get("sheet", 1)) - 1
        if not 0 <= sheet < per_cycle_sheets:
            raise ImpositionError(f"place.sheet {sheet + 1} is outside 1..{per_cycle_sheets}")
        base = dict(corner=p.get("corner", "top-left"), x=ctx.L(p.get("x", 0)), y=ctx.L(p.get("y", 0)),
                    scale=float(p.get("scale", 100)) / 100, rotate=int(p.get("rotate", 0)) % 360,
                    marks=bool(p.get("crop_marks", default_marks)), page=p.get("page"))
        if side not in ("front", "back", "both"):
            raise ImpositionError("place.side must be front, back or both")
        if side in ("back", "both") and not double:
            raise ImpositionError("back placements need sides = double-h or double-v")
        if side in ("front", "both"):
            slots.append(dict(base, sheet=sheet * (2 if double else 1)))
        if side in ("back", "both"):
            back = dict(base, sheet=sheet * 2 + 1, corner=mirror_corner(base["corner"], sides),
                        rotate=mirror_rotation(base["rotate"], sides))
            if side == "both" and base["page"] is not None:
                back["page"] = None
            slots.append(back)

    n = len(pdf.pages)
    out = Pdf.new()
    imp = pu.Importer(out)
    next_page = 0
    cycle = 0
    sheets: dict[int, tuple[pu.Canvas, list]] = {}
    while True:
        consumed = False
        for sl in slots:
            if sl["page"] is not None:
                idx = int(sl["page"]) - 1
                if not 0 <= idx < n:
                    raise ImpositionError(f"page {sl['page']} is out of range")
            else:
                if next_page >= n:
                    continue
                idx = next_page
                next_page += 1
                consumed = True
            s_no = cycle * sheets_per_cycle + sl["sheet"]
            while len(sheets) <= s_no:
                k = len(sheets)
                canvas = pu.new_sheet(out, W, H)
                if bg is not None:
                    bgp = bg.page_for(k)
                    if bgp is not None:
                        draw_background(canvas, imp, bgp, W, H)
                sheets[k] = (canvas, [])
            canvas, rects = sheets[s_no]
            page = pdf.pages[idx].obj
            geom = pu.geometry(page, ctx.use_bleed)
            pw, ph = geom.size(sl["rotate"])
            pw, ph = pw * sl["scale"], ph * sl["scale"]
            c = sl["corner"]
            x = sl["x"] if "left" in c else W - sl["x"] - pw
            y = H - sl["y"] - ph if "top" in c else sl["y"]
            rect = pu.place_page(canvas, imp, page, geom, x, y, sl["scale"], rotate_cw=sl["rotate"])
            if sl["marks"]:
                rects.append(rect)
        cycle += 1
        if not repeat or not consumed or next_page >= n:
            break
    if next_page < n and not repeat:
        ctx.warn(f"{n - next_page} page(s) were not placed (repeat = false)")
    for k in sorted(sheets):
        canvas, rects = sheets[k]
        if rects:
            if a.smart_marks:
                pu.smart_crop_marks(canvas, rects, style, sheet=(0, 0, W, H))
            else:
                segs = []
                o, ln = style.offset, style.length
                for r in rects:
                    for cx, sx in ((r[0], -1), (r[2], 1)):
                        for cy, sy in ((r[1], -1), (r[3], 1)):
                            segs.append((cx + sx * o, cy, cx + sx * (o + ln), cy))
                            segs.append((cx, cy + sy * o, cx, cy + sy * (o + ln)))
                pu.draw_lines(canvas, segs, style)
        canvas.finish()
    return out
