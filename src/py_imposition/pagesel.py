"""Page numbers and page ranges.

Page numbers are 1-based in user input and may be written relative to the
last page: ``LAST``, ``LAST-1``. Ranges use ``a..b`` or ``a-b`` (``LAST-3..LAST``).
Lists are separated by commas or spaces. ``all``, ``odd`` and ``even`` are
accepted as whole specs.
"""

from __future__ import annotations

import re

_NUM = r"(?:LAST(?:-\d+)?|\d+)"


def page_number(token: str, n: int) -> int:
    """Resolve one page number (1-based, LAST allowed) to a 1-based int."""
    t = token.strip().upper().replace(" ", "")
    if t.startswith("LAST"):
        rest = t[4:]
        if not rest:
            return n
        if rest.startswith("-") and rest[1:].isdigit():
            return n - int(rest[1:])
        raise ValueError(f"invalid page number {token!r}")
    if t.isdigit():
        return int(t)
    raise ValueError(f"invalid page number {token!r}")


def _split_range(token: str) -> tuple[str, str] | None:
    t = token.strip()
    if ".." in t:
        a, b = t.split("..", 1)
        return a, b
    # a-b, but not LAST-1 on its own
    m = re.match(rf"^({_NUM})-({_NUM})$", t.upper().replace(" ", ""))
    if m and not re.fullmatch(r"LAST-\d+", t.upper().replace(" ", "")):
        return m.group(1), m.group(2)
    return None


def parse_pages(spec: str | None, n: int, *, allow_out_of_range: bool = False,
                keep_order: bool = False) -> list[int]:
    """Return 0-based page indices selected by ``spec``.

    By default the result is sorted and de-duplicated.
    """
    if spec is None or spec.strip().lower() in ("", "all"):
        return list(range(n))
    s = spec.strip().lower()
    if s == "odd":
        return list(range(0, n, 2))
    if s == "even":
        return list(range(1, n, 2))
    out: list[int] = []
    for token in re.split(r"[,\s]+", spec.strip()):
        token = token.strip()
        if not token:
            continue
        rng = _split_range(token)
        if rng:
            a, b = page_number(rng[0], n), page_number(rng[1], n)
            step = 1 if b >= a else -1
            nums = list(range(a, b + step, step))
        else:
            nums = [page_number(token, n)]
        for p in nums:
            if not 1 <= p <= n:
                if allow_out_of_range:
                    continue
                raise ValueError(f"page {p} is out of range (document has {n} pages)")
            out.append(p - 1)
    if keep_order:
        return out
    return sorted(set(out))


def filter_parity(indices: list[int], parity: str | None) -> list[int]:
    """Keep only odd/even page numbers (1-based parity)."""
    if parity in (None, "all", "both"):
        return indices
    if parity == "odd":
        return [i for i in indices if i % 2 == 0]
    if parity == "even":
        return [i for i in indices if i % 2 == 1]
    raise ValueError(f"invalid parity {parity!r}")


def select(spec: str | None, n: int, parity: str | None = None) -> list[int]:
    return filter_parity(parse_pages(spec, n), parity)
