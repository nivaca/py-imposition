"""py-imposition: a PDF imposition toolkit."""

from __future__ import annotations

import sys
from pathlib import Path

from pikepdf import Pdf

from . import (  # noqa: F401  (importing registers the commands)
    bleed, datamerge, impose, info, insert, manual, pagetools, sequence, shuffle, split, stamp,
)
from .common import COMMANDS, Context, ImpositionError
from .runner import build_parser, make_context, record, save_result, strip_io

__all__ = ["main", "COMMANDS", "Context", "ImpositionError"]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # "py-imposition file.pdf [options]" -> booklet with the default settings
    first = next((t for t in argv if not t.startswith("-")), None)
    if first and first not in COMMANDS and first.lower().endswith(".pdf"):
        argv.insert(argv.index(first), "booklet")
    parser = build_parser()
    ns = parser.parse_args(argv)
    if not ns.command:
        parser.print_help()
        return 1
    cmd = COMMANDS[ns.command]
    inp: Path | None = getattr(ns, "input", None)
    ctx = make_context(ns, input_path=inp)
    try:
        pdf = None
        if inp is not None:
            if not inp.is_file():
                raise ImpositionError(f"{inp} not found")
            pdf = Pdf.open(inp)
        result = cmd.run(pdf, ns, ctx)
        if result is None:  # command handled its own output (info, run, watch...)
            return 0
        record(pdf, result, strip_io(argv, ns))
        out = ns.output
        if out is None:
            stem = inp.with_suffix("") if inp is not None else Path(ns.command)
            out = Path(f"{stem}-{ns.command}.pdf")
        paths = save_result(result, out)
    except ImpositionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for p in paths:
        try:
            n = len(Pdf.open(p).pages)
            print(f"Wrote {p} ({n} page{'s' if n != 1 else ''})")
        except Exception:
            print(f"Wrote {p}")
    return 0
