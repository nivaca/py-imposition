"""Page shuffling: Shuffle Pages For Imposing, Shuffle Even/Odd Pages, Reverse Pages."""

from __future__ import annotations

import re

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, command
from .interface import N_, tr

ROT_SUFFIX = {"*": 180, ">": 90, "<": 270, "": 0}

_TOKEN = re.compile(r"^(?:(X)|(\d+)(?:\.\.(\d+))?)([*<>]?)$", re.I)


def parse_rule(rule: str) -> list[tuple[int | None, int]]:
    """Parse a shuffle rule into (page number or None for blank, clockwise rotation).

    Syntax: page numbers separated by spaces/commas; ``a..b`` ranges;
    suffix ``*`` = upside down, ``>`` = 90° clockwise, ``<`` = 90° anticlockwise;
    ``X`` = blank page.
    """
    out: list[tuple[int | None, int]] = []
    for tok in re.split(r"[\s,]+", rule.strip()):
        if not tok:
            continue
        m = _TOKEN.match(tok)
        if not m:
            raise ImpositionError(tr('invalid token {tok!r} in shuffle rule', tok=tok))
        blank, a, b, suf = m.groups()
        rot = ROT_SUFFIX[suf]
        if blank:
            out.append((None, rot))
            continue
        a = int(a)
        if b is None:
            out.append((a, rot))
        else:
            b = int(b)
            step = 1 if b >= a else -1
            out.extend((p, rot) for p in range(a, b + step, step))
    if not out:
        raise ImpositionError(tr("empty shuffle rule"))
    return out


