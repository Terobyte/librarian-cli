"""Генерация фикстур. Запуск: uv run python scripts/make_fixtures.py"""
from pathlib import Path

FIX = Path(__file__).parent.parent / "tests" / "fixtures"

ROMAN = """Роман о трудной судьбе инженера.

Том первый

Глава 1

Инженер Пётр Семёнович проснулся рано утром и долго смотрел в окно на заводскую трубу.
Мысли его были тяжелы: проект горел, сроки поджимали, а вдохновение не приходило.
Утренний туман поднимался над промышленным районом, и где-то далеко гудела проходная.

Он допил остывший чай, собрал бумаги и вышел в серый рассвет. Трамвай был полон
уставшими людьми, и каждый из них, казалось, нёс свою невидимую тяжесть, как он.

На работе его ждал обычный день чертежей, согласований и пустых совещаний, но
именно в этот день что-то тихо надломилось внутри, и он впервые подумал об ином.

Глава 2

На работе его ждала неожиданная новость: проект закрыли, отдел расформировали.
Пётр Семёнович вышел на улицу и впервые за десять лет вдохнул полной грудью.

Дома он долго сидел перед окном, перебирая в памяти годы, отданные чужому делу.
Жена молча поставила перед ним ужин и ушла на кухню, не задавая лишних вопросов.

К ночи он понял, что свободен, и эта свобода пугала его сильнее любого дедлайна.
Он достал старую карту юга и долго водил пальцем по тонким линиям прибрежных дорог.

Том второй

Глава 1

Новая жизнь началась с малого: он купил билет на поезд до южного города.
В вагоне пахло углём и свободой, колёса стучали ободряюще и ровно.

За окном проплывали поля, перелески и редкие станции с тёмными фонарями.
Он задремал и увидел маяк, стоящий на самом краю скалы над бушующим морем.

К утру поезд прибыл в приморский посёлок, где пахло солью, водорослями и йодом.
Маяк из сна оказался настоящим, и старый смотритель искал себе замену.

Глава 2

Море встретило его серым штормом, но даже шторм показался ему праздником.
Так инженер стал смотрителем маяка, и об этом не пожалел ни разу.

Дни потекли медленно и ровно, отмеченные приливами, туманами и сигналами.
Он научился чинить механизм, вести журнал и слушать тишину между двумя бурями.

Иногда ночью он поднимался на галерею и смотрел, как луч уходит во тьму воды.
Там, в этом мерцающем одиночестве, он наконец нашёл то, что давно потерял."""

PERENOSY = """Проверка склейки переносов в обычном тексте про науку и жизнь.

Здесь наука побеждает: сло-
во разорвано переносом, а кто-
то остался с дефисом, как и что-
либо ещё из списка частиц."""

STATYA = """---
title: Статья
---
# Введение

Первый абзац статьи со [ссылкой](https://example.com) внутри текста.

## Метод

Описание метода достаточно подробное, чтобы глава не была крошечной.

Список шагов:

- собрать данные
- обучить модель

## Результаты

Таблица и код иллюстрируют результат.

```python
print("hello")
```

> Цитата рецензента о значимости работы.

# Заключение

Работа завершена, выводы сделаны, планы намечены на будущее."""

(FIX / "txt").mkdir(parents=True, exist_ok=True)
(FIX / "md").mkdir(parents=True, exist_ok=True)
(FIX / "txt" / "roman_cp1251.txt").write_bytes(ROMAN.encode("cp1251"))
(FIX / "txt" / "koi8.txt").write_bytes(ROMAN.encode("koi8-r"))
(FIX / "txt" / "perenosy.txt").write_bytes(PERENOSY.encode("utf-8"))
(FIX / "md" / "statya.md").write_bytes(STATYA.encode("utf-8"))

# --- M2: fb2 / epub ---------------------------------------------------------
import zipfile

FB2_DIR = FIX / "fb2"
EPUB_DIR = FIX / "epub"
FB2_DIR.mkdir(parents=True, exist_ok=True)
EPUB_DIR.mkdir(parents=True, exist_ok=True)

_PARA = ("Кит шёл на юг, раздвигая тяжёлую воду, и берег медленно таял за "
         "кормой рыбацких лодок. ") * 12                 # ~150 токенов на абзац

SKAZKA = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
             xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info>
  <author><first-name>Иван</first-name><last-name>Хвостов</last-name></author>
  <book-title>Сказка о ките</book-title>
  <lang>ru</lang>
</title-info></description>
<body>
  <title><p>Сказка о ките</p></title>
  <section><title><p>Часть первая</p></title>
    <epigraph><p>Море зовёт всякого.</p><text-author>Н. Волнов</text-author></epigraph>
    <section><title><p>Глава 1</p></title>
      <p>Жил-был кит<a l:href="#n1" type="note">1</a>. {p}</p>
      <subtitle>* * *</subtitle>
      <p>{p}</p>
      <poem><stanza><v>Волна идёт,</v><v>волна поёт,</v></stanza>
            <stanza><v>а кит молчит и ждёт.</v></stanza></poem>
    </section>
    <section><title><p>Глава 2</p></title>
      <p>{p}</p>
      <cite><p>Так говорили старики на берегу.</p></cite>
      <p>{p}</p>
    </section>
  </section>
</body>
<body name="notes">
  <section id="n1"><title><p>1</p></title>
    <p>Кит — самое большое морское млекопитающее.</p></section>
