from __future__ import annotations

from typing import Any

from .model import Block, Page


def serialize(page: Page) -> str:
    parts: list[str] = []
    parts.extend(page.header_raw_lines)
    for block in page.blocks:
        parts.extend(block.raw_lines)
    return "".join(parts)


def to_dict(page: Page) -> dict[str, Any]:
    return {
        "page": {
            "name": page.name,
            "title": page.title,
            "type": page.type,
            "file_path": page.file_path,
            "properties": page.properties,
            "aliases": page.aliases,
            "namespace_parent": page.namespace_parent,
            "journal_day": page.journal_day,
            "block_count": len(page.blocks),
        },
        "blocks": [_block_to_dict(b) for b in page.blocks],
    }


def _block_to_dict(b: Block) -> dict[str, Any]:
    return {
        "uuid": b.uuid,
        "has_explicit_id": b.has_explicit_id,
        "page": b.page,
        "parent_uuid": b.parent_uuid,
        "sibling_order": b.sibling_order,
        "depth": b.depth,
        "marker": b.marker,
        "content": b.content,
        "properties": b.properties,
        "refs": [{"kind": r.kind, "target": r.target, "raw": r.raw} for r in b.refs],
        "line_start": b.line_start,
        "line_end": b.line_end,
    }
