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
