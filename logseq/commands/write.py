from __future__ import annotations

import contextlib
import sys
from datetime import date
from pathlib import Path


def cmd_capture(vault: str, content: str, marker: str | None) -> int:
    """Append a block to today's journal in <vault>."""
    from ..index import db_path_for, reindex, validate_vault
    from ..writer import FileChangedDuringWrite, append_to_today

    vault_path = Path(vault)
    try:
        validate_vault(vault_path.expanduser().resolve())
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        path = append_to_today(vault_path, content, marker=marker)
    except FileChangedDuringWrite as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(str(path))
    _maybe_reindex(vault_path, db_path_for, reindex)
    return 0


def cmd_append(
    vault: str, page: str, content: str, marker: str | None
) -> int:
    """Append a block to an existing page (or today's journal if page='today')."""
    from ..index import db_path_for, reindex, validate_vault
    from ..writer import FileChangedDuringWrite, append_to_page_file

    vault_path = Path(vault)
    try:
        validate_vault(vault_path.expanduser().resolve())
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        target = _resolve_page_path(vault_path, page)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 5
    try:
        uuid = append_to_page_file(target, content, marker=marker)
    except FileChangedDuringWrite as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(uuid)
    _maybe_reindex(vault_path, db_path_for, reindex)
    return 0


def _resolve_page_path(vault: Path, page: str) -> Path:
    """Resolve page-name → file path. We do NOT create new page files
    (Logseq's job); we DO create today's journal if missing."""
    if page == "today":
        fname = "_".join(date.today().isoformat().split("-")) + ".md"
        return vault / "journals" / fname
    if page.endswith(".md") or page.startswith(("/", "./", "../")):
        p = Path(page)
        if not p.is_absolute():
            p = (vault / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"file not found: {p}")
        return p
    needle = page.lower()
    for sub in ("pages", "journals"):
        d = vault / sub
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            if md.stem.lower() == needle:
                return md
    raise FileNotFoundError(
        f"page {page!r} not found in {vault}. Create it in Logseq first, "
        f"or use 'logseq capture' for today's journal."
    )


def _maybe_reindex(vault: Path, db_path_for_fn, reindex_fn) -> None:
    """Incrementally reindex IF an index already exists. We don't create
    a new index here — that's `logseq index`'s job."""
    canonical = vault.expanduser().resolve()
    db = db_path_for_fn(canonical)
    if db.exists():
        # Reindex is best-effort post-write; the write itself succeeded.
        # Don't fail the command if reindex hits an issue.
        with contextlib.suppress(Exception):
            reindex_fn(canonical)
