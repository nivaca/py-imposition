"""Imposition Info / Page monitor: report page sizes, boxes, bleeds and recorded commands."""

from __future__ import annotations

import json
import shlex

from pikepdf import Pdf

from . import pdfutil as pu
from .common import Context, command
from .units import UNITS


def _info_args(p):
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--all-pages", action="store_true", help="list every page instead of grouping runs")
    p.add_argument("--report-units", choices=["cm", "mm", "in", "pt"], default=None,
                   help="units for the report (default: --units)")


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
         description="Imposition Info / Page monitor.")
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

    print(f"{ctx.input_path}: {len(pages)} page{'s' if len(pages) != 1 else ''}")
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
        rng = f"page {p['page']}" if len(g) == 1 else f"pages {p['page']}-{g[-1]['page']}"
        line = f"  {rng}: {sz(*p['size'])}"
        if p["rotate"]:
            line += f", rotated {p['rotate']}°"
        if p["bleed_margins"]:
            bm = p["bleed_margins"]
            line += f"; trim {sz(*p['trim_size'])}, bleed L{bm[0] / f:.3g} B{bm[1] / f:.3g} " \
                    f"R{bm[2] / f:.3g} T{bm[3] / f:.3g} {u}"
        if p["user_unit"] != 1:
            line += f", UserUnit {p['user_unit']:g}"
        if p["annotations"]:
            line += f", {p['annotations']} annotation(s)"
        print(line)
    if history:
        print("Recorded commands (replay with 'replay --from'):")
        for k, step in enumerate(history, 1):
            print(f"  {k}. {shlex.join(step)}")
    return None
