# py-imposition

A command-line tool that imposes a PDF as a **2-up booklet**. It reorders the
pages and places them, two per side, on larger sheets. You print the result
double-sided, fold each sheet in half, and the pages read in the right order.

## Installation

You need Python 3.15+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> py-imposition
cd py-imposition
uv sync
```

To install the `py-imposition` command globally:

```bash
uv tool install .
```

## Usage

```bash
uv run py-imposition input.pdf              # writes input-imposed.pdf
uv run py-imposition input.pdf output.pdf
```

### Default settings

| Setting      | Default                                   |
|--------------|-------------------------------------------|
| Type         | 2-up booklet                              |
| Binding      | Perfect binding, 4 pages per fold         |
| Binding edge | Left                                      |
| Paper        | Legal (35.56 × 21.59 cm), landscape       |
| Scaling      | Auto (fit each page to half the sheet)    |
| Alignment    | Centered in each half                     |
| Margins      | 0 cm on every side                        |
| Gutter       | 0 cm                                      |

### Options

| Option                         | Description |
|--------------------------------|-------------|
| `--binding {perfect,saddle}`   | `perfect`: each signature is folded separately and the signatures are stacked. `saddle`: every sheet is nested into a single signature. |
| `--pages-per-fold N`           | Pages per signature for perfect binding. Must be a multiple of 4 (default: 4, one sheet folded once). |
| `--direction {left,right}`     | Binding edge: `left` for left-to-right books, `right` for right-to-left books. |
| `--paper NAME`                 | Sheet size: `letter`, `legal`, `tabloid`, `a3`, `a4`, `a5`. |
| `--orientation {landscape,portrait}` | Sheet orientation. |
| `--margin CM`                  | Margin on all four sides, in cm. |
| `--margin-top/-bottom/-left/-right CM` | Margin on one side, in cm. Overrides `--margin`. |
| `--gutter CM`                  | Space between the two pages at the fold, in cm. |
| `--align {center,fold}`        | `center`: center each page in its half of the sheet. `fold`: push pages against the fold so any spare space goes to the outer edges. |
| `--no-auto-scale`              | Shrink pages that are too large, but never enlarge small ones. |

### Examples

```bash
# Saddle-stitched A4 booklet from A5 pages
uv run py-imposition --binding saddle --paper a4 doc.pdf

# 8-page signatures, pages flush at the fold, 0.5 cm outer margins
uv run py-imposition --pages-per-fold 8 --align fold --margin 0.5 doc.pdf

# Right-to-left book
uv run py-imposition --direction right doc.pdf
```

## Printing

Print the output **double-sided, flipping on the short edge**. Each sheet
holds four pages: with the default settings, the first sheet has pages 4 | 1 on
the front and 2 | 3 on the back. Fold each sheet in half and stack the folded
sheets in order.

If the page count is not a multiple of the signature size, blank pages are
added at the end.

## How it works

- **Page order.** Within a signature of *n* pages, sheet *i* (counting from 0,
  outermost first) carries pages `n−2i | 2i+1` on the front and
  `2i+2 | n−2i−1` on the back (1-based). With right binding, left and right
  are swapped.
- **Placement.** The sheet is split into two cells, after subtracting the
  margins and gutter. Each source page is turned into a PDF Form XObject and
  scaled to fit its cell, keeping its proportions. Page rotation (`/Rotate`)
  is respected. The source content stays vector; nothing is rasterized.

The core logic is in `src/py_imposition/imposition.py` and can be used from
Python:

```python
from pathlib import Path
from py_imposition import impose, Settings, Margins

impose(Path("in.pdf"), Path("out.pdf"),
       Settings(paper="a4", align="fold", margins=Margins(left=1, right=1)))
```

## Dependencies

- [pikepdf](https://pikepdf.readthedocs.io/) (based on QPDF)
