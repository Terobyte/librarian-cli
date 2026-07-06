import re
from pathlib import Path
from librarian.xmlsafe import parse_xml

_XXE = b"""<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<r>&xxe;</r>"""

def test_xxe_not_resolved():
    root = parse_xml(_XXE)
    assert (root.text or "").strip() == ""

def test_no_raw_lxml_calls():
    src = Path(__file__).parents[2] / "src" / "librarian"
    pat = re.compile(
        r"\b(?:etree|html)\.(?:parse|fromstring|XML|HTML|"
        r"document_fromstring|fragment_fromstring)\s*\(")
    bad = [p.name for p in sorted(src.rglob("*.py"))
           if p.name != "xmlsafe.py" and pat.search(p.read_text(encoding="utf-8"))]
    assert bad == []


from librarian.xmlsafe import parse_html


def test_parse_html_body_and_text():
    doc = parse_html("<p>Привет, <b>мир</b></p>".encode("utf-8"))
    assert doc.body is not None
    assert "Привет" in doc.body.text_content()


def test_parse_html_script_entity_safe():
    xxe = (b'<!DOCTYPE html [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           b"<html><body><p>&x;ok</p></body></html>")
    doc = parse_html(xxe)
    assert "root:" not in doc.body.text_content()
