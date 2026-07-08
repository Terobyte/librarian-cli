# src/librarian/extractors/docx.py
from __future__ import annotations

from pathlib import Path

import mammoth

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base, zipsafe
from librarian.extractors.html_blocks import walk_body
from librarian.extractors.textrules import apply_patterns_to_blocks
from librarian.ir import BlockKind, Format, RawDoc
from librarian.xmlsafe import parse_html, parse_xml


def _local(tag) -> str:
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _core_meta(path: Path, cfg: Config) -> tuple[str | None, str | None, str | None]:
    """docProps/core.xml → (title, creator, language); части может не быть."""
    try:
        data = zipsafe.read_entry(path, "docProps/core.xml", cfg)
        root = parse_xml(data)
    except Exception:                       # noqa: BLE001 — битая мета не валит книгу
        return None, None, None
    vals: dict[str, str | None] = {"title": None, "creator": None, "language": None}
    for el in root.iter():
        name = _local(el.tag)
        if name in vals and vals[name] is None and el.text and el.text.strip():
            vals[name] = el.text.strip()
    return vals["title"], vals["creator"], vals["language"]


class DocxExtractor:
    format = Format.DOCX

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        zipsafe.check_zip(path, cfg)                     # лимиты §6.0 до mammoth
        try:
            with path.open("rb") as f:
                html = mammoth.convert_to_html(f).value
            with path.open("rb") as f:                   # эталон coverage §11.1
                ref_text = mammoth.extract_raw_text(f).value
        except Exception as e:                           # noqa: BLE001 — битый docx → failed
            raise BrokenFileError(f"{path.name}: битый DOCX: {e}") from None
        if not html.strip():
            raise BrokenFileError(f"{path.name}: в DOCX нет текста")
        body = parse_html(html.encode("utf-8")).body
        blocks = walk_body(body)
        if not any(b.kind is BlockKind.HEADING for b in blocks):
            blocks = apply_patterns_to_blocks(blocks, cfg)   # §6.5 fallback → 6.1.3
        title, author, lang = _core_meta(path, cfg)
        return RawDoc(fmt=Format.DOCX, blocks=blocks, title=title,
                      author=author, lang=lang, ref_text=ref_text)


base.register(DocxExtractor())
