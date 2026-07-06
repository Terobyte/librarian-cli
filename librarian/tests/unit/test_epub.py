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
