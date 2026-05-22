from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from logseq.parser import parse
from logseq.render import render_page


def _render_to_text(page) -> str:
    """Render a page and capture the plain (no-ANSI) text output."""
    from io import StringIO

    from rich.console import Console

    console = Console(file=StringIO(), force_terminal=False, width=200)
    console.print(render_page(page))
    return console.file.getvalue()


def test_render_includes_title_and_type_tag() -> None:
    page = parse("- hello\n", "/tmp/Foo.md")
    out = _render_to_text(page)
    assert "Foo" in out
    assert "[page]" in out
    assert "1 blocks" in out


def test_render_includes_journal_date_tag() -> None:
    page = parse("- morning\n", "/tmp/2024_01_15.md")
    out = _render_to_text(page)
    assert "[journal · 2024-01-15]" in out


def test_render_includes_block_content() -> None:
    page = parse(
        "- alpha\n- bravo with [[ref]] and #tag\n", "/tmp/X.md"
    )
    out = _render_to_text(page)
    assert "alpha" in out
    assert "bravo with" in out
    assert "[[ref]]" in out
    assert "#tag" in out


def test_render_marker_visible() -> None:
    page = parse("- TODO write notes\n- DONE finish task\n", "/tmp/X.md")
    out = _render_to_text(page)
    assert "TODO" in out
    assert "DONE" in out
    assert "write notes" in out


def test_render_nested_indent() -> None:
    page = parse("- parent\n\t- child\n\t\t- grandchild\n", "/tmp/X.md")
    out = _render_to_text(page)
    # Direct prefix-based ordering check: depth 0 / 1 / 2 = 0 / 2 / 4 spaces
    assert "- parent" in out
    assert "  - child" in out
    assert "    - grandchild" in out


def test_render_empty_page_shows_placeholder() -> None:
    page = parse("alias:: stub\n", "/tmp/Empty.md")  # properties only, no bullets
    out = _render_to_text(page)
    assert "Empty" in out
    assert "0 blocks" in out
    assert "(no blocks)" in out


def test_render_page_aliases() -> None:
    page = parse(
        "alias:: foo, bar\n- content\n", "/tmp/Page.md"
    )
    out = _render_to_text(page)
    assert "aliases:" in out
    assert "foo" in out
    assert "bar" in out


# CLI smoke


CLI = [sys.executable, "-m", "logseq"]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(CLI + args, capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "logseq").mkdir()
    (tmp_path / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (tmp_path / "journals").mkdir()
    (tmp_path / "pages").mkdir()
    return tmp_path


def test_cli_view_by_page_name(vault: Path) -> None:
    (vault / "pages" / "Hello.md").write_text(
        "- world [[link]]\n", encoding="utf-8"
    )
    result = _run(["view", "hello", str(vault)])
    assert result.returncode == 0, result.stderr
    assert "Hello" in result.stdout
    assert "world" in result.stdout


def test_cli_view_today(vault: Path) -> None:
    from datetime import date

    today = date.today().isoformat()
    fname = "_".join(today.split("-")) + ".md"
    (vault / "journals" / fname).write_text(
        "- morning routine\n", encoding="utf-8"
    )
    result = _run(["view", "today", str(vault)])
    assert result.returncode == 0, result.stderr
    assert "morning routine" in result.stdout


def test_cli_view_returns_5_when_not_found(vault: Path) -> None:
    result = _run(["view", "nonexistent", str(vault)])
    assert result.returncode == 5
    assert "no page matching" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_view_returns_2_when_not_a_vault(tmp_path: Path) -> None:
    result = _run(["view", "x", str(tmp_path)])  # no logseq/config.edn
    assert result.returncode == 2
    assert "not a logseq vault" in result.stderr
