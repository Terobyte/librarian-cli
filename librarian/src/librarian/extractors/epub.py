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


def _nav_titles(book) -> dict[str, str]:
    """href (basename, без фрагмента) → название; первая запись побеждает."""
    out: dict[str, str] = {}

    def walk(items) -> None:
        for it in items:
            if isinstance(it, tuple):                   # (Section, [children])
                sec, children = it
                href = getattr(sec, "href", "") or ""
                if href and sec.title and _basename(href) not in out:
                    out[_basename(href)] = sec.title
                walk(children)
            else:                                       # Link
                href = getattr(it, "href", "") or ""
                title = getattr(it, "title", "") or ""
                if href and title and _basename(href) not in out:
                    out[_basename(href)] = title

    walk(book.toc or [])
    return out


def _nav_counts(book) -> dict[str, int]:
    """href (basename) → число TOC-записей БЕЗ дедупа (гранулярность издательского TOC)."""
    out: dict[str, int] = {}

    def bump(href: str) -> None:
        if href:
            name = _basename(href)
            out[name] = out.get(name, 0) + 1

    def walk(items) -> None:
        for it in items:
            if isinstance(it, tuple):                   # (Section, [children])
                sec, children = it
                href = getattr(sec, "href", "") or ""
                if href and sec.title:
                    bump(href)
                walk(children)
            else:                                       # Link
                href = getattr(it, "href", "") or ""
                title = getattr(it, "title", "") or ""
                if href and title:
                    bump(href)

    walk(book.toc or [])
    return out


def _restructure_file(name: str, bs: list[Block], titles: dict[str, str]) -> list[Block]:
    """§6.4.3 отклонение: DocBook-подобный файл — граница файла становится
    уровнем 1, остальные заголовки файла сдвигаются на +1 (без cap)."""
    if bs and bs[0].kind is BlockKind.HEADING and bs[0].level == 1:
        bs[0].origin = "epub-file"
        for b in bs[1:]:
            if b.kind is BlockKind.HEADING:
                b.level += 1
        return bs
    for b in bs:
        if b.kind is BlockKind.HEADING:
            b.level += 1
    t = titles.get(name)
    if not t:
        first = next((b.text for b in bs if b.kind is BlockKind.PARA), "")
        t = first[:60] or name
    return [Block(BlockKind.HEADING, t, level=1, origin="epub-file"), *bs]


def _is_divider(bs: list[Block]) -> bool:
    """§6.4.3 доп. отклонение (Plan v3, B2'): файл-разделитель (part/volume) —
    ровно один блок в файле, и это HEADING уровня 1 с нетривиальным текстом
    (m7': guard `len(text.strip()) > 1`, чтобы не поймать огрызок §6.4.5)."""
    return (len(bs) == 1 and bs[0].kind is BlockKind.HEADING
            and bs[0].level == 1 and len(bs[0].text.strip()) > 1)


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
        titles = _nav_titles(book)
        n_heads = sum(1 for _, bs in per_file for b in bs
                      if b.kind is BlockKind.HEADING)
        blocks: list[Block] = []
        if n_heads < 2:                                  # §6.4.4: файл = секция
            for name, bs in per_file:
                t = titles.get(name)
                if not t:
                    first = next((b.text for b in bs
                                  if b.kind is BlockKind.PARA), "")
                    t = first[:60] or name
                blocks.append(Block(BlockKind.HEADING, t, level=1,
                                    origin="epub-fallback"))
                blocks.extend(bs)
        else:                                            # §6.4.5: nav чинит пустые названия
            nav_counts = _nav_counts(book)
            processed: list[list[Block]] = []
            restructured_any = False
            for name, bs in per_file:
                if (bs and bs[0].kind is BlockKind.HEADING
                        and len(bs[0].text.strip()) <= 1 and titles.get(name)):
                    bs[0].text = titles[name]
                # §6.4.3 отклонение: границы spine-файла — не границы глав, КРОМЕ
                # DocBook-подобных файлов (≥2 книга, ≥2 h1 в файле, файл — ровно
                # одна TOC-единица) — см. deviations в docs/superpowers/plans.
                if (len(per_file) >= 2
                        and sum(1 for b in bs if b.kind is BlockKind.HEADING
                                and b.level == 1) >= 2
                        and nav_counts.get(name) == 1):
                    processed.append(_restructure_file(name, bs, titles))
                    restructured_any = True
                else:
                    processed.append(bs)
            # Plan v3 (repair delta, дельта B2'/M3'): part-разделители — файлы
            # ровно из одного HEADING — становятся предком уровня 1 для
            # DocBook-перестроенных глав, НО только если книга вообще содержит
            # restructured-файл (иначе разделять нечего — "ничего не меняется").
            if restructured_any:
                any_part_tagged = False
                for i, bs in enumerate(processed):
                    if not _is_divider(bs):
                        continue
                    has_later_content = any(
                        not _is_divider(processed[j])
                        and any(b.kind is BlockKind.HEADING for b in processed[j])
                        for j in range(i + 1, len(processed)))
                    if has_later_content:
                        bs[0].origin = "epub-part"
                        any_part_tagged = True
                if any_part_tagged:
                    for bs in processed:
                        for b in bs:
                            if b.kind is BlockKind.HEADING and b.origin != "epub-part":
                                b.level += 1
            for bs in processed:
                blocks.extend(bs)
        return RawDoc(fmt=Format.EPUB, blocks=blocks, title=_dc(book, "title"),
                      author=_dc(book, "creator"), lang=_dc(book, "language"),
                      ref_text="\n".join(ref_parts))


base.register(EpubExtractor())
