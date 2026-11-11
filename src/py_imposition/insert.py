"""Insert blank pages or pages from a file, with intervals and conditions."""

from __future__ import annotations

import re

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, command
from .pagesel import page_number, parse_pages
from .interface import N_, tr


def _insert_args(p):
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--blank", type=int, metavar="N", help=tr("insert N blank pages"))
    src.add_argument("--file", metavar="PDF", help=tr("insert pages from this PDF"))
    p.add_argument("--file-pages", default="all", metavar="RANGE", help=tr("pages of --file to insert"))
    p.add_argument("--copies", type=int, default=1, help=tr("copies of the inserted pages (default: 1)"))
    p.add_argument("--no-collate", action="store_true", help=tr("copies as A A B B instead of A B A B"))
    pos = p.add_mutually_exclusive_group()
    pos.add_argument("--before", metavar="PAGE", help=tr("insert before this page (e.g. 1, LAST)"))
    pos.add_argument("--after", metavar="PAGE", help=tr("insert after this page (e.g. 3, LAST-1)"))
    pos.add_argument("--at", choices=["start", "end"], default=None, help=tr("insert at the start or end (default)"))
    p.add_argument("--size", metavar="SIZE", help=tr("blank page size (paper or WxH); default: size of a "
                                                    "neighbouring page"))
    p.add_argument("--size-of", metavar="PAGE", help=tr("blank pages the same size as this page"))
    p.add_argument("--every", type=int, default=0, metavar="K",
                   help=tr("insert at intervals: insert, then skip K original pages, and repeat"))
    p.add_argument("--each-time", default="all", metavar="N|all",
                   help=tr("with --file and --every: insert the whole selection each time, or the next N pages"))
    p.add_argument("--stop-when-exhausted", action="store_true",
                   help=tr("with --each-time N: stop when the file's pages run out instead of starting again"))
    cond = p.add_mutually_exclusive_group()
    cond.add_argument("--if", dest="cond_if", metavar="COND",
                      help=tr("insert only if the page count meets COND: odd, even, lt:N, ge:N, multiple:N"))
    cond.add_argument("--unless", dest="cond_unless", metavar="COND", help=tr("insert unless COND is met"))
    cond.add_argument("--until", dest="cond_until", metavar="COND",
                      help=tr("insert pages one at a time until COND is met (up to the number requested)"))


def check(cond: str, n: int) -> bool:
    c = cond.strip().lower()
    if c == "odd":
        return n % 2 == 1
    if c == "even":
        return n % 2 == 0
    m = re.fullmatch(r"(lt|less-than|ge|at-least|multiple|multiple-of)\s*:\s*(\d+)", c)
    if not m:
        raise ImpositionError(tr('invalid condition {cond!r} (odd, even, lt:N, ge:N, multiple:N)', cond=cond))
    kind, v = m.group(1), int(m.group(2))
    if kind in ("lt", "less-than"):
        return n < v
    if kind in ("ge", "at-least"):
        return n >= v
    if v <= 0:
        raise ImpositionError(tr("multiple:N needs N > 0"))
    return n % v == 0


@command("insert", "insert blank pages or pages from another PDF", _insert_args, needs_input="optional",
         description=N_("Insert Pages: blank pages or pages from a file, at a position, at intervals, or until a "
                     "condition holds (e.g. --until multiple:4). Without an input PDF, creates a new document."))
def insert(pdf: Pdf | None, a, ctx: Context):
    if pdf is None:
        pdf = Pdf.new()
    n = len(pdf.pages)
    src = None
    if a.file:
        src = pu.open_source(a.file)
        sel = parse_pages(a.file_pages, len(src.pages), keep_order=True)
        block = [j for j in sel for _ in range(a.copies)] if a.no_collate else sel * a.copies
        items = [("file", j) for j in block]
    else:
        if a.blank is None or a.blank < 0:
            raise ImpositionError(tr("--blank must be zero or more"))
        items = [("blank", None)] * (a.blank * max(a.copies, 1))

    def blank_size(near: int | None):
        if a.size:
            return ctx.paper(a.size)
        if a.size_of:
            return pu.visual_size(pdf.pages[page_number(a.size_of, n) - 1].obj, use_bleed=False)
        if n:
            idx = min(max(near if near is not None else 0, 0), n - 1)
            return pu.visual_size(pdf.pages[idx].obj, use_bleed=False)
        return (595.28, 841.89)

    # insertion point as an index into the original pages (0 = before page 1)
    if a.before:
        pos, after_mode = page_number(a.before, n) - 1, False
    elif a.after:
        pos, after_mode = page_number(a.after, n), True
    elif a.at == "start":
        pos, after_mode = 0, False
    else:
        pos, after_mode = n, True
    if not 0 <= pos <= n:
        raise ImpositionError(tr("insertion page is out of range"))

    inserts: dict[int, list] = {}
    if a.every:
        if a.cond_if or a.cond_unless or a.cond_until:
            raise ImpositionError(tr("conditions can't be combined with --every"))
        file_cursor = 0
        p = pos
        while True:
            if a.file and a.each_time != "all":
                k = int(a.each_time)
                chunk = []
                for _ in range(k):
                    if file_cursor >= len(items):
                        if a.stop_when_exhausted:
                            break
                        file_cursor = 0
                    chunk.append(items[file_cursor])
                    file_cursor += 1
                if not chunk:
                    break
            else:
                chunk = items
            inserts.setdefault(p, []).extend(chunk)
            p += a.every
            if p > n or (p == n and not after_mode):
                break
    else:
        if a.cond_if and not check(a.cond_if, n) or a.cond_unless and check(a.cond_unless, n):
            return pdf
        if a.cond_until:
            chunk, count = [], n
            for it in items:
                if check(a.cond_until, count):
                    break
                chunk.append(it)
                count += 1
            items = chunk
        inserts[pos] = items

    out = Pdf.new()
    pu.copy_docinfo(pdf, out)
    for idx in range(n + 1):
        for kind, j in inserts.get(idx, []):
            if kind == "file":
                out.pages.append(src.pages[j])
            else:
                pg = out.add_blank_page(page_size=blank_size(idx if idx < n else n - 1))
                if "/Contents" in pg.obj:
                    del pg.obj["/Contents"]
        if idx < n:
            out.pages.append(pdf.pages[idx])
    if not len(out.pages):
        raise ImpositionError(tr("the result has no pages"))
    return out
