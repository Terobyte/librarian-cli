# tests/unit/test_epub.py
import zipfile

from librarian.config import load_config
from librarian.extractors.epub import EpubExtractor
from librarian.ir import BlockKind

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">test-{ident}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>Пелагея Морская</dc:creator>
    <dc:language>ru</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {items}
  </manifest>
  <spine>{spine}</spine>
</package>"""

_XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title></head>
<body>{body}</body></html>"""


def make_epub(path, title, chapters, nav_links, ident="0001"):
    """chapters: list[(fname, body_html)]; nav_links: list[(href, text)]."""
    items = "\n".join(
        f'<item id="c{i}" href="{fn}" media-type="application/xhtml+xml"/>'
        for i, (fn, _) in enumerate(chapters))
    spine = "\n".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
    nav_body = "<nav epub:type=\"toc\" xmlns:epub=\"http://www.idpf.org/2007/ops\"><ol>" + "".join(
        f'<li><a href="{h}">{t}</a></li>' for h, t in nav_links) + "</ol></nav>"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, b"application/epub+zip")
        for name, data in [
            ("META-INF/container.xml", _CONTAINER),
            ("OEBPS/content.opf", _OPF.format(title=title, items=items,
                                              spine=spine, ident=ident)),
            ("OEBPS/nav.xhtml", _XHTML.format(body=nav_body)),
        ] + [(f"OEBPS/{fn}", _XHTML.format(body=b)) for fn, b in chapters]:
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data.encode("utf-8"))
    return path


def _extract(tmp_path, chapters, nav_links=(), title="Повесть о шторме"):
    p = make_epub(tmp_path / "b.epub", title, chapters, list(nav_links))
    return EpubExtractor().extract(p, load_config(None))


def test_metadata(tmp_path):
    raw = _extract(tmp_path, [("ch1.xhtml", "<h1>Глава 1</h1><p>Текст.</p>")])
    assert raw.title == "Повесть о шторме"
    assert raw.author == "Пелагея Морская"
    assert raw.lang == "ru"


def test_spine_order_and_mapping(tmp_path):
    raw = _extract(tmp_path, [
        ("ch1.xhtml", "<h1>Глава 1</h1><p>Первый.</p><blockquote><p>Цитата.</p></blockquote>"),
        ("ch2.xhtml", "<h2>Подглава</h2><ul><li>пункт</li></ul>"),
    ])
    kinds = [(b.kind, b.text) for b in raw.blocks]
    assert kinds == [
        (BlockKind.HEADING, "Глава 1"), (BlockKind.PARA, "Первый."),
        (BlockKind.QUOTE, "Цитата."), (BlockKind.HEADING, "Подглава"),
        (BlockKind.LIST_ITEM, "пункт")]


def test_nav_not_in_flow(tmp_path):
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>Глава 1</h1><p>Текст.</p>"),
                    ("ch2.xhtml", "<h1>Глава 2</h1><p>Ещё.</p>")],
                   nav_links=[("ch1.xhtml", "Глава 1"), ("ch2.xhtml", "Глава 2")])
    # nav.xhtml не в spine у нашего билдера; главное — li из nav не просочились
    assert sum(1 for b in raw.blocks if b.kind is BlockKind.LIST_ITEM) == 0


def test_ref_text(tmp_path):
    raw = _extract(tmp_path, [("ch1.xhtml", "<h1>Глава 1</h1><p>Опорный текст.</p>")])
    assert "Опорный текст." in raw.ref_text


def test_broken_epub(tmp_path):
    import pytest
    from librarian.errors import BrokenFileError
    p = tmp_path / "b.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", b"application/epub+zip")   # ни container, ни opf
    with pytest.raises(BrokenFileError):
        EpubExtractor().extract(p, load_config(None))


def test_registered():
    from librarian import extractors                      # noqa: F401
    from librarian.extractors.base import get_extractor
    from librarian.ir import Format
    assert type(get_extractor(Format.EPUB)).__name__ == "EpubExtractor"


