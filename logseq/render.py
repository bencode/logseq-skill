from __future__ import annotations

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.text import Text

from .model import Block, Page
from .parser import (
    BLOCK_REF_RE,
    EMBED_RE,
    PAGE_REF_RE,
    TAG_BARE_RE,
    TAG_BRACKET_RE,
)

MARKER_STYLES = {
    "TODO": "bold red",
    "DOING": "bold yellow",
    "DONE": "dim green",
    "NOW": "bold magenta",
    "LATER": "yellow",
    "WAITING": "dim yellow",
    "CANCELLED": "strike dim",
}

REF_STYLES = {
    "page": "cyan",
    "tag": "magenta",
    "block": "yellow dim",
    "embed": "yellow dim",
}


def render_page(page: Page) -> RenderableType:
    parts: list[RenderableType] = [_render_header(page), Rule(style="dim")]
    if not page.blocks:
        parts.append(Text("(no blocks)", style="dim italic"))
    else:
        for block in page.blocks:
            parts.append(_render_block(block))
    return Group(*parts)


def _render_header(page: Page) -> RenderableType:
    title = Text()
    title.append("# ", style="bold dim")
    title.append(page.title, style="bold")
    title.append("    ")
    type_tag = f"[{page.type}]"
    if page.journal_day:
        ymd = str(page.journal_day)
        type_tag = f"[journal · {ymd[:4]}-{ymd[4:6]}-{ymd[6:]}]"
    title.append(type_tag, style="dim cyan")
    title.append(f"    {len(page.blocks)} blocks", style="dim")

    lines: list[RenderableType] = [title]
    if page.aliases:
        a = Text()
        a.append("  aliases: ", style="dim")
        a.append(", ".join(page.aliases))
        lines.append(a)
    extra_props = {k: v for k, v in page.properties.items() if k not in ("alias", "aliases")}
    for k, v in extra_props.items():
        p = Text()
        p.append(f"  {k}: ", style="dim")
        p.append(v)
        lines.append(p)
    return Group(*lines)


def _render_block(block: Block) -> Text:
    text = Text()
    text.append("  " * block.depth, style="dim")
    text.append("- ", style="dim")
    if block.marker:
        text.append(block.marker + " ", style=MARKER_STYLES.get(block.marker, "bold"))
    _append_with_refs(text, block.content)
    return text


def _append_with_refs(text: Text, content: str) -> None:
    spans = _find_ref_spans(content)
    pos = 0
    for start, end, kind in spans:
        if start > pos:
            text.append(content[pos:start])
        text.append(content[start:end], style=REF_STYLES[kind])
        pos = end
    if pos < len(content):
        text.append(content[pos:])


def _find_ref_spans(content: str) -> list[tuple[int, int, str]]:
    """Return non-overlapping (start, end, kind) spans, mirroring parser._scan_refs."""
    embed_spans = [(m.start(), m.end(), "embed") for m in EMBED_RE.finditer(content)]
    tag_bracket_spans = [(m.start(), m.end(), "tag") for m in TAG_BRACKET_RE.finditer(content)]
    page_spans = [
        (m.start(), m.end(), "page")
        for m in PAGE_REF_RE.finditer(content)
        if not _in_any(tag_bracket_spans, m.start())
    ]
    block_spans = [
        (m.start(), m.end(), "block")
        for m in BLOCK_REF_RE.finditer(content)
        if not _in_any(embed_spans, m.start())
    ]
    tag_bare_spans = [
        (m.start(), m.end(), "tag")
        for m in TAG_BARE_RE.finditer(content)
        if not _in_any(tag_bracket_spans, m.start())
        and not (m.start() > 0 and content[m.start() - 1].isalnum())
    ]
    all_spans = embed_spans + tag_bracket_spans + page_spans + block_spans + tag_bare_spans
    all_spans.sort(key=lambda x: x[0])
    deduped: list[tuple[int, int, str]] = []
    last_end = -1
    for span in all_spans:
        if span[0] >= last_end:
            deduped.append(span)
            last_end = span[1]
    return deduped


def _in_any(spans: list[tuple[int, int, str]], pos: int) -> bool:
    return any(s <= pos < e for s, e, _ in spans)
