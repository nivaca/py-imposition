"""Stick On / Peel Off: text and numbers, PDF pages, masking tape; Create Sample Document."""

from __future__ import annotations

import datetime as _dt
import io
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, add_page_args, command
from .pagesel import parse_pages, select

STANDARD_FONTS = [
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
]

POSITIONS = ["top-left", "top-center", "top-right", "left", "center", "right",
             "bottom-left", "bottom-center", "bottom-right"]


# --------------------------------------------------------------------------- fonts & colours


_registered: dict[str, str] = {}


def resolve_font(name: str) -> str:
    """Return a reportlab font name, registering TrueType fonts as needed."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for std in STANDARD_FONTS:
        if name.lower() == std.lower():
            return std
    if name in _registered:
        return _registered[name]
    path = Path(name).expanduser()
    if not path.is_file():
        found = None
        if shutil.which("fc-match"):
            try:
                found = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True,
                                       text=True, timeout=10).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                found = None
        if not found or not Path(found).is_file():
            raise ImpositionError(f"font {name!r} not found; use a standard font "
                                  f"({', '.join(STANDARD_FONTS[:4])}...) or a .ttf path")
        path = Path(found)
    if path.suffix.lower() not in (".ttf", ".ttc"):
        raise ImpositionError(f"font file {path} is not TrueType (.ttf); only TrueType fonts can be embedded")
    rl_name = "F_" + re.sub(r"\W", "_", path.stem)
    try:
        pdfmetrics.registerFont(TTFont(rl_name, str(path)))
    except Exception as e:
        raise ImpositionError(f"cannot use font {path}: {e}") from None
    _registered[name] = rl_name
    return rl_name


def parse_color(spec: str, ctx: Context):
    from reportlab.lib import colors

    s = spec.strip().lower()
    if s in ("registration", "reg"):
        if ctx.registration == "cmyk":
            return colors.CMYKColor(1, 1, 1, 1)
        if ctx.registration == "all":
            return colors.CMYKColorSep(1, 1, 1, 1, spotName="All")
        return colors.black
    if s.startswith("rgb:"):
        r, g, b = (float(v) / 255 for v in s[4:].split(","))
        return colors.Color(r, g, b)
    if s.startswith("cmyk:"):
        c, m, y, k = (float(v) / 100 for v in s[5:].split(","))
        return colors.CMYKColor(c, m, y, k)
    if s.startswith("gray:") or s.startswith("grey:"):
        v = float(s[5:])
        v = v / 100 if v > 1 else v
        return colors.Color(1 - v, 1 - v, 1 - v)
    if s.startswith("#"):
        return colors.HexColor(s)
    named = getattr(colors, s, None)
    if named is not None and isinstance(named, colors.Color):
        return named
    raise ImpositionError(f"invalid colour {spec!r} (black, red, #ff0000, rgb:255,0,0, cmyk:0,100,100,0, "
                          "gray:50, registration)")


# --------------------------------------------------------------------------- fields


def expand_fields(text: str, ctx: Context, pdf: Pdf, page_no: int, number: str | None,
                  now: _dt.datetime | None = None, extra: dict | None = None) -> str:
    now = now or _dt.datetime.now()
    path = ctx.input_path
    title = ""
    try:
        title = str(pdf.docinfo.get("/Title", ""))
    except Exception:
        pass
    values = {
        "#": number if number is not None else "",
        "page": str(page_no),
        "doc:numpages": str(len(pdf.pages)),
        "date": now.strftime("%d/%m/%y"),
        "date:dmy": now.strftime("%d/%m/%y"),
        "date:mdy": now.strftime("%m/%d/%y"),
        "date:iso": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "datetime": now.strftime("%d/%m/%y %H:%M:%S"),
        "file:name": path.name if path else "",
        "file:path": str(path.resolve()) if path else "",
        "file:folder": path.resolve().parent.name if path else "",
        "doc:title": title,
        "computer": socket.gethostname(),
    }
    if extra:
        values.update({k.lower(): v for k, v in extra.items()})

    def rep(m):
        key = m.group(1).strip().lower()
        return values[key] if key in values else m.group(0)

    return re.sub(r"\[([^\[\]]+)\]", rep, text)


# --------------------------------------------------------------------------- text placement


@dataclass
class TextSpec:
    text: str
    font: str
    size: float
    color: object
    position: str
    dx: float
    dy: float
    rotation: int = 0  # counterclockwise


def anchor_point(box: pu.Rect, position: str, dx: float, dy: float) -> tuple[float, float, str]:
    """Anchor point and horizontal alignment ('left'/'center'/'right') for a position."""
    x0, y0, x1, y1 = box
    v, _, h = position.partition("-") if "-" in position else ("middle", "", position)
    if position == "center":
        v, h = "middle", "center"
    if h == "left":
        x, align = x0 + dx, "left"
    elif h == "right":
        x, align = x1 - dx, "right"
    else:
        x, align = (x0 + x1) / 2 + dx, "center"
    if v == "top":
        y = y1 - dy
    elif v == "bottom":
        y = y0 + dy
    else:
        y = (y0 + y1) / 2 + dy
        if h in ("left", "right"):
            align = "center"  # text running down the side is centred on the anchor
    return x, y, align


def draw_text(c, spec: TextSpec, box: pu.Rect):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    x, y, align = anchor_point(box, spec.position, spec.dx, spec.dy)
    lines = spec.text.split("\n")
    c.saveState()
    c.translate(x, y)
    if spec.rotation:
        c.rotate(spec.rotation)
    c.setFont(spec.font, spec.size)
    c.setFillColor(spec.color)
    lead = spec.size * 1.2
    for k, line in enumerate(lines):
        w = stringWidth(line, spec.font, spec.size)
        lx = 0 if align == "left" else (-w if align == "right" else -w / 2)
        c.drawString(lx, -k * lead, line)
    c.restoreState()


class Overlay:
    """Collects reportlab drawings per target page and applies them as tagged overlays."""

    def __init__(self, pdf: Pdf):
        from reportlab.pdfgen import canvas as rlcanvas

        self.pdf = pdf
        self.buf = io.BytesIO()
        self.c = rlcanvas.Canvas(self.buf, pageCompression=1)
        self.c.setCreator("py-imposition")
        self.targets: list[tuple[int, pu.Rect]] = []

    def page(self, index: int, box: pu.Rect | None = None):
        """Start drawing for page ``index``; coordinates are page visual coordinates with
        the visible box's lower-left at (0, 0). Returns the canvas and the box size."""
        page = self.pdf.pages[index].obj
        geom = pu.geometry(page, use_bleed=False)
        w, h = geom.size()
        self.c.setPageSize((w, h))
        self.targets.append((index, (0, 0, w, h)))
        return self.c, (0, 0, w, h)

    def end_page(self):
        self.c.showPage()

    def apply(self, tag: str, under: bool = False):
        if not self.targets:
            return
        self.c.save()
        self.buf.seek(0)
        ov = Pdf.open(self.buf)
        imp = pu.Importer(self.pdf)
        for k, (index, box) in enumerate(self.targets):
            page = self.pdf.pages[index].obj
            geom = pu.geometry(page, use_bleed=False)
            # overlay visual coordinates -> page user space
            inv = invert(geom.visual_matrix())
            form = imp.form(ov.pages[k].obj, box)
            canvas = pu.Canvas(self.pdf, page)
            canvas.form(form, inv, tag=tag)
            canvas.finish(prepend=under)
        pu.keep_alive(ov)


