# src/librarian/xmlsafe.py
from __future__ import annotations

import re

import lxml.html
from lxml import etree

_DECL = re.compile(rb"<\?xml[^>]*\?>", re.I)


def decode_html(data: bytes) -> str:
    """Декодируем bytes → str для lxml.html. Голые UTF-8-байты без объявления
    о кодировке lxml по эвристике ошибочно читает как Latin-1 (мошибейк на
    кириллице), поэтому декодируем сами: BOM → <?xml encoding=...?> → UTF-8.
    Объявление вырезаем, иначе document_fromstring(str) падает на encoding-decl."""
    if data.startswith(b"\xef\xbb\xbf"):
        return _DECL.sub(b"", data[3:], count=1).decode("utf-8", errors="replace")
    m = re.search(rb'<\?xml[^>]*encoding=["\']([A-Za-z0-9_\-]+)', data[:512], re.I)
    if m:
        enc = m.group(1).decode("ascii", errors="replace")
        try:
            return _DECL.sub(b"", data, count=1).decode(enc, errors="replace")
        except LookupError:
            pass
    return data.decode("utf-8", errors="replace")


def xml_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True,
                           load_dtd=False, huge_tree=False)


def html_parser() -> lxml.html.HTMLParser:
    return lxml.html.HTMLParser(no_network=True, huge_tree=False)


def parse_xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, parser=xml_parser())


def parse_html(data: bytes) -> lxml.html.HtmlElement:
    return lxml.html.document_fromstring(decode_html(data), parser=html_parser())
