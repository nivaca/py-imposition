"""Split/merge (partials): split a document, run different commands on each part, rejoin."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, command
from .pagesel import page_number
from .shuffle import ROT_SUFFIX, build

_TOK = re.compile(r"^(X|(?:LAST(?:-\d+)?|\d+)(?:\.\.(?:LAST(?:-\d+)?|\d+))?)([*<>]?)$", re.I)


def parse_piece(spec: str, n: int, ignore_missing: bool) -> list[tuple[int | None, int]]:
    out = []
    for tok in re.split(r"[\s,]+", spec.strip()):
        if not tok:
            continue
        m = _TOK.match(tok.upper())
        if not m:
            raise ImpositionError(f"invalid token {tok!r} in page list")
        body, suf = m.groups()
        rot = ROT_SUFFIX[suf]
        if body == "X":
            out.append((None, rot))
            continue
        a, _, b = body.partition("..")
        pa = page_number(a, n)
        pb = page_number(b, n) if b else pa
        step = 1 if pb >= pa else -1
        for p in range(pa, pb + step, step):
            if not 1 <= p <= n:
                if ignore_missing:
                    continue
                raise ImpositionError(f"page {p} does not exist (document has {n} pages)")
            out.append((p - 1, rot))
    return out


def _split_args(p):
    p.add_argument("--by", choices=["odd-even", "list", "equal", "duplicates"], required=True,
                   help="odd-even: two parts; list: pages listed per part; equal: parts of --size pages; "
                        "duplicates: --copies complete copies of the document")
    p.add_argument("--list", metavar="PARTS",
                   help="with --by list: parts separated by ';', e.g. '1..4 9..12; 5..8*'. Pages may use "
                        "LAST/LAST-n, ranges a..b, rotation suffixes * > < and X for a blank")
    p.add_argument("--page-count", type=int, default=0,
                   help="with --by list: require exactly this many pages (0 = any)")
    p.add_argument("--ignore-missing", action="store_true", help="skip listed pages beyond the end")
    p.add_argument("--size", type=int, help="with --by equal: pages per part")
    p.add_argument("--copies", type=int, help="with --by duplicates: number of copies")
    p.add_argument("--sequence", type=Path, help="sequence file to run on every part")
    p.add_argument("--part-sequence", action="append", metavar="N=FILE", default=[],
                   help="sequence file for part N (overrides --sequence); repeatable")
    p.add_argument("--part-steps", action="append", metavar="N=STEPS", default=[],
                   help="inline commands for part N, separated by ';', e.g. "
                        "'2=nup --cols 2 --rows 2 --scale fit'; repeatable")
    p.add_argument("--merge", action="store_true", help="join the processed parts into one document")


@command("split", "split into parts, process each part differently, and optionally rejoin", _split_args,
         description="Split/merge (partials): split a document by odd/even, page lists, equal sizes or "
                     "duplicates, run a sequence on each part, then merge or keep the parts.")
def split(pdf: Pdf, a, ctx: Context):
    from .runner import run_steps
    from .sequence import load_sequence, prefs_context

    n = len(pdf.pages)
    if a.by == "odd-even":
        parts = [[(i, 0) for i in range(0, n, 2)], [(i, 0) for i in range(1, n, 2)]]
        parts = [p for p in parts if p]
    elif a.by == "list":
        if not a.list:
            raise ImpositionError("--by list needs --list")
        if a.page_count and a.page_count != n:
            raise ImpositionError(f"expected {a.page_count} pages, document has {n}")
        parts = [parse_piece(s, n, a.ignore_missing) for s in a.list.split(";") if s.strip()]
    elif a.by == "equal":
        if not a.size or a.size < 1:
            raise ImpositionError("--by equal needs --size N")
        parts = [[(i, 0) for i in range(s, min(s + a.size, n))] for s in range(0, n, a.size)]
    else:
        if not a.copies or a.copies < 1:
            raise ImpositionError("--by duplicates needs --copies N")
        parts = [[(i, 0) for i in range(n)] for _ in range(a.copies)]
    if not parts:
        raise ImpositionError("nothing to split")

    seqs: dict[int, tuple[list, dict]] = {}
    default = load_sequence(a.sequence) if a.sequence else None
    for spec in a.part_sequence:
        k, _, f = spec.partition("=")
        seqs[int(k)] = load_sequence(Path(f))
    for spec in a.part_steps:
        k, _, body = spec.partition("=")
        steps = [shlex.split(s) for s in body.split(";") if s.strip()]
        seqs[int(k)] = (steps, {})

    results = []
    for k, part in enumerate(parts, 1):
        if not part:
            ctx.warn(f"part {k} is empty")
            continue
        doc = pu.roundtrip(build(pdf, part, ctx))
        steps, prefs = seqs.get(k) or default or ([], {})
        if steps:
            doc = run_steps(doc, steps, prefs_context(prefs, ctx))
            if isinstance(doc, dict):
                raise ImpositionError(f"the sequence for part {k} produced several documents")
        results.append((k, doc))
    if a.merge:
        out = Pdf.new()
        pu.copy_docinfo(pdf, out)
        for _, doc in results:
            pu.keep_alive(doc)
            out.pages.extend(doc.pages)
        return out
    return {f"part{k}": doc for k, doc in results}
