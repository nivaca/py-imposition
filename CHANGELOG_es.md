# Registro de cambios

Los cambios notables de py-imposition. Las versiones publicadas, con el
paquete wheel, el paquete fuente, la AppImage y el RPM, están en
[Codeberg](https://codeberg.org/nivaca/py-imposition/releases) y
[GitHub](https://github.com/nivaca/py-imposition/releases); el RPM está
también en el proyecto de Copr nivaca/py-imposition.

## Sin publicar

- `tools/zenodo.py` prepara el depósito de una versión en Zenodo. `collect`
  deja en `dist/zenodo/` el árbol de la etiqueta como
  `py-imposition-VERSIÓN-source.tar.gz`, con su firma, un `SHA256SUMS` del
  depósito, firmado, y la clave pública, y comprueba cada firma con solo esa
  clave (`--packages` añade los archivos de la versión). `upload` lo sube a
  Zenodo como borrador, versión nueva del depósito si ya lo hay, y nunca lo
  publica. `tools/release.py` reúne ahora el depósito después de la etiqueta
  y lo sube como borrador, salvo con `--no-zenodo`. Los metadatos están en
  `.zenodo.json`.

## 0.10.5 — 2026-11-22

- **Cada versión firmada**: además del RPM, cada archivo publicado (el
  paquete wheel, el paquete fuente, la AppImage) va con su firma (`.asc`),
  con `SHA256SUMS` y su firma, y con la clave pública; también la etiqueta
  de la versión va firmada. `tools/release.py` hace siempre el RPM firmado
  (`--no-rpm` lo deja fuera) y comprueba cada firma con la clave publicada
  antes de publicar nada. Los README explican cómo comprobar una descarga.

## 0.10.4 — 2026-11-21

- `docs/OPEN-SOURCE_es.md` (y `docs/OPEN-SOURCE.md`, en inglés) recoge el
  software de código abierto que usa py-imposition, con la licencia de
  cada uno; los README enlazan con él.
- Se necesita Python 3.14 o posterior (antes, 3.15), en
  `requires-python` y los README. Las pruebas pasan con 3.14; la AppImage
  sigue llevando Python 3.15.
- `packaging/build-rpm.sh` copia también el RPM más reciente en `dist/`,
  en lugar de los anteriores que hubiera allí.
- `docs/DESCRIPCIÓN_es.md` se ciñe a seis secciones, cada una de menos de
  4000 caracteres, escritas en tercera persona.

## 0.10.3 — 2026-11-17

- PDF/A y PDF/X los hace pdf2iso, el nuevo nombre de py-pdfconform. El
  programa busca primero `pdf2iso` y sigue encontrando `py-pdfconform`,
  así que una instalación anterior sigue funcionando; una ruta indicada en
  los ajustes se conserva.
- El correo de contacto es nicolasvaughan@proton.me.

## 0.10.2 — 2026-11-17

- **Los medianiles solo mueven las páginas.** En `impose`, el tamaño de
  las páginas sale únicamente del pliego y de los márgenes: un medianil
  más ancho separa las páginas y uno más estrecho las junta, sin cambiar
  su tamaño (antes, cuando ya no quedaba espacio libre por fuera, un
  medianil más ancho encogía las páginas). Avisa cuando los medianiles
  empujan las páginas fuera del pliego.
- La ventana empieza cada sesión con los ajustes por defecto: ya no
  restaura las opciones de las órdenes (incluido el modo básico), las
  preferencias de la barra de herramientas, la secuencia ni los candados
  de los márgenes. Todo ello se mantiene cuando la ventana se reconstruye
  en otro idioma; la disposición, el modo, la vista previa automática, los
  perfiles y los documentos recientes se conservan.

## 0.10.1 — 2026-11-17

- Un margen negativo hace crecer las páginas hasta que se salen del
  pliego esa cantidad por ese lado (cortadas en el borde); antes, los
  márgenes izquierdo y derecho negativos no tenían efecto cuando la altura
  de la página fijaba la escala.
- En los folletos el pliegue queda en la mitad: si los márgenes izquierdo
  y derecho son distintos, cuenta el mayor en los dos lados.

## 0.10 — 2026-11-17

- **Medianiles exactos.** `impose` coloca las páginas juntas, como un
  bloque, con exactamente los medianiles entre ellas, centrado dentro de
  los márgenes; el espacio que sobra va hacia fuera, de modo que los
  márgenes son un mínimo. Antes cada página se centraba en su propio
  lugar, y un medianil más ancho le quitaba espacio a los márgenes.
- Cuando se vuelve a hacer un resultado, la vista previa se queda en la
  página que se estaba viendo.
- **Salida en PDF/A (1b, 2b, 3b) y PDF/X-4** mediante py-pdfconform:
  File > Save as en la ventana (*Archivo ▸ Guardar como*), `--conform` en
  la línea de órdenes, y Settings > py-pdfconform… para indicar dónde está
  (se guarda como `pdfconform` en `config.toml`).
- Se corrigió un fallo al salir de Python en las pruebas (el panel de
  vista previa se eliminaba con Qt todavía en marcha).

## 0.9 — 2026-11-17

- `impose` imprime la información de página (nombre del documento, número
  de pliego, fecha y hora) salvo que se dé `--no-page-info`; en el modo
  básico viene marcada por defecto. Los formularios avanzados manejan las
  opciones de activar y desactivar (`--x` / `--no-x`).
- Modo básico: en Margins y en Page Trim (*Márgenes*, *Recorte de
  páginas*), un candado para Top/Bottom y otro para Left/Right mantienen
  iguales los dos lados. La ventana los recuerda, y un candado cuyos
  valores difieran después de cargar los ajustes se abre.

## 0.8.3 — 2026-11-17

- El modo básico pone en gris el medianil horizontal cuando hay una sola
  fila de páginas (un folleto de 2) y el vertical cuando hay una sola
  columna, y los deja fuera de la línea de órdenes.
- `impose` avisa cuando `--gutter-v` o `--gutter-h` no pueden aplicarse.
- `tools/icons.py` busca Inkscape primero como `$INKSCAPE` o
  `~/AppImages/inkscape.appimage`, luego en el PATH y luego como Flatpak.

## 0.8.2 — 2026-11-14

- Se necesita Python 3.15 o posterior (antes, 3.13). La AppImage lleva
  Python 3.15, y Copr ya no construye para Fedora 44.

## 0.8.1 — 2026-11-14

- Se necesita Python 3.13 o posterior (antes, 3.12).
- Una nueva clave para firmar el RPM (ed25519, válida hasta 2029), fijada
  en `build-rpm.sh`, con su clave pública en `packaging/`.

## 0.8 — 2026-11-12

- **Un solo Guardar.** Save… (*Guardar…*; Ctrl+S, barra de herramientas,
  botón) guarda lo que muestra el panel de la derecha, y ejecuta antes la
  orden si la vista previa no está al día; File > Save the document as
  it is… (*Archivo ▸ Guardar el documento tal como está…*; Ctrl+Shift+S)
  guarda las órdenes aplicadas sin la actual.
- Después de Apply (*Aplicar*), el panel de la derecha muestra el
  documento aplicado en lugar de ejecutar otra vez la misma orden.
- **Cambios sin guardar.** Si hay trabajo sin guardar, la barra de título
  muestra un asterisco, y al cerrar, abrir otro documento o volver al
  original se pregunta antes si se desea guardar.
- Los títulos y mensajes de los diálogos de guardado están traducidos.
- Los README presentan juntas la ventana y la línea de órdenes;
  `docs/DESCRIPTION.md` y `docs/DESCRIPCIÓN_es.md` cuentan cómo se hizo
  el programa.

## 0.7 — 2026-11-12

- `impose`: la encuadernación encolada pliega cuadernillos de cuatro
  pliegos, salvo que `--sheets-per-fold` diga otra cosa, en la línea de
  órdenes y en el modo básico.
- `--page-trim` (y `-top`, `-bottom`, `-left`, `-right`) corta los bordes
  blancos de cada página antes de colocarla; `--enlarge` permite que la
  escala automática también amplíe las páginas hasta llenar sus celdas.
- Márgenes y medianiles pueden ser negativos: las páginas se salen del
  pliego o se solapan, cortadas en el borde o en la mitad del
  solapamiento.
- El modo básico tiene un grupo Page Trim (*Recorte de páginas*) y una
  casilla Enlarge (*Ampliar*).

## 0.6 — 2026-11-11

- File > Open recent (*Archivo ▸ Abrir reciente*) muestra los últimos diez
  documentos abiertos, con Clear the list (*Vaciar la lista*).
- About nombra al autor, con un enlace a su sitio.
- Se quitó el libro de ejemplo; las capturas de pantalla, el README y las
  pruebas usan `numbers-100.pdf`, un documento de 100 páginas numeradas
  con el que se comprueba de un vistazo el orden de las páginas.
- La clave para firmar el RPM está fijada en `build-rpm.sh` y en
  `release.py`, y su clave pública se distribuye en
  `packaging/RPM-GPG-KEY-py-imposition`.

## 0.5.1 — 2026-11-11

- View > Show the original document (*Ver ▸ Mostrar el documento
  original*) muestra u oculta, junto al resultado, la vista previa del
  documento actual. Viene desactivada por defecto, y la elección se guarda
  en `config.toml` (`show_document`).
- Las pruebas de la interfaz gráfica usan una carpeta de configuración
  propia y ya no tocan el `config.toml` del usuario.

## 0.5 — 2026-11-11

- **La orden `impose`**: las imposiciones habituales en una sola orden.
  Hace folletos de 2, de 4 y de 8 (grapados a caballete, o de
  encuadernación encolada en cuadernillos de pliegos doblados), corte y
  apilado, secuencial y paso y repetición, con columnas y filas, borde de
  encuadernación, una o dos caras, medianiles, corrimiento, tamaño del
  soporte, giro y escala automáticos, márgenes, y marcas de corte, de
  sangrado y de registro e información de página.
- **Modo básico en la ventana**: un selector Basic | Advanced. El modo
  básico es un único formulario para `impose`, con perfiles con nombre
  (guardar, guardar como, eliminar, el menú Profiles); las opciones que no
  se aplican aparecen en gris, y al cambiar de unidades se convierten los
  valores. El modo avanzado es la ventana de antes.
- Traducciones al español, pruebas, los README y las capturas de
  pantalla.

## 0.4.1 — 2026-11-11

- **La AppImage contiene todas sus dependencias.** La AppImage de la 0.4
  se construyó mientras pip veía el site-packages del usuario, así que
  dejó fuera pikepdf y Pillow y solo funcionaba donde estuvieran
  instalados. `tools/bundle-appimage.py` instala ahora de forma aislada,
  comprueba que el Python incluido importa todo y ejecuta la AppImage
  terminada con una carpeta personal vacía.
- Los campos vacíos de la ventana muestran un ejemplo de lo que admiten
  ("e.g. 5mm or 1.5cm") en lugar del metavar de la opción.
- La línea de órdenes que hay encima de las opciones usa el color de
  texto del tema, así que se lee bien en los temas oscuros.

## 0.4 — 2026-11-11

### Nuevo

- **La interfaz en español**, en la línea de órdenes y en la ventana
  (`src/py_imposition/locale/es.xml`). `py-imposition interface es|en`
  guarda la elección en `config.toml`, `--interface CODE` la cambia para
  una ejecución, y la ventana tiene Settings > Language of the interface
  (*Ajustes ▸ Idioma de la interfaz*). `README_es.md` y las capturas de
  pantalla en los dos idiomas.
- Una AppImage con su propio Python 3.14, PySide6 y el programa
  (`tools/bundle-appimage.py`).
- Un RPM (`packaging/py-imposition.spec`, `packaging/build-rpm.sh
  [--sign]`) y el proyecto de Copr nivaca/py-imposition.
- `tools/release.py` publica una versión en GitHub, Codeberg y Copr.

### Cambios

- Admite Python 3.12 o posterior, y los pikepdf, reportlab y PySide6 de
  Fedora 44 y 45.
- El README ya no se refiere a otros productos.

## 0.3 — 2026-11-11

- `py-imposition-install` añade la ventana al menú de aplicaciones con el
  icono del programa (Linux, Windows y macOS, sin permisos de
  administrador); `--uninstall` quita solo lo que añadió.
- Un icono, y todos los tamaños que `tools/icons.py` hace a partir de él.
- La ventana cabe en pantallas más pequeñas: su ancho mínimo pasa de unos
  1990 a 1036 píxeles.
- Un libro de ejemplo, `tools/screenshots.py` y capturas de pantalla en
  el README.

## 0.2 — 2026-11-11

- **Una interfaz gráfica**, `py-imposition-gui`, con el extra opcional
  `gui` (PySide6): todas las órdenes, con formularios de opciones hechos a
  partir del analizador de la línea de órdenes; vistas previas del
  documento y del resultado; Apply/Undo para encadenar órdenes; un panel
  de secuencia; información de la imposición, ejecuciones por lotes y
  carpetas vigiladas. Las órdenes se ejecutan en un proceso en segundo
  plano que puede detenerse.
- Funciona `python -m py_imposition`.

## 0.1 — 2026-11-11

- Primera versión: un programa de línea de órdenes que impone páginas de
  PDF para imprimir. Empezó como un generador de folletos de 2
  (encuadernación encolada o grapado a caballete) y creció hasta ser un
  conjunto de subórdenes: folletos, n-up, paso y repetición, unión e
  imposiciones manuales; orden de las páginas (barajar, pares/impares,
  invertir, duplicar, borrar, mover, insertar, dividir); cambios en las
  páginas (recorte y desplazamiento, corrimiento, cambio de tamaño, giro,
  mosaico, sangrado); texto, números, sellos y máscaras; datos variables
  desde CSV; archivos de secuencia, repetición de las órdenes registradas
  en cada salida, y carpetas vigiladas.
- Pruebas con pytest, que se ejecutan en GitHub en cada push.
- GPL-3.0-or-later; `--version`.
