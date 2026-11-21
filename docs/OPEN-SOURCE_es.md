Software de código abierto que usa py-imposition
================================================

py-imposition es software libre, bajo la Licencia Pública General de GNU,
versión 3 o posterior (GPL-3.0-or-later).  Está hecho con el software de
código abierto de esta lista, y funciona sobre él; de cada uno se da la
licencia, con su identificador SPDX.  Las versiones son las de `uv.lock`
para py-imposition 0.10.3.  Cada paquete lleva el texto completo de su
propia licencia.


El programa
-----------

Lo que py-imposition necesita para funcionar, y que se instala con él desde
PyPI.

| Software | Versión | Para qué | Licencia |
|---|---|---|---|
| [Python](https://www.python.org) | 3.14 o posterior | El lenguaje y su biblioteca estándar | PSF-2.0 |
| [pikepdf](https://github.com/pikepdf/pikepdf) | 10.18.0 | Leer y escribir los PDF | MPL-2.0 |
| [reportlab](https://www.reportlab.com/opensource/) | 5.1.0 | Texto y fuentes (sellos, números de página, combinación de datos) | BSD-3-Clause |
| [lxml](https://lxml.de) | 6.1.3 | XML, para pikepdf (metadatos XMP) | BSD-3-Clause |
| [packaging](https://github.com/pypa/packaging) | 26.3 | Números de versión, para pikepdf | Apache-2.0 OR BSD-2-Clause |
| [Pillow](https://python-pillow.github.io) | 13.0.0 | Imágenes, para pikepdf y reportlab | MIT-CMU |
| [charset-normalizer](https://github.com/jawah/charset_normalizer) | 3.5.2 | Codificaciones de texto, para reportlab | MIT |

pikepdf se apoya en la biblioteca de C++ [QPDF](https://qpdf.sourceforge.io)
(Apache-2.0), que va dentro de sus wheels junto con libjpeg-turbo (IJG,
BSD-3-Clause y Zlib).  Las wheels de Pillow llevan FreeType (FTL o
GPL-2.0-or-later), HarfBuzz (MIT), Little CMS (MIT), libpng (Libpng-2.0),
libjpeg-turbo, LibTIFF (libtiff), libwebp (BSD-3-Clause), OpenJPEG
(BSD-2-Clause), libavif (BSD-2-Clause), Brotli (MIT), la liblzma de XZ
(0BSD), Zstandard (BSD-3-Clause), y libxcb y libXau (MIT).


La ventana
----------

La ventana es opcional (`py-imposition[gui]`).

| Software | Versión | Para qué | Licencia |
|---|---|---|---|
| [PySide6](https://doc.qt.io/qtforpython-6/) (pyside6-essentials) | 6.12.0 | Qt para Python: la ventana | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6 (pyside6-pdf) | 6.12.0.140 | QtPdf: la vista previa del documento | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| shiboken6 | 6.12.0 | El enlace entre Python y Qt | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| [Qt 6](https://www.qt.io) | 6.12 | La biblioteca gráfica, que viene en las wheels de PySide6 | LGPL-3.0-only (los módulos usados) |

py-imposition usa Qt y PySide6 bajo la LGPL, versión 3.


Programas que llama, si están instalados
----------------------------------------

Ninguno es necesario: py-imposition busca cada uno y prescinde de él si no
lo encuentra.

| Software | Para qué | Licencia |
|---|---|---|
| [pdf2iso](https://github.com/nivaca/pdf2iso) (antes py-pdfconform), del mismo autor | Salida PDF/A y PDF/X (`--conform`, *Guardar como*) | GPL-3.0-or-later |
| [Ghostscript](https://www.ghostscript.com), por medio de pdf2iso | La conversión a PDF/A y PDF/X | AGPL-3.0-or-later |
| [veraPDF](https://verapdf.org), por medio de pdf2iso | La validación de los PDF/A | GPL-3.0-or-later OR MPL-2.0 |
| [Fontconfig](https://www.freedesktop.org/wiki/Software/fontconfig/) (`fc-match`) | Encontrar una fuente por su nombre, para los sellos | HPND-sell-variant (tipo MIT) |


Construcción, pruebas y paquetes
--------------------------------

Sirven para hacer y comprobar py-imposition, y no forman parte de lo que se
instala (salvo el Python que lleva la AppImage).

| Software | Para qué | Licencia |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) y uv_build | El entorno, el archivo de bloqueo, la wheel y el paquete de fuentes | Apache-2.0 OR MIT |
| [pytest](https://pytest.org) 9.2.0, con iniconfig, pluggy, Pygments y colorama | Las pruebas | MIT (Pygments: BSD-2-Clause; colorama: BSD-3-Clause) |
| [QPDF](https://qpdf.sourceforge.io) (`qpdf --check`) | Comprobar la estructura de los PDF que hacen las pruebas | Apache-2.0 |
| [Poppler](https://poppler.freedesktop.org) (`pdftotext`) | Leer el texto de las páginas que hacen las pruebas | GPL-2.0-or-later |
| [python-appimage](https://github.com/niess/python-appimage) | El Python 3.15 reubicable que va dentro de la AppImage | GPL-3.0-only (la herramienta); PSF-2.0 (Python) |
| [appimagetool](https://github.com/AppImage/appimagetool) | Hacer la AppImage | MIT |
| [Inkscape](https://inkscape.org) | Dibujar los iconos a partir del SVG (`tools/icons.py`) | GPL-2.0-or-later |
| [RPM](https://rpm.org) y las macros pyproject de Fedora | El paquete RPM | GPL-2.0-or-later |
| [desktop-file-utils](https://www.freedesktop.org/wiki/Software/desktop-file-utils/) | Comprobar el archivo `.desktop` del RPM | GPL-2.0-or-later |
| [Copr](https://copr.fedorainfracloud.org) | Construir los RPM para Fedora | GPL-2.0-or-later |
| [GnuPG](https://gnupg.org) | Firmar los RPM | GPL-3.0-or-later |

El RPM usa los paquetes de PySide6 y de Python de Fedora, bajo las mismas
licencias de arriba.
