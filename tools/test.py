#!/usr/bin/env python3
"""Corre a la vez las pruebas de py-imposition: uv run python tools/test.py [-j N] [-v] [NOMBRE ...]

Cada archivo de pruebas (tests/test_*.py) corre en un proceso de pytest propio, tantos a la vez como procesadores
tenga el computador (-j lo cambia), primero los más lentos; así, la suite entera tarda más o menos lo que su
archivo más lento, y no la suma de todos. Cada proceso tiene su carpeta personal (y en ella sus carpetas XDG), su
carpeta temporal de pytest y su carpeta de ejecución, de modo que ninguna prueba toque la configuración del
usuario ni la de otra.

Los NOMBRE eligen qué correr: un archivo (test_gui) o un patrón (test_*mpos*). Al final aparecen los archivos
que fallaron, con su salida, y los totales; -v muestra además cada archivo a medida que termina. El código de
salida es 1 si falló alguna prueba. (uv run python -m pytest las corre una tras otra, como antes.) Así las
corren también la publicación (tools/release.py) y el %check del RPM, este con el Python del sistema y el
paquete ya instalado en su raíz de construcción.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
# The slowest files, started first (the rest follow in alphabetical order): measured with -v on 2026-11-26
SLOW = ("test_gui.py", "test_zenodo.py", "test_imposition.py", "test_conform.py", "test_interface.py")


def files(names: list[str]) -> list[Path]:
    """The test files to run, the slowest first."""
    found = sorted(TESTS.rglob("test_*.py"))
    if names:
        found = [p for p in found if any(fnmatch.fnmatch(p.name, n) or fnmatch.fnmatch(p.stem, n)
                                         or n in p.relative_to(TESTS).parts[:-1] for n in names)]

    def rank(p: Path) -> int:
        name = p.relative_to(TESTS).as_posix()
        return SLOW.index(name) if name in SLOW else len(SLOW)

    return sorted(found, key=rank)


def run(path: Path, work: Path, env: dict) -> tuple[Path, int, str, float]:
    """PATH run by pytest in a process of its own: (path, exit status, output, seconds)."""
    own = work / re.sub(r"[^\w.-]", "_", str(path.relative_to(TESTS)))
    for sub in ("home", "tmp", "run"):
        (own / sub).mkdir(parents=True, exist_ok=True)
    (own / "run").chmod(0o700)
    home = own / "home"
    # Las carpetas XDG van dentro de la carpeta personal propia: si siguieran apuntando a las del usuario, una
    # prueba podría escribir en su configuración real.
    env = {**env, "HOME": str(home), "XDG_RUNTIME_DIR": str(own / "run"),
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local" / "share"),
           "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".local" / "state")}
    start = time.time()
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "-o", "faulthandler_timeout=120", f"--basetemp={own / 'tmp'}", str(path)],
                          cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          errors="replace")
    return path, done.returncode, done.stdout, time.time() - start


def counts(output: str) -> dict[str, int]:
    """{'passed': n, 'failed': n, 'skipped': n, 'error': n} of pytest's summary: the last line that says how long
    it took (not simply the last line: Qt may write something after it, as a process ends)."""
    lines = [line for line in output.splitlines() if re.search(r"\bin \d+(\.\d+)?s\b", line)]
    last = lines[-1] if lines else ""
    return {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|errors?)", last)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools/test.py",
                                     description="Run the tests of py-imposition, each file in a process of its own, "
                                                 "at once.")
    parser.add_argument("names", nargs="*", metavar="NAME", help="files or patterns to run (default: all)")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2,
                        help="how many at a time (default: the processors)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show each file as it ends")
    args = parser.parse_args(argv)
    todo = files(args.names)
    if not todo:
        print("tools/test.py: no tests match " + " ".join(args.names), file=sys.stderr)
        return 2
    work = Path(tempfile.mkdtemp(prefix="py-imposition-tests-"))
    # La ventana se dibuja siempre fuera de la pantalla: con una carpeta de ejecución propia, Qt no hallaría el
    # enchufe de Wayland del escritorio (y QT_QPA_PLATFORM=wayland lo haría abortar).
    env = {k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"}
    env["QT_QPA_PLATFORM"] = "offscreen"
    start = time.time()
    failed: list[tuple[Path, str]] = []
    totals: dict[str, int] = {}
    try:
        with ThreadPoolExecutor(max(1, args.jobs)) as pool:
            jobs = [pool.submit(run, path, work, env) for path in todo]
            for n, job in enumerate(as_completed(jobs), 1):
                path, status, output, seconds = job.result()
                found = counts(output)
                for k, v in found.items():
                    totals[k] = totals.get(k, 0) + v
                # (5: pytest no encontró pruebas en el archivo; no es un fallo)
                if status not in (0, 5):
                    failed.append((path, output))
                if args.verbose or status not in (0, 5):
                    mark = "ok" if status in (0, 5) else "FAILED"
                    print(f"[{n}/{len(todo)}] {path.relative_to(TESTS)}: {found.get('passed', 0)} passed, "
                          f"{seconds:.1f}s, {mark}", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for path, output in failed:
        print(f"\n{'=' * 70}\n{path.relative_to(TESTS)}\n{'=' * 70}\n{output.rstrip()}")
    said = ", ".join(f"{v} {k}" for k, v in sorted(totals.items()))
    print(f"\n{said} ({len(todo)} files) in {time.time() - start:.1f}s: "
          + (f"FAILED ({len(failed)} files)" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
