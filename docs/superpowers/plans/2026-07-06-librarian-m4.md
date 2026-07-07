# Librarian M4 «PDF + качество» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lib ingest книга.pdf` работает офлайн: PDF-экстрактор (§6.7), проходы вёрстки P1–P7 (§7.2), **полный** quality-контур 11.1–11.6 (coverage/garbage/encoding/structure/dehyphen, субоценки, score, жёсткие триггеры), полная схема report.json, команда `lib doctor`. Скан честно даёт `failed` (`ScanError`), пароль — `EncryptedError`, пустой user-пароль открывается штатно. Этап M4 из §18 — самый большой.

**Architecture:** Экстрактор PDF отдаёт плоские PARA-блоки с координатами (`page/bbox/font_size/bold`) и НЕ содержит эвристик — вся вёрстка живёт в `passes/pdf_layout.py` (P1–P7, каждый проход тестируем на синтетических блоках без реального PDF). `quality.py` переписывается со стаба на полные формулы; финальный Markdown рендерится в pipeline один раз и передаётся в метрики. Смена схемы report.json меняет байты **всех** книг → bump `PIPELINE_VERSION` «2.2» → «2.3» и разовая регенерация всех golden — это осознанный, изолированный в задаче 4 шаг.

**Tech Stack:** pymupdf 1.28 (уже в `pyproject.toml`/lock), pytest. Ничего нового не ставим.

**Скоуп:** только M4 (§18). Вне скоупа: `--budget`, `reingest --all`, `extract_timeout_s`, перф-смоук, CI-матрица (всё — M5).

**Проверено пробниками до планирования (2026-07-06, pymupdf 1.28):**
- `needs_pass` для PDF с пустым user-паролем (owner задан) = **False** — открывается сразу; настоящий пароль → `needs_pass=1`, `authenticate("")==0`.
- Страницы из одной графики → `page.get_text("text") == ""` — детект скана по медиане работает.
- `get_text("dict", sort=True)`: `span = {size: float, flags: int, text: str}`, `block["bbox"]`; helv 16pt → size 16.0, flags 0.
- **Сохранение PDF недетерминировано** (два одинаковых `doc.save()` → разные байты, /ID). Следствие: PDF-фикстуры генерируются один раз и коммитятся байтами; повторный запуск `make_fixtures.py` изменит их → это осознанный diff + регенерация golden (отклонение 21).
- Кириллица в base-14 шрифтах (`helv`) не рисуется — PDF-фикстуры латинские («Volume/Chapter» — паттерны 6.1.3 их знают).

## Global Constraints

- **Детерминизм (§2):** без `random`/wall-clock/сети; итерация `set`/`dict` — только `sorted(...)`; `casefold()`; сортировка по кодпоинтам. В P2/P3/P5 гистограммы и пороги — только детерминированные (спека 0.10).
- **Правило чистки (v1-6.3):** удалять только порождённое форматом. Всё вырезанное P1/P2/P7 — в `ctx.report.removed`, ничего бесследно.
- **Порядок проходов (§7):** N1→N2→N3→P1→P2→P3→P4→P5→P6→P7, каждый — чистая функция `list[Block] → list[Block]` с атрибутом `.name`.
- **`PIPELINE_VERSION`:** bump «2.2»→«2.3» ровно один раз, в задаче 4 (полная схема report.json меняет байты всех книг); задачи 1–3 байты существующих golden менять **не должны** (PDF-проходы не трогают не-PDF форматы) — полный прогон после каждой задачи.
- **Предусловие M4 (проверить ДО Task 1):** M3 завершён целиком и закоммичен, `uv run pytest -q` зелёный. На 2026-07-06 дерево — mid-M3: `extractors/html.py`/`tests/unit/test_html.py` незакоммичены, `test_html.py::test_empty_content_raises` красный, фикстур docx/html нет, в `librarian/` лежит бесхозный `_probe.py` (удалить). Незелёный baseline — стоп: сначала добить M3, иначе чекпоинты «все зелёные» этого плана лгут.
- **Канон (§12.2), ошибки по-русски (§16), пакет не падает.**
- **Коммиты:** короткие, lowercase, без префиксов и Co-Authored-By.
- Тесты без сети. Рабочая директория: `/Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian/`. Запуск: `uv run pytest`.

---

## File Structure (дельта M4)

```
librarian/
  scripts/make_fixtures.py      # MODIFY: + 6 pdf-фикстур
  src/librarian/
    __init__.py                 # MODIFY: PIPELINE_VERSION = "2.3" (задача 4)
    ir.py                       # MODIFY: ReportDraft.pages_flagged, .multi_column_pages
    pipeline.py                 # MODIFY: рендер глав один раз, rendered → compute_metrics
    quality.py                  # REWRITE: полный 11.1–11.6
    catalog.py                  # MODIFY: + broken_dirs()
    cli.py                      # MODIFY: + команда doctor
    extractors/
      __init__.py               # MODIFY: + import pdf
      pdf.py                    # CREATE: PdfExtractor (§6.7)
    passes/
      normalize.py              # MODIFY: PDF_PASSES после N1–N3 для fmt=PDF
      pdf_layout.py             # CREATE: P1–P7 (§7.2)
  tests/
    fixtures/pdf/{voyage,kolonki2,kolonki3,pustoy_parol,zaparoleny,skan}.pdf
    golden/{voyage,kolonki2,kolonki3,pustoy_parol,zaparoleny,skan}/
    unit/test_pdf.py            # CREATE: экстрактор (PDF строится в тесте pymupdf-ом)
    unit/test_pdf_layout.py     # CREATE: P1–P7 на синтетических блоках
    unit/test_quality.py        # REWRITE: субоценки, формулы, триггеры, схема report
    unit/test_cli.py            # MODIFY: + doctor
```

Зависимости вниз: `pipeline → passes → (ir, config)`; `passes/pdf_layout` импортирует `extractors/textrules` (см. отклонение 19 — это модуль *правил*, не экстрактор).

---

### Task 1: PDF-экстрактор (§6.7)

**Files:**
- Create: `src/librarian/extractors/pdf.py`
- Modify: `src/librarian/extractors/__init__.py`
- Test: `tests/unit/test_pdf.py`

**Interfaces:**
- Consumes: `textrules.merge_lines(lines, cfg)` (склейка переносов §6.1.2 — обязанность экстрактора, §0.9); ошибки `ScanError`, `EncryptedError`, `BrokenFileError` из `librarian.errors`.
- Produces: `PdfExtractor` (format=`Format.PDF`): каждый текстовый блок словаря → `Block(PARA, page=1-based, bbox=tuple, font_size=доминирующий_округлённый, bold=≥60%, origin=f"pdf:{число_строк}")`. Число строк кодируется в `origin` — оно нужно P5 («заголовок ≤ 2 строк»), а склейка строк убирает `\n` из текста (отклонение 20). `RawDoc.pages`, `RawDoc.page_rects=[(x0,y0,x1,y1),…]`, `ref_text` = конкатенация `get_text("text")`.

- [ ] **Step 1: Красный тест** — создать `tests/unit/test_pdf.py`:

```python
# tests/unit/test_pdf.py
import pymupdf
import pytest

from librarian.config import load_config
from librarian.errors import EncryptedError, ScanError
from librarian.extractors.pdf import PdfExtractor
from librarian.ir import BlockKind

CFG = load_config(None)


def make_pdf(path, pages, encryption=None, owner_pw=None, user_pw=None):
    """pages: список страниц; страница — список (x, y, text, size, fontname)."""
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=595, height=842)
        for x, y, text, size, font in items:
            page.insert_text((x, y), text, fontsize=size, fontname=font)
    kw = {}
    if encryption is not None:
        kw = {"encryption": encryption, "owner_pw": owner_pw, "user_pw": user_pw}
    doc.save(path, **kw)
    doc.close()
    return path


def test_blocks_have_geometry_and_sizes(tmp_path):
    p = make_pdf(tmp_path / "a.pdf", [[
        (72, 100, "Chapter 1", 16, "helv"),
        (72, 200, "The ship left the harbour at dawn and the wind was fair.", 10, "helv"),
    ]])
    raw = PdfExtractor().extract(p, CFG)
    assert raw.pages == 1 and len(raw.page_rects) == 1
    assert all(b.kind is BlockKind.PARA for b in raw.blocks)     # эвристик нет — всё PARA
    sizes = sorted(b.font_size for b in raw.blocks)
    assert sizes == [10.0, 16.0]
    b0 = raw.blocks[0]
    assert b0.page == 1 and b0.bbox is not None and b0.origin.startswith("pdf:")
    assert "harbour" in raw.ref_text


def test_hyphen_merge_inside_block(tmp_path):
    # §6.7.3: строки ОДНОГО блока склеиваются по правилу переносов 6.1.2.
    # Две insert_text-строки с шагом в межстрочник MuPDF собирает в один блок;
    # прекондишн-assert проверяет геометрию фикстуры: если он упал — чинить
    # фикстуру (позиции строк), а НЕ экстрактор. Перенос через ГРАНИЦУ блоков —
    # работа P6, здесь не тестируется.
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "the har-", fontsize=10, fontname="helv")
    page.insert_text((72, 112), "bour was calm", fontsize=10, fontname="helv")
    tblocks = [b for b in page.get_text("dict", sort=True)["blocks"]
               if b.get("type") == 0]
    assert len(tblocks) == 1 and len(tblocks[0]["lines"]) == 2   # прекондишн фикстуры
    doc.save(tmp_path / "h.pdf")
    doc.close()
    raw = PdfExtractor().extract(tmp_path / "h.pdf", CFG)
    joined = " ".join(b.text for b in raw.blocks)
    assert "harbour" in joined and "har-" not in joined


def test_bold_flag(tmp_path):
    p = make_pdf(tmp_path / "b.pdf",
                 [[(72, 100, "Bold line", 10, "hebo"),
                   (72, 200, "Plain line", 10, "helv")]])
    raw = PdfExtractor().extract(p, CFG)
    by_text = {b.text: b.bold for b in raw.blocks}
    assert by_text["Bold line"] is True and by_text["Plain line"] is False


def test_scan_raises(tmp_path):
    doc = pymupdf.open()
    for _ in range(5):
        pg = doc.new_page()
        pg.draw_rect(pymupdf.Rect(50, 50, 500, 700), fill=(0.8, 0.8, 0.8))
    doc.save(tmp_path / "s.pdf")
    doc.close()
    with pytest.raises(ScanError, match="скан"):
        PdfExtractor().extract(tmp_path / "s.pdf", CFG)


def test_encrypted_raises(tmp_path):
    p = make_pdf(tmp_path / "e.pdf", [[(72, 100, "locked", 10, "helv")]],
                 encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    with pytest.raises(EncryptedError):
        PdfExtractor().extract(p, CFG)


def test_empty_user_password_opens(tmp_path):
    # §6.7.1 / 0.29: пустой user-пароль → открывается штатно
    p = make_pdf(tmp_path / "p.pdf",
                 [[(72, 100, "Chapter 1", 16, "helv"),
                   (72, 200, "Open sesame text for the reader.", 10, "helv")]],
                 encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="")
    raw = PdfExtractor().extract(p, CFG)
    assert any("sesame" in b.text for b in raw.blocks)
```

