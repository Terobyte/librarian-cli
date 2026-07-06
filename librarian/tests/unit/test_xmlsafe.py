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
    pat = re.compile(r"\betree\.(parse|fromstring|XML|HTML)\s*\(")
    bad = [p.name for p in sorted(src.rglob("*.py"))
           if p.name != "xmlsafe.py" and pat.search(p.read_text(encoding="utf-8"))]
    assert bad == []
