# Librarian M1 «каркас» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Рабочий офлайн-CLI `lib`: `lib ingest роман.txt && lib get <id> 1-3` — конвейер TXT/MD → библиотека Markdown-глав с каталогом, по спеке `librarian-spec-v2.2.md` (этап M1 из §18).

**Architecture:** Однонаправленный конвейер `DETECT → EXTRACT → NORMALIZE → STRUCTURE → REFINE → VALIDATE → EMIT` (§3.1). Модули общаются только через IR (§4); зависимости строго вниз: `cli → pipeline → (detect, extractors, passes, structure, quality, emit, catalog) → ir, config, errors, xmlsafe`. Запись — атомарный протокол staging → trash → replace с recovery и lock (§12.4).

**Tech Stack:** Python ≥ 3.11, uv (lock — часть контракта детерминизма), hatchling, typer, rich, charset-normalizer, tiktoken (вендоренный `o200k_base`), lxml (только фабрика xmlsafe в M1), pytest.

**Скоуп:** только M1 (§18). Вне скоупа M1: FB2/EPUB/DOCX/HTML/PDF-экстракторы, R1–R2, полный quality (coverage/garbage/encoding/dehyphen), `doctor`, `--budget`, `reingest`, лимиты/таймауты экстракции (поля в конфиге есть, enforcement — M2/M5). M2–M5 — отдельными планами.

## Global Constraints

Скопировано из спеки, действует для **каждой** задачи:

- **Детерминизм (§2):** запрещены `random`, `uuid4`, wall-clock (кроме `provenance.ingested_at`), любой сетевой I/O, итерация по `set`/`dict` без `sorted(...)`, локале-зависимые операции. Регистронезависимость — только `str.casefold()`, сортировка — по кодпоинтам.
- **`ingested_at`** — из `SOURCE_DATE_EPOCH`, если задана, иначе системные часы; UTC, ISO 8601 без миллисекунд. Единственное недетерминированное поле.
- **Канон сериализации (§12.2):** JSON — `json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)` + `"\n"`. Все текстовые файлы: UTF-8, NFC, LF, без хвостовых пробелов, один завершающий `\n`.
- **`PIPELINE_VERSION = "2.2"`** — строковая константа в `librarian/__init__.py`; bump при любом изменении выходных байт.
- **Правило чистки (v1-6.3):** удалять можно только порождённое форматом, не автором. Никаких исправлений опечаток/типографики.
- **Ошибки — по-русски, человеческим языком** (§11.5, §16).
- **Python ≥ 3.11**; запись текстов: `write_text(..., encoding="utf-8", newline="\n")`.
- **Коммиты:** короткие, lowercase, без префиксов `feat:`/`fix:`, без Co-Authored-By (правило пользователя, переопределяет шаблоны скилла).
- Тесты не ходят в сеть. Рабочая директория проекта: `/Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian/`.

---

## File Structure (итог M1)

```
librarian/
  pyproject.toml            # deps (все из §19 — lock сразу фиксирует контракт), lib = librarian.cli:app
  uv.lock
  .gitignore
  scripts/
    vendor_tokenizer.py     # разовый, С СЕТЬЮ (dev-time): скачать и вшить o200k_base
    make_fixtures.py        # генерация cp1251/koi8-r фикстур
    update_golden.py        # регенерация tests/golden/*
    smoke_wheel.sh          # wheel → чистый venv → lib работает
  src/librarian/
    __init__.py             # PIPELINE_VERSION = "2.2"
    __main__.py             # python -m librarian (нужен тестам с PYTHONHASHSEED)
    assets/o200k_base.tiktoken
    errors.py  ir.py  config.py  slug.py  tokens.py  detect.py  xmlsafe.py
    extractors/{__init__,base,textrules,txt,md}.py
    passes/{__init__,normalize,sections}.py
    structure.py  quality.py  emit.py  catalog.py  pipeline.py  cli.py
  tests/
    fixtures/{txt,md}/...
    golden/<fixture>/...    # эталонные библиотеки
    unit/test_*.py
    test_golden.py  test_determinism.py  test_cache.py  test_recovery.py  test_install.py
```

Один файл — одна ответственность (см. §3.3 спеки). Экстракторы не знают о проходах, проходы — об экстракторах.

---

### Task 1: Скелет проекта, errors, PIPELINE_VERSION

**Files:**
- Create: `librarian/pyproject.toml`, `librarian/.gitignore`, `librarian/src/librarian/__init__.py`, `librarian/src/librarian/errors.py`, `librarian/tests/unit/test_errors.py`
- Git: `git init` в `libby/` (репозитория ещё нет), спеки закоммитить первым коммитом

**Interfaces:**
- Produces: `librarian.PIPELINE_VERSION: str`; иерархия исключений §16: `LibError, DetectError, ExtractError(LibError), ScanError, EncryptedError, BrokenFileError, LimitError(ExtractError), UnknownBookError(LibError)`

- [ ] **Step 1: git init + скелет**

```bash
cd /Users/terobyte/Desktop/Projects/Active/scripts/libby
git init && git add librarian-spec-v2.1.md librarian-spec-v2.2.md docs/ && git commit -m "librarian specs v2.1 and v2.2"
mkdir -p librarian/src/librarian librarian/tests/unit librarian/scripts
```

- [ ] **Step 2: pyproject.toml** (все зависимости §19 сразу — uv.lock фиксирует контракт детерминизма с первого дня)

```toml
[project]
name = "librarian"
version = "0.1.0"
description = "Deterministic book-to-markdown pipeline for LLM consumption"
requires-python = ">=3.11"
dependencies = [
    "pymupdf>=1.24", "ebooklib>=0.18", "lxml>=5.0", "mammoth>=1.7",
    "trafilatura>=1.9", "charset-normalizer>=3.3", "tiktoken>=0.7",
    "typer>=0.12", "rich>=13",
]

[project.scripts]
lib = "librarian.cli:app"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/librarian"]
# hatchling кладёт в wheel все файлы пакета, включая src/librarian/assets/* (К-4);
# гарантия проверяется smoke-тестом установки (Task 20), а не верой в дефолт.

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
__pycache__/
*.egg-info/
.venv/
dist/
library/
.pytest_cache/
```

- [ ] **Step 3: `src/librarian/__init__.py`**

```python
PIPELINE_VERSION = "2.2"
```

- [ ] **Step 4: тест на иерархию ошибок** — `tests/unit/test_errors.py`

```python
from librarian.errors import (LibError, DetectError, ExtractError, ScanError,
                              EncryptedError, BrokenFileError, LimitError, UnknownBookError)

def test_hierarchy():
    for exc in (ScanError, EncryptedError, BrokenFileError, LimitError):
        assert issubclass(exc, ExtractError)
    for exc in (DetectError, ExtractError, UnknownBookError):
        assert issubclass(exc, LibError)
```

Run: `uv run pytest tests/unit/test_errors.py -v` → FAIL (модуля нет).

- [ ] **Step 5: `src/librarian/errors.py`** — дословно §16

```python
class LibError(Exception): ...
class DetectError(LibError): ...          # неизвестный формат
class ExtractError(LibError): ...
class ScanError(ExtractError): ...        # PDF без текстового слоя
class EncryptedError(ExtractError): ...   # PDF под паролем (пустой пароль уже испробован)
class BrokenFileError(ExtractError): ...  # битый zip/xml, недекодируемый текст, zip-bomb
class LimitError(ExtractError): ...       # превышен лимит 6.0 (размер, таймаут)
class UnknownBookError(LibError): ...     # id не найден (get/info/rm)
```

- [ ] **Step 6:** `uv sync && uv run pytest -v` → PASS; `uv.lock` появился.
- [ ] **Step 7: Commit** — `git add librarian && git commit -m "librarian skeleton: pyproject, errors, pipeline version"`

---

### Task 2: ir.py — модель данных

**Files:**
- Create: `src/librarian/ir.py`, `tests/unit/test_ir.py`

**Interfaces:**
- Produces (§4 дословно + M1-дополнения): `Format(str, Enum)`, `BlockKind(str, Enum)`, `Block`, `Section`, `Chapter` (+поле `part: int | None = None` — для имён файлов `-pK`, см. R4), `RawDoc`, `ReportDraft`, `DocContext`, `BookMeta` (нужен emit и pipeline — живёт в ir, чтобы не было цикла импортов).

- [ ] **Step 1: тест** — `tests/unit/test_ir.py`

```python
from librarian.ir import Block, BlockKind, Chapter, Format, RawDoc, ReportDraft, DocContext

def test_block_defaults():
    b = Block(kind=BlockKind.PARA, text="hello")
    assert (b.level, b.page, b.bbox, b.font_size, b.bold, b.origin) == (None, None, None, None, False, "")

def test_chapter_defaults():
    c = Chapter(n=0, title="t", blocks=[])
    assert c.tokens == 0 and c.part is None

def test_format_values():
    assert Format.TXT.value == "txt" and Format.MD.value == "md"
```

Run: `uv run pytest tests/unit/test_ir.py -v` → FAIL.

- [ ] **Step 2: `src/librarian/ir.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Format(str, Enum):
    FB2 = "fb2"; EPUB = "epub"; DOCX = "docx"; HTML = "html"
    TXT = "txt"; MD = "md"; PDF = "pdf"


class BlockKind(str, Enum):
    HEADING = "heading"; PARA = "para"; QUOTE = "quote"
    LIST_ITEM = "list_item"; TABLE = "table"; FOOTNOTE = "footnote"
    CODE = "code"; META = "meta"


@dataclass
class Block:
    kind: BlockKind
    text: str                       # NFC после NORMALIZE; \n внутри блока допустим
    level: int | None = None        # heading: 1..4; после нарезки — относительный (1 = разрезной+1)
    page: int | None = None         # только PDF, 1-based
    bbox: tuple[float, float, float, float] | None = None
    font_size: float | None = None
    bold: bool = False
    origin: str = ""


@dataclass
class Section:
    title: str
    level: int                      # 0 — корень
    blocks: list[Block]
    children: list["Section"]


@dataclass
class Chapter:
    n: int
    title: str                      # заголовок-путь (8.4), возможно "(i/k)"
    blocks: list[Block]
    tokens: int = 0                 # финальное значение — по рендеру
    part: int | None = None         # номер части R4/8.5 → суффикс -pK в имени файла


@dataclass
class RawDoc:
    fmt: Format
    blocks: list[Block]
    title: str | None
    author: str | None
    lang: str | None
    ref_text: str                   # эталон coverage (11.1); в M1 не используется quality-заглушкой
    pages: int | None = None
    page_rects: list[tuple] | None = None


@dataclass
class ReportDraft:
    """Копилка вырезанного и флагов. Расширяется в M2/M4."""
    control_chars: int = 0
    oversize_blocks_split: int = 0
    structure_fallback: bool = False
    removed: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DocContext:
    fmt: Format
    cfg: "Config"                   # noqa: F821 — типовая ссылка, без импорта (нет цикла)
    raw: RawDoc
    report: ReportDraft


@dataclass
class BookMeta:
    """Всё, что нужно emit_book для book.json (12.5)."""
    id: str
    title: str
    author: str
    lang: str | None
    meta_locked: bool
    source_path: Path
    fmt: Format
    sha256: str
    config_hash: str
    cache_key: str
    status: str
    score: float
    keep_source: bool
```

- [ ] **Step 3:** `uv run pytest tests/unit/test_ir.py -v` → PASS.
- [ ] **Step 4: Commit** — `git commit -m "ir: blocks, sections, chapters, rawdoc"`

---

### Task 3: config.py — дефолты §14, TOML-оверлей, config_hash

**Files:**
- Create: `src/librarian/config.py`, `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Config` (вложенные dataclass-ы `general/limits/tokens/chapters/clean/pdf/quality/slug` + `keep_source: bool = True`), `load_config(path: Path | None = None, *, keep_source: bool = True) -> Config`, `config_hash(cfg: Config) -> str` (полный sha256-hex канонического JSON).
- Consumes: —

- [ ] **Step 1: тест**

```python
import dataclasses
from librarian.config import Config, config_hash, load_config

def test_defaults_match_spec():
    cfg = Config()
    assert cfg.chapters.max_tokens == 8000
    assert cfg.chapters.tiny_tokens == 30
    assert cfg.clean.keep_hyphen_suffixes == ("то", "либо", "нибудь", "ка", "таки")
    assert cfg.general.preface_title == "Начало"
    assert cfg.quality.weights == {"coverage": 0.30, "structure": 0.25,
                                   "garbage": 0.20, "encoding": 0.15, "dehyphen": 0.10}
    assert cfg.keep_source is True

def test_toml_overlay(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[chapters]\nmax_tokens = 4000\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.chapters.max_tokens == 4000
    assert cfg.chapters.tiny_tokens == 30          # остальное — дефолты

def test_hash_stable_and_sensitive(tmp_path):
    h1, h2 = config_hash(Config()), config_hash(Config())
    assert h1 == h2 and len(h1) == 64
    assert config_hash(load_config(None, keep_source=False)) != h1   # §13: keep_source входит в хэш
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/config.py`** — все значения дословно из §14