</body>
<binary id="cover.png" content-type="image/png">aWdub3JlZA==</binary>
</FictionBook>""".format(p=_PARA.strip())

(FB2_DIR / "skazka.fb2").write_text(SKAZKA, encoding="utf-8", newline="\n")

ARHIV_FB2 = SKAZKA.replace("Сказка о ките", "Сказка из архива")


def zip_write(zf, name, data, compress=zipfile.ZIP_DEFLATED):
    zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))   # детерминизм
    zi.compress_type = compress
    zi.external_attr = 0o644 << 16
    zf.writestr(zi, data)


with zipfile.ZipFile(FB2_DIR / "arhiv.zip", "w") as z:
    zip_write(z, "kniga.fb2", ARHIV_FB2.encode("utf-8"))

# EPUB — переиспользуем билдер из юнит-теста
import sys
sys.path.insert(0, str(FIX.parent))                       # FIX.parent == .../tests
from unit.test_epub import make_epub                     # noqa: E402

_CH = ("<p>" + _PARA.strip() + "</p>") * 3

make_epub(EPUB_DIR / "povest.epub", "Повесть о шторме",
          chapters=[("ch1.xhtml", "<h1>Глава 1</h1>" + _CH +
                     "<blockquote><p>Цитата о море.</p></blockquote>"),
                    ("ch2.xhtml", "<h1>Глава 2</h1>" + _CH +
                     "<ul><li>сеть</li><li>парус</li></ul>")],
          nav_links=[("ch1.xhtml", "Глава 1"), ("ch2.xhtml", "Глава 2")],
          ident="povest")

make_epub(EPUB_DIR / "bezgolov.epub", "Безголовая книга",
          chapters=[("text1.xhtml", _CH), ("text2.xhtml", _CH)],
          nav_links=[("text1.xhtml#start", "Пролог"), ("text2.xhtml", "Эпилог")],
          ident="bezgolov")

# DocBook-стиль (§6.4.3 отклонение): в файле — заголовок главы и заголовки
# подразделов одним уровнем h1; nav — ровно одна запись на файл. Plan v3
# (repair delta): part1.xhtml — heading-only part-разделитель перед главами.
make_epub(EPUB_DIR / "spravochnik.epub", "Справочник программиста",
          chapters=[("part1.xhtml", "<h1>Часть I. Основы</h1>"),
                    ("ch1.xhtml",
                     "<h1>Глава 1. Основы работы</h1>" + _CH +
                     "<h1>1.1 Установка</h1>" + _CH +
                     "<h2>1.1.1 Требования</h2>" + _CH +
                     "<h1>1.2 Настройка</h1>" + _CH),
                    ("ch2.xhtml",
                     "<h1>Глава 2. Продвинутые приёмы</h1>" + _CH +
                     "<h1>2.1 Оптимизация</h1>" + _CH +
                     "<h2>2.1.1 Профилирование</h2>" + _CH +
                     "<h1>2.2 Отладка</h1>" + _CH)],
          nav_links=[("part1.xhtml", "Часть I. Основы"),
                     ("ch1.xhtml", "Глава 1. Основы работы"),
                     ("ch2.xhtml", "Глава 2. Продвинутые приёмы")],
          ident="spravochnik")

print("fixtures written")
print("fb2/epub fixtures written")

# --- M3: docx / html --------------------------------------------------------
from unit.test_docx import make_docx                      # noqa: E402

DOCX_DIR = FIX / "docx"
HTML_DIR = FIX / "html"
DOCX_DIR.mkdir(parents=True, exist_ok=True)
HTML_DIR.mkdir(parents=True, exist_ok=True)

_DPARA = ("Судно шло вдоль берега, и смотритель маяка отмечал его путь в "
          "журнале, пока волны считали часы вахты. ") * 10

make_docx(DOCX_DIR / "otchet.docx",
          [("Heading1", "Глава 1. Отплытие"), (None, _DPARA), (None, _DPARA),
           ("Heading2", "Наблюдение первое"), (None, _DPARA),
           ("Heading1", "Глава 2. Шторм"), (None, _DPARA), (None, _DPARA),
           ("Heading2", "Наблюдение второе"), (None, _DPARA)],
          title="Отчёт о плавании", author="Пелагея Морская",
          extra_body_xml=('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>День</w:t></w:r></w:p></w:tc>'
                          '<w:tc><w:p><w:r><w:t>Мили</w:t></w:r></w:p></w:tc></w:tr>'
                          '<w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>'
                          '<w:tc><w:p><w:r><w:t>120</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'))

make_docx(DOCX_DIR / "bezstiley.docx",
          [(None, "Глава 1"), (None, _DPARA), (None, _DPARA),
           (None, "Глава 2"), (None, _DPARA), (None, _DPARA)])

_ZAMETKA = """<!doctype html><html><head><title>Как устроен маяк — блог</title>
<meta name="author" content="Иван Хвостов"></head><body>
<nav><a href="/">Главная</a><a href="/tags">Теги</a><a href="/about">Обо мне</a></nav>
<article>
<h1>Как устроен маяк</h1>
<p>{p}</p><p>{p}</p>
<h2>Линза Френеля</h2>
<p>{p}</p><p>{p}</p>
<ul><li>вес — восемьсот килограммов</li><li>высота — два метра</li></ul>
<h2>Часовой механизм</h2>
<p>{p}</p><p>{p}</p>
<blockquote><p>Свет должен гореть, пока жив хоть один корабль в море.</p></blockquote>
</article>
<footer>© 1826—2026 Маяк</footer></body></html>""".format(
    p=("Маяк стоит на скале уже двести лет, и свет его виден за тридцать миль, "
       "а смотритель поднимается по винтовой лестнице дважды в сутки, проверяя "
       "линзы и часовой механизм, который вращает световую камеру. ") * 4)

(HTML_DIR / "zametka.html").write_text(_ZAMETKA, encoding="utf-8", newline="\n")
print("docx/html fixtures written")
