# tests/unit/test_pdf.py
import pymupdf
import pytest

from librarian.config import load_config
from librarian.errors import EncryptedError, ScanError
from librarian.extractors.pdf import PdfExtractor
from librarian.ir import BlockKind

CFG = load_config(None)


def make_pdf(path, pages, encryption=None, owner_pw=None, user_pw=None):
    """pages: список страниц; страница — список (x, y, text, size, fontname)."""
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=595, height=842)
        for x, y, text, size, font in items:
            page.insert_text((x, y), text, fontsize=size, fontname=font)
    kw = {}
    if encryption is not None:
        kw = {"encryption": encryption, "owner_pw": owner_pw, "user_pw": user_pw}
    doc.save(path, **kw)
    doc.close()
    return path


def test_blocks_have_geometry_and_sizes(tmp_path):
    p = make_pdf(tmp_path / "a.pdf", [[
        (72, 100, "Chapter 1", 16, "helv"),
        (72, 200, "The ship left the harbour at dawn and the wind was fair.", 10, "helv"),
    ]])
    raw = PdfExtractor().extract(p, CFG)
    assert raw.pages == 1 and len(raw.page_rects) == 1
    assert all(b.kind is BlockKind.PARA for b in raw.blocks)     # эвристик нет — всё PARA
    sizes = sorted(b.font_size for b in raw.blocks)
    assert sizes == [10.0, 16.0]
    b0 = raw.blocks[0]
    assert b0.page == 1 and b0.bbox is not None and b0.origin.startswith("pdf:")
    assert "harbour" in raw.ref_text


def test_hyphen_merge_inside_block(tmp_path):
    # §6.7.3: строки ОДНОГО блока склеиваются по правилу переносов 6.1.2.
    # Две insert_text-строки с шагом в межстрочник MuPDF собирает в один блок;
    # прекондишн-assert проверяет геометрию фикстуры: если он упал — чинить
    # фикстуру (позиции строк), а НЕ экстрактор. Перенос через ГРАНИЦУ блоков —
    # работа P6, здесь не тестируется.
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "the har-", fontsize=10, fontname="helv")
    page.insert_text((72, 112), "bour was calm", fontsize=10, fontname="helv")
    tblocks = [b for b in page.get_text("dict", sort=True)["blocks"]
               if b.get("type") == 0]
    assert len(tblocks) == 1 and len(tblocks[0]["lines"]) == 2   # прекондишн фикстуры
    doc.save(tmp_path / "h.pdf")
    doc.close()
    raw = PdfExtractor().extract(tmp_path / "h.pdf", CFG)
    joined = " ".join(b.text for b in raw.blocks)
    assert "harbour" in joined and "har-" not in joined


def test_bold_flag(tmp_path):
    p = make_pdf(tmp_path / "b.pdf",
                 [[(72, 100, "Bold line", 10, "hebo"),
                   (72, 200, "Plain line", 10, "helv")]])
    raw = PdfExtractor().extract(p, CFG)
    by_text = {b.text: b.bold for b in raw.blocks}
    assert by_text["Bold line"] is True and by_text["Plain line"] is False


def test_scan_raises(tmp_path):
    doc = pymupdf.open()
    for _ in range(5):
        pg = doc.new_page()
        pg.draw_rect(pymupdf.Rect(50, 50, 500, 700), fill=(0.8, 0.8, 0.8))
    doc.save(tmp_path / "s.pdf")
    doc.close()
    with pytest.raises(ScanError, match="скан"):
        PdfExtractor().extract(tmp_path / "s.pdf", CFG)


def test_encrypted_raises(tmp_path):
    p = make_pdf(tmp_path / "e.pdf", [[(72, 100, "locked", 10, "helv")]],
                 encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    with pytest.raises(EncryptedError):
        PdfExtractor().extract(p, CFG)


def test_empty_user_password_opens(tmp_path):
    # §6.7.1 / 0.29: пустой user-пароль → открывается штатно
    p = make_pdf(tmp_path / "p.pdf",
                 [[(72, 100, "Chapter 1", 16, "helv"),
                   (72, 200, "Open sesame text for the reader.", 10, "helv")]],
                 encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="")
    raw = PdfExtractor().extract(p, CFG)
    assert any("sesame" in b.text for b in raw.blocks)
