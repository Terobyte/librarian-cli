# Librarian M6 «поиск + MCP» — Implementation Plan

> **For agentic workers:** implement task-by-task. This file is the canon (tero run
> file): players and judges reference items by number; senior is the only writer.
> Design source of truth: `docs/superpowers/specs/2026-07-07-librarian-m6-mcp-search-design.md`.

**Goal:** две ридерские фичи поверх готового конвейера — `lib find` (полнотекстовый
поиск FTS5 по главам всей библиотеки) и `lib serve` (MCP-сервер, stdio). Оба — чистые
читатели выхода (`<id>/chapters/*.md`, `book.json`, `index.json`). Плюс вынос общего
ядра ридеров в `catalog.py` и закрытие пред-существующей дыры traversal в `read_book`.

**Architecture:** ноль изменений в конвейере (§2 спеки). `PIPELINE_VERSION` = 2.4,
golden не регенерируются — **инвариант каждой задачи**. `.search.db` — производный кэш,
исключён из `tree_bytes`, пересобирается из markdown. Поиск и MCP разделяют одно ядро
в `catalog.py`.

**Порядок задач строго последовательный** (плееры никогда не параллельны):
T1 (общее ядро — фундамент) → T2 (search.py зависит от ядра) → T3 (serve.py зависит
от ядра + search.py). Каждая задача — свой tero-луп: плеер реализует, судья гоняет
реальный e2e, senior коммитит.

## Global Constraints

- **Выходные байты не меняются:** после каждой задачи `uv run pytest -q` зелёный **без**
  регенерации golden. Изменение байтов = дефект задачи. `.search.db` не попадает в golden
  (T1 правит `tree_bytes`).
- **Коды выхода (§15):** 0 — успех (включая пустой результат поиска и review); 1 — ошибка
  выполнения; 2 — ошибка использования (typer, spec×budget, пустой запрос).
- **Данные — stdout, диагностика — stderr.** `--json` в stdout без stderr-примесей.
- **Ошибки по-русски (§16); пакет/сервер не падает от плохого ввода.**
- **Коммиты:** короткие, lowercase, без префиксов и **без Co-Authored-By/AI-атрибуции**.
- Рабочая директория: `/Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian/`.
  Запуск: `uv run pytest`. Git-корень — уровнем выше (`libby/`).

## File Structure (дельта M6)

```
librarian/
  pyproject.toml            # T2: dependencies += "snowballstemmer>=3"
                            # T3: [project.optional-dependencies] serve = ["mcp>=1.0"]
                            #     [dependency-groups] dev += "mcp>=1.0" (осознанный дубль)
  src/librarian/
    catalog.py              # T1: + validate_book_id, read_index, get_chapters_core,
                            #        info_projection; read_book вызывает validate_book_id
    cli.py                  # T1: list/get/info — тонкие обёртки над ядром; rm → validate_book_id
                            # T2: + find;  T3: + serve
    search.py               # T2: CREATE — индекс, синхронизация, запросы, слияние хитов
    serve.py                # T3: CREATE — MCP-сервер (ленивый импорт mcp)
  tests/
    conftest.py             # T1: tree_bytes исключает .search.db
    test_golden.py          # T1: удалить свою копию tree_bytes, импорт из conftest
    unit/test_catalog.py    # T1: CREATE (или дополнить, если есть) — traversal у read_book
    unit/test_cli.py        # T1: регресс get/info; T2: + find
    unit/test_search.py     # T2: CREATE
    unit/test_serve.py      # T3: CREATE
```

---

## Task 1: общее ридерское ядро в `catalog.py` + закрытие traversal

**Files:** modify `src/librarian/catalog.py`, `src/librarian/cli.py`,
`tests/conftest.py`, `tests/test_golden.py`; create/extend `tests/unit/test_catalog.py`;
verify `tests/unit/test_cli.py` (регресс).
**Forbidden:** любой файл в `tests/golden/`, `pipeline.py`, `emit.py`, `quality.py`.

**Почему фундамент:** T2 (`find`) и T3 (MCP) — тонкие адаптеры над этим ядром.
`read_book` сегодня открывает `lib/<book_id>/book.json` **без валидации** — `../x` или
абсолютный путь утекают наружу; `is_relative_to` в `get` бессилен, если `book_id` уже
сбежал. MCP сделал бы дыру сетево-доступной. Закрываем для всех читателей разом.

**Interfaces (catalog.py):**