Если `test_bold_flag` упадёт — проверить фактический `span["flags"]` для `hebo` (бит 4 = bold, критерий ≥ 60% символов) и поправить только критерий чтения флага, не тест.

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_pdf.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extractors.pdf'`

- [ ] **Step 3: Реализация** — создать `src/librarian/extractors/pdf.py`:

```python
# src/librarian/extractors/pdf.py
from __future__ import annotations

from pathlib import Path
from statistics import median

import pymupdf

from librarian.config import Config
from librarian.errors import BrokenFileError, EncryptedError, ScanError
from librarian.extractors import base
from librarian.extractors.textrules import merge_lines
from librarian.ir import Block, BlockKind, Format, RawDoc


class PdfExtractor:
    format = Format.PDF

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        try:
            doc = pymupdf.open(str(path))
        except Exception as e:                           # noqa: BLE001 — битый pdf → failed
            raise BrokenFileError(f"{path.name}: битый PDF: {e}") from None
        try:
            if doc.needs_pass and not doc.authenticate(""):      # §6.7.1
                raise EncryptedError(
                    f"{path.name}: PDF зашифрован (пустой пароль не подошёл)")
            texts = [page.get_text("text") for page in doc]
            if not texts or median(len(t) for t in texts) < cfg.pdf.scan_chars_per_page:
                raise ScanError(
                    f"{path.name}: текстовый слой отсутствует — это скан, нужен OCR")
            blocks: list[Block] = []
            rects: list[tuple] = []
            for pno, page in enumerate(doc, 1):
                r = page.rect
                rects.append((r.x0, r.y0, r.x1, r.y1))
                for blk in page.get_text("dict", sort=True)["blocks"]:
                    if blk.get("type") != 0:                     # не текст — мимо
                        continue
                    b = self._make_block(blk, pno, cfg)
                    if b is not None:
                        blocks.append(b)
            meta = doc.metadata or {}
            return RawDoc(fmt=Format.PDF, blocks=blocks,
                          title=(meta.get("title") or "").strip() or None,
                          author=(meta.get("author") or "").strip() or None,
                          lang=None, ref_text="\n".join(texts),     # эталон §11.1
                          pages=doc.page_count, page_rects=rects)
        finally:
            doc.close()

    @staticmethod
    def _make_block(blk: dict, pno: int, cfg: Config) -> Block | None:
        lines: list[str] = []
        size_chars: dict[float, int] = {}
        bold_chars = total_chars = 0
        for ln in blk.get("lines", []):
            text = "".join(s["text"] for s in ln["spans"])
            if text.strip():
                lines.append(text)
            for s in ln["spans"]:
                n = len(s["text"])
                size = round(s["size"] / cfg.pdf.size_round) * cfg.pdf.size_round
                size_chars[size] = size_chars.get(size, 0) + n
                if s["flags"] & 16:                              # бит bold
                    bold_chars += n
                total_chars += n
        if not lines:
            return None
        font = (min(sorted(size_chars.items()),
                    key=lambda kv: (-kv[1], kv[0]))[0] if size_chars else None)
        return Block(BlockKind.PARA, merge_lines(lines, cfg),    # склейка §6.1.2
                     page=pno, bbox=tuple(blk["bbox"]), font_size=font,
                     bold=total_chars > 0 and bold_chars / total_chars >= 0.6,
                     origin=f"pdf:{len(lines)}")                 # строк до склейки — для P5


base.register(PdfExtractor())
```

В `src/librarian/extractors/__init__.py` добавить:

```python
from librarian.extractors import pdf   # noqa: F401  (регистрация в EXTRACTORS)
```

- [ ] **Step 4: Зелёный + старые golden не тронуты**

Run: `uv run pytest tests/unit/test_pdf.py -q` → PASS; `uv run pytest -q` → все зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/extractors/pdf.py src/librarian/extractors/__init__.py tests/unit/test_pdf.py
git commit -m "pdf extractor: geometry blocks, scan/encrypted detection"
```

---

### Task 2: проходы P1–P4 (§7.2) + поля ReportDraft

**Files:**
- Modify: `src/librarian/ir.py`
- Create: `src/librarian/passes/pdf_layout.py` (P1–P4; P5–P7 — задача 3)
- Test: `tests/unit/test_pdf_layout.py`

**Interfaces:**
- Produces: `ReportDraft.pages_flagged: list[int]`, `ReportDraft.multi_column_pages: list[int]`; проходы `p1_page_numbers`, `p2_headers_footers`, `p3_reading_order`, `p4_defect_pages` — каждый `(list[Block], DocContext) -> list[Block]` с `.name`. Отчётность: `removed["page_numbers"]: int`, `removed["headers_footers"]: [{"signature", "pages"}]`, `report.pages_flagged`, `report.multi_column_pages`, warning на дефектную страницу.
- Consumes: `ctx.raw.page_rects` (геометрия страниц), `ctx.cfg.pdf.*`.

- [ ] **Step 1: Красный тест** — создать `tests/unit/test_pdf_layout.py`:

```python
# tests/unit/test_pdf_layout.py
from librarian.config import load_config
from librarian.ir import Block, BlockKind, DocContext, Format, RawDoc, ReportDraft


def ctx_pdf(pages=1, w=595.0, h=842.0):
    cfg = load_config(None)
    raw = RawDoc(fmt=Format.PDF, blocks=[], title=None, author=None, lang=None,
                 ref_text="", pages=pages, page_rects=[(0.0, 0.0, w, h)] * pages)
    return DocContext(Format.PDF, cfg, raw, ReportDraft())


def para(text, page=1, bbox=(72, 400, 300, 420), size=10.0, bold=False, lines=1):
    return Block(BlockKind.PARA, text, page=page, bbox=bbox,
                 font_size=size, bold=bold, origin=f"pdf:{lines}")


# --- P1 ---------------------------------------------------------------------

def test_p1_removes_decorated_pagenum_in_zone():
    from librarian.passes.pdf_layout import p1_page_numbers
    ctx = ctx_pdf()
    blocks = [para("— 12 —", bbox=(280, 810, 315, 825)),          # низ, зона 10%
              para("iv", bbox=(280, 20, 315, 40)),                 # верх, римская
              para("12", bbox=(280, 400, 315, 420)),               # середина — не трогать
              para("1234567", bbox=(280, 810, 315, 825))]          # длиннее 4 — не номер
    out = p1_page_numbers(blocks, ctx)
    assert [b.text for b in out] == ["12", "1234567"]
    assert ctx.report.removed["page_numbers"] == 2


def test_p1_keeps_large_roman_chapter_number():
    # отклонение 25: крупный кегль в зоне колонтитула — вероятный номер главы,
    # P1 его не трогает (иначе заголовок погибнет до того, как P5 его увидит)
    from librarian.passes.pdf_layout import p1_page_numbers
    ctx = ctx_pdf()
    blocks = [para("IV", bbox=(280, 30, 315, 60), size=20.0)] + [
        para(f"Обычный длинный абзац основного текста номер {i}.",
             bbox=(72, 200 + 40 * i, 520, 230 + 40 * i))
        for i in range(4)]
    out = p1_page_numbers(blocks, ctx)
    assert any(b.text == "IV" for b in out)


# --- P2 ---------------------------------------------------------------------

def test_p2_frequent_running_header_removed():
    from librarian.passes.pdf_layout import p2_headers_footers
    ctx = ctx_pdf(pages=10)
    blocks = []
    for p in range(1, 11):
        blocks.append(para(f"Voyage Log · стр. {p}", page=p, bbox=(200, 20, 400, 40)))
        blocks.append(para(f"Body paragraph {p}", page=p))
    rare = para("Одинокая шапка", page=1, bbox=(200, 20, 400, 40))
    blocks.append(rare)
    out = p2_headers_footers(blocks, ctx)
    texts = [b.text for b in out]
    assert all(not t.startswith("Voyage Log") for t in texts)      # 10 стр ≥ порога
    assert "Одинокая шапка" in texts                               # 1 стр < hf_min_pages
    hf = ctx.report.removed["headers_footers"]
    assert hf[0]["signature"] == "voyage log · стр. #"
    assert hf[0]["pages"] == list(range(1, 11))


def test_p2_short_doc_protected_by_min_pages():
    from librarian.passes.pdf_layout import p2_headers_footers
    ctx = ctx_pdf(pages=3)                                         # ceil(0.3*3)=1 < 5
    blocks = [para("Шапка", page=p, bbox=(200, 20, 400, 40)) for p in (1, 2, 3)]
    assert len(p2_headers_footers(blocks, ctx)) == 3


# --- P3 ---------------------------------------------------------------------

def _two_column_page(page=1):
    # 3 блока слева (x-центр ~160), 3 справа (~440); порядок sort=True — по y
    left = [para(f"L{i}", page=page, bbox=(60, 100 + 200 * i, 260, 120 + 200 * i))
            for i in range(3)]
    right = [para(f"R{i}", page=page, bbox=(340, 100 + 200 * i, 540, 120 + 200 * i))
             for i in range(3)]
    interleaved = [b for pair in zip(left, right) for b in pair]   # L0 R0 L1 R1 …
    return interleaved


def test_p3_two_columns_reordered():
    from librarian.passes.pdf_layout import p3_reading_order
    ctx = ctx_pdf()
    out = p3_reading_order(_two_column_page(), ctx)
    assert [b.text for b in out] == ["L0", "L1", "L2", "R0", "R1", "R2"]
    assert ctx.report.multi_column_pages == []


def test_p3_three_columns_flagged_order_kept():
    from librarian.passes.pdf_layout import p3_reading_order
    ctx = ctx_pdf()
    blocks = [para(f"C{c}{i}", bbox=(40 + 180 * c, 100 + 200 * i,
                                     180 + 180 * c, 120 + 200 * i))
              for i in range(3) for c in range(3)]
    out = p3_reading_order(blocks, ctx)
    assert [b.text for b in out] == [b.text for b in blocks]       # порядок не тронут
    assert ctx.report.multi_column_pages == [1]


def test_p3_single_column_untouched():
    from librarian.passes.pdf_layout import p3_reading_order
    ctx = ctx_pdf()
    blocks = [para(f"B{i}", bbox=(72, 100 + 40 * i, 520, 130 + 40 * i))
              for i in range(4)]
    assert [b.text for b in p3_reading_order(blocks, ctx)] == ["B0", "B1", "B2", "B3"]


# --- P4 ---------------------------------------------------------------------

