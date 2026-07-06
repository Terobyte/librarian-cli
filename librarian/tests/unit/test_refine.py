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
