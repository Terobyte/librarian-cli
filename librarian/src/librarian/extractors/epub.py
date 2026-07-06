# src/librarian/extractors/epub.py
from __future__ import annotations

import posixpath
import warnings
from pathlib import Path

import ebooklib
from ebooklib import epub as ebl

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base, zipsafe
from librarian.extractors.html_blocks import walk_body
from librarian.ir import Block, BlockKind, Format, RawDoc
from librarian.xmlsafe import parse_html


def _strip_frag(href: str) -> str:
    return href.partition("#")[0]


def _basename(href: str) -> str:
    return posixpath.basename(_strip_frag(href))


def _dc(book, name: str) -> str | None:
    vals = book.get_metadata("DC", name)
    if vals and vals[0][0] and vals[0][0].strip():
        return vals[0][0].strip()
    return None


class EpubExtractor:
    format = Format.EPUB

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        zipsafe.check_zip(path, cfg)                     # лимиты §6.0 до ebooklib
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")          # ebooklib шумит про ignore_ncx
                book = ebl.read_epub(str(path))
        except Exception as e:                           # noqa: BLE001 — битый epub → failed
            raise BrokenFileError(f"{path.name}: битый EPUB: {e}") from None
        skip = {_basename(g.get("href", "")) for g in book.guide
                if g.get("type") in ("cover", "toc")}
        per_file: list[tuple[str, list[Block]]] = []     # (basename файла, блоки)
        ref_parts: list[str] = []
        for idref, _linear in book.spine:
            item = book.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            if "nav" in (item.properties or []) or _basename(item.get_name()) in skip:
                continue
            content = item.get_content()
            if not content or not content.strip():
                continue
            body = parse_html(content).body
            per_file.append((_basename(item.get_name()), walk_body(body)))
            ref_parts.append(body.text_content())
        if not per_file:
            raise BrokenFileError(f"{path.name}: в EPUB нет контентных документов")
        blocks = [b for _, bs in per_file for b in bs]
        return RawDoc(fmt=Format.EPUB, blocks=blocks, title=_dc(book, "title"),
                      author=_dc(book, "creator"), lang=_dc(book, "language"),
                      ref_text="\n".join(ref_parts))


base.register(EpubExtractor())