def test_p4_defect_page_flagged():
    from librarian.passes.pdf_layout import p4_defect_pages
    ctx = ctx_pdf(pages=2)
    good = para("Чистый текст страницы один. " * 5, page=1)
    bad = para("Гнилой" + "�" * 20 + " текст", page=2)        # ~70% мусора
    out = p4_defect_pages([good, bad], ctx)
    assert len(out) == 2                                           # ничего не удаляется
    assert ctx.report.pages_flagged == [2]
    assert "страница 2" in ctx.report.warnings[0]


def test_p4_counts_private_use_area():
    # PUA (категория Co) — типичный след битого шрифт-маппинга, считается дефектом
    from librarian.passes.pdf_layout import p4_defect_pages
    ctx = ctx_pdf()
    bad = para("Тело " + "\ue000\ue001" * 10, page=1)   # 20 из 25 симв. — PUA
    p4_defect_pages([bad], ctx)
    assert ctx.report.pages_flagged == [1]
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_pdf_layout.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.passes.pdf_layout'`

- [ ] **Step 3: Реализация.** В `src/librarian/ir.py`, в `ReportDraft` после `structure_fallback` добавить:

```python
    pages_flagged: list[int] = field(default_factory=list)          # P4
    multi_column_pages: list[int] = field(default_factory=list)     # P3 / С-11
```

Создать `src/librarian/passes/pdf_layout.py` (пока P1–P4; PDF_PASSES появится в задаче 3):

```python
# src/librarian/passes/pdf_layout.py
from __future__ import annotations

import math
import re
import unicodedata

from librarian.ir import Block, BlockKind, DocContext

_PAGENUM_FRAME = " \t\n—–-.()[]"
_ROMAN = re.compile(r"[ivxlcdm]+", re.IGNORECASE)
_DIGIT = re.compile(r"\d")
_WS = re.compile(r"\s+")


def _page_rect(ctx: DocContext, page: int) -> tuple:
    return ctx.raw.page_rects[page - 1]


def _page_h(ctx: DocContext, page: int) -> float:
    r = _page_rect(ctx, page)
    return r[3] - r[1]


def _page_w(ctx: DocContext, page: int) -> float:
    r = _page_rect(ctx, page)
    return r[2] - r[0]


def _zone(b: Block, ctx: DocContext) -> str | None:
    """'top'/'bottom', если центр bbox в зоне колонтитула (§7.2), иначе None."""
    if b.page is None or b.bbox is None:
        return None
    h = _page_h(ctx, b.page)
    cy = (b.bbox[1] + b.bbox[3]) / 2
    if cy < ctx.cfg.pdf.hf_zone * h:
        return "top"
    if cy > (1 - ctx.cfg.pdf.hf_zone) * h:
        return "bottom"
    return None


def _body_size(blocks: list[Block]) -> float | None:
    """Размер тела B (§7.2 P5.1): максимум символов, при равенстве — меньший.
    Нужен уже P1 (guard крупного кегля) и позже P5/P7."""
    hist: dict[float, int] = {}
    for b in blocks:
        if b.kind is BlockKind.PARA and b.font_size is not None:
            hist[b.font_size] = hist.get(b.font_size, 0) + len(b.text)
    if not hist:
        return None
    return min(sorted(hist.items()), key=lambda kv: (-kv[1], kv[0]))[0]


def p1_page_numbers(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    B = _body_size(blocks)
    out: list[Block] = []
    removed = 0
    for b in blocks:
        core = b.text.strip(_PAGENUM_FRAME)
        big = (B is not None and b.font_size is not None            # отклонение 25:
               and b.font_size >= cfg.heading_size_ratio * B)       # крупный кегль — не номер
        if (b.kind is BlockKind.PARA and not big and _zone(b, ctx) is not None
                and core and len(core) <= cfg.pagenum_max_chars
                and (core.isdigit() or _ROMAN.fullmatch(core))):
            removed += 1
            continue
        out.append(b)
    if removed:
        ctx.report.removed["page_numbers"] = (
            ctx.report.removed.get("page_numbers", 0) + removed)
    return out
p1_page_numbers.name = "P1 page numbers"


def _signature(text: str) -> str:
    return _WS.sub(" ", _DIGIT.sub("#", text)).strip().casefold()


def p2_headers_footers(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    pages = ctx.raw.pages or 0
    threshold = max(cfg.hf_min_pages, math.ceil(cfg.hf_page_ratio * pages))
    keys: dict[int, tuple[str, str]] = {}
    sig_pages: dict[tuple[str, str], set[int]] = {}
    for i, b in enumerate(blocks):
        z = _zone(b, ctx)
        if z is not None and b.page is not None:
            key = (z, _signature(b.text))
            keys[i] = key
            sig_pages.setdefault(key, set()).add(b.page)
    doomed = {k for k, ps in sig_pages.items() if len(ps) >= threshold}
    if doomed:
        ctx.report.removed.setdefault("headers_footers", []).extend(
            {"signature": sig, "pages": sorted(sig_pages[(z, sig)])}
            for z, sig in sorted(doomed))
    return [b for i, b in enumerate(blocks) if keys.get(i) not in doomed]
p2_headers_footers.name = "P2 headers/footers"


def _yx(b: Block) -> tuple:
    return (b.bbox[1], b.bbox[0])


def _split_pages(blocks: list[Block]) -> list[tuple[int | None, list[Block]]]:
    groups: list[tuple[int | None, list[Block]]] = []
    for b in blocks:
        if not groups or groups[-1][0] != b.page:
            groups.append((b.page, []))
        groups[-1][1].append(b)
    return groups


def p3_reading_order(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    out: list[Block] = []
    for page, group in _split_pages(blocks):
        if page is None:
            out.extend(group)
            continue
        flags = [_zone(b, ctx) is None and b.bbox is not None for b in group]
        body = [b for b, f in zip(group, flags) if f]
        if len(body) >= 2:
            w = _page_w(ctx, page)
            xs = sorted((b.bbox[0] + b.bbox[2]) / 2 for b in body)
            cuts = [k for k in range(len(xs) - 1)
                    if xs[k + 1] - xs[k] >= cfg.column_gap_ratio * w
                    and (k + 1) >= cfg.column_min_share * len(body)
                    and (len(body) - k - 1) >= cfg.column_min_share * len(body)]
            if len(cuts) == 1:                                   # §7.2 P3.2
                split_x = (xs[cuts[0]] + xs[cuts[0] + 1]) / 2
                left = sorted((b for b in body
                               if (b.bbox[0] + b.bbox[2]) / 2 < split_x), key=_yx)
                right = sorted((b for b in body
                                if (b.bbox[0] + b.bbox[2]) / 2 >= split_x), key=_yx)
                it = iter(left + right)
                group = [next(it) if f else b for b, f in zip(group, flags)]
            elif len(cuts) >= 2:                                 # §7.2 P3.3 / С-11
                ctx.report.multi_column_pages.append(page)
        out.extend(group)
    return out
p3_reading_order.name = "P3 reading order"


def p4_defect_pages(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    stats: dict[int, list[int]] = {}                             # page → [bad, total]
    for b in blocks:
        if b.page is None:
            continue
        st = stats.setdefault(b.page, [0, 0])
        for ch in b.text:
            st[1] += 1
            if ch == "�" or (ch not in "\n\t"                       # Co = PUA: типичный
                                  and unicodedata.category(ch)      # битый шрифт-маппинг
                                  in ("Cc", "Cn", "Co")):
                st[0] += 1
    for page in sorted(stats):
        bad, total = stats[page]
        if total and bad / total > cfg.defect_char_ratio:
            ctx.report.pages_flagged.append(page)
            ctx.report.warnings.append(
                f"страница {page}: дефектный текстовый слой "
                f"({bad / total:.1%} нечитаемых символов)")
    return blocks
p4_defect_pages.name = "P4 defect pages"
```

- [ ] **Step 4: Зелёный**

Run: `uv run pytest tests/unit/test_pdf_layout.py -q` → PASS; `uv run pytest -q` → все зелёные (проходы ещё никуда не подключены — байты golden не тронуты).

- [ ] **Step 5: Commit**

```bash
git add src/librarian/ir.py src/librarian/passes/pdf_layout.py tests/unit/test_pdf_layout.py
git commit -m "pdf layout passes p1-p4: page numbers, headers, columns, defects"
```

---

### Task 3: проходы P5–P7 + подключение PDF_PASSES

**Files:**
- Modify: `src/librarian/passes/pdf_layout.py` (+P5, P6, P7, PDF_PASSES)
- Modify: `src/librarian/passes/normalize.py` (подключение для fmt=PDF)
- Test: `tests/unit/test_pdf_layout.py` (дописать)

**Interfaces:**
- Consumes: `textrules.apply_patterns_to_blocks` (P5.5, создана в M3), `textrules.merge_lines` (P6), `origin="pdf:N"` из задачи 1 (число строк для «≤ 2 строк» и высоты строки).
- Produces: `p5_headings`, `p6_cross_page`, `p7_footnotes`, `PDF_PASSES = [p1…p7]`; `apply_block_passes` гоняет PDF_PASSES после N1–N3 только для `ctx.fmt is Format.PDF`. Отчётность: `removed["footnotes_moved" | "footnotes_dropped"]: int`.

- [ ] **Step 1: Красный тест** — дописать в `tests/unit/test_pdf_layout.py`:

