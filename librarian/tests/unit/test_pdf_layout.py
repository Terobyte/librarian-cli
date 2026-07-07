# tests/unit/test_pdf_layout.py
from librarian.config import load_config
from librarian.ir import Block, BlockKind, DocContext, Format, RawDoc, ReportDraft


def ctx_pdf(pages=1, w=595.0, h=842.0):
    cfg = load_config(None)
    raw = RawDoc(fmt=Format.PDF, blocks=[], title=None, author=None, lang=None,
                 ref_text="", pages=pages, page_rects=[(0.0, 0.0, w, h)] * pages)
    return DocContext(Format.PDF, cfg, raw, ReportDraft())


def para(text, page=1, bbox=(72, 400, 300, 420), size=10.0, bold=False, lines=1):
    return Block(BlockKind.PARA, text, page=page, bbox=bbox,
                 font_size=size, bold=bold, origin=f"pdf:{lines}")


# --- P1 ---------------------------------------------------------------------

def test_p1_removes_decorated_pagenum_in_zone():
    from librarian.passes.pdf_layout import p1_page_numbers
    ctx = ctx_pdf()
    blocks = [para("— 12 —", bbox=(280, 810, 315, 825)),          # низ, зона 10%
              para("iv", bbox=(280, 20, 315, 40)),                 # верх, римская
              para("12", bbox=(280, 400, 315, 420)),               # середина — не трогать
              para("1234567", bbox=(280, 810, 315, 825))]          # длиннее 4 — не номер
    out = p1_page_numbers(blocks, ctx)
    assert [b.text for b in out] == ["12", "1234567"]
    assert ctx.report.removed["page_numbers"] == 2


def test_p1_keeps_large_roman_chapter_number():
    # отклонение 25: крупный кегль в зоне колонтитула — вероятный номер главы,
    # P1 его не трогает (иначе заголовок погибнет до того, как P5 его увидит)
    from librarian.passes.pdf_layout import p1_page_numbers
    ctx = ctx_pdf()
    blocks = [para("IV", bbox=(280, 30, 315, 60), size=20.0)] + [
        para(f"Обычный длинный абзац основного текста номер {i}.",
             bbox=(72, 200 + 40 * i, 520, 230 + 40 * i))
        for i in range(4)]
    out = p1_page_numbers(blocks, ctx)
    assert any(b.text == "IV" for b in out)


# --- P2 ---------------------------------------------------------------------

def test_p2_frequent_running_header_removed():
    from librarian.passes.pdf_layout import p2_headers_footers
    ctx = ctx_pdf(pages=10)
    blocks = []
    for p in range(1, 11):
        blocks.append(para(f"Voyage Log · стр. {p}", page=p, bbox=(200, 20, 400, 40)))
        blocks.append(para(f"Body paragraph {p}", page=p))
    rare = para("Одинокая шапка", page=1, bbox=(200, 20, 400, 40))
    blocks.append(rare)
    out = p2_headers_footers(blocks, ctx)
    texts = [b.text for b in out]
    assert all(not t.startswith("Voyage Log") for t in texts)      # 10 стр ≥ порога
    assert "Одинокая шапка" in texts                               # 1 стр < hf_min_pages
    hf = ctx.report.removed["headers_footers"]
    assert hf[0]["signature"] == "voyage log · стр. #"
    assert hf[0]["pages"] == list(range(1, 11))


def test_p2_short_doc_protected_by_min_pages():
    from librarian.passes.pdf_layout import p2_headers_footers
    ctx = ctx_pdf(pages=3)                                         # ceil(0.3*3)=1 < 5
    blocks = [para("Шапка", page=p, bbox=(200, 20, 400, 40)) for p in (1, 2, 3)]
    assert len(p2_headers_footers(blocks, ctx)) == 3


# --- P3 ---------------------------------------------------------------------

def _two_column_page(page=1):
    # 3 блока слева (x-центр ~160), 3 справа (~440); порядок sort=True — по y
    left = [para(f"L{i}", page=page, bbox=(60, 100 + 200 * i, 260, 120 + 200 * i))
            for i in range(3)]
    right = [para(f"R{i}", page=page, bbox=(340, 100 + 200 * i, 540, 120 + 200 * i))
             for i in range(3)]
    interleaved = [b for pair in zip(left, right) for b in pair]   # L0 R0 L1 R1 …
    return interleaved


def test_p3_two_columns_reordered():
    from librarian.passes.pdf_layout import p3_reading_order
    ctx = ctx_pdf()
    out = p3_reading_order(_two_column_page(), ctx)
    assert [b.text for b in out] == ["L0", "L1", "L2", "R0", "R1", "R2"]
    assert ctx.report.multi_column_pages == []


def test_p3_three_columns_flagged_order_kept():
    from librarian.passes.pdf_layout import p3_reading_order
    ctx = ctx_pdf()
    blocks = [para(f"C{c}{i}", bbox=(40 + 180 * c, 100 + 200 * i,
                                     180 + 180 * c, 120 + 200 * i))
              for i in range(3) for c in range(3)]
    out = p3_reading_order(blocks, ctx)
    assert [b.text for b in out] == [b.text for b in blocks]       # порядок не тронут
    assert ctx.report.multi_column_pages == [1]


def test_p3_single_column_untouched():
    from librarian.passes.pdf_layout import p3_reading_order
    ctx = ctx_pdf()
    blocks = [para(f"B{i}", bbox=(72, 100 + 40 * i, 520, 130 + 40 * i))
              for i in range(4)]
    assert [b.text for b in p3_reading_order(blocks, ctx)] == ["B0", "B1", "B2", "B3"]


# --- P4 ---------------------------------------------------------------------

def test_p4_defect_page_flagged():
    from librarian.passes.pdf_layout import p4_defect_pages
    ctx = ctx_pdf(pages=2)
    good = para("Чистый текст страницы один. " * 5, page=1)
    bad = para("Гнилой" + "�" * 20 + " текст", page=2)        # ~70% мусора
    out = p4_defect_pages([good, bad], ctx)
    assert len(out) == 2                                           # ничего не удаляется
    assert ctx.report.pages_flagged == [2]
    assert "страница 2" in ctx.report.warnings[0]


def test_p4_counts_private_use_area():
    # PUA (категория Co) — типичный след битого шрифт-маппинга, считается дефектом
    from librarian.passes.pdf_layout import p4_defect_pages
    ctx = ctx_pdf()
    bad = para("Тело " + "\ue000\ue001" * 10, page=1)   # 20 из 25 симв. — PUA
    p4_defect_pages([bad], ctx)
    assert ctx.report.pages_flagged == [1]
