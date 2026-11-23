# py-imposition 0.10.4: descripción

## Análisis

py-imposition impone páginas PDF para imprimirlas: coloca las páginas de un documento en pliegos más grandes, en el orden y la posición que necesitan el impresor, la plegadora y el encuadernador, de modo que, una vez impresos, plegados, cortados y encuadernados los pliegos, las páginas queden en orden. Hace folletos (grapados a caballete, encolados, de corte y apilado), disposiciones n-up y de paso y repetición, y además reordena, recorta, desplaza, gira y cambia de tamaño las páginas, añade sangrados, corrimiento, marcas de corte, números de página, sellos y cinta de enmascarar, combina datos variables y ejecuta secuencias de órdenes y carpetas vigiladas. Lo hizo Nicolas Vaughan en 2026.

Tiene una ventana, con un modo básico para las imposiciones habituales y un modo avanzado con todas las órdenes, y una línea de órdenes con las mismas órdenes, en inglés o en español. py-imposition es software libre, bajo la Licencia Pública General de GNU, versión 3 o posterior.

Los requisitos quedaron claros desde el principio. Lo primero era no estropear el documento: las páginas tenían que llegar al pliego tal como son, con su texto vectorial, sus fuentes y sus imágenes, sin rasterizarlas ni reescribirlas, y el original no debía cambiar nunca. Lo segundo, que cada herramienta fuera una orden que lee un PDF y escribe otro, de modo que las órdenes pudieran encadenarse, guardarse como secuencias y repetirse sobre otros documentos.

Además, el programa tenía que servirle a cualquiera: a quien solo quiere un folleto, con un formulario sencillo como el de cualquier diálogo de imposición; a quien necesita todas las herramientas, con vistas previas y sin tener que aprender la línea de órdenes; y a quien quiere automatizar, con la línea de órdenes, las secuencias y las carpetas vigiladas. Debía instalarse fácilmente en Linux, recordar sus ajustes de una sesión a otra y estar en inglés y en español.

## Diseño

El programa está dividido en módulos pequeños, cada uno con un solo trabajo. `pdfutil.py` es la base: las cajas de página (de recorte y de sangrado), la colocación de páginas como Form XObjects, las marcas de corte y la historia que cada orden deja en el PDF. `units.py` y `pagesel.py` leen las longitudes con unidades (`5mm`, `1.5cm`, `3/8in`), los tamaños de papel (`a4`, `21x29.7cm`) y los intervalos de páginas (`1-4,7`, `3..LAST`).

Las órdenes están agrupadas por tarea. `impose.py` coloca páginas en pliegos (folleto, n-up, paso y repetición, unir dos páginas) y `manual.py` lo hace según un archivo de disposición; `simple.py` tiene `impose`, todas las imposiciones habituales en una sola orden. `shuffle.py` reordena las páginas según reglas; `pagetools.py` recorta, desplaza, gira, cambia de tamaño, duplica, elimina, mueve y divide en mosaico; `bleed.py`, `insert.py` y `split.py` definen sangrados, insertan páginas y dividen el documento en partes. `stamp.py` pega texto, números, otras páginas y cinta de enmascarar, y los despega; `datamerge.py` combina datos variables; `info.py` informa sobre una imposición, y `sequence.py` ejecuta secuencias, repite la historia de un documento y vigila carpetas.

Todas las órdenes comparten una estructura (`common.py`): un decorador registra cada orden con sus opciones, y a partir de esas definiciones se construyen tanto la línea de órdenes (`runner.py`) como la ventana. La ventana está en `gui/`: `window.py` (la ventana principal, sus menús, el panel Secuencia y la ejecución de procesos), `basic.py` (el modo básico y sus perfiles), `forms.py` (los formularios de opciones, generados a partir de la línea de órdenes) y `preview.py` (el visor de PDF).

De los idiomas se ocupa `interface.py`, con `tr()`, que traduce cada texto del programa a partir de `locale/es.xml`. `config.py` lee y escribe el archivo de configuración, `config.toml` (el idioma de la interfaz y si la ventana muestra el documento original), e `install.py` añade la entrada del menú de aplicaciones en Linux, Windows y macOS.

Fuera del paquete quedan las herramientas: `tools/screenshots.py` hace las capturas de los README, `tools/icons.py` hace todos los iconos a partir de un SVG, `tools/bundle-appimage.py` arma la AppImage, `packaging/build-rpm.sh` el RPM firmado, y `tools/release.py` publica cada versión.

## Implementación

Está escrito en Python 3.14 o superior, con dos bibliotecas: pikepdf (basada en QPDF), que lee y escribe los PDF, y reportlab, para el texto y las fuentes. La ventana usa PySide6 (Qt 6), con QtPdf para las vistas previas. Son 28 módulos, unas 7800 líneas, y 30 órdenes.

Ninguna página se rasteriza ni se reescribe. Cada página de origen se convierte en un Form XObject, un trozo independiente de contenido PDF, que el pliego dibuja con una matriz que la mueve, la escala y la gira, dentro de un rectángulo de recorte. Así las páginas conservan su texto, sus fuentes y sus imágenes, y una página colocada muchas veces se guarda una sola vez. Lo que se alinea en el pliego es la caja de recorte, y el sangrado se ve más allá, sin invadir la página vecina. Las marcas de corte se omiten donde caerían sobre una página.

El orden de las páginas de los folletos y de `shuffle` se escribe como reglas, por ejemplo `8 1 5* 4* 2 7 3* 6*` (con `*` para una página cabeza abajo), que se repiten a lo largo del documento. Lo que el programa pega en una página queda etiquetado como contenido marcado, de modo que `peel` puede despegarlo después. Cada orden escribe su línea de órdenes en la información del documento PDF: `replay` la lee y hace lo mismo con otro documento, y `run` ejecuta una secuencia guardada.