```python
# --- P5 ---------------------------------------------------------------------

def _sized_doc():
    body = [para("Обычный длинный абзац основного текста номер %d. Он тянется и тянется." % i,
                 bbox=(72, 200 + 40 * i, 520, 230 + 40 * i), size=10.0)
            for i in range(6)]
    return body


def test_p5_size_histogram_levels():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Volume I", bbox=(72, 60, 200, 84), size=20.0),
               para("Chapter 1", bbox=(72, 100, 200, 120), size=16.0)]
              + _sized_doc()
              + [para("Volume II", page=1, bbox=(72, 500, 200, 524), size=20.0),
                 para("Chapter 2", page=1, bbox=(72, 540, 200, 560), size=16.0)])
    out = p5_headings(blocks, ctx)
    heads = {b.text: b.level for b in out if b.kind is BlockKind.HEADING}
    assert heads == {"Volume I": 1, "Volume II": 1, "Chapter 1": 2, "Chapter 2": 2}


def test_p5_rejects_long_and_punctuated():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    long3 = para("Три строки крупного текста " * 6, bbox=(72, 60, 520, 130),
                 size=16.0, lines=3)                               # > 2 строк
    dotted = para("Это не заголовок.", bbox=(72, 140, 300, 160), size=16.0)
    blocks = [long3, dotted] + _sized_doc() + [
        para("Настоящий", bbox=(72, 500, 200, 520), size=16.0),
        para("Второй настоящий", bbox=(72, 540, 300, 560), size=16.0)]
    out = p5_headings(blocks, ctx)
    kinds = {b.text[:12]: b.kind for b in out}
    assert kinds["Три строки к"] is BlockKind.PARA
    assert kinds["Это не загол"] is BlockKind.PARA
    assert kinds["Настоящий"] is BlockKind.HEADING


def test_p5_bold_rule_next_level():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Chapter 1", bbox=(72, 60, 200, 80), size=16.0),
               para("Chapter 2", bbox=(72, 90, 200, 110), size=16.0)]
              + _sized_doc()
              + [para("Врез жирным", bbox=(72, 500, 220, 515), size=10.0, bold=True)])
    out = p5_headings(blocks, ctx)
    bold = next(b for b in out if b.text == "Врез жирным")
    assert bold.kind is BlockKind.HEADING and bold.level == 2      # 1 размерный + 1


def test_p5_monofont_falls_back_to_patterns():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = [para("Chapter 1", bbox=(72, 60, 200, 80))] + _sized_doc()
    out = p5_headings(blocks, ctx)                                 # все 10pt
    head = next(b for b in out if b.kind is BlockKind.HEADING)
    assert head.text == "Chapter 1" and head.origin == "pattern:rank3"


def test_p5_multiline_heading_merged():
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Очень длинное", bbox=(72, 60, 300, 80), size=16.0),
               para("название главы", bbox=(72, 82, 300, 102), size=16.0)]
              + _sized_doc())
    out = p5_headings(blocks, ctx)
    heads = [b for b in out if b.kind is BlockKind.HEADING]
    assert len(heads) == 1 and heads[0].text == "Очень длинное название главы"
    assert heads[0].origin == "pdf:2"                   # честное число строк после склейки
    swallowed = next(b for b in blocks if b.text == "название главы")
    assert swallowed.kind is BlockKind.PARA             # фантом в raw.blocks демотирован


def test_p5_two_distinct_short_headings_not_merged():
    # отклонение 27: два РАЗНЫХ коротких заголовка рядом (короткие главы на
    # одной странице) не должны схлопнуться в «Chapter 1 Chapter 2»
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    blocks = ([para("Chapter 1", bbox=(72, 60, 200, 80), size=16.0),
               para("Chapter 2", bbox=(72, 90, 200, 110), size=16.0)]
              + _sized_doc())
    out = p5_headings(blocks, ctx)
    heads = [b.text for b in out if b.kind is BlockKind.HEADING]
    assert heads == ["Chapter 1", "Chapter 2"]


def test_p5_levels_found_but_no_candidates_no_pattern_fallback():
    # §7.2 P5.5 буквально: паттерны 6.1.3 — ТОЛЬКО если размерных уровней
    # «не нашлось вовсе»; уровни есть, но кандидаты отфильтрованы → фолбэка нет
    from librarian.passes.pdf_layout import p5_headings
    ctx = ctx_pdf()
    big = [para("Крупный кегль, но это длинное предложение с точкой на конце.",
                bbox=(72, 60 + 90 * i, 520, 130 + 90 * i), size=16.0, lines=3)
           for i in range(2)]
    blocks = big + [para("Chapter 1", bbox=(72, 300, 200, 320))] + _sized_doc()
    out = p5_headings(blocks, ctx)                      # «Chapter 1» — мишень паттернов
    assert all(b.kind is BlockKind.PARA for b in out)   # но фолбэк не сработал


# --- P6 ---------------------------------------------------------------------

def test_p6_merges_across_pages_with_hyphen():
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    a = para("Корабль шёл на юг сквозь тяжёлую во-", page=1, bbox=(72, 700, 520, 730))
    b = para("ду, и берег таял за кормой.", page=2, bbox=(72, 80, 520, 110))
    out = p6_cross_page([a, b], ctx)
    assert len(out) == 1
    assert "воду, и берег" in out[0].text


def test_p6_respects_sentence_end():
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    a = para("Предложение закончилось.", page=1, bbox=(72, 700, 520, 730))
    b = para("и началось новое со строчной", page=2, bbox=(72, 80, 520, 110))
    assert len(p6_cross_page([a, b], ctx)) == 2


def test_p6_three_page_chain_merges_fully():
    # риск-находка ревью: цепочка через 3 страницы должна домердживаться
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=3)
    a = para("Корабль шёл на юг сквозь тяжёлую во-", page=1, bbox=(72, 700, 520, 730))
    b = para("ду по всему проливу, где берег та-", page=2, bbox=(72, 80, 520, 110))
    c = para("ял за кормой.", page=3, bbox=(72, 80, 520, 110))
    out = p6_cross_page([a, b, c], ctx)
    assert len(out) == 1
    assert "воду" in out[0].text and "таял" in out[0].text


def test_p6_merges_across_pictureonly_page():
    # страница-иллюстрация без PARA-блоков не рвёт склейку
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=3)
    a = para("Хвост предложения без точки и с продолжением на", page=1,
             bbox=(72, 700, 520, 730))
    c = para("следующей текстовой странице.", page=3, bbox=(72, 80, 520, 110))
    assert len(p6_cross_page([a, c], ctx)) == 1


def test_p6_does_not_merge_through_heading():
    # заголовок в начале следующей страницы = граница главы, склейки нет
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    a = para("глава оборвалась на полуслове без точки и", page=1,
             bbox=(72, 700, 520, 730))
    h = Block(BlockKind.HEADING, "Chapter 2", level=1, page=2, bbox=(72, 60, 200, 80))
    b = para("новый текст со строчной", page=2, bbox=(72, 100, 520, 130))
    assert len(p6_cross_page([a, h, b], ctx)) == 3


def test_p6_skips_footnote_candidate():
    # отклонение 28: сноска (мелкий кегль, подвал страницы) — последний PARA
    # страницы в sort-порядке; она НЕ должна срастись с телом следующей страницы
    from librarian.passes.pdf_layout import p6_cross_page
    ctx = ctx_pdf(pages=2)
    body1 = para("Абзац, обрывающийся без точки в конце страницы и", page=1,
                 bbox=(72, 600, 520, 630))
    fn = para("1 Сноска мелким кеглем без точки", page=1,
              bbox=(72, 780, 520, 800), size=8.0)
    body2 = para("это тело, продолжающееся здесь.", page=2,
                 bbox=(72, 100, 520, 130))
    out = p6_cross_page([body1, fn, body2], ctx)
    assert [b.text for b in out] == [body1.text, fn.text, body2.text]


# --- P7 ---------------------------------------------------------------------

def test_p7_footnote_tagged_and_kept_in_place():
    from librarian.passes.pdf_layout import p7_footnotes
    ctx = ctx_pdf()
    blocks = _sized_doc() + [
        para("1 Сноска мелким кеглем у подвала страницы.",
             bbox=(72, 780, 520, 800), size=8.0)]
    out = p7_footnotes(blocks, ctx)
    assert out[-1].kind is BlockKind.FOOTNOTE                      # позиция не меняется
    assert ctx.report.removed["footnotes_moved"] == 1


def test_p7_drop_mode(monkeypatch):
    import dataclasses
    from librarian.passes.pdf_layout import p7_footnotes
    ctx = ctx_pdf()
    ctx.cfg = dataclasses.replace(
        ctx.cfg, pdf=dataclasses.replace(ctx.cfg.pdf, footnotes="drop"))
    blocks = _sized_doc() + [
        para("* Сноска на выброс.", bbox=(72, 780, 520, 800), size=8.0)]
    out = p7_footnotes(blocks, ctx)
    assert all(b.kind is not BlockKind.FOOTNOTE for b in out)
    assert ctx.report.removed["footnotes_dropped"] == 1


# --- подключение ------------------------------------------------------------

def test_pdf_passes_wired_for_pdf_only():
    from librarian.passes.normalize import apply_block_passes
    ctx = ctx_pdf()
    blocks = [para("— 4 —", bbox=(280, 810, 315, 825))]            # P1-мишень
    assert apply_block_passes(blocks, ctx) == []                   # PDF: P1 удалил

    from librarian.ir import DocContext, Format, RawDoc, ReportDraft
    raw_txt = RawDoc(fmt=Format.TXT, blocks=[], title=None, author=None,
                     lang=None, ref_text="")
    ctx_txt = DocContext(Format.TXT, ctx.cfg, raw_txt, ReportDraft())
    kept = apply_block_passes([Block(BlockKind.PARA, "— 4 —")], ctx_txt)
    assert len(kept) == 1                                          # не-PDF не трогаем
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_pdf_layout.py -q`
Expected: FAIL — `ImportError: cannot import name 'p5_headings'`

- [ ] **Step 3: Реализация** — дописать в `src/librarian/passes/pdf_layout.py`:

