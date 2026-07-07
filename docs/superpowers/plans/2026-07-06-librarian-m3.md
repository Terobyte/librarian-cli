# Librarian M3 «DOCX + HTML» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lib ingest отчёт.docx / статья.html` работает офлайн: экстрактор DOCX через mammoth (§6.5), экстрактор HTML через trafilatura (§6.6), общий fallback-паттерн 6.1.3 для документов без заголовков. Этап M3 из §18 спеки `librarian-spec-v2.2.md`.

**Architecture:** Конвейер не меняется — добавляются два экстрактора в реестр `EXTRACTORS` (self-register при импорте, как fb2/epub в M2). DOCX: mammoth → HTML → уже существующий `html_blocks.walk_body` (ради этого он и выносился в M2). HTML: trafilatura XML-вывод → собственный маленький маппер (структура XML другая: `head rend=`, `list/item`, `row/cell`). Fallback без заголовков — новая общая функция `apply_patterns_to_blocks` в `textrules` (её же переиспользует P5.5 в M4). Плюс маленький сквозной канал `unknown_tags`: RawDoc → ReportDraft → report.json (§6.6 «не молча»).

**Tech Stack:** mammoth 1.12, trafilatura 2.1 (оба уже в `pyproject.toml` и в lock — зависимости не меняются), zipfile (stdlib), pytest.

**Скоуп:** только M3 (§18). Вне скоупа: PDF, полный quality/coverage, doctor (M4); `--budget`, `reingest`, таймауты (M5).

**Проверено пробниками до планирования (2026-07-06):**
- mammoth 1.12 переваривает минимальный рукодельный DOCX (6 записей zip: `[Content_Types].xml`, `_rels/.rels`, `word/_rels/document.xml.rels`, `word/document.xml`, `word/styles.xml`, `docProps/core.xml`); Heading1/Heading2 → `<h1>/<h2>`, таблица → `<table><tr><td><p>`; стиль `Quote` он НЕ мапит (warning «Unrecognised paragraph style») — в фикстуре цитат не будет.
- trafilatura 2.1, `output_format="xml"`: корень `<doc>`, контент в `<main>`; теги: `<head rend="h1|h2|…">`, `<p>`, `<list rend="ul"><item>`, `<quote><p>`, `<code>`, `<table><row span="2"><cell role="head">`. `extract_metadata(html)` отдаёт `.title`/`.author`. Plain-text вывод (`output_format` по умолчанию) — эталон coverage §11.1.

## Global Constraints

Скопировано из спеки, действует для **каждой** задачи:

- **Детерминизм (§2):** запрещены `random`, `uuid4`, wall-clock (кроме `provenance.ingested_at`), любой сетевой I/O, итерация по `set`/`dict` без `sorted(...)`, локале-зависимые операции. Регистронезависимость — только `str.casefold()`.
- **Харднинг (§6.0):** входные файлы недоверенные. lxml — только через `xmlsafe` (grep-тест это проверяет). DOCX — это ZIP: перед mammoth обязателен `zipsafe.check_zip` (лимиты zip-bomb). trafilatura парсит HTML своим внутренним lxml — это зависимость, grep-тест сканирует только `src/librarian`, нарушения нет; наш парсинг её XML-вывода — через `xmlsafe.parse_xml`.
- **Правило чистки (v1-6.3):** удалять можно только порождённое форматом, не автором. Неизвестные теги trafilatura не выбрасываются молча — текст в PARA, тег в `unknown_tags` (§6.6).
- **Канон сериализации (§12.2):** JSON — `json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)` + `"\n"`.
- **`PIPELINE_VERSION` не трогаем:** M3 не должен менять байты существующих golden (TXT/MD/FB2/EPUB). Ключ `unknown_tags` пишется в report.json **только непустым** (отклонение 17, снимается в M4) — именно чтобы старые golden остались байт-в-байт. Полный прогон golden без регенерации — обязательная проверка каждой задачи.
- **Ошибки — по-русски, человеческим языком** (§16); пакет не падает.
- **Коммиты:** короткие, lowercase, без префиксов и Co-Authored-By.
- Тесты не ходят в сеть. Рабочая директория: `/Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian/`. Запуск: `uv run pytest` (голого `python` на PATH нет).

