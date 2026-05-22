from __future__ import annotations

from pathlib import Path

import pytest

from logseq.index import reindex
from logseq.tui.app import LogseqTUI
from logseq.tui.main import MainScreen


@pytest.fixture
def indexed_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    v = tmp_path / "vault"
    (v / "logseq").mkdir(parents=True)
    (v / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (v / "pages").mkdir()
    (v / "journals").mkdir()
    (v / "pages" / "Alpha.md").write_text(
        "- alpha content [[Beta]]\n- TODO finish alpha\n", encoding="utf-8"
    )
    (v / "pages" / "Beta.md").write_text("- beta details\n", encoding="utf-8")
    reindex(v)
    return v


@pytest.mark.asyncio
async def test_app_launches_and_lists_pages(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        page_titles = [p.title for p in screen.all_pages]
        assert "Alpha" in page_titles
        assert "Beta" in page_titles


@pytest.mark.asyncio
async def test_filter_narrows_page_list(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        screen.filter_text = "beta"
        await pilot.pause()
        assert [p.title for p in screen._visible_pages()] == ["Beta"]


@pytest.mark.asyncio
async def test_view_updates_when_current_changes(indexed_vault: Path) -> None:
    from textual.widgets import Static

    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        beta = next(p for p in screen.all_pages if p.title == "Beta")
        screen.current = beta
        await pilot.pause()
        view = screen.query_one("#view-panel", Static)
        rendered = view.renderable
        # Static.renderable may be a str or RenderableType; convert to str
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO(), force_terminal=False, width=200)
        console.print(rendered)
        txt = console.file.getvalue()
        assert "Beta" in txt
        assert "beta details" in txt


@pytest.mark.asyncio
async def test_app_exits_3_when_no_index(tmp_path: Path) -> None:
    v = tmp_path / "vault"
    (v / "logseq").mkdir(parents=True)
    (v / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (v / "pages").mkdir()
    app = LogseqTUI(v)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
    assert app.return_code == 3
