"""Block construction primitives.

Stage 6a deliberately covers only what we can prove round-trips through
our own parser. File I/O lives in Stage 6b; CLI in 6c; TUI in 6d.

Constructed blocks are guaranteed to parse back with all structural
fields (content, marker, depth, properties, refs) preserved — the
property-based tests in tests/test_writer.py enforce this on every
representative content shape."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from .model import Block, Page
from .parser import _scan_refs, parse
from .serializer import serialize

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


# ============================================================================
# File-level write API (Stage 6b)
# ============================================================================


class FileChangedDuringWrite(RuntimeError):
    """Raised when the target file's mtime changed between our read and
    write — Logseq desktop or another writer may have touched it."""


def append_to_page_file(
    path: Path,
    content: str,
    *,
    marker: str | None = None,
    properties: dict[str, str] | None = None,
    explicit_id: str | None = None,
    depth: int = 0,
) -> str:
    """Read `path` → parse → construct + append a block → atomic write back.
    Returns the new block's uuid (the explicit_id you passed, or the
    auto:<sha1> the parser assigns on the next read).

    Atomicity: writes to `<path>.tmp` then `os.replace` (POSIX-atomic).
    Race detection: if the file's mtime changes between our read and our
    write, raises FileChangedDuringWrite — caller should retry."""
    if path.exists():
        before_mtime = path.stat().st_mtime
        text = path.read_text(encoding="utf-8-sig")
    else:
        before_mtime = None
        text = ""
    page = parse(text, str(path))
    new = construct_block(
        content,
        depth=depth,
        marker=marker,
        properties=properties,
        explicit_id=explicit_id,
    )
    updated = append_block(page, new)
    new_text = serialize(updated)

    if before_mtime is not None and path.stat().st_mtime != before_mtime:
        raise FileChangedDuringWrite(
            f"{path} changed under us between read ({before_mtime}) "
            f"and write ({path.stat().st_mtime}); refusing to overwrite"
        )

    tmp = path.with_name(path.name + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)

    if explicit_id is not None:
        return explicit_id
    # Re-parse to get the auto-uuid the parser computed for the new block
    reread = parse(path.read_text(encoding="utf-8-sig"), str(path))
    return reread.blocks[-1].uuid


def append_to_today(
    vault: Path,
    content: str,
    *,
    marker: str | None = None,
    properties: dict[str, str] | None = None,
) -> Path:
    """Append `content` to today's journal in `vault`. Creates the journal
    file if missing (no header). Returns the journal file path."""
    today = date.today().isoformat()
    fname = "_".join(today.split("-")) + ".md"
    journal_dir = vault / "journals"
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = journal_dir / fname
    append_to_page_file(
        path, content, marker=marker, properties=properties
    )
    return path
