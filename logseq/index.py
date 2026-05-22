from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .db import (
    SCHEMA_VERSION,
    connect,
    count,
    existing_files,
    insert_page,
)
from .parser import parse

CACHE_DIR = Path.home() / ".cache" / "logseq-skill"


@dataclass(frozen=True)
class IndexStats:
    scanned: int
    skipped: int
    reindexed: int
    deleted: int
    elapsed_ms: int


def db_path_for(vault_dir: Path) -> Path:
    digest = hashlib.sha1(str(vault_dir.absolute()).encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.db"


def reindex(
    vault_dir: Path,
    *,
    full: bool = False,
    db_path: Path | None = None,
) -> IndexStats:
    _validate_vault(vault_dir)
    started = time.monotonic()
    resolved_db = db_path or db_path_for(vault_dir)
    if full and resolved_db.exists():
        resolved_db.unlink()
    conn = connect(resolved_db)
    try:
        conn.execute("BEGIN")
        scanned, skipped, reindexed, deleted = _do_reindex(conn, vault_dir)
        _write_meta(conn, vault_dir)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return IndexStats(scanned, skipped, reindexed, deleted, elapsed_ms)


def stats(vault_dir: Path, *, db_path: Path | None = None) -> dict:
    _validate_vault(vault_dir)
    resolved_db = db_path or db_path_for(vault_dir)
    if not resolved_db.exists():
        return _empty_stats(vault_dir, resolved_db)
    conn = sqlite3.connect(resolved_db)
    try:
        pages = count(conn, "pages")
        blocks = count(conn, "blocks")
        refs = count(conn, "refs")
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    last_ts = meta.get("last_index_ts")
    return {
        "db_path": str(resolved_db),
        "db_exists": True,
        "pages": pages,
        "blocks": blocks,
        "refs": refs,
        "db_size_bytes": resolved_db.stat().st_size,
        "last_index_ts": float(last_ts) if last_ts else None,
        "vault_path": meta.get("vault_path"),
        "schema_version": meta.get("schema_version"),
    }


def _validate_vault(vault_dir: Path) -> None:
    if not (vault_dir / "logseq" / "config.edn").exists():
        raise ValueError(f"not a logseq vault (no logseq/config.edn): {vault_dir}")


def _vault_md_files(vault_dir: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("journals", "pages"):
        d = vault_dir / sub
        if d.exists():
            out.extend(sorted(d.glob("*.md")))
    return out


def _do_reindex(conn: sqlite3.Connection, vault_dir: Path) -> tuple[int, int, int, int]:
    existing = existing_files(conn)
    seen: set[str] = set()
    scanned = skipped = reindexed = 0
    for md in _vault_md_files(vault_dir):
        scanned += 1
        file_path = str(md)
        seen.add(file_path)
        stat = md.stat()
        if existing.get(file_path) == (stat.st_mtime, stat.st_size):
            skipped += 1
            continue
        page = parse(md.read_text(encoding="utf-8"), file_path)
        conn.execute("DELETE FROM pages WHERE file_path = ?", (file_path,))
        insert_page(conn, page, stat.st_mtime, stat.st_size)
        reindexed += 1
    deleted = _delete_missing(conn, set(existing.keys()) - seen)
    return scanned, skipped, reindexed, deleted


def _delete_missing(conn: sqlite3.Connection, missing: set[str]) -> int:
    for fp in missing:
        conn.execute("DELETE FROM pages WHERE file_path = ?", (fp,))
    return len(missing)


def _write_meta(conn: sqlite3.Connection, vault_dir: Path) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        [
            ("last_index_ts", str(time.time())),
            ("vault_path", str(vault_dir.absolute())),
            ("schema_version", SCHEMA_VERSION),
        ],
    )


def _empty_stats(vault_dir: Path, db_path: Path) -> dict:
    return {
        "db_path": str(db_path),
        "db_exists": False,
        "pages": 0,
        "blocks": 0,
        "refs": 0,
        "db_size_bytes": 0,
        "last_index_ts": None,
        "vault_path": str(vault_dir.absolute()),
        "schema_version": None,
    }
