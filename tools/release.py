#!/usr/bin/env python3
"""Publica una versión de py-imposition en GitHub (con gh) y en Codeberg (con tea):
la etiqueta vVERSION (la versión de pyproject.toml), firmada, con el wheel, el paquete
fuente, la AppImage y el RPM firmado adjuntos (el RPM se publica también en Copr), cada
uno con su firma (FILE.asc), con SHA256SUMS y su firma, y con la clave pública que las
comprueba todas.

Todo se firma con la clave del proyecto (SIGNING_KEY de packaging/build-rpm.sh), y cada
firma se comprueba con la clave pública que se publica antes de publicar nada.

    uv run python tools/release.py [--notes TEXT | --notes-file FILE] [--no-rpm | --no-copr]
                                   [--no-build] [--no-appimage] [--no-tests] [--redo]
                                   [--only github|codeberg] [--dry-run] [--yes]

En orden, y cada paso solo si hace falta:

1. comprueba que el repositorio esté en main, sin cambios por confirmar, que las
   versiones coincidan (pyproject.toml, __init__.py y, salvo con --no-rpm, el spec), que
   estén instaladas las herramientas (gh, tea, gpg; salvo con --no-rpm, rpmbuild y
   copr-cli) y que la clave de firma esté en gpg;
2. corre las pruebas (tools/test.py, cada archivo en un proceso propio, todos a la vez),
   salvo con --no-tests;
3. hace el wheel y el paquete fuente (uv build) y la AppImage (tools/bundle-appimage.py)
   en build/release/, salvo con --no-build (entonces usa los que haya en build/release/);
   salvo con --no-rpm, también el RPM firmado en build/rpm/ (packaging/build-rpm.sh
   --sign, que comprueba su firma; gpg pide la frase de contraseña); luego firma cada
   archivo (tools/sign_release.py: FILE.asc, build/release/SHA256SUMS y su .asc) y
   comprueba cada firma solo con la clave pública que se publica
   (packaging/RPM-GPG-KEY-py-imposition);
4. pone en HEAD la etiqueta vVERSION, firmada con la misma clave (git tag --sign), y la
   comprueba (git tag -v). Si la etiqueta ya está en otro commit, se detiene, a menos
   que --redo la mueva;
5. sube main y la etiqueta a cada remoto (origin es GitHub, codeberg es Codeberg; --redo
   sube la etiqueta con --force);
6. en cada forja, hace la versión de la etiqueta, o conserva la que ya haya, y le
   adjunta los archivos, en lugar de los que tengan el mismo nombre;
7. salvo con --no-rpm o --no-copr, envía el RPM fuente firmado a Copr (copr-cli build,
   proyecto nivaca/py-imposition). Copr lo construye para cada Fedora del proyecto y lo firma con
   su propia clave. Cada construcción necesita un version-release mayor que el de la
   anterior, así que antes hay que haber subido la del spec (rpmdev-bumpspec; véase
   packaging/COPR.org).

Hecha la versión, aquí solo queda el RPM (en build/rpm/, y su copia en dist/, donde no
hay nada más): al final se borran build/release/ y build/zenodo/, porque las forjas y
Zenodo ya tienen lo que había en ellas.

Antes de hacer nada, muestra las órdenes que va a correr y pregunta; con --yes no
pregunta, con --dry-run solo las muestra. Las notas de una versión nueva son las de
--notes o --notes-file o, si no, las que hace GitHub a partir de los commits (en
Codeberg, ninguna); una versión que ya existe conserva sus notas.

El depósito para Zenodo se reúne en build/zenodo/ después de la etiqueta (tools/zenodo.py
collect: el árbol de la etiqueta, firmado, con SHA256SUMS y la clave pública), y al final
se sube a Zenodo y se publica (con el token de $ZENODO_TOKEN o del llavero), salvo con
--no-zenodo. Allí queda publicado, con un DOI nuevo; con --zenodo-draft queda como
borrador, para publicarlo a mano.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
TAG = f"v{VERSION}"
TITLE = f"py-imposition {VERSION}"
BRANCH = "main"
# Lo que se publica se hace en build/release/, no en dist/: en local solo se guarda el RPM (en build/rpm/, y su
# copia en dist/, que no tiene nada más)
OUT = "build/release"
WHEEL = f"{OUT}/py_imposition-{VERSION}-py3-none-any.whl"
SDIST = f"{OUT}/py_imposition-{VERSION}.tar.gz"
APPIMAGE = f"{OUT}/py-imposition-{VERSION}-x86_64.AppImage"
SPEC = "packaging/py-imposition.spec"
PUBLIC_KEY = "packaging/RPM-GPG-KEY-py-imposition"  # (the public key published with every release)
SUMS = f"{OUT}/SHA256SUMS"
COPR_PROJECT = "py-imposition"  # (of the copr-cli user, nivaca)
REMOTES = {"github": "origin", "codeberg": "codeberg"}


def zenodo_token() -> bool:
    """Whether tools/zenodo.py finds a Zenodo token, in $ZENODO_TOKEN or
    in the desktop keyring (secret-tool)."""
    tool = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "zenodo.py")
    done = subprocess.run([sys.executable, tool, "check-token"],
                          capture_output=True, check=False)
    return done.returncode == 0


def signing_key() -> str:
    """The project's signing key, as packaging/build-rpm.sh pins it."""
    m = re.search(r'SIGNING_KEY="\$\{SIGNING_KEY:-([0-9A-F]{40})\}"', (ROOT / "packaging/build-rpm.sh").read_text())
    return m.group(1) if m else ""


