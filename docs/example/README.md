# Example document

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