```python
from __future__ import annotations

import dataclasses
import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from librarian.errors import LibError


@dataclass(frozen=True)
class GeneralCfg:
    preface_title: str = "Начало"
    notes_chapter_title: str = "Примечания"
    lock_timeout_s: int = 30


@dataclass(frozen=True)
class LimitsCfg:
    max_source_mb: int = 256
    zip_max_uncompressed_mb: int = 512
    zip_ratio_max: int = 100
    extract_timeout_s: int = 120


@dataclass(frozen=True)
class TokensCfg:
    encoding: str = "o200k_base"


def _default_patterns() -> dict[str, tuple[str, ...]]:
    tail = r"([.:—\-]\s*.{0,80})?$"
    return {
        "rank1": (r"^(том|книга|book|volume)\s+([0-9ivxlc]+|[а-яёa-z]+)" + tail,),
        "rank2": (r"^(часть|part|раздел)\s+([0-9ivxlc]+|[а-яёa-z]+)" + tail,),
        "rank3": (r"^(глава|chapter)\s+([0-9ivxlc]+|[а-яёa-z]+)" + tail,
                  r"^([0-9]{1,4}|[IVXLC]{1,7})\.?$"),
    }


@dataclass(frozen=True)
class ChaptersCfg:
    cut_level_start: int = 2
    deepen_median: int = 12000
    shallow_median: int = 500
    max_tokens: int = 8000
    part_target_tokens: int = 6000
    fallback_part_tokens: int = 6000
    tiny_tokens: int = 30
    patterns: dict[str, tuple[str, ...]] = field(default_factory=_default_patterns)


@dataclass(frozen=True)
class CleanCfg:
    meta_max_tokens: int = 150
    meta_markers: tuple[str, ...] = ("ISBN", "©", "Все права защищены",
                                     "All rights reserved", "Литагент")
    toc_numeric_line_ratio: float = 0.60
    toc_heading_dup_ratio: float = 0.80
    toc_max_tokens: int = 2000
    keep_hyphen_suffixes: tuple[str, ...] = ("то", "либо", "нибудь", "ка", "таки")


@dataclass(frozen=True)
class PdfCfg:
    scan_chars_per_page: int = 20
    size_round: float = 0.5
    hf_zone: float = 0.10
    hf_page_ratio: float = 0.30
    hf_min_pages: int = 5
    pagenum_max_chars: int = 4
    column_gap_ratio: float = 0.15
    column_min_share: float = 0.25
    multi_column_page_ratio: float = 0.10
    heading_size_ratio: float = 1.15
    heading_max_levels: int = 3
    heading_max_chars: int = 120
    bold_heading_max_chars: int = 60
    footnote_size_ratio: float = 0.85
    footnote_zone: float = 0.33
    footnotes: str = "keep"
    defect_char_ratio: float = 0.02


def _default_weights() -> dict[str, float]:
    return {"coverage": 0.30, "structure": 0.25, "garbage": 0.20,
            "encoding": 0.15, "dehyphen": 0.10}


@dataclass(frozen=True)
class QualityCfg:
    mojibake_markers: tuple[str, ...] = ("Ð", "Ñ", "Ã", "â€", "пїЅ")
    weights: dict[str, float] = field(default_factory=_default_weights)
    ok_min: float = 0.90
    failed_max: float = 0.60
    coverage_points: tuple[float, ...] = (0.40, 0.70, 1.02, 1.15)
    coverage_review: tuple[float, ...] = (0.60, 1.02)
    garbage: dict[str, float] = field(default_factory=lambda: {"full": 0.005, "zero": 0.05, "review": 0.02})
    encoding: dict[str, float] = field(default_factory=lambda: {"full": 0.0, "zero": 0.02, "review": 0.005})
    dehyphen: dict[str, float] = field(default_factory=lambda: {"full": 0.002, "zero": 0.03, "review": 0.01})


@dataclass(frozen=True)
class SlugCfg:
    max_len: int = 60
    chapter_len: int = 50


@dataclass(frozen=True)
class Config:
    general: GeneralCfg = field(default_factory=GeneralCfg)
    limits: LimitsCfg = field(default_factory=LimitsCfg)
    tokens: TokensCfg = field(default_factory=TokensCfg)
    chapters: ChaptersCfg = field(default_factory=ChaptersCfg)
    clean: CleanCfg = field(default_factory=CleanCfg)
    pdf: PdfCfg = field(default_factory=PdfCfg)
    quality: QualityCfg = field(default_factory=QualityCfg)
    slug: SlugCfg = field(default_factory=SlugCfg)
    keep_source: bool = True        # §13: --no-keep-source → False, входит в config_hash


_SECTIONS = {"general": GeneralCfg, "limits": LimitsCfg, "tokens": TokensCfg,
             "chapters": ChaptersCfg, "clean": CleanCfg, "pdf": PdfCfg,
             "quality": QualityCfg, "slug": SlugCfg}

# TOML §14 кладёт status/subscore-точки во вложенные таблицы — маппинг в плоские поля:
_QUALITY_TABLES = {"status": {"ok_min": "ok_min", "failed_max": "failed_max"},
                   "coverage": {"points": "coverage_points", "review": "coverage_review"}}


def load_config(path: Path | None = None, *, keep_source: bool = True) -> Config:
    overrides: dict = {}
    if path is not None:
        overrides = tomllib.loads(path.read_text(encoding="utf-8"))
    kwargs: dict = {"keep_source": keep_source}
    for name, cls in sorted(_SECTIONS.items()):
        section = dict(overrides.get(name, {}))
        if name == "quality":
            for table, mapping in _QUALITY_TABLES.items():
                for toml_key, attr in mapping.items():
                    if table in section and toml_key in section[table]:
                        section[attr] = section[table][toml_key]
                section.pop(table, None)
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(section) - known)
        if unknown:
            raise LibError(f"неизвестные ключи в [{name}]: {', '.join(unknown)}")
        # tuple-поля: TOML отдаёт list — приводим для frozen-каноничности
        for f in dataclasses.fields(cls):
            if f.name in section and isinstance(section[f.name], list):
                section[f.name] = tuple(section[f.name])
            if f.name == "patterns" and f.name in section:
                section[f.name] = {k: tuple(v) for k, v in sorted(section[f.name].items())}
        kwargs[name] = cls(**section)
    return Config(**kwargs)


def config_hash(cfg: Config) -> str:
    payload = json.dumps(dataclasses.asdict(cfg), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 3:** `uv run pytest tests/unit/test_config.py -v` → PASS.
- [ ] **Step 4: Commit** — `git commit -m "config: spec defaults, toml overlay, config hash"`

---

### Task 4: slug.py — транслит, slugify, make_id

**Files:**
- Create: `src/librarian/slug.py`, `tests/unit/test_slug.py`

**Interfaces:**
- Produces: `slugify(s: str, max_len: int) -> str`; `make_id(title: str | None, author: str | None, source_stem: str, max_len: int) -> str` — базовый id **без** коллизионного суффикса (суффикс `-{sha[:6]}` вешает pipeline, Task 17: правило требует знать ФС; slug.py остаётся чистой функцией — осознанное отклонение от `make_id(meta, sha)` §3.3).

- [ ] **Step 1: тест** — кейсы §12.1 + фикс 0.16 (заглавная кириллица) + М-минор «висячий дефис»

```python
from librarian.slug import make_id, slugify

def test_translit_casefold_order():
    assert slugify("Война и Мир", 60) == "voyna-i-mir"      # 0.16: NFC → casefold → транслит
    assert slugify("Щёлкин съел объём", 60) == "schelkin-sel-obem"

def test_specials_collapse():
    assert slugify("a---b  c!!!", 60) == "a-b-c"
    assert slugify("«Привет»", 60) == "privet"

def test_truncate_on_dash_no_hanging():
    assert slugify("aaa-bbb-ccc", 7) == "aaa-bbb"            # усечение по границе -
    assert slugify("aaaaaaaaaa", 5) == "aaaaa"               # нет дефиса — жёсткий срез
    assert not slugify("aaa-bbb", 4).endswith("-")           # висячего дефиса нет

def test_empty_fallback():
    assert slugify("!!!", 60) == "text"

def test_make_id():
    assert make_id("Война и мир", "Лев Толстой", "voyna", 60) == "lev-tolstoy-voyna-i-mir"
    assert make_id(None, None, "Мой Файл", 60) == "moy-fayl"  # нет меты — слаг имени файла
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/slug.py`**

```python
from __future__ import annotations

import re
import unicodedata

# §12.1: фиксированная таблица, не внешняя библиотека
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(s: str, max_len: int) -> str:
    s = unicodedata.normalize("NFC", s).casefold()
    s = "".join(_TRANSLIT.get(ch, ch) for ch in s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > max_len:
        cut = s.rfind("-", 1, max_len + 1)
        s = s[:cut] if cut > 0 else s[:max_len]
        s = s.strip("-")
    return s or "text"


def make_id(title: str | None, author: str | None, source_stem: str, max_len: int) -> str:
    base = " ".join(p for p in (author, title) if p)
    return slugify(base or source_stem, max_len)
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "slug: translit table, slugify, make_id"`

---

### Task 5: tokens.py — вендоренный o200k_base, офлайн-энкодер

**Files:**
- Create: `scripts/vendor_tokenizer.py`, `src/librarian/assets/o200k_base.tiktoken`, `src/librarian/tokens.py`, `tests/unit/test_tokens.py`

**Interfaces:**
- Produces: `count(text: str) -> int` (финальный подсчёт), `draft_count(blocks: list[Block]) -> int` (черновой: тексты через `\n\n`, §10), `block_tokens(b: Block) -> int`.

- [ ] **Step 1: вендоринг (разовый, с сетью — dev-time, НЕ рантайм)** — `scripts/vendor_tokenizer.py`

```python
"""Разовый скрипт: скачивает o200k_base через tiktoken и вшивает в пакет.
Запуск: uv run python scripts/vendor_tokenizer.py  (нужна сеть)."""
import base64
import hashlib
from pathlib import Path

import tiktoken

enc = tiktoken.get_encoding("o200k_base")          # сеть — только здесь
lines = b"".join(
    base64.b64encode(tok) + b" " + str(rank).encode() + b"\n"
    for tok, rank in sorted(enc._mergeable_ranks.items(), key=lambda kv: kv[1])
)
out = Path(__file__).parent.parent / "src" / "librarian" / "assets" / "o200k_base.tiktoken"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(lines)
print("sha256 =", hashlib.sha256(lines).hexdigest())
print("pat_str =", enc._pat_str)
print("special_tokens =", enc._special_tokens)
```

Run: `uv run python scripts/vendor_tokenizer.py`. **Скопировать напечатанные sha256 / pat_str / special_tokens в константы Step 3** (К-3: BPE-файла одного недостаточно).

- [ ] **Step 2: тест**

```python
import pytest
from librarian import tokens
from librarian.errors import LibError
from librarian.ir import Block, BlockKind

def test_count_basic():
    assert tokens.count("") == 0
    assert tokens.count("Война и мир") > 0
    assert tokens.count("a" * 1000) < 1000          # BPE сжимает

def test_draft_count_joins():
    blocks = [Block(BlockKind.PARA, "раз"), Block(BlockKind.PARA, "два")]
    assert tokens.draft_count(blocks) == tokens.count("раз\n\nдва")

def test_special_tokens_are_plain_text():
    # пользовательский текст со спецтокеном не должен ронять подсчёт
    assert tokens.count("<|endoftext|>") > 0

def test_corrupt_asset(monkeypatch):
    tokens._encoder.cache_clear()
    monkeypatch.setattr(tokens, "_read_asset", lambda: b"broken")
    with pytest.raises(LibError):
        tokens.count("x")
    tokens._encoder.cache_clear()
```

Run → FAIL.

- [ ] **Step 3: `src/librarian/tokens.py`**

```python
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from importlib import resources

import tiktoken

from librarian.errors import LibError
from librarian.ir import Block

_ASSET = "o200k_base.tiktoken"
# ↓↓↓ значения — из вывода scripts/vendor_tokenizer.py (Step 1), не выдумывать ↓↓↓
_ASSET_SHA256 = "<вставить sha256 из вывода вендоринга>"
_PAT_STR = "<вставить pat_str из вывода вендоринга>"
_SPECIAL_TOKENS = {"<|endoftext|>": 199999, "<|endofprompt|>": 200018}  # сверить с выводом


def _read_asset() -> bytes:
    return resources.files("librarian.assets").joinpath(_ASSET).read_bytes()


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    data = _read_asset()
    if hashlib.sha256(data).hexdigest() != _ASSET_SHA256:
        raise LibError("повреждён словарь токенизатора")
    ranks = {
        base64.b64decode(tok): int(rank)
        for tok, rank in (line.split() for line in data.splitlines() if line)
    }
    return tiktoken.Encoding(name="o200k_base", pat_str=_PAT_STR,
                             mergeable_ranks=ranks, special_tokens=_SPECIAL_TOKENS)


def count(text: str) -> int:
    return len(_encoder().encode(text, disallowed_special=()))


def block_tokens(b: Block) -> int:
    return count(b.text)


def draft_count(blocks: list[Block]) -> int:
    return count("\n\n".join(b.text for b in blocks))
```

`src/librarian/assets/__init__.py` не нужен (`importlib.resources.files` работает с namespace-пакетом), но hatchling надёжнее с пустым `__init__.py` — создать его.

- [ ] **Step 4:** PASS. Проверить офлайн: `uv run python -c "import librarian.tokens as t; print(t.count('тест'))"` при выключенной сети (или `--offline`-прокси) — сетевых запросов нет.
- [ ] **Step 5: Commit** — `git commit -m "tokens: vendored o200k_base, offline encoder, sha256 check"` (ассет коммитится в git).

---

### Task 6: detect.py — форматы по магическим байтам

**Files:**
- Create: `src/librarian/detect.py`, `tests/unit/test_detect.py`

**Interfaces:**
- Produces: `detect(path: Path) -> Format` — таблица §5 сверху вниз, сниффер значимого тега, правило текстовости 5.1.

- [ ] **Step 1: тест** — синтетические файлы всех веток

```python
import zipfile
import pytest
from librarian.detect import detect
from librarian.errors import BrokenFileError, DetectError
from librarian.ir import Format

def _zip(tmp_path, name, entries):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        for arcname, data in entries:
            z.writestr(arcname, data)
    return p

def test_pdf(tmp_path):
    p = tmp_path / "x.bin"; p.write_bytes(b"%PDF-1.7 rest")
    assert detect(p) is Format.PDF

def test_epub(tmp_path):
    p = _zip(tmp_path, "b.epub", [("mimetype", "application/epub+zip"), ("x.xhtml", "<html/>")])
    assert detect(p) is Format.EPUB

def test_docx(tmp_path):
    p = _zip(tmp_path, "d.docx", [("word/document.xml", "<w:document/>")])
    assert detect(p) is Format.DOCX

def test_fb2_zip(tmp_path):
    p = _zip(tmp_path, "b.fb2.zip", [("book.fb2", "<FictionBook/>"), ("cover.jpg", "xx")])
    assert detect(p) is Format.FB2

def test_fb2_zip_two_fb2_is_error(tmp_path):
    p = _zip(tmp_path, "b.zip", [("a.fb2", "x"), ("b.fb2", "y")])
    with pytest.raises(DetectError):
        detect(p)

def test_zip_other_is_error(tmp_path):
    with pytest.raises(DetectError):
        detect(_zip(tmp_path, "z.zip", [("data.txt", "hi")]))

def test_fb2_xml_with_comment_and_decl(tmp_path):
    p = tmp_path / "b.fb2"
    p.write_text('<?xml version="1.0"?>\n<!-- к -->\n<FictionBook xmlns="...">', encoding="utf-8")
    assert detect(p) is Format.FB2

def test_html_xhtml(tmp_path):
    p = tmp_path / "a.html"
    p.write_text("﻿  <!-- x --><!DOCTYPE HTML><html>", encoding="utf-8")
    assert detect(p) is Format.HTML

def test_md_by_extension(tmp_path):
    p = tmp_path / "note.md"; p.write_text("# Hi", encoding="utf-8")
    assert detect(p) is Format.MD

def test_txt_cp1251(tmp_path):
    p = tmp_path / "т.txt"; p.write_bytes("Глава первая. Проза.".encode("cp1251"))
    assert detect(p) is Format.TXT

def test_binary_is_detect_error(tmp_path):
    p = tmp_path / "x.dat"; p.write_bytes(bytes(range(256)) * 8)
    with pytest.raises(DetectError):
        detect(p)

def test_broken_zip(tmp_path):
    p = tmp_path / "x.epub"; p.write_bytes(b"PK\x03\x04" + b"\x00" * 30)
    with pytest.raises(BrokenFileError):
        detect(p)
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/detect.py`**

```python
from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path

import charset_normalizer

from librarian.errors import BrokenFileError, DetectError
from librarian.ir import Format

_SKIP = re.compile(r"^(?:\s+|<\?.*?\?>|<!--.*?-->)", re.S)


def detect(path: Path) -> Format:
    head = path.open("rb").read(1024)
    if b"%PDF" in head:
        return Format.PDF
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return _detect_zip(path)
    tag = _first_significant_tag(path)
    if tag.startswith("<FictionBook"):
        return Format.FB2
    if tag.casefold().startswith(("<!doctype html", "<html")):
        return Format.HTML
    if path.suffix.casefold() in (".md", ".markdown") and _is_texty(path):
        return Format.MD
    if _is_texty(path):
        return Format.TXT
    raise DetectError(f"{path.name}: неизвестный формат")


def _detect_zip(path: Path) -> Format:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if any(zi.flag_bits & 0x1 for zi in z.infolist()):
                raise BrokenFileError(f"{path.name}: зашифрованный zip")
            if "mimetype" in names and z.read("mimetype").strip() == b"application/epub+zip":
                return Format.EPUB
            if "word/document.xml" in names:            # именно запись-файл
                return Format.DOCX
            fb2 = [n for n in names if n.casefold().endswith(".fb2") and not n.endswith("/")]
            if len(fb2) == 1:
                return Format.FB2
            if len(fb2) >= 2:
                raise DetectError(f"{path.name}: в архиве несколько .fb2")
            raise DetectError(f"{path.name}: zip неизвестного назначения")
    except zipfile.BadZipFile as e:
        raise BrokenFileError(f"{path.name}: битый zip: {e}") from None


def _first_significant_tag(path: Path) -> str:
    data = path.open("rb").read(4096)
    if data.startswith(b"\xef\xbb\xbf"):
        text = data[3:].decode("utf-8", errors="replace")
    elif data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace")
    else:
        best = charset_normalizer.from_bytes(data).best()
        text = str(best) if best else data.decode("latin-1")
    i = 0
    while True:
        m = _SKIP.match(text, i)
        if not m or m.end() == i:
            break
        i = m.end()
    return text[i:i + 64]


def _is_texty(path: Path) -> bool:
    """5.1: уверенность ≥ 0.5 (chaos ≤ 0.5) и управляющих (кроме \\n\\r\\t) < 1%."""
    best = charset_normalizer.from_path(path).best()
    if best is None or best.chaos > 0.5:
        return False
    text = str(best)
    if not text:
        return True
    ctrl = sum(1 for ch in text
               if unicodedata.category(ch) == "Cc" and ch not in "\n\r\t")
    return ctrl / len(text) < 0.01
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "detect: magic bytes, zip dispatch, tag sniffer"`

---

### Task 7: xmlsafe.py — харднинг lxml + grep-тест CI

**Files:**
- Create: `src/librarian/xmlsafe.py`, `tests/unit/test_xmlsafe.py`

**Interfaces:**
- Produces: `xml_parser() -> etree.XMLParser`, `html_parser() -> etree.HTMLParser`, `parse_xml(data: bytes) -> etree._Element`. В M1 боевых потребителей нет (FB2/EPUB — M2), но модуль и grep-тест ставятся сейчас, чтобы запрет действовал с первого экстрактора (К-2).

- [ ] **Step 1: тест** — XXE не разворачивается + grep-запрет

```python
import re
from pathlib import Path
from librarian.xmlsafe import parse_xml

_XXE = b"""<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<r>&xxe;</r>"""

def test_xxe_not_resolved():
    root = parse_xml(_XXE)
    assert (root.text or "").strip() == ""      # сущность не развёрнута

def test_no_raw_lxml_calls():
    src = Path(__file__).parents[2] / "src" / "librarian"
    pat = re.compile(r"\betree\.(parse|fromstring|XML|HTML)\s*\(")
    bad = [p.name for p in sorted(src.rglob("*.py"))
           if p.name != "xmlsafe.py" and pat.search(p.read_text(encoding="utf-8"))]
    assert bad == []
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/xmlsafe.py`** — единственная точка создания парсеров (§6.0)

```python
from __future__ import annotations

from lxml import etree


def xml_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True,
                           load_dtd=False, huge_tree=False)


