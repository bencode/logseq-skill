from __future__ import annotations

import json
from pathlib import Path

import pytest

from logseq.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_cases() -> list[tuple[str, Path, Path]]:
    cases = []
    for md in sorted(FIXTURES.glob("*.md")):
        expected = md.with_suffix(".expected.json")
        if expected.exists():
            cases.append((md.stem, md, expected))
    return cases


@pytest.mark.parametrize(
    "name,md_path,expected_path",
    fixture_cases(),
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_fixture_semantics(name: str, md_path: Path, expected_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    page = parse(text, str(md_path))

    if "page_properties" in expected:
        assert page.properties == expected["page_properties"], (
            f"page_properties mismatch in {name}"
        )
    for attr in ("title", "type", "journal_day", "namespace_parent"):
        if attr in expected:
            assert getattr(page, attr) == expected[attr], (
                f"page.{attr} mismatch in {name}: got {getattr(page, attr)!r}"
            )
    if "aliases" in expected:
        assert page.aliases == expected["aliases"], f"page.aliases mismatch in {name}"

    expected_blocks = expected["blocks"]
    assert len(page.blocks) == len(expected_blocks), (
        f"block count mismatch in {name}: got {len(page.blocks)} expected {len(expected_blocks)}"
    )

    for i, (got, want) in enumerate(zip(page.blocks, expected_blocks)):
        loc = f"{name}[{i}]"
        if "depth" in want:
            assert got.depth == want["depth"], f"{loc} depth"
        if "content" in want:
            assert got.content == want["content"], f"{loc} content"
        if "has_explicit_id" in want:
            assert got.has_explicit_id == want["has_explicit_id"], f"{loc} has_explicit_id"
        if "explicit_id" in want:
            assert got.uuid == want["explicit_id"], f"{loc} explicit_id"
        if "parent_index" in want:
            if want["parent_index"] is None:
                assert got.parent_uuid is None, f"{loc} parent_uuid should be None"
            else:
                expected_parent_uuid = page.blocks[want["parent_index"]].uuid
                assert got.parent_uuid == expected_parent_uuid, f"{loc} parent_uuid"
        if "sibling_order" in want:
            assert got.sibling_order == want["sibling_order"], f"{loc} sibling_order"
        if "marker" in want:
            assert got.marker == want["marker"], f"{loc} marker"
        if "properties_keys" in want:
            assert sorted(got.properties.keys()) == sorted(want["properties_keys"]), (
                f"{loc} properties_keys, got {sorted(got.properties.keys())}"
            )
        if "refs" in want:
            got_refs = [{"kind": r.kind, "target": r.target} for r in got.refs]
            assert got_refs == want["refs"], f"{loc} refs, got {got_refs}"
