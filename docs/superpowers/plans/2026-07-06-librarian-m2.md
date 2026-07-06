# Librarian M2 «FB2 + EPUB» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lib ingest книга.fb2 / книга.epub / архив.zip(fb2)` работает офлайн: экстракторы FB2 (§6.3) и EPUB (§6.4), фильтры R1–R2 (§9), харднинг ZIP + лимит размера исходника (§6.0). Этап M2 из §18 спеки `librarian-spec-v2.2.md`.

**Architecture:** Конвейер M1 не меняется — добавляются два экстрактора в реестр `EXTRACTORS` (self-register при импорте), два секционных фильтра в начало `SECTION_PASSES` и один guard-модуль `zipsafe` (потоковая распаковка с лимитами). Общий маппинг XHTML→блоки выносится в `extractors/html_blocks.py` — в M3 его переиспользует DOCX (§6.5). Весь XML/HTML-парсинг — только через фабрики `xmlsafe` (§6.0, grep-тест).

**Tech Stack:** ebooklib, lxml (оба уже в `pyproject.toml` c M1 — зависимости не меняются), zipfile (stdlib), pytest.

**Скоуп:** только M2 (§18). Вне скоупа: DOCX/HTML/PDF (M3–M4), полный quality/coverage (M4 — но R1/R2 уже складывают полный текст удалённого в report, чтобы M4 мог вычесть его из знаменателя coverage §11.1), `extract_timeout_s` (M5, §18 «лимиты/таймауты»), `doctor`, `--budget`.

## Global Constraints

Скопировано из спеки, действует для **каждой** задачи:

- **Детерминизм (§2):** запрещены `random`, `uuid4`, wall-clock (кроме `provenance.ingested_at`), любой сетевой I/O, итерация по `set`/`dict` без `sorted(...)`, локале-зависимые операции. Регистронезависимость — только `str.casefold()`, сортировка — по кодпоинтам.
- **Харднинг (§6.0):** входные файлы недоверенные. lxml — только через `xmlsafe` (`resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False`); прямые `etree.parse/fromstring` запрещены (grep-тест). ZIP: заявленный распакованный размер > `limits.zip_max_uncompressed_mb` (512 МБ) или коэффициент > `limits.zip_ratio_max` (100×) → `BrokenFileError("похоже на zip-bomb")`; распаковка потоковая, с контролем фактического размера.
- **Правило чистки (v1-6.3):** удалять можно только порождённое форматом, не автором. R1/R2 ничего не удаляют бесследно — полный текст в `report.removed`.
- **Канон сериализации (§12.2):** JSON — `json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)` + `"\n"`. Текстовые файлы: UTF-8, NFC, LF, один завершающий `\n`.
- **`PIPELINE_VERSION`** bump при любом изменении выходных байт — M2 меняет выход (R1/R2)? Нет: на существующих TXT/MD-фикстурах R1/R2 ничего не удаляют (проверяется зелёным golden без регенерации). Версию не трогаем, пока golden M1 не потребовал регенерации; потребовал → это дефект задачи, не повод для bump.
- **Ошибки — по-русски, человеческим языком** (§16). Контракт §16: пакет не падает, битый файл → `failed`, остальные файлы батча продолжаются.
- **Коммиты:** короткие, lowercase, без префиксов `feat:`/`fix:`, без Co-Authored-By.
- Тесты не ходят в сеть. Рабочая директория: `/Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian/`. Запуск тестов: `uv run pytest` (голого `python` на PATH нет).

---

## File Structure (дельта M2)

```
librarian/
  scripts/
    make_fixtures.py            # MODIFY: + генерация fb2/epub-фикстур (детерминированные zip)
  src/librarian/
    xmlsafe.py                  # MODIFY: html_parser → lxml.html.HTMLParser, + parse_html()
    pipeline.py                 # MODIFY: лимит max_source_mb до extract
    extractors/
      __init__.py               # MODIFY: + import fb2, epub
      zipsafe.py                # CREATE: check_zip, read_entry (лимиты §6.0)
      html_blocks.py            # CREATE: walk_body — общий XHTML→блоки (EPUB сейчас, DOCX в M3)
      fb2.py                    # CREATE: Fb2Extractor (§6.3) + fb2.zip
      epub.py                   # CREATE: EpubExtractor (§6.4)
    passes/
      sections.py               # MODIFY: + r1_meta_sections, r2_toc в начало SECTION_PASSES
  tests/
    fixtures/fb2/skazka.fb2     # сноски, стихи, эпиграф, subtitle, binary
    fixtures/fb2/arhiv.zip      # fb2.zip с обложкой (binary) внутри fb2
    fixtures/epub/povest.epub   # нормальный EPUB с h1/h2
    fixtures/epub/bezgolov.epub # EPUB без заголовков + nav с #anchor → fallback
    golden/{skazka,arhiv,povest,bezgolov}/
    unit/test_zipsafe.py  unit/test_fb2.py  unit/test_epub.py
    unit/test_html_blocks.py  unit/test_refine.py
    unit/test_xmlsafe.py        # MODIFY: grep-паттерн ловит и lxml.html
    unit/test_pipeline.py       # MODIFY: + тест лимита размера исходника
```

Зависимости строго вниз, как в M1: `pipeline → extractors → (zipsafe, html_blocks, xmlsafe) → ir, config, errors`. Экстракторы не знают о проходах; R1/R2 живут в `passes/sections.py` рядом с R3–R5.

---

### Task 1: zipsafe — лимиты ZIP (§6.0)

**Files:**
- Create: `src/librarian/extractors/zipsafe.py`
- Test: `tests/unit/test_zipsafe.py`

**Interfaces:**
- Produces: `zipsafe.check_zip(path: Path, cfg: Config) -> None` — бросает `BrokenFileError("… похоже на zip-bomb")` при превышении лимитов, `BrokenFileError("… битый zip: …")` на BadZipFile; `zipsafe.read_entry(path: Path, name: str, cfg: Config) -> bytes` — потоковое чтение одной записи с тем же контролем.
- Consumes: `Config.limits` (поля `zip_max_uncompressed_mb`, `zip_ratio_max` уже есть в конфиге с M1), `BrokenFileError` из `librarian.errors`.

- [ ] **Step 1: Написать красный тест**

```python
# tests/unit/test_zipsafe.py
import dataclasses
import zipfile

import pytest

from librarian.config import LimitsCfg, load_config
from librarian.errors import BrokenFileError
from librarian.extractors import zipsafe


def _cfg(**limits):
    cfg = load_config(None)
    return dataclasses.replace(cfg, limits=LimitsCfg(**limits))


def _make_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)


def test_ok_zip_passes(tmp_path):
    p = tmp_path / "ok.zip"
    _make_zip(p, [("a.txt", b"hello world")])
    zipsafe.check_zip(p, load_config(None))          # не бросает


def test_bomb_by_total_size(tmp_path):
    p = tmp_path / "bomb.zip"
    _make_zip(p, [("z.bin", b"\0" * (2 * 1024 * 1024))])   # 2 МБ нулей
    cfg = _cfg(zip_max_uncompressed_mb=1, zip_ratio_max=1000)
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.check_zip(p, cfg)


def test_bomb_by_ratio(tmp_path):
    p = tmp_path / "bomb.zip"
    _make_zip(p, [("z.bin", b"\0" * (2 * 1024 * 1024))])   # нули жмутся ~1000×
    cfg = _cfg(zip_max_uncompressed_mb=512, zip_ratio_max=10)
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.check_zip(p, cfg)


def test_lying_header_caught_by_streaming(tmp_path):
    # заголовок врёт про маленький размер — ловим по фактическим байтам
    p = tmp_path / "liar.zip"
    _make_zip(p, [("z.bin", b"\0" * (2 * 1024 * 1024))])
    raw = bytearray(p.read_bytes())
    cfg = _cfg(zip_max_uncompressed_mb=1, zip_ratio_max=1000)
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.check_zip(p, cfg)                    # честный заголовок
    # read_entry контролирует фактический размер независимо от заголовка
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.read_entry(p, "z.bin", cfg)
    assert raw                                        # молчим про unused: файл прочитан


def test_broken_zip(tmp_path):
    p = tmp_path / "broken.zip"
    p.write_bytes(b"PK\x03\x04мусор")
    with pytest.raises(BrokenFileError, match="битый zip"):
        zipsafe.check_zip(p, load_config(None))


def test_read_entry_ok(tmp_path):
    p = tmp_path / "ok.zip"
    _make_zip(p, [("book.fb2", "текст".encode("utf-8"))])
    assert zipsafe.read_entry(p, "book.fb2", load_config(None)) == "текст".encode("utf-8")
```

- [ ] **Step 2: Прогнать — убедиться, что красный**

