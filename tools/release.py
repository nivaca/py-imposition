#!/usr/bin/env python3
"""Publish a release of py-imposition on GitHub (with gh) and Codeberg (with
tea): the tag vVERSION (the version of pyproject.toml), with the wheel, the
source package and the AppImage attached, and (--rpm) the signed RPM and its
public key, also published on Copr.

    uv run python tools/release.py [--notes TEXT | --notes-file FILE] [--rpm [--no-copr]]
                                   [--no-build] [--no-appimage] [--no-tests] [--redo]
                                   [--only github|codeberg] [--dry-run] [--yes]

In order, each step only if it is needed:

1. checks that the repository is on main, with nothing left to commit, that
   the versions agree (pyproject.toml, __init__.py and, with --rpm, the spec)
   and that the tools are installed (gh, tea; with --rpm, rpmbuild and
   copr-cli);
2. runs the tests (unless --no-tests);
3. makes the wheel and the source package (uv build) and the AppImage
   (tools/bundle-appimage.py) in dist/, unless --no-build (then those in
   dist/ are used); with --rpm, also the signed RPM and its public key in
   build/rpm/ (packaging/build-rpm.sh --sign; gpg asks for the passphrase);
4. tags HEAD as vVERSION. If the tag is already on another commit, it stops,
   unless --redo moves it;
5. pushes main and the tag to each remote (origin is GitHub, codeberg is
   Codeberg; --redo pushes the tag with --force);
6. on each forge, makes the release of the tag, or keeps the one there is,
   and attaches the files to it, replacing those of the same name;
7. with --rpm, sends the signed source RPM to Copr (copr-cli build, project
   nivaca/py-imposition), unless --no-copr. Copr builds it for each Fedora of
   the project and signs it with its own key. Each build needs a higher
   version-release than the last, so the spec must have been bumped
   (rpmdev-bumpspec; see packaging/COPR.org).

Before doing anything, it shows the commands it will run and asks; --yes
doesn't ask, --dry-run only shows them. The notes of a new release are
--notes, --notes-file, or else made by GitHub from the commits (on Codeberg,
none); a release that is there keeps its notes.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
TAG = f"v{VERSION}"
TITLE = f"py-imposition {VERSION}"
BRANCH = "main"
WHEEL = f"dist/py_imposition-{VERSION}-py3-none-any.whl"
SDIST = f"dist/py_imposition-{VERSION}.tar.gz"
APPIMAGE = f"dist/py-imposition-{VERSION}-x86_64.AppImage"
SPEC = "packaging/py-imposition.spec"
RPM_KEY = "build/rpm/RPM-GPG-KEY-py-imposition"
COPR_PROJECT = "py-imposition"  # (of the copr-cli user, nivaca)
REMOTES = {"github": "origin", "codeberg": "codeberg"}


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
        if self.args.rpm:
            tools += ["rpmbuild", "rpmsign"] + ([] if self.args.no_copr else ["copr-cli"])
        for tool in tools:
            if not shutil.which(tool):
                sys.exit(f"release.py: {tool} is not installed")
        if self.args.rpm:
            key = signing_key()
            have = subprocess.run(["gpg", "--batch", "--list-secret-keys", key], capture_output=True).returncode
            if not key or have != 0:
                sys.exit(f"release.py: the signing key {key or '(none pinned)'} is not in this machine's gpg "
                         "keyring; import it first (see packaging/COPR.org)")
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
            self.plan("Run the tests", "uv", "run", "--all-extras", "pytest", "-q")

    def build(self):
        if self.args.no_build:
            for f in self.files:
                if not (ROOT / f).is_file():
                    sys.exit(f"release.py: there is no {f} (leave out --no-build to make it)")
            return
        self.plan("Make the wheel and the source package", "uv", "build", "--out-dir", "dist")
        if APPIMAGE in self.files:
            self.plan("Make the AppImage", "uv", "run", "python", "tools/bundle-appimage.py")
        if self.args.rpm:
            self.plan("Make the signed RPM", "packaging/build-rpm.sh", "--sign")

    def tag(self):
        head = self.read("git", "rev-parse", "HEAD")
        tagged = self.read("git", "rev-parse", "--verify", "--quiet", f"refs/tags/{TAG}^{{commit}}", check=False)
        if tagged and tagged != head and not self.args.redo:
            sys.exit(f"release.py: {TAG} is already the tag of {tagged[:7]}, not of HEAD ({head[:7]}); --redo "
                     "moves it (and replaces the files of the releases)")
        if tagged != head:
            self.plan("Move the tag to HEAD" if tagged else "Tag HEAD", "git", "tag", "--force", "--annotate", TAG,
                      "--message", TITLE)
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

    def __call__(self):
        a = self.args
        self.forges = [a.only] if a.only else ["github", "codeberg"]
        self.files = [WHEEL, SDIST] + ([] if a.no_appimage else [APPIMAGE])
        if a.rpm:
            self.files += [rpm(), RPM_KEY]
        self.check()
        repos = self.repos()
        self.tests()
        self.build()
        self.tag()
        for forge in self.forges:
            getattr(self, forge)(repos[forge])
        if a.rpm and not a.no_copr:
            self.copr()
        self.run_plan()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools/release.py",
                                     description=f"Publish {TAG} on GitHub and Codeberg, with the wheel, the source "
                                                 "package, the AppImage and (--rpm) the signed RPM, also on Copr.")
    notes = parser.add_mutually_exclusive_group()
    notes.add_argument("--notes", metavar="TEXT", help="the notes of a new release")
    notes.add_argument("--notes-file", metavar="FILE", help="the notes of a new release, from FILE")
    parser.add_argument("--rpm", action="store_true",
                        help="also the signed RPM and its public key (packaging/build-rpm.sh --sign), and a Copr "
                             "build of it")
    parser.add_argument("--no-copr", action="store_true", help="with --rpm, don't send it to Copr")
    parser.add_argument("--no-build", action="store_true", help="use the files in dist/ (and build/rpm/) as they are")
    parser.add_argument("--no-appimage", action="store_true", help="without the AppImage")
    parser.add_argument("--no-tests", action="store_true", help="don't run the tests first")
    parser.add_argument("--redo", action="store_true",
                        help=f"move {TAG} to HEAD if it is on another commit (here and on the remotes), and "
                             "replace the files of the releases")
    parser.add_argument("--only", choices=("github", "codeberg"), help="publish on one forge only")
    parser.add_argument("--tea-login", default="codeberg", help="the login of tea for Codeberg (default: codeberg)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only show the commands")
    parser.add_argument("-y", "--yes", action="store_true", help="don't ask before running them")
    args = parser.parse_args(argv)
    if args.notes_file:
        args.notes_file = str(Path(args.notes_file).resolve())
    Release(args)()


if __name__ == "__main__":
    main()