def invert(m: pu.Matrix) -> pu.Matrix:
    a, b, c, d, e, f = m
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(e * ia + f * ic), -(e * ib + f * id_))


# --------------------------------------------------------------------------- stick on text and numbers


def _text_args(p):
    add_page_args(p)
    p.add_argument("--text", default=None,
                   help="text to add; [#] is the number, and fields like [Doc:NumPages], [Page], [Date], "
                        "[Date:mdy], [Time], [DateTime], [File:Name], [File:Path], [File:Folder], [Doc:Title], "
                        "[Computer] are replaced. Use \\n for a new line. Default: '[#]'")
    p.add_argument("--start", default="1",
                   help="first number; leading zeros are kept (e.g. 00098 for Bates numbering) (default: 1)")
    p.add_argument("--repeat-each", type=int, default=1, metavar="N", help="repeat each number N times")
    p.add_argument("--increase-by", type=int, default=1, metavar="N", help="step between numbers (may be negative)")
    p.add_argument("--every", type=int, default=1, metavar="N",
                   help="add text only every N-th page (numbers don't advance on skipped pages)")
    p.add_argument("--position", choices=POSITIONS, default="bottom-center", help="(default: bottom-center)")
    p.add_argument("--offset-x", default="0", metavar="LEN", help="horizontal offset from the position")
    p.add_argument("--offset-y", default="1cm", metavar="LEN",
                   help="vertical offset (to the text baseline) from the position (default: 1cm)")
    p.add_argument("--mirror-odd-even", action="store_true",
                   help="swap left and right positions on even pages (outside corners of a book)")
    p.add_argument("--font", default="Helvetica", help="standard PDF font name, TrueType file, or installed "
                                                        "font name (embedded) (default: Helvetica)")
    p.add_argument("--size", type=float, default=10, help="point size (default: 10)")
    p.add_argument("--color", default="black",
                   help="black, red, #rrggbb, rgb:R,G,B, cmyk:C,M,Y,K (percent), gray:P, or registration")
    p.add_argument("--rotation", type=int, choices=[0, 90, 180, 270], default=0,
                   help="text rotation, counterclockwise")


