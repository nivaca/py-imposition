"""PDF/A and PDF/X output, made by the author's pdf2iso (Ghostscript and
pikepdf), which must be installed: the result is written first as a plain
PDF, then converted (File > Save as in the window, --conform on the command
line).

This is not --pdfx, which only keeps a TrimBox when bleeds are removed: here
a whole PDF/X-4 (or PDF/A) file is made.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .interface import N_, tr

COMMAND = "pdf2iso"
#  Its name before version 2.0, still looked for after the new one
OLD_COMMAND = "py-pdfconform"
# (value of pdf2iso --target, name shown)
STANDARDS = [("a-1b", N_("PDF/A-1b (archiving, the oldest)")), ("a-2b", N_("PDF/A-2b (archiving)")),
             ("a-3b", N_("PDF/A-3b (archiving, with attachments)")), ("x-4", N_("PDF/X-4 (printing)"))]
TIMEOUT = 600  # seconds


class ConformError(Exception):
    """A conversion that failed."""


def own_folders() -> list[Path]:
    """The folders of this program's own Python (its virtual environment, or the
    AppImage), which pdf2iso must not see: it would run with this Python,
    which hasn't its libraries."""
    out = []
    if sys.prefix != sys.base_prefix:
        out.append(Path(sys.prefix).resolve())
    for name in ("APPDIR", "VIRTUAL_ENV"):  # (also a virtual environment this program was started from)
        if os.environ.get(name):
            out.append(Path(os.environ[name]).resolve())
    return out


def clean_env() -> dict[str, str]:
    """The environment for pdf2iso: the user's, without this program's Python."""
    own = own_folders()

    def ours(folder: str) -> bool:
        try:
            p = Path(folder).resolve()
        except OSError:
            return False
        return any(p == o or o in p.parents for o in own)

    env = {k: v for k, v in os.environ.items()
           if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
                        "SSL_CERT_FILE", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH")}
    env["PATH"] = os.pathsep.join(f for f in os.environ.get("PATH", "").split(os.pathsep) if f and not ours(f))
    return env


# (where a script of the user's may be, though a session started from the desktop menu
# often doesn't have these folders on its PATH)
USER_FOLDERS = ("~/bin", "~/.local/bin")


def configured() -> str:
    """The path of pdf2iso given in the configuration file ('' for none)."""
    from . import config

    value = config.get("pdfconform")
    return value if isinstance(value, str) else ""


def find(path: str = "") -> Path | None:
    """pdf2iso: PATH if given (a file), or else the first of
    pdf2iso or pdf2iso.py on the PATH or in ~/bin and ~/.local/bin, or of
    py-pdfconform or py-pdfconform.py (its name before version 2.0)."""
    if path:
        p = Path(path).expanduser()
        return p if p.is_file() else None
    folders = clean_env()["PATH"].split(os.pathsep) + [str(Path(f).expanduser()) for f in USER_FOLDERS]
    for name in (COMMAND, COMMAND + ".py", OLD_COMMAND, OLD_COMMAND + ".py"):
        found = shutil.which(name, path=os.pathsep.join(folders))
        if found:
            return Path(found)
    return None


def command(path: str | None = None) -> list[str] | None:
    """How to run pdf2iso (the one of the configuration file, or else the one found;
    see find): [the script], or [python3, the script] for a script that can't
    be run by itself; None if there is none."""
    script = find(configured() if path is None else path)
    if script is None:
        return None
    if os.access(script, os.X_OK):
        return [str(script)]
    python = shutil.which("python3", path=clean_env()["PATH"]) or "/usr/bin/python3"
    return [python, str(script)]


def available(path: str | None = None) -> bool:
    return command(path) is not None


def label(standard: str) -> str:
    return "PDF/" + standard[0].upper() + standard[1:] if standard else "PDF"


def convert(source: Path, target: Path, standard: str, password: str = "") -> str:
    """SOURCE converted to STANDARD ('a-2b', 'x-4'...) as TARGET (safely: TARGET
    may be SOURCE). Returns what pdf2iso says about it (its check)."""
    exe = command()
    if exe is None:
        raise ConformError(tr("{command} is not installed (or not on the PATH)", command=COMMAND))
    if standard not in [s for s, _ in STANDARDS]:
        raise ConformError(standard)
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
    os.close(fd)
    args = [*exe, "-t", standard, "-o", tmp] + (["-p", password] if password else []) + [str(source)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT, env=clean_env())
        if r.returncode != 0 or not Path(tmp).stat().st_size:
            raise ConformError(tr("{command} could not make {standard}: {error}", command=COMMAND,
                                  standard=label(standard),
                                  error=(r.stderr or r.stdout).strip() or r.returncode))
        os.replace(tmp, target)
    except subprocess.TimeoutExpired:
        raise ConformError(tr("{command} took too long", command=COMMAND)) from None
    except OSError as e:
        raise ConformError(str(e)) from None
    finally:
        Path(tmp).unlink(missing_ok=True)
    # its last line: "OK  (veraPDF: PASS) in.pdf -> out.pdf [PDF/A-2b]"
    said = r.stdout.strip().splitlines()
    check = said[-1] if said else ""
    return check[check.index("(") + 1:check.index(")")] if "(" in check and ")" in check else ""