```python
from librarian.config import Config
from librarian.extractors.textrules import (apply_patterns_to_blocks,   # см. откл. 19
                                            compile_patterns, line_rank,
                                            merge_lines)
# (при записи файла оба импорта — к верхнему import-блоку задачи 2, не в середину)

_NO_MERGE_END = tuple(".!?…:;»\")")


def _nlines(b: Block) -> int:
    """Число строк блока до склейки — экстрактор кодирует его в origin="pdf:N"."""
    if b.origin.startswith("pdf:"):
        try:
            return int(b.origin.split(":", 1)[1])
        except ValueError:
            pass
    return b.text.count("\n") + 1


def _line_h(b: Block) -> float:
    return (b.bbox[3] - b.bbox[1]) / max(1, _nlines(b))


# _body_size уже в модуле — создан в задаче 2 (нужен P1); здесь только используется.


def _merge_split_headings(blocks: list[Block], cfg: Config) -> list[Block]:
    """§7.2 P5.6: два подряд HEADING одного уровня на одной странице
    с зазором по y < 1.5 высоты строки — один многострочный заголовок.
    Guard (отклонение 27): если ОБЕ строки сами по себе — полноценные
    заголовки по паттернам 6.1.3, это две РАЗНЫЕ короткие главы на одной
    странице, а не перенос — не сливать (иначе теряется граница главы)."""
    patterns = compile_patterns(cfg)
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (prev is not None and b.kind is BlockKind.HEADING
                and prev.kind is BlockKind.HEADING and prev.level == b.level
                and prev.page == b.page and prev.bbox and b.bbox
                and b.bbox[1] - prev.bbox[3] < 1.5 * _line_h(prev)
                and not (line_rank(prev.text, patterns) is not None
                         and line_rank(b.text, patterns) is not None)):
            n = _nlines(prev) + _nlines(b)              # ДО перезаписи origin
            prev.text = f"{prev.text} {b.text}"
            prev.bbox = (min(prev.bbox[0], b.bbox[0]), prev.bbox[1],
                         max(prev.bbox[2], b.bbox[2]), b.bbox[3])
            prev.origin = f"pdf:{n}"                    # иначе _line_h деградирует каскадно
            b.kind, b.level = BlockKind.PARA, None      # не оставлять фантомный HEADING
            continue                                    # в ctx.raw.blocks (его читает r2_toc)
        out.append(b)
    return out


def p5_headings(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    B = _body_size(blocks)
    levels: dict[float, int] = {}
    if B is not None:
        counts: dict[float, int] = {}
        for b in blocks:
            if b.kind is BlockKind.PARA and b.font_size is not None:
                counts[b.font_size] = counts.get(b.font_size, 0) + 1
        sizes = sorted((s for s, n in sorted(counts.items())
                        if s >= cfg.heading_size_ratio * B and n >= 2), reverse=True)
        levels = {s: i + 1 for i, s in enumerate(sizes[:cfg.heading_max_levels])}
        for b in blocks:
            if b.kind is not BlockKind.PARA or b.font_size is None:
                continue
            lvl = levels.get(b.font_size)
            if (lvl is not None and _nlines(b) <= 2
                    and len(b.text) <= cfg.heading_max_chars
                    and not b.text.rstrip().endswith((".", ","))):
                b.kind, b.level = BlockKind.HEADING, lvl
                # origin НЕ трогаем: "pdf:N" — единственный носитель числа строк,
                # он нужен _line_h в _merge_split_headings ниже
            elif (b.font_size == B and b.bold and _nlines(b) == 1
                    and len(b.text) <= cfg.bold_heading_max_chars
                    and not b.text.rstrip().endswith(".")):
                b.kind = BlockKind.HEADING
                b.level = min(len(levels) + 1, 4)
        blocks = _merge_split_headings(blocks, ctx.cfg)
    if not levels:                       # §7.2 P5.5 буквально: размерных уровней
        blocks = apply_patterns_to_blocks(blocks, ctx.cfg)   # не нашлось вовсе
    return blocks
p5_headings.name = "P5 headings"


def p6_cross_page(blocks: list[Block], ctx: DocContext) -> list[Block]:
    """Кандидат на склейку — последний PARA страницы и СЛЕДУЮЩИЙ ЗА НИМ блок
    порядка чтения (PARA более поздней страницы). Adjacency-правило переживает
    страницы без текста, не сшивает через заголовок и, с переносом page/bbox на
    хвост, домердживает цепочки из 3+ страниц (отклонение 26).
    Guard (отклонение 28): P6 идёт ДО P7 (§7), поэтому сноска внизу страницы —
    ещё PARA и в sort-порядке стоит последней; без фильтра она срослась бы
    с телом следующей страницы (или утащила его в сноски). Кандидат,
    похожий на сноску геометрией и кеглем, пропускается — им займётся P7."""
    cfg = ctx.cfg.pdf
    out = list(blocks)
    B = _body_size(out)

    def _footnotish(b: Block) -> bool:
        return (B is not None and b.font_size is not None
                and b.font_size < cfg.footnote_size_ratio * B
                and b.page is not None and b.bbox is not None
                and b.bbox[1] >= (1 - cfg.footnote_zone) * _page_h(ctx, b.page))

    changed = True
    while changed:
        changed = False
        last_para: dict[int, int] = {}
        for idx, b in enumerate(out):
            if b.kind is BlockKind.PARA and b.page is not None:
                last_para[b.page] = idx
        for page in sorted(last_para):
            i = last_para[page]
            if _footnotish(out[i]):                      # откл. 28
                continue
            j = i + 1
            if j >= len(out):
                continue
            nb = out[j]
            if (nb.kind is not BlockKind.PARA or nb.page is None
                    or nb.page <= page):                 # не начало более поздней страницы
                continue
            tail = out[i].text.rstrip()
            head = nb.text.lstrip()
            if (tail and head and not tail.endswith(_NO_MERGE_END)
                    and (head[0].islower() or head[0] in "—–-")):
                out[i].text = merge_lines([out[i].text, nb.text], ctx.cfg)
                out[i].page = nb.page                    # хвост блока теперь на этой
                out[i].bbox = nb.bbox                    # странице — zone/B-логика P7
                del out[j]                               # смотрит на согласованную геометрию
                changed = True
                break                       # индексы поплыли — пересчитать карту
    return out
p6_cross_page.name = "P6 cross-page merge"


def p7_footnotes(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    B = _body_size(blocks)
    if B is None:
        return blocks
    moved = 0
    for b in blocks:
        if (b.kind is BlockKind.PARA and b.font_size is not None
                and b.font_size < cfg.footnote_size_ratio * B
                and b.page is not None and b.bbox is not None
                and b.bbox[1] >= (1 - cfg.footnote_zone) * _page_h(ctx, b.page)
                and b.text[:1] and (b.text[0].isdigit() or b.text[0] == "*")):
            b.kind = BlockKind.FOOTNOTE
            moved += 1
    if not moved:
        return blocks
    if cfg.footnotes == "drop":
        ctx.report.removed["footnotes_dropped"] = (
            ctx.report.removed.get("footnotes_dropped", 0) + moved)
        return [b for b in blocks if b.kind is not BlockKind.FOOTNOTE]
    ctx.report.removed["footnotes_moved"] = (
        ctx.report.removed.get("footnotes_moved", 0) + moved)
    return blocks
p7_footnotes.name = "P7 footnotes"


PDF_PASSES = [p1_page_numbers, p2_headers_footers, p3_reading_order,
              p4_defect_pages, p5_headings, p6_cross_page, p7_footnotes]
```

В `src/librarian/passes/normalize.py`: добавить `Format` в импорт из `librarian.ir` и заменить `apply_block_passes`:

```python
from librarian.ir import Block, BlockKind, DocContext, Format
from librarian.passes.pdf_layout import PDF_PASSES


def apply_block_passes(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for p in COMMON_PASSES:
        blocks = p(blocks, ctx)
    if ctx.fmt is Format.PDF:                            # §7: P1–P7 только PDF
        for p in PDF_PASSES:
            blocks = p(blocks, ctx)
    return blocks
```

- [ ] **Step 4: Зелёный + golden без изменений**

Run: `uv run pytest -q` → все зелёные (PDF-фикстур ещё нет, не-PDF байты не тронуты).

- [ ] **Step 5: Commit**

```bash
git add src/librarian/passes/pdf_layout.py src/librarian/passes/normalize.py tests/unit/test_pdf_layout.py
git commit -m "pdf layout passes p5-p7, wire pdf pass chain"
```

---

### Task 4: полный quality (§11.1–11.6) + схема report.json + bump версии

**Files:**
- Rewrite: `src/librarian/quality.py`
- Modify: `src/librarian/pipeline.py` (шаги 9–10: рендер один раз)
- Modify: `src/librarian/__init__.py` (`PIPELINE_VERSION = "2.3"`)
- Rewrite: `tests/unit/test_quality.py`
- Regenerate: `tests/golden/**` (все — схема report.json меняется)

**Interfaces:**
- Produces: `Metrics(coverage, garbage_ratio, encoding_score, structure, dehyphen_residue, median_tokens, chapters_found, layout_flag)`; `compute_metrics(chapters, ctx, rendered: list[str]) -> Metrics` (третий аргумент — отклонение 18); `score_and_status(m, cfg) -> (score, status, subscores, triggers)`; `build_report(...)` — полная схема §11.6 (ключ `unknown_tags` теперь безусловный — снимает отклонение 17 из M3; ключ `control_chars` уходит — управляющие уже учтены в encoding-метрике).
- Consumes: `ch.tokens` (финальные, посчитаны в pipeline до метрик), `ctx.raw.ref_text`, `ctx.report.removed["meta_sections"|"toc"][i]["tokens"]` (R1/R2 кладут их с M2), `ctx.report.{control_chars,pages_flagged,multi_column_pages,unknown_tags,warnings}`, `cfg.quality.*`, `cfg.pdf.multi_column_page_ratio`.

- [ ] **Step 1: Красный тест** — переписать `tests/unit/test_quality.py` (старые стаб-тесты заменить; тест `test_report_unknown_tags_only_when_present` из M3 заменяется на безусловный вариант ниже):

