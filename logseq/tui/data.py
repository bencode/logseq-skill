from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..index import db_path_for


@dataclass(frozen=True)
class PageRef:
    name: str
    title: str
    type: str
    file_path: str
    block_count: int


def list_pages(vault: Path, *, include_journals: bool = False) -> list[PageRef]:
    """List pages with metadata. Default: non-empty pages only (Logseq-aligned).
    With include_journals=True: pages first (alpha), then journals (reverse-chrono)."""
    db = db_path_for(vault)
    conn = sqlite3.connect(db)
    try:
        if include_journals:
            sql = (
                "SELECT p.name, p.title, p.type, p.file_path, count(b.uuid) "
                "FROM pages p LEFT JOIN blocks b ON b.page = p.name "
                "GROUP BY p.name "
                "HAVING count(b.uuid) > 0 "
                "ORDER BY "
                "  CASE WHEN p.type = 'journal' THEN 1 ELSE 0 END, "
                "  CASE WHEN p.type = 'journal' THEN -p.journal_day ELSE 0 END, "
                "  p.name"
            )
        else:
            sql = (
                "SELECT p.name, p.title, p.type, p.file_path, count(b.uuid) "
                "FROM pages p LEFT JOIN blocks b ON b.page = p.name "
                "WHERE p.type = 'page' "
                "GROUP BY p.name "
                "HAVING count(b.uuid) > 0 "
                "ORDER BY p.name"
            )
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    return [PageRef(*r) for r in rows]