def shuffle_order(count: int, rule: list[tuple[int | None, int]], group: int, repeat: str = "normal",
                  consecutive: int = 1, restart_after: int = 0) -> list[tuple[int | None, int]]:
    """Expand a rule over a document. Returns (0-based page index or None, rotation)."""
    if group < 1:
        raise ImpositionError(tr("group size must be at least 1"))
    for p, _ in rule:
        if p is not None and not 1 <= p <= group:
            raise ImpositionError(tr('page {page} in rule is outside the group size {group}', page=p, group=group))

    def ceil(a, b):
        return -(-a // b)

    total = max(ceil(count, group), 1) * group
    out: list[tuple[int | None, int]] = []

    def emit(page_no, rot):
        out.append((page_no - 1 if page_no is not None and page_no <= count else None, rot))

    if repeat == "normal":
        for k in range(total // group):
            for p, rot in rule:
                emit(None if p is None else k * group + p, rot)
    elif repeat == "saddle":
        if group % 2:
            raise ImpositionError(tr("saddle repeat needs an even group size"))
        half = group // 2
        sheets = total // group
        for s in range(sheets):
            for p, rot in rule:
                if p is None:
                    emit(None, rot)
                elif p <= half:
                    emit(s * half + p, rot)
                else:
                    emit(total - (group - p) - s * half, rot)
    elif repeat in ("cut-single", "cut-double"):
        unit = consecutive * (1 if repeat == "cut-single" else 2)
        if group % unit:
            raise ImpositionError(tr('group size {group} must be a multiple of {unit} for these cut stacks', group=group, unit=unit))
        chunk_sheets = restart_after or (total // group)
        sheets_total = total // group
        done = 0
        while done < sheets_total:
            S = min(chunk_sheets, sheets_total - done)
            off = done * group
            for s in range(S):
                for p, rot in rule:
                    if p is None:
                        emit(None, rot)
                        continue
                    a, b = divmod(p - 1, unit)
                    emit(off + a * unit * S + s * unit + b + 1, rot)
            done += S
    else:
        raise ImpositionError(tr('unknown repeat mode {repeat!r}', repeat=repeat))
    return out


def build(pdf: Pdf, order: list[tuple[int | None, int]], ctx: Context) -> Pdf:
    out = Pdf.new()
    pu.copy_docinfo(pdf, out)
    blank = pu.visual_size(pdf.pages[0].obj, use_bleed=False) if len(pdf.pages) else (612, 792)
    for idx, rot in order:
        if idx is None:
            pg = out.add_blank_page(page_size=blank)
            if "/Contents" in pg.obj:
                del pg.obj["/Contents"]
            if rot:
                pg.obj.Rotate = rot
            continue
        out.pages.append(pdf.pages[idx])
        new = out.pages[-1].obj
        if rot:
            new.Rotate = (pu.page_rotation(new) + rot) % 360
    return out


def _shuffle_args(p):
    p.add_argument("--rule", required=True,
                   help=tr("page order for one group, e.g. '4 1 2 3' or '8 1 5* 4* 2 7 3* 6*'. "
                        "Suffix * = upside down, > = 90° clockwise, < = 90° anticlockwise; X = blank; "
                        "a..b = range"))
    p.add_argument("--group", type=int, default=None,
                   help=tr("group size: pages before the rule repeats (default: highest page number in the rule)"))
    p.add_argument("--repeat", choices=["normal", "saddle", "cut-single", "cut-double"], default="normal",
                   help=tr("normal/perfect bound: repeat the rule every group; saddle: the rule describes the "
                        "first sheet of a saddle-stitched book and stretches to any length; cut-single / "
                        "cut-double: cut stacks printed on one or both sides (default: normal)"))
    p.add_argument("--consecutive", type=int, default=1, metavar="A",
                   help=tr("cut stacks: consecutive pages per group (advanced stacks A)"))
    p.add_argument("--restart-after", type=int, default=0, metavar="B",
                   help=tr("cut stacks: start the stacks again after B sheets; 0 = never (advanced stacks B)"))


@command("shuffle", "reorder (and rotate) pages by a repeating rule", _shuffle_args,
         description=N_("Shuffle Pages For Imposing. Usually followed by 'nup'."))
def shuffle(pdf: Pdf, a, ctx: Context):
    rule = parse_rule(a.rule)
    group = a.group or max((p for p, _ in rule if p is not None), default=1)
    used = [p for p, _ in rule if p is not None]
    missing = sorted(set(range(1, group + 1)) - set(used))
    dup = sorted({p for p in used if used.count(p) > 1})
    if missing and a.repeat == "normal":
        ctx.warn(tr('rule omits page(s) {items} of each group; they will be dropped', items=', '.join(map(str, missing))))
    if dup:
        ctx.warn(tr('rule repeats page(s) {items}; they will be duplicated', items=', '.join(map(str, dup))))
    order = shuffle_order(len(pdf.pages), rule, group, a.repeat, a.consecutive, a.restart_after)
    return build(pdf, order, ctx)


def _evenodd_args(p):
    p.add_argument("--mode", choices=["none", "odds-first", "split", "join"], default="odds-first",
                   help=tr("none: keep order; odds-first: all odd pages then all even; split: two documents; "
                        "join: interleave this document (odd pages) with --evens (default: odds-first)"))
    p.add_argument("--evens", metavar="PDF", help=tr("with --mode join: the document holding the even pages"))
    p.add_argument("--reverse-evens", action="store_true", help=tr("reverse the order of the even pages"))
    p.add_argument("--rotate-evens", action="store_true", help=tr("turn the even pages upside down"))


@command("evenodd", "separate, reorder or rejoin odd and even pages", _evenodd_args,
         description=N_("Shuffle Even/Odd Pages: handy for printing double-sided on a single-sided printer."))
def evenodd(pdf: Pdf, a, ctx: Context):
    n = len(pdf.pages)
    if a.mode == "join":
        if not a.evens:
            raise ImpositionError(tr("--mode join needs --evens FILE"))
        ev = pu.open_source(a.evens)
        odds = [(pdf, i) for i in range(n)]
        evens = [(ev, i) for i in range(len(ev.pages))]
        if a.reverse_evens:
            evens.reverse()
        out = Pdf.new()
        pu.copy_docinfo(pdf, out)
        for k in range(max(len(odds), len(evens))):
            for lst, is_even in ((odds, False), (evens, True)):
                if k < len(lst):
                    src, i = lst[k]
                    out.pages.append(src.pages[i])
                    if is_even and a.rotate_evens:
                        pg = out.pages[-1].obj
                        pg.Rotate = (pu.page_rotation(pg) + 180) % 360
        return out
    odds = list(range(0, n, 2))
    evens = list(range(1, n, 2))
    if a.reverse_evens:
        evens.reverse()
    rot = {i: 180 for i in evens} if a.rotate_evens else {}
    if a.mode == "none":
        # keep positions; reversing evens swaps them among the even slots
        order = []
        ev = iter(evens)
        for i in range(n):
            order.append(i if i % 2 == 0 else next(ev))
    elif a.mode == "odds-first":
        order = odds + evens
    else:  # split
        return {"odd": build(pdf, [(i, 0) for i in odds], ctx),
                "even": build(pdf, [(i, rot.get(i, 0)) for i in evens], ctx)}
    return build(pdf, [(i, rot.get(i, 0)) for i in order], ctx)


@command("reverse", "reverse the order of all pages", lambda p: None)
def reverse(pdf: Pdf, a, ctx: Context):
    return build(pdf, [(i, 0) for i in reversed(range(len(pdf.pages)))], ctx)