def html_parser() -> etree.HTMLParser:
    return etree.HTMLParser(no_network=True, huge_tree=False)


def parse_xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, parser=xml_parser())
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "xmlsafe: hardened lxml factory, grep guard test"`

---

### Task 8: passes/normalize.py — N1–N3

**Files:**
- Create: `src/librarian/passes/__init__.py` (пустой), `src/librarian/passes/normalize.py`, `tests/unit/test_normalize.py`

**Interfaces:**
- Consumes: `Block`, `DocContext`.
- Produces: `n1_unicode`, `n2_whitespace`, `n3_controls` (каждый: `(list[Block], DocContext) -> list[Block]`, атрибут `name`), `COMMON_PASSES`, `apply_block_passes(blocks, ctx) -> list[Block]` (общие проходы; PDF-проходы добавятся в M4).

- [ ] **Step 1: тест**

```python
from librarian.config import Config
from librarian.ir import Block, BlockKind, DocContext, Format, RawDoc, ReportDraft
from librarian.passes.normalize import apply_block_passes, n1_unicode, n2_whitespace, n3_controls

def _ctx():
    raw = RawDoc(Format.TXT, [], None, None, None, "")
    return DocContext(Format.TXT, Config(), raw, ReportDraft())

def test_n1_removes_invisibles_and_nfc():
    b = [Block(BlockKind.PARA, "ку­да​-то\r\nтуда\rвот﻿")]
    out = n1_unicode(b, _ctx())
    assert out[0].text == "куда-то\nтуда\nвот"

def test_n2_collapses_spaces_keeps_code():
    ctx = _ctx()
    out = n2_whitespace([Block(BlockKind.PARA, "a   b\t\tc  \n\n\n\nd  "),
                         Block(BlockKind.CODE, "x\t\ty"),
                         Block(BlockKind.PARA, "   ")], ctx)
    assert out[0].text == "a b c\n\nd"
    assert out[1].text == "x\t\ty"                    # CODE не трогаем
    assert len(out) == 2                              # пустой блок удалён

def test_n3_counts_controls():
    ctx = _ctx()
    out = n3_controls([Block(BlockKind.PARA, "a\x01b\x9cc\nd\te")], ctx)
    assert out[0].text == "abc\nd\te"
    assert ctx.report.control_chars == 2

def test_idempotent():
    ctx = _ctx()
    blocks = [Block(BlockKind.PARA, "a  b­\r\nc\x01")]
    once = apply_block_passes(blocks, ctx)
    twice = apply_block_passes([Block(b.kind, b.text) for b in once], ctx)
    assert [b.text for b in once] == [b.text for b in twice]
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/passes/normalize.py`**

```python
from __future__ import annotations

import re
import unicodedata

from librarian.ir import Block, BlockKind, DocContext

_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"))
_MULTISPACE = re.compile(r"[ \t]+")
_MULTIBREAK = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")  # C0/C1 кроме \n\t


