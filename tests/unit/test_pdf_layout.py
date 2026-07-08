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


# --- P5 ---------------------------------------------------------------------

def _sized_doc():
    body = [para("Обычный длинный абзац основного текста номер %d. Он тянется и тянется." % i,
                 bbox=(72, 200 + 40 * i, 520, 230 + 40 * i), size=10.0)
            for i in range(6)]
    return body


def test_p5_size_histogram_levels():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Volume I", bbox=(72, 60, 200, 84), size=20.0),
               para("Chapter 1", bbox=(72, 100, 200, 120), size=16.0)]
              + _sized_doc()
              + [para("Volume II", page=1, bbox=(72, 500, 200, 524), size=20.0),
                 para("Chapter 2", page=1, bbox=(72, 540, 200, 560), size=16.0)])
    out = p5_headings(blocks, ctx)
    heads = {b.text: b.level for b in out if b.kind is BlockKind.HEADING}
    assert heads == {"Volume I": 1, "Volume II": 1, "Chapter 1": 2, "Chapter 2": 2}


def test_p5_rejects_long_and_punctuated():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    long3 = para("Три строки крупного текста " * 6, bbox=(72, 60, 520, 130),
                 size=16.0, lines=3)                               # > 2 строк
    dotted = para("Это не заголовок.", bbox=(72, 140, 300, 160), size=16.0)
    blocks = [long3, dotted] + _sized_doc() + [
        para("Настоящий", bbox=(72, 500, 200, 520), size=16.0),
        para("Второй настоящий", bbox=(72, 540, 300, 560), size=16.0)]
    out = p5_headings(blocks, ctx)
    kinds = {b.text[:12]: b.kind for b in out}
    assert kinds["Три строки к"] is BlockKind.PARA
    assert kinds["Это не загол"] is BlockKind.PARA
    assert kinds["Настоящий"] is BlockKind.HEADING


def test_p5_bold_rule_next_level():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Chapter 1", bbox=(72, 60, 200, 80), size=16.0),
               para("Chapter 2", bbox=(72, 90, 200, 110), size=16.0)]
              + _sized_doc()
              + [para("Врез жирным", bbox=(72, 500, 220, 515), size=10.0, bold=True)])
    out = p5_headings(blocks, ctx)
    bold = next(b for b in out if b.text == "Врез жирным")
    assert bold.kind is BlockKind.HEADING and bold.level == 2      # 1 размерный + 1


def test_p5_monofont_falls_back_to_patterns():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = [para("Chapter 1", bbox=(72, 60, 200, 80))] + _sized_doc()
    out = p5_headings(blocks, ctx)                                 # все 10pt
    head = next(b for b in out if b.kind is BlockKind.HEADING)
    assert head.text == "Chapter 1" and head.origin == "pattern:rank3"


def test_p5_multiline_heading_merged():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Очень длинное", bbox=(72, 60, 300, 80), size=16.0),
               para("название главы", bbox=(72, 82, 300, 102), size=16.0)]
              + _sized_doc())
    out = p5_headings(blocks, ctx)
    heads = [b for b in out if b.kind is BlockKind.HEADING]
    assert len(heads) == 1 and heads[0].text == "Очень длинное название главы"
    assert heads[0].origin == "pdf:2"                   # честное число строк после склейки
    swallowed = next(b for b in blocks if b.text == "название главы")
    assert swallowed.kind is BlockKind.PARA             # фантом в raw.blocks демотирован


def test_p5_two_distinct_short_headings_not_merged():
    # отклонение 27: два РАЗНЫХ коротких заголовка рядом (короткие главы на
    # одной странице) не должны схлопнуться в «Chapter 1 Chapter 2»
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Chapter 1", bbox=(72, 60, 200, 80), size=16.0),
               para("Chapter 2", bbox=(72, 90, 200, 110), size=16.0)]
              + _sized_doc())
    out = p5_headings(blocks, ctx)
    heads = [b.text for b in out if b.kind is BlockKind.HEADING]
    assert heads == ["Chapter 1", "Chapter 2"]


def test_p5_levels_found_but_no_candidates_no_pattern_fallback():
    # §7.2 P5.5 буквально: паттерны 6.1.3 — ТОЛЬКО если размерных уровней
    # «не нашлось вовсе»; уровни есть, но кандидаты отфильтрованы → фолбэка нет
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    big = [para("Крупный кегль, но это длинное предложение с точкой на конце.",
                bbox=(72, 60 + 90 * i, 520, 130 + 90 * i), size=16.0, lines=3)
           for i in range(2)]
    blocks = big + [para("Chapter 1", bbox=(72, 300, 200, 320))] + _sized_doc()
    out = p5_headings(blocks, ctx)                      # «Chapter 1» — мишень паттернов
    assert all(b.kind is BlockKind.PARA for b in out)   # но фолбэк не сработал


# --- P6 ---------------------------------------------------------------------