def test_fallback_chapter_per_file(tmp_path):
    raw = _extract(tmp_path,
                   [("text1.xhtml", "<p>Первый файл без заголовков.</p>"),
                    ("text2.xhtml", "<p>Второй файл, тоже голый.</p>")],
                   nav_links=[("text1.xhtml#start", "Пролог"),
                              ("text1.xhtml#more", "Дубль — игнор"),
                              ("text2.xhtml", "Эпилог")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks
             if b.kind is BlockKind.HEADING]
    assert heads == [("Пролог", 1, "epub-fallback"), ("Эпилог", 1, "epub-fallback")]


def test_fallback_without_nav_uses_first_para(tmp_path):
    raw = _extract(tmp_path,
                   [("text1.xhtml", "<p>Однажды на рассвете кит выплыл к берегу.</p>"),
                    ("text2.xhtml", "<p>Вторая часть истории про кита и шторм.</p>")],
                   nav_links=[])
    heads = [b.text for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[0] == "Однажды на рассвете кит выплыл к берегу."[:60]
    assert len(heads) == 2


def test_no_fallback_when_headings_exist(tmp_path):
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>Глава 1</h1><p>Раз.</p>"),
                    ("ch2.xhtml", "<h1>Глава 2</h1><p>Два.</p>")],
                   nav_links=[("ch1.xhtml", "Глава 1"), ("ch2.xhtml", "Глава 2")])
    assert all(b.origin != "epub-fallback" for b in raw.blocks)