---

## File Structure (дельта M3)

```
librarian/
  scripts/
    make_fixtures.py            # MODIFY: + otchet.docx, bezstiley.docx, zametka.html
  src/librarian/
    ir.py                       # MODIFY: RawDoc.unknown_tags, ReportDraft.unknown_tags
    pipeline.py                 # MODIFY: перенос raw.unknown_tags в ReportDraft
    quality.py                  # MODIFY: unknown_tags в report (только непустым)
    xmlsafe.py                  # MODIFY: _decode_html → публичный decode_html
    extractors/
      __init__.py               # MODIFY: + import docx, html
      textrules.py              # MODIFY: + apply_patterns_to_blocks (общий fallback)
      docx.py                   # CREATE: DocxExtractor (§6.5)
      html.py                   # CREATE: HtmlExtractor (§6.6)
  tests/
    fixtures/docx/otchet.docx       # стили Heading1/2, таблица, core.xml-метаданные
    fixtures/docx/bezstiley.docx    # без стилей заголовков → fallback 6.1.3
    fixtures/html/zametka.html      # сохранённая статья: nav/footer-мусор вокруг article
    golden/{otchet,bezstiley,zametka}/
    unit/test_docx.py  unit/test_html.py
    unit/test_textrules.py      # MODIFY: + тесты apply_patterns_to_blocks
    unit/test_quality.py        # MODIFY: + тест условного unknown_tags
```

Зависимости строго вниз, как раньше: `pipeline → extractors → (zipsafe, html_blocks, textrules, xmlsafe) → ir, config, errors`.

---

### Task 1: textrules — общий fallback `apply_patterns_to_blocks` (§6.1.3 ↔ §6.5)

**Files:**
- Modify: `src/librarian/extractors/textrules.py`
- Test: `tests/unit/test_textrules.py`

**Interfaces:**
- Consumes: `compile_patterns(cfg)`, `line_rank(line, patterns)` — уже в textrules с M1.
- Produces: `apply_patterns_to_blocks(blocks: list[Block], cfg: Config) -> list[Block]` — PARA-однострочники, совпавшие с паттернами, становятся HEADING; ранги сжаты в уровни 1..k; прочие блоки не тронуты. Это общая функция для DOCX (§6.5) и для PDF-прохода P5.5 в M4 (§7.2).

- [ ] **Step 1: Написать красный тест** — добавить в конец `tests/unit/test_textrules.py`:

```python
def test_apply_patterns_to_blocks_mixed():
    # DOCX/PDF-fallback (§6.5, §7.2 P5.5): PARA-однострочники через паттерны 6.1.3,
    # ранги сжимаются в плотные уровни; QUOTE и многострочные PARA не трогаются.
    from librarian.config import load_config
    from librarian.extractors.textrules import apply_patterns_to_blocks
    from librarian.ir import Block, BlockKind

    cfg = load_config(None)
    blocks = [
        Block(BlockKind.PARA, "Часть первая"),                    # rank2
        Block(BlockKind.PARA, "Обычный абзац текста, спокойный и длинный."),
        Block(BlockKind.PARA, "Глава 1"),                         # rank3
        Block(BlockKind.QUOTE, "Глава 2"),                        # не PARA — не трогаем
        Block(BlockKind.PARA, "Глава 3\nвторая строка"),          # многострочный — не трогаем
    ]
    out = apply_patterns_to_blocks(blocks, cfg)
    assert [b.kind for b in out] == [BlockKind.HEADING, BlockKind.PARA,
                                     BlockKind.HEADING, BlockKind.QUOTE,
                                     BlockKind.PARA]
    assert out[0].level == 1 and out[2].level == 2                # ранги {2,3} → уровни {1,2}
    assert out[2].origin == "pattern:rank3"


def test_apply_patterns_to_blocks_no_match():
    from librarian.config import load_config
    from librarian.extractors.textrules import apply_patterns_to_blocks
    from librarian.ir import Block, BlockKind

    blocks = [Block(BlockKind.PARA, "Просто текст без намёка на главы.")]
    out = apply_patterns_to_blocks(blocks, load_config(None))
    assert [b.kind for b in out] == [BlockKind.PARA]
```

