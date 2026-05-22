from __future__ import annotations

import sqlite3
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from ..index import db_path_for, needs_rebuild, reindex, validate_vault
from .main import MainScreen


class LogseqTUI(App):
    """Terminal browser for Logseq vaults."""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, vault: Path, theme: str = "catppuccin-mocha") -> None:
        super().__init__()
        self.vault = vault.expanduser().resolve()
        self._initial_theme = theme

    def on_mount(self) -> None:
        self.theme = self._initial_theme
        status = _check_index(self.vault)
        if status == "missing":
            self.exit(
                message=(
                    f"No index for {self.vault}.\n"
                    f"Run `logseq index {self.vault}` first, then re-launch."
                ),
                return_code=3,
            )
            return
        if status == "stale":
            self.exit(
                message=(
                    f"Index for {self.vault} is stale.\n"
                    f"Run `logseq index {self.vault}` to refresh, then re-launch."
                ),
                return_code=4,
            )
            return
        self.push_screen(MainScreen(self.vault))


def _check_index(vault: Path) -> str:
    """Return 'missing' | 'stale' | 'ok'."""
    validate_vault(vault)
    db = db_path_for(vault)
    if not db.exists():
        return "missing"
    needs, _ = needs_rebuild(db)
    return "stale" if needs else "ok"


def run(vault: Path, theme: str = "catppuccin-mocha") -> int:
    try:
        vault = vault.expanduser().resolve()
        validate_vault(vault)
    except ValueError as e:
        print(f"error: {e}")
        return 2
    app = LogseqTUI(vault, theme=theme)
    app.run()
    return app.return_code or 0
