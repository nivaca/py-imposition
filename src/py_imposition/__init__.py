"""py-imposition: a PDF imposition toolkit."""

from __future__ import annotations

import sys
from pathlib import Path

from pikepdf import Pdf

from . import (  # noqa: F401  (importing registers the commands)
    bleed, datamerge, impose, info, insert, manual, pagetools, sequence, shuffle, simple, split, stamp,
)
from .common import COMMANDS, Context, ImpositionError
from .runner import build_parser, make_context, record, save_result, strip_io
from . import interface
from .interface import ntr, tr

__version__ = "0.8.2"

__all__ = ["main", "COMMANDS", "Context", "ImpositionError", "__version__"]


def interface_option(argv: list[str]) -> str | None:
    """The value of --interface in ARGV (needed before the parser is built)."""
    for i, tok in enumerate(argv):
        if tok == "--interface" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--interface="):
            return tok.split("=", 1)[1]
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    interface.use_configured(interface_option(argv))
    interface.translate_argparse()
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
                raise ImpositionError(tr('{inp} not found', inp=inp))
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
        print(tr('error: {error}', error=e), file=sys.stderr)
        return 1
    for p in paths:
        try:
            n = len(Pdf.open(p).pages)
            print(ntr('Wrote {path} ({count} page)', 'Wrote {path} ({count} pages)', n, path=p))
        except Exception:
            print(tr("Wrote {path}", path=p))
    return 0