- [ ] **Step 2: Убедиться, что тест красный**

Run: `uv run pytest tests/unit/test_textrules.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_patterns_to_blocks'`

- [ ] **Step 3: Реализация** — добавить в конец `src/librarian/extractors/textrules.py`:

```python
def apply_patterns_to_blocks(blocks: list[Block], cfg: Config) -> list[Block]:
    """§6.1.3 как общий fallback (§6.5 DOCX, §7.2 P5.5): PARA-блоки из одной
    строки прогоняются через паттерны; ранги сжимаются в уровни 1..k."""
    patterns = compile_patterns(cfg)
    ranks: dict[int, int] = {}
    for i, b in enumerate(blocks):
        if b.kind is BlockKind.PARA and "\n" not in b.text:
            r = line_rank(b.text, patterns)
            if r is not None:
                ranks[i] = r
    level_of = {r: k + 1 for k, r in enumerate(sorted(set(ranks.values())))}
    return [
        Block(BlockKind.HEADING, b.text, level=level_of[ranks[i]],
              origin=f"pattern:rank{ranks[i]}")
        if i in ranks else b
        for i, b in enumerate(blocks)
    ]
```

- [ ] **Step 4: Тесты зелёные, старые не задеты**

Run: `uv run pytest tests/unit/test_textrules.py -q` → PASS; затем `uv run pytest -q` → все зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/extractors/textrules.py tests/unit/test_textrules.py
git commit -m "textrules: apply_patterns_to_blocks shared fallback"
```

---

### Task 2: канал `unknown_tags` (§6.6 «не молча»)

**Files:**
- Modify: `src/librarian/ir.py` (RawDoc, ReportDraft)
- Modify: `src/librarian/pipeline.py` (перенос raw → report)
- Modify: `src/librarian/quality.py` (`build_report`)
- Test: `tests/unit/test_quality.py`

**Interfaces:**
- Produces: `RawDoc.unknown_tags: dict[str, int]` (заполняет экстрактор HTML); `ReportDraft.unknown_tags: dict[str, int]`; ключ `"unknown_tags"` в report.json — **только когда непуст** (отклонение 17: полная схема report.json — M4; условная эмиссия сохраняет старые golden байт-в-байт).

- [ ] **Step 1: Красный тест** — добавить в конец `tests/unit/test_quality.py`:

```python
def test_report_unknown_tags_only_when_present():
    # §6.6: неизвестные теги trafilatura не молча; до M4 ключ пишется
    # только непустым, чтобы не менять байты старых golden (отклонение 17).
    from librarian.config import load_config
    from librarian.ir import DocContext, Format, RawDoc, ReportDraft
    from librarian.quality import build_report, compute_metrics, score_and_status

    cfg = load_config(None)
    raw = RawDoc(fmt=Format.HTML, blocks=[], title=None, author=None,
                 lang=None, ref_text="")
    ctx = DocContext(Format.HTML, cfg, raw, ReportDraft())
    m = compute_metrics([], ctx)
    score, status, subs, trig = score_and_status(m, cfg)
    assert "unknown_tags" not in build_report(ctx, m, subs, trig, score, status, cfg)

    ctx.report.unknown_tags["graphic"] = 2
    rep = build_report(ctx, m, subs, trig, score, status, cfg)
    assert rep["unknown_tags"] == {"graphic": 2}
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_quality.py -q`
Expected: FAIL — `AttributeError: 'ReportDraft' object has no attribute 'unknown_tags'`

- [ ] **Step 3: Реализация.** В `src/librarian/ir.py`:

в `RawDoc` после `page_rects` добавить поле:

```python
    unknown_tags: dict[str, int] = field(default_factory=dict)   # §6.6, заполняет HTML
```

в `ReportDraft` после `removed` добавить:

```python
    unknown_tags: dict[str, int] = field(default_factory=dict)