```python
# tests/unit/test_quality.py
from librarian.config import load_config
from librarian.ir import (Block, BlockKind, Chapter, DocContext, Format,
                          RawDoc, ReportDraft)
from librarian.quality import (Metrics, build_report, compute_metrics,
                               score_and_status)
from librarian.tokens import count

CFG = load_config(None)


def _ctx(fmt=Format.TXT, ref_text="", pages=None, **report_kw):
    raw = RawDoc(fmt=fmt, blocks=[], title=None, author=None, lang=None,
                 ref_text=ref_text, pages=pages)
    return DocContext(fmt, CFG, raw, ReportDraft(**report_kw))


def _chapter(text, n=1):
    ch = Chapter(n, f"Глава {n}", [Block(BlockKind.PARA, text)])
    ch.tokens = count(f"# Глава {n}\n\n{text}\n")
    return ch


def _rendered(ch):
    return f"# {ch.title}\n\n{ch.blocks[0].text}\n"


BODY = ("Ровный длинный абзац основного текста, в котором достаточно слов, "
        "чтобы глава не была крошечной и метрики имели смысл. ") * 30


def test_coverage_subtracts_legit_removed():
    # §11.1: токены секций, удалённых R1/R2, вычитаются из знаменателя
    ch = _chapter(BODY)
    removed_text = "ISBN 5-1234. Все права защищены. " * 20
    ctx = _ctx(ref_text=BODY + "\n\n" + removed_text)
    ctx.report.removed["meta_sections"] = [
        {"title": "х", "tokens": count(removed_text), "text": removed_text}]
    m = compute_metrics([ch], ctx, [_rendered(ch)])
    assert 0.90 < m.coverage <= 1.05                    # без вычета было бы ~0.6


def test_garbage_counts_short_and_lone_numbers():
    ch = _chapter(BODY)
    junk = "# Глава 1\n\n" + BODY + "\n\nаб\n\n1234\n\n— \n"
    # «аб» (≤2), «1234» (одинокое число), «—» — легитимный短 не считается
    m = compute_metrics([ch], _ctx(ref_text=BODY), [junk])
    lines = [ln for ln in junk.split("\n") if ln.strip()]
    assert m.garbage_ratio == 2 / len(lines)


def test_encoding_counts_fffd_mojibake_and_controls():
    ch = _chapter(BODY)
    bad = "# Глава 1\n\n" + BODY + "��" + "â€" + "\n"
    ctx = _ctx(ref_text=BODY, control_chars=3)
    m = compute_metrics([ch], ctx, [bad])
    assert m.encoding_score == (2 + 1 + 3) / len(bad)


def test_dehyphen_only_for_merge_formats():
    ch = _chapter(BODY)
    hy = "# Глава 1\n\nстрока с пере-\nносом\n" + BODY + "\n"
    m_txt = compute_metrics([ch], _ctx(fmt=Format.TXT, ref_text=BODY), [hy])
    m_fb2 = compute_metrics([ch], _ctx(fmt=Format.FB2, ref_text=BODY), [hy])
    assert m_txt.dehyphen_residue > 0 and m_fb2.dehyphen_residue == 0


def test_layout_flag_multicolumn_ratio():
    ch = _chapter(BODY)
    ctx = _ctx(fmt=Format.PDF, ref_text=BODY, pages=10,
               multi_column_pages=[1, 2])                # 20% > 10%
    m = compute_metrics([ch], ctx, [_rendered(ch)])
    assert m.layout_flag is True


def test_layout_flag_alone_forces_review():
    # С-11 изолированно: многоколоночность — жёсткий триггер review даже при
    # идеальных остальных метриках (golden kolonki3 сам по себе это не докажет)
    m = Metrics(coverage=1.0, garbage_ratio=0.0, encoding_score=0.0,
                structure=1.0, dehyphen_residue=0.0, median_tokens=5000,
                chapters_found=True, layout_flag=True)
    score, status, _, triggers = score_and_status(m, CFG)
    assert status == "review"
    assert any("колон" in t for t in triggers)


def test_subscores_piecewise_and_example_from_spec():
    # §11.6: coverage 0.55 → субоценка 0.5, score ≈ 0.85, триггер «< 0.60»
    m = Metrics(coverage=0.55, garbage_ratio=0.004, encoding_score=0.0002,
                structure=1.0, dehyphen_residue=0.001, median_tokens=5000,
                chapters_found=True, layout_flag=False)
    score, status, subs, triggers = score_and_status(m, CFG)
    assert subs["coverage"] == 0.5
    assert 0.84 < score < 0.87
    assert status == "review"
    assert any("coverage" in t and "< 0.60" in t for t in triggers)


def test_status_boundaries():
    def mk(cov, structure=1.0, chapters_found=True):
        return Metrics(coverage=cov, garbage_ratio=0.0, encoding_score=0.0,
                       structure=structure, dehyphen_residue=0.0, median_tokens=5000,
                       chapters_found=chapters_found, layout_flag=False)
    assert score_and_status(mk(1.0), CFG)[1] == "ok"
    # провал одной coverage НЕ роняет в failed: 0.30·0 + 0.25 + 0.20 + 0.15 + 0.10 = 0.70
    assert score_and_status(mk(0.15), CFG)[1] == "review"
    # failed достижим только совокупно: 0.30·0 + 0.25·0.3 + 0.20 + 0.15 + 0.10 = 0.525 < 0.60
    assert score_and_status(mk(0.15, structure=0.3, chapters_found=False),
                            CFG)[1] == "failed"
    m_fallback = Metrics(coverage=1.0, garbage_ratio=0.0, encoding_score=0.0,
                         structure=0.3, dehyphen_residue=0.0, median_tokens=0,
                         chapters_found=False, layout_flag=False)
    score, status, _, triggers = score_and_status(m_fallback, CFG)
    assert round(score, 3) == 0.825 and status == "review"          # §8.5


def test_report_full_schema():
    ch = _chapter(BODY)
    ctx = _ctx(ref_text=BODY)
    m = compute_metrics([ch], ctx, [_rendered(ch)])
    score, status, subs, trig = score_and_status(m, CFG)
    rep = build_report(ctx, m, subs, trig, score, status, CFG)
    assert set(rep) == {"pipeline_version", "config_hash", "status", "score",
                        "metrics", "subscores", "hard_triggers", "pages_flagged",
                        "multi_column_pages", "oversize_blocks_split",
                        "unknown_tags", "removed", "warnings"}
    assert set(rep["metrics"]) == {"coverage", "garbage_ratio", "encoding_score",
                                   "structure", "dehyphen_residue"}
    assert rep["unknown_tags"] == {}                     # теперь безусловный ключ
```

И туда же — §3.2 шаг 11 (fail loudly: причина failed-книги обязана попасть в stderr).
⚠️ В фикстуре сознательно НЕТ символа «�»: короткий репитативный текст с U+FFFD
сбивает автодетект кодировки TXT-экстрактора (vowel-score уводит в iso8859-5 — 
проверено прогоном), и раскладка субоценок стала бы зависеть от версии
charset_normalizer. Естественный русский текст детектится как utf-8 надёжно:

```python
def test_failed_by_score_prints_triggers_to_stderr(tmp_path, capsys):
    # раскладка: coverage 0.30 + structure 0.25·0.3 + encoding 0.15
    #            + garbage 0 (треть строк ≤2 симв.) + dehyphen 0 (треть строк
    #            с висячим дефисом) = 0.525 < 0.60 → failed
    from librarian.pipeline import run_ingest
    junk = tmp_path / "musor.txt"
    junk.write_text(
        ("Обычная спокойная строка про море и маяк, ровная и достаточно длинная.\n\n"
         "аб\n\n"
         "и снова про море, но эта строка обрывается на самом инте-\n\n") * 60,
        encoding="utf-8")
    out = run_ingest([junk], CFG, tmp_path / "lib")[0]
    assert out.status == "failed"
    assert out.score is not None and out.score < 0.60
    err = capsys.readouterr().err
    assert "garbage_ratio" in err and "не сохранена" in err
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_quality.py -q`
Expected: FAIL — `ImportError`/`TypeError` (новая сигнатура и Metrics ещё не существуют).

- [ ] **Step 3: Реализация.** Переписать `src/librarian/quality.py`:

```python
# src/librarian/quality.py
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from librarian import PIPELINE_VERSION
from librarian.config import Config, config_hash
from librarian.ir import Chapter, DocContext, Format
from librarian.tokens import count

_MEDIAN_LO, _MEDIAN_HI = 300, 20000
_OK_SHORT = {"—", "–", "*", "―"}                       # §11.2 garbage-исключения
_DEHYPHEN_FMTS = (Format.TXT, Format.MD, Format.PDF)   # §11.2 / М-минор


@dataclass
class Metrics:
    coverage: float
    garbage_ratio: float
    encoding_score: float
    structure: float
    dehyphen_residue: float
    median_tokens: float
    chapters_found: bool
    layout_flag: bool


def compute_metrics(chapters: list[Chapter], ctx: DocContext,
                    rendered: list[str]) -> Metrics:
    found = bool(chapters) and not ctx.report.structure_fallback
    med = float(median(c.tokens for c in chapters)) if chapters else 0.0
    structure = 0.3 if not found else (1.0 if _MEDIAN_LO <= med <= _MEDIAN_HI else 0.7)

    removed_tokens = sum(e.get("tokens", 0)                       # §11.1
                         for key in ("meta_sections", "toc")
                         for e in ctx.report.removed.get(key, []))
    denom = max(1, count(ctx.raw.ref_text) - removed_tokens)
    coverage = sum(ch.tokens for ch in chapters) / denom

    total_lines = garbage = residue = 0
    for text in rendered:
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            s = ln.strip()
            if not s:
                continue
            total_lines += 1
            if len(s) <= 2 and s not in _OK_SHORT:
                garbage += 1
            elif (s.isdigit() and len(s) <= 4
                    and (i == 0 or not lines[i - 1].strip())
                    and (i + 1 == len(lines) or not lines[i + 1].strip())):
                garbage += 1                                       # одинокое число
            r = ln.rstrip()
            if len(r) >= 2 and r.endswith("-") and r[-2].isalpha():
                residue += 1
    garbage_ratio = garbage / total_lines if total_lines else 0.0
    dehyphen = (residue / total_lines
                if ctx.fmt in _DEHYPHEN_FMTS and total_lines else 0.0)

    total_chars = sum(len(t) for t in rendered)
    bad = sum(t.count("�") for t in rendered) + ctx.report.control_chars
    for marker in ctx.cfg.quality.mojibake_markers:
        bad += sum(t.count(marker) for t in rendered)
    encoding = bad / total_chars if total_chars else 0.0

    pages = ctx.raw.pages or 0
    layout_flag = (pages > 0 and len(ctx.report.multi_column_pages)
                   > ctx.cfg.pdf.multi_column_page_ratio * pages)
    return Metrics(coverage, garbage_ratio, encoding, structure, dehyphen,
                   med, found, layout_flag)


def _down(x: float, full: float, zero: float) -> float:
    """1 при x ≤ full, 0 при x ≥ zero, между — линейно (§11.3)."""
    if x <= full:
        return 1.0
    if x >= zero:
        return 0.0
    return (zero - x) / (zero - full)


def _coverage_sub(c: float, pts: tuple[float, ...]) -> float:
    z_lo, f_lo, f_hi, z_hi = pts
    if f_lo <= c <= f_hi:
        return 1.0
    if c <= z_lo or c >= z_hi:
        return 0.0
    if c < f_lo:
        return (c - z_lo) / (f_lo - z_lo)
    return (z_hi - c) / (z_hi - f_hi)


def score_and_status(m: Metrics, cfg: Config) -> tuple[float, str, dict, list[str]]:
    q = cfg.quality
    subscores = {
        "coverage": round(_coverage_sub(m.coverage, q.coverage_points), 4),
        "garbage": round(_down(m.garbage_ratio, q.garbage["full"], q.garbage["zero"]), 4),
        "encoding": round(_down(m.encoding_score, q.encoding["full"], q.encoding["zero"]), 4),
        "dehyphen": round(_down(m.dehyphen_residue, q.dehyphen["full"], q.dehyphen["zero"]), 4),
        "structure": m.structure,
    }
    score = round(sum(q.weights[k] * subscores[k] for k in sorted(subscores)), 4)
    triggers: list[str] = []                                       # §11.2, порядок фиксирован
    lo, hi = q.coverage_review
    if m.coverage < lo:
        triggers.append(f"coverage {m.coverage:.2f} < {lo:.2f}")
    elif m.coverage > hi:
        triggers.append(f"coverage {m.coverage:.2f} > {hi:.2f}")
    if m.garbage_ratio > q.garbage["review"]:
        triggers.append(f"garbage_ratio {m.garbage_ratio:.4f} > {q.garbage['review']}")
    if m.encoding_score > q.encoding["review"]:
        triggers.append(f"encoding_score {m.encoding_score:.4f} > {q.encoding['review']}")
    if not m.chapters_found:
        triggers.append("главы не найдены (fallback-раскрой)")
    if m.dehyphen_residue > q.dehyphen["review"]:
        triggers.append(f"dehyphen_residue {m.dehyphen_residue:.4f} > {q.dehyphen['review']}")
    if m.layout_flag:
        triggers.append("многоколоночная вёрстка (3+ колонки) на более чем 10% страниц")
    if score < q.failed_max:
        status = "failed"
    elif score < q.ok_min or triggers:
        status = "review"
    else:
        status = "ok"
    return score, status, subscores, triggers


def build_report(ctx: DocContext, m: Metrics, subscores: dict, triggers: list[str],
                 score: float, status: str, cfg: Config) -> dict:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "config_hash": config_hash(cfg),
        "status": status,
        "score": score,
        "metrics": {"coverage": round(m.coverage, 4),
                    "garbage_ratio": round(m.garbage_ratio, 4),
                    "encoding_score": round(m.encoding_score, 4),
                    "structure": m.structure,
                    "dehyphen_residue": round(m.dehyphen_residue, 4)},
        "subscores": subscores,
        "hard_triggers": triggers,
        "pages_flagged": ctx.report.pages_flagged,
        "multi_column_pages": ctx.report.multi_column_pages,
        "oversize_blocks_split": ctx.report.oversize_blocks_split,
        "unknown_tags": dict(sorted(ctx.report.unknown_tags.items())),
        "removed": ctx.report.removed,
        "warnings": ctx.report.warnings,
    }
```

