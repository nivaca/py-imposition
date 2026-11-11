#!/usr/bin/env python3
"""Make all the icons afresh from src/py_imposition/icons/py-imposition.svg:

    python3 tools/icons.py [--svg FILE] [-o FOLDER] [--dry-run]

In FOLDER (src/py_imposition/icons/ by default) it writes:

* linux/hicolor/NxN/apps/py-imposition.png, for each N in HICOLOR_SIZES, and
  linux/hicolor/scalable/apps/py-imposition.svg (a copy of the SVG), for
  py-imposition-install and the window;
* macos/py-imposition.iconset/icon_NxN[@2x].png and macos/py-imposition.icns;
* windows/py-imposition.ico.

Each size is drawn by Inkscape from the SVG (never scaled down from a
bigger PNG), all of them in a single run of Inkscape. The .ico is put
together with Pillow from those same PNGs, and the .icns from the iconset
as py-imposition-install does it (as iconutil would, with all ten sizes).

Inkscape may be a Flatpak (org.inkscape.Inkscape), and then it is run with
"flatpak run", with absolute paths, and writing only inside FOLDER: a
Flatpak does not see the host's /tmp. So the PNGs are first drawn in a
hidden folder inside FOLDER, and only moved to their places once all are
there. If there is no Flatpak, the inkscape on the PATH is used.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NAME = "py-imposition"
FLATPAK_ID = "org.inkscape.Inkscape"
HICOLOR_SIZES = [16, 22, 24, 32, 48, 64, 96, 128, 192, 256, 512]
ICONSET_SIZES = [16, 32, 128, 256, 512]  # each also @2x
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]

#  Every size that is drawn
SIZES = sorted(set(HICOLOR_SIZES) | set(ICONSET_SIZES) | {2 * n for n in ICONSET_SIZES} | set(ICO_SIZES))

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "src" / "py_imposition" / "icons"
sys.path.insert(0, str(ROOT / "src"))


def find_inkscape():
    """The command to run Inkscape, and whether it is a Flatpak."""
    if shutil.which("flatpak"):
        found = subprocess.run(["flatpak", "info", FLATPAK_ID], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if found.returncode == 0:
            return ["flatpak", "run", FLATPAK_ID], True
    native = shutil.which("inkscape")
    if native:
        return [native], False
    sys.exit(f"Inkscape was not found (neither the Flatpak {FLATPAK_ID} nor inkscape on the PATH).")


def render(inkscape, svg, folder, sizes):
    """Draw svg as folder/N.png for each N in sizes, in one run."""
    actions = []
    for n in sizes:
        actions += [f"export-width:{n}", f"export-height:{n}", "export-type:png",
                    f"export-filename:{folder / f'{n}.png'}", "export-do"]
    result = subprocess.run(inkscape + [str(svg), "--actions=" + ";".join(actions)],
                            capture_output=True, text=True)
    missing = [n for n in sizes if not (folder / f"{n}.png").is_file()]
    if result.returncode != 0 or missing:
        sys.stderr.write(result.stderr)
        sys.exit("Inkscape did not draw the sizes " + ", ".join(map(str, missing or sizes)) + ".")


def check_sizes(folder, sizes):
    from PIL import Image
    for n in sizes:
        with Image.open(folder / f"{n}.png") as im:
            if im.size != (n, n):
                sys.exit(f"{n}.png came out {im.size[0]}x{im.size[1]}: is the SVG not square?")


def put(src, dst):
    """Copy src to dst, replacing it even if it is read-only."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    shutil.copyfile(src, dst)


def save_ico(path, sizes, png):
    from PIL import Image
    images = [Image.open(png(n)).convert("RGBA") for n in sizes]
    tmp = path.with_name(path.name + ".tmp")
    images[-1].save(tmp, format="ICO", append_images=images[:-1], sizes=[(n, n) for n in sizes])
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description="Make all the icons afresh from the SVG.")
    parser.add_argument("--svg", type=Path, default=ICONS / f"{NAME}.svg",
                        help=f"the SVG (src/py_imposition/icons/{NAME}.svg)")
    parser.add_argument("-o", "--output", type=Path, default=ICONS,
                        help="the folder for the icons (src/py_imposition/icons/)")
    parser.add_argument("--dry-run", action="store_true", help="only show how Inkscape would be run")
    args = parser.parse_args()

    svg = args.svg.resolve()
    out = args.output.resolve()
    if not svg.is_file():
        sys.exit(f"There is no {svg}.")
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("Pillow is needed for the .ico (it comes with pikepdf: run this with 'uv run').")

    inkscape, flatpak = find_inkscape()
    print(f"Inkscape: {' '.join(inkscape)}{' (Flatpak)' if flatpak else ''}")
    if flatpak and (out == Path("/tmp") or Path("/tmp") in out.parents):
        sys.exit("The Flatpak of Inkscape cannot write in /tmp; choose another folder with -o.")
    if args.dry_run:
        print(f"Would draw {svg} at {', '.join(map(str, SIZES))} px into {out}.")
        return

    out.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".render-", dir=out))
    try:
        render(inkscape, svg, stage, SIZES)
        check_sizes(stage, SIZES)

        def png(n):
            return stage / f"{n}.png"

        hicolor = out / "linux" / "hicolor"
        for n in HICOLOR_SIZES:
            put(png(n), hicolor / f"{n}x{n}" / "apps" / f"{NAME}.png")
        scalable = hicolor / "scalable" / "apps" / f"{NAME}.svg"
        if svg != scalable.resolve():
            put(svg, scalable)

        macos = out / "macos"
        iconset = macos / f"{NAME}.iconset"
        for n in ICONSET_SIZES:
            put(png(n), iconset / f"icon_{n}x{n}.png")
            put(png(2 * n), iconset / f"icon_{n}x{n}@2x.png")
        from py_imposition.install import make_icns
        icns = macos / f"{NAME}.icns"
        icns.with_name(icns.name + ".tmp").write_bytes(make_icns(iconset))
        os.replace(icns.with_name(icns.name + ".tmp"), icns)

        windows = out / "windows"
        windows.mkdir(parents=True, exist_ok=True)
        save_ico(windows / f"{NAME}.ico", ICO_SIZES, png)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    print(f"Made the icons in {out}:")
    for part in ["linux/hicolor", "macos", "windows"]:
        print(f"  {part}/")


if __name__ == "__main__":
    main()
