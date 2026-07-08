# tests/unit/test_refine.py
from librarian.config import load_config
from librarian.ir import (Block, BlockKind, Chapter, DocContext, Format,
                          RawDoc, ReportDraft)
from librarian.passes.sections import r1_meta_sections


def _ctx(raw_blocks=()):
    return DocContext(fmt=Format.FB2, cfg=load_config(None),
                      raw=RawDoc(fmt=Format.FB2, blocks=list(raw_blocks),
                                 title=None, author=None, lang=None, ref_text=""),
                      report=ReportDraft())


def _ch(title, *texts):
    return Chapter(0, title, [Block(BlockKind.PARA, t) for t in texts])


def test_r1_removes_short_meta_chapter():
    ctx = _ctx()
    chapters = [
        _ch("Выходные данные", "© Издательство «Прибой», 2024. ISBN 978-5-00000-000-0."),
        _ch("Глава 1", "Обычный текст главы, никакого копирайта, просто история."),
    ]
    out = r1_meta_sections(chapters, ctx)
    assert [c.title for c in out] == ["Глава 1"]
    removed = ctx.report.removed["meta_sections"]
    assert removed[0]["title"] == "Выходные данные"
    assert "ISBN" in removed[0]["text"]           # ничего не исчезает бесследно
    assert removed[0]["tokens"] > 0


def test_r1_keeps_long_chapter_with_marker():
    ctx = _ctx()
    long_text = "Герой размышлял о правах. " * 60      # заведомо > 150 токенов
    chapters = [_ch("Глава", long_text + " Все права защищены — подумал он.")]
    assert r1_meta_sections(chapters, ctx) == chapters
    assert "meta_sections" not in ctx.report.removed


def test_r1_keeps_short_chapter_without_marker():
    ctx = _ctx()
    chapters = [_ch("Эпиграф", "Короткий текст без служебных маркеров.")]
    assert r1_meta_sections(chapters, ctx) == chapters


from librarian.passes.sections import SECTION_PASSES, r2_toc


def test_r2_numeric_lines():
    ctx = _ctx()
    toc = Chapter(0, "Содержание", [Block(
        BlockKind.PARA,
        "Пролог 3\nГлава первая 7\nГлава вторая 25\nЭпилог 210")])
    body = _ch("Глава первая", "Длинный текст главы, который никуда не денется.")
    out = r2_toc([toc, body], ctx)
    assert [c.title for c in out] == ["Глава первая"]
    assert "Глава вторая 25" in ctx.report.removed["toc"][0]["text"]


def test_r2_heading_duplicates_without_page_numbers():
    heads = [Block(BlockKind.HEADING, t, level=1)
             for t in ("Пролог", "Глава первая", "Глава вторая", "Эпилог")]
    ctx = _ctx(raw_blocks=heads)
    toc = Chapter(0, "Оглавление", [Block(
        BlockKind.PARA, "Пролог\nГлава  ПЕРВАЯ\nглава вторая\nЭпилог")])
    body = _ch("Глава первая", "Текст.")
    out = r2_toc([toc, body], ctx)
    assert [c.title for c in out] == ["Глава первая"]


def test_r2_keeps_ordinary_chapter():
    ctx = _ctx()
    ch = _ch("Глава 1", "Он посчитал до 5\nи замолчал\nа потом ушёл в ночь")
    assert r2_toc([ch], ctx) == [ch]                    # 1/3 строк с цифрой — мало


def test_r2_respects_size_cap():
    import dataclasses
    from librarian.config import CleanCfg
    ctx = _ctx()
    ctx = dataclasses.replace(ctx, cfg=dataclasses.replace(
        ctx.cfg, clean=CleanCfg(toc_max_tokens=1)))
    toc = Chapter(0, "Содержание", [Block(BlockKind.PARA, "Глава 1 5\nГлава 2 9")])
    assert r2_toc([toc], ctx) == [toc]                  # больше лимита — не трогаем


def test_pass_order_r1_r2_first():
    names = [p.__name__ for p in SECTION_PASSES]
    assert names == ["r1_meta_sections", "r2_toc", "r3_merge_tiny",
                     "r4_split_giants", "r5_drop_empty"]
