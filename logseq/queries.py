from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import connect
from .index import db_path_for, needs_rebuild, validate_vault


class IndexMissing(Exception):
    """Vault has no cache DB yet — caller should run `logseq index` first."""


class IndexStale(Exception):
    """Cache DB is corrupt or has an outdated schema_version."""


def search(vault_dir: Path, query: str, *, limit: int = 20) -> list[dict]:
    with _read(vault_dir) as conn:
        rows = conn.execute(
            "SELECT b.page, b.uuid, b.content "
            "FROM blocks b "
            "JOIN blocks_fts ON blocks_fts.rowid = b.rowid "
            "WHERE blocks_fts MATCH ? "
            "LIMIT ?",
            (query, limit),
        ).fetchall()
    return [{"page": r[0], "uuid": r[1], "content": r[2]} for r in rows]


def backlinks(
    vault_dir: Path,
    name: str,
    *,
    limit: int = 50,
    case_sensitive: bool = False,
) -> list[dict]:
    if case_sensitive:
        where = "r.target = ? AND r.kind = 'page'"
        params: tuple[object, ...] = (name, limit)
    else:
        where = "LOWER(r.target) = LOWER(?) AND r.kind = 'page'"
        params = (name, limit)
    with _read(vault_dir) as conn:
        rows = conn.execute(
            f"SELECT b.page, b.uuid, b.content "
            f"FROM refs r "
            f"JOIN blocks b ON r.block_uuid = b.uuid "
            f"WHERE {where} "
            f"LIMIT ?",
            params,
        ).fetchall()
    return [{"page": r[0], "uuid": r[1], "content": r[2]} for r in rows]


def todos(
    vault_dir: Path,
    *,
    marker: str = "TODO",
    page: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if page is None:
        sql = (
            "SELECT page, uuid, content FROM blocks "
            "WHERE marker = ? LIMIT ?"
        )
        params: tuple[object, ...] = (marker, limit)
    else:
        sql = (
            "SELECT page, uuid, content FROM blocks "
            "WHERE marker = ? AND page = ? LIMIT ?"
        )
        params = (marker, page.lower(), limit)
    with _read(vault_dir) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{"page": r[0], "uuid": r[1], "content": r[2]} for r in rows]


class _read:
    """Context manager: open the index DB for read, or raise IndexMissing/IndexStale."""

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = vault_dir.expanduser().resolve()
        self.conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        validate_vault(self.vault_dir)
        db = db_path_for(self.vault_dir)
        if not db.exists():
            raise IndexMissing(
                f"no index for {self.vault_dir}. "
                f"Run 'logseq index <vault>' first."
            )
        needs, reason = needs_rebuild(db)
        if needs:
            raise IndexStale(
                f"index for {self.vault_dir} is stale ({reason}). "
                f"Run 'logseq index <vault>' to refresh."
            )
        self.conn = connect(db)
        return self.conn

    def __exit__(self, *exc: object) -> None:
        if self.conn is not None:
            self.conn.close()