В `src/librarian/pipeline.py` шаги 9–10 заменить:

```python
    rendered = [render_chapter(ch) for ch in chapters]               # 9 — рендер один раз
    for ch, text in zip(chapters, rendered):
        ch.tokens = count(text)
    metrics = compute_metrics(chapters, ctx, rendered)               # 10
```

Там же ветка `if status == "failed":` сейчас печатает только голый score — заменить
печать на причины (§3.2 шаг 11, fail loudly; `triggers` — из `score_and_status`):

```python
    if status == "failed":
        reasons = "; ".join(triggers) if triggers else f"score {score}"
        print(f"{path.name}: failed ({reasons}) — книга не сохранена", file=sys.stderr)
```

В `src/librarian/__init__.py`: `PIPELINE_VERSION = "2.3"` (схема report.json изменила байты всех книг — §2).

- [ ] **Step 4: Юниты зелёные, регенерация golden**

Run: `uv run pytest tests/unit -q` → PASS.
Run: `uv run python scripts/update_golden.py && git diff --stat tests/golden`
Expected: у **всех** книг изменились `report.json` и `provenance` в `book.json` (новая версия); главы `.md` — **ни одного диффа**. Проверить `git diff` на 2–3 report.json глазами: метрики заполнены, статусы прежние (`ok`). Если какая-то книга сползла в `review` из-за coverage > 1.02 (маленькие фикстуры: заголовки-пути раздувают числитель) — **удлинить тексты фикстуры** и перегенерировать fixtures+golden; формулы не подгонять.
Run: `uv run pytest -q` → все зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/quality.py src/librarian/pipeline.py src/librarian/__init__.py tests/unit/test_quality.py tests/golden
git commit -m "full quality metrics, report schema 11.6, pipeline version 2.3"
```

---

### Task 5: `lib doctor` (§15)

**Files:**
- Modify: `src/librarian/catalog.py` (+`broken_dirs`)
- Modify: `src/librarian/cli.py` (+`doctor`)
- Test: `tests/unit/test_catalog.py`, `tests/unit/test_cli.py` (дописать)

**Interfaces:**
- Produces: `catalog.broken_dirs(lib_root: Path) -> list[str]` — каталоги с нечитаемым book.json; команда `lib doctor` (без id: таблица review-книг + битые каталоги; с id: JSON с `hard_triggers`, `pages_flagged`, `multi_column_pages`, `warnings`, `removed` из report.json). Данные — stdout, ошибки — stderr/exit 1.

- [ ] **Step 1: Красный тест.** В `tests/unit/test_catalog.py` дописать:

```python
def test_broken_dirs_lists_unreadable_book_json(tmp_path):
    from librarian.catalog import broken_dirs
    good = tmp_path / "good-book"; good.mkdir()
    (good / "book.json").write_text('{"id": "good-book"}', encoding="utf-8")
    bad = tmp_path / "bad-book"; bad.mkdir()
    (bad / "book.json").write_text("{оборвано…", encoding="utf-8")
    nojson = tmp_path / "no-json"; nojson.mkdir()
    assert broken_dirs(tmp_path) == ["bad-book"]
```

В `tests/unit/test_cli.py` дописать (используя существующие в файле хелперы создания библиотеки — там уже есть ingest-фикстуры; если хелпера нет, собрать библиотеку через `run_ingest` на txt-фикстуре, как в соседних тестах):

```python
def test_doctor_book_shows_triggers_and_removed(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from typer.testing import CliRunner
    from librarian.cli import app
    from librarian.config import load_config
    from librarian.pipeline import run_ingest

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    fx = Path(__file__).parent.parent / "fixtures" / "txt" / "roman_cp1251.txt"
    out = run_ingest([fx], load_config(None), tmp_path)[0]
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "doctor", out.book_id])
    assert r.exit_code == 0
    payload = json.loads(r.stdout)
    assert {"hard_triggers", "pages_flagged", "removed", "warnings"} <= set(payload)


def test_doctor_unknown_id_exits_1(tmp_path):
    from typer.testing import CliRunner
    from librarian.cli import app
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "doctor", "net-takoy"])
    assert r.exit_code == 1
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_catalog.py tests/unit/test_cli.py -q`
Expected: FAIL — `ImportError: broken_dirs` / doctor неизвестная команда (exit 2).

- [ ] **Step 3: Реализация.** В `src/librarian/catalog.py`:

```python
def broken_dirs(lib_root: Path) -> list[str]:
    """Каталоги книг с нечитаемым book.json (С-4) — для doctor."""
    out: list[str] = []
    if not lib_root.is_dir():
        return out
    for d in sorted(p for p in lib_root.iterdir()
                    if p.is_dir() and not p.name.startswith(".")):
        bj = d / "book.json"
        if not bj.is_file():
            continue
        try:
            json.loads(bj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            out.append(d.name)
    return out
```

В `src/librarian/cli.py` добавить команду (импорты: `broken_dirs`, `scan_books` из catalog):

```python
@app.command()
def doctor(book_id: str = typer.Argument(None)) -> None:
    import json
    out = Console()
    lib = _lib_root()
    try:
        if book_id is None:
            t = Table("id", "score", "триггеры", title="книги в review")
            for bid, b in scan_books(lib):
                if b.get("quality", {}).get("status") != "review":
                    continue
                rep = _read_report(lib, bid)
                t.add_row(bid, str(b["quality"].get("score", "")),
                          "; ".join(rep.get("hard_triggers", [])))
            out.print(t)
            for bid in broken_dirs(lib):
                out.print(f"битый book.json: {bid}")
        else:
            read_book(lib, book_id)                     # неизвестный id → exit 1
            rep = _read_report(lib, book_id)
            payload = {k: rep.get(k) for k in
                       ("status", "score", "hard_triggers", "pages_flagged",
                        "multi_column_pages", "warnings", "removed")}
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2,
                                        sort_keys=True) + "\n")
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)


def _read_report(lib: Path, book_id: str) -> dict:
    import json
    p = lib / book_id / "report.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
```

- [ ] **Step 4: Зелёный**

Run: `uv run pytest -q` → все зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/catalog.py src/librarian/cli.py tests/unit/test_catalog.py tests/unit/test_cli.py
git commit -m "doctor command: review table, broken book.json, per-book report"
```

---

### Task 6: PDF-фикстуры, golden, DoD M4

**Files:**
- Modify: `scripts/make_fixtures.py`
- Create: `tests/fixtures/pdf/*.pdf`, `tests/golden/{voyage,kolonki2,kolonki3,pustoy_parol,zaparoleny,skan}/`

- [ ] **Step 1: Дописать генерацию** — в конец `scripts/make_fixtures.py`:

```python
# --- M4: pdf (§17) -----------------------------------------------------------
# ВНИМАНИЕ: pymupdf сохраняет недетерминированно (/ID) — фикстуры коммитятся
# байтами; каждый перезапуск этого блока = новые байты = регенерация golden
# (отклонение 21).
import pymupdf

PDF_DIR = FIX / "pdf"
PDF_DIR.mkdir(parents=True, exist_ok=True)

_PDFP = ("The whale went south through heavy water and the shore slowly melted "
         "behind the fishing boats of the northern coast while the keeper wrote "
         "down every light he saw across the strait during the long night watch. ")


def _tb(page, x, y, w, h, text, size=10.0):
    page.insert_textbox(pymupdf.Rect(x, y, x + w, y + h), text,
                        fontsize=size, fontname="helv")


# voyage.pdf — Volume/Chapter, колонтитул, номера страниц (P1/P2/P5/P6)
doc = pymupdf.open()
for i, (vol, chap) in enumerate([("Volume I", "Chapter 1"), (None, "Chapter 2"),
                                 ("Volume II", "Chapter 3"), (None, "Chapter 4"),
                                 (None, "Chapter 5"), (None, "Chapter 6")], 1):
    page = doc.new_page(width=595, height=842)
    page.insert_text((240, 40), "VOYAGE LOG", fontsize=9, fontname="helv")
    y = 120
    if vol:
        page.insert_text((72, y), vol, fontsize=20, fontname="helv"); y += 50
    page.insert_text((72, y), chap, fontsize=16, fontname="helv"); y += 30
    for _ in range(3):
        _tb(page, 72, y, 450, 130, _PDFP * 3); y += 145
    page.insert_text((290, 820), str(i), fontsize=9, fontname="helv")
doc.save(PDF_DIR / "voyage.pdf", deflate=True); doc.close()

# kolonki2.pdf — двухколоночный (P3.2)
doc = pymupdf.open()
for i in range(6):
    page = doc.new_page(width=595, height=842)
    if i == 0:
        page.insert_text((72, 100), "Chapter 1", fontsize=16, fontname="helv")
    for y in (140, 300, 460, 620):
        _tb(page, 36, y, 250, 140, _PDFP * 2)
        _tb(page, 320, y, 240, 140, _PDFP * 2)
doc.save(PDF_DIR / "kolonki2.pdf", deflate=True); doc.close()

# kolonki3.pdf — трёхколоночный → review ИМЕННО по С-11: заголовок обязателен,
# иначе structure-fallback сам по себе даёт review и golden доказывает не тот механизм
doc = pymupdf.open()
for i in range(6):
    page = doc.new_page(width=595, height=842)
    if i == 0:
        page.insert_text((72, 60), "Chapter 1", fontsize=16, fontname="helv")
    for y in (100, 280, 460, 640):
        for x in (36, 216, 396):
            _tb(page, x, y, 160, 170, _PDFP * 2)
doc.save(PDF_DIR / "kolonki3.pdf", deflate=True); doc.close()

# pustoy_parol.pdf — пустой user-пароль → открывается штатно (0.29)
doc = pymupdf.open()
for chap in ("Chapter 1", "Chapter 2"):
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), chap, fontsize=16, fontname="helv")
    _tb(page, 72, 140, 450, 400, _PDFP * 8)
doc.save(PDF_DIR / "pustoy_parol.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
         owner_pw="owner-secret", user_pw=""); doc.close()

# zaparoleny.pdf — настоящий пароль → EncryptedError → failed
doc = pymupdf.open()
page = doc.new_page(); page.insert_text((72, 100), "locked", fontsize=11, fontname="helv")
doc.save(PDF_DIR / "zaparoleny.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
         owner_pw="o", user_pw="sekret"); doc.close()

# skan.pdf — 5 страниц без текстового слоя → ScanError → failed
doc = pymupdf.open()
for _ in range(5):
    pg = doc.new_page()
    pg.draw_rect(pymupdf.Rect(50, 50, 500, 700), fill=(0.85, 0.85, 0.85))
doc.save(PDF_DIR / "skan.pdf"); doc.close()
print("pdf fixtures written")
```

