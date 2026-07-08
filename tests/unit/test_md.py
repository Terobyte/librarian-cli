from librarian.config import Config
from librarian.extractors.md import MdExtractor
from librarian.ir import BlockKind

DOC = """---
title: тест
---
# Глава 1

Текст с [ссылкой](http://x) и ![картинкой](i.png) и <https://auto.link>.

Заголовок setext
================

подзаголовок
------------

```py
код  с   пробелами
```

> цитата
> вторая строка

- пункт один
- пункт два

***

##### мелкий
"""

def _extract(tmp_path, text):
    p = tmp_path / "d.md"
    p.write_text(text, encoding="utf-8")
    return MdExtractor().extract(p, Config())

def test_md_blocks(tmp_path):
    raw = _extract(tmp_path, DOC)
    b = raw.blocks
    assert (b[0].kind, b[0].origin) == (BlockKind.META, "frontmatter")
    assert (b[1].kind, b[1].level, b[1].text) == (BlockKind.HEADING, 1, "Глава 1")
    assert b[2].text == "Текст с ссылкой и картинкой и https://auto.link."
    assert (b[3].kind, b[3].level) == (BlockKind.HEADING, 1)
    assert (b[4].kind, b[4].level) == (BlockKind.HEADING, 2)
    assert (b[5].kind, b[5].text) == (BlockKind.CODE, "код  с   пробелами")
    assert (b[6].kind, b[6].text) == (BlockKind.QUOTE, "цитата\nвторая строка")
    assert [x.text for x in b[7:9]] == ["пункт один", "пункт два"]
    assert (b[9].kind, b[9].level) == (BlockKind.HEADING, 4)

def test_md_thematic_break_not_setext(tmp_path):
    raw = _extract(tmp_path, "текст\n\n---\n\nещё")
    assert [x.kind for x in raw.blocks] == [BlockKind.PARA, BlockKind.PARA]

def test_md_setext_dash(tmp_path):
    raw = _extract(tmp_path, "Название\n---\n\nтело")
    assert (raw.blocks[0].kind, raw.blocks[0].level) == (BlockKind.HEADING, 2)


def test_md_fallback_retains_hierarchy(tmp_path):
    # BUG F-5: MD fallback сплющивает иерархию заголовков в level=1
    text = "Том 1\n\nГлава первая\n\nТекст.\n\nГлава вторая\n\nЕщё."
    raw = _extract(tmp_path, text)
    headings = [b for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert len(headings) == 3
    assert headings[0].text == "Том 1"
    assert headings[0].level == 1
    assert headings[1].text == "Глава первая"
    assert headings[1].level == 2
    assert headings[2].text == "Глава вторая"
    assert headings[2].level == 2


def test_md_code_block_fence_prefix_safety(tmp_path):
    # BUG F-6: MD fence закрывается по префиксу, теряя контент code-блока
    text = "```\ncode line\n```text\nmore code\n```"
    raw = _extract(tmp_path, text)
    assert len(raw.blocks) == 1
    assert raw.blocks[0].kind is BlockKind.CODE
    assert raw.blocks[0].text == "code line\n```text\nmore code"