1. `validate_book_id(lib_root: Path, book_id: str) -> None` — правила `rm`
   (cli.py:205-208 дословно): `LibError(f"недопустимый id книги: «{book_id}»")` если
   `"/" in book_id or "\\" in book_id or resolved == lib.resolve() or not
   resolved.is_relative_to(lib.resolve())`, где `resolved = (lib_root / book_id).resolve()`.
2. `read_book` — **первой строкой** вызывает `validate_book_id(lib_root, book_id)`
   (закрывает дыру для всех читателей; вычисленные конвейером id — валидные слаги, проходят).
3. `read_index(lib_root: Path) -> list[dict]` — проекция каталога: читает `index.json`,
   возвращает `books` (список dict id/author/title/chapters/total_tokens/status); нет
   файла → `[]`. Ровно текущая инлайн-логика cli.py:83-89. Общая для `lib list` и MCP.
4. `info_projection(lib_root: Path, book_id: str) -> dict` — `{"book", "metrics",
   "subscores", "score", "hard_triggers"}` из book.json + report.json. Ровно cli.py:180-188.
5. `get_chapters_core(lib_root, book_id, *, spec=None, budget=None, from_=1) -> dict`
   — переезд логики выбора глав из cli.py:114-144. Возвращает
   `{"text": str, "chapters": list[int], "next_from": int | None, "message": str | None}`.
   - Ровно один из `spec`/`budget` не None (вызывающий гарантирует; иначе
     `ValueError("нужно ровно одно из: spec или budget")`).
   - spec-режим: `parse_spec` (остаётся в cli.py — импортировать), собрать номера,
     прочитать файлы с **проверкой пути** (`ch_path.resolve().is_relative_to(book_dir)`,
     нарушение → `LibError`), `next_from=None`, `message=None`.
   - budget-режим: жадно подряд с `from_`; `from_` вне 1..N → `ValueError`;
     **первая глава не влезает → НЕ исключение**, а `{"text": "", "chapters": [],
     "next_from": from_, "message": "глава N (X токенов) не влезает в бюджет Y"}`;
     остались не вошедшие → `next_from` = номер первой не вошедшей, `message` про них;
     всё вошло → `next_from=None`.

**Interfaces (cli.py) — тонкие обёртки, поведение байт-в-байт как сейчас:**
- `list_cmd`: ветка «без book_id» зовёт `read_index`.
- `get`: usage-проверки (spec×budget взаимоисключение, `--from` только с budget) остаются
  в CLI → exit 2. Затем `res = get_chapters_core(...)`; budget-режим и `res["chapters"]`
  пуст → печать `res["message"]` в stderr + exit 1 (сохраняем §15). Иначе
  `res["message"]` (не-вошедшие) в stderr, `res["text"]` в stdout. `LibError/ValueError`
  → stderr + exit 1.
- `info`: зовёт `info_projection`, печатает JSON.
- `rm`: заменить инлайн-проверку на `validate_book_id(lib, book_id)`.

**Tests:**
- `test_catalog.py`: `validate_book_id`/`read_book` бросают `LibError` на `book_id`
  `"../x"`, `"a/b"`, абсолютный путь, `""`/`.` (→ lib root); валидный слаг проходит;
  `read_index` на fixtures-библиотеке (собрать через `run_ingest`, `SOURCE_DATE_EPOCH=0`)
  возвращает ожидаемую проекцию; `get_chapters_core` budget-режим: первая глава больше
  бюджета → `chapters == []`, `next_from == from_`, `message` не пуст (НЕ исключение).
- `test_cli.py`: **существующие** тесты get/info/rm/list проходят без изменений
  (это и есть регресс выноса ядра). Добавить traversal-регресс через CLI:
  `lib get ../x 1` и `lib info ../x` → exit 1.
- Инвариант: golden байт-в-байт (conftest.tree_bytes + test_golden после дедупликации).

**Verify (senior гоняет сам перед судьёй):**
```
uv run pytest -q                       # всё зелёное, golden не тронуты
git status tests/golden                # чисто
```
**Judge e2e:** реальный `uv run lib` на временной библиотеке: `get`/`info`/`list`
дают тот же вывод, что до рефактора; `lib get ../etc 1` → exit 1, ничего не утекло;
полный `uv run pytest -q` зелёный.

**Commit:** `catalog: shared reader core, book_id validation closes traversal`

---

## Task 2: `search.py` + `lib find` (FTS5)

