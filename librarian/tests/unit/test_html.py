# tests/unit/test_html.py
import pytest

from librarian.config import load_config
from librarian.errors import BrokenFileError
from librarian.extractors.html import HtmlExtractor, _walk
from librarian.ir import BlockKind
from librarian.xmlsafe import parse_xml

_PAGE = """<!doctype html><html><head><title>Как устроен маяк — блог</title>
<meta name="author" content="Иван Хвостов"></head><body>
<nav><a href="/">Главная</a><a href="/tags">Теги</a><a href="/about">Обо мне</a></nav>
<article>
<h1>Как устроен маяк</h1>
<p>Маяк стоит на скале уже двести лет, и свет его виден за тридцать миль.
Смотритель поднимается по винтовой лестнице дважды в сутки, проверяя линзы
и часовой механизм, который вращает световую камеру.</p>
<h2>Линза Френеля</h2>
<p>Линза собрана из концентрических колец, каждое из которых преломляет свет
к общему фокусу. Такая конструкция легче цельной линзы в десятки раз
и пропускает больше света, чем любое зеркало той эпохи.</p>
<ul><li>вес — восемьсот килограммов</li><li>высота — два метра</li></ul>
<h2>Механизм</h2>
<p>Часовой механизм заводится гирей, опускающейся в шахте башни. Полного завода
хватает на шесть часов, поэтому ночью смотритель спит урывками.</p>
<blockquote><p>Свет должен гореть, пока жив хоть один корабль в море.</p></blockquote>
<table><tr><th>Год</th><th>Событие</th></tr><tr><td>1826</td><td>постройка</td></tr></table>
</article>
<footer>© 1826—2026 Маяк</footer></body></html>"""


def test_article_extracted(tmp_path):
    p = tmp_path / "z.html"
    p.write_text(_PAGE, encoding="utf-8")
    raw = HtmlExtractor().extract(p, load_config(None))
    kinds = [b.kind for b in raw.blocks]
    assert kinds == [BlockKind.HEADING, BlockKind.PARA, BlockKind.HEADING,
                     BlockKind.PARA, BlockKind.LIST_ITEM, BlockKind.LIST_ITEM,
                     BlockKind.HEADING, BlockKind.PARA, BlockKind.QUOTE,
                     BlockKind.TABLE]
    heads = [b for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[0].level == 1 and heads[1].level == 2       # rend="h1"/"h2"
    assert "Главная" not in " ".join(b.text for b in raw.blocks)   # nav отрезан
    assert raw.title == "Как устроен маяк" and raw.author == "Иван Хвостов"
    assert "двести лет" in raw.ref_text                      # plain-text эталон §11.1
    table = raw.blocks[-1]
    assert table.text == "Год\tСобытие\n1826\tпостройка"


def test_unknown_tag_counted():
    # §6.6: неизвестный тег — текст в PARA, счётчик в unknown_tags, не молча
    # NB: bytes-literal не может содержать кириллицу (SyntaxError в Py3),
    # поэтому собираем UTF-8 из str — байты идентичны задуманному b'...'.
    root = parse_xml(('<main><graphic src="x"/><figure>подпись к рисунку</figure>'
                      "<p>обычный абзац</p></main>").encode("utf-8"))
    blocks, unknown = [], {}
    _walk(root, blocks, unknown)
    assert unknown == {"figure": 1, "graphic": 1}
    assert [(b.kind, b.text) for b in blocks] == [
        (BlockKind.PARA, "подпись к рисунку"), (BlockKind.PARA, "обычный абзац")]


def test_empty_content_raises(tmp_path):
    p = tmp_path / "e.html"
    # Пустой <nav> (без текста в ссылках): trafilatura на синтетике без <article>
    # честно возвращает None → BrokenFileError (§Step 4: capriz trafilatura).
    p.write_text("<!doctype html><html><body><nav><a href='/'></a></nav></body></html>",
                 encoding="utf-8")
    with pytest.raises(BrokenFileError, match="основной контент"):
        HtmlExtractor().extract(p, load_config(None))
