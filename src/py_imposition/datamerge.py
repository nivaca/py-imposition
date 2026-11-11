"""Variable data merge: add text, text blocks and pictures from a CSV data source."""

from __future__ import annotations

import csv
import io
import re
import tomllib
from pathlib import Path

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, command
from .pagesel import parse_pages
from .stamp import POSITIONS, Overlay, TextSpec, draw_text, invert, parse_color, resolve_font

FIELDS_HELP = """\
Fields file (TOML). Column values are written as {Column Name}:

    [[text]]
    template = "{Name} - {Company Name}"
    page = 1                       # page within the master / record (default: all)
    position = "top-left"          # see 'text --help' for positions
    x = "2cm"
    y = "2cm"
    font = "Helvetica"
    size = 12
    color = "black"
    rotation = 0

    [[picture]]
    file = "logos.pdf"             # one picture per page
    column = "Logo number"         # page number of the picture to use
    position = "top-right"
    x = "1cm"
    y = "1cm"
    fit = "3x2cm"                  # or scale = 100

    [[block]]                      # a text block, e.g. a mailing label
    width = "8cm"
    height = "4cm"
    position = "bottom-left"
    x = "2cm"
    y = "2cm"
    font = "Helvetica"
    size = 11
    justify = "left"               # left | center | right
    overflow = "scale"             # scale | cut | fail
    warn_below = 50                # warn if text is scaled below this percent
    rotation = 0
    lines = [
      { text = "{Title}" },
      { text = "{First name}" },
      { text = "{Last name}", same_line = true },
      { text = "{Address 1}", close_gap = true },
      { text = "{Address 2}", close_gap = true, justify = "right", size = 9 },
    ]
"""


def _merge_args(p):
    p.add_argument("--data", required=True, type=Path, help="data source: CSV/TSV with a header row")
    p.add_argument("--fields", required=True, type=Path, help="fields file (TOML); see the description")
    p.add_argument("--separator", default="auto", help="column separator: auto, ',', ';', 'tab'")
    p.add_argument("--encoding", default="utf-8-sig", help="text encoding of the data (default: utf-8-sig)")
    p.add_argument("--master", action="store_true",
                   help="the document is a master copied once per record (otherwise records are added to "
                        "successive groups of pages)")
    p.add_argument("--pages-per-record", type=int, default=1, metavar="N",
                   help="without --master: pages used by each record (default: 1)")
    p.add_argument("--strict", action="store_true", help="fail if records and pages don't match exactly")
    p.add_argument("--records", default="all", metavar="RANGE", help="records to use, e.g. 1-10")


def read_data(path: Path, sep: str, encoding: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError) as e:
        raise ImpositionError(f"cannot read data source {path}: {e}") from None
    if sep == "auto":
        try:
            dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else ",", delimiters=",;\t")
            delim = dialect.delimiter
        except csv.Error:
            delim = ","
    else:
        delim = {"tab": "\t", "\\t": "\t"}.get(sep, sep)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        raise ImpositionError("data source is empty")
    header = [h.strip() for h in rows[0]]
    records = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        records.append({h: (r[k].strip() if k < len(r) else "") for k, h in enumerate(header)})
    return header, records


def fill(template: str, record: dict[str, str], header: list[str]) -> str:
    def rep(m):
        key = m.group(1)
        if key in record:
            return record[key]
        for h in header:
            if h.lower() == key.lower():
                return record[h]
        raise ImpositionError(f"unknown column {{{key}}} (columns: {', '.join(header)})")

    return re.sub(r"\{([^{}]+)\}", rep, template)


def block_rect(box: pu.Rect, position: str, x: float, y: float, w: float, h: float) -> pu.Rect:
    W, H = box[2], box[3]
    v, _, hz = position.partition("-") if "-" in position else ("middle", "", position)
    if position == "center":
        v, hz = "middle", "center"
    bx = {"left": x, "right": W - w - x}.get(hz, (W - w) / 2 + x)
    by = {"bottom": y, "top": H - h - y}.get(v, (H - h) / 2 + y)
    return (bx, by, bx + w, by + h)


def draw_block(c, blk: dict, record, header, ctx: Context, warnings: list[str], rec_no: int):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    w, h = ctx.L(blk["width"]), ctx.L(blk["height"])
    font = resolve_font(blk.get("font", "Helvetica"))
    size = float(blk.get("size", 11))
    color = parse_color(blk.get("color", "black"), ctx)
    justify = blk.get("justify", "left")
    overflow = blk.get("overflow", "scale")
    warn_below = float(blk.get("warn_below", 50))
    lines: list[dict] = []
    for ln in blk.get("lines", []):
        text = fill(ln.get("text", ""), record, header)
        if ln.get("same_line") and lines:
            if text.strip():
                lines[-1]["text"] = (lines[-1]["text"] + " " + text).strip()
            continue
        if ln.get("close_gap") and not text.strip():
            continue
        lines.append(dict(text=text, font=resolve_font(ln["font"]) if "font" in ln else font,
                          size=float(ln.get("size", size)), justify=ln.get("justify", justify),
                          overflow=ln.get("overflow", overflow),
                          color=parse_color(ln["color"], ctx) if "color" in ln else color))
    x0, y0 = blk["_rect"][0], blk["_rect"][1]
    c.saveState()
    c.translate(x0, y0)
    if blk.get("rotation"):
        c.rotate(int(blk["rotation"]))
    p = c.beginPath()
    p.rect(0, 0, w, h)
    c.clipPath(p, stroke=0, fill=0)
    top = h
    for ln in lines:
        fs = ln["size"]
        text = ln["text"]
        tw = stringWidth(text, ln["font"], fs)
        if tw > w:
            if ln["overflow"] == "fail":
                raise ImpositionError(f"record {rec_no}: line too long for the block: {text!r}")
            if ln["overflow"] == "scale":
                new = fs * w / tw
                if new / fs * 100 < warn_below:
                    warnings.append(f"record {rec_no}: text scaled to {new / fs:.0%}: {text!r}")
                fs = new
                tw = w
            else:
                warnings.append(f"record {rec_no}: text cut off: {text!r}")
                while text and stringWidth(text, ln["font"], fs) > w:
                    text = text[:-1]
                tw = stringWidth(text, ln["font"], fs)
        top -= ln["size"] * 1.2 if ln is not lines[0] else ln["size"]
        x = {"left": 0, "center": (w - tw) / 2, "centre": (w - tw) / 2, "right": w - tw}.get(ln["justify"], 0)
        c.setFont(ln["font"], fs)
        c.setFillColor(ln["color"])
        c.drawString(x, top, text)
    c.restoreState()