def n1_unicode(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for b in blocks:
        t = unicodedata.normalize("NFC", b.text)
        t = t.translate(_INVISIBLE)
        b.text = t.replace("\r\n", "\n").replace("\r", "\n")
    return blocks
n1_unicode.name = "N1 unicode"


def n2_whitespace(blocks: list[Block], ctx: DocContext) -> list[Block]:
    out = []
    for b in blocks:
        if b.kind not in (BlockKind.CODE, BlockKind.TABLE):
            lines = [_MULTISPACE.sub(" ", ln).rstrip() for ln in b.text.split("\n")]
            b.text = _MULTIBREAK.sub("\n\n", "\n".join(lines)).strip("\n")
        if b.text.strip():
            out.append(b)
    return out
n2_whitespace.name = "N2 whitespace"


def n3_controls(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for b in blocks:
        cleaned, n = _CONTROL.subn("", b.text)
        ctx.report.control_chars += n
        b.text = cleaned
    return blocks
n3_controls.name = "N3 controls"


COMMON_PASSES = [n1_unicode, n2_whitespace, n3_controls]


def apply_block_passes(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for p in COMMON_PASSES:                 # M4 добавит PDF_PASSES при ctx.fmt is PDF
        blocks = p(blocks, ctx)
    return blocks
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "normalize passes n1-n3"`

---

### Task 9: extractors: base + textrules + TXT

**Files:**
- Create: `src/librarian/extractors/__init__.py`, `base.py`, `textrules.py`, `txt.py`; `tests/unit/test_textrules.py`, `tests/unit/test_txt.py`

**Interfaces:**
- Produces:
  - `base.py`: `class Extractor(Protocol): format: Format; def extract(self, path, cfg) -> RawDoc`; `EXTRACTORS: dict[Format, Extractor]`; `get_extractor(fmt) -> Extractor` (нет → `LibError("формат {fmt} будет поддержан в следующих этапах")`).
  - `textrules.py` (общие для TXT/MD, позже DOCX-fallback): `merge_lines(lines: list[str], cfg: Config) -> str` (склейка переносов 6.1.2), `line_rank(line: str, patterns) -> int | None`, `compile_patterns(cfg)`, `apply_heading_patterns(paras: list[tuple[str, bool]], cfg) -> list[Block]` — paras как `(текст, была_одной_строкой)`.
  - `txt.py`: `TxtExtractor` (format=TXT), регистрируется в `EXTRACTORS`.

- [ ] **Step 1: тест textrules** — правило переносов 0.24 и ранги 6.1.3

```python
from librarian.config import Config
from librarian.extractors.textrules import compile_patterns, line_rank, merge_lines

CFG = Config()

def test_merge_plain_hyphen():
    assert merge_lines(["нау-", "ка победила"], CFG) == "наука победила"

def test_merge_particle_keeps_hyphen():
    assert merge_lines(["кто-", "то пришёл"], CFG) == "кто-то пришёл"
    assert merge_lines(["как-", "нибудь потом"], CFG) == "как-нибудь потом"

def test_merge_capital_next_is_space_join():
    assert merge_lines(["тире-", "Москва"], CFG) == "тире- Москва"   # не строчная — не перенос

def test_merge_cross_alphabet_no_glue():
    assert merge_lines(["сло-", "world"], CFG) == "сло- world"       # разные алфавиты

def test_plain_join():
    assert merge_lines(["первая строка", "вторая строка"], CFG) == "первая строка вторая строка"

def test_ranks():
    pats = compile_patterns(CFG)
    assert line_rank("Том первый", pats) == 1
    assert line_rank("ЧАСТЬ ВТОРАЯ", pats) == 2
    assert line_rank("Глава 3. Встреча", pats) == 3
    assert line_rank("XIV.", pats) == 3
    assert line_rank("ЭПИЛОГ", pats) == 3            # caps-правило
    assert line_rank("Обычное предложение.", pats) is None
```

- [ ] **Step 2: тест TXT-экстрактора**

```python
from librarian.config import Config
from librarian.extractors.txt import TxtExtractor
from librarian.ir import BlockKind

BOOK = """Роман о жизни.

Том первый

Глава 1

Жил-был человек, который никог-
да не сдавался и шёл кто-
то знает куда.

Глава 2

Продолжение истории."""

def test_txt_structure(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes(BOOK.encode("cp1251"))             # кодировки — обязательный тест §6.1.1
    raw = TxtExtractor().extract(p, Config())
    kinds = [(b.kind, b.level) for b in raw.blocks]
    assert kinds == [(BlockKind.PARA, None), (BlockKind.HEADING, 1),
                     (BlockKind.HEADING, 2), (BlockKind.PARA, None),
                     (BlockKind.HEADING, 2), (BlockKind.PARA, None)]
    body = raw.blocks[3].text
    assert "никогда не сдавался" in body and "кто-то знает" in body
    assert raw.ref_text.startswith("Роман о жизни.")
    assert raw.title is None and raw.lang is None

def test_txt_koi8r(tmp_path):
    p = tmp_path / "k.txt"
    p.write_bytes("Глава 1\n\nТекст по-русски.".encode("koi8-r"))
    raw = TxtExtractor().extract(p, Config())
    assert raw.blocks[0].text == "Глава 1"

def test_txt_rank_compression(tmp_path):
    # только «Глава N» (ранг 3) → уровень 1
    p = tmp_path / "g.txt"
    p.write_text("Глава 1\n\nТекст.\n\nГлава 2\n\nЕщё.", encoding="utf-8")
    raw = TxtExtractor().extract(p, Config())
    assert [b.level for b in raw.blocks if b.kind is BlockKind.HEADING] == [1, 1]
```

Run → FAIL.

- [ ] **Step 3: реализация.** `base.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from librarian.config import Config
from librarian.errors import LibError
from librarian.ir import Format, RawDoc


class Extractor(Protocol):
    format: Format
    def extract(self, path: Path, cfg: Config) -> RawDoc: ...


EXTRACTORS: dict[Format, Extractor] = {}


def register(extractor: Extractor) -> None:
    EXTRACTORS[extractor.format] = extractor


def get_extractor(fmt: Format) -> Extractor:
    if fmt not in EXTRACTORS:
        raise LibError(f"формат {fmt.value} будет поддержан в следующих этапах")
    return EXTRACTORS[fmt]
```

`textrules.py`:

```python
from __future__ import annotations

import re

from librarian.config import Config
from librarian.ir import Block, BlockKind

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _alphabet(ch: str) -> str:
    ch = ch.casefold()
    if "а" <= ch <= "я" or ch == "ё":
        return "cyr"
    if ch.isascii() and ch.isalpha():
        return "lat"
    return "other"


def merge_lines(lines: list[str], cfg: Config) -> str:
    out = lines[0].strip()
    for raw_next in lines[1:]:
        nxt = raw_next.strip()
        if not nxt:
            continue
        hyphen_break = (
            len(out) >= 2 and out.endswith("-") and out[-2].isalpha()
            and nxt[0].isalpha() and nxt[0].islower()
            and _alphabet(out[-2]) == _alphabet(nxt[0])
        )
        if hyphen_break:
            m = _WORD.match(nxt)
            suffix = m.group(0) if m else ""
            if suffix in cfg.clean.keep_hyphen_suffixes:
                out += nxt                       # «кто-то»: дефис сохраняется
            else:
                out = out[:-1] + nxt             # обычный перенос
        else:
            out += " " + nxt
    return out


def compile_patterns(cfg: Config) -> dict[int, list[re.Pattern]]:
    return {rank: [re.compile(p, re.IGNORECASE)
                   for p in cfg.chapters.patterns.get(f"rank{rank}", ())]
            for rank in (1, 2, 3)}


def line_rank(line: str, patterns: dict[int, list[re.Pattern]]) -> int | None:
    for rank in (1, 2, 3):
        if any(p.fullmatch(line) for p in patterns[rank]):
            return rank
    letters = [c for c in line if c.isalpha()]
    if letters and len(line) <= 60 and not any(c.islower() for c in letters):
        return 3                                  # caps-правило 6.1.3 (в коде, не в конфиге)
    return None


def apply_heading_patterns(paras: list[tuple[str, bool]], cfg: Config) -> list[Block]:
    """paras: (текст-после-склейки, исходный-абзац-был-одной-строкой)."""
    patterns = compile_patterns(cfg)
    ranked: list[tuple[str, int | None]] = [
        (text, line_rank(text, patterns) if single else None)
        for text, single in paras
    ]
    present = sorted({r for _, r in ranked if r is not None})
    level_of = {r: i + 1 for i, r in enumerate(present)}   # сжатие рангов 6.1.3
    return [
        Block(BlockKind.HEADING, text, level=level_of[r], origin=f"pattern:rank{r}")
        if r is not None else Block(BlockKind.PARA, text)
        for text, r in ranked
    ]
```

`txt.py`:

```python
from __future__ import annotations

from pathlib import Path

import charset_normalizer

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.extractors.textrules import apply_heading_patterns, merge_lines
from librarian.ir import Format, RawDoc


class TxtExtractor:
    format = Format.TXT

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        best = charset_normalizer.from_path(path).best()
        if best is None:
            raise BrokenFileError(f"{path.name}: не удалось определить кодировку")
        text = str(best)
        paras: list[tuple[str, bool]] = []
        for chunk in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
            lines = [ln for ln in chunk.split("\n") if ln.strip()]
            if lines:
                paras.append((merge_lines(lines, cfg), len(lines) == 1))
        blocks = apply_heading_patterns(paras, cfg)
        return RawDoc(fmt=Format.TXT, blocks=blocks, title=None, author=None,
                      lang=None, ref_text=text)


base.register(TxtExtractor())
```

В `extractors/__init__.py` — импорт для регистрации:

```python
from librarian.extractors import txt  # noqa: F401  (регистрация в EXTRACTORS)
```

Примечание: разделитель абзацев «одна и более пустых строк» — сплит по `\n\n` после нормализации концов строк покрывает случай нескольких пустых строк (пустые куски отфильтровываются условием `if lines`).

- [ ] **Step 4:** PASS → **Commit** `git commit -m "txt extractor: encoding, hyphen merge, heading patterns"`

---

### Task 10: extractors/md.py — минимальный Markdown-парсер

**Files:**
- Create: `src/librarian/extractors/md.py`, `tests/unit/test_md.py`
- Modify: `src/librarian/extractors/__init__.py` (добавить `from librarian.extractors import md  # noqa: F401`)

**Interfaces:**
- Consumes: `merge_lines`, `apply_heading_patterns` из textrules.
- Produces: `MdExtractor` (format=MD). Правила 6.2 в порядке приоритета: front matter → fence → setext → ATX → thematic break → quote → list → PARA; инлайн-чистка ссылок/картинок/автоссылок на всех блоках, кроме CODE. Решение M1: если после разбора нет ни одного HEADING — применить паттерны 6.1.3 к PARA-блокам (таблица §6.0 относит 6.1.3 и к MD).

- [ ] **Step 1: тест**

```python
from librarian.config import Config
from librarian.extractors.md import MdExtractor
from librarian.ir import BlockKind

DOC = """---
title: тест
---
# Глава 1

Текст с [ссылкой](http://x) и ![картинкой](i.png) и <https://auto.link>.

Заголовок setext
================

подзаголовок
------------

```py
код  с   пробелами
```

> цитата
> вторая строка

- пункт один
- пункт два

***

##### мелкий
"""

def _extract(tmp_path, text):
    p = tmp_path / "d.md"
    p.write_text(text, encoding="utf-8")
    return MdExtractor().extract(p, Config())

def test_md_blocks(tmp_path):
    raw = _extract(tmp_path, DOC)
    b = raw.blocks
    assert (b[0].kind, b[0].origin) == (BlockKind.META, "frontmatter")
    assert (b[1].kind, b[1].level, b[1].text) == (BlockKind.HEADING, 1, "Глава 1")
    assert b[2].text == "Текст с ссылкой и картинкой и https://auto.link."
    assert (b[3].kind, b[3].level) == (BlockKind.HEADING, 1)      # setext =
    assert (b[4].kind, b[4].level) == (BlockKind.HEADING, 2)      # setext -
    assert (b[5].kind, b[5].text) == (BlockKind.CODE, "код  с   пробелами")
    assert (b[6].kind, b[6].text) == (BlockKind.QUOTE, "цитата\nвторая строка")
    assert [x.text for x in b[7:9]] == ["пункт один", "пункт два"]
    assert (b[9].kind, b[9].level) == (BlockKind.HEADING, 4)      # h5 → 4; *** пропущен

def test_md_thematic_break_not_setext(tmp_path):
    raw = _extract(tmp_path, "текст\n\n---\n\nещё")
    assert [x.kind for x in raw.blocks] == [BlockKind.PARA, BlockKind.PARA]

def test_md_setext_dash(tmp_path):
    raw = _extract(tmp_path, "Название\n---\n\nтело")
    assert (raw.blocks[0].kind, raw.blocks[0].level) == (BlockKind.HEADING, 2)
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/extractors/md.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

import charset_normalizer

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.extractors.textrules import apply_heading_patterns, merge_lines
from librarian.ir import Block, BlockKind, Format, RawDoc

_FENCE = re.compile(r"^(`{3,})")
_SETEXT = re.compile(r"^(=+|-+)\s*$")
_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_BREAK = re.compile(r"^(?:[-*_][ \t]*){3,}$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d{1,9}\.)\s+(.*)$")
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_AUTO = re.compile(r"<(https?://[^>\s]+)>")


def _strip_inline(text: str) -> str:
    text = _IMG.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    return _AUTO.sub(r"\1", text)


class MdExtractor:
    format = Format.MD

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        best = charset_normalizer.from_path(path).best()
        if best is None:
            raise BrokenFileError(f"{path.name}: не удалось определить кодировку")
        text = str(best)
        blocks = _parse(text.replace("\r\n", "\n").replace("\r", "\n"), cfg)
        for b in blocks:
            if b.kind is not BlockKind.CODE:
                b.text = _strip_inline(b.text)
        if not any(b.kind is BlockKind.HEADING for b in blocks):
            blocks = _fallback_patterns(blocks, cfg)    # 6.1.3 на однострочных PARA
        return RawDoc(fmt=Format.MD, blocks=blocks, title=None, author=None,
                      lang=None, ref_text=text)


def _fallback_patterns(blocks: list[Block], cfg: Config) -> list[Block]:
    out: list[Block] = []
    for b in blocks:
        if b.kind is BlockKind.PARA and "\n" not in b.text:
            out.extend(apply_heading_patterns([(b.text, True)], cfg))
        else:
            out.append(b)
    return out


def _parse(text: str, cfg: Config) -> list[Block]:
    lines = text.split("\n")
    blocks: list[Block] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(Block(BlockKind.PARA, merge_lines(para, cfg)))
            para.clear()

    i = 0
    if lines and lines[0].strip() == "---":                      # 1. front matter
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                blocks.append(Block(BlockKind.META, "\n".join(lines[1:j]),
                                    origin="frontmatter"))
                i = j + 1
                break
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        m = _FENCE.match(stripped)                               # 2. fence
        if m:
            flush()
            fence, body = m.group(1), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                body.append(lines[i])
                i += 1
            blocks.append(Block(BlockKind.CODE, "\n".join(body), origin="fence"))
            i += 1
            continue
        if para and _SETEXT.match(stripped):                     # 3. setext
            head = para.pop()
            flush()
            blocks.append(Block(BlockKind.HEADING, head,
                                level=1 if stripped[0] == "=" else 2, origin="setext"))
            i += 1
            continue
        m = _ATX.match(stripped)                                 # 4. ATX
        if m:
            flush()
            blocks.append(Block(BlockKind.HEADING, m.group(2),
                                level=min(len(m.group(1)), 4),
                                origin=f"h{len(m.group(1))}"))
            i += 1
            continue
        if _BREAK.match(stripped):                               # 5. thematic break
            flush()
            i += 1
            continue
        if stripped.startswith(">"):                             # 6. цитаты
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(re.sub(r"^\s*> ?", "", lines[i]).rstrip())
                i += 1
            blocks.append(Block(BlockKind.QUOTE, "\n".join(q)))
            continue
        m = _LIST.match(line)                                    # 7. списки
        if m:
            flush()
            blocks.append(Block(BlockKind.LIST_ITEM, m.group(1).strip()))
            i += 1
            continue
        if not stripped:
            flush()
            i += 1
            continue
        para.append(stripped)                                    # 8. PARA
        i += 1
    flush()
    return blocks


base.register(MdExtractor())
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "md extractor: frontmatter, fences, setext, atx, inline strip"`

---

### Task 11: structure.py — дерево, auto-deepen, нарезка, fallback

**Files:**
- Create: `src/librarian/structure.py`, `tests/unit/test_structure.py`

**Interfaces:**
- Consumes: `tokens.draft_count`, `Config`, IR.
- Produces:
  - `normalize_heading_levels(blocks) -> list[Block]` (8.1: плотные 1..k)
  - `build_tree(blocks, cfg) -> Section` (8.2; +cfg против §3.3 — нужен `preface_title`)
  - `choose_cut_level(root, cfg) -> int` (8.3)
  - `cut_chapters(root, level, cfg) -> list[Chapter]` (8.4: title = путь через « · », дубли подряд схлопнуты; внутренние HEADING получают **относительный** уровень k, где 1 = «разрезной + 1»)
  - `fallback_cut(blocks, title, cfg) -> list[Chapter]` (8.5: части `«{title} (i/k)»`, блок неделим)

- [ ] **Step 1: тест**

```python
from librarian.config import Config
from librarian.ir import Block, BlockKind
from librarian.structure import (build_tree, choose_cut_level, cut_chapters,
                                 fallback_cut, normalize_heading_levels)

CFG = Config()
H, P = BlockKind.HEADING, BlockKind.PARA

def _h(text, level): return Block(H, text, level=level)
def _p(text="абзац текста для объёма"): return Block(P, text)

def test_normalize_levels_dense():
    blocks = [_h("a", 2), _h("b", 4), _h("c", 2)]
    out = normalize_heading_levels(blocks)
    assert [b.level for b in out] == [1, 2, 1]

def test_tree_and_preface():
    blocks = [_p("до заголовка"), _h("Том 1", 1), _h("Глава 1", 2), _p(), _h("Глава 2", 2), _p()]
    root = build_tree(blocks, CFG)
    assert [s.title for s in root.children] == ["Начало", "Том 1"]
    assert [s.title for s in root.children[1].children] == ["Глава 1", "Глава 2"]

def test_cut_titles_are_paths():
    blocks = [_h("Том первый", 1), _h("Часть первая", 2), _p(), _h("Часть вторая", 2), _p()]
    root = build_tree(blocks, CFG)
    chapters = cut_chapters(root, 2, CFG)
    assert [c.title for c in chapters] == ["Том первый · Часть первая",
                                           "Том первый · Часть вторая"]

def test_cut_inner_headings_relative():
    blocks = [_h("Глава", 1), _p(), _h("Сцена", 2), _p()]
    root = build_tree(blocks, CFG)
    ch = cut_chapters(root, 1, CFG)[0]
    inner = [b for b in ch.blocks if b.kind is H]
    assert [b.level for b in inner] == [1]         # уровень 2 → относительный 1

def test_choose_level_deepens(monkeypatch):
    import librarian.structure as st
    # сегменты уровня 2 «большие», уровня 3 «маленькие» — подделываем черновой счётчик
    monkeypatch.setattr(st, "draft_count",
                        lambda blocks: 20000 if any(b.level == 3 and b.kind is H for b in blocks) is False else 100)
    blocks = [_h("Том", 1), _h("Часть", 2), _h("Гл 1", 3), _p(), _h("Гл 2", 3), _p()]
    root = build_tree(blocks, CFG)
    assert choose_cut_level(root, CFG) == 3

def test_fallback_parts():
    blocks = [_p("слово " * 400) for _ in range(10)]   # ~10 крупных блоков
    chapters = fallback_cut(blocks, "Роман", CFG)
    assert len(chapters) >= 2
    assert chapters[0].title == f"Роман (1/{len(chapters)})"
    assert sum(len(c.blocks) for c in chapters) == 10  # блоки не делятся
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/structure.py`**

```python
from __future__ import annotations

from statistics import median

from librarian.config import Config
from librarian.ir import Block, BlockKind, Chapter, Section
from librarian.tokens import draft_count


def normalize_heading_levels(blocks: list[Block]) -> list[Block]:
    levels = sorted({b.level for b in blocks if b.kind is BlockKind.HEADING})
    remap = {lvl: i + 1 for i, lvl in enumerate(levels)}
    for b in blocks:
        if b.kind is BlockKind.HEADING:
            b.level = remap[b.level]
    return blocks


def build_tree(blocks: list[Block], cfg: Config) -> Section:
    root = Section(title="", level=0, blocks=[], children=[])
    stack = [root]
    for b in blocks:
        if b.kind is BlockKind.HEADING:
            while stack[-1].level >= b.level:
                stack.pop()
            sec = Section(title=b.text, level=b.level, blocks=[], children=[])
            stack[-1].children.append(sec)
            stack.append(sec)
        else:
            if stack[-1] is root:                       # блоки до первого заголовка
                pre = Section(title=cfg.general.preface_title, level=1,
                              blocks=[], children=[])
                root.children.append(pre)
                stack.append(pre)
            stack[-1].blocks.append(b)
    return root


def _max_level(sec: Section) -> int:
    return max([sec.level] + [_max_level(c) for c in sec.children])


def _segments(root: Section, level: int) -> list[list[Block]]:
    """Разрез потока по заголовкам уровня ≤ level; сегмент = блоки секции
    (+ для секций разрезного уровня — все потомки, их заголовки остаются блоками)."""
    out: list[list[Block]] = []

    def collect_deep(sec: Section, acc: list[Block]) -> None:
        acc.extend(sec.blocks)
        for c in sec.children:
            acc.append(Block(BlockKind.HEADING, c.title, level=c.level))
            collect_deep(c, acc)

    def walk(sec: Section) -> None:
        for c in sec.children:
            if c.level < level:
                if c.blocks:
                    out.append(list(c.blocks))
                walk(c)
            else:
                acc: list[Block] = []
                collect_deep(c, acc)
                out.append(acc)

    walk(root)
    return out


def choose_cut_level(root: Section, cfg: Config) -> int:
    top = _max_level(root)
    if top == 0:
        return cfg.chapters.cut_level_start
    L = min(cfg.chapters.cut_level_start, top)
    while True:
        segs = _segments(root, L) or [[]]
        med = median(draft_count(s) for s in segs)
        if med > cfg.chapters.deepen_median and L + 1 <= top and L < 4:
            L += 1
            continue
        break
    if L == cfg.chapters.cut_level_start and med < cfg.chapters.shallow_median and L > 1:
        L = 1
    return L


def cut_chapters(root: Section, level: int, cfg: Config) -> list[Chapter]:
    chapters: list[Chapter] = []

    def path_title(path: list[str]) -> str:
        dedup: list[str] = []
        for t in path:
            if not dedup or dedup[-1] != t:
                dedup.append(t)
        return " · ".join(dedup)

    def collect_deep(sec: Section, acc: list[Block]) -> None:
        acc.extend(sec.blocks)
        for c in sec.children:
            acc.append(Block(BlockKind.HEADING, c.title,
                             level=c.level - level, origin="inner"))
            collect_deep(c, acc)

    def walk(sec: Section, path: list[str]) -> None:
        for c in sec.children:
            p = path + [c.title]
            if c.level < level:
                if c.blocks:
                    chapters.append(Chapter(0, path_title(p), list(c.blocks)))
                walk(c, p)
            else:
                acc: list[Block] = []
                collect_deep(c, acc)
                chapters.append(Chapter(0, path_title(p), acc))

    walk(root, [])
    return chapters


def fallback_cut(blocks: list[Block], title: str, cfg: Config) -> list[Chapter]:
    parts: list[list[Block]] = []
    cur: list[Block] = []
    cur_tokens = 0
    for b in blocks:
        t = draft_count([b])
        if cur and cur_tokens + t > cfg.chapters.fallback_part_tokens:
            parts.append(cur)
            cur, cur_tokens = [], 0
        cur.append(b)
        cur_tokens += t
    if cur:
        parts.append(cur)
    k = len(parts)
    if k == 1:
        return [Chapter(0, title, parts[0])]
    return [Chapter(0, f"{title} ({i}/{k})", p, part=i)
            for i, p in enumerate(parts, 1)]
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "structure: tree, auto-deepen, path titles, fallback cut"`

---

### Task 12: passes/sections.py — R3, R4, R5, нумерация

**Files:**
- Create: `src/librarian/passes/sections.py`, `tests/unit/test_sections.py`

**Interfaces:**
- Consumes: `draft_count`, `block_tokens`, `Chapter`, `DocContext`.
- Produces: `r3_merge_tiny`, `r4_split_giants`, `r5_drop_empty` (`SectionPass = (list[Chapter], DocContext) -> list[Chapter]`), `renumber(chapters)`, `apply_section_passes(chapters, ctx)` (порядок R3→R4→R5→нумерация; R1–R2 встанут в начало списка в M2).

- [ ] **Step 1: тест**

```python
from librarian.config import Config
from librarian.ir import Block, BlockKind, Chapter, DocContext, Format, RawDoc, ReportDraft
from librarian.passes.sections import apply_section_passes, r3_merge_tiny, r4_split_giants

H, P = BlockKind.HEADING, BlockKind.PARA

def _ctx():
    return DocContext(Format.TXT, Config(),
                      RawDoc(Format.TXT, [], None, None, None, ""), ReportDraft())

def _big_para():
    return Block(P, "слово " * 300)          # ~сотни токенов

def test_r3_tiny_merges_into_next():
    tiny = Chapter(0, "Эпиграф", [Block(P, "короткая строка")])
    big = Chapter(0, "Глава 1", [_big_para()])
    out = r3_merge_tiny([tiny, big], _ctx())
    assert len(out) == 1 and out[0].title == "Глава 1"
    assert out[0].blocks[0].kind is H and out[0].blocks[0].text == "Эпиграф"
    assert out[0].blocks[0].level == 1        # разрезной + 1

def test_r3_last_tiny_appends_to_prev():
    big = Chapter(0, "Глава 1", [_big_para()])
    tiny = Chapter(0, "Финал", [Block(P, "конец")])
    out = r3_merge_tiny([big, tiny], _ctx())
    assert len(out) == 1 and out[0].blocks[-2].text == "Финал"

def test_r4_splits_by_inner_headings():
    ch = Chapter(0, "Часть", [Block(P, "интро " * 50),
                              Block(H, "Гл 1", level=1), Block(P, "слово " * 9000),
                              Block(H, "Гл 2", level=1), Block(P, "слово " * 9000)])
    out = r4_split_giants([ch], _ctx())
    assert len(out) >= 3                                  # интро + 2 главы (возможно, дорезанные)
    assert out[1].title.startswith("Часть · Гл 1")

def test_r4_mechanical_parts_and_oversize_block():
    ctx = _ctx()
    ch = Chapter(0, "Стенограмма", [Block(P, ("фраза. " * 12000))])   # один неделимый гигант
    out = r4_split_giants([ch], ctx)
    assert len(out) > 1
    assert out[0].title == f"Стенограмма (1/{len(out)})" and out[0].part == 1
    assert ctx.report.oversize_blocks_split == 1

def test_pipeline_numbering():
    chs = [Chapter(0, "A", [_big_para()]), Chapter(0, "B", []), Chapter(0, "C", [_big_para()])]
    out = apply_section_passes(chs, _ctx())
    assert [c.n for c in out] == [1, 2]                   # пустая B удалена (R5), нумерация плотная
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/passes/sections.py`**

```python
from __future__ import annotations

import re

from librarian.ir import Block, BlockKind, Chapter, DocContext
from librarian.tokens import block_tokens, draft_count

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def r3_merge_tiny(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    tiny = ctx.cfg.chapters.tiny_tokens
    chs = list(chapters)
    i = 0
    while i < len(chs):
        ch = chs[i]
        if len(chs) > 1 and draft_count(ch.blocks) < tiny:
            demoted = [Block(BlockKind.HEADING, ch.title, level=1, origin="r3")] + ch.blocks
            if i + 1 < len(chs):
                chs[i + 1].blocks = demoted + chs[i + 1].blocks
            else:
                chs[i - 1].blocks = chs[i - 1].blocks + demoted
            del chs[i]              # принявшая глава оценивается заново на этой же позиции
        else:
            i += 1
    return chs


def r4_split_giants(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.chapters
    out: list[Chapter] = []
    for ch in chapters:
        if draft_count(ch.blocks) <= cfg.max_tokens:
            out.append(ch)
            continue
        pieces = _split_by_headings(ch, cfg.max_tokens) or [ch]
        for p in pieces:
            if draft_count(p.blocks) > cfg.max_tokens:
                out.extend(_mechanical_split(p, ctx))
            else:
                out.append(p)
    return out


def _split_by_headings(ch: Chapter, max_tokens: int) -> list[Chapter] | None:
    depths = sorted({b.level for b in ch.blocks if b.kind is BlockKind.HEADING})
    if not depths:
        return None
    pieces: list[Chapter] = []
    for k in depths:                       # от самого неглубокого вглубь (§9 R4.1)
        pieces = _cut_at(ch, k)
        if all(draft_count(p.blocks) <= max_tokens for p in pieces):
            return pieces
    return pieces                          # самый глубокий; остатки дорежет механика


def _cut_at(ch: Chapter, k: int) -> list[Chapter]:
    pieces: list[Chapter] = []
    cur_title = ch.title
    cur: list[Block] = []
    for b in ch.blocks:
        if b.kind is BlockKind.HEADING and b.level is not None and b.level <= k:
            if cur:
                pieces.append(Chapter(0, cur_title, cur))
            cur_title, cur = f"{ch.title} · {b.text}", []
        else:
            nb = b
            if b.kind is BlockKind.HEADING and b.level is not None:
                nb = Block(b.kind, b.text, level=b.level - k, origin=b.origin)
            cur.append(nb)
    if cur:
        pieces.append(Chapter(0, cur_title, cur))
    return pieces


def _mechanical_split(ch: Chapter, ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.chapters
    blocks: list[Block] = []
    for b in ch.blocks:
        if block_tokens(b) > cfg.max_tokens and b.kind in (
                BlockKind.PARA, BlockKind.QUOTE, BlockKind.CODE, BlockKind.TABLE):
            blocks.extend(_force_split(b, cfg.part_target_tokens))
            ctx.report.oversize_blocks_split += 1
        else:
            blocks.append(b)
    parts: list[list[Block]] = []
    cur: list[Block] = []
    cur_tokens = 0
    for b in blocks:
        t = block_tokens(b)
        if cur and cur_tokens + t > cfg.part_target_tokens:
            parts.append(cur)
            cur, cur_tokens = [], 0
        cur.append(b)
        cur_tokens += t
    if cur:
        parts.append(cur)
    k = len(parts)
    if k == 1:
        return [Chapter(0, ch.title, parts[0])]
    return [Chapter(0, f"{ch.title} ({i}/{k})", p, part=i)
            for i, p in enumerate(parts, 1)]


def _force_split(b: Block, target: int) -> list[Block]:
    if b.kind in (BlockKind.CODE, BlockKind.TABLE):
        units = b.text.split("\n")
        glue = "\n"
    else:
        units = _SENT_SPLIT.split(b.text)
        glue = " "
    out: list[Block] = []
    cur: list[str] = []
    cur_tokens = 0
    from librarian.tokens import count
    for u in units:
        t = count(u)
        if cur and cur_tokens + t > target:
            out.append(Block(b.kind, glue.join(cur), origin=b.origin))
            cur, cur_tokens = [], 0
        cur.append(u)
        cur_tokens += t
    if cur:
        out.append(Block(b.kind, glue.join(cur), origin=b.origin))
    return out


def r5_drop_empty(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    return [c for c in chapters if c.blocks]


def renumber(chapters: list[Chapter]) -> list[Chapter]:
    for i, c in enumerate(chapters, 1):
        c.n = i
    return chapters


SECTION_PASSES = [r3_merge_tiny, r4_split_giants, r5_drop_empty]   # M2: R1, R2 в начало


def apply_section_passes(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    for p in SECTION_PASSES:
        chapters = p(chapters, ctx)
    return renumber(chapters)
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "section passes r3-r5, renumber"`

---

### Task 13: quality.py — заглушка M1 (structure-метрика)

**Files:**
- Create: `src/librarian/quality.py`, `tests/unit/test_quality.py`

**Interfaces:**
- Produces: `Metrics` (`structure: float, chapters_found: bool, median_tokens: float`), `compute_metrics(chapters, ctx) -> Metrics`, `score_and_status(m, cfg) -> tuple[float, str, dict, list[str]]` (score, status, subscores, hard_triggers — расширение сигнатуры §3.3 ради report.json), `build_report(ctx, m, subscores, score, status, cfg) -> dict` (схема 11.6, недостающие метрики — нейтральные заглушки; M4 заменит).
- Правило M1: остальные субоценки = 1.0, поэтому `score = 0.75 + 0.25·s_struct`; fallback (0.3) → 0.825 → `review` (§8.5).

- [ ] **Step 1: тест**

```python
from librarian.config import Config
from librarian.ir import Chapter, DocContext, Format, RawDoc, ReportDraft
from librarian.quality import build_report, compute_metrics, score_and_status

def _ctx(fallback=False):
    r = ReportDraft(structure_fallback=fallback)
    return DocContext(Format.TXT, Config(),
                      RawDoc(Format.TXT, [], None, None, None, ""), r)

def _chapters(tokens_list):
    return [Chapter(i + 1, f"Гл {i+1}", [], tokens=t) for i, t in enumerate(tokens_list)]

def test_structure_ok():
    m = compute_metrics(_chapters([1000, 2000, 3000]), _ctx())
    assert m.structure == 1.0
    score, status, subs, triggers = score_and_status(m, Config())
    assert (score, status, triggers) == (1.0, "ok", [])

def test_structure_median_out_of_range():
    # 11.5: медиана вне [300, 20000] — НЕ жёсткий триггер; 0.925 ≥ 0.90 → ok
    m = compute_metrics(_chapters([50, 60, 70]), _ctx())
    assert m.structure == 0.7
    score, status, _, triggers = score_and_status(m, Config())
    assert abs(score - 0.925) < 1e-9 and status == "ok" and triggers == []

def test_fallback_forces_review():
    m = compute_metrics(_chapters([5000]), _ctx(fallback=True))
    assert m.structure == 0.3
    score, status, _, triggers = score_and_status(m, Config())
    assert status == "review" and abs(score - 0.825) < 1e-9 and triggers

def test_report_schema():
    ctx = _ctx()
    m = compute_metrics(_chapters([1000]), ctx)
    score, status, subs, trig = score_and_status(m, Config())
    rep = build_report(ctx, m, subs, trig, score, status, Config())
    assert set(rep) >= {"pipeline_version", "config_hash", "status", "score",
                        "metrics", "subscores", "hard_triggers", "removed", "warnings"}
    assert rep["hard_triggers"] == trig
```

- [ ] **Step 2: `src/librarian/quality.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from librarian import PIPELINE_VERSION
from librarian.config import Config, config_hash
from librarian.ir import Chapter, DocContext

_MEDIAN_LO, _MEDIAN_HI = 300, 20000        # категории structure, §11.2


@dataclass
class Metrics:
    structure: float
    chapters_found: bool
    median_tokens: float


def compute_metrics(chapters: list[Chapter], ctx: DocContext) -> Metrics:
    found = bool(chapters) and not ctx.report.structure_fallback
    med = float(median(c.tokens for c in chapters)) if chapters else 0.0
    if not found:
        s = 0.3
    elif _MEDIAN_LO <= med <= _MEDIAN_HI:
        s = 1.0
    else:
        s = 0.7
    return Metrics(structure=s, chapters_found=found, median_tokens=med)


def score_and_status(m: Metrics, cfg: Config) -> tuple[float, str, dict, list[str]]:
    subscores = {"coverage": 1.0, "garbage": 1.0, "encoding": 1.0,
                 "dehyphen": 1.0, "structure": m.structure}   # M1: заглушки, кроме structure
    w = cfg.quality.weights
    score = round(sum(w[k] * subscores[k] for k in sorted(subscores)), 4)
    triggers = [] if m.chapters_found else ["главы не найдены (fallback-раскрой)"]
    if score < cfg.quality.failed_max:
        status = "failed"
    elif score < cfg.quality.ok_min or triggers:
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
        "metrics": {"structure": m.structure, "median_tokens": m.median_tokens},
        "subscores": subscores,
        "hard_triggers": triggers,
        "oversize_blocks_split": ctx.report.oversize_blocks_split,
        "control_chars": ctx.report.control_chars,
        "removed": ctx.report.removed,
        "warnings": ctx.report.warnings,
    }
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "quality stub: structure metric, score, report schema"`

---

### Task 14: emit.py (часть 1) — рендер Markdown и канон JSON

**Files:**
- Create: `src/librarian/emit.py`, `tests/unit/test_render.py`

**Interfaces:**
- Produces: `render_chapter(ch: Chapter) -> str` (таблица 12.3; первая строка `# {заголовок-путь}`; FOOTNOTE — в конец после `---`; META не выводится; без хвостовых пробелов, NFC, один `\n` в конце), `canonical_json(obj) -> str` (12.2), `chapter_filename(ch, cfg) -> str` (12.1, `-pK` для частей).

- [ ] **Step 1: тест**

```python
from librarian.config import Config
from librarian.emit import canonical_json, chapter_filename, render_chapter
from librarian.ir import Block, BlockKind, Chapter

K = BlockKind

def test_render_full():
    ch = Chapter(1, "Том · Глава 1", [
        Block(K.PARA, "Абзац один."),
        Block(K.HEADING, "Сцена", level=1),
        Block(K.QUOTE, "строка раз\nстрока два"),
        Block(K.LIST_ITEM, "первый"),
        Block(K.LIST_ITEM, "второй"),
        Block(K.CODE, "x = `тик`"),
        Block(K.TABLE, "Имя\tЗначение\nа|б\t2"),
        Block(K.META, "скрыто"),
        Block(K.FOOTNOTE, "1. сноска"),
        Block(K.PARA, "Последний."),
    ])
    md = render_chapter(ch)
    lines = md.split("\n")
    assert lines[0] == "# Том · Глава 1"
    assert "## Сцена" in md                       # k=1 → «##»
    assert "> строка раз\n> строка два" in md
    assert "- первый\n- второй" in md
    assert "``` " not in md and "```\nx = `тик`\n```" in md
    assert "| Имя | Значение |" in md and "|---|---|" in md and "а\\|б" in md
    assert "скрыто" not in md
    assert md.rstrip("\n").endswith("1. сноска") and "\n---\n" in md
    assert md.endswith("\n") and not md.endswith("\n\n")
    assert not any(ln != ln.rstrip() for ln in lines)

def test_fence_grows():
    ch = Chapter(1, "T", [Block(K.CODE, "a ```` b")])
    assert "`````\na ```` b\n`````" in render_chapter(ch)

def test_canonical_json():
    s = canonical_json({"б": 1, "а": [2, 1]})
    assert s == '{\n  "а": [\n    2,\n    1\n  ],\n  "б": 1\n}\n'

def test_chapter_filename():
    cfg = Config()
    assert chapter_filename(Chapter(3, "Глава 1. Начало пути", []), cfg) == "003-glava-1-nachalo-puti.md"
    part = Chapter(7, "Стенограмма (2/5)", [], part=2)
    assert chapter_filename(part, cfg) == "007-stenogramma-p2.md"
```

Run → FAIL.

- [ ] **Step 2: реализация (первая половина `emit.py`)**

```python
from __future__ import annotations

import json
import re
import unicodedata

from librarian.config import Config
from librarian.ir import Block, BlockKind, Chapter
from librarian.slug import slugify

_PART_SUFFIX = re.compile(r"\s*\(\d+/\d+\)$")


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def chapter_filename(ch: Chapter, cfg: Config) -> str:
    title, suffix = ch.title, ""
    if ch.part is not None:
        title = _PART_SUFFIX.sub("", title)
        suffix = f"-p{ch.part}"
    return f"{ch.n:03d}-{slugify(title, cfg.slug.chapter_len)}{suffix}.md"


def _render_table(text: str) -> str:
    rows = [[c.replace("|", "\\|") for c in r.split("\t")] for r in text.split("\n")]
    width = len(rows[0])
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _render_code(text: str) -> str:
    runs = re.findall(r"`+", text)
    fence = "`" * max(3, max((len(r) for r in runs), default=0) + 1)
    return f"{fence}\n{text}\n{fence}"


def render_chapter(ch: Chapter) -> str:
    body: list[str] = [f"# {ch.title}"]
    footnotes: list[Block] = []
    items: list[str] = []

    def flush_items() -> None:
        if items:
            body.append("\n".join(items))
            items.clear()

    for b in ch.blocks:
        if b.kind is BlockKind.META:
            continue
        if b.kind is BlockKind.FOOTNOTE:
            footnotes.append(b)
            continue
        if b.kind is BlockKind.LIST_ITEM:
            items.append(f"- {b.text}")
            continue
        flush_items()
        if b.kind is BlockKind.HEADING:
            body.append(f"{'#' * min((b.level or 1) + 1, 6)} {b.text}")
        elif b.kind is BlockKind.QUOTE:
            body.append("\n".join(f"> {ln}" if ln else ">" for ln in b.text.split("\n")))
        elif b.kind is BlockKind.CODE:
            body.append(_render_code(b.text))
        elif b.kind is BlockKind.TABLE:
            body.append(_render_table(b.text))
        else:
            body.append(b.text)
    flush_items()
    if footnotes:
        body.append("---")
        body.extend(b.text for b in footnotes)
    text = "\n\n".join(body)
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))
    return unicodedata.normalize("NFC", text).rstrip("\n") + "\n"
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "emit: markdown render, canonical json, chapter filenames"`

---

### Task 15: emit.py (часть 2) — lock, протокол публикации, recovery

**Files:**
- Modify: `src/librarian/emit.py` (дописать)
- Create: `tests/unit/test_publish.py`

**Interfaces:**
- Produces: `library_lock(lib_root: Path, timeout_s: float)` (contextmanager; занято → `LibError("библиотека занята другим процессом")`), `recover(lib_root: Path) -> None` (порядок С-8: откат `.trash` → чистка `.staging` → чистка `.trash`), `publish(staging_dir: Path, lib_root: Path, book_id: str) -> Path` (шаги 2–4 протокола 12.4), `ingested_at() -> str` (SOURCE_DATE_EPOCH | wall-clock, UTC, ISO 8601 без мс).

- [ ] **Step 1: тест**

```python
import os
from pathlib import Path
import pytest
from librarian.emit import ingested_at, library_lock, publish, recover
from librarian.errors import LibError

def _mkbook(d: Path, marker: str):
    d.mkdir(parents=True)
    (d / "book.json").write_text(marker, encoding="utf-8")

def test_publish_replaces_and_cleans(tmp_path):
    lib = tmp_path
    _mkbook(lib / "my-book", "old")
    _mkbook(lib / ".staging" / "my-book", "new")
    publish(lib / ".staging" / "my-book", lib, "my-book")
    assert (lib / "my-book" / "book.json").read_text(encoding="utf-8") == "new"
    assert not (lib / ".trash").exists() and not (lib / ".staging" / "my-book").exists()

def test_recover_restores_trash_first(tmp_path):
    lib = tmp_path
    _mkbook(lib / ".trash" / "lost-book", "precious")     # упали между шагами 2 и 3
    _mkbook(lib / ".staging" / "lost-book", "half-built")
    recover(lib)
    assert (lib / "lost-book" / "book.json").read_text(encoding="utf-8") == "precious"
    assert not (lib / ".staging").exists() and not (lib / ".trash").exists()

def test_recover_keeps_existing_target(tmp_path):
    lib = tmp_path
    _mkbook(lib / "b", "current")
    _mkbook(lib / ".trash" / "b", "older")
    recover(lib)
    assert (lib / "b" / "book.json").read_text(encoding="utf-8") == "current"

def test_lock_times_out(tmp_path):
    with library_lock(tmp_path, 5):
        with pytest.raises(LibError):
            with library_lock(tmp_path, 0.3):     # второй захват в том же процессе
                pass

def test_ingested_at_source_date_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert ingested_at() == "1970-01-01T00:00:00Z"
```

Примечание: `fcntl.flock` на POSIX не реентерабелен по разным fd — тест таймаута валиден в одном процессе. Если на macOS flock окажется реентерабельным для одного процесса (это возможно), переписать тест через `subprocess`, держащий lock; проверить фактическое поведение при реализации.

Run → FAIL.

- [ ] **Step 2: дописать `emit.py`**

```python
import os
import shutil
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from librarian.errors import LibError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def ingested_at() -> str:
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    ts = int(sde) if sde else int(time.time())
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def library_lock(lib_root: Path, timeout_s: float):
    lib_root.mkdir(parents=True, exist_ok=True)
    f = open(lib_root / ".lock", "a+b")
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                if os.name == "nt":
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LibError("библиотека занята другим процессом") from None
                time.sleep(0.1)
        yield
    finally:
        try:
            if os.name == "nt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


def recover(lib_root: Path) -> None:
    trash, staging = lib_root / ".trash", lib_root / ".staging"
    if trash.is_dir():                                # 1. сначала откат .trash (С-8!)
        for d in sorted(p for p in trash.iterdir() if p.is_dir()):
            target = lib_root / d.name
            if not target.exists():
                os.replace(d, target)
                print(f"восстановлена книга {d.name} после прерванной записи",
                      file=sys.stderr)
    if staging.exists():                              # 2. потом недособранное
        shutil.rmtree(staging)
    if trash.exists():                                # 3. потом замещённые копии
        shutil.rmtree(trash)


def publish(staging_dir: Path, lib_root: Path, book_id: str) -> Path:
    target = lib_root / book_id
    trash = lib_root / ".trash" / book_id
    if target.exists():
        trash.parent.mkdir(exist_ok=True)
        if trash.exists():
            shutil.rmtree(trash)
        os.replace(target, trash)                     # шаг 2
    os.replace(staging_dir, target)                   # шаг 3 — атомарный rename
    shutil.rmtree(lib_root / ".trash", ignore_errors=True)   # шаг 4
    return target
```

- [ ] **Step 3:** PASS → **Commit** `git commit -m "emit: lock, publish protocol, crash recovery"`

---

### Task 16: emit_book + summary + lang + catalog.py

**Files:**
- Modify: `src/librarian/emit.py` (дописать `emit_book`, `build_summary`, `lang_heuristic`)
- Create: `src/librarian/catalog.py`, `tests/unit/test_emit_book.py`, `tests/unit/test_catalog.py`

**Interfaces:**
- Produces:
  - `emit.build_summary(ch: Chapter) -> str` (12.5: первый PARA ≥ 15 токенов → обрезка 300 симв. по слову с «…»; нет → первый непустой блок; подзаголовки → « — » + до 8 названий через « · »; `\n` → пробел)
  - `emit.lang_heuristic(text: str) -> str | None` (12.5)
  - `emit.emit_book(meta: BookMeta, chapters: list[Chapter], report: dict, lib_root: Path, cfg: Config) -> Path` (сборка в `.staging` → publish; `+cfg` против §3.3 — нужен `slug.chapter_len`)
  - `catalog.scan_books(lib_root) -> list[tuple[str, dict]]` (sorted по каталогу, битые book.json — warning в stderr + пропуск, С-4)
  - `catalog.rebuild_index(lib_root) -> None` (12.6; атомарно tmp+`os.replace`, С-1)
  - `catalog.read_book(lib_root, book_id) -> dict` (нет → `UnknownBookError`)
  - `catalog.find_by_sha256(lib_root, sha) -> str | None`, `catalog.find_by_cache_key(lib_root, key) -> str | None`

- [ ] **Step 1: тест emit_book/summary/lang**

```python
import json
from pathlib import Path
from librarian.config import Config, config_hash
from librarian.emit import build_summary, emit_book, lang_heuristic
from librarian.ir import Block, BlockKind, BookMeta, Chapter, Format

K = BlockKind
LONG_PARA = "Это первый содержательный абзац главы, в нём достаточно слов и токенов. " * 6

def test_summary_rules():
    ch = Chapter(1, "Глава", [Block(K.PARA, "коротко"), Block(K.PARA, LONG_PARA),
                              Block(K.HEADING, "Сцена I", level=1),
                              Block(K.HEADING, "Сцена II", level=1)])
    s = build_summary(ch)
    assert s.startswith("Это первый содержательный")
    assert "…" in s and " — Сцена I · Сцена II" in s
    assert len(s.split(" — ")[0]) <= 301

def test_summary_empty_chapter():
    assert build_summary(Chapter(1, "x", [])) == ""

def test_lang_heuristic():
    assert lang_heuristic("Сплошной русский текст про библиотеку") == "ru"
    assert lang_heuristic("Plain english text about libraries") == "en"
    assert lang_heuristic("12345 --- 67890") is None

def test_emit_book_layout(tmp_path):
    cfg = Config()
    src = tmp_path / "роман.txt"
    src.write_text("исходник", encoding="utf-8")
    meta = BookMeta(id="avtor-roman", title="Роман", author="Автор", lang="ru",
                    meta_locked=False, source_path=src, fmt=Format.TXT,
                    sha256="ab" * 32, config_hash=config_hash(cfg),
                    cache_key=f"{'ab'*32}:2.2:{config_hash(cfg)}",
                    status="ok", score=1.0, keep_source=True)
    chapters = [Chapter(1, "Глава 1", [Block(K.PARA, LONG_PARA)], tokens=120)]
    lib = tmp_path / "library"
    out = emit_book(meta, chapters, {"status": "ok"}, lib, cfg)
    book = json.loads((out / "book.json").read_text(encoding="utf-8"))
    assert book["id"] == "avtor-roman" and book["title"] == "Роман"
    assert book["total_tokens"] == 120
    assert book["chapters"][0]["file"] == "chapters/001-glava-1.md"
    assert book["provenance"]["cache_key"] == meta.cache_key
    assert (out / "chapters" / "001-glava-1.md").exists()
    assert (out / "source" / "роман.txt").read_text(encoding="utf-8") == "исходник"
    assert (out / "report.json").exists()
    assert not (lib / ".staging").exists()
```

- [ ] **Step 2: тест catalog**

```python
import json
from librarian.catalog import find_by_sha256, read_book, rebuild_index, scan_books
from librarian.errors import UnknownBookError
import pytest

def _book(lib, bid, sha="x", status="ok"):
    d = lib / bid
    (d / "chapters").mkdir(parents=True)
    (d / "book.json").write_text(json.dumps({
        "id": bid, "title": bid.upper(), "author": "A", "lang": "ru",
        "meta_locked": False,
        "source": {"file": "f.txt", "format": "txt", "sha256": sha},
        "provenance": {"cache_key": f"{sha}:2.2:c"},
        "quality": {"status": status, "score": 1.0},
        "total_tokens": 10, "chapters": [{"n": 1}],
    }, ensure_ascii=False), encoding="utf-8")

def test_index_sorted_and_atomic(tmp_path):
    _book(tmp_path, "bbb"); _book(tmp_path, "aaa")
    rebuild_index(tmp_path)
    idx = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in idx["books"]] == ["aaa", "bbb"]
    assert idx["books"][0] == {"id": "aaa", "title": "AAA", "author": "A",
                               "chapters": 1, "total_tokens": 10, "status": "ok"}

def test_broken_book_json_skipped(tmp_path, capsys):
    _book(tmp_path, "good")
    bad = tmp_path / "bad"; bad.mkdir()
    (bad / "book.json").write_text("{оборвано", encoding="utf-8")
    rebuild_index(tmp_path)
    idx = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in idx["books"]] == ["good"]
    assert "bad" in capsys.readouterr().err

def test_dot_dirs_ignored(tmp_path):
    _book(tmp_path, "one")
    (tmp_path / ".staging" / "junk").mkdir(parents=True)
    assert [bid for bid, _ in scan_books(tmp_path)] == ["one"]

def test_find_and_read(tmp_path):
    _book(tmp_path, "one", sha="deadbeef")
    assert find_by_sha256(tmp_path, "deadbeef") == "one"
    assert find_by_sha256(tmp_path, "nope") is None
    assert read_book(tmp_path, "one")["id"] == "one"
    with pytest.raises(UnknownBookError):
        read_book(tmp_path, "missing")
```

Run → FAIL.

- [ ] **Step 3: дописать `emit.py`**

```python
from librarian import PIPELINE_VERSION
from librarian.ir import BookMeta
from librarian.tokens import count as _tok_count


def build_summary(ch: Chapter) -> str:
    base = ""
    for b in ch.blocks:
        if b.kind is BlockKind.PARA and _tok_count(b.text) >= 15:
            base = _cut_300(b.text)
            break
    if not base:
        first = next((b for b in ch.blocks if b.text.strip()), None)
        base = _cut_300(first.text) if first else ""
    subs = [b.text for b in ch.blocks if b.kind is BlockKind.HEADING][:8]
    if subs:
        base = (base + " — " if base else "") + " · ".join(subs)
    return base


def _cut_300(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= 300:
        return text
    cut = text[:300].rsplit(" ", 1)[0]
    return cut + "…"


def lang_heuristic(text: str) -> str | None:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    cyr = sum(1 for ch in letters if "а" <= ch.casefold() <= "я" or ch.casefold() == "ё")
    lat = sum(1 for ch in letters if ch.isascii())
    if cyr / len(letters) >= 0.5:
        return "ru"
    if lat / len(letters) >= 0.5:
        return "en"
    return None


def emit_book(meta: BookMeta, chapters: list[Chapter], report: dict,
              lib_root: Path, cfg: Config) -> Path:
    staging = lib_root / ".staging" / meta.id
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "chapters").mkdir(parents=True)
    entries = []
    for ch in chapters:
        fname = chapter_filename(ch, cfg)
        (staging / "chapters" / fname).write_text(render_chapter(ch),
                                                  encoding="utf-8", newline="\n")
        entries.append({"n": ch.n, "file": f"chapters/{fname}", "title": ch.title,
                        "tokens": ch.tokens, "summary": build_summary(ch)})
    book = {
        "id": meta.id, "title": meta.title, "author": meta.author, "lang": meta.lang,
        "meta_locked": meta.meta_locked,
        "source": {"file": meta.source_path.name, "format": meta.fmt.value,
                   "sha256": meta.sha256},
        "provenance": {"ingested_at": ingested_at(),
                       "pipeline_version": PIPELINE_VERSION,
                       "config_hash": meta.config_hash,
                       "cache_key": meta.cache_key},
        "quality": {"status": meta.status, "score": meta.score},
        "total_tokens": sum(ch.tokens for ch in chapters),
        "chapters": entries,
    }
    (staging / "book.json").write_text(canonical_json(book), encoding="utf-8", newline="\n")
    (staging / "report.json").write_text(canonical_json(report), encoding="utf-8", newline="\n")
    if meta.keep_source:
        (staging / "source").mkdir()
        shutil.copyfile(meta.source_path, staging / "source" / meta.source_path.name)
    return publish(staging, lib_root, meta.id)
```

- [ ] **Step 4: `src/librarian/catalog.py`**

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from librarian import PIPELINE_VERSION
from librarian.emit import canonical_json
from librarian.errors import UnknownBookError


def scan_books(lib_root: Path) -> list[tuple[str, dict]]:
    if not lib_root.is_dir():
        return []
    out: list[tuple[str, dict]] = []
    for d in sorted(p for p in lib_root.iterdir()
                    if p.is_dir() and not p.name.startswith(".")):
        bj = d / "book.json"
        if not bj.is_file():
            continue
        try:
            out.append((d.name, json.loads(bj.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError) as e:
            print(f"предупреждение: {d.name}/book.json повреждён ({e}), книга пропущена",
                  file=sys.stderr)
    return out


def rebuild_index(lib_root: Path) -> None:
    books = [{"id": bid,
              "title": b.get("title"),
              "author": b.get("author"),
              "chapters": len(b.get("chapters", [])),
              "total_tokens": b.get("total_tokens", 0),
              "status": b.get("quality", {}).get("status")}
             for bid, b in scan_books(lib_root)]
    index = {"pipeline_version": PIPELINE_VERSION,
             "books": sorted(books, key=lambda x: x["id"])}
    lib_root.mkdir(parents=True, exist_ok=True)
    tmp = lib_root / "index.json.tmp"
    tmp.write_text(canonical_json(index), encoding="utf-8", newline="\n")
    os.replace(tmp, lib_root / "index.json")


def read_book(lib_root: Path, book_id: str) -> dict:
    bj = lib_root / book_id / "book.json"
    if not bj.is_file():
        raise UnknownBookError(f"книга «{book_id}» не найдена")
    return json.loads(bj.read_text(encoding="utf-8"))


def find_by_sha256(lib_root: Path, sha: str) -> str | None:
    for bid, b in scan_books(lib_root):
        if b.get("source", {}).get("sha256") == sha:
            return bid
    return None


def find_by_cache_key(lib_root: Path, key: str) -> str | None:
    for bid, b in scan_books(lib_root):
        if b.get("provenance", {}).get("cache_key") == key:
            return bid
    return None
```

- [ ] **Step 5:** PASS → **Commit** `git commit -m "emit book, summary, lang heuristic, catalog index"`

---

### Task 17: pipeline.py — сквозной ingest (§3.2)

**Files:**
- Create: `src/librarian/pipeline.py`, `tests/unit/test_pipeline.py`

**Interfaces:**
- Consumes: всё выше.
- Produces: `IngestOutcome` (`path, book_id: str | None, status: str, score: float | None, message: str = ""`), `ingest_file(path, cfg, lib_root, force=False) -> IngestOutcome`, `run_ingest(paths: list[Path], cfg, lib_root, force=False) -> list[IngestOutcome]` (lock → recover → файлы по очереди → **один** rebuild_index, С-7; ошибка одного файла не валит пакет).

- [ ] **Step 1: тест**

```python
import json
from librarian.config import Config
from librarian.pipeline import run_ingest

BOOK = """Глава 1

Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.

Глава 2

Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога."""

def _write(tmp_path, name="роман.txt", text=BOOK):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p

def test_ingest_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    out = run_ingest([_write(tmp_path)], Config(), lib)
    assert [o.status for o in out] == ["ok"]
    bid = out[0].book_id
    book = json.loads((lib / bid / "book.json").read_text(encoding="utf-8"))
    assert len(book["chapters"]) == 2
    assert book["lang"] == "ru"                     # эвристика
    assert book["provenance"]["ingested_at"] == "1970-01-01T00:00:00Z"
    idx = json.loads((lib / "index.json").read_text(encoding="utf-8"))
    assert idx["books"][0]["id"] == bid

def test_ingest_cache_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    src = _write(tmp_path)
    run_ingest([src], Config(), lib)
    out2 = run_ingest([src], Config(), lib)
    assert out2[0].status == "skipped"

def test_force_reuses_id_k1(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    src = _write(tmp_path)
    id1 = run_ingest([src], Config(), lib)[0].book_id
    id2 = run_ingest([src], Config(), lib, force=True)[0].book_id
    assert id1 == id2                               # К-1: идентичность стабильна

def test_meta_locked_survives_force(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    src = _write(tmp_path)
    bid = run_ingest([src], Config(), lib)[0].book_id
    bj = lib / bid / "book.json"
    data = json.loads(bj.read_text(encoding="utf-8"))
    data["title"], data["meta_locked"] = "Ручное имя", True
    bj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run_ingest([src], Config(), lib, force=True)
    after = json.loads(bj.read_text(encoding="utf-8"))
    assert after["title"] == "Ручное имя" and after["meta_locked"] is True   # С-2

def test_broken_file_does_not_kill_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    bad = tmp_path / "bad.dat"; bad.write_bytes(bytes(range(256)) * 4)
    good = _write(tmp_path)
    out = run_ingest([bad, good], Config(), tmp_path / "library")
    assert out[0].status == "skipped" and "формат" in out[0].message   # DetectError → пропуск
    assert out[1].status == "ok"

def test_fallback_review(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    p = _write(tmp_path, "плоский.txt", "Просто длинный текст без заголовков. " * 40)
    out = run_ingest([p], Config(), tmp_path / "library")
    assert out[0].status == "review"                # 8.5: структурный флаг
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/pipeline.py`**

```python
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from librarian import PIPELINE_VERSION
from librarian.catalog import find_by_cache_key, find_by_sha256, read_book, rebuild_index
from librarian.config import Config, config_hash
from librarian.detect import detect
from librarian.emit import (emit_book, lang_heuristic, library_lock,
                            recover, render_chapter)
from librarian.errors import DetectError, LibError
from librarian.extractors.base import get_extractor
from librarian.ir import BlockKind, BookMeta, DocContext, Format, ReportDraft
from librarian.passes.normalize import apply_block_passes
from librarian.passes.sections import apply_section_passes
from librarian.quality import build_report, compute_metrics, score_and_status
from librarian.slug import make_id
from librarian.structure import (build_tree, choose_cut_level, cut_chapters,
                                 fallback_cut, normalize_heading_levels)
from librarian.tokens import count


@dataclass
class IngestOutcome:
    path: Path
    book_id: str | None
    status: str
    score: float | None
    message: str = ""


def run_ingest(paths: list[Path], cfg: Config, lib_root: Path,
               force: bool = False) -> list[IngestOutcome]:
    lib_root.mkdir(parents=True, exist_ok=True)
    with library_lock(lib_root, cfg.general.lock_timeout_s):
        recover(lib_root)
        outcomes = [_safe_ingest(p, cfg, lib_root, force) for p in paths]
        rebuild_index(lib_root)                     # один раз на команду (С-7)
    return outcomes


def _safe_ingest(path: Path, cfg: Config, lib_root: Path, force: bool) -> IngestOutcome:
    try:
        return ingest_file(path, cfg, lib_root, force)
    except DetectError as e:
        return IngestOutcome(path, None, "skipped", None, str(e))
    except LibError as e:
        return IngestOutcome(path, None, "failed", None, str(e))
    except Exception as e:                          # noqa: BLE001 — §16: пакет не падает
        return IngestOutcome(path, None, "failed", None, f"{type(e).__name__}: {e}")


def ingest_file(path: Path, cfg: Config, lib_root: Path,
                force: bool = False) -> IngestOutcome:
    fmt = detect(path)                                                   # 1
    sha = hashlib.sha256(path.read_bytes()).hexdigest()                  # 2
    chash = config_hash(cfg)
    cache_key = f"{sha}:{PIPELINE_VERSION}:{chash}"
    if not force:                                                        # 3
        existing = find_by_cache_key(lib_root, cache_key)
        if existing:
            return IngestOutcome(path, existing, "skipped", None, "уже в библиотеке")
    raw = get_extractor(fmt).extract(path, cfg)                          # 4
    ctx = DocContext(fmt, cfg, raw, ReportDraft())                       # 5
    blocks = apply_block_passes(raw.blocks, ctx)                         # 6
    if any(b.kind is BlockKind.HEADING for b in blocks):                 # 7
        blocks = normalize_heading_levels(blocks)
        root = build_tree(blocks, cfg)
        level = choose_cut_level(root, cfg)
        chapters = cut_chapters(root, level, cfg)
    else:
        ctx.report.structure_fallback = True
        chapters = fallback_cut(blocks, raw.title or cfg.general.preface_title, cfg)
    chapters = apply_section_passes(chapters, ctx)                       # 8
    for ch in chapters:                                                  # 9 — финальные токены
        ch.tokens = count(render_chapter(ch))
    metrics = compute_metrics(chapters, ctx)                             # 10
    score, status, subscores, triggers = score_and_status(metrics, cfg)
    report = build_report(ctx, metrics, subscores, triggers, score, status, cfg)
    if status == "failed":                                               # 11
        print(f"{path.name}: failed (score {score}) — книга не сохранена",
              file=sys.stderr)
        return IngestOutcome(path, None, "failed", score, "score ниже порога")
    book_id = _resolve_identity(path, raw, sha, lib_root, cfg)           # 12
    title, author, lang, locked = (raw.title or path.stem), (raw.author or ""), raw.lang, False
    try:
        prev = read_book(lib_root, book_id)
    except LibError:
        prev = None
    if prev and prev.get("meta_locked"):                                 # С-2
        title, author, lang, locked = (prev["title"], prev["author"],
                                       prev["lang"], True)
    if lang is None:
        lang = lang_heuristic("\n".join(b.text for b in blocks))
    meta = BookMeta(id=book_id, title=title, author=author, lang=lang,
                    meta_locked=locked, source_path=path, fmt=fmt, sha256=sha,
                    config_hash=chash, cache_key=cache_key,
                    status=status, score=score, keep_source=cfg.keep_source)
    emit_book(meta, chapters, report, lib_root, cfg)                     # 13
    return IngestOutcome(path, book_id, status, score)                   # 15


def _resolve_identity(path: Path, raw, sha: str, lib_root: Path, cfg: Config) -> str:
    same = find_by_sha256(lib_root, sha)            # переингест того же файла (--force)
    if same:
        return same
    book_id = make_id(raw.title, raw.author, path.stem, cfg.slug.max_len)
    bj = lib_root / book_id / "book.json"
    if bj.is_file():                                # коллизия id с другим файлом (12.1)
        try:
            other = read_book(lib_root, book_id)
            if other.get("source", {}).get("sha256") != sha:
                return f"{book_id}-{sha[:6]}"
        except LibError:
            return f"{book_id}-{sha[:6]}"
    return book_id
```

Примечание: сигнатура `build_report(ctx, metrics, subscores, triggers, score, status, cfg)` — согласована с фиксом из Task 13.

- [ ] **Step 3:** PASS → **Commit** `git commit -m "pipeline: end-to-end ingest with cache, identity, meta_locked"`

---

### Task 18: cli.py — typer-приложение

**Files:**
- Create: `src/librarian/cli.py`, `src/librarian/__main__.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `app` (typer), `parse_spec(spec: str, n_max: int) -> list[int]`. Команды M1: `ingest`, `list`, `get`, `info`, `rm` (§15). Первое действие — `reconfigure(encoding="utf-8", newline="\n")` для stdout/stderr (С-6). Данные → stdout; диагностика/таблицы прогресса → stderr. Приоритет корня: `--library` → `$LIB_HOME` → `./library`. Коды выхода: 0 успех (включая review), 1 ошибка выполнения, 2 ошибка использования.

- [ ] **Step 1: тест** — через `typer.testing.CliRunner` + прямые юниты `parse_spec`

```python
import json
import pytest
from typer.testing import CliRunner
from librarian.cli import app, parse_spec

runner = CliRunner()

BOOK = """Глава 1

Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.

Глава 2

Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога."""

@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    src = tmp_path / "роман.txt"
    src.write_text(BOOK, encoding="utf-8")
    lib_dir = tmp_path / "library"
    r = runner.invoke(app, ["--library", str(lib_dir), "ingest", str(src)])
    assert r.exit_code == 0, r.output
    idx = json.loads((lib_dir / "index.json").read_text(encoding="utf-8"))
    return lib_dir, idx["books"][0]["id"]

def test_parse_spec():
    assert parse_spec("3", 10) == [3]
    assert parse_spec("2,5-7", 10) == [2, 5, 6, 7]
    assert parse_spec("1-3,9", 10) == [1, 2, 3, 9]
    for bad in ("0", "5-3", "1-3-5", "11", "a"):
        with pytest.raises(ValueError):
            parse_spec(bad, 10)

def test_get_outputs_chapters(lib):
    lib_dir, bid = lib
    r = runner.invoke(app, ["--library", str(lib_dir), "get", bid, "1-2"])
    assert r.exit_code == 0
    assert r.stdout.count("# ") >= 2 and "Первый абзац" in r.stdout

def test_get_bad_spec_exit_1(lib):
    lib_dir, bid = lib
    r = runner.invoke(app, ["--library", str(lib_dir), "get", bid, "99"])
    assert r.exit_code == 1

def test_get_unknown_book_exit_1(lib):
    lib_dir, _ = lib
    r = runner.invoke(app, ["--library", str(lib_dir), "get", "нет-такой", "1"])
    assert r.exit_code == 1

def test_list_and_info(lib):
    lib_dir, bid = lib
    assert bid in runner.invoke(app, ["--library", str(lib_dir), "list"]).stdout
    assert bid in runner.invoke(app, ["--library", str(lib_dir), "list", bid]).stdout
    assert "score" in runner.invoke(app, ["--library", str(lib_dir), "info", bid]).stdout

def test_rm(lib):
    lib_dir, bid = lib
    r = runner.invoke(app, ["--library", str(lib_dir), "rm", bid])
    assert r.exit_code == 0 and not (lib_dir / bid).exists()
    idx = json.loads((lib_dir / "index.json").read_text(encoding="utf-8"))
    assert idx["books"] == []
```

Run → FAIL.

- [ ] **Step 2: `src/librarian/cli.py`**

```python
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from librarian.catalog import read_book, rebuild_index
from librarian.config import load_config
from librarian.emit import library_lock, recover
from librarian.errors import LibError
from librarian.pipeline import run_ingest

app = typer.Typer(add_completion=False, no_args_is_help=True)
_state: dict = {"library": None}
_err = Console(stderr=True)


def _lib_root() -> Path:
    if _state["library"]:
        return _state["library"]
    return Path(os.environ.get("LIB_HOME") or "./library")


@app.callback()
def _main(library: Path | None = typer.Option(None, "--library",
                                              help="корень библиотеки")) -> None:
    if hasattr(sys.stdout, "reconfigure"):          # С-6: до любого вывода
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    _state["library"] = library


def parse_spec(spec: str, n_max: int) -> list[int]:
    import re
    if not re.fullmatch(r"\d+(-\d+)?(,\d+(-\d+)?)*", spec):
        raise ValueError(f"неверный формат диапазона: {spec}")
    nums: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        n, m = int(a), int(b or a)
        if m < n or n < 1 or m > n_max:
            raise ValueError(f"диапазон {part} вне 1..{n_max}")
        nums.extend(range(n, m + 1))
    return nums


@app.command()
def ingest(paths: list[Path],
           force: bool = typer.Option(False, "--force"),
           no_keep_source: bool = typer.Option(False, "--no-keep-source"),
           config: Path | None = typer.Option(None, "--config"),
           verbose: bool = typer.Option(False, "--verbose")) -> None:
    cfg = load_config(config, keep_source=not no_keep_source)
    outcomes = run_ingest(paths, cfg, _lib_root(), force=force)
    table = Table("файл", "id", "статус", "score")
    for o in outcomes:
        table.add_row(o.path.name, o.book_id or "—", o.status,
                      f"{o.score:.2f}" if o.score is not None else "—")
        if o.message:
            _err.print(f"  {o.path.name}: {o.message}")
    _err.print(table)                               # сводка — диагностика → stderr
    if any(o.status == "failed" for o in outcomes):
        raise typer.Exit(1)


@app.command("list")
def list_cmd(book_id: str = typer.Argument(None)) -> None:
    out = Console()
    try:
        if book_id is None:
            import json
            idx_path = _lib_root() / "index.json"
            books = (json.loads(idx_path.read_text(encoding="utf-8"))["books"]
                     if idx_path.is_file() else [])
            t = Table("id", "автор", "название", "глав", "токенов", "статус")
            for b in books:
                t.add_row(b["id"], b["author"] or "", b["title"] or "",
                          str(b["chapters"]), str(b["total_tokens"]), b["status"])
            out.print(t)
        else:
            book = read_book(_lib_root(), book_id)
            t = Table("n", "заголовок", "токенов", "summary")
            for ch in book["chapters"]:
                t.add_row(str(ch["n"]), ch["title"], str(ch["tokens"]),
                          (ch["summary"] or "")[:80])
            out.print(t)
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)


@app.command()
def get(book_id: str, spec: str) -> None:
    try:
        book = read_book(_lib_root(), book_id)
        nums = parse_spec(spec, len(book["chapters"]))
        by_n = {ch["n"]: ch for ch in book["chapters"]}
        texts = [(_lib_root() / book_id / by_n[n]["file"])
                 .read_text(encoding="utf-8") for n in nums]
        sys.stdout.write("\n\n".join(t.rstrip("\n") for t in texts) + "\n")
    except (LibError, ValueError) as e:
        _err.print(str(e))
        raise typer.Exit(1)


@app.command()
def info(book_id: str) -> None:
    import json
    try:
        book = read_book(_lib_root(), book_id)
        report_path = _lib_root() / book_id / "report.json"
        report = (json.loads(report_path.read_text(encoding="utf-8"))
                  if report_path.is_file() else {})
        payload = {"book": book,
                   "metrics": report.get("metrics", {}),
                   "subscores": report.get("subscores", {}),
                   "score": report.get("score"),
                   "hard_triggers": report.get("hard_triggers", [])}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n")
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)


@app.command()
def rm(book_id: str) -> None:
    lib = _lib_root()
    cfg = load_config(None)
    try:
        with library_lock(lib, cfg.general.lock_timeout_s):
            recover(lib)
            target = lib / book_id
            if not (target / "book.json").is_file():
                raise LibError(f"книга «{book_id}» не найдена")
            shutil.rmtree(target)
            rebuild_index(lib)
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)
```

`src/librarian/__main__.py`:

```python
from librarian.cli import app

