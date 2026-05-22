from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RefKind = Literal["page", "tag", "block", "embed"]
PageType = Literal["page", "journal"]


@dataclass
class Reference:
    kind: RefKind
    target: str
    raw: str


@dataclass
class Block:
    uuid: str
    has_explicit_id: bool
    page: str
    parent_uuid: str | None
    sibling_order: int
    depth: int
    content: str
    marker: str | None
    properties: dict[str, str]
    refs: list[Reference]
    raw_lines: list[str]
    line_start: int
    line_end: int


@dataclass
class Page:
    name: str
    title: str
    file_path: str
    type: PageType
    properties: dict[str, str]
    aliases: list[str] = field(default_factory=list)
    namespace_parent: str | None = None
    journal_day: int | None = None
    header_raw_lines: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
