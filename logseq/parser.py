from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .model import Block, Page, PageType, Reference

BULLET_RE = re.compile(r"^(\t*)- ?")
PAGE_PROP_RE = re.compile(r"^([a-zA-Z_][\w-]*)::[ \t]+(.*)$")
TASK_MARKER_RE = re.compile(r"^(TODO|DOING|DONE|NOW|LATER|WAITING|CANCELLED)\b[ \t]*")
JOURNAL_NAME_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})$")

PAGE_REF_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
TAG_BRACKET_RE = re.compile(r"#\[\[([^\[\]]+)\]\]")
TAG_BARE_RE = re.compile(r"#([A-Za-z0-9_\-/一-鿿]+)")
BLOCK_REF_RE = re.compile(r"\(\(([0-9a-fA-F-]{36})\)\)")
EMBED_RE = re.compile(r"\{\{embed\s+\(\(([0-9a-fA-F-]{36})\)\)\s*\}\}")


def parse(text: str, file_path: str | Path, *, page_type: PageType | None = None) -> Page:
    file_path_str = str(file_path)
    title = Path(file_path_str).stem
    name = title.lower()
    type_ = page_type or _derive_type(file_path_str, title)
    journal_day = _derive_journal_day(title) if type_ == "journal" else None
    namespace_parent = name.rsplit("/", 1)[0] if "/" in name else None

    lines = text.splitlines(keepends=True)
    boundaries = _find_block_boundaries(lines)

    if not boundaries:
        props = _parse_page_properties(lines)
        return Page(
            name=name,
            title=title,
            file_path=file_path_str,
            type=type_,
            properties=props,
            aliases=_extract_aliases(props),
            namespace_parent=namespace_parent,
            journal_day=journal_day,
            header_raw_lines=lines,
            blocks=[],
        )

    first_block_line = boundaries[0][0]
    header_lines = lines[:first_block_line]
    page_props = _parse_page_properties(header_lines)

    blocks: list[Block] = []
    for i, (start, depth) in enumerate(boundaries):
        end_excl = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(lines)
        raw_lines = lines[start:end_excl]
        block = _build_block(
            raw_lines=raw_lines,
            line_start=start,
            line_end=end_excl - 1,
            depth=depth,
            page_name=name,
            file_path=file_path_str,
        )
        blocks.append(block)

    _link_parents(blocks)

    return Page(
        name=name,
        title=title,
        file_path=file_path_str,
        type=type_,
        properties=page_props,
        aliases=_extract_aliases(page_props),
        namespace_parent=namespace_parent,
        journal_day=journal_day,
        header_raw_lines=header_lines,
        blocks=blocks,
    )


def _derive_type(file_path: str, title: str) -> PageType:
    if "/journals/" in file_path:
        return "journal"
    if "/pages/" in file_path:
        return "page"
    return "journal" if JOURNAL_NAME_RE.match(title) else "page"


def _derive_journal_day(title: str) -> int | None:
    m = JOURNAL_NAME_RE.match(title)
    if not m:
        return None
    return int(m.group(1) + m.group(2) + m.group(3))


def _extract_aliases(properties: dict[str, str]) -> list[str]:
    raw = properties.get("alias") or properties.get("aliases")
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    out: list[str] = []
    for p in parts:
        m = re.fullmatch(r"\[\[(.+?)\]\]", p)
        out.append(m.group(1) if m else p)
    return [x for x in out if x]


def _find_block_boundaries(lines: list[str]) -> list[tuple[int, int]]:
    boundaries: list[tuple[int, int]] = []
    in_fence = False
    in_logbook = False
    for i, line in enumerate(lines):
        if not in_fence and not in_logbook:
            m = BULLET_RE.match(line)
            if m:
                boundaries.append((i, len(m.group(1))))
        if _is_fence_line(line):
            in_fence = not in_fence
        bare = line.strip()
        if bare == ":LOGBOOK:":
            in_logbook = True
        elif bare == ":END:" and in_logbook:
            in_logbook = False
    return boundaries


def _is_fence_line(line: str) -> bool:
    s = line.lstrip(" \t").rstrip("\r\n")
    m = re.match(r"-\s*", s)
    if m:
        s = s[m.end():]
    return s.startswith("```")


