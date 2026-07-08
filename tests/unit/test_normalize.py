from librarian.config import Config
from librarian.ir import Block, BlockKind, DocContext, Format, RawDoc, ReportDraft
from librarian.passes.normalize import apply_block_passes, n1_unicode, n2_whitespace, n3_controls

def _ctx():
    raw = RawDoc(Format.TXT, [], None, None, None, "")
    return DocContext(Format.TXT, Config(), raw, ReportDraft())

def test_n1_removes_invisibles_and_nfc():
    b = [Block(BlockKind.PARA, "ку­да​-то\r\nтуда\rвот﻿")]
    out = n1_unicode(b, _ctx())
    assert out[0].text == "куда-то\nтуда\nвот"

def test_n2_collapses_spaces_keeps_code():
    ctx = _ctx()
    out = n2_whitespace([Block(BlockKind.PARA, "a   b\t\tc  \n\n\n\nd  "),
                         Block(BlockKind.CODE, "x\t\ty"),
                         Block(BlockKind.PARA, "   ")], ctx)
    assert out[0].text == "a b c\n\nd"
    assert out[1].text == "x\t\ty"
    assert len(out) == 2

def test_n3_counts_controls():
    ctx = _ctx()
    out = n3_controls([Block(BlockKind.PARA, "a\x01b\x9cc\nd\te")], ctx)
    assert out[0].text == "abc\nd\te"
    assert ctx.report.control_chars == 2

def test_idempotent():
    ctx = _ctx()
    blocks = [Block(BlockKind.PARA, "a  b­\r\nc\x01")]
    once = apply_block_passes(blocks, ctx)
    twice = apply_block_passes([Block(b.kind, b.text) for b in once], ctx)
    assert [b.text for b in once] == [b.text for b in twice]
