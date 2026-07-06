# src/librarian/extractors/html_blocks.py
from __future__ import annotations

from librarian.ir import Block, BlockKind

_HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}


def _tag(el) -> str:
    t = el.tag
    if not isinstance(t, str):          # комментарии, PI
        return ""
    return t.rpartition("}")[2].casefold()


def _flat(el) -> str:
    return " ".join(el.text_content().split())


def walk_body(body) -> list[Block]:
    blocks: list[Block] = []
    _walk(body, blocks)
    return blocks


def _walk(el, blocks: list[Block]) -> None:
    for child in el:
        tag = _tag(child)
        if tag in _HEADING_LEVEL:
            if t := _flat(child):
                blocks.append(Block(BlockKind.HEADING, t, level=_HEADING_LEVEL[tag]))
        elif tag == "p":
            if t := _flat(child):
                blocks.append(Block(BlockKind.PARA, t))
        elif tag == "blockquote":
            paras = [t for p in child.iter()
                     if _tag(p) == "p" and (t := _flat(p))]
            if t := ("\n".join(paras) or _flat(child)):
                blocks.append(Block(BlockKind.QUOTE, t))
        elif tag == "li":
            if t := _flat(child):
                blocks.append(Block(BlockKind.LIST_ITEM, t))
        elif tag == "pre":
            t = child.text_content().strip("\n")
            if t.strip():
                blocks.append(Block(BlockKind.CODE, t))
        elif tag == "table":
            rows = []
            for tr in child.iter():
                if _tag(tr) == "tr":
                    cells = [_flat(c) for c in tr if _tag(c) in ("td", "th")]
                    rows.append("\t".join(cells))
            if rows:
                blocks.append(Block(BlockKind.TABLE, "\n".join(rows)))
        else:
            _walk(child, blocks)        # div, section, article, …