def _parse_page_properties(header_lines: list[str]) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in header_lines:
        stripped = line.rstrip("\r\n")
        m = PAGE_PROP_RE.match(stripped)
        if m:
            props[m.group(1)] = m.group(2)
    return props


def _build_block(
    raw_lines: list[str],
    line_start: int,
    line_end: int,
    depth: int,
    page_name: str,
    file_path: str,
) -> Block:
    first_line = raw_lines[0]
    m = BULLET_RE.match(first_line)
    assert m is not None, f"expected bullet at start of block: {first_line!r}"
    raw_content = first_line[m.end():].rstrip("\r\n")

    marker: str | None = None
    content = raw_content
    tm = TASK_MARKER_RE.match(content)
    if tm:
        marker = tm.group(1)
        content = content[tm.end():]

    prop_prefix = "\t" * depth + "  "
    prop_re = re.compile(
        re.escape(prop_prefix) + r"([a-zA-Z_][\w-]*)::[ \t]+(.*)$"
    )

    properties: dict[str, str] = {}
    explicit_id: str | None = None
    for line in raw_lines[1:]:
        stripped = line.rstrip("\r\n")
        pm = prop_re.match(stripped)
        if pm:
            key, value = pm.group(1), pm.group(2)
            properties[key] = value
            if key == "id":
                explicit_id = value

    refs = _scan_refs(raw_lines)

    if explicit_id:
        block_uuid = explicit_id
        has_explicit_id = True
    else:
        digest = hashlib.sha1(
            f"{file_path}:{line_start}:{raw_content}".encode("utf-8")
        ).hexdigest()[:12]
        block_uuid = f"auto:{digest}"
        has_explicit_id = False

    return Block(
        uuid=block_uuid,
        has_explicit_id=has_explicit_id,
        page=page_name,
        parent_uuid=None,
        sibling_order=0,
        depth=depth,
        content=content,
        marker=marker,
        properties=properties,
        refs=refs,
        raw_lines=raw_lines,
        line_start=line_start,
        line_end=line_end,
    )


def _scan_refs(raw_lines: list[str]) -> list[Reference]:
    text = "".join(raw_lines)
    refs: list[Reference] = []

    embed_spans: list[tuple[int, int]] = []
    for m in EMBED_RE.finditer(text):
        refs.append(Reference(kind="embed", target=m.group(1), raw=m.group(0)))
        embed_spans.append((m.start(), m.end()))

    def in_span(spans: list[tuple[int, int]], pos: int) -> bool:
        return any(s <= pos < e for s, e in spans)

    tag_bracket_spans: list[tuple[int, int]] = []
    for m in TAG_BRACKET_RE.finditer(text):
        refs.append(Reference(kind="tag", target=m.group(1), raw=m.group(0)))
        tag_bracket_spans.append((m.start(), m.end()))

    for m in PAGE_REF_RE.finditer(text):
        if in_span(tag_bracket_spans, m.start()):
            continue
        refs.append(Reference(kind="page", target=m.group(1), raw=m.group(0)))

    for m in BLOCK_REF_RE.finditer(text):
        if in_span(embed_spans, m.start()):
            continue
        refs.append(Reference(kind="block", target=m.group(1), raw=m.group(0)))

    for m in TAG_BARE_RE.finditer(text):
        if in_span(tag_bracket_spans, m.start()):
            continue
        if m.start() > 0 and text[m.start() - 1].isalnum():
            continue
        refs.append(Reference(kind="tag", target=m.group(1), raw=m.group(0)))

    return refs


def _link_parents(blocks: list[Block]) -> None:
    stack: list[Block] = []
    sibling_counters: dict[str | None, int] = {}
    for block in blocks:
        while stack and stack[-1].depth >= block.depth:
            stack.pop()
        parent = stack[-1] if stack else None
        block.parent_uuid = parent.uuid if parent else None
        key = parent.uuid if parent else None
        block.sibling_order = sibling_counters.get(key, 0)
        sibling_counters[key] = block.sibling_order + 1
        stack.append(block)