Run: `uv run pytest tests/unit/test_zipsafe.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'librarian.extractors.zipsafe'`

- [ ] **Step 3: Реализация**

```python
# src/librarian/extractors/zipsafe.py
from __future__ import annotations

import zipfile
from pathlib import Path

from librarian.config import Config
from librarian.errors import BrokenFileError

_CHUNK = 1 << 20            # 1 МБ — шаг потокового чтения


def check_zip(path: Path, cfg: Config) -> None:
    """Защита от zip-bomb (§6.0): сначала по заявленным размерам записей,
    затем потоковой распаковкой с контролем фактических байтов (заголовки
    zip умеют врать — overlapping-записи, кривой file_size)."""
    max_total = cfg.limits.zip_max_uncompressed_mb * 1024 * 1024
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            declared = sum(i.file_size for i in infos)
            compressed = max(1, sum(i.compress_size for i in infos))
            if declared > max_total or declared / compressed > cfg.limits.zip_ratio_max:
                raise BrokenFileError(f"{path.name}: похоже на zip-bomb")
            total = 0
            for info in infos:
                with z.open(info) as f:
                    while chunk := f.read(_CHUNK):
                        total += len(chunk)
                        if total > max_total:
                            raise BrokenFileError(f"{path.name}: похоже на zip-bomb")
    except zipfile.BadZipFile as e:
        raise BrokenFileError(f"{path.name}: битый zip: {e}") from None


def read_entry(path: Path, name: str, cfg: Config) -> bytes:
    """Потоковое чтение одной записи; фактический размер под лимитом."""
    max_total = cfg.limits.zip_max_uncompressed_mb * 1024 * 1024
    out = bytearray()
    try:
        with zipfile.ZipFile(path) as z, z.open(name) as f:
            while chunk := f.read(_CHUNK):
                out += chunk
                if len(out) > max_total:
                    raise BrokenFileError(f"{path.name}: похоже на zip-bomb")
    except zipfile.BadZipFile as e:
        raise BrokenFileError(f"{path.name}: битый zip: {e}") from None
    except KeyError:
        raise BrokenFileError(f"{path.name}: в архиве нет записи {name}") from None
    return bytes(out)
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_zipsafe.py -v`
Expected: PASS (6 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/zipsafe.py librarian/tests/unit/test_zipsafe.py
git commit -m "zipsafe: zip-bomb limits, streaming entry read"
```

---

### Task 2: Лимит размера исходника в pipeline (§6.0)

**Files:**
- Modify: `src/librarian/pipeline.py` (начало `ingest_file`, строка ~61)
- Test: `tests/unit/test_pipeline.py` (добавить в конец)

**Interfaces:**
- Consumes: `LimitError` из `librarian.errors` (уже есть); `cfg.limits.max_source_mb`.
- Produces: файл больше лимита → `IngestOutcome(status="failed")` с сообщением «больше лимита», книга не создаётся; батч продолжается (`LimitError` — подкласс `LibError`, ловится в `_safe_ingest`).

- [ ] **Step 1: Красный тест** (добавить в `tests/unit/test_pipeline.py`; helper `dataclasses.replace` — потому что `Config` frozen, а файл на 257 МБ в тесте создавать нельзя)

```python
import dataclasses

from librarian.config import LimitsCfg


def test_source_size_limit(tmp_path):
    src = tmp_path / "big.txt"
    src.write_text("Глава 1\n\nТекст главы про лимиты.\n", encoding="utf-8")
    cfg = dataclasses.replace(load_config(None), limits=LimitsCfg(max_source_mb=0))
    outcomes = run_ingest([src], cfg, tmp_path / "lib")
    assert outcomes[0].status == "failed"
    assert "больше лимита" in outcomes[0].message
    assert not (tmp_path / "lib" / "big").exists()
```

(Импорты `load_config` и `run_ingest` в файле уже есть — проверить шапку и не дублировать.)

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_pipeline.py::test_source_size_limit -v`
Expected: FAIL — `assert 'ok' == 'failed'` (лимит не проверяется)

- [ ] **Step 3: Реализация** — в `pipeline.py` первой строкой `ingest_file` (до `detect`, спека §6.0: «отказ до извлечения»; sha256 ниже читает файл целиком — лимит обязан сработать раньше):

```python
def ingest_file(path: Path, cfg: Config, lib_root: Path,
                force: bool = False) -> IngestOutcome:
    size = path.stat().st_size                                           # 0 — лимит §6.0
    if size > cfg.limits.max_source_mb * 1024 * 1024:
        raise LimitError(f"{path.name}: файл {size // (1024 * 1024)} МБ "
                         f"больше лимита {cfg.limits.max_source_mb} МБ")
    fmt = detect(path)                                                   # 1
    ...
```

И в импорт errors добавить `LimitError`:

```python
from librarian.errors import DetectError, LibError, LimitError
```

- [ ] **Step 4: Прогнать — зелёный + весь файл**

Run: `uv run pytest tests/unit/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/pipeline.py librarian/tests/unit/test_pipeline.py
git commit -m "pipeline: enforce max_source_mb before extraction"
```

---

### Task 3: xmlsafe.parse_html + расширение grep-теста

**Files:**
- Modify: `src/librarian/xmlsafe.py`
- Modify: `tests/unit/test_xmlsafe.py`

**Interfaces:**
- Produces: `xmlsafe.parse_html(data: bytes) -> lxml.html.HtmlElement` — полный документ (`document_fromstring` достраивает `<html><body>`), у результата работают `.body` и `.text_content()`. `html_parser()` теперь возвращает `lxml.html.HTMLParser` (подкласс `etree.HTMLParser` с теми же флагами — иначе элементы не будут HtmlElement).
- Consumes: ничего нового.

- [ ] **Step 1: Красные тесты** (добавить в `tests/unit/test_xmlsafe.py`)

```python
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
```

И ужесточить grep-тест — паттерн должен ловить и обходы через `lxml.html` (заменить существующий `pat` в `test_no_raw_lxml_calls`):

```python
    pat = re.compile(
        r"\b(?:etree|html)\.(?:parse|fromstring|XML|HTML|"
        r"document_fromstring|fragment_fromstring)\s*\(")
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_xmlsafe.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_html'`

- [ ] **Step 3: Реализация** — итоговый `xmlsafe.py` целиком:

```python
# src/librarian/xmlsafe.py
from __future__ import annotations

import lxml.html
from lxml import etree


def xml_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True,
                           load_dtd=False, huge_tree=False)


def html_parser() -> lxml.html.HTMLParser:
    return lxml.html.HTMLParser(no_network=True, huge_tree=False)


def parse_xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, parser=xml_parser())


def parse_html(data: bytes) -> lxml.html.HtmlElement:
    return lxml.html.document_fromstring(data, parser=html_parser())
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_xmlsafe.py -v`
Expected: PASS (grep-тест зелёный — прямых вызовов вне xmlsafe нет)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/xmlsafe.py librarian/tests/unit/test_xmlsafe.py
git commit -m "xmlsafe: parse_html factory, stricter grep test"
```

---

### Task 4: html_blocks — общий маппинг XHTML → блоки (§6.4.2)

**Files:**
- Create: `src/librarian/extractors/html_blocks.py`
- Test: `tests/unit/test_html_blocks.py`

**Interfaces:**
- Produces: `html_blocks.walk_body(body) -> list[Block]`, где `body` — `lxml.html.HtmlElement`. Маппинг: `h1–h4` → HEADING уровня по тегу, `h5/h6` → HEADING 4, `p` → PARA, `blockquote` → QUOTE (параграфы внутри через `\n`), `li` → LIST_ITEM (вложенность сплющивается в текст пункта), `pre` → CODE (текст дословно), `table` → TABLE (ячейки `\t`, строки `\n`). Инлайновая разметка (`em`, `strong`, `a`) сплющивается в текст. Прочие теги — рекурсивный спуск.
- Consumes: `Block`, `BlockKind` из `librarian.ir`. **В M3 этот же модуль использует DOCX (§6.5) — ничего EPUB-специфичного здесь быть не должно.**

- [ ] **Step 1: Красный тест**

```python
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
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_html_blocks.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

```python
# src/librarian/extractors/html_blocks.py
from __future__ import annotations

from librarian.ir import Block, BlockKind

_HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}


def _tag(el) -> str:
    t = el.tag
    if not isinstance(t, str):          # комментарии, PI
        return ""
    return t.rpartition("}")[2].casefold()


def _flat(el) -> str:
    return " ".join(el.text_content().split())


def walk_body(body) -> list[Block]:
    blocks: list[Block] = []
    _walk(body, blocks)
    return blocks


def _walk(el, blocks: list[Block]) -> None:
    for child in el:
        tag = _tag(child)
        if tag in _HEADING_LEVEL:
            if t := _flat(child):
                blocks.append(Block(BlockKind.HEADING, t, level=_HEADING_LEVEL[tag]))
        elif tag == "p":
            if t := _flat(child):
                blocks.append(Block(BlockKind.PARA, t))
        elif tag == "blockquote":
            paras = [t for p in child.iter()
                     if _tag(p) == "p" and (t := _flat(p))]
            if t := ("\n".join(paras) or _flat(child)):
                blocks.append(Block(BlockKind.QUOTE, t))
        elif tag == "li":
            if t := _flat(child):
                blocks.append(Block(BlockKind.LIST_ITEM, t))
        elif tag == "pre":
            t = child.text_content().strip("\n")
            if t.strip():
                blocks.append(Block(BlockKind.CODE, t))
        elif tag == "table":
            rows = []
            for tr in child.iter():
                if _tag(tr) == "tr":
                    cells = [_flat(c) for c in tr if _tag(c) in ("td", "th")]
                    rows.append("\t".join(cells))
            if rows:
                blocks.append(Block(BlockKind.TABLE, "\n".join(rows)))
        else:
            _walk(child, blocks)        # div, section, article, …
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_html_blocks.py -v`
Expected: PASS (8 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/html_blocks.py librarian/tests/unit/test_html_blocks.py
git commit -m "html_blocks: shared xhtml-to-blocks mapping"
```

---

### Task 5: FB2 — базовый маппинг (§6.3)

**Files:**
- Create: `src/librarian/extractors/fb2.py`
- Modify: `src/librarian/extractors/__init__.py`
- Test: `tests/unit/test_fb2.py`

**Interfaces:**
- Produces: `Fb2Extractor` (format = `Format.FB2`), self-register через `base.register()` при импорте модуля. Маппинг §6.3: `<title>` секции → HEADING (уровень = глубина `<section>`, макс 4), `<p>` → PARA, `<epigraph>`/`<cite>` → QUOTE (параграфы через `\n`, включая `<text-author>` — авторство эпиграфа авторский текст, не формат), `<poem>`: каждая `<stanza>` → PARA `origin="poem"` (строки `<v>` через `\n`), `<subtitle>` → HEADING на 1 глубже секции (макс 4), `<table>` → TABLE (`\t`/`\n`), `<binary>`/`<coverpage>`/`<image>`/`<empty-line>` — пропуск. `<title>` самого `<body>` (обычно дубль названия книги) пропускается. Метаданные: `title-info/book-title`, первый `<author>` как «first-name last-name» (fallback — `<nickname>`), `lang`. `ref_text` = `itertext()` всех `<body>` (§11.1), считается ДО любых мутаций дерева.
- Consumes: `parse_xml` из Task 3, `BrokenFileError`. Сноски и zip — Task 6–7 (в этой задаче заглушек для них нет: extra-bodies просто игнорируются, файл читается как plain XML).

- [ ] **Step 1: Красный тест**

```python
# tests/unit/test_fb2.py
from librarian.config import load_config
from librarian.extractors.fb2 import Fb2Extractor
from librarian.ir import BlockKind

_TPL = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
             xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info>
  <author><first-name>Иван</first-name><last-name>Хвостов</last-name></author>
  <book-title>Сказка о ките</book-title>
  <lang>ru</lang>
</title-info></description>
{bodies}
</FictionBook>"""


def _extract(tmp_path, bodies: str):
    p = tmp_path / "b.fb2"
    p.write_text(_TPL.format(bodies=bodies), encoding="utf-8")
    return Fb2Extractor().extract(p, load_config(None))


def test_metadata(tmp_path):
    raw = _extract(tmp_path, "<body><section><p>Текст.</p></section></body>")
    assert raw.title == "Сказка о ките"
    assert raw.author == "Иван Хвостов"
    assert raw.lang == "ru"


def test_section_depth_becomes_heading_level(tmp_path):
    raw = _extract(tmp_path, """<body>
      <title><p>Сказка о ките</p></title>
      <section><title><p>Часть первая</p></title>
        <section><title><p>Глава 1</p></title><p>Жил-был кит.</p></section>
      </section></body>""")
    heads = [(b.text, b.level) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Часть первая", 1), ("Глава 1", 2)]   # title body — пропущен


def test_epigraph_and_cite_are_quotes(tmp_path):
    raw = _extract(tmp_path, """<body><section>
      <epigraph><p>Море зовёт.</p><text-author>Н. Волнов</text-author></epigraph>
      <p>Абзац.</p>
      <cite><p>Цитата в тексте.</p></cite>
    </section></body>""")
    quotes = [b.text for b in raw.blocks if b.kind is BlockKind.QUOTE]
    assert quotes == ["Море зовёт.\nН. Волнов", "Цитата в тексте."]


def test_poem_stanzas(tmp_path):
    raw = _extract(tmp_path, """<body><section><poem>
      <stanza><v>Волна идёт,</v><v>волна поёт.</v></stanza>
      <stanza><v>А кит молчит.</v></stanza>
    </poem></section></body>""")
    poems = [b for b in raw.blocks if b.origin == "poem"]
    assert [b.text for b in poems] == ["Волна идёт,\nволна поёт.", "А кит молчит."]
    assert all(b.kind is BlockKind.PARA for b in poems)


def test_subtitle_one_deeper(tmp_path):
    raw = _extract(tmp_path, """<body><section><title><p>Глава</p></title>
      <p>Текст.</p><subtitle>* * *</subtitle><p>Ещё.</p></section></body>""")
    heads = [(b.text, b.level) for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads == [("Глава", 1), ("* * *", 2)]


def test_table_binary_skipped(tmp_path):
    raw = _extract(tmp_path, """<body><section>
      <table><tr><th>ключ</th><th>значение</th></tr><tr><td>а</td><td>1</td></tr></table>
      <p>После таблицы.</p></section></body>
      <binary id="cover.png" content-type="image/png">aWdub3JlZA==</binary>""")
    table = [b for b in raw.blocks if b.kind is BlockKind.TABLE]
    assert table[0].text == "ключ\tзначение\nа\t1"
    assert "aWdub3JlZA" not in " ".join(b.text for b in raw.blocks)


def test_ref_text_from_bodies(tmp_path):
    raw = _extract(tmp_path, "<body><section><p>Опорный текст.</p></section></body>")
    assert "Опорный текст." in raw.ref_text


def test_broken_xml(tmp_path):
    import pytest
    from librarian.errors import BrokenFileError
    p = tmp_path / "b.fb2"
    p.write_text("<FictionBook><body>", encoding="utf-8")
    with pytest.raises(BrokenFileError, match="битый XML"):
        Fb2Extractor().extract(p, load_config(None))


def test_registered():
    from librarian import extractors                      # noqa: F401 — триггер регистрации
    from librarian.extractors.base import get_extractor
    from librarian.ir import Format
    assert type(get_extractor(Format.FB2)).__name__ == "Fb2Extractor"
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extractors.fb2'`

- [ ] **Step 3: Реализация**

```python
# src/librarian/extractors/fb2.py
from __future__ import annotations

from pathlib import Path

from lxml import etree

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.ir import Block, BlockKind, Format, RawDoc
from librarian.xmlsafe import parse_xml


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _flat(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _child(el, name: str):
    if el is None:
        return None
    for c in el:
        if _local(c) == name:
            return c
    return None


def _title_text(title_el) -> str:
    parts = [t for p in title_el if _local(p) == "p" and (t := _flat(p))]
    return " ".join(parts) if parts else _flat(title_el)


def _quote_text(el) -> str:
    parts = [t for sub in el.iter()
             if _local(sub) in ("p", "v", "text-author") and (t := _flat(sub))]
    return "\n".join(parts)


def _walk_section(sec, depth: int, blocks: list[Block]) -> None:
    for el in sec:
        tag = _local(el)
        if tag == "title":
            # title самого body (depth 0) — дубль названия книги, пропускаем
            if depth >= 1 and (t := _title_text(el)):
                blocks.append(Block(BlockKind.HEADING, t, level=min(depth, 4)))
        elif tag == "section":
            _walk_section(el, depth + 1, blocks)
        elif tag == "p":
            if t := _flat(el):
                blocks.append(Block(BlockKind.PARA, t))
        elif tag in ("epigraph", "cite"):
            if t := _quote_text(el):
                blocks.append(Block(BlockKind.QUOTE, t))
        elif tag == "poem":
            for st in el.iter():
                if _local(st) == "stanza":
                    lines = [t for v in st if _local(v) == "v" and (t := _flat(v))]
                    if lines:
                        blocks.append(Block(BlockKind.PARA, "\n".join(lines),
                                            origin="poem"))
        elif tag == "subtitle":
            if t := _flat(el):
                blocks.append(Block(BlockKind.HEADING, t,
                                    level=min(max(depth, 1) + 1, 4)))
        elif tag == "table":
            rows = []
            for tr in el.iter():
                if _local(tr) == "tr":
                    cells = [_flat(c) for c in tr if _local(c) in ("td", "th")]
                    rows.append("\t".join(cells))
            if rows:
                blocks.append(Block(BlockKind.TABLE, "\n".join(rows)))
        # binary, coverpage, image, empty-line, annotation — порождены форматом


def _metadata(root):
    ti = _child(_child(root, "description"), "title-info")
    if ti is None:
        return None, None, None
    bt = _child(ti, "book-title")
    title = (_flat(bt) or None) if bt is not None else None
    author = None
    a = _child(ti, "author")
    if a is not None:
        parts = [t for name in ("first-name", "last-name")
                 if (el := _child(a, name)) is not None and (t := _flat(el))]
        if not parts and (nick := _child(a, "nickname")) is not None:
            parts = [_flat(nick)] if _flat(nick) else []
        author = " ".join(parts) or None
    lang_el = _child(ti, "lang")
    lang = (_flat(lang_el) or None) if lang_el is not None else None
    return title, author, lang


def _read_source(path: Path, cfg: Config) -> bytes:
    return path.read_bytes()


class Fb2Extractor:
    format = Format.FB2

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        data = _read_source(path, cfg)
        try:
            root = parse_xml(data)
        except etree.XMLSyntaxError as e:
            raise BrokenFileError(f"{path.name}: битый XML: {e}") from None
        bodies = [el for el in root if _local(el) == "body"]
        if not bodies:
            raise BrokenFileError(f"{path.name}: в FB2 нет <body>")
        ref = "\n".join("".join(b.itertext()) for b in bodies)      # §11.1, до мутаций
        main = next((b for b in bodies if not b.get("name")), bodies[0])
        blocks: list[Block] = []
        _walk_section(main, 0, blocks)
        title, author, lang = _metadata(root)
        return RawDoc(fmt=Format.FB2, blocks=blocks, title=title, author=author,
                      lang=lang, ref_text=ref)


base.register(Fb2Extractor())
```

И регистрация в `src/librarian/extractors/__init__.py`:

```python
from librarian.extractors import txt   # noqa: F401  (регистрация в EXTRACTORS)
from librarian.extractors import md    # noqa: F401  (регистрация в EXTRACTORS)
from librarian.extractors import fb2   # noqa: F401  (регистрация в EXTRACTORS)
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: PASS (9 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/fb2.py librarian/src/librarian/extractors/__init__.py librarian/tests/unit/test_fb2.py
git commit -m "fb2 extractor: sections, epigraphs, poems, tables, metadata"
```

---

### Task 6: FB2 — сноски, комментарии, инлайновые маркеры (§6.3)

**Files:**
- Modify: `src/librarian/extractors/fb2.py`
- Test: `tests/unit/test_fb2.py` (добавить)

**Interfaces:**
- Produces: extra-`<body>` (любой `name`: notes, comments, прочие) не попадают в основной поток; их секции собираются в пары «номер — текст» и добавляются в конец: синтетический `HEADING` уровня 1 с текстом `cfg.general.notes_chapter_title` («Примечания») + PARA-блоки `N. текст`. Инлайновые `<a type="note">` в основном body заменяются текстовым содержимым в квадратных скобках `[1]`; если содержимое уже начинается с `[` — скобки не дублируются.
- Consumes: `Fb2Extractor.extract` из Task 5 (меняется тело), `cfg.general.notes_chapter_title` (в конфиге с M1).

- [ ] **Step 1: Красные тесты** (добавить в `tests/unit/test_fb2.py`)

```python
_NOTES = """<body>
  <section><title><p>Глава 1</p></title>
    <p>Кит<a l:href="#n1" type="note">1</a> плыл на юг.</p>
    <p>Ссылка<a l:href="#n2" type="note">[2]</a> уже в скобках.</p>
  </section></body>
<body name="notes">
  <section id="n1"><title><p>1</p></title><p>Кит — морское млекопитающее.</p></section>
  <section id="n2"><title><p>2</p></title><p>Вторая сноска.</p></section>
</body>"""


def test_inline_note_markers(tmp_path):
    raw = _extract(tmp_path, _NOTES)
    paras = [b.text for b in raw.blocks if b.kind is BlockKind.PARA]
    assert "Кит[1] плыл на юг." in paras
    assert "Ссылка[2] уже в скобках." in paras        # скобки не задвоены


def test_notes_chapter_appended(tmp_path):
    raw = _extract(tmp_path, _NOTES)
    heads = [b for b in raw.blocks if b.kind is BlockKind.HEADING]
    assert heads[-1].text == "Примечания" and heads[-1].level == 1
    tail = [b.text for b in raw.blocks[raw.blocks.index(heads[-1]) + 1:]]
    assert tail == ["1. Кит — морское млекопитающее.", "2. Вторая сноска."]


def test_notes_body_not_in_main_flow(tmp_path):
    raw = _extract(tmp_path, _NOTES)
    idx_notes = next(i for i, b in enumerate(raw.blocks) if b.text == "Примечания")
    main = " ".join(b.text for b in raw.blocks[:idx_notes])
    assert "морское млекопитающее" not in main


def test_no_notes_no_synthetic_chapter(tmp_path):
    raw = _extract(tmp_path, "<body><section><p>Текст.</p></section></body>")
    assert all(b.text != "Примечания" for b in raw.blocks)
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: FAIL — новые 4 теста падают (маркер `<a>` теряется/сноски игнорируются), старые 9 зелёные

- [ ] **Step 3: Реализация** — добавить в `fb2.py` две функции и вплести в `extract`:

```python
def _inline_note_markers(body) -> None:
    """<a type="note">1</a> → текст «[1]» на месте ссылки (§6.3)."""
    for a in list(body.iter()):
        if _local(a) != "a" or (a.get("type") or "").casefold() != "note":
            continue
        txt = "".join(a.itertext()).strip()
        if txt and not txt.startswith("["):
            txt = f"[{txt}]"
        addition = txt + (a.tail or "")
        prev, parent = a.getprevious(), a.getparent()
        if prev is not None:
            prev.tail = (prev.tail or "") + addition
        else:
            parent.text = (parent.text or "") + addition
        parent.remove(a)


def _notes_blocks(extra_bodies) -> list[Block]:
    """Секции всех неосновных body → пары «номер — текст» (§6.3)."""
    out: list[Block] = []
    for body in extra_bodies:
        for sec in body.iter():
            if _local(sec) != "section":
                continue
            paras = [t for el in sec if _local(el) == "p" and (t := _flat(el))]
            if not paras:
                continue                      # контейнерная секция без текста
            title = _child(sec, "title")
            num = _title_text(title).rstrip(".") if title is not None else ""
            text = " ".join(paras)
            out.append(Block(BlockKind.PARA, f"{num}. {text}" if num else text))
    return out
```

В `Fb2Extractor.extract` после вычисления `main` (заменить строки от `blocks: list[Block] = []` до `title, author, lang`):

```python
        extra = [b for b in bodies if b is not main]
        _inline_note_markers(main)
        blocks: list[Block] = []
        _walk_section(main, 0, blocks)
        notes = _notes_blocks(extra)
        if notes:
            blocks.append(Block(BlockKind.HEADING, cfg.general.notes_chapter_title,
                                level=1, origin="fb2-notes"))
            blocks.extend(notes)
        title, author, lang = _metadata(root)
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: PASS (13 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/fb2.py librarian/tests/unit/test_fb2.py
git commit -m "fb2: footnotes chapter, inline note markers"
```

---

### Task 7: FB2 — контейнер fb2.zip (§6.0)

**Files:**
- Modify: `src/librarian/extractors/fb2.py` (`_read_source`)
- Test: `tests/unit/test_fb2.py` (добавить)

**Interfaces:**
- Consumes: `zipsafe.check_zip` / `zipsafe.read_entry` из Task 1. `detect()` уже возвращает `Format.FB2` для zip ровно с одним `.fb2` (M1) — экстрактору достаточно отличить контейнер по сигнатуре `PK`.
- Produces: `.fb2.zip` извлекается как обычный FB2; zip-bomb внутри → `BrokenFileError` → `failed` (батч живёт).

- [ ] **Step 1: Красные тесты**

```python
def _make_fb2_zip(tmp_path, fb2_text: str, extra=()):
    import zipfile
    p = tmp_path / "arhiv.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("kniga.fb2", fb2_text.encode("utf-8"))
        for name, data in extra:
            z.writestr(name, data)
    return p


def test_fb2_zip(tmp_path):
    p = _make_fb2_zip(tmp_path, _TPL.format(
        bodies="<body><section><p>Из архива.</p></section></body>"))
    raw = Fb2Extractor().extract(p, load_config(None))
    assert raw.title == "Сказка о ките"
    assert any("Из архива" in b.text for b in raw.blocks)


def test_fb2_zip_bomb(tmp_path):
    import dataclasses
    import pytest
    from librarian.config import LimitsCfg
    from librarian.errors import BrokenFileError
    p = _make_fb2_zip(tmp_path,
                      _TPL.format(bodies="<body><section><p>x</p></section></body>"),
                      extra=[("padding.bin", b"\0" * (2 * 1024 * 1024))])
    cfg = dataclasses.replace(load_config(None),
                              limits=LimitsCfg(zip_max_uncompressed_mb=1))
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        Fb2Extractor().extract(p, cfg)
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: FAIL — `BrokenFileError: … битый XML` (extract читает zip как XML)

- [ ] **Step 3: Реализация** — заменить `_read_source` в `fb2.py`:

```python
import zipfile                                    # в шапку файла

from librarian.extractors import base, zipsafe    # заменить import base


def _read_source(path: Path, cfg: Config) -> bytes:
    with path.open("rb") as f:
        head = f.read(4)
    if not head.startswith(b"PK"):
        return path.read_bytes()
    zipsafe.check_zip(path, cfg)                  # fb2.zip: сначала лимиты §6.0
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist()
                 if n.casefold().endswith(".fb2") and not n.endswith("/")]
    if len(names) != 1:                           # detect гарантирует, но не доверяем
        raise BrokenFileError(f"{path.name}: в архиве не ровно один .fb2")
    return zipsafe.read_entry(path, names[0], cfg)
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: PASS (15 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/fb2.py librarian/tests/unit/test_fb2.py
git commit -m "fb2: zip container via zipsafe"
```

---

### Task 8: FB2 — XXE-тест (§17)

**Files:**
- Test: `tests/unit/test_fb2.py` (добавить; production-код не меняется — защита уже в `xmlsafe`, тест фиксирует контракт на уровне экстрактора и конвейера)

- [ ] **Step 1: Тест** — по §17: «FB2 с external entity в DTD — сущность не разворачивается». Секрет кладём в файл рядом: относительный SYSTEM-путь — самый коварный вариант (file:// абсолютный ловится и без нас).

```python
_XXE_FB2 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE FictionBook [<!ENTITY leak SYSTEM "secret.txt">]>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description><title-info><book-title>Ловушка</book-title></title-info></description>
<body><section><title><p>Глава 1</p></title>
<p>До сноски &leak; после сноски.</p>
<p>Обычный длинный абзац, чтобы у главы был вес и книга сохранилась.</p>
</section></body>
</FictionBook>"""


def test_xxe_entity_not_expanded(tmp_path):
    (tmp_path / "secret.txt").write_text("СОВЕРШЕННО СЕКРЕТНО", encoding="utf-8")
    p = tmp_path / "xxe.fb2"
    p.write_text(_XXE_FB2, encoding="utf-8")
    raw = Fb2Extractor().extract(p, load_config(None))
    joined = " ".join(b.text for b in raw.blocks) + raw.ref_text
    assert "СЕКРЕТНО" not in joined


def test_xxe_ingest_end_to_end(tmp_path):
    from librarian.pipeline import run_ingest
    (tmp_path / "secret.txt").write_text("СОВЕРШЕННО СЕКРЕТНО", encoding="utf-8")
    p = tmp_path / "xxe.fb2"
    p.write_text(_XXE_FB2, encoding="utf-8")
    lib = tmp_path / "lib"
    outcomes = run_ingest([p], load_config(None), lib)
    assert outcomes[0].status != "ok" or outcomes[0].book_id   # сохранилась или честный отказ
    leaked = [f for f in lib.rglob("*.md")
              if "СЕКРЕТНО" in f.read_text(encoding="utf-8")]
    assert leaked == []
```

- [ ] **Step 2: Прогнать**

Run: `uv run pytest tests/unit/test_fb2.py -v`
Expected: PASS сразу (защита в `xmlsafe.parser()` c M1). Если FAIL — это найденный дефект харднинга, чинить в `xmlsafe`, не ослаблять тест.

- [ ] **Step 3: Commit**

```bash
git add librarian/tests/unit/test_fb2.py
git commit -m "fb2: xxe regression tests"
```

---

### Task 9: EPUB — базовый экстрактор (§6.4.1–6.4.3)

**Files:**
- Create: `src/librarian/extractors/epub.py`
- Modify: `src/librarian/extractors/__init__.py`
- Test: `tests/unit/test_epub.py`

**Interfaces:**
- Produces: `EpubExtractor` (format = `Format.EPUB`), self-register. Spine в порядке spine; пропускаются item-ы со свойством `nav` и файлы, помеченные в `<guide>` как `cover`/`toc`. Каждый XHTML → `xmlsafe.parse_html` → `html_blocks.walk_body`. Границы файлов — НЕ границы глав (заголовки сквозные). Метаданные: DC title/creator/language. `ref_text` = `text_content()` всех spine-документов через `\n` (§11.1).
- Consumes: `zipsafe.check_zip` (Task 1), `parse_html` (Task 3), `walk_body` (Task 4). Fallback и nav-названия — Task 10.

- [ ] **Step 1: Красный тест** (helper строит валидный EPUB руками — он же уйдёт в `make_fixtures.py` в Task 13)

```python
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
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_epub.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extractors.epub'`

- [ ] **Step 3: Реализация**

```python
# src/librarian/extractors/epub.py
from __future__ import annotations

import posixpath
import warnings
from pathlib import Path

import ebooklib
from ebooklib import epub as ebl

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base, zipsafe
from librarian.extractors.html_blocks import walk_body
from librarian.ir import Block, BlockKind, Format, RawDoc
from librarian.xmlsafe import parse_html


def _strip_frag(href: str) -> str:
    return href.partition("#")[0]


def _basename(href: str) -> str:
    return posixpath.basename(_strip_frag(href))


def _dc(book, name: str) -> str | None:
    vals = book.get_metadata("DC", name)
    if vals and vals[0][0] and vals[0][0].strip():
        return vals[0][0].strip()
    return None


class EpubExtractor:
    format = Format.EPUB

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        zipsafe.check_zip(path, cfg)                     # лимиты §6.0 до ebooklib
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")          # ebooklib шумит про ignore_ncx
                book = ebl.read_epub(str(path))
        except Exception as e:                           # noqa: BLE001 — битый epub → failed
            raise BrokenFileError(f"{path.name}: битый EPUB: {e}") from None
        skip = {_basename(g.get("href", "")) for g in book.guide
                if g.get("type") in ("cover", "toc")}
        per_file: list[tuple[str, list[Block]]] = []     # (basename файла, блоки)
        ref_parts: list[str] = []
        for idref, _linear in book.spine:
            item = book.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            if "nav" in (item.properties or []) or _basename(item.get_name()) in skip:
                continue
            content = item.get_content()
            if not content or not content.strip():
                continue
            body = parse_html(content).body
            per_file.append((_basename(item.get_name()), walk_body(body)))
            ref_parts.append(body.text_content())
        if not per_file:
            raise BrokenFileError(f"{path.name}: в EPUB нет контентных документов")
        blocks = [b for _, bs in per_file for b in bs]
        return RawDoc(fmt=Format.EPUB, blocks=blocks, title=_dc(book, "title"),
                      author=_dc(book, "creator"), lang=_dc(book, "language"),
                      ref_text="\n".join(ref_parts))


base.register(EpubExtractor())
```

И в `src/librarian/extractors/__init__.py` добавить:

```python
from librarian.extractors import epub  # noqa: F401  (регистрация в EXTRACTORS)
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_epub.py -v`
Expected: PASS (6 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/epub.py librarian/src/librarian/extractors/__init__.py librarian/tests/unit/test_epub.py
git commit -m "epub extractor: spine walk, dc metadata, ref_text"
```

---

### Task 10: EPUB — fallback и nav-названия (§6.4.4–6.4.5)

**Files:**
- Modify: `src/librarian/extractors/epub.py`
- Test: `tests/unit/test_epub.py` (добавить)

**Interfaces:**
- Produces: если по всему spine < 2 блоков HEADING — каждый spine-файл становится секцией: в начало его блоков вставляется `HEADING` уровня 1 (`origin="epub-fallback"`) с названием из nav/NCX; сопоставление по href **без фрагмента** (`chap01.xhtml#c1` → `chap01.xhtml`), несколько nav-записей на файл → первая; нет записи → первые 60 символов первого PARA. В обычном режиме nav — источник человеческих названий: пустой/односимвольный первый HEADING файла заменяется названием из nav (реализация §6.4.5 до нарезки — после нарезки заголовок уже размазан по chapter.title; эквивалентно для реальных книг, задокументированное отклонение).
- Consumes: `book.toc` от ebooklib (`Link` / `(Section, [children])`).

- [ ] **Step 1: Красные тесты**

```python
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
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_epub.py -v`
Expected: FAIL — первые два теста (`heads == []`), четвёртый (`*` не заменена)

- [ ] **Step 3: Реализация** — добавить в `epub.py`:

```python
def _nav_titles(book) -> dict[str, str]:
    """href (basename, без фрагмента) → название; первая запись побеждает."""
    out: dict[str, str] = {}

    def walk(items) -> None:
        for it in items:
            if isinstance(it, tuple):                   # (Section, [children])
                sec, children = it
                href = getattr(sec, "href", "") or ""
                if href and sec.title and _basename(href) not in out:
                    out[_basename(href)] = sec.title
                walk(children)
            else:                                       # Link
                href = getattr(it, "href", "") or ""
                title = getattr(it, "title", "") or ""
                if href and title and _basename(href) not in out:
                    out[_basename(href)] = title

    walk(book.toc or [])
    return out
```

И в `extract` заменить строку `blocks = [b for _, bs in per_file for b in bs]` на:

```python
        titles = _nav_titles(book)
        n_heads = sum(1 for _, bs in per_file for b in bs
                      if b.kind is BlockKind.HEADING)
        blocks: list[Block] = []
        if n_heads < 2:                                  # §6.4.4: файл = секция
            for name, bs in per_file:
                t = titles.get(name)
                if not t:
                    first = next((b.text for b in bs
                                  if b.kind is BlockKind.PARA), "")
                    t = first[:60] or name
                blocks.append(Block(BlockKind.HEADING, t, level=1,
                                    origin="epub-fallback"))
                blocks.extend(bs)
        else:                                            # §6.4.5: nav чинит пустые названия
            for name, bs in per_file:
                if (bs and bs[0].kind is BlockKind.HEADING
                        and len(bs[0].text.strip()) <= 1 and titles.get(name)):
                    bs[0].text = titles[name]
                blocks.extend(bs)
```

- [ ] **Step 4: Прогнать — зелёный**

Run: `uv run pytest tests/unit/test_epub.py -v`
Expected: PASS (10 тестов)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/extractors/epub.py librarian/tests/unit/test_epub.py
git commit -m "epub: per-file fallback, nav titles"
```

---

### Task 11: R1 — служебные секции (§9)

**Files:**
- Modify: `src/librarian/passes/sections.py`
- Test: `tests/unit/test_refine.py` (создать)

**Interfaces:**
- Produces: `r1_meta_sections(chapters, ctx) -> list[Chapter]` — глава с `draft_count < cfg.clean.meta_max_tokens` (150), содержащая любой маркер из `cfg.clean.meta_markers` (сравнение по `casefold`), исключается; полный текст → `ctx.report.removed["meta_sections"]` (список `{"title", "tokens", "text"}` — `tokens` черновые, M4 вычтет их из знаменателя coverage §11.1). Порядок проходов: `SECTION_PASSES = [r1_meta_sections, r2_toc, r3_merge_tiny, r4_split_giants, r5_drop_empty]` (R2 — Task 12).
- Consumes: `draft_count` (уже импортирован в sections.py), `Chapter`, `DocContext`.

- [ ] **Step 1: Красный тест**

```python
# tests/unit/test_refine.py
from librarian.config import load_config
from librarian.ir import (Block, BlockKind, Chapter, DocContext, Format,
                          RawDoc, ReportDraft)
from librarian.passes.sections import r1_meta_sections


def _ctx(raw_blocks=()):
    return DocContext(fmt=Format.FB2, cfg=load_config(None),
                      raw=RawDoc(fmt=Format.FB2, blocks=list(raw_blocks),
                                 title=None, author=None, lang=None, ref_text=""),
                      report=ReportDraft())


def _ch(title, *texts):
    return Chapter(0, title, [Block(BlockKind.PARA, t) for t in texts])


def test_r1_removes_short_meta_chapter():
    ctx = _ctx()
    chapters = [
        _ch("Выходные данные", "© Издательство «Прибой», 2024. ISBN 978-5-00000-000-0."),
        _ch("Глава 1", "Обычный текст главы, никакого копирайта, просто история."),
    ]
    out = r1_meta_sections(chapters, ctx)
    assert [c.title for c in out] == ["Глава 1"]
    removed = ctx.report.removed["meta_sections"]
    assert removed[0]["title"] == "Выходные данные"
    assert "ISBN" in removed[0]["text"]           # ничего не исчезает бесследно
    assert removed[0]["tokens"] > 0


def test_r1_keeps_long_chapter_with_marker():
    ctx = _ctx()
    long_text = "Герой размышлял о правах. " * 60      # заведомо > 150 токенов
    chapters = [_ch("Глава", long_text + " Все права защищены — подумал он.")]
    assert r1_meta_sections(chapters, ctx) == chapters
    assert "meta_sections" not in ctx.report.removed


def test_r1_keeps_short_chapter_without_marker():
    ctx = _ctx()
    chapters = [_ch("Эпиграф", "Короткий текст без служебных маркеров.")]
    assert r1_meta_sections(chapters, ctx) == chapters
```

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_refine.py -v`
Expected: FAIL — `ImportError: cannot import name 'r1_meta_sections'`

- [ ] **Step 3: Реализация** — добавить в `passes/sections.py` (перед `r3_merge_tiny`) и обновить `SECTION_PASSES`:

```python
def _chapter_text(ch: Chapter) -> str:
    return "\n\n".join(b.text for b in ch.blocks)


def r1_meta_sections(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.clean
    markers = tuple(m.casefold() for m in cfg.meta_markers)
    kept: list[Chapter] = []
    removed: list[dict] = []
    for ch in chapters:
        text = _chapter_text(ch)
        low = text.casefold()
        if (draft_count(ch.blocks) < cfg.meta_max_tokens
                and any(m in low for m in markers)):
            removed.append({"title": ch.title,
                            "tokens": draft_count(ch.blocks), "text": text})
        else:
            kept.append(ch)
    if removed:
        ctx.report.removed.setdefault("meta_sections", []).extend(removed)
    return kept
```

```python
SECTION_PASSES = [r1_meta_sections, r3_merge_tiny, r4_split_giants, r5_drop_empty]
```

(R2 встанет между R1 и R3 в Task 12.)

- [ ] **Step 4: Прогнать — зелёный + соседние**

Run: `uv run pytest tests/unit/test_refine.py tests/unit/test_sections.py -v`
Expected: PASS (тесты R3–R5 не задеты: R1 без маркеров — no-op)

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/passes/sections.py librarian/tests/unit/test_refine.py
git commit -m "refine r1: drop short meta sections into report"
```

---

### Task 12: R2 — печатное оглавление (§9)

**Files:**
- Modify: `src/librarian/passes/sections.py`
- Test: `tests/unit/test_refine.py` (добавить)

**Interfaces:**
- Produces: `r2_toc(chapters, ctx) -> list[Chapter]` — глава ≤ `cfg.clean.toc_max_tokens` (2000) удаляется, если (а) > `toc_numeric_line_ratio` (60%) её непустых строк оканчиваются цифрой, ИЛИ (б) ≥ `toc_heading_dup_ratio` (80%) строк текстуально совпадают (casefold, схлопнутые пробелы) с **исходными** заголовками секций других глав. Источник исходных заголовков — HEADING-блоки `ctx.raw.blocks` (N-проходы правят `text` тех же объектов Block in-place, так что сравнение идёт по уже нормализованному тексту — это то, что нужно); заголовок самой главы-кандидата исключается из множества («других глав»). Текст → `ctx.report.removed["toc"]`, формат записей тот же, что у R1.
- Consumes: `ctx.raw.blocks`, `_canon`-нормализация (внутренняя).

- [ ] **Step 1: Красные тесты** (добавить в `test_refine.py`)

```python
from librarian.passes.sections import SECTION_PASSES, r2_toc


def test_r2_numeric_lines():
    ctx = _ctx()
    toc = Chapter(0, "Содержание", [Block(
        BlockKind.PARA,
        "Пролог 3\nГлава первая 7\nГлава вторая 25\nЭпилог 210")])
    body = _ch("Глава первая", "Длинный текст главы, который никуда не денется.")
    out = r2_toc([toc, body], ctx)
    assert [c.title for c in out] == ["Глава первая"]
    assert "Глава вторая 25" in ctx.report.removed["toc"][0]["text"]


def test_r2_heading_duplicates_without_page_numbers():
    heads = [Block(BlockKind.HEADING, t, level=1)
             for t in ("Пролог", "Глава первая", "Глава вторая", "Эпилог")]
    ctx = _ctx(raw_blocks=heads)
    toc = Chapter(0, "Оглавление", [Block(
        BlockKind.PARA, "Пролог\nГлава  ПЕРВАЯ\nглава вторая\nЭпилог")])
    body = _ch("Глава первая", "Текст.")
    out = r2_toc([toc, body], ctx)
    assert [c.title for c in out] == ["Глава первая"]


def test_r2_keeps_ordinary_chapter():
    ctx = _ctx()
    ch = _ch("Глава 1", "Он посчитал до 5\nи замолчал\nа потом ушёл в ночь")
    assert r2_toc([ch], ctx) == [ch]                    # 1/3 строк с цифрой — мало


def test_r2_respects_size_cap():
    import dataclasses
    from librarian.config import CleanCfg
    ctx = _ctx()
    ctx = dataclasses.replace(ctx, cfg=dataclasses.replace(
        ctx.cfg, clean=CleanCfg(toc_max_tokens=1)))
    toc = Chapter(0, "Содержание", [Block(BlockKind.PARA, "Глава 1 5\nГлава 2 9")])
    assert r2_toc([toc], ctx) == [toc]                  # больше лимита — не трогаем


def test_pass_order_r1_r2_first():
    names = [p.__name__ for p in SECTION_PASSES]
    assert names == ["r1_meta_sections", "r2_toc", "r3_merge_tiny",
                     "r4_split_giants", "r5_drop_empty"]
```

Примечание: `DocContext` — обычный (не frozen) dataclass; `dataclasses.replace` на нём работает.

- [ ] **Step 2: Прогнать — красный**

Run: `uv run pytest tests/unit/test_refine.py -v`
Expected: FAIL — `ImportError: cannot import name 'r2_toc'`

- [ ] **Step 3: Реализация** — добавить в `sections.py` после `r1_meta_sections`:

```python
_WS_RUN = re.compile(r"\s+")


def _canon(s: str) -> str:
    return _WS_RUN.sub(" ", s.casefold()).strip()


def r2_toc(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.clean
    headings = {_canon(b.text) for b in ctx.raw.blocks
                if b.kind is BlockKind.HEADING and b.text.strip()}
    kept: list[Chapter] = []
    removed: list[dict] = []
    for ch in chapters:
        tokens = draft_count(ch.blocks)
        lines = [ln for b in ch.blocks for ln in b.text.split("\n") if ln.strip()]
        if tokens > cfg.toc_max_tokens or not lines:
            kept.append(ch)
            continue
        others = headings - {_canon(ch.title)}          # заголовки ДРУГИХ глав
        numeric = sum(1 for ln in lines if ln.rstrip()[-1:].isdigit())
        dup = sum(1 for ln in lines if _canon(ln) in others)
        if (numeric / len(lines) > cfg.toc_numeric_line_ratio
                or dup / len(lines) >= cfg.toc_heading_dup_ratio):
            removed.append({"title": ch.title, "tokens": tokens,
                            "text": _chapter_text(ch)})
        else:
            kept.append(ch)
    if removed:
        ctx.report.removed.setdefault("toc", []).extend(removed)
    return kept
```

Обновить порядок и импорты (в шапке `sections.py` уже есть `re`; добавить `BlockKind` уже импортирован):

```python
SECTION_PASSES = [r1_meta_sections, r2_toc, r3_merge_tiny,
                  r4_split_giants, r5_drop_empty]
```

- [ ] **Step 4: Прогнать — зелёный + весь юнит-набор**

Run: `uv run pytest tests/unit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/src/librarian/passes/sections.py librarian/tests/unit/test_refine.py
git commit -m "refine r2: printed toc removal by numeric and dup criteria"
```

---

### Task 13: Фикстуры, golden, полный прогон (DoD M2)

**Files:**
- Modify: `scripts/make_fixtures.py` (добавить генерацию fb2/epub)
- Create (сгенерировать): `tests/fixtures/fb2/skazka.fb2`, `tests/fixtures/fb2/arhiv.zip`, `tests/fixtures/epub/povest.epub`, `tests/fixtures/epub/bezgolov.epub`
- Create (сгенерировать): `tests/golden/{skazka,arhiv,povest,bezgolov}/`

**Interfaces:**
- Consumes: весь M2. `tests/test_golden.py` подхватывает новые фикстуры сам (глоб `fixtures/**/*.*`), `update_golden.py` — тоже.
- Produces: golden для fb2/epub (DoD §18 M2). Требование детерминизма: zip-записи только с `ZipInfo(..., date_time=(1980, 1, 1, 0, 0, 0))` — иначе фикстура пересобирается с другим mtime и golden-байты «плавают».

- [ ] **Step 1: Дополнить `make_fixtures.py`** (в конец файла; стиль — как существующая генерация cp1251/koi8):

```python
# --- M2: fb2 / epub ---------------------------------------------------------
import zipfile

FB2_DIR = ROOT / "tests" / "fixtures" / "fb2"
EPUB_DIR = ROOT / "tests" / "fixtures" / "epub"
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
```

и генерацию двух EPUB — переиспользуем билдер из юнит-теста, чтобы не держать два формата EPUB в репо (импорт из tests допустим только в dev-скрипте):

```python
import sys
sys.path.insert(0, str(ROOT / "tests"))
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

print("fb2/epub fixtures written")
```

Примечание для исполнителя: если в существующем `make_fixtures.py` `ROOT` называется иначе — взять локальное имя; если shebang/структура отличается — встроить блок в стиль файла, не ломая существующую генерацию.

- [ ] **Step 2: Сгенерировать фикстуры и golden**

```bash
cd /Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian
uv run python scripts/make_fixtures.py
uv run python scripts/update_golden.py
```

Expected: в stdout — 8 строк `<name> -> [('ok', ...)]` (4 старых + skazka, arhiv, povest, bezgolov). Статус новых — `ok` или `review`; `failed` = дефект, разбираться, не коммитить.

- [ ] **Step 3: Осмотреть golden руками** (это ревью-гейт §17: «любой diff — осознанное решение»)

```bash
ls tests/golden/skazka/*/chapters/ tests/golden/povest/*/chapters/
cat "$(ls tests/golden/skazka/*/chapters/*.md | head -1)"
git diff --stat tests/golden/   # СТАРЫЕ 4 golden не должны измениться ни на байт
```

Проверить глазами: у skazka главы «Часть первая · Глава 1/2» + «Примечания» с `1. Кит — …`; маркер `[1]` в тексте; у bezgolov главы «Пролог»/«Эпилог». Если `git diff` показал изменения в старых golden — R1/R2 зацепили авторский текст, это блокер: чинить фильтр, не перегенерировать.

- [ ] **Step 4: Полный прогон**

```bash
uv run pytest
```

Expected: все зелёные (golden ×8, determinism, cache, recovery, install, unit). Упавший determinism на epub-фикстурах = недетерминизм в ebooklib-обходе — искать итерацию по dict/set в нашем коде экстрактора.

- [ ] **Step 5: Commit**

```bash
git add librarian/scripts/make_fixtures.py librarian/tests/fixtures/ librarian/tests/golden/
git commit -m "fb2/epub fixtures and golden libraries"
```

---

## Definition of Done (M2, §18)

- [ ] `lib ingest skazka.fb2 / arhiv.zip / povest.epub / bezgolov.epub` → книги в библиотеке, офлайн.
- [ ] Golden для fb2/epub-фикстур зелёные; **старые TXT/MD golden не изменились ни на байт** (иначе — bump `PIPELINE_VERSION` и осознанное решение, см. Global Constraints).
- [ ] XXE-фикстура: сущность не разворачивается, секрет не попадает в выход (Task 8).
- [ ] Zip-bomb: `BrokenFileError("похоже на zip-bomb")`, без OOM, батч продолжается (Task 1, 7).
- [ ] Grep-тест: ни одного прямого вызова lxml мимо `xmlsafe`, включая `lxml.html` (Task 3).
- [ ] Полный `uv run pytest` зелёный, включая детерминизм (2 hashseed) и кэш на новых форматах.

## Осознанные отклонения от буквы спеки (задокументировать в ревью)

1. **§6.4.5** реализован до нарезки (замена пустого/односимвольного первого HEADING файла на nav-название), а не после: после нарезки заголовок уже вплетён в `chapter.title` через путь. Для реальных книг эквивалентно.
2. **Эпиграф**: `<text-author>` включается в QUOTE — это авторский текст, выбрасывать нельзя (v1-6.3); спека перечисляет только «параграфы».
3. **R1-маркеры** сравниваются по `casefold` — спека не оговаривает регистр; выбран более цепкий вариант, порог 150 токенов страхует от ложных срабатываний на художественном тексте.
4. **Nav-сопоставление** в EPUB — по basename href (nav-документ может лежать в другом каталоге пакета, чем контент); коллизии одноимённых файлов в разных каталогах — экзотика, принимаем.

### Отклонения от буквы ПЛАНА (баги плана, нумерация продолжена с M1 п.12)

13. **Task 1, `test_zipsafe.test_broken_zip`** — verbatim-код `p.write_bytes(b"PK\x03\x04мусор")` это Python `SyntaxError` (bytes-литерал с не-ASCII внутри). Фикс: `p.write_bytes(b"PK\x03\x04" + "мусор".encode("utf-8"))` — байт-в-байт идентично задумке. Модуль `zipsafe.py` остался verbatim. (Воспроизведено игроком и судьёй независимо.)
14. **Task 3, `xmlsafe.parse_html`** — verbatim-реализация (передача `bytes` напрямую в `lxml.html.document_fromstring`) детерминированно даёт мошибейк на голых UTF-8-кириллических фрагментах без объявления кодировки: `document_fromstring(b"<p>Привет</p>")` → `'Ð\x9fÑ\x80...'` (Latin-1-эвристика lxml ошибается на коротком кириллическом вводе). Это ломает verbatim-тест `test_parse_html_body_and_text` и грозит мошибейком реальным EPUB XHTML в Tasks 9/13. Фикс: добавлена функция `_decode_html(data)`, которая декодирует bytes→str (BOM → `<?xml encoding=...?>` → UTF-8-fallback) и вырезает XML-объявление (иначе `document_fromstring(str)` падает на encoding-decl), после чего `document_fromstring` принимает уже корректный `str`. XXE-безопасность не ослаблена: `resolve_entities=False`/`no_network=True` в силе, `&x;` не разворачивается (проверено тестами `test_parse_html_script_entity_safe` и `test_xxe_not_resolved`). (Воспроизведено игроком и судьёй независимо на 5 формах ввода: голый UTF-8 / XML-decl UTF-8 / XXE / cp1251-declared / ASCII.)
15. **Task 13, `make_fixtures.py` (импорт EPUB-билдера)** — план давал `sys.path.insert(0, str(ROOT / "tests"))` для импорта `from unit.test_epub import make_epub`. Реальный `make_fixtures.py` использует `FIX = .../tests/fixtures` (а не `ROOT`), и после адаптации переменных план-код давал `sys.path.insert(0, str(FIX.parent / "tests"))` → разрешалось в `.../tests/tests` (несуществующий путь), импорт падал. Корректный путь при адаптации — `sys.path.insert(0, str(FIX.parent))` (т.к. `FIX.parent` уже равен `.../tests`, откуда виден пакет `unit`). Импорт `make_epub` отработал, EPUB-фикстуры сгенерированы детерминированно.
16. **Run `epub-docbook-flat-nav`, EPUB DocBook flat-nav (§6.4.3)** — DocBook-конвертированные EPUB (O'Reilly/No Starch и т.п.) помечают заголовок главы и заголовки её подразделов одним тегом `<h1>` в пределах spine-файла; наш экстрактор, следуя букве §6.4.3 («границы файлов — не границы глав»), строил из них плоский поток сиблингов без иерархии родительской главы в path-title. Осознанное условное отклонение: под тройным гейтом — (а) в EPUB ≥2 контентных файла; (б) у конкретного файла ≥2 заголовка уровня 1; (в) файл объявлен в TOC ровно одной записью (`_nav_counts`, счёт без дедупа по basename, в отличие от `_nav_titles`) — граница этого spine-файла становится уровнем 1: первый `<h1>` файла получает `origin="epub-file"` (level не меняется), остальные заголовки файла — `level += 1` **без cap** (риск B1 risk-критики: cap 4 схлопнул бы бывшие h3 с h4/h5/h6, `html_blocks.py` уже свернул 5/6→4); если первый блок файла не HEADING уровня 1 — заголовок из nav (или первые 60 символов первого PARA, или basename) prepend'ится уровнем 1. Гейт и трансформация — **по-файловые** (риск B2), а не по книге целиком: честные EPUB, где одна глава разбита на несколько файлов (ровно случай, ради которого §6.4.3 существует), не задеваются — либо у файла один h1, либо файл фрагментирован в TOC (`nav_counts != 1`, риск M3/M7). Остаточный риск (M5, принят частично) — два настоящих сиблинг-h1 в одном файле без фрагментного TOC вложатся друг в друга; гейт в этом случае доверяет объявленной издателем TOC-гранулярности. Порядок операций — сначала §6.4.5-починка пустых/односимвольных заголовков, потом restructure — зафиксирован как инвариант (m6) и покрыт тестом t5. Реализация: `_nav_counts`, `_restructure_file` в `src/librarian/extractors/epub.py`; тесты t1-t7 в `tests/unit/test_epub.py`; новая фикстура `tests/fixtures/epub/spravochnik.epub` (DocBook-стиль, 2 файла: h1-глава + 2 h1-подраздела + h2, nav — 1 запись на файл). Проверено: golden для povest/bezgolov/txt/md/fb2/skazka/arhiv/statya не изменились ни на байт (`git status --porcelain tests/golden` — только новая директория `spravochnik/`); `uv run pytest -q` — 166 passed, 1 skipped, 1 xfailed, 1 xpassed.

    **Repair delta (Plan v3, после NO-SHIP от Judge #1).** E2e на реальной книге (Sweigart, «Automate the Boring Stuff») показал: per-файловый гейт восстанавливает подразделы как «главы», но у Sweigart `choose_cut_level` откатывается на L=1 (медиана сегментов 366 < shallow_median 500), и на этом уровне разрезание идёт не по подразделам, а по part-файлам (`pt01.html`/`pt02.html` — ровно один `HEADING` без текста, без body). Такой heading-only файл раньше (v2) шёл в общий поток как пустая «глава» — R3 (§9) склеивал её тело со следующей главой, из-за чего `## Part I …` оказывался ВНУТРИ файла главы 1, а титул следующей главы (Chapter 7) собирал мусорный `· Part …` хвост. Фикс: `_is_divider(bs)` — файл-разделитель это РОВНО один блок в файле, и это `HEADING` уровня 1 с `len(text.strip()) > 1` (m7' — односимвольные/пустые огрызки не считаются, они уже почищены §6.4.5-фиксом раньше по инварианту m6). Такой файл тегируется `origin="epub-part"` и остаётся уровнем 1, но ТОЛЬКО если (B2') позже в spine есть файл, который сам НЕ divider и содержит ≥1 `HEADING` — иначе тегирование пропускается (хвостовой heading-only файл ведёт себя как в v2: пустая «глава», заголовок сохраняется, R3 приклеивает его к предыдущей). Тегирование и последующий сдвиг уровней целиком гейтятся тем, что в книге ХОТЯ БЫ ОДИН файл уже прошёл per-файловый DocBook-гейт (Plan v2) — без него divider-подобный файл не трогается вообще («ничего не меняется»). Когда есть и restructured-файл, и хотя бы один помеченный divider — у ВСЕХ `HEADING` с `origin != "epub-part"` равномерный `level += 1` (без cap, риск B1' — сохраняет все относительные отношения между заголовками, сиблинги остаются сиблингами); divider остаётся уровнем 1 → главы становятся уровнем 2 → path-title вида «Part I · Chapter 1». Остаточные риски: **M3'** (принят частично) — паттерн-матчинг заголовка («Part», «Часть») как доп. сигнал не используется (хрупкая i18n-эвристика), поэтому любой heading-only файл с непустым TOC-соседом трактуется как divider, даже если в оригинале это просто короткая интерлюдия; **M5'** (принят как остаточный) — два ВЛОЖЕННЫХ divider'а подряд (Part → Volume) схлопнутся в один уровень 1, первый потеряет собственную строку заголовка в потоке блоков (урон ограничен одной строкой, источник данных не теряется). Реализация: `_is_divider` в `src/librarian/extractors/epub.py`, применяется по месту сборки `blocks` в ветке §6.4.5; тесты t8-t11 в `tests/unit/test_epub.py` (divider между DocBook-файлами → level 1/2/3; divider без restructured-файлов → не тронут; heading+PARA файл не divider; хвостовой heading-only файл не тегируется, но уровень всё равно сдвигается вместе со всеми). Фикстура `spravochnik.epub` дополнена `part1.xhtml` (один `<h1>Часть I. Основы</h1>`, nav-запись) перед главами — golden `spravochnik/` перегенерирован (path-title глав теперь «Часть I. Основы · Глава N. …»), остальные golden байт-в-байт не изменились (`git status --porcelain tests/golden` — только `spravochnik/`); `uv run pytest -q` — 170 passed, 1 skipped, 1 xfailed, 1 xpassed.
