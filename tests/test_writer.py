"""Stage 6a: certify that construct_block + append_block produce text our
parser fully recovers — including on every real-world file in our 1122-file
corpus. User point: 'since the parser is hand-written, all our document
cases must pass'."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from logseq.parser import parse
from logseq.serializer import serialize
from logseq.writer import (
    FileChangedDuringWrite,
    append_block,
    append_to_page_file,
    append_to_today,
    construct_block,
)

# ============================================================================
# Block construction roundtrip — matrix of representative content shapes
# ============================================================================

CONSTRUCT_CASES: list[tuple[str, dict]] = [
    # (label, kwargs to construct_block)
    ("plain", {"content": "hello world"}),
    ("starts-with-dash", {"content": "- not a real bullet"}),
    ("marker-TODO", {"content": "write notes", "marker": "TODO"}),
    ("marker-DOING", {"content": "polish PR", "marker": "DOING"}),
    ("marker-DONE", {"content": "shipped it", "marker": "DONE"}),
    ("page-ref", {"content": "see [[Trantor]] for details"}),
    ("tag-bare", {"content": "discussion #physics"}),
    ("tag-bracket", {"content": "topic #[[Open Source]]"}),
    ("block-ref", {"content": "as per ((11111111-1111-1111-1111-111111111111))"}),
    ("embed", {"content": "{{embed ((22222222-2222-2222-2222-222222222222))}}"}),
    ("mixed-refs", {"content": "[[Foo]] then #bar then ((33333333-3333-3333-3333-333333333333))"}),
    ("depth-1", {"content": "first child", "depth": 1}),
    ("depth-3", {"content": "deep child", "depth": 3}),
    ("with-props", {"content": "task", "properties": {"prio": "A", "owner": "me"}}),
    ("with-explicit-id", {
        "content": "anchor block",
        "explicit_id": "44444444-4444-4444-4444-444444444444",
    }),
    ("marker-and-ref", {
        "content": "ship [[Trantor]] DSL refactor",
        "marker": "TODO",
    }),
    ("marker-and-props", {
        "content": "review PR",
        "marker": "DOING",
        "properties": {"prio": "B"},
    }),
    ("cjk-content", {"content": "中文内容也要 work 啊"}),
    ("cjk-ref", {"content": "看了 [[费曼]] 的访谈"}),
    ("punctuation-heavy", {"content": "edge: foo, bar; baz? \"quoted\" 'apos'"}),
    ("colon-in-content-not-property", {"content": "ratio 3:1 means..."}),
    ("nested-with-everything", {
        "content": "implement [[Foo]] #urgent",
        "depth": 2,
        "marker": "TODO",
        "properties": {"deadline": "2026-06-01"},
        "explicit_id": "55555555-5555-5555-5555-555555555555",
    }),
]


@pytest.mark.parametrize(
    "label,kwargs",
    CONSTRUCT_CASES,
    ids=[c[0] for c in CONSTRUCT_CASES],
)
def test_construct_block_roundtrips(label: str, kwargs: dict) -> None:
    block = construct_block(**kwargs)
    text = "".join(block.raw_lines)
    recovered_page = parse(text, "/tmp/test.md")
    assert len(recovered_page.blocks) == 1, (
        f"[{label}] expected 1 block, got {len(recovered_page.blocks)}"
    )
    rb = recovered_page.blocks[0]
    assert rb.content == block.content, f"[{label}] content mismatch"
    assert rb.depth == block.depth, f"[{label}] depth mismatch"
    assert rb.marker == block.marker, f"[{label}] marker mismatch"
    assert rb.properties == block.properties, (
        f"[{label}] properties mismatch: got {rb.properties}, want {block.properties}"
    )
    if kwargs.get("explicit_id"):
        assert rb.has_explicit_id, f"[{label}] should have explicit id"
        assert rb.uuid == kwargs["explicit_id"], f"[{label}] uuid mismatch"
    else:
        assert not rb.has_explicit_id, f"[{label}] should not have explicit id"
    got_refs = [(r.kind, r.target) for r in rb.refs]
    want_refs = [(r.kind, r.target) for r in block.refs]
    assert got_refs == want_refs, f"[{label}] refs mismatch: got {got_refs}, want {want_refs}"


# ============================================================================
# Validation errors — refuse to construct what parser can't safely re-read
# ============================================================================


def test_construct_rejects_multiline_content() -> None:
    with pytest.raises(ValueError, match="multi-line"):
        construct_block("line one\nline two")


def test_construct_rejects_carriage_return() -> None:
    with pytest.raises(ValueError, match="multi-line"):
        construct_block("with CR\rin middle")


def test_construct_rejects_logbook_marker() -> None:
    with pytest.raises(ValueError, match=r"LOGBOOK|parser state"):
        construct_block(":LOGBOOK:")


def test_construct_rejects_end_marker() -> None:
    with pytest.raises(ValueError, match=r"LOGBOOK|parser state"):
        construct_block(":END:")


def test_construct_rejects_multiline_property_value() -> None:
    with pytest.raises(ValueError, match="multi-line"):
        construct_block("ok", properties={"bad": "line1\nline2"})


# ============================================================================
# append_block roundtrip — append to various pages, re-parse, verify
# ============================================================================


def _page_from_text(text: str, file_path: str = "/tmp/test.md"):
    return parse(text, file_path)


def test_append_to_empty_page() -> None:
    page = _page_from_text("")
    new = construct_block("first ever block")
    updated = append_block(page, new)
    text = serialize(updated)
    reparsed = parse(text, "/tmp/test.md")
    assert len(reparsed.blocks) == 1
    assert reparsed.blocks[0].content == "first ever block"


def test_append_to_header_only_page() -> None:
    page = _page_from_text("alias:: stub\ntags:: bookshelf\n")
    new = construct_block("first content block", marker="TODO")
    updated = append_block(page, new)
    text = serialize(updated)
    reparsed = parse(text, "/tmp/test.md")
    # Header properties preserved
    assert reparsed.properties == {"alias": "stub", "tags": "bookshelf"}
    assert len(reparsed.blocks) == 1
    assert reparsed.blocks[0].content == "first content block"
    assert reparsed.blocks[0].marker == "TODO"


def test_append_to_page_with_blocks() -> None:
    initial = "- existing one\n- existing two\n"
    page = _page_from_text(initial)
    new = construct_block("new third")
    updated = append_block(page, new)
    text = serialize(updated)
    reparsed = parse(text, "/tmp/test.md")
    assert [b.content for b in reparsed.blocks] == ["existing one", "existing two", "new third"]


def test_append_as_sibling_sets_sibling_order() -> None:
    page = _page_from_text("- alpha\n- beta\n")
    new = construct_block("gamma", depth=0)
    updated = append_block(page, new)
    assert updated.blocks[-1].parent_uuid is None
    assert updated.blocks[-1].sibling_order == 2


def test_append_as_child_sets_parent_uuid() -> None:
    page = _page_from_text("- parent\n")
    parent_uuid = page.blocks[0].uuid
    new = construct_block("child", depth=1)
    updated = append_block(page, new)
    assert updated.blocks[-1].parent_uuid == parent_uuid
    assert updated.blocks[-1].depth == 1


def test_append_grandchild() -> None:
    page = _page_from_text("- parent\n\t- child\n")
    child_uuid = page.blocks[1].uuid
    new = construct_block("grandchild", depth=2)
    updated = append_block(page, new)
    text = serialize(updated)
    reparsed = parse(text, "/tmp/test.md")
    assert reparsed.blocks[-1].depth == 2
    # parent in our updated structure is the existing child
    assert updated.blocks[-1].parent_uuid == child_uuid


# ============================================================================
# Corpus regression — append a constructed block to EVERY existing fixture
# and assert the resulting text still parses cleanly with all original
# blocks preserved + new block present.
# ============================================================================


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "fixture_path",
    sorted(FIXTURES.glob("*.md")),
    ids=lambda p: p.name if isinstance(p, Path) else None,
)
def test_corpus_fixture_survives_append(fixture_path: Path) -> None:
    original = fixture_path.read_text(encoding="utf-8")
    page = parse(original, str(fixture_path))
    original_count = len(page.blocks)

    new = construct_block("appended sentinel block")
    updated = append_block(page, new)
    text = serialize(updated)
    reparsed = parse(text, str(fixture_path))

    assert len(reparsed.blocks) == original_count + 1, (
        f"block count changed unexpectedly: {original_count} → {len(reparsed.blocks)}"
    )
    # Original blocks' content preserved (by index)
    for i in range(original_count):
        assert reparsed.blocks[i].content == page.blocks[i].content, (
            f"existing block {i} content drifted"
        )
    # New block intact at the end
    assert reparsed.blocks[-1].content == "appended sentinel block"


# ============================================================================
# Real-vault corpus — same regression on every file in the real vault
# (skipped when LOGSEQ_VAULT / default vault not present).
# This is the "几百份" the user pointed to as enough volume.
# ============================================================================


VAULT_PATH = Path(
    os.environ.get("LOGSEQ_VAULT", "/Users/bencode/Documents/bcd-new")
)


def _vault_md_files() -> list[Path]:
    if not VAULT_PATH.exists():
        return []
    out: list[Path] = []
    for sub in ("journals", "pages"):
        d = VAULT_PATH / sub
        if d.exists():
            out.extend(sorted(d.glob("*.md")))
    return out


_VAULT_FILES = _vault_md_files()


@pytest.mark.skipif(not _VAULT_FILES, reason=f"vault not found at {VAULT_PATH}")
@pytest.mark.parametrize(
    "vault_md", _VAULT_FILES, ids=lambda p: p.name if isinstance(p, Path) else None
)
def test_real_vault_file_survives_append(vault_md: Path) -> None:
    """For every real-world .md in the user's vault: parse → append a
    constructed block → serialize → parse → assert the result is well-formed
    and the original blocks are preserved. This is the 'all our document
    cases must pass' guarantee for hand-written parsing."""
    original_bytes = vault_md.read_bytes()
    try:
        original = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        pytest.skip(f"file not utf-8: {vault_md}")
    page = parse(original, str(vault_md))
    original_count = len(page.blocks)

    new = construct_block("__test_sentinel__", explicit_id="00000000-0000-0000-0000-000000000001")
    updated = append_block(page, new)
    text = serialize(updated)
    reparsed = parse(text, str(vault_md))

    assert len(reparsed.blocks) == original_count + 1, (
        f"{vault_md.name}: block count changed {original_count} → {len(reparsed.blocks)}"
    )
    # Check existing blocks' content is byte-equal in order
    for i in range(original_count):
        assert reparsed.blocks[i].content == page.blocks[i].content, (
            f"{vault_md.name}: block {i} content drifted"
        )
    # New block at the end with the sentinel content + explicit id
    assert reparsed.blocks[-1].content == "__test_sentinel__"
    assert reparsed.blocks[-1].uuid == "00000000-0000-0000-0000-000000000001"
    assert reparsed.blocks[-1].has_explicit_id