def format_number(start: str, value: int) -> str:
    width = len(start.lstrip("-")) if start.lstrip("-").startswith("0") and len(start.lstrip("-")) > 1 else 0
    return str(value).zfill(width) if value >= 0 else "-" + str(-value).zfill(width)


@command("text", "stick on text and page numbers", _text_args,
         description="Stick On Text and Numbers: page numbers, Bates numbers, labels and fields. "
                     "Remove later with 'peel --what text'.")
def stick_text(pdf: Pdf, a, ctx: Context):
    n = len(pdf.pages)
    rng = parse_pages(a.pages, n)
    template = (a.text if a.text is not None else "[#]").replace("\\n", "\n")
    try:
        start = int(a.start)
    except ValueError:
        raise ImpositionError("--start must be a whole number") from None
    if a.repeat_each < 1 or a.every < 1:
        raise ImpositionError("--repeat-each and --every must be at least 1")
    font = resolve_font(a.font)
    color = parse_color(a.color, ctx)
    ov = Overlay(pdf)
    k = 0  # number counter
    processed = 0
    now = _dt.datetime.now()
    for i in rng:
        page_no = i + 1
        if a.parity == "odd" and page_no % 2 == 0 or a.parity == "even" and page_no % 2 == 1:
            k += 1
            continue
        stamp = processed % a.every == 0
        processed += 1
        if not stamp:
            continue
        value = start + (k // a.repeat_each) * a.increase_by
        k += 1
        text = expand_fields(template, ctx, pdf, page_no, format_number(a.start, value), now)
        pos = a.position
        if a.mirror_odd_even and page_no % 2 == 0:
            pos = pos.replace("left", "@").replace("right", "left").replace("@", "right")
        c, box = ov.page(i)
        draw_text(c, TextSpec(text, font, a.size, color, pos, ctx.L(a.offset_x), ctx.L(a.offset_y),
                              a.rotation), box)
        ov.end_page()
    ov.apply(pu.TAG_TEXT)
    return pdf


# --------------------------------------------------------------------------- stick on PDF pages


def _stickpdf_args(p):
    p.add_argument("--file", required=True, help="PDF whose pages are added")
    p.add_argument("--source-pages", default="all", metavar="RANGE",
                   help="pages of --file to use; they cycle over the target pages (default: all)")
    add_page_args(p, "target pages")
    p.add_argument("--position", choices=POSITIONS, default="center", help="(default: center)")
    p.add_argument("--offset-x", default="0", metavar="LEN",
                   help="horizontal offset, measured in the natural direction from the position")
    p.add_argument("--offset-y", default="0", metavar="LEN", help="vertical offset")
    sc = p.add_mutually_exclusive_group()
    sc.add_argument("--scale", type=float, default=100, help="percentage (default: 100)")
    sc.add_argument("--fit", metavar="WxH", help="scale to fit this box")
    p.add_argument("--stretch", action="store_true", help="with --fit: don't preserve the aspect ratio")
    p.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0, help="clockwise rotation")
    p.add_argument("--under", action="store_true", help="place behind the page content")


@command("stick-pdf", "stick pages of another PDF onto pages", _stickpdf_args,
         description="Stick On PDF Pages: add a logo, stamp or advert from another PDF.")
