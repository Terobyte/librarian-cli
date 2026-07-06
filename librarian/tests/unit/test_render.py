from librarian.config import Config
from librarian.emit import canonical_json, chapter_filename, render_chapter
from librarian.ir import Block, BlockKind, Chapter

K = BlockKind

def test_render_full():
    ch = Chapter(1, "Том · Глава 1", [
        Block(K.PARA, "Абзац один."),
        Block(K.HEADING, "Сцена", level=1),
        Block(K.QUOTE, "строка раз\nстрока два"),
        Block(K.LIST_ITEM, "первый"),
        Block(K.LIST_ITEM, "второй"),
        Block(K.CODE, "x = `тик`"),
        Block(K.TABLE, "Имя\tЗначение\nа|б\t2"),
        Block(K.META, "скрыто"),
        Block(K.FOOTNOTE, "1. сноска"),
        Block(K.PARA, "Последний."),
    ])
    md = render_chapter(ch)
    lines = md.split("\n")
    assert lines[0] == "# Том · Глава 1"
    assert "## Сцена" in md
    assert "> строка раз\n> строка два" in md
    assert "- первый\n- второй" in md
    assert "``` " not in md and "```\nx = `тик`\n```" in md
    assert "| Имя | Значение |" in md and "|---|---|" in md and "а\\|б" in md
    assert "скрыто" not in md
    assert md.rstrip("\n").endswith("1. сноска") and "\n---\n" in md
    assert md.endswith("\n") and not md.endswith("\n\n")
    assert not any(ln != ln.rstrip() for ln in lines)

def test_fence_grows():
    ch = Chapter(1, "T", [Block(K.CODE, "a ```` b")])
    assert "`````\na ```` b\n`````" in render_chapter(ch)

def test_canonical_json():
    s = canonical_json({"б": 1, "а": [2, 1]})
    assert s == '{\n  "а": [\n    2,\n    1\n  ],\n  "б": 1\n}\n'

def test_chapter_filename():
    cfg = Config()
    assert chapter_filename(Chapter(3, "Глава 1. Начало пути", []), cfg) == "003-glava-1-nachalo-puti.md"
    part = Chapter(7, "Стенограмма (2/5)", [], part=2)
    assert chapter_filename(part, cfg) == "007-stenogramma-p2.md"
