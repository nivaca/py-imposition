"""Measurements and paper sizes.

All internal measurements are PDF points (1/72 inch). User input may carry a
unit suffix (``10mm``, ``1.5cm``, ``0.5in``, ``12pt``) or a simple fraction
(``3/8in``); bare numbers use the current default unit.
"""

from __future__ import annotations

import re
from fractions import Fraction
from .interface import tr

UNITS = {
    "pt": 1.0,
    "mm": 72 / 25.4,
    "cm": 72 / 2.54,
    "in": 72.0,
    '"': 72.0,
}

DEFAULT_UNIT = "cm"

# Portrait (tall) sizes, width x height in points.
PAPER_SIZES: dict[str, tuple[float, float]] = {
    "letter": (612, 792),
    "legal": (612, 1008),
    "tabloid": (792, 1224),
    "ledger": (792, 1224),
    "executive": (522, 756),
    "statement": (396, 612),
    "a0": (2383.94, 3370.39),
    "a1": (1683.78, 2383.94),
    "a2": (1190.55, 1683.78),
    "a3": (841.89, 1190.55),
    "a4": (595.28, 841.89),
    "a5": (419.53, 595.28),
    "a6": (297.64, 419.53),
    "b4": (708.66, 1000.63),
    "b5": (498.9, 708.66),
    "sra3": (907.09, 1275.59),
    "max": (14400, 14400),  # 200 x 200 inches, the largest page size PDF viewers accept
}

_LEN_RE = re.compile(r"^\s*([-+]?[0-9./]+)\s*([a-z\"]*)\s*$", re.I)


def parse_length(value: str | float | int, unit: str | None = None) -> float:
    """Parse a length into points."""
    if isinstance(value, (int, float)):
        return float(value) * UNITS[unit or DEFAULT_UNIT]
    m = _LEN_RE.match(str(value))
    if not m:
        raise ValueError(tr('invalid length: {value!r}', value=value))
    num, suffix = m.groups()
    suffix = suffix.lower() or (unit or DEFAULT_UNIT)
    if suffix not in UNITS:
        raise ValueError(tr('unknown unit {suffix!r} in {value!r} (use pt, mm, cm or in)', suffix=suffix, value=value))
    try:
        n = float(Fraction(num))
    except (ValueError, ZeroDivisionError):
        raise ValueError(tr('invalid number in {value!r}', value=value)) from None
    return n * UNITS[suffix]


def parse_length_list(value: str, unit: str | None = None) -> list[float]:
    """Parse a space/comma separated list of lengths ("0 40", "1cm,2cm")."""
    parts = [p for p in re.split(r"[\s,]+", value.strip()) if p]
    if not parts:
        raise ValueError(tr("empty list of lengths"))
    return [parse_length(p, unit) for p in parts]


def format_length(points: float, unit: str | None = None) -> str:
    unit = unit or DEFAULT_UNIT
    return f"{points / UNITS[unit]:.4g} {unit}"


def parse_paper(spec: str, unit: str | None = None) -> tuple[float, float]:
    """Parse a paper name (``a4``) or explicit ``WxH`` size (``21x29.7cm``).

    Returns (width, height) as given; named sizes are returned tall.
    """
    s = spec.strip().lower()
    if s in PAPER_SIZES:
        return PAPER_SIZES[s]
    m = re.match(r"^([-+0-9./]+)\s*([a-z\"]*)\s*[x×*]\s*([-+0-9./]+)\s*([a-z\"]*)$", s)
    if m:
        w, wu, h, hu = m.groups()
        u = hu or wu or unit
        return parse_length(w + (wu or u or ""), unit), parse_length(h + (hu or u or ""), unit)
    raise ValueError(
        tr('unknown paper size {spec!r}; use one of {items} or WxH like 21x29.7cm', spec=spec, items=', '.join(sorted(PAPER_SIZES)))
    )


def orient(size: tuple[float, float], orientation: str) -> tuple[float, float]:
    """Apply 'wide'/'landscape' or 'tall'/'portrait' to a size; 'as-is' keeps it."""
    w, h = size
    o = orientation.lower()
    if o in ("wide", "landscape"):
        return (max(w, h), min(w, h))
    if o in ("tall", "portrait"):
        return (min(w, h), max(w, h))
    return (w, h)
