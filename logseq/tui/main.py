from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from .. import queries
from ..db import connect
from ..index import db_path_for
from ..parser import parse
from ..render import render_page


@dataclass(frozen=True)
class PageRef:
    name: str
    title: str
    type: str
    file_path: str
    block_count: int


def list_pages(vault: Path) -> list[PageRef]:
    db = db_path_for(vault)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT p.name, p.title, p.type, p.file_path, count(b.uuid) "
            "FROM pages p LEFT JOIN blocks b ON b.page = p.name "
            "GROUP BY p.name ORDER BY p.type DESC, p.name"
        ).fetchall()
    finally:
        conn.close()
    return [PageRef(*r) for r in rows]


class MainScreen(Screen):
    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("/", "focus_filter", "Filter", show=True),
        Binding("ctrl+f", "search_modal", "Search", show=True),
        Binding("t", "todos_modal", "TODOs", show=True),
        Binding("escape", "blur_filter", show=False),
        Binding("ctrl+r", "refresh_pages", "Refresh", show=True),
    ]

    filter_text = reactive("")
    current: reactive[PageRef | None] = reactive(None)

    def __init__(self, vault: Path) -> None:
        super().__init__()
        self.vault = vault
        self.all_pages: list[PageRef] = []

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
        if pages:
            lv.index = 0
            self.current = pages[0]
        else:
            self.current = None

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "page-filter":
            self.filter_text = event.value

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

    def watch_current(self, _old: PageRef | None, new: PageRef | None) -> None:
        view = self.query_one("#view-panel", Static)
        bl = self.query_one("#backlinks-panel", Static)
        if new is None:
            view.update("(no page)")
            bl.update("")
            return
        try:
            text = Path(new.file_path).read_text(encoding="utf-8")
            page = parse(text, new.file_path)
            view.update(render_page(page))
        except Exception as e:
            view.update(f"[red]error: {type(e).__name__}: {e}[/red]")
        try:
            results = queries.backlinks(self.vault, new.title, limit=10)
        except (queries.IndexMissing, queries.IndexStale) as e:
            bl.update(f"[red]backlinks unavailable: {e}[/red]")
            return
        if not results:
            bl.update("[dim](no backlinks)[/dim]")
            return
        lines = [
            f"[cyan]{r['page']}[/cyan]: {r['content'][:120]}"
            for r in results
        ]
        bl.update("\n".join(lines))

    def action_cursor_down(self) -> None:
        self.query_one("#page-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#page-list", ListView).action_cursor_up()

    def action_focus_filter(self) -> None:
        self.query_one("#page-filter", Input).focus()

    def action_blur_filter(self) -> None:
        self.query_one("#page-list", ListView).focus()

    def action_refresh_pages(self) -> None:
        self.all_pages = list_pages(self.vault)
        self._populate_list(self._visible_pages())

    def action_search_modal(self) -> None:
        from .modals import SearchModal
        self.app.push_screen(SearchModal(self.vault))

    def action_todos_modal(self) -> None:
        from .modals import TodosModal
        self.app.push_screen(TodosModal(self.vault))