def stick_pdf(pdf: Pdf, a, ctx: Context):
    src = pu.open_source(a.file)
    sidx = parse_pages(a.source_pages, len(src.pages), keep_order=True)
    targets = select(a.pages, len(pdf.pages), a.parity)
    imp = pu.Importer(pdf)
    dx, dy = ctx.L(a.offset_x), ctx.L(a.offset_y)
    fit = ctx.paper(a.fit) if a.fit else None
    for k, i in enumerate(targets):
        spage = src.pages[sidx[k % len(sidx)]].obj
        geom = pu.geometry(spage, use_bleed=False)
        w, h = geom.size(a.rotate)
        if fit:
            sx, sy = fit[0] / w, fit[1] / h
            if not a.stretch:
                sx = sy = min(sx, sy)
        else:
            sx = sy = a.scale / 100
        pw, ph = w * sx, h * sy
        page = pdf.pages[i].obj
        tgeom = pu.geometry(page, use_bleed=False)
        tw, th = tgeom.size()
        pos = a.position
        vpart, _, hpart = pos.partition("-") if "-" in pos else ("middle", "", pos)
        if pos == "center":
            vpart, hpart = "middle", "center"
        x = {"left": dx, "right": tw - pw - dx}.get(hpart, (tw - pw) / 2 + dx)
        y = {"bottom": dy, "top": th - ph - dy}.get(vpart, (th - ph) / 2 + dy)
        m = pu.chain(geom.visual_matrix(a.rotate), pu.scale(sx, sy), pu.translate(x, y),
                     invert(tgeom.visual_matrix()))
        canvas = pu.Canvas(pdf, page)
        canvas.form(imp.form(spage, geom.clip), m, tag=pu.TAG_PDF)
        canvas.finish(prepend=a.under)
    return pdf


# --------------------------------------------------------------------------- masking tape


def _mask_args(p):
    add_page_args(p)
    p.add_argument("--rect", action="append", required=True, metavar="X,Y,W,H",
                   help="area to cover, measured from --origin of the visible page; repeatable")
    p.add_argument("--origin", choices=["bottom-left", "top-left"], default="bottom-left",
                   help="corner the --rect coordinates are measured from (default: bottom-left)")
    p.add_argument("--color", default="white", help="tape colour (default: white)")


@command("mask", "stick masking tape over areas of pages", _mask_args,
         description="Stick On Masking Tape: cover areas (e.g. old page numbers) with opaque rectangles. "
                     "Remove later with 'peel --what tape'.")
def mask(pdf: Pdf, a, ctx: Context):
    rects = []
    for r in a.rect:
        parts = [p for p in re.split(r"[,\s]+", r.strip()) if p]
        if len(parts) != 4:
            raise ImpositionError(f"--rect needs X,Y,W,H, got {r!r}")
        rects.append([ctx.L(p) for p in parts])
    color = parse_color(a.color, ctx)
    ov = Overlay(pdf)
    for i in select(a.pages, len(pdf.pages), a.parity):
        c, box = ov.page(i)
        c.setFillColor(color)
        c.setStrokeColor(color)
        for x, y, w, h in rects:
            yy = box[3] - y - h if a.origin == "top-left" else y
            c.rect(x, yy, w, h, stroke=0, fill=1)
        ov.end_page()
    ov.apply(pu.TAG_TAPE)
    return pdf


# --------------------------------------------------------------------------- peel off


def strip_tagged(instructions, tags: set[str]):
    out = []
    depth = 0  # nesting depth inside a removed section
    for ins in instructions:
        op = str(getattr(ins, "operator", ""))
        if depth:
            if op in ("BMC", "BDC"):
                depth += 1
            elif op == "EMC":
                depth -= 1
            continue
        if op in ("BMC", "BDC") and ins.operands and str(ins.operands[0]).lstrip("/") in tags:
            depth = 1
            continue
        out.append(ins)
    return out, len(out) != len(instructions)


