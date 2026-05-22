from __future__ import annotations

import sys
from pathlib import Path


def cmd_tui(vault: str, theme: str) -> int:
    try:
        from ..tui.app import run
    except ImportError as e:
        name = e.name or ""
        if name.startswith("textual"):
            print(
                "error: TUI requires Textual >= 0.86 "
                f"(import failed: {e})",
                file=sys.stderr,
            )
        else:
            print(
                f"error: TUI requires `pip install -e \".[tui]\"` "
                f"(missing: {name or e})",
                file=sys.stderr,
            )
        return 2
    return run(Path(vault), theme=theme)
