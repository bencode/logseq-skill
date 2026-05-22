"""Block construction primitives.

Stage 6a deliberately covers only what we can prove round-trips through
our own parser. File I/O lives in Stage 6b; CLI in 6c; TUI in 6d.

Constructed blocks are guaranteed to parse back with all structural
fields (content, marker, depth, properties, refs) preserved — the
property-based tests in tests/test_writer.py enforce this on every
representative content shape."""

from __future__ import annotations

from dataclasses import replace

from .model import Block, Page
from .parser import _scan_refs

# Logseq syntax fragments we refuse to construct because they'd flip the
# parser into a multi-line state that single-line construction can't model
# correctly (LOGBOOK and code fences consume subsequent bullets).
_DANGEROUS_BARE_LINES = {":LOGBOOK:", ":END:"}


def construct_block(
    content: str,
    *,
    depth: int = 0,
    marker: str | None = None,
    properties: dict[str, str] | None = None,
    explicit_id: str | None = None,
) -> Block:
    """Build a Block whose raw_lines our parser will fully recover.

    Constraints (v1, may relax later):
    - content is a single line (no '\\n' or '\\r')
    - content is not a Logseq parser-state marker like ':LOGBOOK:'
    - properties values are also single-line
    """
    if "\n" in content or "\r" in content:
        raise ValueError("multi-line content not supported (single-line only)")
    if content.strip() in _DANGEROUS_BARE_LINES:
        raise ValueError(
            f"content {content!r} would trigger Logseq parser state and "
            f"swallow subsequent blocks; refuse to construct"
        )
    props = dict(properties or {})
    if explicit_id is not None:
        props["id"] = explicit_id
    for k, v in props.items():
        if "\n" in v or "\r" in v:
            raise ValueError(f"property {k!r} value is multi-line: {v!r}")

    bullet_prefix = "\t" * depth + "- "
    prop_prefix = "\t" * depth + "  "

    first_content = f"{marker} {content}" if marker else content
    raw_lines = [bullet_prefix + first_content + "\n"]
    for key, value in props.items():
        raw_lines.append(f"{prop_prefix}{key}:: {value}\n")

    refs = _scan_refs(raw_lines)

    if explicit_id is not None:
        uuid = explicit_id
        has_explicit_id = True
    else:
        # Sentinel — parser will reassign auto:<sha1> when this block
        # is parsed back as part of a real file (with real line_start)
        uuid = "constructed:pending"
        has_explicit_id = False

    return Block(
        uuid=uuid,
        has_explicit_id=has_explicit_id,
        page="",
        parent_uuid=None,
        sibling_order=0,
        depth=depth,
        content=content,
        marker=marker,
        properties=props,
        refs=refs,
        raw_lines=raw_lines,
        line_start=-1,
        line_end=-1,
    )


def append_block(page: Page, new_block: Block) -> Page:
    """Return a new Page with new_block appended after page.blocks[-1].
    Sets parent_uuid / sibling_order based on the existing block tree
    (mirrors parser._link_parents logic). Header lines unchanged.

    The new block's `page` field is set to page.name.

    Files that don't end with '\\n' (common in real Logseq vaults — naked
    `\\t-` bullets that the user started but didn't finish) would otherwise
    cause our new bullet to splice onto the previous line and the parser
    would see a single longer bullet. Defensive newline prefix handles it."""
    parent_uuid: str | None = None
    sibling_order = 0
    for b in reversed(page.blocks):
        if b.depth < new_block.depth:
            parent_uuid = b.uuid
            break
        if b.depth == new_block.depth:
            parent_uuid = b.parent_uuid
            sibling_order = b.sibling_order + 1
            break
    placed_raw = new_block.raw_lines
    existing_text = "".join(page.header_raw_lines) + "".join(
        line for b in page.blocks for line in b.raw_lines
    )
    if existing_text and not existing_text.endswith("\n"):
        placed_raw = ["\n" + placed_raw[0], *placed_raw[1:]]
    placed = replace(
        new_block,
        page=page.name,
        parent_uuid=parent_uuid,
        sibling_order=sibling_order,
        raw_lines=placed_raw,
    )
    return replace(page, blocks=[*page.blocks, placed])
