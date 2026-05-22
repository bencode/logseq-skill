from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "logseq"]


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI + args, capture_output=True, text=True, encoding="utf-8"
    )


@pytest.fixture
def fake_vault(tmp_path: Path) -> Path:
    (tmp_path / "logseq").mkdir()
    (tmp_path / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (tmp_path / "journals").mkdir()
    (tmp_path / "pages").mkdir()
    return tmp_path


def test_journal_requires_in(fake_vault: Path) -> None:
    result = run(["journal", "2024-01-15"])
    assert result.returncode != 0
    assert "--in" in (result.stderr + result.stdout)


def test_journal_finds_file(fake_vault: Path) -> None:
    (fake_vault / "journals" / "2024_01_15.md").write_text(
        "- Morning routine\n- [[Project X]]\n", encoding="utf-8"
    )
    result = run(["journal", "2024-01-15", "--in", str(fake_vault)])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["page"]["journal_day"] == 20240115
    assert data["page"]["type"] == "journal"
    assert len(data["blocks"]) == 2


def test_journal_missing_date(fake_vault: Path) -> None:
    result = run(["journal", "2099-12-31", "--in", str(fake_vault)])
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_journal_invalid_date(fake_vault: Path) -> None:
    result = run(["journal", "not-a-date", "--in", str(fake_vault)])
    assert result.returncode == 2


def test_find_page_exact(fake_vault: Path) -> None:
    target = fake_vault / "pages" / "Feynman.md"
    target.write_text("- physicist\n", encoding="utf-8")
    result = run(["find-page", "feynman", str(fake_vault)])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    kind, path = lines[0].split("\t", 1)
    assert kind == "exact"
    assert Path(path) == target.resolve()


def test_find_page_substring_fallback(fake_vault: Path) -> None:
    target = fake_vault / "pages" / "费曼语录.md"
    target.write_text("- quotes\n", encoding="utf-8")
    result = run(["find-page", "费曼", str(fake_vault)])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    kind, path = lines[0].split("\t", 1)
    assert kind == "substring"
    assert Path(path) == target.resolve()


def test_find_page_exact_preferred_over_substring(fake_vault: Path) -> None:
    exact = fake_vault / "pages" / "Feynman.md"
    sub = fake_vault / "pages" / "Feynman语录.md"
    exact.write_text("", encoding="utf-8")
    sub.write_text("", encoding="utf-8")
    result = run(["find-page", "feynman", str(fake_vault)])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("exact\t")


def test_find_page_no_match(fake_vault: Path) -> None:
    (fake_vault / "pages" / "OtherPage.md").write_text("", encoding="utf-8")
    result = run(["find-page", "nonexistent", str(fake_vault)])
    assert result.returncode == 1
    assert result.stdout == ""


def test_capture_creates_today_journal(tmp_path: Path) -> None:
    """`logseq capture` should write to today's journal (creating it if
    missing) and emit the journal path on stdout."""
    from datetime import date

    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")

    result = run(["capture", str(vault), "captured from CLI"])
    assert result.returncode == 0, result.stderr
    expected_name = "_".join(date.today().isoformat().split("-")) + ".md"
    journal = vault / "journals" / expected_name
    assert journal.exists()
    assert "captured from CLI" in journal.read_text(encoding="utf-8")
    # Returned path on stdout
    assert str(journal) in result.stdout


def test_capture_with_marker(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")

    result = run(["capture", str(vault), "write the blog post", "--marker", "TODO"])
    assert result.returncode == 0, result.stderr
    from datetime import date

    fname = "_".join(date.today().isoformat().split("-")) + ".md"
    text = (vault / "journals" / fname).read_text(encoding="utf-8")
    assert "TODO write the blog post" in text


def test_append_to_existing_page(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (vault / "pages").mkdir()
    (vault / "pages" / "Notes.md").write_text("- one\n- two\n", encoding="utf-8")

    result = run(["append", str(vault), "notes", "appended via CLI"])
    assert result.returncode == 0, result.stderr
    text = (vault / "pages" / "Notes.md").read_text(encoding="utf-8")
    assert "appended via CLI" in text
    # Original blocks preserved
    assert "- one" in text and "- two" in text


def test_append_emits_uuid_on_stdout(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (vault / "pages").mkdir()
    (vault / "pages" / "Foo.md").write_text("- existing\n", encoding="utf-8")

    result = run(["append", str(vault), "foo", "new content"])
    assert result.returncode == 0
    # First (and only) stdout line is the uuid
    uuid_out = result.stdout.strip().splitlines()[-1]
    assert uuid_out.startswith("auto:") or len(uuid_out) == 36


def test_append_returns_5_for_unknown_page(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")

    result = run(["append", str(vault), "NonexistentPage12345", "x"])
    assert result.returncode == 5
    assert "not found" in result.stderr


def test_capture_returns_2_for_non_vault(tmp_path: Path) -> None:
    # tmp_path has no logseq/config.edn
    result = run(["capture", str(tmp_path), "x"])
    assert result.returncode == 2
    assert "not a logseq vault" in result.stderr


def test_capture_auto_reindexes_if_index_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the user already has an index, `capture` should incrementally
    update it so the new block is searchable right away."""
    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (vault / "pages").mkdir()
    (vault / "pages" / "Seed.md").write_text("- starter\n", encoding="utf-8")
    # Build an index first
    from logseq.index import reindex

    reindex(vault)

    # Capture should auto-reindex (because index dir exists for this vault).
    # We can't easily monkeypatch the CACHE_DIR for the subprocess; instead,
    # invoke the cmd_capture function directly.
    from logseq.commands.write import cmd_capture

    rc = cmd_capture(str(vault), "fresh capture for FTS", marker=None)
    assert rc == 0
    # Now query the index — the new block should be findable
    from logseq.queries import search

    hits = search(vault, '"fresh capture"')
    assert len(hits) >= 1, "auto-reindex didn't pick up the captured block"


def test_find_page_non_empty_filters_empty_pages(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    # All three stems substring-match query "page"
    (pages / "EmptyPage.md").write_text("", encoding="utf-8")
    (pages / "PropertiesPage.md").write_text(
        "alias:: stub\n", encoding="utf-8"  # properties only, no bullets
    )
    (pages / "ContentPage.md").write_text(
        "- has content\n- more content\n", encoding="utf-8"
    )

    result = run(["find-page", "page", str(tmp_path)])
    assert result.returncode == 0
    assert "EmptyPage.md" in result.stdout
    assert "PropertiesPage.md" in result.stdout
    assert "ContentPage.md" in result.stdout

    result = run(["find-page", "page", str(tmp_path), "--non-empty"])
    assert result.returncode == 0
    assert "EmptyPage.md" not in result.stdout
    assert "PropertiesPage.md" not in result.stdout
    assert "ContentPage.md" in result.stdout


def test_index_returns_2_on_non_vault(tmp_path: Path) -> None:
    result = run(["index", str(tmp_path)])
    assert result.returncode == 2
    assert "not a logseq vault" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_stats_returns_2_on_non_vault(tmp_path: Path) -> None:
    result = run(["stats", str(tmp_path)])
    assert result.returncode == 2
    assert "not a logseq vault" in result.stderr
    assert "Traceback" not in result.stderr


def test_find_page_multi_dirs(tmp_path: Path) -> None:
    d1 = tmp_path / "vault1"
    d2 = tmp_path / "vault2"
    (d1 / "pages").mkdir(parents=True)
    (d2 / "pages").mkdir(parents=True)
    (d1 / "pages" / "Alpha.md").write_text("", encoding="utf-8")
    (d2 / "pages" / "Beta.md").write_text("", encoding="utf-8")
    result = run(["find-page", "beta", str(d1), str(d2)])
    assert result.returncode == 0, result.stderr
    assert "exact\t" in result.stdout
    assert str((d2 / "pages" / "Beta.md").resolve()) in result.stdout
