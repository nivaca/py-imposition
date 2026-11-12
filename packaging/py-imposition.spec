# py-imposition, a PDF imposition toolkit.
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed WITHOUT ANY
# WARRANTY; see the LICENSE file, or <https://www.gnu.org/licenses/>.
#
# Build with packaging/build-rpm.sh, which makes the source tarball.

Name:           py-imposition
Version:        0.8
Release:        1%{?dist}
Summary:        PDF imposition toolkit: booklets, n-up, step and repeat and more

License:        GPL-3.0-or-later
URL:            https://github.com/nivaca/py-imposition
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
# For %%check: the tests run the commands and the window (headless), and
# read the results with pdftotext and qpdf.
BuildRequires:  python3-pytest
BuildRequires:  python3-pyside6
BuildRequires:  poppler-utils
BuildRequires:  qpdf

# pikepdf and reportlab come from the package's metadata (pyproject.toml).
# The window: Fedora's PySide6 (the "gui" extra names the PyPI wheels).
Requires:       python3-pyside6
Requires:       hicolor-icon-theme

%description
py-imposition imposes PDF pages for printing: booklets (saddle-stitched,
perfect bound, cut stacks), n-up and step and repeat with margins, crop marks
and backgrounds, page shuffling by rules, trimming and shifting, creep,
bleeds, page numbers and stamps, masking tape, manual imposition, variable
data merge, split/merge (partials), automation sequences and hot folders.

It comes as a command line (py-imposition) and a window with live previews
(py-imposition-gui), in English or Spanish.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l py_imposition
# The package has its own menu entry; py-imposition-install (for pip/uv
# installations) would add a second one.
rm %{buildroot}%{_bindir}/py-imposition-install
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/py-imposition.desktop
install -d %{buildroot}%{_datadir}/icons
cp -pr src/py_imposition/icons/linux/hicolor %{buildroot}%{_datadir}/icons/

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/py-imposition.desktop
%pyproject_check_import -e 'py_imposition.gui*'
# The whole test suite, on the installed package, with no settings of the
# builder's and the window drawn offscreen.
export HOME="$PWD/check-home" PY_IMPOSITION_CONFIG="$PWD/check-home/config" QT_QPA_PLATFORM=offscreen
%pytest -q tests
%{py3_test_envvars} %{buildroot}%{_bindir}/py-imposition --version | grep -q '%{version}'

%files -f %{pyproject_files}
%doc README.md README_es.md
%{_bindir}/py-imposition
%{_bindir}/py-imposition-gui
%{_datadir}/applications/py-imposition.desktop
%{_datadir}/icons/hicolor/*/apps/py-imposition.*

%changelog
* Thu Nov 12 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.8-1
- The window: one Save, and a warning about unsaved changes

* Thu Nov 12 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.7-1
- impose: perfect binding in stacks of four sheets per fold by default
- impose: page trim, enlarge, and negative margins and gutters

* Thu Nov 12 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.6-1
- Open recent documents; the author in About; numbers-100.pdf as the only
  example; signing key pinned and shipped

* Thu Nov 12 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.5.1-1
- View > Show the original document: the document's preview is optional, off by
  default, and kept in config.toml

* Wed Nov 11 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.5-1
- Basic mode in the window: one imposition form (layout, profiles, binding,
  gutters, paper, margins, printer marks); a Basic | Advanced switch
- The impose command: 2-, 4- and 8-up booklets, cut stacks, sequential and
  step and repeat in one step, with trim, bleed and registration marks and
  page information

* Wed Nov 11 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.4.1-1
- The AppImage includes pikepdf and Pillow (0.4's did not run without them
  installed)
- Empty fields in the window show an example of what they take, and the
  command line above the options is readable in dark themes
- Signed with a new key (236EF043AB7A4434A05CA4ECB5549099FC0D6464)

* Wed Nov 11 2026 Nicolas Vaughan <nivaca@fastmail.com> - 0.4-1
- First package: the command line and the window, in English or Spanish,
  with a menu entry that also opens PDF files
