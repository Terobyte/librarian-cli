# tests/unit/test_fb2.py
from librarian.config import load_config
from librarian.extractors.fb2 import Fb2Extractor
from librarian.ir import BlockKind

_TPL = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
             xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info>
  <author><first-name>Иван</first-name><last-name>Хвостов</last-name></author>
  <book-title>Сказка о ките</book-title>
  <lang>ru</lang>
</title-info></description>
{bodies}
</FictionBook>"""


def _extract(tmp_path, bodies: str):
    p = tmp_path / "b.fb2"
    p.write_text(_TPL.format(bodies=bodies), encoding="utf-8")
    return Fb2Extractor().extract(p, load_config(None))


def test_metadata(tmp_path):
    raw = _extract(tmp_path, "<body><section><p>Текст.</p></section></body>")
    assert raw.title == "Сказка о ките"
    assert raw.author == "Иван Хвостов"
    assert raw.lang == "ru"


def test_section_depth_becomes_heading_level(tmp_path):
    raw = _extract(tmp_path, """<body>
      <title><p>Сказка о ките</p></title>
      <section><title><p>Часть первая</p></title>
        <section><title><p>Глава 1</p></title><p>Жил-был кит.</p></section>
      </section></body>""")
    heads = [(b.text, b.level) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Часть первая", 1), ("Глава 1", 2)]   # title body — пропущен


def test_epigraph_and_cite_are_quotes(tmp_path):
    raw = _extract(tmp_path, """<body><section>
      <epigraph><p>Море зовёт.</p><text-author>Н. Волнов</text-author></epigraph>
      <p>Абзац.</p>
      <cite><p>Цитата в тексте.</p></cite>
    </section></body>""")
    quotes = [b.text for b in raw.blocks if b.kind is BlockKind.QUOTE]
    assert quotes == ["Море зовёт.\nН. Волнов", "Цитата в тексте."]


def test_poem_stanzas(tmp_path):
    raw = _extract(tmp_path, """<body><section><poem>
      <stanza><v>Волна идёт,</v><v>волна поёт.</v></stanza>
      <stanza><v>А кит молчит.</v></stanza>
    </poem></section></body>""")
    poems = [b for b in raw.blocks if b.origin == "poem"]
    assert [b.text for b in poems] == ["Волна идёт,\nволна поёт.", "А кит молчит."]
    assert all(b.kind is BlockKind.PARA for b in poems)


def test_subtitle_one_deeper(tmp_path):
    raw = _extract(tmp_path, """<body><section><title><p>Глава</p></title>
      <p>Текст.</p><subtitle>* * *</subtitle><p>Ещё.</p></section></body>""")
    heads = [(b.text, b.level) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Глава", 1), ("* * *", 2)]


def test_table_binary_skipped(tmp_path):
    raw = _extract(tmp_path, """<body><section>
      <table><tr><th>ключ</th><th>значение</th></tr><tr><td>а</td><td>1</td></tr></table>
      <p>После таблицы.</p></section></body>
      <binary id="cover.png" content-type="image/png">aWdub3JlZA==</binary>""")
    table = [b for b in raw.blocks if b.kind is BlockKind.TABLE]
    assert table[0].text == "ключ\tзначение\nа\t1"
    assert "aWdub3JlZA" not in " ".join(b.text for b in raw.blocks)


def test_ref_text_from_bodies(tmp_path):
    raw = _extract(tmp_path, "<body><section><p>Опорный текст.</p></section></body>")
    assert "Опорный текст." in raw.ref_text


def test_broken_xml(tmp_path):
    import pytest
    from librarian.errors import BrokenFileError
    p = tmp_path / "b.fb2"
    p.write_text("<FictionBook><body>", encoding="utf-8")
    with pytest.raises(BrokenFileError, match="битый XML"):
        Fb2Extractor().extract(p, load_config(None))


def test_registered():
    from librarian import extractors                      # noqa: F401 — триггер регистрации
    from librarian.extractors.base import get_extractor
    from librarian.ir import Format
    assert type(get_extractor(Format.FB2)).__name__ == "Fb2Extractor"