app()
```

- [ ] **Step 3:** PASS. Ручная проверка: `uv run lib ingest tests/fixtures/... && uv run lib list` (после Task 19 — на фикстурах).
- [ ] **Step 4: Commit** — `git commit -m "cli: ingest, list, get, info, rm with spec grammar"`

---

### Task 19: фикстуры и golden-тесты TXT/MD

**Files:**
- Create: `scripts/make_fixtures.py`, `tests/fixtures/txt/roman_cp1251.txt`, `tests/fixtures/txt/koi8.txt`, `tests/fixtures/txt/perenosy.txt`, `tests/fixtures/md/statya.md`, `scripts/update_golden.py`, `tests/golden/…`, `tests/test_golden.py`

**Interfaces:**
- Consumes: `run_ingest`, `load_config`.
- Produces: golden-деревья в `tests/golden/<имя-фикстуры>/` (эталонные библиотеки), сравнение — рекурсивное побайтовое.

- [ ] **Step 1: `scripts/make_fixtures.py`** — фикстуры генерируются кодом (кодировки руками не набрать)

```python
"""Генерация фикстур. Запуск: uv run python scripts/make_fixtures.py"""
from pathlib import Path

FIX = Path(__file__).parent.parent / "tests" / "fixtures"

ROMAN = """Роман о трудной судьбе инженера.

Том первый

Глава 1

Инженер Пётр Семёнович проснулся рано утром и долго смотрел в окно на заводскую трубу.
Мысли его были тяжелы: проект горел, сроки поджимали, а вдохновение не приходило.

Глава 2

На работе его ждала неожиданная новость: проект закрыли, отдел расформировали.
Пётр Семёнович вышел на улицу и впервые за десять лет вдохнул полной грудью.

Том второй

Глава 1

Новая жизнь началась с малого: он купил билет на поезд до южного города.
В вагоне пахло углём и свободой, колёса стучали ободряюще и ровно.

Глава 2

Море встретило его серым штормом, но даже шторм показался ему праздником.
Так инженер стал смотрителем маяка, и об этом не пожалел ни разу."""

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
print("fixtures written")
```

Run: `uv run python scripts/make_fixtures.py`.

- [ ] **Step 2: `scripts/update_golden.py`**

```python
"""Регенерация golden-библиотек. Любой diff в git — осознанное решение ревью (§17)."""
import os
import shutil
from pathlib import Path

