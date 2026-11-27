# Changelog

All notable changes to py-imposition. The releases, with the wheel, the
source package, the AppImage and the RPM, are on
[Codeberg](https://codeberg.org/nivaca/py-imposition/releases) and
[GitHub](https://github.com/nivaca/py-imposition/releases); the RPM is also
in the Copr project nivaca/py-imposition.

## Unreleased

- `tools/zenodo.py`: the description of the deposit is now the whole
  README of the tag, in HTML. The draft also gets the contributor (the
  project leader), the languages, the copyright, the repository on GitHub,
  the programming language and the development status, these last through
  Zenodo's records API (its deposit API doesn't take them). The token can
  be kept in the desktop keyring (`secret-tool store --label="Zenodo
  token" service zenodo`) instead of `$ZENODO_TOKEN`; `tools/zenodo.py
  check-token` says whether there is one.

- `tools/zenodo.py` prepares the deposit of a release for Zenodo. `collect`
  puts in `dist/zenodo/` the tree of the tag as
  `py-imposition-VERSION-source.tar.gz`, with its signature, a signed
  `SHA256SUMS` of the deposit and the public key, and checks every signature
  with only that key (`--packages` adds the files of the release). `upload`
  sends it to Zenodo as a draft, a new version of the deposit if there is
  one already, and never publishes it. `tools/release.py` now collects the
  deposit after the tag and uploads it as a draft, unless `--no-zenodo`. The
  metadata are in `.zenodo.json`.
- `tools/zenodo.py`: the description of the deposit leaves out the line
  that points to the README in other languages and the Screenshots section,
  whose images Zenodo does not show.
- `tools/release.py` now publishes each release on Zenodo
  (`tools/zenodo.py upload --publish`), instead of leaving a draft;
  `--zenodo-draft` still leaves one. `tools/zenodo.py publish` publishes a
  draft already there (by default the one waiting with the project's title).
- `tools/test.py` runs the tests at once, each test file in a pytest
  process of its own, as many as there are processors, the slowest first.
  `tools/release.py` and the RPM's `%check` run them so, instead of one
  pytest for them all.

## 0.10.5 — 2026-11-22

- **Every release signed**: besides the RPM, each file published (the
  wheel, the source package, the AppImage) comes with its signature
  (`.asc`), with `SHA256SUMS` and its signature, and with the public key;
  the tag of the version is signed too. `tools/release.py` makes the
  signed RPM always (`--no-rpm` leaves it out) and checks each signature
  with the published key before anything is published. The READMEs say
  how to check a download.

## 0.10.4 — 2026-11-21

- `docs/OPEN-SOURCE.md` (and `docs/OPEN-SOURCE_es.md`, in Spanish) lists
  the open-source software py-imposition uses, with the licence of each;
  the READMEs link to it.
- Python 3.14 or later is needed (it was 3.15), in `requires-python`
  and the READMEs. The tests pass with 3.14; the AppImage still carries
  Python 3.15.
- `packaging/build-rpm.sh` copies the newest RPM to `dist/` too, in place
  of the older ones there.
- `docs/DESCRIPCIÓN_es.md` keeps to six sections, each under 4000
  characters, written in the third person.

## 0.10.3 — 2026-11-17

- PDF/A and PDF/X are made by pdf2iso, the new name of py-pdfconform. The
  program looks for `pdf2iso` first and still finds `py-pdfconform`, so an
  older installation keeps working; a path given in the settings is kept.
- The contact email is nicolasvaughan@proton.me.

## 0.10.2 — 2026-11-17

- **Gutters only move the pages.** In `impose`, the size of the pages
  comes from the sheet and the margins only: a wider gutter spreads the
  pages apart and a narrower one brings them together, without changing
  their size (before, once there was no spare space outside, a wider
  gutter shrank the pages). It warns when the gutters push the pages off
  the sheet.
- The window starts each session with the default settings: the options
  of the commands (basic mode included), the toolbar preferences, the
  sequence and the margin locks are no longer restored. They still carry
  over when the window is rebuilt in another language; the layout, mode,
  auto preview, profiles and recent documents are kept.

## 0.10.1 — 2026-11-17

- A negative margin makes the pages grow until they run off the sheet by
  that much on that side (cut at the edge); before, negative left and
  right margins did nothing when the page height set the scale.
- In booklets the fold stays in the middle: uneven left and right margins
  count as the larger one on both sides.

## 0.10 — 2026-11-17

- **Exact gutters.** `impose` places the pages together as one block,
  with exactly the gutters between them, centred within the margins;
  space left over goes to the outside, so the margins are a minimum.
  Before, each page was centred in its own place, and a wider gutter took
  space from the margins.
- When a result is made again, the preview stays on the page being looked
  at.
- **PDF/A (1b, 2b, 3b) and PDF/X-4 output** through py-pdfconform: File >
  Save as in the window, `--conform` on the command line, and Settings >
  py-pdfconform… to say where it is (kept as `pdfconform` in
  `config.toml`).
- A crash at Python's exit in the tests is fixed (the preview pane is
  deleted while Qt is still running).

## 0.9 — 2026-11-17

- `impose` prints the page information (document name, sheet number, date
  and time) unless `--no-page-info` is given; basic mode has it ticked by
  default. The advanced forms handle on/off options (`--x` / `--no-x`).
- Basic mode: in Margins and in Page Trim, a lock for Top/Bottom and
  another for Left/Right keep both sides equal. The window remembers them,
  and a lock whose values differ after loading settings is released.

## 0.8.3 — 2026-11-17

- Basic mode greys out the horizontal gutter when there is a single row
  of pages (a 2-up booklet) and the vertical one when there is a single
  column, and leaves them out of the command line.
- `impose` warns when `--gutter-v` or `--gutter-h` cannot apply.
- `tools/icons.py` finds Inkscape as `$INKSCAPE` or
  `~/AppImages/inkscape.appimage` first, then on the PATH, then as a
  Flatpak.

## 0.8.2 — 2026-11-14

- Python 3.15 or later is needed (it was 3.13). The AppImage carries
  Python 3.15, and Copr no longer builds for Fedora 44.

## 0.8.1 — 2026-11-14

- Python 3.13 or later is needed (it was 3.12).
- A new RPM signing key (ed25519, valid until 2029), pinned in
  `build-rpm.sh`, with its public key in `packaging/`.

## 0.8 — 2026-11-12

- **One Save.** Save… (Ctrl+S, toolbar, button) saves what the right pane
  shows, running the command first if the preview is not up to date;
  File > Save the document as it is… (Ctrl+Shift+S) saves the applied
  commands without the current one.
- After Apply, the right pane shows the applied document instead of
  running the same command again.
- **Unsaved changes.** With unsaved work, the title bar shows an asterisk,
  and closing, opening another document or reverting asks whether to save
  first.
- The save dialogs' titles and messages are translated.
- The READMEs present the window and the command line together;
  `docs/DESCRIPTION.md` and `docs/DESCRIPCIÓN_es.md` describe how the
  program was made.

## 0.7 — 2026-11-12

- `impose`: perfect binding folds stacks of four sheets unless
  `--sheets-per-fold` says otherwise, on the command line and in basic
  mode.
- `--page-trim` (and `-top`, `-bottom`, `-left`, `-right`) cuts the white
  edges off every page before it is placed; `--enlarge` lets auto scale
  also enlarge pages to fill their cells.
- Margins and gutters can be negative: pages run off the sheet or
  overlap, cut at the edge or in the middle of the overlap.
- Basic mode has a Page Trim group and an Enlarge checkbox.

## 0.6 — 2026-11-11

- File > Open recent lists the last ten documents opened, with Clear the
  list.
- About names the author, with a link to his site.
- The example book is removed; the screenshots, the README and the tests
  use `numbers-100.pdf`, a document of 100 numbered pages for checking
  page order at a glance.
- The RPM signing key is pinned in `build-rpm.sh` and `release.py`, and
  its public key is shipped in `packaging/RPM-GPG-KEY-py-imposition`.

## 0.5.1 — 2026-11-11

- View > Show the original document shows or hides the preview of the
  current document beside the result. It is off by default, and the
  choice is kept in `config.toml` (`show_document`).
- The GUI tests use a configuration folder of their own and no longer
  touch the user's `config.toml`.

## 0.5 — 2026-11-11

- **The `impose` command**: the usual impositions in one command. It does
  2-, 4- and 8-up booklets (saddle-stitched, or perfect bound in stacks of
  folded sheets), cut stacks, sequential and step and repeat, with
  columns and rows, binding edge, single or double sided, gutters, creep,
  media size, auto-rotate and auto scale, margins, and trim, bleed and
  registration marks and page information.
- **Basic mode in the window**: a Basic | Advanced switch. Basic mode is
  one form for `impose`, with named profiles (save, save as, delete, the
  Profiles menu); options that do not apply are greyed out, and changing
  units converts the values. Advanced mode is the window as before.
- Spanish translations, tests, the READMEs and the screenshots.

## 0.4.1 — 2026-11-11

- **The AppImage holds all its dependencies.** The 0.4 AppImage was built
  while pip could see the user's site-packages, so it left out pikepdf
  and Pillow and only ran where they were installed.
  `tools/bundle-appimage.py` now installs in isolation, checks that the
  bundled Python imports everything, and runs the finished AppImage with
  an empty home folder.
- Empty fields in the window show an example of what they take ("e.g. 5mm
  or 1.5cm") instead of the option's metavar.
- The command line above the options uses the theme's text colour, so it
  is readable in dark themes.

## 0.4 — 2026-11-11

### Added

- **The interface in Spanish**, on the command line and in the window
  (`src/py_imposition/locale/es.xml`). `py-imposition interface es|en`
  keeps the choice in `config.toml`, `--interface CODE` changes it for one
  run, and the window has Settings > Language of the interface.
  `README_es.md` and the screenshots in both languages.
- An AppImage with its own Python 3.14, PySide6 and the program
  (`tools/bundle-appimage.py`).
- An RPM (`packaging/py-imposition.spec`, `packaging/build-rpm.sh
  [--sign]`) and the Copr project nivaca/py-imposition.
- `tools/release.py` publishes a release on GitHub, Codeberg and Copr.

### Changed

- Python 3.12 or later, and the pikepdf, reportlab and PySide6 of Fedora
  44 and 45, are supported.
- The README no longer refers to other products.

## 0.3 — 2026-11-11

- `py-imposition-install` adds the window to the applications menu with
  the program's icon (Linux, Windows and macOS, no administrator rights);
  `--uninstall` removes only what it added.
- An icon, and every size made from it by `tools/icons.py`.
- The window fits smaller screens: its minimum width goes from about 1990
  to 1036 pixels.
- An example book, `tools/screenshots.py`, and screenshots in the README.

## 0.2 — 2026-11-11

- **A graphical interface**, `py-imposition-gui`, with the optional `gui`
  extra (PySide6): every command, with option forms made from the command
  line parser; previews of the document and the result; Apply/Undo to
  chain commands; a sequence panel; imposition info, batch runs and hot
  folders. Commands run in a background process that can be stopped.
- `python -m py_imposition` works.

## 0.1 — 2026-11-11

- First version: a command line program that imposes PDF pages for
  printing. It began as a 2-up booklet maker (perfect or saddle binding)
  and grew into a set of subcommands: booklets, n-up, step and repeat,
  join and manual layouts; page arrangement (shuffle, even/odd, reverse,
  duplicate, delete, move, insert, split); page changes (trim and shift,
  creep, resize, rotate, tile, bleed); text, numbers, stamps and masks;
  variable data from CSV; sequence files, replay of the commands recorded
  in each output, and hot folders.
- Tests with pytest, run on GitHub at every push.
- GPL-3.0-or-later; `--version`.
