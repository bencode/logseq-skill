from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from logseq.index import db_path_for, reindex, stats


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "logseq").mkdir()
    (tmp_path / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (tmp_path / "journals").mkdir()
    (tmp_path / "pages").mkdir()
    return tmp_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def test_rejects_non_vault(tmp_path: Path, db_path: Path) -> None:
    with pytest.raises(ValueError, match="not a logseq vault"):
        reindex(tmp_path, db_path=db_path)


def test_full_index_writes_pages_blocks_refs(vault: Path, db_path: Path) -> None:
    (vault / "journals" / "2024_01_15.md").write_text(
        "- Morning routine\n- Read [[Project X]] and #tag1\n",
        encoding="utf-8",
    )
    (vault / "pages" / "Feynman.md").write_text(
        "alias:: feyn\n- physicist\n", encoding="utf-8"
    )
    result = reindex(vault, db_path=db_path)
    assert result.scanned == 2 and result.reindexed == 2 and result.skipped == 0

    conn = _connect(db_path)
    pages = conn.execute("SELECT name, type FROM pages ORDER BY name").fetchall()
    assert pages == [("2024_01_15", "journal"), ("feynman", "page")]
    assert conn.execute("SELECT count(*) FROM blocks").fetchone()[0] == 3
    page_refs = conn.execute(
        "SELECT target FROM refs WHERE kind='page'"
    ).fetchall()
    tag_refs = conn.execute(
        "SELECT target FROM refs WHERE kind='tag'"
    ).fetchall()
    assert ("Project X",) in page_refs
    assert ("tag1",) in tag_refs


def test_incremental_skips_unchanged(vault: Path, db_path: Path) -> None:
    (vault / "pages" / "A.md").write_text("- a\n", encoding="utf-8")
    (vault / "pages" / "B.md").write_text("- b\n", encoding="utf-8")
    reindex(vault, db_path=db_path)

    again = reindex(vault, db_path=db_path)
    assert again.scanned == 2 and again.skipped == 2 and again.reindexed == 0


def test_incremental_picks_up_modified(vault: Path, db_path: Path) -> None:
    f = vault / "pages" / "A.md"
    f.write_text("- old\n", encoding="utf-8")
    (vault / "pages" / "B.md").write_text("- b\n", encoding="utf-8")
    reindex(vault, db_path=db_path)

    # bump mtime + change content
    f.write_text("- new content\n", encoding="utf-8")
    os.utime(f, (time.time() + 10, time.time() + 10))

    result = reindex(vault, db_path=db_path)
    assert result.reindexed == 1 and result.skipped == 1

    conn = _connect(db_path)
    content = conn.execute(
        "SELECT content FROM blocks WHERE page='a'"
    ).fetchone()[0]
    assert content == "new content"


def test_cascade_delete_on_file_removal(vault: Path, db_path: Path) -> None:
    f = vault / "pages" / "Doomed.md"
    f.write_text("- bye [[X]]\n", encoding="utf-8")
    reindex(vault, db_path=db_path)
    f.unlink()

    result = reindex(vault, db_path=db_path)
    assert result.deleted == 1

    conn = _connect(db_path)
    assert conn.execute("SELECT count(*) FROM pages WHERE name='doomed'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM blocks WHERE page='doomed'").fetchone()[0] == 0
    # CASCADE through blocks → refs
    assert conn.execute(
        "SELECT count(*) FROM refs WHERE target='X'"
    ).fetchone()[0] == 0


def test_fts_search_works(vault: Path, db_path: Path) -> None:
    (vault / "pages" / "Notes.md").write_text(
        "- learning quantum mechanics\n- feynman diagrams are useful\n",
        encoding="utf-8",
    )
    reindex(vault, db_path=db_path)

    conn = _connect(db_path)
    hits = conn.execute(
        "SELECT content FROM blocks_fts WHERE blocks_fts MATCH 'feynman'"
    ).fetchall()
    assert len(hits) == 1
    assert "feynman" in hits[0][0]


def test_full_rebuild_wipes_existing(vault: Path, db_path: Path) -> None:
    f = vault / "pages" / "A.md"
    f.write_text("- v1\n", encoding="utf-8")
    reindex(vault, db_path=db_path)
    assert db_path.exists()
    first_size = db_path.stat().st_size

    f.write_text("- v2\n", encoding="utf-8")
    os.utime(f, (time.time() + 10, time.time() + 10))
    result = reindex(vault, db_path=db_path, full=True)
    assert result.reindexed == 1 and result.skipped == 0

    conn = _connect(db_path)
    content = conn.execute("SELECT content FROM blocks WHERE page='a'").fetchone()[0]
    assert content == "v2"
    # DB still around
    assert db_path.stat().st_size > 0
    assert first_size  # silence unused


def test_stats_reports_counts(vault: Path, db_path: Path) -> None:
    (vault / "pages" / "A.md").write_text("- a [[B]]\n", encoding="utf-8")
    reindex(vault, db_path=db_path)

    s = stats(vault, db_path=db_path)
    assert s["db_exists"] is True
    assert s["pages"] == 1 and s["blocks"] == 1 and s["refs"] == 1
    assert s["db_size_bytes"] > 0
    assert s["schema_version"] == "1"
    assert s["last_index_ts"] is not None


def test_stats_when_no_db(vault: Path, db_path: Path) -> None:
    s = stats(vault, db_path=db_path)
    assert s["db_exists"] is False
    assert s["pages"] == 0 and s["blocks"] == 0 and s["refs"] == 0


def test_cross_file_uuid_collision_does_not_corrupt_fts(
    vault: Path, db_path: Path
) -> None:
    same_id = "11111111-1111-1111-1111-111111111111"
    (vault / "pages" / "A.md").write_text(
        f"- alpha bravo\n  id:: {same_id}\n", encoding="utf-8"
    )
    (vault / "pages" / "B.md").write_text(
        f"- charlie delta\n  id:: {same_id}\n", encoding="utf-8"
    )
    result = reindex(vault, db_path=db_path)
    assert result.errors >= 1

    conn = _connect(db_path)
    content = conn.execute(
        "SELECT content FROM blocks WHERE uuid=?", (same_id,)
    ).fetchone()[0]
    assert content == "alpha bravo"  # A.md sorts first → wins

    # Regression: FTS5 MATCH must not raise on either token
    hits_alpha = conn.execute(
        "SELECT count(*) FROM blocks_fts WHERE blocks_fts MATCH 'alpha'"
    ).fetchone()[0]
    hits_charlie = conn.execute(
        "SELECT count(*) FROM blocks_fts WHERE blocks_fts MATCH 'charlie'"
    ).fetchone()[0]
    assert hits_alpha == 1
    assert hits_charlie == 0  # B.md's duplicate was skipped


def test_canonical_paths_produce_same_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")

    v = tmp_path / "vault"
    (v / "logseq").mkdir(parents=True)
    (v / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (v / "pages").mkdir()
    (v / "pages" / "A.md").write_text("- hello\n", encoding="utf-8")

    r1 = reindex(v)
    assert r1.reindexed == 1

    v_with_dots = Path(str(v) + "/././.")
    r2 = reindex(v_with_dots)
    assert r2.reindexed == 0 and r2.skipped == 1

    assert stats(v)["db_path"] == stats(v_with_dots)["db_path"]


def test_unicode_decode_error_skips_only_bad_file(
    vault: Path, db_path: Path
) -> None:
    (vault / "pages" / "Good.md").write_text(
        "- valid content\n", encoding="utf-8"
    )
    (vault / "pages" / "Bad.md").write_bytes(
        b"\xff\xfe not valid utf-8 \x80\x81"
    )

    result = reindex(vault, db_path=db_path)
    assert result.errors == 1
    assert result.reindexed == 1

    conn = _connect(db_path)
    pages = {row[0] for row in conn.execute("SELECT name FROM pages")}
    assert "good" in pages
    assert "bad" not in pages


def test_full_rebuild_preserves_old_db_on_parse_failure(
    vault: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (vault / "pages" / "A.md").write_text("- alpha\n", encoding="utf-8")
    (vault / "pages" / "B.md").write_text("- beta\n", encoding="utf-8")
    reindex(vault, db_path=db_path)

    conn = _connect(db_path)
    pages_before = sorted(
        row[0] for row in conn.execute("SELECT name FROM pages")
    )
    conn.close()
    assert pages_before == ["a", "b"]

    from logseq import index as index_module

    original_parse = index_module.parse
    calls = [0]

    def flaky_parse(*args: object, **kwargs: object) -> object:
        calls[0] += 1
        if calls[0] >= 2:
            raise RuntimeError("simulated parse failure")
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(index_module, "parse", flaky_parse)

    with pytest.raises(RuntimeError):
        reindex(vault, db_path=db_path, full=True)

    assert db_path.exists(), "live DB was destroyed by failed rebuild"
    conn = _connect(db_path)
    pages_after = sorted(
        row[0] for row in conn.execute("SELECT name FROM pages")
    )
    conn.close()
    assert pages_after == pages_before
