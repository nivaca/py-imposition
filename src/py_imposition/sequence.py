"""Automation: sequences of commands, replay ("imposition by example") and hot folders."""

from __future__ import annotations

import shlex
import sys
import time
import tomllib
from pathlib import Path

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, ImpositionError, command
from .interface import N_, ntr, tr

SEQUENCE_HELP = """\
Sequence file (TOML):

    name = "numbered booklet"
    units = "mm"                   # optional preferences: units, registration, bleed, pdfx
    steps = [
      "text --position bottom-center --offset-y 10",
      "booklet --paper legal --orientation wide",
    ]

Each step is a command line without the input and output files.
"""


def load_sequence(path: Path) -> tuple[list[list[str]], dict]:
    try:
        data = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ImpositionError(tr('cannot read sequence {path}: {error}', path=path, error=e)) from None
    steps = data.get("steps")
    if not steps or not isinstance(steps, list):
        raise ImpositionError(tr("sequence {path} has no 'steps' list", path=path))
    out = []
    for s in steps:
        tokens = shlex.split(s) if isinstance(s, str) else [str(t) for t in s]
        if not tokens:
            continue
        out.append(tokens)
    prefs = {k: data[k] for k in ("units", "registration", "bleed", "pdfx") if k in data}
    prefs["name"] = data.get("name") or Path(path).stem
    return out, prefs


def prefs_context(prefs: dict, ctx: Context, input_path: Path | None = None) -> Context:
    return Context(
        units=prefs.get("units", ctx.units),
        registration=prefs.get("registration", ctx.registration),
        use_bleed=(prefs["bleed"] != "ignore") if "bleed" in prefs else ctx.use_bleed,
        pdfx=bool(prefs.get("pdfx", ctx.pdfx)),
        input_path=input_path or ctx.input_path,
        quiet=ctx.quiet,
        warnings=ctx.warnings,
    )


def write_sequence(steps: list[list[str]], name: str) -> str:
    lines = [f'name = "{name}"', "steps = ["]
    for s in steps:
        lines.append("  " + _toml_str(shlex.join(s)) + ",")
    lines.append("]")
    return "\n".join(lines) + "\n"


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def process_file(path: Path, steps, prefs, ctx: Context, output: Path) -> list[Path]:
    from .runner import run_steps, save_result

    pdf = Pdf.open(path)
    sctx = prefs_context(prefs, ctx, path)
    result = run_steps(pdf, steps, sctx)
    return save_result(result, output)


def _run_args(p):
    p.add_argument("--sequence", required=True, type=Path, help=tr("sequence file (TOML); see the description"))
    p.add_argument("inputs", nargs="+", type=Path, help=tr("PDF files to process"))
    p.add_argument("--out-dir", type=Path, help=tr("directory for outputs (default: next to each input)"))
    p.add_argument("--suffix", default=None, help=tr("output name suffix (default: the sequence name)"))


@command("run", "run a saved sequence of commands on one or more PDFs", _run_args, needs_input=False,
         description="Automation sequences: run several commands in order, on a batch of files.\n\n"
                     + SEQUENCE_HELP)
def run(pdf, a, ctx: Context):
    steps, prefs = load_sequence(a.sequence)
    suffix = a.suffix or prefs["name"].replace(" ", "-")
    if a.output and len(a.inputs) > 1:
        raise ImpositionError(tr("-o can only be used with a single input; use --out-dir"))
    for inp in a.inputs:
        if not inp.is_file():
            raise ImpositionError(tr('{inp} not found', inp=inp))
        out = a.output or (a.out_dir or inp.parent) / f"{inp.stem}-{suffix}.pdf"
        if a.out_dir:
            a.out_dir.mkdir(parents=True, exist_ok=True)
        for p in process_file(inp, steps, prefs, ctx, out):
            print(tr("Wrote {path}", path=p))
    return None


