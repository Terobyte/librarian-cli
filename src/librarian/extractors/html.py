# src/librarian/extractors/html.py
from __future__ import annotations

from pathlib import Path

import trafilatura

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.ir import Block, BlockKind, Format, RawDoc
from librarian.xmlsafe import decode_html, parse_xml

_HEAD_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}


def _local(tag) -> str:
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _flat(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _walk(el, blocks: list[Block], unknown: dict[str, int]) -> None:
    """Маппер XML-вывода trafilatura 2.x (§6.6): head[rend], p, quote,
    list/item, code, table/row/cell; неизвестное — PARA + счётчик."""
    for child in el:
        tag = _local(child.tag)
        if not tag:                                     # комментарии, PI
            continue
        if tag == "head":
            level = _HEAD_LEVEL.get((child.get("rend") or "h2").casefold(), 2)
            if t := _flat(child):
                blocks.append(Block(BlockKind.HEADING, t, level=level,
                                    origin="traf-head"))
        elif tag == "p":
            if t := _flat(child):
                blocks.append(Block(BlockKind.PARA, t))
        elif tag == "quote":
            paras = [t for p in child.iter()
                     if _local(p.tag) == "p" and (t := _flat(p))]
            if t := ("\n".join(paras) or _flat(child)):
                blocks.append(Block(BlockKind.QUOTE, t))
        elif tag == "item":
            if t := _flat(child):
                blocks.append(Block(BlockKind.LIST_ITEM, t))
        elif tag == "code":
            t = "".join(child.itertext()).strip("\n")
            if t.strip():
                blocks.append(Block(BlockKind.CODE, t))
        elif tag == "table":
            rows = []
            for row in child.iter():
                if _local(row.tag) == "row":
                    cells = [_flat(c) for c in row if _local(c.tag) == "cell"]
                    rows.append("\t".join(cells))
            if rows:
                blocks.append(Block(BlockKind.TABLE, "\n".join(rows)))
        elif tag == "list":
            _walk(child, blocks, unknown)               # <list><item>…</list>
        else:                                           # §6.6: не молча
            unknown[tag] = unknown.get(tag, 0) + 1
            if t := _flat(child):
                blocks.append(Block(BlockKind.PARA, t, origin=f"traf-{tag}"))


class HtmlExtractor:
    format = Format.HTML

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        html = decode_html(path.read_bytes())
        xml = trafilatura.extract(html, output_format="xml",
                                  include_comments=False, include_tables=True,
                                  include_formatting=True)
        if not xml:
            raise BrokenFileError(f"{path.name}: не удалось выделить основной контент")
        root = parse_xml(xml.encode("utf-8"))
        main = next((el for el in root.iter() if _local(el.tag) == "main"), root)
        blocks: list[Block] = []
        unknown: dict[str, int] = {}
        _walk(main, blocks, unknown)
        if not blocks:
            raise BrokenFileError(f"{path.name}: не удалось выделить основной контент")
        meta = trafilatura.extract_metadata(html)
        ref_text = trafilatura.extract(html, include_comments=False,
                                       include_tables=True) or ""     # §11.1
        return RawDoc(fmt=Format.HTML, blocks=blocks,
                      title=(getattr(meta, "title", None) or None) if meta else None,
                      author=(getattr(meta, "author", None) or None) if meta else None,
                      lang=(getattr(meta, "language", None) or None) if meta else None,
                      ref_text=ref_text, unknown_tags=unknown)


base.register(HtmlExtractor())
