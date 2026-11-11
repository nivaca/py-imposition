"""Imposition info: report page sizes, boxes, bleeds and recorded commands."""

from __future__ import annotations

import json
import shlex

from pikepdf import Pdf

from . import pdfutil as pu
from . import config, interface
from .common import Context, ImpositionError, command
from .units import UNITS
from .interface import N_, ntr, tr


def _info_args(p):
    p.add_argument("--json", action="store_true", help=tr("machine-readable output"))
    p.add_argument("--all-pages", action="store_true", help=tr("list every page instead of grouping runs"))
    p.add_argument("--report-units", choices=["cm", "mm", "in", "pt"], default=None,
                   help=tr("units for the report (default: --units)"))


def page_info(page, idx: int) -> dict:
    mb = pu.media_box(page)
    cb = pu.crop_box(page)
    tb = pu.trim_box(page)
    bb = pu.bleed_box(page)
    rot = pu.page_rotation(page)
    w, h = pu.geometry(page, use_bleed=False).size()
    tw, th = pu.geometry(page, use_bleed=True).size()
    return {
        "page": idx + 1,
        "size": [w, h],
        "trim_size": [tw, th],
        "rotate": rot,
        "user_unit": float(page.get("/UserUnit", 1)),
        "media_box": list(mb),
        "crop_box": list(cb),
        "trim_box": list(tb) if "/TrimBox" in page else None,
        "bleed_box": list(bb) if "/BleedBox" in page else None,
        "bleed_margins": [tb[0] - bb[0], tb[1] - bb[1], bb[2] - tb[2], bb[3] - tb[3]] if pu.has_bleed(page) else None,
        "annotations": len(page.get("/Annots", [])),
    }


@command("info", "show page sizes, boxes, bleeds and recorded commands", _info_args,
         description=N_("Show the size, boxes and bleeds of the pages, and the commands recorded in the document."))
def info(pdf: Pdf, a, ctx: Context):
    pages = [page_info(p.obj, i) for i, p in enumerate(pdf.pages)]
    history = pu.get_history(pdf)
    if a.json:
        print(json.dumps({"pages": pages, "history": history}, indent=2))
        return None
    u = a.report_units or ctx.units
    f = UNITS[u]

    def sz(w, h):
        return f"{w / f:.4g} x {h / f:.4g} {u}"

    print(ntr('{path}: {count} page', '{path}: {count} pages', len(pages), path=ctx.input_path))
    groups: list[list[dict]] = []
    for p in pages:
        key = (round(p["size"][0], 2), round(p["size"][1], 2), p["rotate"], p["bleed_margins"] and
               tuple(round(v, 2) for v in p["bleed_margins"]))
        if groups and not a.all_pages and groups[-1][0]["_key"] == key:
            groups[-1].append(p)
        else:
            p["_key"] = key
            groups.append([p])
    for g in groups:
        p = g[0]
        rng = tr("page {page}", page=p["page"]) if len(g) == 1 else \
            tr("pages {first}-{last}", first=p["page"], last=g[-1]["page"])
        line = f"  {rng}: {sz(*p['size'])}"
        if p["rotate"]:
            line += tr(", rotated {degrees}°", degrees=p["rotate"])
        if p["bleed_margins"]:
            bm = p["bleed_margins"]
            line += tr("; trim {size}, bleed L{left} B{bottom} R{right} T{top} {unit}",
                       size=sz(*p["trim_size"]), left=f"{bm[0] / f:.3g}", bottom=f"{bm[1] / f:.3g}",
                       right=f"{bm[2] / f:.3g}", top=f"{bm[3] / f:.3g}", unit=u)
        if p["user_unit"] != 1:
            line += f", UserUnit {p['user_unit']:g}"
        if p["annotations"]:
            line += ntr(", {count} annotation", ", {count} annotations", p["annotations"])
        print(line)
    if history:
        print(tr("Recorded commands (replay with 'replay --from'):"))
        for k, step in enumerate(history, 1):
            print(f"  {k}. {shlex.join(step)}")
    return None


def _interface_args(p):
    p.add_argument("language", nargs="?", choices=sorted(interface.names()),
                   help=tr("the language to keep for the interface; without it, show the languages and the "
                           "one in use"))


@command("interface", "show or choose the language of the interface", _interface_args, needs_input=False,
         description=N_("The language of the help, the messages and the window. The choice is kept in the "
                        "configuration file; --interface CODE changes it for one run only."))
def choose_interface(pdf, a, ctx: Context):
    names = interface.names()
    if a.language is None:
        current = interface.code()
        print(tr("Languages of the interface:"))
        for code, name in names.items():
            print(f"  {'*' if code == current else ' '} {code}  {name}")
        print(tr("Configuration file: {path}", path=config.config_path()))
        return None
    if not interface.use(a.language):
        raise ImpositionError(tr("the language {code} cannot be used: {error}", code=a.language,
                                 error=interface.error()))
    path = config.set("interface", a.language)
    print(tr("The interface is now in {name} (kept in {path}).", name=names[a.language], path=path))
    return None

