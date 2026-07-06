import pytest
from librarian.config import Config
from librarian.ir import Block, BlockKind, Chapter, DocContext, Format, RawDoc, ReportDraft
from librarian.passes.sections import apply_section_passes, r3_merge_tiny, r4_split_giants

H, P = BlockKind.HEADING, BlockKind.PARA

def _ctx():
    return DocContext(Format.TXT, Config(),
                      RawDoc(Format.TXT, [], None, None, None, ""), ReportDraft())

def _big_para():
    return Block(P, "слово " * 300)

def test_r3_tiny_merges_into_next():
    tiny = Chapter(0, "Эпиграф", [Block(P, "короткая строка")])
    big = Chapter(0, "Глава 1", [_big_para()])
    out = r3_merge_tiny([tiny, big], _ctx())
    assert len(out) == 1 and out[0].title == "Глава 1"
    assert out[0].blocks[0].kind is H and out[0].blocks[0].text == "Эпиграф"
    assert out[0].blocks[0].level == 1

def test_r3_last_tiny_appends_to_prev():
    big = Chapter(0, "Глава 1", [_big_para()])
    tiny = Chapter(0, "Финал", [Block(P, "конец")])
    out = r3_merge_tiny([big, tiny], _ctx())
    assert len(out) == 1 and out[0].blocks[-2].text == "Финал"

def test_r4_splits_by_inner_headings():
    ch = Chapter(0, "Часть", [Block(P, "интро " * 50),
                              Block(H, "Гл 1", level=1), Block(P, "слово " * 9000),
                              Block(H, "Гл 2", level=1), Block(P, "слово " * 9000)])
    out = r4_split_giants([ch], _ctx())
    assert len(out) >= 3
    assert out[1].title.startswith("Часть · Гл 1")

def test_r4_mechanical_parts_and_oversize_block():
    ctx = _ctx()
    ch = Chapter(0, "Стенограмма", [Block(P, ("фраза. " * 12000))])
    out = r4_split_giants([ch], ctx)
    assert len(out) > 1
    assert out[0].title == f"Стенограмма (1/{len(out)})" and out[0].part == 1
    assert ctx.report.oversize_blocks_split == 1

def test_pipeline_numbering():
    chs = [Chapter(0, "A", [_big_para()]), Chapter(0, "B", []), Chapter(0, "C", [_big_para()])]
    out = apply_section_passes(chs, _ctx())
    assert [c.n for c in out] == [1, 2]

