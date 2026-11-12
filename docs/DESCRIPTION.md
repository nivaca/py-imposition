How py-imposition was made
==========================

py-imposition imposes PDF pages for printing: it places the pages of a
document on larger sheets, in the order and position that a printer, a
folder and a binder need, so that once the sheets are printed, folded,
cut and bound the pages come out in order.  It makes booklets
(saddle-stitched, perfect bound, cut stacks), n-up and step and repeat
layouts, and it shuffles, trims, shifts, rotates and resizes pages, adds
bleeds, creep, crop marks, page numbers, stamps and masking tape, merges
variable data, and runs sequences of commands and hot folders.
Nicolas Vaughan made it in 2026.  It has a window, with a basic mode for
the usual impositions and an advanced mode with every command, and a
command line with the same commands, in English or in Spanish.  Here I
explain how it was made, in eight stages.

py-imposition is free software, under the GNU General Public License,
version 3 or later.  It is written in Python and stands on two libraries:
pikepdf (based on QPDF), which reads and writes the PDF files, and
reportlab, for text and fonts; the window uses PySide6 (Qt 6).

Nicolas Vaughan is Associate Professor of Literature at the School of Arts
and Humanities of the Universidad de los Andes, Bogotá, Colombia.

1. A booklet on the command line
--------------------------------

The first version did one thing: a 2-up booklet.  It took a PDF and put
its pages two by two on each side of a sheet, in the order that makes a
booklet when the sheets are folded, with the settings of a common
imposition dialog as defaults: perfect binding with four pages per fold,
binding on the left, Legal paper in landscape, no margins or gutters,
and pages shrunk only when they don't fit.  An option pushes the pages
against the fold, so the space left over goes to the outside edges.

From the start, a page is never rasterised or rewritten.  Each source
page becomes a Form XObject, an independent piece of PDF content, which
the sheet draws with a matrix that moves, scales and turns it, inside a
clipping rectangle.  The pages keep their vector text, fonts and images,
and a page placed many times (as in step and repeat) is stored once.

2. A whole toolkit
------------------

Then the program grew into a toolkit with the tools that an imposition
program usually has, each one a command: `booklet`, `nup`, `step-repeat`,
`join` and `manual` for placing pages on sheets; `shuffle`, `evenodd`,
`reverse`, `duplicate`, `delete`, `move`, `insert` and `split` for
arranging them; `trim-shift`, `creep`, `resize`, `rotate`, `tile` and
`bleed` for changing them; `text`, `stick-pdf`, `mask`, `merge-data` and
`peel` for sticking things on and taking them off; and `info`, `run`,
`replay` and `watch` for information and automation.  `sample` makes a
test document.

A few ideas carry most of the work:

- The page orders of the booklets and of `shuffle` are written as rules,
  such as `8 1 5* 4* 2 7 3* 6*` (the first sheet of a 4-up booklet,
  front and back, with `*` for a page upside down), which repeat over the
  whole document.  The tests check them against worked examples.
- Every page has its boxes: the trim box is what lines up on the sheet,
  and the bleed box, if there is one, shows beyond it, clipped so that it
  never runs into the next page.  The crop marks are "smart": a mark is
  left out where it would fall on a page.
- What the program sticks on a page (text, tape, marks, other pages) is
  tagged as marked content, so `peel` can take it off later.
- Each command writes its command line into the PDF's document
  information.  `replay` reads it and does the same to another document
  (imposition by example), and `run` runs a saved sequence of commands.
  `watch` turns a folder into a hot folder: each PDF dropped into it goes
  through a sequence.

All the commands share one framework (`common.py`): a decorator
registers each one with its options, and the command line (`argparse`)
and, later, the window are built from those definitions.  Lengths take
units (`5mm`, `1.5cm`, `3/8in`), paper sizes take names or sizes
(`a4`, `21x29.7cm`), and page ranges take expressions (`1-4,7`,
`3..LAST`).  This was version 0.1.

3. The window
-------------

Version 0.2 added a window, with PySide6.  Its forms are not drawn by
hand: they are generated from the same argparse definitions as the
command line, so every option of every command has a field, with the
same name, default and help, and a new option appears in the window by
itself.  Above the form, the window shows the equivalent command line.

The window doesn't impose anything itself.  It runs the command line in
a background process (QProcess), so it never freezes and a long job can
be stopped; a Log tab shows each command and its output.  The result is
shown with QtPdf, and with *Auto preview* it is made again shortly after
each change.  *Apply* makes the result the current document, so commands
can be chained, with *Undo apply* and *Revert to original*.  A Sequence
panel collects the steps, loads them from a document's history and runs
them on a batch of files.

Version 0.3 added an installer for the applications menu (Linux, Windows
and macOS), an icon made from one SVG in every size, an example document
and a tool that takes the screenshots of the README.  The tool runs the
window with Qt's offscreen platform, so nothing appears on the screen
and the pictures don't depend on the screen they were made on.

