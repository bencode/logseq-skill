from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .db import (
    SCHEMA_VERSION,
    connect,
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
    errors: int = 0
    auto_rebuilt: bool = False


def db_path_for(vault_dir: Path) -> Path:
    digest = hashlib.sha1(str(vault_dir).encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.db"


def reindex(
    vault_dir: Path,
    *,
    full: bool = False,
    db_path: Path | None = None,
) -> IndexStats:
    vault_dir = vault_dir.expanduser().resolve()
    _validate_vault(vault_dir)
    started = time.monotonic()
    target_db = db_path or db_path_for(vault_dir)
    auto_rebuilt = False
    if not full and target_db.exists() and _needs_rebuild(target_db):
        full = True
        auto_rebuilt = True
    working_db = (
        target_db.with_name(target_db.name + ".tmp") if full else target_db
    )
    if full and working_db.exists():
        working_db.unlink()
    conn = connect(working_db)
    try:
        conn.execute("BEGIN")
        scanned, skipped, reindexed, deleted, errors = _do_reindex(conn, vault_dir)
        _write_meta(conn, vault_dir)
        conn.commit()
    except Exception:
        conn.rollback()
        if full:
            working_db.unlink(missing_ok=True)
        raise
    finally:
        conn.close()
    if full and working_db != target_db:
        os.replace(working_db, target_db)
        for sidecar in ("-wal", "-shm"):
            working_db.with_name(working_db.name + sidecar).unlink(missing_ok=True)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return IndexStats(
        scanned, skipped, reindexed, deleted, elapsed_ms, errors, auto_rebuilt
    )


def _needs_rebuild(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        _warn(f"cache DB unreadable ({type(e).__name__}: {e}); will rebuild from vault")
        return True
    if row is None:
        return False
    if row[0] != SCHEMA_VERSION:
        _warn(
            f"cache DB schema_version={row[0]!r}, current={SCHEMA_VERSION!r}; "
            f"will rebuild from vault"
        )
        return True
    return False


def _warn(msg: str) -> None:
    print(f"warn: {msg}", file=sys.stderr)


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


def _do_reindex(conn: sqlite3.Connection, vault_dir: Path) -> tuple[int, int, int, int, int]:
    existing = existing_files(conn)
    db_uuids = {row[0] for row in conn.execute("SELECT uuid FROM blocks")}
    seen_files: set[str] = set()
    scanned = skipped = reindexed = errors = 0
    for md in _vault_md_files(vault_dir):
        scanned += 1
        file_path = str(md)
        seen_files.add(file_path)
        stat = md.stat()
        if existing.get(file_path) == (stat.st_mtime, stat.st_size):
            skipped += 1
            continue
        try:
            page = parse(md.read_text(encoding="utf-8"), file_path)
        except (UnicodeDecodeError, ValueError) as e:
            _warn(f"skipping {file_path}: {type(e).__name__}: {e}")
            errors += 1
            continue
        old_uuids = {
            row[0] for row in conn.execute(
                "SELECT uuid FROM blocks WHERE page = ?", (page.name,)
            )
        }
        db_uuids -= old_uuids
        unique_blocks = []
        for b in page.blocks:
            if b.uuid in db_uuids:
                _warn(
                    f"duplicate block uuid {b.uuid} in {file_path}; "
                    f"already indexed from another file, skipping this occurrence"
                )
                errors += 1
                continue
            unique_blocks.append(b)
            db_uuids.add(b.uuid)
        page.blocks = unique_blocks
        conn.execute("DELETE FROM pages WHERE file_path = ?", (file_path,))
        insert_page(conn, page, stat.st_mtime, stat.st_size)
        reindexed += 1
    deleted = _delete_missing(conn, set(existing.keys()) - seen_files)
    return scanned, skipped, reindexed, deleted, errors


def _delete_missing(conn: sqlite3.Connection, missing: set[str]) -> int:
    deleted = 0
    for fp in missing:
        cur = conn.execute("DELETE FROM pages WHERE file_path = ?", (fp,))
        deleted += cur.rowcount
    return deleted


def _write_meta(conn: sqlite3.Connection, vault_dir: Path) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        [
            ("last_index_ts", str(time.time())),
            ("vault_path", str(vault_dir)),
            ("schema_version", SCHEMA_VERSION),
        ],
    )


