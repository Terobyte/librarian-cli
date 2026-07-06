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


_NOTES = """<body>
  <section><title><p>Глава 1</p></title>
    <p>Кит<a l:href="#n1" type="note">1</a> плыл на юг.</p>
    <p>Ссылка<a l:href="#n2" type="note">[2]</a> уже в скобках.</p>
  </section></body>
<body name="notes">
  <section id="n1"><title><p>1</p></title><p>Кит — морское млекопитающее.</p></section>
  <section id="n2"><title><p>2</p></title><p>Вторая сноска.</p></section>
</body>"""


def test_inline_note_markers(tmp_path):
    raw = _extract(tmp_path, _NOTES)
    paras = [b.text for b in raw.blocks if b.kind is BlockKind.PARA]
    assert "Кит[1] плыл на юг." in paras
    assert "Ссылка[2] уже в скобках." in paras        # скобки не задвоены


def test_notes_chapter_appended(tmp_path):
    raw = _extract(tmp_path, _NOTES)
    heads = [b for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[-1].text == "Примечания" and heads[-1].level == 1
    tail = [b.text for b in raw.blocks[raw.blocks.index(heads[-1]) + 1:]]
    assert tail == ["1. Кит — морское млекопитающее.", "2. Вторая сноска."]


def test_notes_body_not_in_main_flow(tmp_path):
    raw = _extract(tmp_path, _NOTES)
    idx_notes = next(i for i, b in enumerate(raw.blocks) if b.text == "Примечания")
    main = " ".join(b.text for b in raw.blocks[:idx_notes])
    assert "морское млекопитающее" not in main


def test_no_notes_no_synthetic_chapter(tmp_path):
    raw = _extract(tmp_path, "<body><section><p>Текст.</p></section></body>")
    assert all(b.text != "Примечания" for b in raw.blocks)


def _make_fb2_zip(tmp_path, fb2_text: str, extra=()):
    import zipfile
    p = tmp_path / "arhiv.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("kniga.fb2", fb2_text.encode("utf-8"))
        for name, data in extra:
            z.writestr(name, data)
    return p


def test_fb2_zip(tmp_path):
    p = _make_fb2_zip(tmp_path, _TPL.format(
        bodies="<body><section><p>Из архива.</p></section></body>"))
    raw = Fb2Extractor().extract(p, load_config(None))
    assert raw.title == "Сказка о ките"
    assert any("Из архива" in b.text for b in raw.blocks)


def test_fb2_zip_bomb(tmp_path):
    import dataclasses
    import pytest
    from librarian.config import LimitsCfg
    from librarian.errors import BrokenFileError
    p = _make_fb2_zip(tmp_path,
                      _TPL.format(bodies="<body><section><p>x</p></section></body>"),
                      extra=[("padding.bin", b"\0" * (2 * 1024 * 1024))])
    cfg = dataclasses.replace(load_config(None),
                              limits=LimitsCfg(zip_max_uncompressed_mb=1))
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        Fb2Extractor().extract(p, cfg)


_XXE_FB2 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE FictionBook [<!ENTITY leak SYSTEM "secret.txt">]>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description><title-info><book-title>Ловушка</book-title></title-info></description>
<body><section><title><p>Глава 1</p></title>
<p>До сноски &leak; после сноски.</p>
<p>Обычный длинный абзац, чтобы у главы был вес и книга сохранилась.</p>
</section></body>
</FictionBook>"""


def test_xxe_entity_not_expanded(tmp_path):
    (tmp_path / "secret.txt").write_text("СОВЕРШЕННО СЕКРЕТНО", encoding="utf-8")
    p = tmp_path / "xxe.fb2"
    p.write_text(_XXE_FB2, encoding="utf-8")
    raw = Fb2Extractor().extract(p, load_config(None))
    joined = " ".join(b.text for b in raw.blocks) + raw.ref_text
    assert "СЕКРЕТНО" not in joined


def test_xxe_ingest_end_to_end(tmp_path):
    from librarian.pipeline import run_ingest
    (tmp_path / "secret.txt").write_text("СОВЕРШЕННО СЕКРЕТНО", encoding="utf-8")
    p = tmp_path / "xxe.fb2"
    p.write_text(_XXE_FB2, encoding="utf-8")
    lib = tmp_path / "lib"
    outcomes = run_ingest([p], load_config(None), lib)
    assert outcomes[0].status != "ok" or outcomes[0].book_id   # сохранилась или честный отказ
    leaked = [f for f in lib.rglob("*.md")
              if "СЕКРЕТНО" in f.read_text(encoding="utf-8")]
    assert leaked == []