def test_p6_merges_across_pages_with_hyphen():
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    a = para("Корабль шёл на юг сквозь тяжёлую во-", page=1, bbox=(72, 700, 520, 730))
    b = para("ду, и берег таял за кормой.", page=2, bbox=(72, 80, 520, 110))
    out = p6_cross_page([a, b], ctx)
    assert len(out) == 1
    assert "воду, и берег" in out[0].text


def test_p6_respects_sentence_end():
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    a = para("Предложение закончилось.", page=1, bbox=(72, 700, 520, 730))
    b = para("и началось новое со строчной", page=2, bbox=(72, 80, 520, 110))
    assert len(p6_cross_page([a, b], ctx)) == 2


def test_p6_three_page_chain_merges_fully():
    # риск-находка ревью: цепочка через 3 страницы должна домердживаться
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=3)
    a = para("Корабль шёл на юг сквозь тяжёлую во-", page=1, bbox=(72, 700, 520, 730))
    b = para("ду по всему проливу, где берег та-", page=2, bbox=(72, 80, 520, 110))
    c = para("ял за кормой.", page=3, bbox=(72, 80, 520, 110))
    out = p6_cross_page([a, b, c], ctx)
    assert len(out) == 1
    assert "воду" in out[0].text and "таял" in out[0].text


def test_p6_merges_across_pictureonly_page():
    # страница-иллюстрация без PARA-блоков не рвёт склейку
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=3)
    a = para("Хвост предложения без точки и с продолжением на", page=1,
             bbox=(72, 700, 520, 730))
    c = para("следующей текстовой странице.", page=3, bbox=(72, 80, 520, 110))
    assert len(p6_cross_page([a, c], ctx)) == 1


def test_p6_does_not_merge_through_heading():
    # заголовок в начале следующей страницы = граница главы, склейки нет
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    a = para("глава оборвалась на полуслове без точки и", page=1,
             bbox=(72, 700, 520, 730))
    h = Block(BlockKind.HEADING, "Chapter 2", level=1, page=2, bbox=(72, 60, 200, 80))
    b = para("новый текст со строчной", page=2, bbox=(72, 100, 520, 130))
    assert len(p6_cross_page([a, h, b], ctx)) == 3


def test_p6_skips_footnote_candidate():
    # отклонение 28: сноска (мелкий кегль, подвал страницы) — последний PARA
    # страницы в sort-порядке; она НЕ должна срастись с телом следующей страницы
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    body1 = para("Абзац, обрывающийся без точки в конце страницы и", page=1,
                 bbox=(72, 600, 520, 630))
    fn = para("1 Сноска мелким кеглем без точки", page=1,
              bbox=(72, 780, 520, 800), size=8.0)
    body2 = para("это тело, продолжающееся здесь.", page=2,
                 bbox=(72, 100, 520, 130))
    out = p6_cross_page([body1, fn, body2], ctx)
    assert [b.text for b in out] == [body1.text, fn.text, body2.text]


# --- P7 ---------------------------------------------------------------------

def test_p7_footnote_tagged_and_kept_in_place():
    from librarian.passes.pdf_layout import p7_footnotes
    ctx = ctx_pdf()
    blocks = _sized_doc() + [
        para("1 Сноска мелким кеглем у подвала страницы.",
             bbox=(72, 780, 520, 800), size=8.0)]
    out = p7_footnotes(blocks, ctx)
    assert out[-1].kind is BlockKind.FOOTNOTE                      # позиция не меняется
    assert ctx.report.removed["footnotes_moved"] == 1


def test_p7_drop_mode(monkeypatch):
    import dataclasses
    from librarian.passes.pdf_layout import p7_footnotes
    ctx = ctx_pdf()
    ctx.cfg = dataclasses.replace(
        ctx.cfg, pdf=dataclasses.replace(ctx.cfg.pdf, footnotes="drop"))
    blocks = _sized_doc() + [
        para("* Сноска на выброс.", bbox=(72, 780, 520, 800), size=8.0)]
    out = p7_footnotes(blocks, ctx)
    assert all(b.kind is not BlockKind.FOOTNOTE for b in out)
    assert ctx.report.removed["footnotes_dropped"] == 1


# --- подключение ------------------------------------------------------------

def test_pdf_passes_wired_for_pdf_only():
    from librarian.passes.normalize import apply_block_passes
    ctx = ctx_pdf()
    blocks = [para("— 4 —", bbox=(280, 810, 315, 825))]            # P1-мишень
    assert apply_block_passes(blocks, ctx) == []                   # PDF: P1 удалил

    from librarian.ir import DocContext, Format, RawDoc, ReportDraft
    raw_txt = RawDoc(fmt=Format.TXT, blocks=[], title=None, author=None,
                     lang=None, ref_text="")
    ctx_txt = DocContext(Format.TXT, ctx.cfg, raw_txt, ReportDraft())
    kept = apply_block_passes([Block(BlockKind.PARA, "— 4 —")], ctx_txt)
    assert len(kept) == 1                                          # не-PDF не трогаем