# ============================================================================
# Stage 6b: file-level write API — atomic write + race detection
# ============================================================================


def test_append_to_page_file_creates_new_file(tmp_path: Path) -> None:
    path = tmp_path / "Fresh.md"
    uuid = append_to_page_file(path, "first content here", marker="TODO")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "TODO first content here" in text
    # uuid is auto:<sha1> since no explicit_id
    assert uuid.startswith("auto:")


def test_append_to_page_file_preserves_existing_content(tmp_path: Path) -> None:
    path = tmp_path / "Existing.md"
    path.write_text("- block one\n- block two\n", encoding="utf-8")
    append_to_page_file(path, "block three")
    page = parse(path.read_text(encoding="utf-8"), str(path))
    assert [b.content for b in page.blocks] == ["block one", "block two", "block three"]


def test_append_to_page_file_with_explicit_id_returns_it(tmp_path: Path) -> None:
    path = tmp_path / "WithId.md"
    target_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    returned = append_to_page_file(path, "anchored", explicit_id=target_id)
    assert returned == target_id
    page = parse(path.read_text(encoding="utf-8"), str(path))
    assert page.blocks[-1].uuid == target_id
    assert page.blocks[-1].has_explicit_id


def test_append_to_page_file_is_atomic_no_tmp_leftover(tmp_path: Path) -> None:
    path = tmp_path / "Foo.md"
    append_to_page_file(path, "x")
    tmp = path.with_name(path.name + ".tmp")
    assert not tmp.exists(), "tmp file leaked after successful write"


