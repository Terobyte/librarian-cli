from __future__ import annotations

from lxml import etree


def xml_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True,
                           load_dtd=False, huge_tree=False)


def html_parser() -> etree.HTMLParser:
    return etree.HTMLParser(no_network=True, huge_tree=False)


def parse_xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, parser=xml_parser())