os.environ["SOURCE_DATE_EPOCH"] = "0"

from librarian.config import load_config          # noqa: E402
from librarian.pipeline import run_ingest         # noqa: E402

ROOT = Path(__file__).parent.parent
GOLDEN = ROOT / "tests" / "golden"
FIXTURES = sorted((ROOT / "tests" / "fixtures").rglob("*.*"))

for fx in FIXTURES:
    name = fx.stem
    out = GOLDEN / name
    if out.exists():
        shutil.rmtree(out)
    outcomes = run_ingest([fx], load_config(None), out)
    print(name, "->", [(o.status, o.book_id) for o in outcomes])
```

- [ ] **Step 3: `tests/test_golden.py`**

```python
import os
from pathlib import Path

import pytest

from librarian.config import load_config
from librarian.pipeline import run_ingest

ROOT = Path(__file__).parent
FIXTURES = sorted((ROOT / "fixtures").rglob("*.*"))


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)).replace(os.sep, "/"): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != ".lock"}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_golden(fixture, tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    golden = ROOT / "golden" / fixture.stem
    assert golden.is_dir(), f"нет golden для {fixture.stem}: запусти scripts/update_golden.py"
    run_ingest([fixture], load_config(None), tmp_path)
    actual, expected = tree_bytes(tmp_path), tree_bytes(golden)
    assert sorted(actual) == sorted(expected)
    for rel in sorted(expected):
        assert actual[rel] == expected[rel], f"байтовое расхождение: {rel}"
```

- [ ] **Step 4:** Запустить `uv run python scripts/update_golden.py`, **глазами проверить** результат (чек-лист):
  - `roman_cp1251`: главы = `Том … · Глава N` (4 шт.), русский текст без кракозябр, `lang: "ru"`, status `ok`;
  - `koi8`: побайтово те же главы, id отличается только именем файла-источника (тот же слаг «Начало»? — нет: title нет, id из имени файла);
  - `perenosy`: в тексте «слово разорвано», «кто-то», «что-либо» — склейка верна; status `review` не обязателен (заголовков нет → fallback → `review` — это ожидаемо, зафиксировать);
  - `statya`: front matter не попал в главы, код в fence, ссылка развёрнута в текст.
- [ ] **Step 5:** `uv run pytest tests/test_golden.py -v` → PASS → **Commit** `git commit -m "fixtures and golden libraries for txt/md"` (golden-деревья коммитятся).

---

### Task 20: интеграционные тесты DoD — детерминизм, кэш, восстановление, wheel

**Files:**
- Create: `tests/test_determinism.py`, `tests/test_cache.py`, `tests/test_recovery.py`, `tests/test_install.py`, `scripts/smoke_wheel.sh`

**Interfaces:**
- Consumes: CLI (`python -m librarian`), `run_ingest`, `publish/recover`.

- [ ] **Step 1: `tests/test_determinism.py`** — два `PYTHONHASHSEED` (С-10) через subprocess

```python
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".lock"}


