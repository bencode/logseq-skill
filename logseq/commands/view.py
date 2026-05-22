from __future__ import annotations

import sys
from pathlib import Path


def cmd_view(name: str, vault: str) -> int:
    try:
        path = _resolve_view_target(name, Path(vault))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 5
    from rich.console import Console

    from ..parser import parse
    from ..render import render_page
    # utf-8-sig handles Windows-edited files with BOM transparently
    text = path.read_text(encoding="utf-8-sig")
    page = parse(text, str(path))
    Console().print(render_page(page))
    return 0


def _resolve_view_target(name: str, vault: Path) -> Path:
    from ..index import validate_vault
    validate_vault(vault)
    if name == "today":
        from datetime import date
        return _journal_path_or_error(vault, date.today().isoformat())
    if _looks_like_date(name):
        return _journal_path_or_error(vault, name)
    # Treat as a literal file path only if it looks like one:
    # absolute, starts with ./ or ../, or ends in .md.
    # NOT if it contains '/' alone — Logseq namespace pages
    # ("Project/Frontend") would otherwise be mis-classified.
    if name.startswith(("/", "./", "../")) or name.endswith(".md"):
        p = Path(name)
        if not p.is_absolute():
            p = (vault / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"file not found: {p}")
        return p
    needle = name.lower()
    candidates: list[Path] = []
    for sub in ("pages", "journals"):
        d = vault / sub
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            if md.stem.lower() == needle:
                return md
            if needle in md.stem.lower():
                candidates.append(md)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"no page matching {name!r} in {vault}")


def _looks_like_date(s: str) -> bool:
    parts = s.split("-")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def _journal_path_or_error(vault: Path, date_iso: str) -> Path:
    fname = "_".join(date_iso.split("-")) + ".md"
    p = vault / "journals" / fname
    if not p.exists():
        raise FileNotFoundError(f"journal not found: {p}")
    return p