```

В `src/librarian/pipeline.py` строка `ctx = DocContext(fmt, cfg, raw, ReportDraft())` меняется на:

```python
    ctx = DocContext(fmt, cfg, raw,
                     ReportDraft(unknown_tags=dict(raw.unknown_tags)))         # 5
```

В `src/librarian/quality.py`, `build_report`: собрать словарь в переменную `report`, перед `return` добавить:

```python
    if ctx.report.unknown_tags:
        report["unknown_tags"] = dict(sorted(ctx.report.unknown_tags.items()))
    return report
```

- [ ] **Step 4: Зелёный + все golden без регенерации**

Run: `uv run pytest -q` → все зелёные (golden M1/M2 не изменились — ключ пуст и не пишется).

- [ ] **Step 5: Commit**

```bash
git add src/librarian/ir.py src/librarian/pipeline.py src/librarian/quality.py tests/unit/test_quality.py
git commit -m "ir/report: unknown_tags channel from extractor to report"
```

---

### Task 3: DOCX-экстрактор (§6.5)

**Files:**
- Create: `src/librarian/extractors/docx.py`
- Modify: `src/librarian/extractors/__init__.py`
- Test: `tests/unit/test_docx.py`

**Interfaces:**
- Consumes: `zipsafe.check_zip(path, cfg)`, `zipsafe.read_entry(path, name, cfg) -> bytes` (бросает `BrokenFileError` и на отсутствующую запись); `html_blocks.walk_body(body) -> list[Block]`; `xmlsafe.parse_html(bytes)`, `xmlsafe.parse_xml(bytes)`; `textrules.apply_patterns_to_blocks` (Task 1).
- Produces: `DocxExtractor` (format=`Format.DOCX`), self-register через `base.register`. Тест-хелпер `make_docx(path, paragraphs, title=None, author=None, extra_body_xml="")` — модульная функция в `tests/unit/test_docx.py`, переиспользуется make_fixtures (как `make_epub` в M2).

- [ ] **Step 1: Красный тест** — создать `tests/unit/test_docx.py`:

```python
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
    p.write_bytes(b"PK\x03\x04мусор далеко не zip")
    with pytest.raises(BrokenFileError):
        DocxExtractor().extract(p, load_config(None))


def test_missing_core_xml_gives_none_meta(tmp_path):
    p = make_docx(tmp_path / "m.docx", [("Heading1", "Глава 1"), (None, _BODY)])
    raw = DocxExtractor().extract(p, load_config(None))
    assert raw.title is None and raw.author is None
```

(В `make_docx` без title/author `docProps/core.xml` всё равно пишется, но пустой — метаданных нет → `None`.)

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_docx.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extractors.docx'`

- [ ] **Step 3: Реализация** — создать `src/librarian/extractors/docx.py`:

```python
# src/librarian/extractors/docx.py
from __future__ import annotations

from pathlib import Path

import mammoth

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base, zipsafe
from librarian.extractors.html_blocks import walk_body
from librarian.extractors.textrules import apply_patterns_to_blocks
from librarian.ir import BlockKind, Format, RawDoc
from librarian.xmlsafe import parse_html, parse_xml


def _local(tag) -> str:
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _core_meta(path: Path, cfg: Config) -> tuple[str | None, str | None, str | None]:
    """docProps/core.xml → (title, creator, language); части может не быть."""
    try:
        data = zipsafe.read_entry(path, "docProps/core.xml", cfg)
        root = parse_xml(data)
    except (BrokenFileError, Exception):        # noqa: BLE001 — битая мета не валит книгу
        return None, None, None
    vals: dict[str, str | None] = {"title": None, "creator": None, "language": None}
    for el in root.iter():
        name = _local(el.tag)
        if name in vals and vals[name] is None and el.text and el.text.strip():
            vals[name] = el.text.strip()
    return vals["title"], vals["creator"], vals["language"]


class DocxExtractor:
    format = Format.DOCX

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        zipsafe.check_zip(path, cfg)                     # лимиты §6.0 до mammoth
        try:
            with path.open("rb") as f:
                html = mammoth.convert_to_html(f).value
            with path.open("rb") as f:                   # эталон coverage §11.1
                ref_text = mammoth.extract_raw_text(f).value
        except Exception as e:                           # noqa: BLE001 — битый docx → failed
            raise BrokenFileError(f"{path.name}: битый DOCX: {e}") from None
        if not html.strip():
            raise BrokenFileError(f"{path.name}: в DOCX нет текста")
        body = parse_html(html.encode("utf-8")).body
        blocks = walk_body(body)
        if not any(b.kind is BlockKind.HEADING for b in blocks):
            blocks = apply_patterns_to_blocks(blocks, cfg)   # §6.5 fallback → 6.1.3
        title, author, lang = _core_meta(path, cfg)
        return RawDoc(fmt=Format.DOCX, blocks=blocks, title=title,
                      author=author, lang=lang, ref_text=ref_text)


base.register(DocxExtractor())
```