**Files:** create `src/librarian/search.py`, `tests/unit/test_search.py`; modify
`pyproject.toml` (dep), `src/librarian/cli.py` (+`find`), `tests/unit/test_cli.py`.
**Forbidden:** `tests/golden/`, `pipeline.py`, `emit.py`, `catalog.py` ядро (только импорт).

**Interfaces (search.py):**
- `search(lib_root, query, *, limit=10, book_id=None, reindex=False) -> dict` →
  `{"hits": [ {book_id, book_title, author, n, chapter_title, snippet} ], "partial": bool}`
  (книжный хит: `n=None`, `chapter_title=None`). Синхронизирует индекс, затем ищет.
- `sync(lib_root, *, force=False)` — ленивая синхронизация: fingerprint книги =
  sha256(book.json) + `(size, mtime_ns)` каждого файла глав; сверка с `meta`;
  переиндексация добавленных/изменённых, удаление ушедших; `force`/schema-mismatch →
  drop+rebuild. Весь write-путь — `BEGIN IMMEDIATE … COMMIT`; `busy_timeout=10000`.
- Печать «строю индекс…» в stderr при холодной сборке (не в `--json`-путь — это делает CLI).

**Ключевые детали (§3 спеки — свериться):**
- Две FTS5-таблицы `chapters(book_id UNINDEXED,n UNINDEXED,title,text)` +
  `books(book_id UNINDEXED,title,author)`, обе `tokenize='unicode61 remove_diacritics 2'`;
  `meta(key,value)` со `schema_version` и per-book fingerprint.
- Нет FTS5 в сборке sqlite → `LibError("sqlite без поддержки FTS5 — поиск недоступен")`.
- Пути глав — из `book.json` `chapters[].file` (не глоббинг); проверка пути как в ядре.
- Запрос: `query.split()` (без арг); стемминг (кириллица→snowball ru, латиница→en;
  стем только если **префикс** исходного слова и len≥3, иначе слово как есть);
  экранирование `'"' + w.replace('"','""') + '"*'`; join `AND`; 0 хитов при ≥2 словах →
  автоповтор `OR`, `partial=True`. Пустой запрос после split → CLI даёт exit 2.
- Ранжирование `bm25(chapters,0,0,5.0,1.0)` / `bm25(books,0,2.0,1.0)`; сниппеты
  `snippet(chapters,3,'«','»','…',12)`; книжный хит — `highlight` названия/автора.
- Слияние: книжные хиты первыми, **кап ≤3**, затем главы по bm25; `limit` — на объединённый.
- Книги в статусе `review` индексируются.

**Interfaces (cli.py `find`):**
`lib find <query> [--limit 10] [--book <id>] [--reindex] [--json]`.
- Табличный вывод (rich): `id · глава · заголовок · сниппет`; книжный хит: глава `—`,
  заголовок = название книги, сниппет = название/автор с выделением.
- `--json`: структура из `search()` в stdout; пусто → `{"hits": [], "partial": false}`,
  exit 0, **без** stderr.
- OR-фоллбэк: таблица → предупреждение в stderr; `--json` → `partial:true`.
- Ничего не найдено → сообщение в stderr, **exit 0**. Пустой запрос → exit 2.
- Нет FTS5 / битая библиотека → stderr, exit 1.

**Tests (test_search.py, test_cli.py):** сборка индекса на fixtures-библиотеке;
инкрементальная синхронизация (добавили/удалили/переингестили книгу; ручная правка
meta_locked; **прямая правка .md ловится по stat**); RU+EN запросы; **стемминг-recall**
(«поэзию»→«поэзия», «маятники»→«маятник», EN «pendulums»→«pendulum»; «poetry»→фоллбэк
на слово); кривые запросы (`o"brien`, скобки, пусто); слово с дефисом; сниппеты;
**OR-фоллбэк** (AND→0 при ≥2 словах → `partial`); **книжный хит** (n=None, книги перед
главами, кап ≤3); **реингест-детекция с РАЗНЫМИ SOURCE_DATE_EPOCH на два прогона**
(при «0» в обоих book.json побайтово идентичен — ветка хэша не покрывается);
смена `schema_version` → пересборка; `--reindex`. CLI `find`: таблица, exit 0 при пустом,
`--book`, `--reindex`, exit 2 на пустой запрос, `--json` валиден и без stderr.