Run: `uv run python scripts/make_fixtures.py`

- [ ] **Step 2: Прогнать вручную, проверить статусы и структуру**

Run: `uv run python -c "
from pathlib import Path
import tempfile, json
from librarian.config import load_config
from librarian.pipeline import run_ingest
for fx in sorted(Path('tests/fixtures/pdf').glob('*.pdf')):
    with tempfile.TemporaryDirectory() as d:
        o = run_ingest([fx], load_config(None), Path(d))[0]
        print(fx.name, '→', o.status, o.score, o.message[:60])
        if o.book_id:
            book = json.loads((Path(d) / o.book_id / 'book.json').read_text())
            print('  ', [c['title'] for c in book['chapters']][:6])
"`
Expected: `voyage`/`kolonki2`/`pustoy_parol` → ok, главы «Volume I · Chapter 1»-стиля; `kolonki3` → review с триггером про колонки (глава «Chapter 1» найдена паттерном — structure-fallback НЕ срабатывает, review именно из-за С-11); `zaparoleny` → failed «зашифрован»; `skan` → failed «скан, нужен OCR». Колонтитул «VOYAGE LOG» и номера страниц в главах отсутствуют. Расхождения → дефект соответствующей задачи (сначала красный юнит там, потом фикс).

- [ ] **Step 3: Golden + полный прогон**

Run: `uv run python scripts/update_golden.py && uv run pytest -q`
Expected: новые golden `{voyage,kolonki2,kolonki3,pustoy_parol,zaparoleny,skan}` (для failed-книг — только index.json с пустым списком: книга честно не сохранена); старые golden не изменились; все тесты зелёные.

- [ ] **Step 4: Commit**

```bash
git add scripts/make_fixtures.py tests/fixtures/pdf tests/golden
git commit -m "pdf fixtures and golden: columns, passwords, scan"
```

---

## Отклонения от спеки (нумерация сквозная; за M3 — 17)

- **18.** `compute_metrics(chapters, ctx, rendered)` — третий аргумент против сигнатуры §3.3: финальный Markdown рендерится в pipeline один раз и переиспользуется для токенов и метрик (иначе двойной рендер каждой главы).
- **19.** `passes/pdf_layout` импортирует `extractors/textrules` (P5.5, P6): textrules — модуль общих правил текста, а не экстрактор; правило §3.3 «проходы не знают об экстракторах» трактуем как запрет на классы-экстракторы.
- **20.** Критерий P5 «заголовок ≤ 2 строк»: экстрактор склеивает строки блока (§6.7.3), поэтому число строк до склейки кодируется в `Block.origin = "pdf:N"` и читается проходом.
- **21.** PDF-фикстуры недетерминированы при генерации (pymupdf пишет случайный /ID): фикстуры коммитятся байтами один раз; `make_fixtures.py` их перезаписывает только осознанно (с регенерацией golden).
- **25.** P1 пропускает кандидата-«номер страницы», если его кегль ≥ `heading_size_ratio·B`: крупная римская цифра у верха страницы — вероятный номер главы, спека §7.2 P1 этот случай не оговаривает, а потеря случилась бы ДО P5 и была бы невосстановима (риск-находка ревью).
- **26.** P6 склеивает последний PARA страницы только со СЛЕДУЮЩИМ БЛОКОМ порядка чтения (PARA более поздней страницы), после склейки блоку присваиваются страница и bbox хвоста: буквальное «первый блок следующей страницы» из спеки рвало цепочки 3+ страниц, страницы-иллюстрации и сшивало текст через заголовок (риск-находка ревью).
- **27.** P5.6 не сливает два подряд HEADING, если ОБЕ строки по отдельности — полноценные заголовки по паттернам 6.1.3: чисто геометрический критерий спеки схлопывал две разные короткие главы на одной странице в «Chapter 1 Chapter 2» с потерей границы главы (риск-находка ревью, воспроизведено). Цена: caps-перенос, где обе половины сами матчатся паттернами, останется двумя заголовками — осознанный трейд-офф в пользу сохранения границ.
- **28.** P6 пропускает кандидата, похожего на сноску (кегль < `footnote_size_ratio·B`, подвал `footnote_zone`): P6 идёт до P7 по фиксированному порядку §7, и без guard'а сноска в конце страницы срасталась с телом следующей (риск-находка ревью, воспроизведено).
- **17 — снято:** `unknown_tags` в report.json теперь безусловный (полная схема §11.6).
- **30.** `_DIGIT = re.compile(r"\d+")` (вся последовательность цифр → один `#`) вместо вербатимного `r"\d"`: при `r"\d"` подписи `стр. 1`..`стр. 9` → `voyage log · стр. #`, а `стр. 10` → `voyage log · стр. ##` (две решётки) — два разных кластера P2, и `стр. 10` (1 страница < threshold=5) выживает, что ломает вербатим-тест `test_p2_frequent_running_header_removed`. Воспроизведено эмпирически (judge подтвердил: `r"\d"` даёт `{...стр. #: 9, ...стр. ##: 1}`, `r"\d+"` даёт единый кластер из 10). Фикс `\d+` — точечный, влияет только на кластеризацию цифровых последовательностей в `_signature()` (P2); P1/P3/P4 не затронуты (`_DIGIT` используется только в `_signature`).
- **31.** Две копипастных ошибки в вербатим-`p5_headings`/`_merge_split_headings` (Task 3), каждая ломала вербатим-тесты — исправлено эмпирически, тесты и остальная логика не правлены:
  (a) Внутренний guard-цикл классификации содержал `if b.kind is BlockKind.PARA or b.font_size is None: continue` — инверсия: PARA-блоки (как раз мишени классификации) пропускались, ни один блок не становился HEADING по размеру → 5 P5-тестов падали (`heads == {}`). Должно быть `if b.kind is not BlockKind.PARA or b.font_size is None:`.
  (b) Порог слияния в `_merge_split_headings` был `gap < 1.5 * line_h` (§7.2 P5.6) — слишком широкий: в `test_p5_rejects_long_and_punctuated` «Настоящий»/«Второй настоящий» (обе 16pt lvl1, та же страница, gap=20=line_h, ни одна не матчится паттернам 6.1.3 → guard откл. 27 не блокирует) ложно сливались в «Настоящий Второй настоящий». Анализ геометрии всех 3 случаев: настоящий перенос верстки (`test_p5_multiline_heading_merged`) даёт gap=2 (плотнее высоты строки); две разные главы — gap ≥ line_h. Фикс: порог `gap < line_h` (строки одного заголовка идут плотнее высоты строки). Проверено: multiline_merged (gap=2<20 → слить), rejects (gap=20 ≮ 20 → не слить), two_distinct (gap=10<20, но обе матчатся паттернам → guard откл. 27 блокирует, как и задумано).
- **32.** Удлинение фикстуры `ROMAN` в `scripts/make_fixtures.py` (Task 4): полные формулы quality (§11.6) честно давали coverage 1.0369 > 1.02 у крошечных cp1251/koi8 фикстур (ref_text 217 токенов, рендер с заголовками `# Том`/`# Глава` чуть больше → coverage >1.02 → триггер → review). План Task 4 Step 4 прямо предусматривает этот случай: «Если какая-то книга сползла в review из-за coverage > 1.02 (маленькие фикстуры) — удлинить тексты фикстуры и перегенерировать; формулы не подгонять». Каждой из 4 глав ROMAN добавлены содержательные абзацы (~120–180 токенов/глава; median > 300). После регенерации: coverage koi8/roman_cp1251 = 1.0063, статус ok, score 1.0. Книги с неизменными фикстурами: `.md` байт-идентичны, дрейф только в report.json (новая схема) + book.json provenance (version 2.2→2.3, cache_key) + index.json. Сопутствующее: удлинена синтетическая `BOOK` в `tests/unit/test_pipeline.py` (та же причина, coverage 1.022 → 1.0). `test_cache.py` оставлен строгим (`status == "ok"`): игрок релаксировал его до `in ("ok","review")` — это была подгонка теста под дефект фикстуры, откачено orchestrator'ом, фикстура удлинена вместо этого.
- **33.** Геометрия `kolonki3.pdf` в `scripts/make_fixtures.py` (Task 6): вербатим-блок `_tb(page, x, y, 160, 170, _PDFP * 2)` (420 символов при fontsize=10) давал отрицательный return-code -11.61 от `page.insert_textbox` (текст физически не влезал в прямоугольник 160×170) → pymupdf НЕ вставлял текст → `page.get_text("text")` давал только заголовок «Chapter 1» (10 симв.) → медиана текста по 6 страницам = 0 < `scan_chars_per_page=20` → `ScanError` → failed «скан». Воспроизведено эмпирически (orchestrator): вербатим page text lens `[10,0,0,0,0,0]`, median=0. Это баг ГЕОМЕТРИИ ФИКСТУРЫ, не экстрактора/проходов (сканер честно детектирует отсутствие текстового слоя; P1–P7/quality не виноваты). Фикс: прямоугольник `170×180`, 3 ряда `y=(100,300,500)` вместо 4 `y=(100,280,460,640)` (3 ряда без наложения). После фикса: page text lens median=3780, x-центры блоков кластеризуются в 3 колонки (119/299/479) на всех 6 страницах → `multi_column_pages=[1..6]` → `layout_flag=True` → review ровно по С-11 «многоколоночная вёрстка (3+ колонки)…», «Chapter 1» найдена паттерном (structure=1.0, НЕ fallback), coverage 0.8481. Фикс изолирован в `make_fixtures.py` (только kolonki3-блок), экстрактор/проходы/формулы/спека НЕ тронуты.

Новые отклонения при исполнении — сюда, номера 34+ (22–24 занял план M5, 25–33 добавило ревью планов/исполнение, 29 — ревью M5).

## Self-Review (выполнено при написании плана)

1. **Покрытие §18 M4:** pdf-экстрактор — T1; P1–P7 с multi-column-флагом — T2/T3; полный quality 11.1–11.6 — T4; report.json — T4; doctor — T5; EncryptedError/ScanError — T1; golden двух-/трёхколоночного и пустого пароля, скан → failed — T6. ✓
2. **Placeholder-скан:** каждый шаг с кодом/командами; «поправь тест» в T4 Step 1 сопровождён точным расчётом. ✓
3. **Типы согласованы:** `origin="pdf:N"` пишет T1, читает T3; `ReportDraft.pages_flagged/multi_column_pages` создаёт T2, читает T4; `Metrics.layout_flag` создаёт T4-compute, читает T4-score; `apply_patterns_to_blocks` — из M3 Task 1. ✓
