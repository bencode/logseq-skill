from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.theme import Theme

from ..index import db_path_for, needs_rebuild, validate_vault
from .main import MainScreen

LOGSEQ_BLACK = Theme(
    name="logseq-black",
    primary="#7aa2f7",          # soft blue for highlights
    secondary="#9d7cd8",         # mauve
    accent="#7dcfff",            # cyan for borders / accents
    background="#000000",        # pure black
    surface="#0a0a0a",           # near-black for panels
    panel="#0f0f0f",
    boost="#1a1a1a",
    foreground="#e0e0e0",
    success="#9ece6a",
    warning="#e0af68",
    error="#f7768e",
    dark=True,
)

LOGSEQ_WHITE = Theme(
    name="logseq-white",
    primary="#3b5fc0",           # darker blue for contrast on white
    secondary="#7c3aed",         # purple
    accent="#0066cc",            # blue borders / accents
    background="#ffffff",        # pure white
    surface="#fafafa",           # near-white for panels
    panel="#f0f0f0",
    boost="#e5e5e5",
    foreground="#1a1a1a",
    success="#16a34a",
    warning="#ca8a04",
    error="#dc2626",
    dark=False,
)


class LogseqTUI(App):
    """Terminal browser for Logseq vaults."""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, vault: Path, theme: str = "textual-dark") -> None:
        super().__init__()
        self.vault = vault.expanduser().resolve()
        self._initial_theme = theme

    def on_mount(self) -> None:
        self.register_theme(LOGSEQ_BLACK)
        self.register_theme(LOGSEQ_WHITE)
        if self._initial_theme not in self.available_themes:
            names = ", ".join(sorted(self.available_themes.keys()))
            self.exit(
                message=(
                    f"Unknown theme {self._initial_theme!r}. "
                    f"Available: {names}"
                ),
                return_code=2,
            )
            return
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


def run(vault: Path, theme: str = "textual-dark") -> int:
    try:
        vault = vault.expanduser().resolve()
        validate_vault(vault)
    except ValueError as e:
        print(f"error: {e}")
        return 2
    app = LogseqTUI(vault, theme=theme)
    app.run()
    return app.return_code or 0