def _run(seed: str, lib: Path, fixture: Path) -> None:
    env = {**os.environ, "PYTHONHASHSEED": seed, "SOURCE_DATE_EPOCH": "0"}
    r = subprocess.run(
        [sys.executable, "-m", "librarian", "--library", str(lib),
         "ingest", str(fixture)],
        env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_determinism_across_hashseeds(tmp_path):
    fixture = ROOT / "fixtures" / "txt" / "roman_cp1251.txt"
    lib_a, lib_b = tmp_path / "a", tmp_path / "b"
    _run("0", lib_a, fixture)
    _run("42", lib_b, fixture)
    ta, tb = tree_bytes(lib_a), tree_bytes(lib_b)
    assert sorted(ta) == sorted(tb)
    for rel in sorted(ta):
        assert ta[rel] == tb[rel], f"недетерминизм: {rel}"
```

- [ ] **Step 2: `tests/test_cache.py`** — идемпотентность (§17)

```python
from pathlib import Path
from librarian.config import Config
from librarian.pipeline import run_ingest
from tests.test_determinism import tree_bytes   # или продублировать хелпер

FIXTURE = Path(__file__).parent / "fixtures" / "txt" / "roman_cp1251.txt"

def test_second_ingest_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    assert run_ingest([FIXTURE], Config(), lib)[0].status == "ok"
    before = tree_bytes(lib)
    out = run_ingest([FIXTURE], Config(), lib)
    assert out[0].status == "skipped"
    assert tree_bytes(lib) == before               # библиотека не изменилась побайтово
```

(Если импорт `tests.test_determinism` неудобен — вынести `tree_bytes` в `tests/conftest.py` как фикстуру-функцию; сделать это сразу и переиспользовать в golden/determinism/cache.)

- [ ] **Step 3: `tests/test_recovery.py`** — прерывание между шагами 2 и 3 протокола (С-8, §17)

```python
import os
from pathlib import Path
import pytest
from librarian.config import Config
from librarian.emit import publish, recover
from librarian.pipeline import run_ingest

FIXTURE = Path(__file__).parent / "fixtures" / "txt" / "roman_cp1251.txt"

def test_crash_between_trash_and_replace(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    bid = run_ingest([FIXTURE], Config(), lib)[0].book_id
    original = (lib / bid / "book.json").read_bytes()

    # имитация падения: первый os.replace (→ .trash) сработал, второй — упал
    real_replace = os.replace
    calls = {"n": 0}
    def crashy(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("имитация падения процесса")
        real_replace(src, dst)
    monkeypatch.setattr(os, "replace", crashy)
    staging = lib / ".staging" / bid
    (staging / "chapters").mkdir(parents=True)
    (staging / "book.json").write_text("новая версия", encoding="utf-8")
    with pytest.raises(RuntimeError):
        publish(staging, lib, bid)
    monkeypatch.setattr(os, "replace", real_replace)

    assert not (lib / bid).exists()                # книга «исчезла» — момент аварии
    recover(lib)                                   # следующая пишущая команда
    assert (lib / bid / "book.json").read_bytes() == original   # книга не потеряна
    assert not (lib / ".trash").exists() and not (lib / ".staging").exists()
```

- [ ] **Step 4: `scripts/smoke_wheel.sh` + `tests/test_install.py`** — К-4

```bash
#!/usr/bin/env bash
# Сборка wheel → чистый venv → lib работает (ассет токенизатора в пакете).
set -euo pipefail
cd "$(dirname "$0")/.."
uv build --wheel
VENV=$(mktemp -d)/venv
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet dist/librarian-*.whl
TMP=$(mktemp -d)
printf 'Глава 1\n\nПроверка установки из колеса, текст главы номер один достаточной длины.\n\nГлава 2\n\nВторая глава смоук-теста установки тоже не совсем пустая.\n' > "$TMP/книга.txt"
SOURCE_DATE_EPOCH=0 "$VENV/bin/lib" --library "$TMP/lib" ingest "$TMP/книга.txt"
"$VENV/bin/lib" --library "$TMP/lib" get "$("$VENV/bin/python" -c "
import json,sys; print(json.load(open('$TMP/lib/index.json'))['books'][0]['id'])")" 1
echo "SMOKE OK"
```

```python
# tests/test_install.py
import os
import subprocess
from pathlib import Path

import pytest

@pytest.mark.skipif(not os.environ.get("RUN_INSTALL_TESTS"),
                    reason="медленный: включается RUN_INSTALL_TESTS=1 (CI и перед релизом)")
def test_wheel_smoke():
    script = Path(__file__).parent.parent / "scripts" / "smoke_wheel.sh"
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SMOKE OK" in r.stdout
```

- [ ] **Step 5:** `uv run pytest -v` (всё) → PASS; `RUN_INSTALL_TESTS=1 uv run pytest tests/test_install.py -v` → PASS.
- [ ] **Step 6: Commit** — `git commit -m "dod tests: determinism, cache idempotency, recovery, wheel smoke"`

---

## Definition of Done (M1, из §18)

- [ ] `uv run lib ingest tests/fixtures/txt/roman_cp1251.txt && uv run lib get <id> 1-3` работает офлайн (проверить с отключённой сетью).
- [ ] Golden для всех TXT/MD-фикстур зелёные.
- [ ] Тест детерминизма с `PYTHONHASHSEED` 0 и 42 зелёный.
- [ ] Тест идемпотентности кэша зелёный.
- [ ] Тест восстановления зелёный.
- [ ] `RUN_INSTALL_TESTS=1` wheel-смоук зелёный.
- [ ] `git status` чистый, все коммиты на месте.

## Отклонения от буквы спеки (зафиксированы осознанно)

1. `build_tree(blocks, cfg)`, `emit_book(..., cfg)` — +параметр против «ключевых сигнатур» §3.3 (нужны `preface_title` и `slug.chapter_len`).
2. `make_id` — чистая функция без sha/ФС; коллизионный суффикс `-{sha[:6]}` вешает `pipeline._resolve_identity` (правило требует читать библиотеку).
3. `score_and_status` возвращает также subscores и triggers (нужны report.json).
4. `Chapter.part: int | None` — служебное поле для имён `-pK`.
5. MD: при нуле HEADING применяются паттерны 6.1.3 к однострочным PARA (трактовка таблицы §6.0).
6. Уровни внутренних HEADING после нарезки — относительные (1 = разрезной+1): упрощает рендер 12.3 и R4.
7. **detect.py `_SKIP`**: в сниппете плану стоит `^(?:\s+|<\?.*?\?>|<!--.*?-->)`, но `re.Pattern.match(text, pos)` с `^` (без `re.M`) всё равно требует индекс 0, поэтому `_SKIP`-цикл не скипает пролог на ненулевой позиции и падают `test_fb2_xml_with_comment_and_decl`/`test_html_xhtml`. Реализация убрала `^` (минимальный фикс, гард `m.end() == i` защищает от зацикливания).
8. **textrules `merge_lines`, частица «ка»**: план внутренне противоречив — `test_config` пинит `keep_hyphen_suffixes == (..., "ка", ...)`, а `test_merge_plain_hyphen` требует `merge_lines(["нау-", "ка победила"]) == "наука победила"`. Словарно-чистого решения нет; реализация добавляет `and suffix != "ка"` в условие сохранения дефиса (нау-ка→наука). Остальные 4 частицы (то/либо/нибудь/таки) дефис сохраняют. Известный побочный эффект: редкое `ну-ка` склеится в `нука`.
9. **txt/md экстракторы, кодировки**: в этом окружении (Python 3.14, charset-normalizer 3.4.7) короткий koi8-r образец детектится как `shift_jis_2004` — `test_txt_koi8r` невозможен на «голом» charset_normalizer. Реализация вводит `_read_text(data, name)`: доверяет charset_normalizer, когда его вывод содержит кириллицу и vowel-ratio ≥ 0.85, иначе перебирает 6 кириллических кодировок по vowel-score. На длинных реальных текстах срабатывает fast-path (поведение совпадает с charset_normalizer); вне скоупа — латиница с акцентами (cp1252), где cn сам слаб.
10. **structure.py тесты (модуль — дословно из плана, правки только в фикстурах):**
    - `test_choose_level_deepens`: в лямбде плану стоит `... is False else 100`, но `_segments(root,2)` через `collect_deep` инжектит level-3 заголовки в сегменты уровня 2, поэтому `any(level==3) is False` ложно → 100 → углубления нет → `choose_cut_level` возвращает 1, а не 3. Реализация инвертировала полярность (`... else 100`, т.е. 20000 когда level-3 есть) — это и есть интент NOTE («L=2 большие, L=3 маленькие»).
    - `test_fallback_parts`: `"слово "*400` даёт ~402 токена/блок (всего 4020 < `fallback_part_tokens`=6000) → 1 часть, ассерты падают. Поднято до `"слово "*700` (~702 ×10 = 7020 > 6000) → 2 части. Модуль `fallback_cut` не менялся.
11. **emit.py `emit_book`, чистка `.staging`**: `publish(staging_dir=lib_root/.staging/meta.id, …)` делает `os.replace` только дочерней директории, оставляя пустого родителя `.staging/`, что ломает ассерт `test_emit_book_layout` `not (lib/".staging").exists()`. Реализация добавляет `rmdir` пустого родителя после `publish` (с гардом `is_dir() and not any(iterdir())`) — безопасно: под `library_lock` конкурентного staging нет, а гард защищает и без инварианта.

## Roadmap после M1

- **M2** (отдельный план): FB2 + EPUB, боевое использование xmlsafe, ZIP-лимиты (С-5), R1–R2, XXE/zip-bomb фикстуры.
- **M3**: DOCX + HTML, общий `html_blocks.py`.
- **M4**: PDF, P1–P7, полный quality 11.1–11.6, `doctor`.
- **M5**: `--budget`, `reingest --all`, лимиты/таймауты, CI-матрица (3 ОС × py3.11/3.13), перф-смоук, README.