def peel_object(pdf: Pdf, obj, tags: set[str], seen: set) -> int:
    """Remove tagged sections from a page or form and the forms it uses. Returns sections removed."""
    removed = 0
    res = obj.get("/Resources") if hasattr(obj, "get") else None
    if res is not None and "/XObject" in res:
        for _, x in res.XObject.items():
            if x.is_indirect and x.objgen in seen:
                continue
            if x.is_indirect:
                seen.add(x.objgen)
            if x.get("/Subtype") == pikepdf.Name.Form:
                removed += peel_object(pdf, x, tags, seen)
    if isinstance(obj, pikepdf.Stream):
        ins = pikepdf.parse_content_stream(obj)
        new, changed = strip_tagged(ins, tags)
        if changed:
            obj.write(pikepdf.unparse_content_stream(new))
            removed += 1
    else:
        page = pikepdf.Page(obj)
        if "/Contents" in obj:
            ins = pikepdf.parse_content_stream(page)
            new, changed = strip_tagged(ins, tags)
            if changed:
                obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new))
                removed += 1
    return removed


def _peel_args(p):
    p.add_argument("--what", choices=["text", "tape", "marks", "pdf", "bleed", "all"], default="text",
                   help="text (Stick On Text), tape (masking tape), marks (crop marks/frames), pdf "
                        "(stuck-on PDF pages), bleed (generated bleed), or all (default: text)")
    add_page_args(p)


@command("peel", "peel off stuck-on text, tape, marks or PDF pages", _peel_args,
         description="Peel Off Text and Numbers / Masking Tape / Registration Marks added by this tool, "
                     "even after further imposition.")
def peel(pdf: Pdf, a, ctx: Context):
    tags = {"text": {pu.TAG_TEXT}, "tape": {pu.TAG_TAPE}, "marks": {pu.TAG_MARKS},
            "pdf": {pu.TAG_PDF}, "bleed": {pu.TAG_BLEED}}.get(a.what)
    if tags is None:
        tags = {pu.TAG_TEXT, pu.TAG_TAPE, pu.TAG_MARKS, pu.TAG_PDF, pu.TAG_BLEED}
    total = 0
    seen: set = set()
    for i in select(a.pages, len(pdf.pages), a.parity):
        total += peel_object(pdf, pdf.pages[i].obj, tags, seen)
    if total == 0:
        ctx.warn(f"nothing to peel off ({a.what})")
    return pdf


# --------------------------------------------------------------------------- sample document


def _sample_args(p):
    p.add_argument("--paper", default="a4", help="page size: paper name or WxH (default: a4)")
    p.add_argument("--orientation", choices=["tall", "wide", "as-is"], default="tall")
    p.add_argument("--count", type=int, default=8, help="number of pages (default: 8)")


@command("sample", "create a sample document for testing impositions", _sample_args, needs_input=False,
         description="Create Sample Document: grey pages with a thick border, a large page number and "
                     "rules 20 mm and 1 inch from each edge.")
def sample(pdf, a, ctx: Context):
    from reportlab.lib.units import inch, mm
    from reportlab.pdfgen import canvas as rlcanvas

    if a.count < 1:
        raise ImpositionError("--count must be at least 1")
    w, h = ctx.paper(a.paper, a.orientation)
    buf = io.BytesIO()
    c = rlcanvas.Canvas(buf, pagesize=(w, h))
    for n in range(1, a.count + 1):
        c.setFillGray(0.88)
        c.rect(0, 0, w, h, stroke=0, fill=1)
        c.setStrokeGray(0.25)
        c.setLineWidth(8)
        c.rect(4, 4, w - 8, h - 8, stroke=1, fill=0)
        c.setLineWidth(0.5)
        for d, label in ((20 * mm, "20 mm"), (inch, "1 in")):
            c.setDash(4, 3) if label == "1 in" else c.setDash()
            c.rect(d, d, w - 2 * d, h - 2 * d, stroke=1, fill=0)
            c.setFont("Helvetica", 6)
            c.setFillGray(0.2)
            c.drawString(d + 2, d + 2, label)
        c.setDash()
        size = min(w, h) * 0.4
        c.setFont("Helvetica-Bold", size)
        c.setFillGray(0.15)
        c.drawCentredString(w / 2, h / 2 - size * 0.35, str(n))
        c.setFont("Helvetica", 9)
        c.drawCentredString(w / 2, h - 20 * mm - 14, "TOP")
        c.drawCentredString(w / 2, 20 * mm + 8, f"page {n} of {a.count}  -  {w:.0f} x {h:.0f} pt")
        c.showPage()
    c.save()
    buf.seek(0)
    return Pdf.open(buf)