Замечание для исполнителя: `except (BrokenFileError, Exception)` схлопни до `except Exception` — оставлено развёрнуто ради ясности намерения; линтер подскажет.

В `src/librarian/extractors/__init__.py` добавить строку:

```python
from librarian.extractors import docx  # noqa: F401  (регистрация в EXTRACTORS)
```

- [ ] **Step 4: Зелёный**

Run: `uv run pytest tests/unit/test_docx.py -q` → PASS; `uv run pytest -q` → все зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/extractors/docx.py src/librarian/extractors/__init__.py tests/unit/test_docx.py
git commit -m "docx extractor: mammoth to html_blocks, core.xml meta, pattern fallback"
```

---

### Task 4: HTML-экстрактор (§6.6)

**Files:**
- Modify: `src/librarian/xmlsafe.py` (публичный `decode_html`)
- Create: `src/librarian/extractors/html.py`
- Modify: `src/librarian/extractors/__init__.py`
- Test: `tests/unit/test_html.py`

**Interfaces:**
- Consumes: `xmlsafe.decode_html(data: bytes) -> str` (переименованный `_decode_html`; `parse_html` продолжает им пользоваться); `xmlsafe.parse_xml`; `RawDoc.unknown_tags` (Task 2).
- Produces: `HtmlExtractor` (format=`Format.HTML`); внутренний `_walk(el, blocks, unknown)` — маппер XML-вывода trafilatura 2.1, тестируется напрямую.

- [ ] **Step 1: Красный тест** — создать `tests/unit/test_html.py`:

```python
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
    root = parse_xml(b'<main><graphic src="x"/><figure>подпись к рисунку</figure>'
                     b"<p>обычный абзац</p></main>")
    blocks, unknown = [], {}
    _walk(root, blocks, unknown)
    assert unknown == {"figure": 1, "graphic": 1}
    assert [(b.kind, b.text) for b in blocks] == [
        (BlockKind.PARA, "подпись к рисунку"), (BlockKind.PARA, "обычный абзац")]


def test_empty_content_raises(tmp_path):
    p = tmp_path / "e.html"
    p.write_text("<!doctype html><html><body><nav><a href='/'>x</a></nav></body></html>",
                 encoding="utf-8")
    with pytest.raises(BrokenFileError, match="основной контент"):
        HtmlExtractor().extract(p, load_config(None))
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_html.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extractors.html'`

- [ ] **Step 3: Реализация.** В `src/librarian/xmlsafe.py` переименовать `_decode_html` → `decode_html` (и обновить единственный вызов в `parse_html`). Затем создать `src/librarian/extractors/html.py`:

```python
# src/librarian/extractors/html.py
from __future__ import annotations

from pathlib import Path

import trafilatura

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.ir import Block, BlockKind, Format, RawDoc
from librarian.xmlsafe import decode_html, parse_xml

_HEAD_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}


def _local(tag) -> str:
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _flat(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _walk(el, blocks: list[Block], unknown: dict[str, int]) -> None:
    """Маппер XML-вывода trafilatura 2.x (§6.6): head[rend], p, quote,
    list/item, code, table/row/cell; неизвестное — PARA + счётчик."""
    for child in el:
        tag = _local(child.tag)
        if not tag:                                     # комментарии, PI
            continue
        if tag == "head":
            level = _HEAD_LEVEL.get((child.get("rend") or "h2").casefold(), 2)
            if t := _flat(child):
                blocks.append(Block(BlockKind.HEADING, t, level=level,
                                    origin="traf-head"))
        elif tag == "p":
            if t := _flat(child):
                blocks.append(Block(BlockKind.PARA, t))
        elif tag == "quote":
            paras = [t for p in child.iter()
                     if _local(p.tag) == "p" and (t := _flat(p))]
            if t := ("\n".join(paras) or _flat(child)):
                blocks.append(Block(BlockKind.QUOTE, t))
        elif tag == "item":
            if t := _flat(child):
                blocks.append(Block(BlockKind.LIST_ITEM, t))
        elif tag == "code":
            t = "".join(child.itertext()).strip("\n")
            if t.strip():
                blocks.append(Block(BlockKind.CODE, t))
        elif tag == "table":
            rows = []
            for row in child.iter():
                if _local(row.tag) == "row":
                    cells = [_flat(c) for c in row if _local(c.tag) == "cell"]
                    rows.append("\t".join(cells))
            if rows:
                blocks.append(Block(BlockKind.TABLE, "\n".join(rows)))
        elif tag == "list":
            _walk(child, blocks, unknown)               # <list><item>…</list>
        else:                                           # §6.6: не молча
            unknown[tag] = unknown.get(tag, 0) + 1
            if t := _flat(child):
                blocks.append(Block(BlockKind.PARA, t, origin=f"traf-{tag}"))


class HtmlExtractor:
    format = Format.HTML

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        html = decode_html(path.read_bytes())
        xml = trafilatura.extract(html, output_format="xml",
                                  include_comments=False, include_tables=True,
                                  include_formatting=True)
        if not xml:
            raise BrokenFileError(f"{path.name}: не удалось выделить основной контент")
        root = parse_xml(xml.encode("utf-8"))
        main = next((el for el in root.iter() if _local(el.tag) == "main"), root)
        blocks: list[Block] = []
        unknown: dict[str, int] = {}
        _walk(main, blocks, unknown)
        if not blocks:
            raise BrokenFileError(f"{path.name}: не удалось выделить основной контент")
        meta = trafilatura.extract_metadata(html)
        ref_text = trafilatura.extract(html, include_comments=False,
                                       include_tables=True) or ""     # §11.1
        return RawDoc(fmt=Format.HTML, blocks=blocks,
                      title=(getattr(meta, "title", None) or None) if meta else None,
                      author=(getattr(meta, "author", None) or None) if meta else None,
                      lang=(getattr(meta, "language", None) or None) if meta else None,
                      ref_text=ref_text, unknown_tags=unknown)


base.register(HtmlExtractor())
```

В `src/librarian/extractors/__init__.py` добавить:

```python
from librarian.extractors import html  # noqa: F401  (регистрация в EXTRACTORS)
```

- [ ] **Step 4: Зелёный.** Если в `test_article_extracted` trafilatura отрежет часть article (она капризна на коротких синтетических страницах) — не подгонять маппер, а **удлинить абзацы** страницы (главный контент должен доминировать над мусором); ассерты на kinds обновить по фактическому честному выводу — но nav/footer обязаны отсутствовать.

