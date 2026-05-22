from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Label, Select

from .. import queries


class SearchModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, vault: Path) -> None:
        super().__init__()
        self.vault = vault

    def compose(self) -> ComposeResult:
        with Vertical(id="search-modal"):
            yield Label("FTS5 search  (Esc to close)", classes="title")
            yield Input(placeholder="query...  (use --min-len via SHIFT+M)", id="search-input")
            yield DataTable(id="search-results", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#search-results", DataTable)
        table.add_columns("page", "content")
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input":
            return
        table = self.query_one("#search-results", DataTable)
        table.clear()
        q = event.value.strip()
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