def test_append_to_page_file_detects_concurrent_change(tmp_path: Path) -> None:
    import os as _os
    import time as _time

    path = tmp_path / "Racing.md"
    path.write_text("- initial\n", encoding="utf-8")
    # Force a future mtime so the post-construct stat check fails
    fake_future = _time.time() + 1000
    _os.utime(path, (fake_future, fake_future))

    # Monkey-patch the parse step's mtime check by writing the file again
    # mid-flight. Easier: directly call and assert RuntimeError by simulating
    # a change between two calls. Simplest test: directly modify mtime to
    # simulate the race.
    # We can also: read file, then re-touch it before our write triggers
    # the comparison. Construct a minimal repro using stat differences.
    from logseq import writer as wr

    # Mock the stat by patching: read, then between parse and stat, mutate
    # the file's mtime. Easiest: monkeypatch Path.stat to return changing
    # values. Use a simpler integration approach — write the file out-of-band
    # using a sibling helper to bump mtime.

    # Capture before_mtime in append_to_page_file = current stat.
    # Then before write, file's mtime must differ to raise. Achieved by
    # touching the file inside the call. Hack: patch Path.read_text to
    # also bump mtime via os.utime so the subsequent stat returns a
    # different value.
    real_read = Path.read_text

    def racing_read(self, *args, **kwargs):
        out = real_read(self, *args, **kwargs)
        # Bump mtime AFTER read so the stat check at write time differs
        st = self.stat()
        _os.utime(self, (st.st_atime, st.st_mtime + 100))
        return out

    Path.read_text = racing_read  # type: ignore[method-assign]
    try:
        with pytest.raises(FileChangedDuringWrite):
            wr.append_to_page_file(path, "racy")
    finally:
        Path.read_text = real_read  # type: ignore[method-assign]


def test_append_to_today_creates_journal_if_missing(tmp_path: Path) -> None:
    from datetime import date as _date

    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")

    p = append_to_today(vault, "captured from terminal", marker="TODO")
    expected_name = "_".join(_date.today().isoformat().split("-")) + ".md"
    assert p.name == expected_name
    assert p.exists()
    page = parse(p.read_text(encoding="utf-8"), str(p))
    assert page.blocks[-1].content == "captured from terminal"
    assert page.blocks[-1].marker == "TODO"


def test_append_to_today_appends_to_existing_journal(tmp_path: Path) -> None:
    from datetime import date as _date

    vault = tmp_path / "vault"
    (vault / "logseq").mkdir(parents=True)
    (vault / "logseq" / "config.edn").write_text("{}", encoding="utf-8")
    journals = vault / "journals"
    journals.mkdir()
    fname = "_".join(_date.today().isoformat().split("-")) + ".md"
    (journals / fname).write_text("- morning task\n", encoding="utf-8")

    append_to_today(vault, "afternoon thought")
    page = parse((journals / fname).read_text(encoding="utf-8"), str(journals / fname))
    assert [b.content for b in page.blocks] == ["morning task", "afternoon thought"]
