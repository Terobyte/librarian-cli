# src/librarian/extractors/fb2.py
from __future__ import annotations

from pathlib import Path

from lxml import etree

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.ir import Block, BlockKind, Format, RawDoc
from librarian.xmlsafe import parse_xml


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _flat(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _child(el, name: str):
    if el is None:
        return None
    for c in el:
        if _local(c) == name:
            return c
    return None


def _title_text(title_el) -> str:
    parts = [t for p in title_el if _local(p) == "p" and (t := _flat(p))]
    return " ".join(parts) if parts else _flat(title_el)


def _quote_text(el) -> str:
    parts = [t for sub in el.iter()
             if _local(sub) in ("p", "v", "text-author") and (t := _flat(sub))]
    return "\n".join(parts)


def _walk_section(sec, depth: int, blocks: list[Block]) -> None:
    for el in sec:
        tag = _local(el)
        if tag == "title":
            # title самого body (depth 0) — дубль названия книги, пропускаем
            if depth >= 1 and (t := _title_text(el)):
                blocks.append(Block(BlockKind.HEADING, t, level=min(depth, 4)))
        elif tag == "section":
            _walk_section(el, depth + 1, blocks)
        elif tag == "p":
            if t := _flat(el):
                blocks.append(Block(BlockKind.PARA, t))
        elif tag in ("epigraph", "cite"):
            if t := _quote_text(el):
                blocks.append(Block(BlockKind.QUOTE, t))
        elif tag == "poem":
            for st in el.iter():
                if _local(st) == "stanza":
                    lines = [t for v in st if _local(v) == "v" and (t := _flat(v))]
                    if lines:
                        blocks.append(Block(BlockKind.PARA, "\n".join(lines),
                                            origin="poem"))
        elif tag == "subtitle":
            if t := _flat(el):
                blocks.append(Block(BlockKind.HEADING, t,
                                    level=min(max(depth, 1) + 1, 4)))
        elif tag == "table":
            rows = []
            for tr in el.iter():
                if _local(tr) == "tr":
                    cells = [_flat(c) for c in tr if _local(c) in ("td", "th")]
                    rows.append("\t".join(cells))
            if rows:
                blocks.append(Block(BlockKind.TABLE, "\n".join(rows)))
        # binary, coverpage, image, empty-line, annotation — порождены форматом


def _metadata(root):
    ti = _child(_child(root, "description"), "title-info")
    if ti is None:
        return None, None, None
    bt = _child(ti, "book-title")
    title = (_flat(bt) or None) if bt is not None else None
    author = None
    a = _child(ti, "author")
    if a is not None:
        parts = [t for name in ("first-name", "last-name")
                 if (el := _child(a, name)) is not None and (t := _flat(el))]
        if not parts and (nick := _child(a, "nickname")) is not None:
            parts = [_flat(nick)] if _flat(nick) else []
        author = " ".join(parts) or None
    lang_el = _child(ti, "lang")
    lang = (_flat(lang_el) or None) if lang_el is not None else None
    return title, author, lang


def _read_source(path: Path, cfg: Config) -> bytes:
    return path.read_bytes()


class Fb2Extractor:
    format = Format.FB2

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        data = _read_source(path, cfg)
        try:
            root = parse_xml(data)
        except etree.XMLSyntaxError as e:
            raise BrokenFileError(f"{path.name}: битый XML: {e}") from None
        bodies = [el for el in root if _local(el) == "body"]
        if not bodies:
            raise BrokenFileError(f"{path.name}: в FB2 нет <body>")
        ref = "\n".join("".join(b.itertext()) for b in bodies)      # §11.1, до мутаций
        main = next((b for b in bodies if not b.get("name")), bodies[0])
        blocks: list[Block] = []
        _walk_section(main, 0, blocks)
        title, author, lang = _metadata(root)
        return RawDoc(fmt=Format.FB2, blocks=blocks, title=title, author=author,
                      lang=lang, ref_text=ref)


base.register(Fb2Extractor())
