from librarian.ir import Block, BlockKind, Chapter, Format, RawDoc, ReportDraft, DocContext

def test_block_defaults():
    b = Block(kind=BlockKind.PARA, text="hello")
    assert (b.level, b.page, b.bbox, b.font_size, b.bold, b.origin) == (None, None, None, None, False, "")

def test_chapter_defaults():
    c = Chapter(n=0, title="t", blocks=[])
    assert c.tokens == 0 and c.part is None

def test_format_values():
    assert Format.TXT.value == "txt" and Format.MD.value == "md"