def init_version() -> str:
    m = re.search(r'^__version__ = "([^"]+)"', (ROOT / "src/py_imposition/__init__.py").read_text(), re.M)
    return m.group(1) if m else ""


def rpm_nvr() -> str:
    """NAME-VERSION-RELEASE of the RPM that build-rpm.sh makes (py-imposition-0.4-1.fc45)."""
    try:
        nvr = subprocess.run(["rpmspec", "-q", "--srpm", "--qf", "%{name}-%{version}-%{release}", SPEC], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("release.py: rpmspec cannot read the spec (sudo dnf install rpm-build)")
    if not nvr.startswith(f"py-imposition-{VERSION}-"):
        sys.exit(f"release.py: {SPEC} is not at version {VERSION} (rpmdev-bumpspec -n {VERSION} ...)")
    return nvr


def rpm() -> str:
    return f"build/rpm/RPMS/noarch/{rpm_nvr()}.noarch.rpm"


def srpm() -> str:
    return f"build/rpm/SRPMS/{rpm_nvr()}.src.rpm"


class Release:
    """The steps, run (or only shown) in order."""

    def __init__(self, args):
        self.args = args
        self.planned: list[tuple[str, list[str]]] = []

    def read(self, *command, check=True) -> str:
        """The output of COMMAND (which only reads, so it runs even with --dry-run)."""
        out = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if check and out.returncode != 0:
            sys.exit(f"release.py: {shlex.join(command)}: {(out.stderr or out.stdout).strip()}")
        return out.stdout.strip() if out.returncode == 0 else ""

    def plan(self, description: str, *command):
        self.planned.append((description, [str(c) for c in command]))

    def run_plan(self):
        print(f"Releasing {TAG}:")
        for description, command in self.planned:
            print(f"\n  # {description}\n  {shlex.join(command)}")
        print()
        if self.args.dry_run:
            return
        if not self.args.yes:
            answer = input("Run these commands? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "s", "sí", "si"):
                sys.exit("Nothing done.")
        for description, command in self.planned:
            print(f"\n==> {description}", flush=True)
            if subprocess.run(command, cwd=ROOT).returncode != 0:
                sys.exit(f"release.py: failed: {shlex.join(command)}\nThe steps before it were done; after fixing "
                         "the cause, run the script again (with --redo if the tag was already moved).")
        print(f"\nReleased {TAG}.")

    # -------------------------------------------------------------- checks

    def check(self):
        tools = ["git", "uv"] + [t for t, f in (("gh", "github"), ("tea", "codeberg")) if f in self.forges]
        tools += ["gpg"]
        if self.args.rpm:
            tools += ["rpmbuild", "rpmsign"] + ([] if self.args.no_copr else ["copr-cli"])
        for tool in tools:
            if not shutil.which(tool):
                sys.exit(f"release.py: {tool} is not installed")
        # Todo se firma, siempre: sin la clave no hay versión.
        key = signing_key()
        have = subprocess.run(["gpg", "--batch", "--list-secret-keys", key], capture_output=True).returncode
        if not key or have != 0:
            sys.exit(f"release.py: the signing key {key or '(none pinned)'} is not in this machine's gpg "
                     "keyring; import it first (see packaging/COPR.org)")
        if not (ROOT / PUBLIC_KEY).is_file():
            sys.exit(f"release.py: there is no {PUBLIC_KEY}, the public key published with the release")
        if init_version() != VERSION:
            sys.exit(f"release.py: pyproject.toml says {VERSION}, src/py_imposition/__init__.py says "
                     f"{init_version()}")
        branch = self.read("git", "rev-parse", "--abbrev-ref", "HEAD")
        if branch != BRANCH:
            sys.exit(f"release.py: on branch {branch}, not {BRANCH}")
        if self.read("git", "status", "--porcelain"):
            message = "there are changes not committed (see git status)"
            if not self.args.dry_run:
                sys.exit(f"release.py: {message}")
            print(f"release.py: (dry run) {message}", file=sys.stderr)

    def repos(self) -> dict[str, str]:
        """{forge: owner/name}, from the push addresses of the remotes."""
        found = {}
        for forge in self.forges:
            url = self.read("git", "remote", "get-url", "--push", REMOTES[forge], check=False)
            m = re.search(r"(github\.com|codeberg\.org)[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
            if not m or ("github" in m[1]) != (forge == "github"):
                sys.exit(f"release.py: the remote {REMOTES[forge]} does not push to {forge} (git remote -v)")
            found[forge] = m[2]
        return found

    # -------------------------------------------------------------- steps

    def tests(self):
        if not self.args.no_tests:
            # (cada archivo de pruebas en un proceso propio, todos a la vez: tools/test.py)
            self.plan("Run the tests", "uv", "run", "--all-extras", "python", "tools/test.py")

    def build(self):
        if self.args.no_build:
            for f in self.files:
                if not (ROOT / f).is_file():
                    sys.exit(f"release.py: there is no {f} (leave out --no-build to make it)")
            return
        (ROOT / OUT).mkdir(parents=True, exist_ok=True)
        self.plan("Make the wheel and the source package", "uv", "build", "--out-dir", OUT)
        if APPIMAGE in self.files:
            self.plan("Make the AppImage", "uv", "run", "python", "tools/bundle-appimage.py", "--output", OUT)
        if self.args.rpm:
            self.plan("Make the signed RPM", "packaging/build-rpm.sh", "--sign")

    def sign(self):
        """Every file published signed (FILE.asc), with SHA256SUMS and its signature, and each signature checked
        with only the public key published."""
        signed = [f for f in self.files if f != PUBLIC_KEY]
        self.plan("Sign the files, and check each signature with the published key", sys.executable,
                  "tools/sign_release.py", "--key", signing_key(), "--public", PUBLIC_KEY, "--sums", SUMS, *signed)
        self.files = signed + [f"{f}.asc" for f in signed] + [SUMS, f"{SUMS}.asc", PUBLIC_KEY]

    def tag(self):
        head = self.read("git", "rev-parse", "HEAD")
        tagged = self.read("git", "rev-parse", "--verify", "--quiet", f"refs/tags/{TAG}^{{commit}}", check=False)
        if tagged and tagged != head and not self.args.redo:
            sys.exit(f"release.py: {TAG} is already the tag of {tagged[:7]}, not of HEAD ({head[:7]}); --redo "
                     "moves it (and replaces the files of the releases)")
        if tagged != head:
            self.plan("Move the tag to HEAD, signed" if tagged else "Tag HEAD, signed", "git", "tag", "--force",
                      "--sign", "--local-user", signing_key(), TAG, "--message", TITLE)
            self.plan("Check the signature of the tag", "git", "tag", "--verify", TAG)
        for forge in self.forges:
            remote = REMOTES[forge]
            self.plan(f"Push {BRANCH} to {remote}", "git", "push", remote, BRANCH)
            if self.args.redo:
                self.plan(f"Push the tag to {remote} (replacing it)", "git", "push", "--force", remote,
                          f"refs/tags/{TAG}")
                continue
            there = self.read("git", "ls-remote", "--tags", remote, f"refs/tags/{TAG}^{{}}", check=False)
            on_remote = there.split()[0] if there else ""
            if on_remote == head:
                continue
            if on_remote:
                sys.exit(f"release.py: on {remote}, {TAG} is the tag of {on_remote[:7]}; --redo moves it")
            self.plan(f"Push the tag to {remote}", "git", "push", remote, f"refs/tags/{TAG}")

    def notes(self, github: bool) -> list[str]:
        if self.args.notes_file:
            return ["--notes-file" if github else "--note-file", self.args.notes_file]
        if self.args.notes:
            return ["--notes" if github else "--note", self.args.notes]
        return ["--generate-notes"] if github else []

    def github(self, repo: str):
        exists = subprocess.run(["gh", "release", "view", TAG, "--repo", repo], cwd=ROOT,
                                capture_output=True).returncode == 0
        if exists:
            self.plan("GitHub: attach the files to the release (replacing those there)", "gh", "release", "upload",
                      TAG, *self.files, "--clobber", "--repo", repo)
        else:
            self.plan("GitHub: make the release", "gh", "release", "create", TAG, *self.files, "--title", TITLE,
                      "--verify-tag", *self.notes(True), "--repo", repo)

    def codeberg(self, repo: str):
        where = ["--repo", repo, "--login", self.args.tea_login]
        releases = self.tea_json("releases", "ls", "--limit", "50", *where)
        if any(TAG in (r.get("tagname"), r.get("tag")) for r in releases):
            names = {a.get("name") for a in self.tea_json("releases", "assets", "ls", TAG, *where)}
            old = [Path(f).name for f in self.files if Path(f).name in names]
            if old:
                self.plan("Codeberg: remove the files of the same name (tea cannot replace them)", "tea",
                          "releases", "assets", "delete", TAG, *old, "--confirm", *where)
            self.plan("Codeberg: attach the files to the release", "tea", "releases", "assets", "create", TAG,
                      *self.files, *where)
        else:
            assets = [a for f in self.files for a in ("--asset", f)]
            self.plan("Codeberg: make the release", "tea", "releases", "create", "--tag", TAG, "--title", TITLE,
                      *self.notes(False), *assets, *where)

    def tea_json(self, *command) -> list[dict]:
        """The rows tea gives in JSON, with its keys made plain ("tag-_name" is tagname)."""
        out = self.read("tea", *command, "--output", "json")
        try:
            rows = json.loads(out or "[]")
        except ValueError:
            sys.exit(f"release.py: tea {' '.join(command)}: not JSON: {out[:200]}")
        return [{re.sub("[^a-z]", "", k.lower()): v for k, v in r.items()} for r in rows]

    def copr(self):
        if self.args.no_build and not (ROOT / srpm()).is_file():
            sys.exit(f"release.py: there is no {srpm()} (leave out --no-build to make it)")
        self.plan(f"Copr: build the RPM (project {COPR_PROJECT})", "copr-cli", "build", COPR_PROJECT, srpm())

    def zenodo_collect(self):
        """The deposit of the release for Zenodo, in build/zenodo/ (tools/zenodo.py): the tree of the tag, signed,
        with SHA256SUMS and the public key, each signature checked with only that key."""
        self.plan("Zenodo: collect the deposit in build/zenodo/", sys.executable, "tools/zenodo.py", "collect",
                  "--tag", TAG)

    def zenodo_upload(self):
        """Unless --no-zenodo, build/zenodo/ uploaded to Zenodo and published (with
        --zenodo-draft, only as a draft, published there by hand)."""
        if self.args.no_zenodo:
            return
        # (sin token se para aquí, antes de hacer nada, y no al final de la versión)
        if not zenodo_token() and not self.args.dry_run:
            sys.exit("release.py: the upload to Zenodo needs a token (see tools/zenodo.py check-token); "
                     "--no-zenodo leaves it out")
        publish = [] if self.args.zenodo_draft else ["--publish"]
        what = " as a draft (not published)" if self.args.zenodo_draft else " and publish it"
        self.plan("Zenodo: upload the deposit" + what, sys.executable, "tools/zenodo.py", "upload", *publish)

    def __call__(self):
        a = self.args
        self.forges = [a.only] if a.only else ["github", "codeberg"]
        a.rpm = not a.no_rpm  # (el RPM firmado, siempre, salvo con --no-rpm)
        self.files = [WHEEL, SDIST] + ([] if a.no_appimage else [APPIMAGE])
        if a.rpm:
            self.files += [rpm()]
        self.files += [PUBLIC_KEY]
        self.check()
        repos = self.repos()
        self.tests()
        self.build()
        self.sign()
        self.tag()
        self.zenodo_collect()
        for forge in self.forges:
            getattr(self, forge)(repos[forge])
        if a.rpm and not a.no_copr:
            self.copr()
        self.zenodo_upload()
        self.clean_up()
        self.run_plan()

    def clean_up(self):
        """Once all is published: only the RPM stays here (build/rpm/, and its copy in dist/); the rest is on the
        forges and on Zenodo."""
        self.plan("Delete what was published from build/ (only the RPM stays)", "rm", "-rf", OUT, "build/zenodo")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools/release.py",
                                     description=f"Publish {TAG} on GitHub and Codeberg, with the wheel, the source "
                                                 "package, the AppImage and the RPM (also on Copr), all signed.")
    notes = parser.add_mutually_exclusive_group()
    notes.add_argument("--notes", metavar="TEXT", help="the notes of a new release")
    notes.add_argument("--notes-file", metavar="FILE", help="the notes of a new release, from FILE")
    parser.add_argument("--rpm", action="store_true",
                        help="(the signed RPM, and a Copr build of it, are made always now: kept for older scripts)")
    parser.add_argument("--no-rpm", action="store_true", help="without the RPM (nor its Copr build)")
    parser.add_argument("--no-copr", action="store_true", help="don't send the RPM to Copr")
    parser.add_argument("--no-build", action="store_true",
                        help="use the files in build/release/ (and build/rpm/) as they are")
    parser.add_argument("--no-appimage", action="store_true", help="without the AppImage")
    parser.add_argument("--no-tests", action="store_true", help="don't run the tests first")
    parser.add_argument("--redo", action="store_true",
                        help=f"move {TAG} to HEAD if it is on another commit (here and on the remotes), and "
                             "replace the files of the releases")
    parser.add_argument("--only", choices=("github", "codeberg"), help="publish on one forge only")
    parser.add_argument("--tea-login", default="codeberg", help="the login of tea for Codeberg (default: codeberg)")
    parser.add_argument("--no-zenodo", action="store_true",
                        help="don't upload build/zenodo/ to Zenodo (by default it is uploaded and "
                             "published, with the token in $ZENODO_TOKEN or the keyring)")
    parser.add_argument("--zenodo-draft", action="store_true",
                        help="upload it to Zenodo as a draft, not published")
    parser.add_argument("--zenodo", action="store_true",
                        help="(the upload to Zenodo is made always now, unless --no-zenodo: kept "
                             "for older scripts)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only show the commands")
    parser.add_argument("-y", "--yes", action="store_true", help="don't ask before running them")
    args = parser.parse_args(argv)
    if args.notes_file:
        args.notes_file = str(Path(args.notes_file).resolve())
    Release(args)()


if __name__ == "__main__":
    main()
