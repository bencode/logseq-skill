from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import SCHEMA_VERSION, connect, count
from .index import db_path_for, validate_vault


def stats(vault_dir: Path, *, db_path: Path | None = None) -> dict:
    vault_dir = vault_dir.expanduser().resolve()
    validate_vault(vault_dir)
    resolved_db = db_path or db_path_for(vault_dir)
    if not resolved_db.exists():
        return _empty_stats(vault_dir, resolved_db)
    try:
        return _read_stats(resolved_db)
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        return _broken_stats(resolved_db, str(e))


def _read_stats(resolved_db: Path) -> dict:
    conn = connect(resolved_db)
    try:
        pages = count(conn, "pages")
        blocks = count(conn, "blocks")
        refs = count(conn, "refs")
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    last_ts = meta.get("last_index_ts")
    stored_version = meta.get("schema_version")
    return {
        "db_path": str(resolved_db),
        "db_exists": True,
        "valid": True,
        "pages": pages,
        "blocks": blocks,
        "refs": refs,
        "db_size_bytes": resolved_db.stat().st_size,
        "last_index_ts": float(last_ts) if last_ts else None,
        "vault_path": meta.get("vault_path"),
        "schema_version": stored_version,
        "expected_schema_version": SCHEMA_VERSION,
        "schema_outdated": stored_version is not None
        and stored_version != SCHEMA_VERSION,
    }


def _empty_stats(vault_dir: Path, db_path: Path) -> dict:
    return {
        "db_path": str(db_path),
        "db_exists": False,
        "pages": 0,
        "blocks": 0,
        "refs": 0,
        "db_size_bytes": 0,
        "last_index_ts": None,
        "vault_path": str(vault_dir),
        "schema_version": None,
    }


def _broken_stats(db_path: Path, error_msg: str) -> dict:
    return {
        "db_path": str(db_path),
        "db_exists": True,
        "valid": False,
        "error": error_msg,
        "db_size_bytes": db_path.stat().st_size,
    }