def _replay_args(p):
    p.add_argument("--from", dest="example", required=True, type=Path,
                   help=tr("a PDF made by this tool; its recorded commands are replayed"))
    p.add_argument("input", type=Path, help=tr("PDF to process"))
    p.add_argument("--export", type=Path, help=tr("write the recorded commands to this sequence file instead"))


@command("replay", "repeat the commands recorded in another output (imposition by example)", _replay_args,
         needs_input=False,
         description=N_("Imposition by example: every output records the commands that made it. Replay them on a "
                     "new document, or export them as a sequence file."))
def replay(pdf, a, ctx: Context):
    ex = Pdf.open(a.example)
    steps = pu.get_history(ex)
    if not steps:
        raise ImpositionError(tr('{example} has no recorded commands', example=a.example))
    if a.export:
        a.export.write_text(write_sequence(steps, a.example.stem))
        print(ntr('Wrote {path} ({count} step)', 'Wrote {path} ({count} steps)', len(steps), path=a.export))
        return None
    if not a.input.is_file():
        raise ImpositionError(tr('{input} not found', input=a.input))
    out = a.output or a.input.with_name(f"{a.input.stem}-replay.pdf")
    for p in process_file(a.input, steps, {}, ctx, out):
        print(tr("Wrote {path}", path=p))
    return None


def _watch_args(p):
    p.add_argument("folder", type=Path, help=tr("hot folder to watch for PDFs"))
    p.add_argument("--sequence", required=True, type=Path, help=tr("sequence file to run on each PDF"))
    p.add_argument("--out", type=Path, help=tr("output folder (default: FOLDER/out)"))
    p.add_argument("--done", type=Path, help=tr("processed inputs are moved here (default: FOLDER/done)"))
    p.add_argument("--errors", type=Path, help=tr("inputs that failed are moved here (default: FOLDER/errors)"))
    p.add_argument("--interval", type=float, default=2.0, help=tr("seconds between scans (default: 2)"))
    p.add_argument("--once", action="store_true", help=tr("process what is there now, then exit"))


@command("watch", "hot folder: process PDFs as they arrive", _watch_args, needs_input=False,
         description=N_("Hot folders: watch a folder and run a sequence on every PDF dropped into it. "
                     "Results go to an output folder; inputs move to done/ or errors/. Ctrl+C to stop."))
def watch(pdf, a, ctx: Context):
    steps, prefs = load_sequence(a.sequence)
    folder = a.folder
    if not folder.is_dir():
        raise ImpositionError(tr('{folder} is not a folder', folder=folder))
    out = a.out or folder / "out"
    done = a.done or folder / "done"
    errors = a.errors or folder / "errors"
    for d in (out, done, errors):
        d.mkdir(parents=True, exist_ok=True)
    sizes: dict[Path, int] = {}
    print(tr('Watching {folder} (sequence: {prefs}); Ctrl+C to stop', folder=folder, prefs=prefs['name']), file=sys.stderr)
    try:
        while True:
            for f in sorted(folder.iterdir()):
                if not f.is_file() or f.suffix.lower() != ".pdf":
                    continue
                size = f.stat().st_size
                if not a.once and sizes.get(f) != size:  # wait until the file stops growing
                    sizes[f] = size
                    continue
                sizes.pop(f, None)
                try:
                    paths = process_file(f, steps, prefs, ctx, out / f.name)
                    f.rename(done / f.name)
                    for p in paths:
                        print(f"{time.strftime('%H:%M:%S')} {f.name} -> {p}", file=sys.stderr)
                except Exception as e:  # keep the folder running
                    f.rename(errors / f.name)
                    (errors / (f.name + ".log")).write_text(f"{type(e).__name__}: {e}\n")
                    print(tr('{strftime} {name} FAILED: {error}', strftime=time.strftime('%H:%M:%S'), name=f.name, error=e), file=sys.stderr)
            if a.once:
                break
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    return None