Run: `uv run pytest tests/unit/test_html.py -q` → PASS; `uv run pytest -q` → все зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/xmlsafe.py src/librarian/extractors/html.py src/librarian/extractors/__init__.py tests/unit/test_html.py
git commit -m "html extractor: trafilatura xml mapping, unknown tags counter"
```

---

### Task 5: фикстуры, golden, DoD M3

**Files:**
- Modify: `scripts/make_fixtures.py`
- Create: `tests/fixtures/docx/otchet.docx`, `tests/fixtures/docx/bezstiley.docx`, `tests/fixtures/html/zametka.html` (генерируются скриптом)
- Create: `tests/golden/{otchet,bezstiley,zametka}/` (генерируются `scripts/update_golden.py`)

**Interfaces:**
- Consumes: `make_docx` из `tests/unit/test_docx.py` (как M2 переиспользовал `make_epub`); `_PAGE`-подобный HTML.

- [ ] **Step 1: Дописать генерацию фикстур** — в конец `scripts/make_fixtures.py`:

```python
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
```

Run: `uv run python scripts/make_fixtures.py`
Expected: три новых файла в `tests/fixtures/{docx,html}/`.

- [ ] **Step 2: Прогнать вручную и проверить глазами**

Run: `uv run python -c "
from pathlib import Path
from librarian.config import load_config
from librarian.pipeline import run_ingest
import tempfile, json
with tempfile.TemporaryDirectory() as d:
    for fx in sorted(Path('tests/fixtures').glob('docx/*')) + sorted(Path('tests/fixtures').glob('html/*')):
        o = run_ingest([fx], load_config(None), Path(d) / fx.stem)[0]
        print(fx.name, o.status, o.score, o.book_id)
        book = json.loads((Path(d) / fx.stem / o.book_id / 'book.json').read_text())
        print('  ', [c['title'] for c in book['chapters']])
"`
Expected: все три `ok` со score 1.00; у otchet главы «Глава 1. Отплытие · Наблюдение первое»-стиля (пути §8.4), у bezstiley — «Глава 1»/«Глава 2», у zametka — «Как устроен маяк · Линза Френеля» и т.п. Если структура не такая — дефект задачи 3/4, чинить там (сначала красный юнит).

- [ ] **Step 3: Golden**

Run: `uv run python scripts/update_golden.py && git status --short tests/golden`
Expected: появились ровно `tests/golden/{otchet,bezstiley,zametka}/`; **старые golden не изменились ни на байт** (git diff пуст по ним). Изменения в старых golden = дефект (нарушен Global Constraint про PIPELINE_VERSION) — откатывать и разбираться.

- [ ] **Step 4: Полный прогон**

Run: `uv run pytest -q`
Expected: PASS, включая `test_golden[otchet|bezstiley|zametka]`, детерминизм, кэш.

- [ ] **Step 5: Commit**

```bash
git add scripts/make_fixtures.py tests/fixtures/docx tests/fixtures/html tests/golden/otchet tests/golden/bezstiley tests/golden/zametka
git commit -m "docx/html fixtures and golden libraries"
```

---

## Отклонения от спеки (нумерация сквозная за M1/M2; последнее там — 16)

- **17.** `unknown_tags` пишется в report.json только непустым — чтобы M3 не менял байты golden M1/M2 и не требовал bump `PIPELINE_VERSION`. Снимается в M4 при переходе на полную схему report.json (§11.6), где ключ становится безусловным.
- **18.** Task 3, `test_docx.test_broken_zip_raises` — verbatim-код `p.write_bytes(b"PK\x03\x04мусор далеко не zip")` это Python `SyntaxError` (bytes-литерал с не-ASCII кириллицей внутри). Тот же класс бага, что M2 Task 1 (отклонение 13 там). Фикс: `p.write_bytes(b"PK\x03\x04" + "мусор далеко не zip".encode("utf-8"))` — байт-в-байт идентично задумке. Реализация `docx.py` осталась verbatim; `_core_meta` схлопнут из `except (BrokenFileError, Exception)` в `except Exception` по совету самого плана (Step 3 примечание, не отклонение). (Воспроизведено игроком и судьёй независимо.)

Новые отклонения, найденные при исполнении, дописывать сюда с номерами 18+ (если M4 уже начат — согласовать номера с его разделом).

## Self-Review (выполнено при написании плана)

1. **Покрытие §18 M3:** mammoth-путь — Task 3; trafilatura-путь — Task 4; общий html_blocks — уже создан в M2, переиспользован Task 3; fallback-паттерны — Task 1 + wiring в Task 3; golden docx/html — Task 5. ✓
2. **Placeholder-скан:** все шаги содержат конкретный код/команды. ✓
3. **Согласованность типов:** `apply_patterns_to_blocks(list[Block], Config) -> list[Block]` одинаковa в Task 1 (определение) и Task 3 (вызов); `RawDoc.unknown_tags` из Task 2 используется в Task 4; `make_docx` из Task 3 импортируется в Task 5. ✓
