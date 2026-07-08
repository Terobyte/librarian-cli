# CLAUDE.md — libby / librarian

`librarian` — детерминированный конвейер «книга → Markdown-главы» для работы с LLM. Любой
формат (FB2, EPUB, DOCX, HTML, TXT/MD, PDF с текстовым слоем) → каталог чистых глав с
подсчётом токенов. Без сети, без LLM, без случайности: одинаковый вход → побайтово
идентичный выход.

## Раскладка

- Git-корень — этот каталог (`libby/`). Пакет — в `librarian/` (все команды запускать оттуда).
- `librarian/README.md` — пользовательская дока (команды, установка, квота качества, лимиты).
- `docs/MILESTONES.md` — история вех M1–M6 и **сквозной список отклонений от спеки** (почему
  код расходится с дизайном). Читать перед правкой спорного места.
- `librarian-spec-v2.2.md` — канон дизайна (спека). `docs/superpowers/` — дизайн-доки/планы.

## Команды (из `librarian/`)

```bash
uv run pytest -q                      # весь набор (~330 тестов, ~19с)
uv run pytest tests/test_golden.py    # только golden (детерминизм выхода)
uv run lib ingest книга.epub          # обработать в ./library
uv run lib find маятник               # FTS5-поиск; --json для машинного вывода
uv run --extra serve lib serve        # MCP-сервер (stdio); extra тянет mcp
uv build                              # wheel; офлайн-установка не требует сети
```

Корень библиотеки: `--library <путь>` / `LIB_HOME` / по умолчанию `./library`.
Данные → stdout, диагностика → stderr. Exit: `0` успех, `1` ошибка выполнения, `2` ошибка
использования.

## Критический инвариант: golden не трогать

Выход детерминирован **побайтово**. `tests/golden/` — эталон. Любая правка, меняющая
выходные байты, валит `test_golden.py`. Это **не** «обнови golden» — это осознанное решение:

- Меняешь выходные байты намеренно → **подними `PIPELINE_VERSION`** (`src/librarian/__init__.py`)
  и регенерируй golden явно. Иначе — дефект: чини код, а не эталон.
- `.search.db` и `.lock` — производные, вне контракта (исключены из `tree_bytes` в conftest).
- PDF-фикстуры недетерминированы при генерации (pymupdf пишет случайный `/ID`) — коммитятся
  байтами один раз; `scripts/make_fixtures.py` перезаписывает только с регенерацией golden.
- Сеть в тестах заблокирована (pytest-socket); stdio/unix-socket разрешены (для MCP-смоука).

## Архитектура

Конвейер (`pipeline.py` оркестрирует): `detect → extract → normalize(N1–N3) →
structure → sections(R1–R5) → quality → emit`.

| Модуль | Роль |
|--------|------|
| `pipeline.py` | оркестратор ingest/reingest; кэш `sha:PIPELINE_VERSION:config_hash`; identity |
| `detect.py` | magic-байты, zip-диспатч, sniff тегов → формат |
| `extractors/` | по формату: `fb2 epub docx html txt md pdf`; `zipsafe`/`xmlsafe` (защита), `html_blocks`/`textrules` (общее), `guard` (spawn-таймаут) |
| `ir.py` | промежуточное представление: blocks, sections, chapters, RawDoc |
| `passes/` | `normalize` (дегифенизация, пробелы), `sections` (R-фильтры, нарезка), `pdf_layout` (P1–P7) |
| `structure.py` | выбор уровня резки, auto-deepen, path-титулы |
| `quality.py` | метрики coverage/structure/garbage/encoding/dehyphen → score → ok/review/failed |
| `emit.py` | canonical-JSON, рендер глав, lock/publish/recover (атомарная запись) |
| `catalog.py` | **ридерское ядро** (M6): `validate_book_id`, `read_index`, `info_projection`, `get_chapters_core` — общее для CLI и MCP |
| `search.py` | FTS5-индекс `.search.db`, ленивая синхронизация по fingerprint, стемминг RU/EN |
| `serve.py` | MCP-сервер: 5 read-only тулов — тонкие адаптеры над `catalog`/`search`, ноль своей логики |
| `cli.py` | typer-обёртки; `parse_spec` (грамматика диапазонов) |
| `tokens.py` | вендорёный o200k_base (офлайн); `slug.py` транслит id; `config.py` спека-дефолты + TOML overlay |

## Фичи (детали — README)

- CLI: `ingest · list · get (spec | --budget) · find · info · doctor · reingest · rm · serve`.
- `lib serve` = детерминированный RAG без эмбеддингов/сети/ключей: Claude сам листает
  каталог, ищет FTS5, тянет главы под токен-бюджет. Extra `librarian[serve]` (тянет `mcp`).
- Качество: `ok` (≥0.90, без триггеров) молча в библиотеку; `review` сохранена с
  предупреждением; `failed` (<0.60) не сохраняется. Правки метаданных руками защищаются
  `"meta_locked": true` в book.json (reingest не перетрёт).

## Гочи

- **Traversal закрыт в ядре:** `read_book`/`validate_book_id` (`catalog.py`) отклоняют `../x`,
  абсолютные пути, `/`,`\`. Не обходить — MCP делает это сетево-доступным.
- **Стемминг** снимает регулярную флексию («поэзию»→«поэзия»), но не супплетивы
  («люди»≠«человек») и не опечатки.
- **`get --budget`:** первая глава больше бюджета → не исключение, а структурированный пустой
  ответ (`next_from`/`message`) — и в CLI (exit 1), и в MCP (валидный ответ).
- Сетевые ФС (NFS/SMB) не поддержаны (advisory-lock ненадёжен). DRM/OCR — вне задач (v3).

## Коммиты

Короткие, lowercase, без `feat:`/`fix:`-префиксов, без emoji. **Никаких `Co-Authored-By` и
AI-атрибуции.** Стиль — как в `git log` этого репо.
