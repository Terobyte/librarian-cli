from librarian.config import Config
from librarian.extractors.txt import TxtExtractor
from librarian.ir import BlockKind

BOOK = """Роман о жизни.

Том первый

Глава 1

Жил-был человек, который никог-
да не сдавался и шёл кто-
то знает куда.

Глава 2

Продолжение истории."""

def test_txt_structure(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes(BOOK.encode("cp1251"))
    raw = TxtExtractor().extract(p, Config())
    kinds = [(b.kind, b.level) for b in raw.blocks]
    assert kinds == [(BlockKind.PARA, None), (BlockKind.HEADING, 1),
                     (BlockKind.HEADING, 2), (BlockKind.PARA, None),
                     (BlockKind.HEADING, 2), (BlockKind.PARA, None)]
    body = raw.blocks[3].text
    assert "никогда не сдавался" in body and "кто-то знает" in body
    assert raw.ref_text.startswith("Роман о жизни.")
    assert raw.title is None and raw.lang is None

def test_txt_koi8r(tmp_path):
    p = tmp_path / "k.txt"
    p.write_bytes("Глава 1\n\nТекст по-русски.".encode("koi8-r"))
    raw = TxtExtractor().extract(p, Config())
    assert raw.blocks[0].text == "Глава 1"

def test_txt_rank_compression(tmp_path):
    p = tmp_path / "g.txt"
    p.write_text("Глава 1\n\nТекст.\n\nГлава 2\n\nЕщё.", encoding="utf-8")
    raw = TxtExtractor().extract(p, Config())
    assert [b.level for b in raw.blocks if b.kind is BlockKind.HEADING] == [1, 1]
