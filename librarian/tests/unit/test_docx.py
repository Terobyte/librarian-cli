# tests/unit/test_docx.py
import zipfile

import pytest

from librarian.config import load_config
from librarian.errors import BrokenFileError
from librarian.extractors.docx import DocxExtractor
from librarian.ir import BlockKind

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>
</w:styles>"""


def _para(text: str, style: str | None) -> str:
    pr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{pr}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def make_docx(path, paragraphs, title=None, author=None, extra_body_xml=""):
    """Минимальный детерминированный DOCX: paragraphs = [(styleId|None, текст)]."""
    body = "".join(_para(t, s) for s, t in paragraphs) + extra_body_xml
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    core_fields = ""
    if title:
        core_fields += f"<dc:title>{title}</dc:title>"
    if author:
        core_fields += f"<dc:creator>{author}</dc:creator>"
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties'
            ' xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
            f' xmlns:dc="http://purl.org/dc/elements/1.1/">{core_fields}</cp:coreProperties>')
    entries = [("[Content_Types].xml", _CT), ("_rels/.rels", _RELS),
               ("word/_rels/document.xml.rels", _DOC_RELS),
               ("word/document.xml", doc), ("word/styles.xml", _STYLES),
               ("docProps/core.xml", core)]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))  # детерминизм
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    return path


_BODY = "Судно вышло из гавани на рассвете, и ветер был попутный. " * 6

_TABLE = ('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>День</w:t></w:r></w:p></w:tc>'
          '<w:tc><w:p><w:r><w:t>Мили</w:t></w:r></w:p></w:tc></w:tr>'
          '<w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>'
          '<w:tc><w:p><w:r><w:t>120</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')


def test_headings_paras_and_meta(tmp_path):
    p = make_docx(tmp_path / "a.docx",
                  [("Heading1", "Глава 1. Отплытие"), (None, _BODY),
                   ("Heading2", "Наблюдение"), (None, _BODY)],
                  title="Отчёт о плавании", author="Пелагея Морская")
    raw = DocxExtractor().extract(p, load_config(None))
    kinds = [(b.kind, b.level) for b in raw.blocks]
    assert kinds == [(BlockKind.HEADING, 1), (BlockKind.PARA, None),
                     (BlockKind.HEADING, 2), (BlockKind.PARA, None)]
    assert raw.title == "Отчёт о плавании" and raw.author == "Пелагея Морская"
    assert "Судно вышло из гавани" in raw.ref_text        # mammoth.extract_raw_text


def test_table_mapped(tmp_path):
    p = make_docx(tmp_path / "t.docx", [(None, _BODY)], extra_body_xml=_TABLE)
    raw = DocxExtractor().extract(p, load_config(None))
    tables = [b for b in raw.blocks if b.kind is BlockKind.TABLE]
    assert tables and tables[0].text == "День\tМили\n1\t120"


def test_fallback_patterns_without_styles(tmp_path):
    # §6.5: ни одного HEADING → паттерны 6.1.3 по PARA-блокам
    p = make_docx(tmp_path / "f.docx",
                  [(None, "Глава 1"), (None, _BODY), (None, "Глава 2"), (None, _BODY)])
    raw = DocxExtractor().extract(p, load_config(None))
    heads = [b for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert [h.text for h in heads] == ["Глава 1", "Глава 2"]
    assert heads[0].level == 1 and heads[0].origin == "pattern:rank3"


def test_broken_zip_raises(tmp_path):
    p = tmp_path / "b.docx"
    p.write_bytes(b"PK\x03\x04" + "мусор далеко не zip".encode("utf-8"))
    with pytest.raises(BrokenFileError):
        DocxExtractor().extract(p, load_config(None))


def test_missing_core_xml_gives_none_meta(tmp_path):
    p = make_docx(tmp_path / "m.docx", [("Heading1", "Глава 1"), (None, _BODY)])
    raw = DocxExtractor().extract(p, load_config(None))
    assert raw.title is None and raw.author is None
