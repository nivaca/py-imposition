# Example document

`numbers-100.pdf` has 100 US Letter portrait pages, each showing only its
own number (1 to 100), centred in 120 pt black Helvetica. Because every page
is identified at a glance, it is handy for checking page order, rotation and
placement after an imposition: in a saddle-stitched booklet, for example, the
first sheet must read 100 | 1 on the front and 2 | 99 on the back.

It is used in the README's examples, in the screenshots made by
`tools/screenshots.py`, and in the tests. It was made for this project and
is under the same licence as py-imposition.

Try it:

```bash
py-imposition info docs/example/numbers-100.pdf
py-imposition booklet --binding saddle --paper a4 docs/example/numbers-100.pdf
py-imposition nup --cols 2 --rows 2 --scale fit --paper a3 --crop-marks docs/example/numbers-100.pdf
py-imposition shuffle --rule "8 1 5* 4* 2 7 3* 6*" --repeat saddle docs/example/numbers-100.pdf
py-imposition-gui docs/example/numbers-100.pdf
```