4. Two languages
----------------

Version 0.4 brought a Spanish interface.  Every text of the program, in
the window and in the command line, including argparse's own messages,
goes through `tr()`, and the translations are kept in one XML file,
`locale/es.xml`, with each text in English and in Spanish.  The language
is chosen in the window (*Settings*), with `--interface` on the command
line, or in a small configuration file, `config.toml` (which
`py-imposition interface es` writes).  A test checks
that every text has its translation and that no translation is left
over, so a new message cannot be forgotten.  The README has a Spanish
version, kept parallel to the English one, and the screenshots are made
in both languages.

5. Packages
-----------

The same version made py-imposition easy to install.  The AppImage holds
its own Python, Qt and libraries, and runs on almost any Linux; its first
argument decides between the window and the command line.  For Fedora
there is an RPM, built with Fedora's own Python, pikepdf, reportlab and
PySide6, that runs the whole test suite while it is built, and that Copr
builds and publishes for each Fedora version.  The RPMs are signed with
the author's key, whose public part ships in the repository.

The first AppImage taught a lesson: on the machine where it was built it
found pikepdf among the user's own Python packages, so it worked there
and nowhere else.  Version 0.4.1 installs the packages in isolation,
checks that each module imports from inside the AppImage, and starts it
once with an empty home folder before publishing it.

A script, `tools/release.py`, makes every release in the same way: it
runs the tests, builds the wheel, the source package, the AppImage and
the signed RPM, tags the version, pushes it to GitHub and Codeberg,
publishes the releases with all the files, and sends the RPM to Copr.

6. A basic mode
---------------

With every command in it, the window had become complicated for the
common case.  Version 0.5 divided it into two modes.  The advanced mode
is the window as it was.  The basic mode is one form, laid out like a
common imposition dialog: the layout (2-, 4- and 8-up booklets, cut
stacks, sequential, step and repeat), the binding, the gutters, the
paper, the margins and the printer marks, with named profiles that can
also go in a menu.  Options that don't apply to the chosen layout are
greyed out.

Behind the basic mode there is a new command, `impose`, which does all
those impositions in one step, so whatever the form does can also be
done on the command line, and the form always shows the command line it
runs.  The 4- and 8-up booklets use the standard folding layouts, as
shuffle rules.

The versions after it made the window easier: the original document is
shown beside the result only if *View ▸ Show the original document* is
ticked (version 0.5.1), and *File ▸ Open recent* lists the last ten
documents (version 0.6).  The example document became a PDF of 100
pages, each showing only its number, on which the order of any
imposition can be checked at a glance.

7. Filling the sheet
--------------------

Many PDFs have wide white margins, and imposed two or four to a sheet
their text becomes small.  Version 0.7 gave `impose` three ways to make
the content fill more of the sheet.  `--page-trim` cuts the white edges
off every page before it is placed (on all sides, or on each one).
`--enlarge` lets the pages grow to fill their place, and not only shrink
when they are too big.  And margins and gutters can be negative: the
pages then run off the sheet or overlap, and each one is cut at the
sheet's edge or in the middle of the overlap.  The same version made
four sheets per fold the default of perfect binding.

8. Saving, and what is not saved
--------------------------------

The window had two ways to save: *Save document*, the original with the
commands applied so far, and *Save result*, the current command's
preview.  Once the original document was hidden by default, the first
saved something that could not be seen, and after *Apply* the automatic
preview ran the same command again, so the result showed it applied
twice.  Version 0.8 has one *Save…*, which saves what the right pane
shows (running the command first if the preview is not up to date);
after *Apply*, that pane shows the document as it is until the options
change.  *File ▸ Save the document as it is…* keeps the other way, for
chains of commands.

The window also says when there is something to lose: while commands
have been applied, or options changed and a result made, since the
document was opened or saved, the title bar shows an asterisk, and
closing the window, opening another document or reverting to the
original asks first whether to save it.

Testing
-------

The program has 97 automated tests (`tests/`), run with pytest.  They
check the page orders against worked examples of standard impositions,
run every command from beginning to end on generated documents and read
the results with pdftotext and `qpdf --check`, and impose the example
document.  The window is tested headless, with Qt's offscreen platform:
the forms, the basic mode and its profiles, the previews, *Apply* and
*Undo*, the recent documents, and the language.  Other tests check that
every text is translated, the menu installer on each system, the
packaging files, and the signing key.

The tests run on every push, on GitHub Actions, and again inside every
RPM build on Copr, with the Python of each Fedora (3.14 and 3.15).  The
screenshots of the README are made again with each change to the
window, and checked by eye.  The program has now about 7,800 lines in 28
modules, and 30 commands.