### La ventana

Los formularios se generan a partir de las mismas definiciones de `argparse` que la línea de órdenes: cada opción tiene su campo, con el mismo nombre, el mismo valor por defecto y la misma ayuda, y una opción nueva aparece sola en la ventana. La ventana no impone nada por sí misma. Ejecuta la línea de órdenes en un proceso aparte (QProcess), así que nunca se congela y un trabajo largo se puede detener. *Aplicar* convierte el resultado en el documento actual, para encadenar órdenes, y el panel Secuencia reúne los pasos y los ejecuta sobre un lote de archivos.

El modo básico es un único formulario, con perfiles con nombre, que ejecuta la orden `impose` y muestra su línea de órdenes.

### Llenar el pliego

`impose` tiene tres maneras de que el contenido ocupe más del pliego: `--page-trim` recorta los bordes blancos de cada página; `--enlarge` permite que las páginas crezcan hasta llenar su lugar; y los márgenes y los medianiles pueden ser negativos. Desde la versión 0.10 las páginas van juntas, como un bloque, con exactamente los medianiles entre ellas, y el bloque se centra dentro de los márgenes; en un folleto, el pliegue cae en la mitad del medianil. El tamaño de las páginas sale del pliego y de los márgenes, y un medianil solo las mueve.

### PDF/A, PDF/X e idiomas

El resultado puede guardarse como PDF/A o como PDF/X-4 (`--conform`). No lo convierte py-imposition, sino pdf2iso, otro programa del autor, con Ghostscript; sin pdf2iso, todo lo demás funciona. Cada texto del programa, incluidos los mensajes propios de `argparse`, pasa por `tr()`, y las traducciones están en un solo archivo XML, `locale/es.xml`.

### Distribución

La AppImage lleva su propio Python, Qt y bibliotecas, y funciona en casi cualquier Linux. Desde la 0.4.1 sus paquetes se instalan aislados (la primera encontraba pikepdf entre los paquetes de Python del usuario, y solo funcionaba en el equipo donde se hizo); antes de publicarla se comprueba que cada módulo se importe desde dentro y se arranca una vez con una carpeta personal vacía. Para Fedora hay un RPM, hecho con los paquetes de Fedora, que corre las pruebas al construirse; va firmado con la clave del autor, y Copr lo publica para cada versión de Fedora.

El código está en un repositorio git publicado en GitHub (https://github.com/nivaca/py-imposition) y en Codeberg (https://codeberg.org/nivaca/py-imposition). Cada versión se publica con `tools/release.py`, que corre las pruebas, hace todos los paquetes, etiqueta la versión, la sube a las dos forjas y envía el RPM a Copr.

## Validación

Hay 121 pruebas automáticas (`tests/`), que se corren con `uv run pytest`. Comprueban el orden de las páginas con ejemplos resueltos de imposiciones habituales, ejecutan cada orden de principio a fin sobre documentos generados y leen los resultados con pdftotext y `qpdf --check`, e imponen el documento de ejemplo, cuyas páginas muestran cada una su número. La ventana se prueba sin pantalla, con la plataforma offscreen de Qt: los formularios, el modo básico y sus perfiles, las vistas previas, *Aplicar* y *Deshacer*, los documentos recientes y el idioma. Otras pruebas comprueban que cada texto tenga su traducción y que no sobre ninguna, el instalador del menú en cada sistema, los archivos de empaquetado y la clave de firma, y la firma de una versión (con una clave hecha en la prueba).

Las pruebas corren con cada push en GitHub Actions, y otra vez dentro de cada construcción del RPM en Copr, con el Python de Fedora (3.15). Las capturas de los README se rehacen con cada cambio de la ventana y se revisan a ojo.

## Plataforma

Funciona en Linux. La AppImage corre en cualquier distribución con glibc 2.34 o posterior (Ubuntu 22.04, Debian 12, Fedora 35 y posteriores) y no necesita nada más; en Fedora, el paquete de Copr se instala con `dnf` y se actualiza con el sistema. Desde el código fuente necesita Python 3.14 o superior, pikepdf y reportlab, y para la ventana PySide6 (unos 250 MB).

Al ser Python y Qt, debería funcionar también en Windows y macOS desde el código fuente, y el instalador del menú los contempla (un acceso en el menú Inicio, una pequeña aplicación en `~/Applications`), pero allí solo se ha probado con las pruebas automáticas. No necesita internet ni permisos de administrador.

## Ambiente

Fue desarrollado en Fedora Linux 45 con KDE Plasma, con Python 3.15 y uv, y con git, con repositorios en GitHub y Codeberg. Los iconos se dibujan con Inkscape, los paquetes de Fedora se construyen en Copr y las pruebas corren también en GitHub Actions. Cada versión se firma con la clave del autor: el RPM, cada archivo publicado (con su firma `.asc`), las sumas `SHA256SUMS` y la etiqueta; antes de publicar, `tools/release.py` comprueba cada firma con la clave pública que va con la versión.

Para usarlo basta descargar la AppImage de las versiones publicadas y ejecutarla, o instalar el paquete de Fedora (`sudo dnf copr enable nivaca/py-imposition` y `sudo dnf install py-imposition`), que añade la entrada del menú. Desde el código fuente, `uv sync --extra gui` lo prepara y `py-imposition-install` añade el acceso al menú de aplicaciones, con su icono. Los ajustes quedan en la carpeta de configuración del usuario (`~/.config/py-imposition/` en Linux).

El software de código abierto que usa, con la licencia de cada uno, está en `docs/OPEN-SOURCE_es.md`.
