from __future__ import annotations

import re
from pathlib import Path

from librarian.config import Config
from librarian.extractors import base
from librarian.extractors.textrules import apply_heading_patterns, apply_patterns_to_blocks, merge_lines
from librarian.extractors.txt import _read_text
from librarian.ir import Block, BlockKind, Format, RawDoc

_FENCE = re.compile(r"^(`{3,})")
_SETEXT = re.compile(r"^(=+|-+)\s*$")
_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_BREAK = re.compile(r"^(?:[-*_][ \t]*){3,}$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d{1,9}\.)\s+(.*)$")
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_AUTO = re.compile(r"<(https?://[^>\s]+)>")


def _strip_inline(text: str) -> str:
    text = _IMG.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    return _AUTO.sub(r"\1", text)


class MdExtractor:
    format = Format.MD

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        text = _read_text(path.read_bytes(), path.name)
        blocks = _parse(text.replace("\r\n", "\n").replace("\r", "\n"), cfg)
        for b in blocks:
            if b.kind is not BlockKind.CODE:
                b.text = _strip_inline(b.text)
        if not any(b.kind is BlockKind.HEADING for b in blocks):
            blocks = _fallback_patterns(blocks, cfg)
        return RawDoc(fmt=Format.MD, blocks=blocks, title=None, author=None,
                      lang=None, ref_text=text)


def _fallback_patterns(blocks: list[Block], cfg: Config) -> list[Block]:
    return apply_patterns_to_blocks(blocks, cfg)


def _parse(text: str, cfg: Config) -> list[Block]:
    lines = text.split("\n")
    blocks: list[Block] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(Block(BlockKind.PARA, merge_lines(para, cfg)))
            para.clear()

    i = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                blocks.append(Block(BlockKind.META, "\n".join(lines[1:j]),
                                    origin="frontmatter"))
                i = j + 1
                break
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        m = _FENCE.match(stripped)
        if m:
            flush()
            fence_ticks = m.group(1)            # голые бэктики (```, ````, …)
            body = []
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                # CommonMark: закрывающий fence — только бэктики, длина ≥ opening
                if s and all(c == '`' for c in s) and len(s) >= len(fence_ticks):
                    break
                body.append(lines[i])
                i += 1
            blocks.append(Block(BlockKind.CODE, "\n".join(body), origin="fence"))
            i += 1
            continue
        if para and _SETEXT.match(stripped):
            head = para.pop()
            flush()
            blocks.append(Block(BlockKind.HEADING, head,
                                level=1 if stripped[0] == "=" else 2, origin="setext"))
            i += 1
            continue
        m = _ATX.match(stripped)
        if m:
            flush()
            blocks.append(Block(BlockKind.HEADING, m.group(2),
                                level=min(len(m.group(1)), 4),
                                origin=f"h{len(m.group(1))}"))
            i += 1
            continue
        if _BREAK.match(stripped):
            flush()
            i += 1
            continue
        if stripped.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(re.sub(r"^\s*> ?", "", lines[i]).rstrip())
                i += 1
            blocks.append(Block(BlockKind.QUOTE, "\n".join(q)))
            continue
        m = _LIST.match(line)
        if m:
            flush()
            blocks.append(Block(BlockKind.LIST_ITEM, m.group(1).strip()))
            i += 1
            continue
        if not stripped:
            flush()
            i += 1
            continue
        para.append(stripped)
        i += 1
    flush()
    return blocks


base.register(MdExtractor())