def test_nav_fixes_empty_heading(tmp_path):
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>*</h1><p>Текст первой.</p>"),
                    ("ch2.xhtml", "<h1>Глава вторая</h1><p>Текст второй.</p>")],
                   nav_links=[("ch1.xhtml", "Глава первая")])
    heads = [b.text for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == ["Глава первая", "Глава вторая"]


# --- DocBook flat-nav restructure (§6.4.3 отклонение, deviation) -----------


def test_docbook_gate_triggers_on_file_with_two_h1_and_single_nav_entry(tmp_path):
    # t1: 2 файла, файл ch1 — DocBook-стиль (h1 A + p + h1 B + h2 C + h1 D),
    # 1 nav-запись на файл → A остаётся level 1 (origin epub-file), B/D → 2, C → 3.
    # "Sec A" (не 1 символ) — чтобы не задеть несвязанную §6.4.5-починку bs[0].
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>Sec A</h1><p>text</p><h1>B</h1><h2>C</h2><h1>D</h1>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>text</p>")],
                   nav_links=[("ch1.xhtml", "Chapter One"), ("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[:4] == [("Sec A", 1, "epub-file"), ("B", 2, ""), ("C", 3, ""), ("D", 2, "")]


def test_docbook_gate_silent_without_nav_entry(tmp_path):
    # t2: файл с 2×h1, но БЕЗ записи в nav → уровни не тронуты.
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>A</h1><h1>B</h1>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>text</p>")],
                   nav_links=[("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[:2] == [("A", 1, ""), ("B", 1, "")]


def test_docbook_gate_silent_on_povest_style_single_h1_per_file(tmp_path):
    # t3: по одному h1 на файл (povest-стиль), полный nav → блоки идентичны прежним.
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>Chapter One</h1><p>one</p>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>two</p>")],
                   nav_links=[("ch1.xhtml", "Chapter One"), ("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Chapter One", 1, ""), ("Chapter Two", 1, "")]


def test_docbook_gate_prepends_when_file_starts_with_para(tmp_path):
    # t4: файл начинается с PARA, дальше 2×h1, nav есть → prepend nav-заголовок
    # level 1, оба h1 → 2.
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<p>Intro para.</p><h1>A</h1><h1>B</h1>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>text</p>")],
                   nav_links=[("ch1.xhtml", "Chapter One"), ("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[:3] == [("Chapter One", 1, "epub-file"), ("A", 2, ""), ("B", 2, "")]


def test_docbook_restructure_runs_after_empty_heading_fix(tmp_path):
    # t5: первый заголовок пустой/односимвольный + гейт срабатывает → сначала
    # §6.4.5 подставляет nav-текст, потом этот же блок становится epub-file
    # заголовком уровня 1 (порядок — инвариант, m6).
    raw = _extract(tmp_path,
                   [("ch1.xhtml", "<h1>*</h1><p>text</p><h1>B</h1>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>two</p>")],
                   nav_links=[("ch1.xhtml", "Chapter One"), ("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[:2] == [("Chapter One", 1, "epub-file"), ("B", 2, "")]


def test_docbook_gate_is_per_file_in_mixed_book(tmp_path):
    # t6: смешанная книга — честный файл (1 h1 + h2) не трогается байт-в-байт,
    # DocBook-файл (2×h1) рядом перестраивается.
    # "Sec A" (не 1 символ) — чтобы не задеть несвязанную §6.4.5-починку bs[0].
    raw = _extract(tmp_path,
                   [("honest.xhtml", "<h1>Honest Chapter</h1><h2>Sub</h2><p>text</p>"),
                    ("doc.xhtml", "<h1>Sec A</h1><h1>B</h1>")],
                   nav_links=[("honest.xhtml", "Honest Chapter"), ("doc.xhtml", "Doc Chapter")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Honest Chapter", 1, ""), ("Sub", 2, ""),
                      ("Sec A", 1, "epub-file"), ("B", 2, "")]


def test_docbook_gate_silent_on_fragmented_nav(tmp_path):
    # t7: 2 nav-записи на один файл (f.xhtml#a, f.xhtml#b) при 2×h1 → не тронут
    # (nav_counts == 2, файл — несколько TOC-единиц, не одна).
    # "Sec A" (не 1 символ) — чтобы не задеть несвязанную §6.4.5-починку bs[0].
    raw = _extract(tmp_path,
                   [("f.xhtml", "<h1>Sec A</h1><h1>B</h1>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>two</p>")],
                   nav_links=[("f.xhtml#a", "Part A"), ("f.xhtml#b", "Part B"),
                              ("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[:2] == [("Sec A", 1, ""), ("B", 1, "")]


# --- part-divider между DocBook-файлами (Plan v3, repair delta) ------------


def test_part_divider_between_docbook_files_becomes_level1_ancestor(tmp_path):
    # t8: divider-файл (ровно один h1, без остального контента) перед DocBook-
    # главой → divider остаётся level 1 (origin=epub-part), глава сдвигается
    # на +1 (2), её подраздел — ещё на +1 (3).
    raw = _extract(tmp_path,
                   [("part1.xhtml", "<h1>Part One</h1>"),
                    ("ch1.xhtml", "<h1>Chapter One</h1><p>text</p><h1>Sub</h1>")],
                   nav_links=[("part1.xhtml", "Part One"), ("ch1.xhtml", "Chapter One")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Part One", 1, "epub-part"),
                      ("Chapter One", 2, "epub-file"),
                      ("Sub", 3, "")]


def test_part_divider_untouched_without_docbook_files(tmp_path):
    # t9: divider-по-форме файл в книге БЕЗ единого DocBook-гейта (все файлы —
    # по одному h1) → ни тегирования, ни сдвига уровней (restructured_any=False).
    raw = _extract(tmp_path,
                   [("part1.xhtml", "<h1>Part One</h1>"),
                    ("ch1.xhtml", "<h1>Chapter One</h1><p>one</p>"),
                    ("ch2.xhtml", "<h1>Chapter Two</h1><p>two</p>")],
                   nav_links=[("part1.xhtml", "Part One"), ("ch1.xhtml", "Chapter One"),
                              ("ch2.xhtml", "Chapter Two")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Part One", 1, ""), ("Chapter One", 1, ""), ("Chapter Two", 1, "")]


def test_heading_plus_para_file_is_not_a_divider(tmp_path):
    # t10: copyright-стиль файл (h1 + p) НЕ divider даже с одним заголовком —
    # структурное условие divider'а требует РОВНО один блок в файле.
    raw = _extract(tmp_path,
                   [("part1.xhtml", "<h1>Part One</h1>"),
                    ("copyright.xhtml", "<h1>Copyright</h1><p>All rights reserved.</p>"),
                    ("ch1.xhtml", "<h1>Chapter One</h1><p>text</p><h1>Sub</h1>")],
                   nav_links=[("part1.xhtml", "Part One"), ("copyright.xhtml", "Copyright"),
                              ("ch1.xhtml", "Chapter One")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Part One", 1, "epub-part"),
                      ("Copyright", 2, ""),
                      ("Chapter One", 2, "epub-file"),
                      ("Sub", 3, "")]


def test_trailing_heading_only_file_is_not_a_divider(tmp_path):
    # t11: хвостовой heading-only файл (нет файла ПОСЛЕ него) не тегируется
    # divider'ом (B2'), но всё равно попадает под общий сдвиг уровней, раз
    # книга уже содержит restructured-файл и другой помеченный divider.
    raw = _extract(tmp_path,
                   [("part1.xhtml", "<h1>Part One</h1>"),
                    ("ch1.xhtml", "<h1>Chapter One</h1><p>text</p><h1>Sub</h1>"),
                    ("trailing.xhtml", "<h1>The End</h1>")],
                   nav_links=[("part1.xhtml", "Part One"), ("ch1.xhtml", "Chapter One"),
                              ("trailing.xhtml", "The End")])
    heads = [(b.text, b.level, b.origin) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Part One", 1, "epub-part"),
                      ("Chapter One", 2, "epub-file"),
                      ("Sub", 3, ""),
                      ("The End", 2, "")]
