Open-source software used by py-imposition
==========================================

py-imposition is free software, under the GNU General Public License,
version 3 or later (GPL-3.0-or-later).  It is made with, and runs on, the
open-source software listed here, with the licence of each.  Licences are
given as SPDX identifiers; the versions are those of `uv.lock` for
py-imposition 0.10.3.  Each package carries the full text of its own
licence.


The program
-----------

What py-imposition needs to run, installed with it from PyPI.

| Software | Version | Used for | Licence |
|---|---|---|---|
| [Python](https://www.python.org) | 3.14 or later | The language and its standard library | PSF-2.0 |
| [pikepdf](https://github.com/pikepdf/pikepdf) | 10.18.0 | Reading and writing the PDF files | MPL-2.0 |
| [reportlab](https://www.reportlab.com/opensource/) | 5.1.0 | Text and fonts (stamps, page numbers, data merge) | BSD-3-Clause |
| [lxml](https://lxml.de) | 6.1.3 | XML, for pikepdf (XMP metadata) | BSD-3-Clause |
| [packaging](https://github.com/pypa/packaging) | 26.3 | Version numbers, for pikepdf | Apache-2.0 OR BSD-2-Clause |
| [Pillow](https://python-pillow.github.io) | 13.0.0 | Images, for pikepdf and reportlab | MIT-CMU |
| [charset-normalizer](https://github.com/jawah/charset_normalizer) | 3.5.2 | Text encodings, for reportlab | MIT |

pikepdf is built on the C++ library [QPDF](https://qpdf.sourceforge.io)
(Apache-2.0), which its wheels carry inside, with libjpeg-turbo (IJG,
BSD-3-Clause and Zlib).  The Pillow wheels carry FreeType (FTL or
GPL-2.0-or-later), HarfBuzz (MIT), Little CMS (MIT), libpng (Libpng-2.0),
libjpeg-turbo, LibTIFF (libtiff), libwebp (BSD-3-Clause), OpenJPEG
(BSD-2-Clause), libavif (BSD-2-Clause), Brotli (MIT), XZ's liblzma (0BSD),
Zstandard (BSD-3-Clause) and libxcb and libXau (MIT).


The window
----------

The window is optional (`py-imposition[gui]`).

| Software | Version | Used for | Licence |
|---|---|---|---|
| [PySide6](https://doc.qt.io/qtforpython-6/) (pyside6-essentials) | 6.12.0 | Qt for Python: the window | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6 (pyside6-pdf) | 6.12.0.140 | QtPdf: the preview of the document | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| shiboken6 | 6.12.0 | The binding between Python and Qt | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| [Qt 6](https://www.qt.io) | 6.12 | The toolkit itself, carried by the PySide6 wheels | LGPL-3.0-only (the modules used) |

py-imposition uses Qt and PySide6 under the LGPL, version 3.


Programs it calls, if installed
-------------------------------

None of these is needed; py-imposition looks for each and does without it
when it is not there.

| Software | Used for | Licence |
|---|---|---|
| [pdf2iso](https://github.com/nivaca/pdf2iso) (formerly py-pdfconform), by the same author | PDF/A and PDF/X output (`--conform`, *Save as*) | GPL-3.0-or-later |
| [Ghostscript](https://www.ghostscript.com), through pdf2iso | The PDF/A and PDF/X conversion | AGPL-3.0-or-later |
| [veraPDF](https://verapdf.org), through pdf2iso | Checking the PDF/A files | GPL-3.0-or-later OR MPL-2.0 |
| [Fontconfig](https://www.freedesktop.org/wiki/Software/fontconfig/) (`fc-match`) | Finding a font by its name, for stamps | HPND-sell-variant (MIT-style) |


Building, testing and packaging
-------------------------------

These are used to make and check py-imposition, and are not part of what is
installed (except the Python carried by the AppImage).

| Software | Used for | Licence |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) and uv_build | The environment, the lock file, the wheel and the source package | Apache-2.0 OR MIT |
| [pytest](https://pytest.org) 9.2.0, with iniconfig, pluggy, Pygments and colorama | The tests | MIT (Pygments: BSD-2-Clause; colorama: BSD-3-Clause) |
| [QPDF](https://qpdf.sourceforge.io) (`qpdf --check`) | Checking the structure of the PDF files the tests make | Apache-2.0 |
| [Poppler](https://poppler.freedesktop.org) (`pdftotext`) | Reading the text of the pages the tests make | GPL-2.0-or-later |
| [python-appimage](https://github.com/niess/python-appimage) | The relocatable Python 3.15 inside the AppImage | GPL-3.0-only (the tool); PSF-2.0 (Python) |
| [appimagetool](https://github.com/AppImage/appimagetool) | Making the AppImage | MIT |
| [Inkscape](https://inkscape.org) | Drawing the icons from the SVG (`tools/icons.py`) | GPL-2.0-or-later |
| [RPM](https://rpm.org) and Fedora's pyproject macros | The RPM package | GPL-2.0-or-later |
| [desktop-file-utils](https://www.freedesktop.org/wiki/Software/desktop-file-utils/) | Checking the `.desktop` file of the RPM | GPL-2.0-or-later |
| [Copr](https://copr.fedorainfracloud.org) | Building the RPMs for Fedora | GPL-2.0-or-later |
| [GnuPG](https://gnupg.org) | Signing the RPMs | GPL-3.0-or-later |

The RPM uses the PySide6 and Python packages of Fedora, under the same
licences as above.