@command("merge-data", "variable data merge from a CSV file", _merge_args,
         description="Variable data merge: add text, text blocks and pictures to pages using records "
                     "from a CSV file, either by copying a master document per record or by filling "
                     "successive pages.\n\n" + FIELDS_HELP)
def merge_data(pdf: Pdf, a, ctx: Context):
    header, records = read_data(a.data, a.separator, a.encoding)
    sel = parse_pages(a.records, len(records)) if records else []
    records = [records[i] for i in sel]
    try:
        fields = tomllib.loads(a.fields.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ImpositionError(f"cannot read fields file {a.fields}: {e}") from None
    texts, pics, blocks = fields.get("text", []), fields.get("picture", []), fields.get("block", [])
    if not (texts or pics or blocks):
        raise ImpositionError("fields file defines no [[text]], [[picture]] or [[block]]")
    base = Path(a.fields).parent
    n = len(pdf.pages)
    if a.master:
        per = n
        out = Pdf.new()
        pu.copy_docinfo(pdf, out)
        for _ in records:
            for i in range(n):
                out.pages.append(pdf.pages[i])
        doc = out
    else:
        per = a.pages_per_record
        if per < 1:
            raise ImpositionError("--pages-per-record must be at least 1")
        groups = -(-n // per)
        if a.strict and (n % per or groups != len(records)):
            raise ImpositionError(f"{len(records)} records but {n} pages in groups of {per}")
        if len(records) > groups:
            ctx.warn(f"{len(records) - groups} record(s) have no pages and are ignored")
            records = records[:groups]
        doc = pdf
    warnings: list[str] = []
    ov = Overlay(doc)
    pictures = []  # (page index, spec, record)
    for r_no, rec in enumerate(records):
        for k in range(per):
            idx = r_no * per + k
            if idx >= len(doc.pages):
                break
            want = lambda f: f.get("page") is None or int(f["page"]) == k + 1  # noqa: E731
            t_here = [t for t in texts if want(t)]
            b_here = [b for b in blocks if want(b)]
            pictures += [(idx, p, rec) for p in pics if want(p)]
            if not (t_here or b_here):
                continue
            c, box = ov.page(idx)
            for t in t_here:
                pos = t.get("position", "top-left")
                if pos not in POSITIONS:
                    raise ImpositionError(f"invalid position {pos!r}")
                draw_text(c, TextSpec(fill(t["template"], rec, header), resolve_font(t.get("font", "Helvetica")),
                                      float(t.get("size", 12)), parse_color(t.get("color", "black"), ctx), pos,
                                      ctx.L(t.get("x", 0)), ctx.L(t.get("y", 0)), int(t.get("rotation", 0))), box)
            for b in b_here:
                rect = block_rect(box, b.get("position", "top-left"), ctx.L(b.get("x", 0)), ctx.L(b.get("y", 0)),
                                  ctx.L(b["width"]), ctx.L(b["height"]))
                draw_block(c, dict(b, _rect=rect), rec, header, ctx, warnings, r_no + 1)
            ov.end_page()
    ov.apply(pu.TAG_TEXT)
    # pictures
    imp = pu.Importer(doc)
    files: dict[str, Pdf] = {}
    for idx, p, rec in pictures:
        fpath = Path(p["file"])
        if not fpath.is_absolute():
            fpath = base / fpath
        src = files.get(str(fpath)) or files.setdefault(str(fpath), pu.open_source(fpath))
        val = fill("{" + p["column"] + "}", rec, header).strip()
        if not val:
            continue
        try:
            pno = int(val)
        except ValueError:
            raise ImpositionError(f"picture column {p['column']!r} must hold a page number, got {val!r}") from None
        if not 1 <= pno <= len(src.pages):
            raise ImpositionError(f"picture page {pno} not in {fpath}")
        spage = src.pages[pno - 1].obj
        geom = pu.geometry(spage, use_bleed=False)
        w, h = geom.size(int(p.get("rotate", 0)))
        if "fit" in p:
            fw, fh = ctx.paper(p["fit"])
            s = min(fw / w, fh / h)
        else:
            s = float(p.get("scale", 100)) / 100
        page = doc.pages[idx].obj
        tg = pu.geometry(page, use_bleed=False)
        tw, th = tg.size()
        r = block_rect((0, 0, tw, th), p.get("position", "top-left"), ctx.L(p.get("x", 0)), ctx.L(p.get("y", 0)),
                       w * s, h * s)
        m = pu.chain(geom.visual_matrix(int(p.get("rotate", 0))), pu.scale(s), pu.translate(r[0], r[1]),
                     invert(tg.visual_matrix()))
        canvas = pu.Canvas(doc, page)
        canvas.form(imp.form(spage, geom.clip), m, tag=pu.TAG_PDF)
        canvas.finish()
    for w in warnings:
        ctx.warn(w)
    return doc
