from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Format(str, Enum):
    FB2 = "fb2"; EPUB = "epub"; DOCX = "docx"; HTML = "html"
    TXT = "txt"; MD = "md"; PDF = "pdf"


class BlockKind(str, Enum):
    HEADING = "heading"; PARA = "para"; QUOTE = "quote"
    LIST_ITEM = "list_item"; TABLE = "table"; FOOTNOTE = "footnote"
    CODE = "code"; META = "meta"


@dataclass
class Block:
    kind: BlockKind
    text: str
    level: int | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    font_size: float | None = None
    bold: bool = False
    origin: str = ""


@dataclass
class Section:
    title: str
    level: int
    blocks: list[Block]
    children: list["Section"]


@dataclass
class Chapter:
    n: int
    title: str
    blocks: list[Block]
    tokens: int = 0
    part: int | None = None


@dataclass
class RawDoc:
    fmt: Format
    blocks: list[Block]
    title: str | None
    author: str | None
    lang: str | None
    ref_text: str
    pages: int | None = None
    page_rects: list[tuple] | None = None
    unknown_tags: dict[str, int] = field(default_factory=dict)   # §6.6, заполняет HTML


@dataclass
class ReportDraft:
    control_chars: int = 0
    oversize_blocks_split: int = 0
    structure_fallback: bool = False
    removed: dict = field(default_factory=dict)
    unknown_tags: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DocContext:
    fmt: Format
    cfg: "Config"
    raw: RawDoc
    report: ReportDraft


@dataclass
class BookMeta:
    id: str
    title: str
    author: str
    lang: str | None
    meta_locked: bool
    source_path: Path
    fmt: Format
    sha256: str
    config_hash: str
    cache_key: str
    status: str
    score: float
    keep_source: bool
