from __future__ import annotations

import sqlite3
import time
from datetime import date
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from .. import queries
from ..parser import parse
from ..render import render_page
from .data import PageRef, list_pages


class MainScreen(Screen):
    BINDINGS = [
        # vim navigation
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("G", "cursor_end", show=False),
        Binding("ctrl+d", "half_down", show=False),
        Binding("ctrl+u", "half_up", show=False),
        Binding("ctrl+f", "page_down", show=False),
        Binding("ctrl+b", "page_up", show=False),
        Binding("h", "focus_list", show=False),
        Binding("l", "focus_view", show=False),
        # filter / search
        Binding("/", "focus_filter", "Filter", show=True),
        Binding("question_mark", "search_modal", "Search", show=True),
        Binding("escape", "blur_filter", show=False),
        # Logseq-style jumps
        Binding("D", "today", "Today", show=True),
        Binding("J", "toggle_journals", "+Journals", show=True),
        # app actions
        Binding("t", "todos_modal", "TODOs", show=True),
        Binding("T", "theme_picker", "Theme", show=True),
        Binding("ctrl+r", "refresh_pages", show=False),
    ]

    filter_text = reactive("")
    current: reactive[PageRef | None] = reactive(None)
    show_journals: reactive[bool] = reactive(False)

    _g_pending_at: float = 0.0

    # debounce windows (seconds)
    RENDER_DEBOUNCE = 0.08
    FILTER_DEBOUNCE = 0.15

    def __init__(self, vault: Path) -> None:
        super().__init__()
        self.vault = vault
        self.all_pages: list[PageRef] = []
        self._render_timer: Timer | None = None
        self._filter_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="main-layout"):
            with Vertical(id="left"):
                yield Input(placeholder="filter pages...", id="page-filter")
                yield ListView(id="page-list")
            with Vertical(id="right"):
                yield Static(id="view-panel", expand=True, markup=False)
                yield Static(id="backlinks-panel", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = str(self.vault)
        self.all_pages = list_pages(self.vault)
        self._populate_list(self.all_pages)
        self.query_one("#page-list", ListView).focus()

    def _populate_list(self, pages: list[PageRef]) -> None:
        lv = self.query_one("#page-list", ListView)
        lv.clear()
        for p in pages:
            label = Text()
            label.append(p.title)
            label.append(f"  ({p.block_count})", style="dim")
            if p.type == "journal":
                label.stylize("cyan", 0, len(p.title))
            lv.append(ListItem(Static(label)))
        if not pages:
            self.current = None
            return
        # Preserve cursor on current page if still visible (filter typing /
        # J toggle shouldn't yank a navigating user back to the top)
        keep_idx = 0
        if self.current is not None:
            for i, p in enumerate(pages):
                if p.name == self.current.name and p.type == self.current.type:
                    keep_idx = i
                    break
        lv.index = keep_idx
        self.current = pages[keep_idx]

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "page-filter":
            value = event.value
            if self._filter_timer is not None:
                self._filter_timer.stop()
            self._filter_timer = self.set_timer(
                self.FILTER_DEBOUNCE,
                lambda: self._apply_filter(value),
            )

    def _apply_filter(self, value: str) -> None:
        self.filter_text = value

    def watch_filter_text(self, value: str) -> None:
        if not value:
            self._populate_list(self.all_pages)
            return
        needle = value.lower()
        filtered = [p for p in self.all_pages if needle in p.title.lower()]
        self._populate_list(filtered)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        items = self.query_one("#page-list", ListView).children
        if idx is None or not (0 <= idx < len(items)):
            return
        # Find the page by filtering with current filter text
        visible = self._visible_pages()
        if 0 <= idx < len(visible):
            self.current = visible[idx]

    def _visible_pages(self) -> list[PageRef]:
        if not self.filter_text:
            return self.all_pages
        needle = self.filter_text.lower()
        return [p for p in self.all_pages if needle in p.title.lower()]

    def watch_current(self, _old: PageRef | None, _new: PageRef | None) -> None:
        """Schedule a debounced render — cursor highlight stays instant,
        the heavy file-read/parse/render/backlinks work happens only after
        keystrokes settle for RENDER_DEBOUNCE seconds."""
        if self._render_timer is not None:
            self._render_timer.stop()
        self._render_timer = self.set_timer(
            self.RENDER_DEBOUNCE, self._do_render_current
        )

    def _do_render_current(self) -> None:
        new = self.current
        view = self.query_one("#view-panel", Static)
        bl = self.query_one("#backlinks-panel", Static)
        if new is None:
            view.update("(no page)")
            bl.update("")
            return
        try:
            # utf-8-sig transparently strips BOM if present; raises on truly
            # broken encodings (caught below)
            text = Path(new.file_path).read_text(encoding="utf-8-sig")
            page = parse(text, new.file_path)
            view.update(render_page(page))
        except Exception as e:
            error_text = Text()
            error_text.append(f"error: {type(e).__name__}: {e}", style="red")
            view.update(error_text)
        try:
            results = queries.backlinks(self.vault, new.title, limit=10)
        except (
            queries.IndexMissing,
            queries.IndexStale,
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
        ) as e:
            bl.update(
                Text.from_markup(f"[red]backlinks unavailable: {e}[/red]")
            )
            return
        if not results:
            bl.update(Text("(no backlinks)", style="dim italic"))
            return
        lines: list[Text] = []
        for r in results:
            line = Text()
            line.append(r["page"], style="cyan")
            line.append(": ")
            line.append(r["content"][:120])
            lines.append(line)
        bl.update(Text("\n").join(lines))

    # --- vim navigation actions ---

    def on_key(self, event: events.Key) -> None:
        """Handle the `gg` two-key sequence for jump-to-top."""
        if event.key == "g":
            now = time.monotonic()
            if now - self._g_pending_at < 0.6:
                self.action_cursor_home()
                self._g_pending_at = 0.0
                event.prevent_default()
                event.stop()
            else:
                self._g_pending_at = now
        else:
            self._g_pending_at = 0.0

    def action_cursor_down(self) -> None:
        self.query_one("#page-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#page-list", ListView).action_cursor_up()

    def action_cursor_home(self) -> None:
        lv = self.query_one("#page-list", ListView)
        if list(lv.children):
            lv.index = 0

    def action_cursor_end(self) -> None:
        lv = self.query_one("#page-list", ListView)
        n = len(list(lv.children))
        if n:
            lv.index = n - 1

    def _scroll_by(self, delta: int) -> None:
        lv = self.query_one("#page-list", ListView)
        n = len(list(lv.children))
        if not n:
            return
        idx = lv.index or 0
        lv.index = max(0, min(idx + delta, n - 1))

    def action_half_down(self) -> None:
        self._scroll_by(self.app.size.height // 2)

    def action_half_up(self) -> None:
        self._scroll_by(-(self.app.size.height // 2))

    def action_page_down(self) -> None:
        self._scroll_by(self.app.size.height)

    def action_page_up(self) -> None:
        self._scroll_by(-self.app.size.height)

    def action_focus_list(self) -> None:
        self.query_one("#page-list", ListView).focus()

    def action_focus_view(self) -> None:
        self.query_one("#view-panel", Static).focus()

    # --- filter / Logseq-style ---

    def action_focus_filter(self) -> None:
        self.query_one("#page-filter", Input).focus()

    def action_blur_filter(self) -> None:
        if self._filter_timer is not None:
            self._filter_timer.stop()
            self._filter_timer = None
        self.query_one("#page-list", ListView).focus()

    def action_refresh_pages(self) -> None:
        self.all_pages = list_pages(self.vault, include_journals=self.show_journals)
        self._populate_list(self._visible_pages())

    def action_search_modal(self) -> None:
        from .modals import SearchModal
        self.app.push_screen(SearchModal(self.vault))

    def action_todos_modal(self) -> None:
        from .modals import TodosModal
        self.app.push_screen(TodosModal(self.vault))

    def action_theme_picker(self) -> None:
        from .modals import ThemePicker
        self.app.push_screen(ThemePicker())

    def action_toggle_journals(self) -> None:
        self.show_journals = not self.show_journals

    def watch_show_journals(self, value: bool) -> None:
        self.all_pages = list_pages(self.vault, include_journals=value)
        self._populate_list(self._visible_pages())
        self.notify(
            "Journals included" if value else "Pages only",
            severity="information",
            timeout=1.5,
        )

    def action_today(self) -> None:
        today = date.today().isoformat()
        fname = "_".join(today.split("-")) + ".md"
        path = self.vault / "journals" / fname
        if not path.exists():
            self.notify(f"No journal for {today}", severity="warning")
            return
        self.current = PageRef(
            name=path.stem.lower(),
            title=path.stem,
            type="journal",
            file_path=str(path),
            block_count=0,
        )
        self.notify(
            f"Viewing today's journal · {today}",
            severity="information",
            timeout=1.5,
        )
