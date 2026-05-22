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
    (v / "pages" / "Gamma.md").write_text(
        "- gamma notes\n- more gamma\n", encoding="utf-8"
    )
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
        # Wait > RENDER_DEBOUNCE (80ms) for the debounced render to fire
        await pilot.pause(0.15)
        view = screen.query_one("#view-panel", Static)
        rendered = view.renderable
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO(), force_terminal=False, width=200)
        console.print(rendered)
        txt = console.file.getvalue()
        assert "Beta" in txt
        assert "beta details" in txt


@pytest.mark.asyncio
async def test_render_is_debounced_on_rapid_current_changes(
    indexed_vault: Path,
) -> None:
    """Rapid current changes coalesce — only the final value renders, not all."""
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        # Let initial mount + first render settle
        await pilot.pause(0.2)
        screen: MainScreen = app.screen  # type: ignore[assignment]

        render_calls: list[str | None] = []
        original = screen._do_render_current

        def counting_render() -> None:
            render_calls.append(screen.current.title if screen.current else None)
            original()

        screen._do_render_current = counting_render  # type: ignore[method-assign]

        # Tight loop: change current 3 times to genuinely distinct pages
        # (fixture has Alpha, Beta, Gamma so reactive fires for each)
        pages = screen.all_pages
        assert len(pages) >= 3, f"fixture too small: {[p.title for p in pages]}"
        screen.current = pages[2]   # 1st distinct change
        screen.current = pages[1]   # 2nd
        screen.current = pages[0]   # 3rd — final
        # Immediately: no render fired (timer pending, will fire in 80ms)
        assert render_calls == [], f"render fired early: {render_calls}"

        # After > RENDER_DEBOUNCE settles, exactly ONE render fires for the
        # final value (coalesced from 3 reactive triggers into 1 render)
        await pilot.pause(0.15)
        assert render_calls == [pages[0].title], (
            f"expected 1 render of final page, got {render_calls}"
        )


@pytest.mark.asyncio
async def test_filter_is_debounced(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        filter_input = screen.query_one("#page-filter")
        filter_input.focus()
        await pilot.pause()

        # Type chars; filter_text should NOT update synchronously
        await pilot.press("b", "e", "t", "a")
        assert screen.filter_text == "", (
            f"filter applied before debounce: {screen.filter_text!r}"
        )

        # After > FILTER_DEBOUNCE settles, filter applies once
        await pilot.pause(0.2)
        assert screen.filter_text == "beta"


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
async def test_question_mark_opens_search_modal(indexed_vault: Path) -> None:
    from logseq.tui.modals import SearchModal

    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, SearchModal)


@pytest.mark.asyncio
async def test_capital_T_opens_theme_picker_with_live_preview(
    indexed_vault: Path,
) -> None:
    from logseq.tui.modals import ThemePicker

    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        starting_theme = app.theme
        await pilot.press("T")
        await pilot.pause()
        assert isinstance(app.screen, ThemePicker)
        # Live-preview: arrowing down should immediately change app.theme
        await pilot.press("down")
        await pilot.pause()
        assert app.theme != starting_theme, "theme did not live-preview on arrow"


@pytest.mark.asyncio
async def test_lowercase_t_opens_todos_modal(indexed_vault: Path) -> None:
    from logseq.tui.modals import TodosModal

    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, TodosModal)


@pytest.mark.asyncio
async def test_unknown_theme_exits_2(indexed_vault: Path) -> None:
    app = LogseqTUI(indexed_vault, theme="nonexistent-theme")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
    assert app.return_code == 2


@pytest.mark.asyncio
async def test_esc_cancels_pending_filter_timer(indexed_vault: Path) -> None:
    """Esc-after-typing must cancel the pending filter; otherwise the
    timer fires post-Esc and silently narrows the list."""
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        screen.query_one("#page-filter").focus()
        await pilot.pause()
        # Type a few chars (timer is pending, value not applied yet)
        await pilot.press("b", "e")
        # Press Esc before the 150ms debounce fires
        await pilot.press("escape")
        # Wait longer than debounce — the stale timer must NOT fire
        await pilot.pause(0.25)
        assert screen.filter_text == "", (
            f"stale filter applied after Esc: {screen.filter_text!r}"
        )


@pytest.mark.asyncio
async def test_ctrl_r_refresh_preserves_show_journals_state(
    indexed_vault: Path,
) -> None:
    """After J toggles journals on, Ctrl+R must not silently drop them."""
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        await pilot.press("J")
        await pilot.pause()
        assert screen.show_journals is True
        n_with_journals = len(screen.all_pages)

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert screen.show_journals is True, "show_journals reset by refresh"
        assert len(screen.all_pages) == n_with_journals, (
            "journals dropped from list despite show_journals=True"
        )


@pytest.mark.asyncio
async def test_filter_does_not_reset_cursor_when_current_still_visible(
    indexed_vault: Path,
) -> None:
    """Typing in filter shouldn't yank the cursor back to the top when the
    currently-selected page is still in the filtered list."""
    app = LogseqTUI(indexed_vault)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen: MainScreen = app.screen  # type: ignore[assignment]
        # Pick the second page as current
        screen.current = screen.all_pages[1]
        await pilot.pause(0.15)
        target = screen.current
        # Apply a filter that still includes 'target' (use first char of title)
        screen.filter_text = target.title[:1].lower()
        await pilot.pause(0.05)
        # current should remain target, not jump back to index 0
        assert screen.current is not None
        assert screen.current.name == target.name, (
            f"filter yanked cursor: was {target.name}, became {screen.current.name}"
        )


@pytest.mark.asyncio
async def test_view_panel_is_scrollable_for_long_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Long pages must render into a scrollable container, not get truncated."""
    from textual.containers import VerticalScroll

    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    v = tmp_path / "vault"
    (v / "logseq").mkdir(parents=True)
    (v / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (v / "pages").mkdir()
    # 200 blocks — comfortably more than a typical terminal height
    long_content = "\n".join(f"- block number {i}" for i in range(200))
    (v / "pages" / "Long.md").write_text(long_content, encoding="utf-8")
    reindex(v)

    app = LogseqTUI(v)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause(0.2)
        screen: MainScreen = app.screen  # type: ignore[assignment]
        # The right pane contains scrollable containers, not bare Static
        scroll = screen.query_one("#view-scroll", VerticalScroll)
        assert scroll is not None
        # And the Static inside it can grow beyond the visible viewport
        # (height=auto in css), so the scroll container has scroll work to do
        assert scroll.virtual_size.height > scroll.size.height, (
            f"view-scroll has nothing to scroll: "
            f"virtual={scroll.virtual_size}, visible={scroll.size}"
        )


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
