from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import DataTable, Input, Label, ListItem, ListView, Select

from .. import queries


class SearchModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    QUERY_DEBOUNCE = 0.2

    def __init__(self, vault: Path) -> None:
        super().__init__()
        self.vault = vault
        self._query_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="search-modal"):
            yield Label("FTS5 search  (Esc to close)", classes="title")
            yield Input(placeholder="query...", id="search-input")
            yield DataTable(id="search-results", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#search-results", DataTable)
        table.add_columns("page", "content")
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input":
            return
        value = event.value
        if self._query_timer is not None:
            self._query_timer.stop()
        self._query_timer = self.set_timer(
            self.QUERY_DEBOUNCE, lambda: self._run_search(value)
        )

    def _run_search(self, q: str) -> None:
        table = self.query_one("#search-results", DataTable)
        table.clear()
        q = q.strip()
        if len(q) < 2:
            return
        try:
            results = queries.search(self.vault, q, limit=30, min_len=20)
        except Exception as e:
            table.add_row("[error]", str(e))
            return
        for r in results:
            table.add_row(r["page"], r["content"][:200])


class TodosModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    MARKERS = ["TODO", "DOING", "NOW", "LATER", "WAITING", "DONE"]

    def __init__(self, vault: Path) -> None:
        super().__init__()
        self.vault = vault

    def compose(self) -> ComposeResult:
        with Vertical(id="todos-modal"):
            yield Label("TODOs  (Esc to close)", classes="title")
            yield Select(
                [(m, m) for m in self.MARKERS],
                value="TODO",
                id="todos-marker",
                allow_blank=False,
            )
            yield DataTable(id="todos-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#todos-table", DataTable)
        table.add_columns("page", "content")
        self._reload("TODO")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "todos-marker":
            self._reload(str(event.value))

    def _reload(self, marker: str) -> None:
        table = self.query_one("#todos-table", DataTable)
        table.clear()
        try:
            results = queries.todos(self.vault, marker=marker, limit=100)
        except Exception as e:
            table.add_row("[error]", str(e))
            return
        for r in results:
            table.add_row(r["page"], r["content"][:200])


class ThemePicker(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-modal"):
            yield Label("Pick a theme  (↑↓ preview · Enter apply · Esc close)", classes="title")
            yield ListView(id="theme-list")

    def on_mount(self) -> None:
        lv = self.query_one("#theme-list", ListView)
        names = sorted(self.app.available_themes.keys())
        current = self.app.theme
        current_idx = 0
        for i, name in enumerate(names):
            label = f"  {name}"
            if name == current:
                label = f"▸ {name}"
                current_idx = i
            lv.append(ListItem(Label(label)))
        lv.index = current_idx
        lv.focus()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Live-preview as user navigates."""
        names = sorted(self.app.available_themes.keys())
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(names):
            self.app.theme = names[idx]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter closes — preview already applied via highlight."""
        self.dismiss()
