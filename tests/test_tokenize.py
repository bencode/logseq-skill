"""Tests for the jieba-based CJK tokenization layer.

Specifically: the false-positive regression test (`学生` must not match
`数学生活`) is the whole reason this module exists, so the test that
proves it works lives here."""

from __future__ import annotations

from pathlib import Path

from logseq.index import reindex
from logseq.queries import search
from logseq.tokenize import tokenize_for_index, tokenize_query


def test_tokenize_for_index_inserts_spaces_at_word_boundaries() -> None:
    # "数学女孩" is two jieba words → space-separated.
    out = tokenize_for_index("我看了数学女孩的第五本")
    parts = out.split(" ")
    assert "数学" in parts
    assert "女孩" in parts


def test_tokenize_for_index_keeps_ascii_words_intact() -> None:
    out = tokenize_for_index("trantor 维护 的 issue")
    parts = out.split()
    assert "trantor" in parts
    assert "维护" in parts


def test_tokenize_for_index_handles_empty() -> None:
    assert tokenize_for_index("") == ""
    assert tokenize_for_index("   ") == ""


def test_tokenize_query_simple_passes_through_jieba() -> None:
    # Plain Chinese query → jieba split, AND-of-tokens.
    out = tokenize_query("数学女孩")
    parts = out.split()
    assert parts == ["数学", "女孩"]


def test_tokenize_query_preserves_fts_operators() -> None:
    # AND/OR survive; phrases inside quotes are re-tokenized.
    out = tokenize_query("数学 AND 物理")
    # Operators stay; tokens still split where applicable
    assert "AND" in out


def test_tokenize_query_tokenizes_inside_quoted_phrase() -> None:
    # User typed "数学女孩" with quotes → we tokenize inside, FTS5 then
    # treats as adjacent phrase (which matches because index also has
    # them adjacent).
    out = tokenize_query('"数学女孩"')
    assert out == '"数学 女孩"'


def test_search_finds_substring_word(
    tmp_path: Path, monkeypatch
) -> None:
    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    """The main use case: user searches '数学' and finds blocks
    containing '数学女孩' (because jieba indexes 数学 as its own word)."""
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (vault / "pages").mkdir()
    (vault / "pages" / "Books.md").write_text(
        "- 数学女孩看完了\n- 关于物理的笔记\n", encoding="utf-8"
    )
    reindex(vault)

    # Search for the prefix word
    hits = search(vault, "数学")
    assert len(hits) == 1
    assert "数学女孩" in hits[0]["content"]


def test_search_no_false_positive_for_substring_across_words(
    tmp_path: Path, monkeypatch
) -> None:
    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    """The crown jewel: `学生` must NOT match `数学生活` because jieba
    splits them as 数学/生活 (no token '学生' indexed). This is the
    false-positive failure mode unicode61 (and LIKE) suffer from."""
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (vault / "pages").mkdir()
    (vault / "pages" / "A.md").write_text(
        "- 数学生活的乐趣\n", encoding="utf-8"
    )
    (vault / "pages" / "B.md").write_text(
        "- 学生时代很美好\n", encoding="utf-8"
    )
    reindex(vault)

    hits = search(vault, "学生")
    # Should find B (which actually has 学生 as a word) but NOT A
    pages = {h["page"] for h in hits}
    assert "b" in pages
    assert "a" not in pages, (
        f"false positive: '学生' incorrectly matched 数学生活 in: "
        f"{[h['content'] for h in hits]}"
    )


def test_search_finds_block_ref_uuid(
    tmp_path: Path, monkeypatch
) -> None:
    from logseq import index as index_module

    monkeypatch.setattr(index_module, "CACHE_DIR", tmp_path / "cache")
    """Sanity check: ASCII / non-CJK search still works after the
    tokenizer change."""
    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    (vault / "pages").mkdir()
    (vault / "pages" / "Notes.md").write_text(
        "- trantor 维护问题\n- feynman 物理课\n", encoding="utf-8"
    )
    reindex(vault)

    hits_en = search(vault, "trantor")
    assert len(hits_en) == 1
    hits_cn = search(vault, "维护")
    assert len(hits_cn) == 1
    hits_mixed = search(vault, "feynman 物理")
    assert len(hits_mixed) == 1
