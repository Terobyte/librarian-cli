# tests/unit/test_html_blocks.py
from librarian.extractors.html_blocks import walk_body
from librarian.ir import BlockKind
from librarian.xmlsafe import parse_html


def _blocks(html: str):
    return walk_body(parse_html(html.encode("utf-8")).body)


def test_headings_levels():
    bs = _blocks("<h1>А</h1><h2>Б</h2><h4>В</h4><h5>Г</h5><h6>Д</h6>")
    assert [(b.kind, b.level) for b in bs] == [
        (BlockKind.HEADING, 1), (BlockKind.HEADING, 2),
        (BlockKind.HEADING, 4), (BlockKind.HEADING, 4), (BlockKind.HEADING, 4)]


def test_para_inline_flattened():
    bs = _blocks("<p>Привет, <em>мир</em> и <a href='x'>ссылка</a>!</p>")
    assert bs[0].kind is BlockKind.PARA
    assert bs[0].text == "Привет, мир и ссылка!"


def test_blockquote_paragraphs_joined():
    bs = _blocks("<blockquote><p>Один.</p><p>Два.</p></blockquote>")
    assert bs[0].kind is BlockKind.QUOTE
    assert bs[0].text == "Один.\nДва."


def test_list_items():
    bs = _blocks("<ul><li>первый</li><li>второй</li></ul>")
    assert [(b.kind, b.text) for b in bs] == [
        (BlockKind.LIST_ITEM, "первый"), (BlockKind.LIST_ITEM, "второй")]


def test_pre_verbatim():
    bs = _blocks("<pre>x = 1\n  y = 2</pre>")
    assert bs[0].kind is BlockKind.CODE
    assert bs[0].text == "x = 1\n  y = 2"


def test_table_tabs_and_rows():
    bs = _blocks("<table><tr><th>а</th><th>б</th></tr>"
                 "<tr><td>1</td><td>2</td></tr></table>")
    assert bs[0].kind is BlockKind.TABLE
    assert bs[0].text == "а\tб\n1\t2"


def test_recurses_into_divs():
    bs = _blocks("<div><section><p>внутри</p></section></div>")
    assert [b.text for b in bs] == ["внутри"]


def test_nested_block_not_double_counted():
    bs = _blocks("<blockquote><p>раз</p></blockquote><p>два</p>")
    assert [b.kind for b in bs] == [BlockKind.QUOTE, BlockKind.PARA]
