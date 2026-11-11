"""Building the argument parser and running commands (singly or in sequences)."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from pikepdf import Pdf

from . import pdfutil as pu
from .common import COMMANDS, Context, ImpositionError, Result
from . import interface
from .interface import tr

GLOBAL_DEFAULTS = {"units": "cm", "registration": "black", "bleed": "use", "pdfx": False, "quiet": False}
PREFERENCE_NAMES = set(GLOBAL_DEFAULTS) | {"interface"}


def global_parent() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group(tr("preferences"))
    g.add_argument("--units", choices=["cm", "mm", "in", "pt"], default=argparse.SUPPRESS,
                   help=tr("unit for lengths given without a suffix (default: cm)"))
    g.add_argument("--registration", choices=["black", "cmyk", "all"], default=argparse.SUPPRESS,
                   help=tr("colour for marks and registration-coloured text: black, CMYK, or all separations"))
    g.add_argument("--bleed", choices=["use", "ignore"], default=argparse.SUPPRESS,
                   help=tr("use page bleed boxes when imposing, or ignore them (default: use)"))
    g.add_argument("--pdfx", action="store_true", default=argparse.SUPPRESS,
                   help=tr("keep a TrimBox when removing bleeds (PDF/X)"))
    g.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS, help=tr("no warnings"))
    g.add_argument("--interface", choices=sorted(interface.names()), default=argparse.SUPPRESS,
                   help=tr("the language of the interface, for this run only (to keep a choice, use the "
                           "'interface' command)"))
    return p


def build_parser(prog: str = "py-imposition") -> argparse.ArgumentParser:
    parent = global_parent()
    parser = argparse.ArgumentParser(
        prog=prog,
        description=tr("PDF imposition toolkit: booklets, n-up, step and repeat, shuffling, trimming, "
                    "bleeds, page numbers, stamps, automation sequences and hot folders."),
        epilog=tr("Run '%(prog)s COMMAND -h' for help on a command. "
                  "'%(prog)s file.pdf' on its own makes a booklet with the default settings."),
        parents=[parent],
    )
    from . import __version__
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar=tr("COMMAND"))
    for name in sorted(COMMANDS):
        cmd = COMMANDS[name]
        sp = sub.add_parser(name, help=tr(cmd.help), description=translate_paragraphs(cmd.description or cmd.help),
                            parents=[parent], formatter_class=argparse.RawDescriptionHelpFormatter)
        if cmd.needs_input is True:
            sp.add_argument("input", type=Path, help=tr("source PDF"))
        elif cmd.needs_input == "optional":
            sp.add_argument("input", type=Path, nargs="?", help=tr("source PDF"))
        sp.add_argument("-o", "--output", type=Path, help=tr("output PDF (default: <input>-<command>.pdf)"))
        cmd.add_args(sp)
    return parser


def translate_paragraphs(text: str) -> str:
    """TEXT translated paragraph by paragraph (descriptions hold reference blocks
    whose layout must be kept)."""
    return "\n\n".join(tr(par) for par in text.split("\n\n"))


def make_context(ns: argparse.Namespace, input_path: Path | None = None, base: Context | None = None) -> Context:
    base = base or Context()
    vals = {k: getattr(ns, k, None) for k in GLOBAL_DEFAULTS}
    return Context(
        units=vals["units"] or base.units,
        registration=vals["registration"] or base.registration,
        use_bleed=(vals["bleed"] != "ignore") if vals["bleed"] else base.use_bleed,
        pdfx=bool(vals["pdfx"]) or base.pdfx,
        input_path=input_path or base.input_path,
        quiet=bool(vals["quiet"]) or base.quiet,
        warnings=base.warnings,
    )


def run_command(pdf: Pdf | None, tokens: list[str], ctx: Context) -> Result:
    """Run one command given as CLI tokens (without input/output) on ``pdf``."""
    parser = build_parser()
    if not tokens or tokens[0] not in COMMANDS:
        raise ImpositionError(tr('unknown command in step: {items!r}', items=' '.join(tokens)))
    cmd = COMMANDS[tokens[0]]
    argv = list(tokens)
    if cmd.needs_input is True:
        argv.insert(1, "-")  # placeholder input
    try:
        ns = parser.parse_args(argv)
    except SystemExit:
        raise ImpositionError(tr('invalid options in step: {items}', items=shlex.join(tokens))) from None
    sctx = make_context(ns, base=ctx)
    result = cmd.run(pdf, ns, sctx)
    record(pdf, result, tokens)
    return result


def record(src: Pdf | None, result: Result, tokens: list[str]):
    """Store the command in each output's history ("imposition by example")."""
    hist = pu.get_history(src) if src is not None else []
    outs = result.values() if isinstance(result, dict) else [result]
    for out in outs:
        pu.set_history(out, hist + [list(tokens)])


def run_steps(pdf: Pdf | None, steps: list[list[str]], ctx: Context) -> Result:
    """Run several commands; each step works on the previous step's result."""
    current: Result | None = pdf
    for i, tokens in enumerate(steps):
        if isinstance(current, dict):
            raise ImpositionError(
                tr('step {index} ({steps}) produced several documents; it must be the last step', index=i, steps=steps[i - 1][0]))
        current = run_command(current, tokens, ctx)
        if not isinstance(current, dict):
            current = pu.roundtrip(current)
        else:
            current = {k: pu.roundtrip(v) for k, v in current.items()}
    return current


def save_result(result: Result, output: Path) -> list[Path]:
    if isinstance(result, dict):
        paths = []
        for suffix, pdf in result.items():
            path = output.with_name(f"{output.stem}-{suffix}{output.suffix or '.pdf'}")
            pdf.save(path)
            paths.append(path)
        return paths
    result.save(output)
    return [output]


def strip_io(argv: list[str], ns: argparse.Namespace) -> list[str]:
    """Remove input/output tokens and global prefs before the command, giving a reusable step."""
    out = []
    skip = False
    started = False
    inp = str(ns.input) if getattr(ns, "input", None) is not None else None
    for tok in argv:
        if skip:
            skip = False
            continue
        if not started:
            if tok == ns.command:
                started = True
                out.append(tok)
            continue
        if tok in ("-o", "--output", "--interface"):  # (the language is not part of a step)
            skip = True
            continue
        if tok.startswith(("--output=", "--interface=")):
            continue
        if inp is not None and tok == inp:
            inp = None
            continue
        out.append(tok)
    return out
