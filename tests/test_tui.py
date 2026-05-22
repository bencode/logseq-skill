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
    (v / "pages" / "EmptyPage.md").write_text("", encoding="utf-8")  # placeholder
    (v / "journals" / "2024_01_15.md").write_text(
        "- morning routine\n", encoding="utf-8"
    )
    (v / "journals" / "2024_03_10.md").write_text(
        "- another day\n", encoding="utf-8"
    )
    reindex(v)
    return v


@pytest.mark.asyncio
async def test_app_launches_with_pages_only_by_default(indexed_vault: Path) -> None:
    """Logseq-aligned: default list is pages only, non-empty, no journals."""
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        types = {p.type for p in screen.all_pages}
        assert types == {"page"}, f"expected pages only, got types={types}"
        titles = [p.title for p in screen.all_pages]
        assert "Alpha" in titles
        assert "Beta" in titles
        assert "EmptyPage" not in titles  # empty page filtered
        assert "2024_01_15" not in titles  # journal not in default list


@pytest.mark.asyncio
async def test_J_toggles_journals_into_list(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        assert screen.show_journals is False
        await pilot.press("J")
        await pilot.pause()
        assert screen.show_journals is True
        titles = [p.title for p in screen.all_pages]
        assert "2024_01_15" in titles
        assert "2024_03_10" in titles
        # Journals come AFTER pages, in reverse-chrono order
        positions = {t: i for i, t in enumerate(titles)}
        assert positions["2024_03_10"] < positions["2024_01_15"], (
            "journals should be reverse-chrono (newer first)"
        )
        assert positions["Alpha"] < positions["2024_03_10"], (
            "pages should come before journals"
        )


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
async def test_D_jumps_to_today_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date as _date

    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    v = tmp_path / "vault"
    (v / "logseq").mkdir(parents=True)
    (v / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (v / "pages").mkdir()
    (v / "journals").mkdir()
    (v / "pages" / "P.md").write_text("- a page\n", encoding="utf-8")
    today_iso = _date.today().isoformat()
    today_fname = "_".join(today_iso.split("-")) + ".md"
    (v / "journals" / today_fname).write_text(
        "- today entry\n", encoding="utf-8"
    )
    reindex(v)

    app = LogseqTUI(v)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        # Default list contains no journal — today not in list
        assert today_fname.removesuffix(".md") not in [p.title for p in screen.all_pages]
        # Press D → current becomes today's journal
        await pilot.press("D")
        await pilot.pause()
        assert screen.current is not None
        assert screen.current.type == "journal"
        assert screen.current.title == today_fname.removesuffix(".md")


@pytest.mark.asyncio
async def test_gg_jumps_to_top(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        # Move down a few first
        await pilot.press("j", "j")
        await pilot.pause()
        # Then gg → back to top
        await pilot.press("g", "g")
        await pilot.pause()
        lv = screen.query_one("#page-list")
        assert lv.index == 0


@pytest.mark.asyncio
async def test_G_jumps_to_bottom(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        await pilot.press("G")
        await pilot.pause()
        lv = screen.query_one("#page-list")
        assert lv.index == len(screen.all_pages) - 1


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
