from __future__ import annotations

import difflib
import os
from pathlib import Path

import pytest

from logseq.parser import parse
from logseq.serializer import serialize

FIXTURES = Path(__file__).parent / "fixtures"
# Real-vault corpus regression: set LOGSEQ_VAULT to a directory containing
# `journals/` and/or `pages/` to enable ~1100 additional round-trip tests
# across real .md files. No fallback default — the corpus tests skip when
# the env var is unset.
VAULT_PATH = Path(os.environ["LOGSEQ_VAULT"]) if os.environ.get("LOGSEQ_VAULT") else None


def fixture_files() -> list[Path]:
    return sorted(FIXTURES.glob("*.md"))


def vault_files() -> list[Path]:
    if VAULT_PATH is None or not VAULT_PATH.exists():
        return []
    out: list[Path] = []
    for sub in ("journals", "pages"):
        d = VAULT_PATH / sub
        if d.exists():
            out.extend(sorted(d.glob("*.md")))
    return out


def _roundtrip(path: Path) -> None:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    page = parse(text, str(path))
    out = serialize(page)
    if out != text:
        diff = "\n".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                out.splitlines(keepends=True),
                fromfile=f"{path}:original",
                tofile=f"{path}:roundtrip",
                lineterm="",
            )
        )
        pytest.fail(f"round-trip mismatch in {path}:\n{diff[:2000]}")


@pytest.mark.parametrize(
    "path", fixture_files(), ids=lambda p: p.name if isinstance(p, Path) else None
)
def test_fixture_roundtrip(path: Path) -> None:
    _roundtrip(path)


_VAULT_FILES = vault_files()


@pytest.mark.skipif(not _VAULT_FILES, reason=f"vault not found at {VAULT_PATH}")
@pytest.mark.parametrize(
    "path", _VAULT_FILES, ids=lambda p: p.name if isinstance(p, Path) else None
)
def test_vault_roundtrip(path: Path) -> None:
    _roundtrip(path)
