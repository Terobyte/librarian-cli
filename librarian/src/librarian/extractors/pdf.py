# src/librarian/extractors/pdf.py
from __future__ import annotations

from pathlib import Path
from statistics import median

import pymupdf

from librarian.config import Config
from librarian.errors import BrokenFileError, EncryptedError, ScanError
from librarian.extractors import base
from librarian.extractors.textrules import merge_lines
from librarian.ir import Block, BlockKind, Format, RawDoc


class PdfExtractor:
    format = Format.PDF

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        try:
            doc = pymupdf.open(str(path))
        except Exception as e:                           # noqa: BLE001 — битый pdf → failed
            raise BrokenFileError(f"{path.name}: битый PDF: {e}") from None
        try:
            if doc.needs_pass and not doc.authenticate(""):      # §6.7.1
                raise EncryptedError(
                    f"{path.name}: PDF зашифрован (пустой пароль не подошёл)")
            texts = [page.get_text("text") for page in doc]
            if not texts or median(len(t) for t in texts) < cfg.pdf.scan_chars_per_page:
                raise ScanError(
                    f"{path.name}: текстовый слой отсутствует — это скан, нужен OCR")
            blocks: list[Block] = []
            rects: list[tuple] = []
            for pno, page in enumerate(doc, 1):
                r = page.rect
                rects.append((r.x0, r.y0, r.x1, r.y1))
                for blk in page.get_text("dict", sort=True)["blocks"]:
                    if blk.get("type") != 0:                     # не текст — мимо
                        continue
                    b = self._make_block(blk, pno, cfg)
                    if b is not None:
                        blocks.append(b)
            meta = doc.metadata or {}
            return RawDoc(fmt=Format.PDF, blocks=blocks,
                          title=(meta.get("title") or "").strip() or None,
                          author=(meta.get("author") or "").strip() or None,
                          lang=None, ref_text="\n".join(texts),     # эталон §11.1
                          pages=doc.page_count, page_rects=rects)
        finally:
            doc.close()

    @staticmethod
    def _make_block(blk: dict, pno: int, cfg: Config) -> Block | None:
        lines: list[str] = []
        size_chars: dict[float, int] = {}
        bold_chars = total_chars = 0
        for ln in blk.get("lines", []):
            text = "".join(s["text"] for s in ln["spans"])
            if text.strip():
                lines.append(text)
            for s in ln["spans"]:
                n = len(s["text"])
                size = round(s["size"] / cfg.pdf.size_round) * cfg.pdf.size_round
                size_chars[size] = size_chars.get(size, 0) + n
                if s["flags"] & 16:                              # бит bold
                    bold_chars += n
                total_chars += n
        if not lines:
            return None
        font = (min(sorted(size_chars.items()),
                    key=lambda kv: (-kv[1], kv[0]))[0] if size_chars else None)
        return Block(BlockKind.PARA, merge_lines(lines, cfg),    # склейка §6.1.2
                     page=pno, bbox=tuple(blk["bbox"]), font_size=font,
                     bold=total_chars > 0 and bold_chars / total_chars >= 0.6,
                     origin=f"pdf:{len(lines)}")                 # строк до склейки — для P5


base.register(PdfExtractor())
