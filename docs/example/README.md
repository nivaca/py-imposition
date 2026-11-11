# Example documents

## `memman.pdf`: a real book

`memman.pdf` is the user guide of the LaTeX *memoir* class: *The Memoir
Class for Configurable Typesetting*, by Peter Wilson, maintained by Lars
Madsen (memoir v3.8.4b, 2025/11/04; 625 US Letter pages).

It is a real book, used in the README's examples, in the screenshots made by
`tools/screenshots.py`, and in the tests. It is included unchanged, as
distributed on CTAN (<https://ctan.org/pkg/memoir>) under the LaTeX Project
Public License, version 1.3c.

Try it:

```bash
py-imposition info docs/example/memman.pdf
py-imposition booklet --signature 16 --paper a4 --crop-marks --margin 1.5cm docs/example/memman.pdf
py-imposition-gui docs/example/memman.pdf
```

## `numbers-100.pdf`: numbered pages

`numbers-100.pdf` has 100 US Letter portrait pages, each showing only its
own number (1 to 100), centred in 120 pt black Helvetica. Because every page
is identified at a glance, it is handy for checking page order, rotation and
placement after an imposition: in a saddle-stitched booklet, for example, the
first sheet must read 100 | 1 on the front and 2 | 99 on the back.

It was made for this project and is under the same licence as py-imposition.

Try it:

```bash
py-imposition booklet --binding saddle --paper a4 docs/example/numbers-100.pdf
py-imposition nup --cols 2 --rows 2 --scale fit --paper a3 --crop-marks docs/example/numbers-100.pdf
py-imposition shuffle --rule "8 1 5* 4* 2 7 3* 6*" --repeat saddle docs/example/numbers-100.pdf
```
