"""Tests of the language of the interface (interface.py, locale/*.xml, config.py):
the translations, and that every text of the program is translated."""

from __future__ import annotations

import argparse
import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from py_imposition import config, interface
from py_imposition.common import COMMANDS
from py_imposition.interface import ntr, tr

SRC = Path(__file__).resolve().parent.parent / "src" / "py_imposition"


def argparse_texts() -> list[str]:
    """argparse's own texts (see interface.translate_argparse): those it gives to _() and ngettext()."""
    texts = []
    for node in ast.walk(ast.parse(inspect.getsource(argparse))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "_" and node.args and isinstance(node.args[0], ast.Constant):
                texts.append(node.args[0].value)
            elif node.func.id == "ngettext":
                texts += [a.value for a in node.args[:2] if isinstance(a, ast.Constant)]
    return texts


# argparse texts that only the other supported Pythons (3.13-3.14) use; they are
# translated too, so the interface is complete on each of them.
OTHER_PYTHONS_ARGPARSE = {
    "%r is not callable", "'required' is an invalid argument for positionals", ".__call__() not defined",
    "cannot have multiple subparser arguments", "cannot merge actions - two groups are named %r",
    "conflicting subparser alias: %s", "conflicting subparser: %s", "dest= is required for options like %r",
    "invalid conflict_resolution value: %r",
    "invalid option string %(option)r: must start with a character %(prefix_chars)r",
    "mutually exclusive arguments must be optional",
}


# argparse texts of the newest Pythons that older ones don't have
NEWER_ARGPARSE = {
    "%(prog)s: warning: %(message)s\n", "argument '%(argument_name)s' is deprecated",
    "command '%(parser_name)s' is deprecated", "option '%(option)s' is deprecated",
    "invalid choice: %(value)r, maybe you meant %(closest)r? (choose from %(choices)s)",
}


def argparse_texts_of_other_pythons() -> list[str]:
    """Texts of the newest argparse (3.15) when the tests run on an older Python."""
    return list(NEWER_ARGPARSE) if sys.version_info < (3, 15) else []


def paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n\n") if p.strip()]


def program_texts() -> set[str]:
    """Every text of the interface: those given to tr(), ntr() and N_() in the program
    (N_ texts and command descriptions are translated paragraph by paragraph), the
    commands' summaries and descriptions, and argparse's own texts."""
    texts: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            name = node.func.id
            args = node.args[:2] if name == "ntr" else node.args[:1]
            if name in ("tr", "N_", "ntr"):
                for a in args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        texts += paragraphs(a.value) if name == "N_" else [a.value]
    for cmd in COMMANDS.values():
        texts.append(cmd.help)
        texts += paragraphs(cmd.description or "")
    texts += argparse_texts()
    return {interface.key_of(t) for t in texts if t.strip()}


@pytest.fixture(autouse=True)
def english_after():
    yield
    interface.use("en")
    interface.translate_argparse()


def test_every_text_is_translated():
    needed = program_texts()
    assert interface.files(), "no translations found"
    for code, path in interface.files().items():
        translated = set(interface.read(path))
        assert sorted(needed - translated) == [], f"{code}: not translated"
        allowed = {interface.key_of(x) for x in OTHER_PYTHONS_ARGPARSE | set(argparse_texts_of_other_pythons())}
        unused = translated - needed - allowed
        assert sorted(unused) == [], f"{code}: not used"


def test_tr():
    assert interface.use("es")
    assert interface.code() == "es"
    assert tr("Preview") == "Vista previa"
    assert tr("  Preview ") == "  Vista previa "  # (the spaces around kept)
    assert tr("Not a text of the program") == "Not a text of the program"
    assert tr("Not a text {x}", x=1) == "Not a text 1"
    assert ntr("Wrote {path} ({count} page)", "Wrote {path} ({count} pages)", 3, path="a.pdf") == \
        "Se escribió a.pdf (3 páginas)"
    interface.use("en")
    assert tr("Preview") == "Preview"


def test_names_and_unknown_languages():
    assert interface.names() == {"en": "English", "es": "Español"}
    assert not interface.use("xx")
    assert interface.code() == "en" and "xx" in interface.error()


def test_bad_files(tmp_path):
    path = tmp_path / "xx.xml"
    for body, message in (("<text><en>a {x}</en><tr>b</tr></text>", "parts"),
                          ("<text><en>a</en><tr>b</tr></text><text><en> a </en><tr>c</tr></text>", "twice"),
                          ("<text><en>a</en></text>", "needs")):
        path.write_text(f'<interface code="xx" name="X">{body}</interface>', encoding="utf-8")
        with pytest.raises(interface.InterfaceError, match=message):
            interface.read(path)


def test_translations_keep_their_parts():
    """Every translation has the same {parts}, and %(...)s / %s placeholders, as its English."""
    import re
    for path in interface.files().values():
        for en, translated in interface.read(path).items():
            for rx in (r"%\(\w+\)[sdr]", r"(?<!%)%[sdr]"):
                assert sorted(re.findall(rx, en)) == sorted(re.findall(rx, translated)), en


def test_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV, str(tmp_path))
    assert config.read() == {}
    assert config.get("interface") == "en"
    path = config.set("interface", "es")
    assert path == tmp_path / "config.toml"
    assert config.get("interface") == "es"
    assert interface.use_configured() == "es"
    assert interface.use_configured("en") == "en"  # (--interface wins)
    path.write_text("[parameters\n")  # broken: the defaults are used
    assert config.get("interface") == "en"


def run_cli(args, tmp_path, env_lang=None):
    import os
    env = dict(os.environ, **{config.ENV: str(tmp_path / "cfg")})
    return subprocess.run([sys.executable, "-m", "py_imposition", *args], capture_output=True, text=True,
                          env=env, cwd=tmp_path)


def test_command_line_in_spanish(tmp_path):
    r = run_cli(["interface", "es"], tmp_path)
    assert r.returncode == 0 and "Español" in r.stdout
    r = run_cli(["booklet", "--help"], tmp_path)
    assert r.stdout.startswith("uso: ") and "encuadernación" in r.stdout
    r = run_cli(["sample", "--count", "2", "-o", "s.pdf"], tmp_path)
    assert r.returncode == 0 and r.stdout.startswith("Se escribió s.pdf (2 páginas)")
    r = run_cli(["shuffle", "--rule", "1 2 Q", "s.pdf"], tmp_path)
    assert r.returncode == 1 and "error:" in r.stderr and "regla" in r.stderr
    r = run_cli(["--interface", "en", "sample", "--count", "1", "-o", "t.pdf"], tmp_path)
    assert r.stdout.startswith("Wrote t.pdf (1 page)")  # (--interface: this run only)
    r = run_cli(["interface"], tmp_path)
    assert "* es" in r.stdout


def test_steps_do_not_record_the_language(tmp_path):
    run_cli(["--interface", "es", "sample", "--count", "2", "-o", "s.pdf"], tmp_path)
    r = run_cli(["text", "--interface", "es", "s.pdf", "-o", "t.pdf"], tmp_path)
    assert r.returncode == 0
    import pikepdf
    from py_imposition.pdfutil import get_history
    assert get_history(pikepdf.open(tmp_path / "t.pdf"))[-1] == ["text"]
