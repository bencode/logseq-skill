from __future__ import annotations

from collections.abc import Callable

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.style import Style
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

# A callable that maps (kind, target) → an action string suitable for
# Textual's @click meta (e.g. "jump_page('Trantor')"), or None for no link.
RefAction = Callable[[str, str], str | None]


def render_page(page: Page, *, ref_action: RefAction | None = None) -> RenderableType:
    """Render a Page as a Rich renderable. If ref_action is provided, every
    page/tag/block/embed ref becomes a clickable element whose @click meta
    is the action string returned by ref_action(kind, target)."""
    parts: list[RenderableType] = [_render_header(page), Rule(style="dim")]
    if not page.blocks:
        parts.append(Text("(no blocks)", style="dim italic"))
    else:
        for block in page.blocks:
            parts.append(_render_block(block, ref_action=ref_action))
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


def _render_block(block: Block, *, ref_action: RefAction | None = None) -> Text:
    text = Text()
    text.append("  " * block.depth, style="dim")
    text.append("- ", style="dim")
    if block.marker:
        text.append(block.marker + " ", style=MARKER_STYLES.get(block.marker, "bold"))
    _append_with_refs(text, block.content, ref_action=ref_action)
    return text


def _append_with_refs(
    text: Text, content: str, *, ref_action: RefAction | None = None
) -> None:
    spans = _find_ref_spans(content)
    pos = 0
    for start, end, kind, target in spans:
        if start > pos:
            text.append(content[pos:start])
        text.append(content[start:end], style=_ref_style(kind, target, ref_action))
        pos = end
    if pos < len(content):
        text.append(content[pos:])


def _ref_style(kind: str, target: str, ref_action: RefAction | None) -> Style | str:
    base = REF_STYLES[kind]
    if ref_action is None:
        return base
    action = ref_action(kind, target)
    if not action:
        return base
    return Style.parse(base) + Style(meta={"@click": action})


def _find_ref_spans(content: str) -> list[tuple[int, int, str, str]]:
    """Return non-overlapping (start, end, kind, target) spans, mirroring
    parser._scan_refs. `target` is the page/tag name or block uuid that
    @click handlers will dispatch to."""
    embed_spans = [
        (m.start(), m.end(), "embed", m.group(1)) for m in EMBED_RE.finditer(content)
    ]
    tag_bracket_spans = [
        (m.start(), m.end(), "tag", m.group(1)) for m in TAG_BRACKET_RE.finditer(content)
    ]
    page_spans = [
        (m.start(), m.end(), "page", m.group(1))
        for m in PAGE_REF_RE.finditer(content)
        if not _in_any(tag_bracket_spans, m.start())
    ]
    block_spans = [
        (m.start(), m.end(), "block", m.group(1))
        for m in BLOCK_REF_RE.finditer(content)
        if not _in_any(embed_spans, m.start())
    ]
    tag_bare_spans = [
        (m.start(), m.end(), "tag", m.group(1))
        for m in TAG_BARE_RE.finditer(content)
        if not _in_any(tag_bracket_spans, m.start())
        and not (m.start() > 0 and content[m.start() - 1].isalnum())
    ]
    all_spans = embed_spans + tag_bracket_spans + page_spans + block_spans + tag_bare_spans
    all_spans.sort(key=lambda x: x[0])
    deduped: list[tuple[int, int, str, str]] = []
    last_end = -1
    for span in all_spans:
        if span[0] >= last_end:
            deduped.append(span)
            last_end = span[1]
    return deduped


def _in_any(spans: list[tuple[int, int, str, str]], pos: int) -> bool:
    return any(s <= pos < e for s, e, _, _ in spans)
