from __future__ import annotations

import json
from pathlib import Path

import pytest

from logseq.parser import parse
from logseq.serializer import to_dict

FIXTURES = Path(__file__).parent / "fixtures"

PAGE_REQUIRED_KEYS = {
    "name",
    "title",
    "type",
    "file_path",
    "properties",
    "aliases",
    "namespace_parent",
    "journal_day",
    "block_count",
}

BLOCK_REQUIRED_KEYS = {
    "uuid",
    "has_explicit_id",
    "page",
    "parent_uuid",
    "sibling_order",
    "depth",
    "marker",
    "content",
    "properties",
    "refs",
    "line_start",
    "line_end",
}

REF_KEYS = {"kind", "target", "raw"}


@pytest.mark.parametrize(
    "md_path",
    sorted(FIXTURES.glob("*.md")),
    ids=lambda p: p.name if isinstance(p, Path) else None,
)
def test_to_dict_contract(md_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    page = parse(text, str(md_path))
    out = to_dict(page)

    assert set(out.keys()) == {"page", "blocks"}, "top-level keys"

    page_obj = out["page"]
    assert set(page_obj.keys()) == PAGE_REQUIRED_KEYS, (
        f"page keys mismatch in {md_path.name}: got {set(page_obj.keys())}"
    )
    assert isinstance(page_obj["properties"], dict)
    assert isinstance(page_obj["aliases"], list)
    assert page_obj["type"] in ("page", "journal")
    if page_obj["journal_day"] is not None:
        assert isinstance(page_obj["journal_day"], int)
        assert 19700101 <= page_obj["journal_day"] <= 99991231
    assert isinstance(page_obj["block_count"], int)
    assert page_obj["block_count"] == len(out["blocks"])

    for i, block in enumerate(out["blocks"]):
        loc = f"{md_path.name}[{i}]"
        assert set(block.keys()) == BLOCK_REQUIRED_KEYS, (
            f"{loc} block keys mismatch: got {set(block.keys())}"
        )
        assert isinstance(block["uuid"], str)
        assert isinstance(block["has_explicit_id"], bool)
        assert isinstance(block["depth"], int)
        assert isinstance(block["sibling_order"], int)
        assert block["marker"] is None or isinstance(block["marker"], str)
        assert isinstance(block["properties"], dict)
        assert isinstance(block["refs"], list)
        for ref in block["refs"]:
            assert set(ref.keys()) == REF_KEYS, f"{loc} ref keys: got {set(ref.keys())}"
            assert ref["kind"] in ("page", "tag", "block", "embed")
        assert "raw_lines" not in block, f"{loc} raw_lines must not leak into JSON"

    json.dumps(out, ensure_ascii=False)


def test_block_count_zero_on_empty_page(tmp_path: Path) -> None:
    f = tmp_path / "Empty.md"
    f.write_text("alias:: stub\n", encoding="utf-8")  # properties only, no bullets
    page = parse(f.read_text(encoding="utf-8"), str(f))
    out = to_dict(page)
    assert out["page"]["block_count"] == 0
    assert out["blocks"] == []
