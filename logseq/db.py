from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .model import Block, Page

# v2: tokenized_content column + FTS5 now indexes jieba-tokenized text
#     (fixes CJK false positives like 学生→数学生活)
SCHEMA_VERSION = "2"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    name TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    journal_day INTEGER,
    namespace_parent TEXT,
    properties_json TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    mtime REAL NOT NULL,
    file_size INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_journal_day
    ON pages(journal_day) WHERE journal_day IS NOT NULL;

CREATE TABLE IF NOT EXISTS blocks (
    uuid TEXT PRIMARY KEY,
    page TEXT NOT NULL REFERENCES pages(name) ON DELETE CASCADE,
    parent_uuid TEXT,
    sibling_order INTEGER NOT NULL,
    depth INTEGER NOT NULL,
    marker TEXT,
    content TEXT NOT NULL,
    tokenized_content TEXT NOT NULL DEFAULT '',
    properties_json TEXT NOT NULL,
    has_explicit_id INTEGER NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_page ON blocks(page);
CREATE INDEX IF NOT EXISTS idx_blocks_parent ON blocks(parent_uuid);
CREATE INDEX IF NOT EXISTS idx_blocks_marker
    ON blocks(marker) WHERE marker IS NOT NULL;

CREATE TABLE IF NOT EXISTS refs (
    block_uuid TEXT NOT NULL REFERENCES blocks(uuid) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refs_target ON refs(target, kind);
CREATE INDEX IF NOT EXISTS idx_refs_block ON refs(block_uuid);

-- FTS5 indexes tokenized_content (jieba-segmented) so CJK words become
-- discrete tokens. unicode61 then splits on the inserted spaces.
-- snippet() will show jieba-segmented text with visible spaces — slightly
-- ugly but functional; result display still uses blocks.content directly.
CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
    tokenized_content,
    content='blocks',
    content_rowid='rowid',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS blocks_ai AFTER INSERT ON blocks BEGIN
    INSERT INTO blocks_fts(rowid, tokenized_content)
        VALUES (new.rowid, new.tokenized_content);
END;

CREATE TRIGGER IF NOT EXISTS blocks_ad AFTER DELETE ON blocks BEGIN
    INSERT INTO blocks_fts(blocks_fts, rowid, tokenized_content)
        VALUES('delete', old.rowid, old.tokenized_content);
END;

-- Defense-in-depth: today the indexer only does INSERT+DELETE on changed
-- files (no UPDATE), so this trigger never fires in practice. Defined
-- anyway so that any future code path doing `UPDATE blocks SET ...`
-- keeps the FTS5 view in sync rather than silently desyncing.
CREATE TRIGGER IF NOT EXISTS blocks_au AFTER UPDATE ON blocks BEGIN
    INSERT INTO blocks_fts(blocks_fts, rowid, tokenized_content)
        VALUES('delete', old.rowid, old.tokenized_content);
    INSERT INTO blocks_fts(rowid, tokenized_content)
        VALUES (new.rowid, new.tokenized_content);
END;
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    return conn


def existing_files(conn: sqlite3.Connection) -> dict[str, tuple[float, int]]:
    rows = conn.execute("SELECT file_path, mtime, file_size FROM pages").fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def insert_page(
    conn: sqlite3.Connection, page: Page, mtime: float, file_size: int
) -> None:
    conn.execute(
        "INSERT INTO pages "
        "(name, title, type, file_path, journal_day, namespace_parent, "
        " properties_json, aliases_json, mtime, file_size) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            page.name,
            page.title,
            page.type,
            page.file_path,
            page.journal_day,
            page.namespace_parent,
            json.dumps(page.properties, ensure_ascii=False),
            json.dumps(page.aliases, ensure_ascii=False),
            mtime,
            file_size,
        ),
    )
    for block in page.blocks:
        insert_block(conn, block)


def insert_block(conn: sqlite3.Connection, block: Block) -> None:
    from .tokenize import tokenize_for_index

    conn.execute(
        "INSERT INTO blocks "
        "(uuid, page, parent_uuid, sibling_order, depth, marker, content, "
        " tokenized_content, properties_json, has_explicit_id, "
        " line_start, line_end) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            block.uuid,
            block.page,
            block.parent_uuid,
            block.sibling_order,
            block.depth,
            block.marker,
            block.content,
            tokenize_for_index(block.content),
            json.dumps(block.properties, ensure_ascii=False),
            int(block.has_explicit_id),
            block.line_start,
            block.line_end,
        ),
    )
    for ref in block.refs:
        conn.execute(
            "INSERT INTO refs (block_uuid, kind, target, raw) VALUES (?, ?, ?, ?)",
            (block.uuid, ref.kind, ref.target, ref.raw),
        )