**Verify + Judge:** `uv run pytest -q` зелёный, golden чист; судья — реальный
`uv run lib find` на временной библиотеке из ≥2 книг: находит по главе и по названию,
`--json` даёт валидный JSON нужной структуры, стемминг-падеж находит, пустой запрос exit 2.

**Commit:** `find: fts5 full-text search over chapters, query stemming, json output`

---

## Task 3: `serve.py` + `lib serve` (MCP)

**Files:** create `src/librarian/serve.py`, `tests/unit/test_serve.py`; modify
`pyproject.toml` (extra + dev dup), `src/librarian/cli.py` (+`serve`).
**Forbidden:** `tests/golden/`, конвейер, ядро catalog/search (только импорт).

**Interfaces:** `lib serve [--library <path>]` — stdio MCP-сервер, официальный SDK `mcp`.
Импорт `mcp` **ленивый, внутри команды**; нет extra → `LibError`-подобная русская
подсказка «установите librarian[serve]», exit 1. Синхронизация индекса **на старте, до
приёма запросов** (§3 холодный старт платится при запуске).

**5 read-only тулов (тонкие адаптеры над ядром T1/T2):**
| Tool | Параметры | Поверх |
|---|---|---|
| `list_books` | — | `catalog.read_index` |
| `list_chapters` | `book_id` | `read_book` |
| `find` | `query, limit=10, book_id?` | `search.search` |
| `get_chapters` | `book_id, spec?/budget?, from=1` | `catalog.get_chapters_core` |
| `book_info` | `book_id` | `catalog.info_projection` |

- `get_chapters`: ни spec ни budget → `budget=12000`; оба → ошибка тула; отдаёт
  структуру ядра как есть (пустой список + `next_from` + `message` — валидный ответ, не
  исключение). `book_id` валидируется ядром (traversal закрыт в T1).
- Описания тулов по-русски (v1 личный).

**Tests (test_serve.py):** тулы in-process (прямой вызов async-хендлеров через anyio
pytest-плагин) — list/find/get roundtrip, spec×budget, **дефолтный budget без
параметров**, **`next_from` на длинной книге**, **первая глава > бюджета →
структурированный ответ, не исключение**, несуществующий/`../` book_id → ошибка тула.
**e2e-смок:** сабпроцесс `lib serve` + MCP handshake (initialize) + один
`list_books`-roundtrip через клиент SDK (stdio — не сеть, pytest-socket не мешает).
**Недостающий extra:** monkeypatch импорта mcp → ImportError → русская подсказка, exit 1.
Сетевой блок не ослабляется (stdio/unix-socket разрешены).

**Verify + Judge:** `uv run pytest -q` зелёный, golden чист; судья — реальный запуск
`lib serve` сабпроцессом, handshake + `list_books` + `get_chapters` с дефолтным бюджетом
отдают ожидаемое; `lib serve` без extra (в чистом окружении/через monkeypatch) → exit 1
с русской подсказкой.

**Commit:** `serve: read-only mcp server over shared reader core`

---

## Deviations (нумерация сквозная; за M5 — 35)

- **36.** (T1) `parse_spec` остаётся в `cli.py`, `get_chapters_core` берёт его локальным
  импортом внутри spec-ветки (`from librarian.cli import parse_spec`) — разрыв цикла
  cli↔catalog. Нулевая цена в рантайме: под `lib serve` точка входа — cli.py, модуль
  уже в `sys.modules`; стандартный приём. Принято, не дефект.

## Run log (tero — senior only)

- **T1:** SHIP. player ✓ · judge SHIP (277 passed, golden чист, traversal `../etc/passwd`
  → exit 1 без утечки) · commit **9ab88aa**.
- **T2:** SHIP. player ✓ · judge SHIP (310 passed, golden чист, e2e: `find маятники`→находит
  «маятник» стеммингом, `--json` 0 байт в stderr, пустой запрос exit 2) · commit **aabc922**.
- **T3:** SHIP. player ✓ (mcp 1.28.1 API проверен до кода) · judge SHIP (327 passed, golden
  чист, реальный `uv run --extra serve lib serve` handshake: SERVER=librarian, list_books→kit,
  get_chapters дефолт-бюджет→текст) · commit **e098b75**.
- **README:** find + serve + MCP-подключение + ограничение стемминга (doc-only, senior).
- **M6 DONE.** Все три задачи зелёные, golden не тронут, PIPELINE_VERSION=2.4.
- Parking lot: (пусто — см. §8 spec для отложенного)
