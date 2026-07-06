# bugs.md — найденные баги `librarian`

Дата ревью: 2026-07-06.
Три параллельных агента (pipeline, extractors/emit, CLI/tests/config), область действия непересекающаяся.
Каждый баг свернут с конкретным симптомом, первопричиной и наброском фикса.
Спецификация — `librarian-spec-v2.2.md`. Документированные-как-принятые отклонения в список не входят (кроме случаев, явно отмеченных как «недокументированное отклонение»).

Всего: **10 багов** (0 Critical / 1 High / 5 Medium / 4 Low).

---

## Итог фазы фиксов (Opus, phase-3, 2026-07-06)

Каждый фикс прошёл gate **red→green** (тест красный без фикса, зелёный с ним). Итог сюита: **102 passed, 1 skipped, 3 xfailed, 1 xpassed, 0 failed**.

| BUG | Вердикт | Действие |
|-----|---------|----------|
| 3 `--verbose` не печатает traceback | ✅ реальный | пофикшен: `pipeline` захватывает `traceback.format_exc()`, `cli` печатает в stderr при `--verbose` |
| 4 `--config` кидает сырой traceback | ✅ реальный | пофикшен: `load_config` → `LibError` на missing/broken, `cli.ingest` ловит → чистое сообщение, exit 1 |
| 6 fd-leak в `detect()` | ✅ реальный | пофикшен: `with path.open("rb")` |
| 7 битый `SOURCE_DATE_EPOCH` валит батч | ✅ реальный | пофикшен: `try/except (TypeError, ValueError)` → fallback на `time.time()` |
| 9 `smoke_wheel.sh` течёт temp-дир | ✅ реальный | пофикшен: `trap 'rm -rf "$VENV_ROOT" "$TMP"' EXIT` |
| 10 `rm` path-traversal | ✅ реальный | пофикшен: guard (сепараторы + `resolve().is_relative_to(lib)` + `!= lib`) |
| 2 R3 demoted level захардкожен в 1 | ❌ **ложный** | откачено — `level=1` спек-корректен: внутренние уровни **относительны** (дев. №6 плана: «1 = разрезной+1»). Мой `cut_level+1` дал бы H5 для романа. Поймано golden-бронёй |
| 8 частица «ка» теряет дефис | ❌ **ложный** | откачено — осознанное отклонение **№8 плана** (`нау-ка→наука` частотнее частицы `ну-ка`), защищено `test_merge_plain_hyphen`. Структурно неразличимо |
| 1 R1/R2 фильтры не реализованы | ⏸ **вне scope M1** | отложено — R1/R2 = этап **M2** по §18 (M1 = «refine R3–R5»). Тесты → `xfail(reason=M2)` как броня для M2 |
| 5 `get --budget/--from` | ⏸ **вне scope M1** | отложено — `--budget` = этап **M5** по §18. Тесты → `xfail(reason=M5)` как броня для M5 |

**Итог:** 6 реальных багов пофикшено, 2 ложноположительных откачено (оба уже были документированными отклонениями плана — №6 и №8; охотник не сверился с секцией отклонений), 2 отложено как фичи будущих этапов (M2/M5). Продакшн-код трогал только Opus; тесты правил sonnet-test-writer.

---

## High

### BUG 1: Фильтры R1 (мета-разделы) и R2 (оглавление) полностью не реализованы
- **Файл:** `src/librarian/passes/sections.py:138` (`SECTION_PASSES = [r3_merge_tiny, r4_split_giants, r5_drop_empty]`); функций R1/R2 нет нигде в `src/librarian/`
- **Severity:** High
- **Type:** logic / spec-deviation (data-quality)
- **Симптом:** Спец §9 требует порядок **R1 → R2 → R3 → R4 → R5**. Существуют только R3/R4/R5. Конкретно:
  - Короткая глава с `ISBN` / `©` / «Все права защищены» / «Литагент» **никогда не вырезается** → уходит в каталог как настоящая глава и завышает `total_tokens` (R1).
  - Печатное оглавление (≤2000 токенов, >60 % строк с цифрой на конце или ≥80 % строк дублируют заголовки других глав) **не удаляется** (R2) → survives как глава, `lib list` показывает мусорную TOC-запись, каждый заголовок дублируется.
  - `report.json.removed` всегда `{}` — гарантия спец «ничего не исчезает бесследно» (`removed.meta_sections` / `.toc`) молча нарушена.
- **Root cause:** Параметры `clean.meta_max_tokens`, `clean.meta_markers`, `clean.toc_numeric_line_ratio`, `clean.toc_heading_dup_ratio`, `clean.toc_max_tokens` определены в `config.py:56–62`, но **не читаются никаким кодом** (`grep` подтверждает: ноль использований вне `config.py`). `ReportDraft.removed` только *читается* в `quality.build_report`, никогда не наполняется. `notes_chapter_title` тоже мёртвый конфиг.
- **Fix sketch:** Реализовать `r1_drop_meta_sections` и `r2_drop_toc` (по точным порогам спец) и поставить их в начало `SECTION_PASSES`: `[r1, r2, r3, r4, r5]`. Каждый должен переносить текст вырезанной главы в `ctx.report.removed["meta_sections"]` / `["toc"]` (dict уже есть на `ReportDraft`).

---

## Medium

### BUG 2: R3 demoted-heading level захардкожен в 1 вместо `cut_level + 1`
- **Файл:** `src/librarian/passes/sections.py:18`
- **Severity:** Medium
- **Type:** logic / spec-deviation
- **Симптом:** При вливании короткой главы (эпиграф, посвящение) в соседнюю спец §9 R3 требует понизить её заголовок до HEADING уровня **«разрезной + 1»**. Код хардкодит `level=1`. Для романа (cut_level = 2, Том › Часть › Глава) слитый эпиграф рендерится как заметный `##` внутри главы вместо глубокого `####`, т.е. поглощённый заголовок становится *заметнее* реального контента. Даже при cut_level=1 неверно (H2 вместо H3 по спец). Тестов нет (молчаливый дефект качества).
- **Root cause:** `demoted = [Block(BlockKind.HEADING, ch.title, level=1, origin="r3")] + ch.blocks`. Выбранный cut level `L` — локальная переменная в `pipeline.ingest_file` (строка 73), **не хранится** на `DocContext`/`ReportDraft` (проверено: ни в одном нет поля), поэтому `r3_merge_tiny` не имеет к нему доступа и автор сдался на константу.
- **Fix sketch:** Прокинуть cut level в контекст (`cut_level: int` на `ReportDraft`/`DocContext`, ставить в `ingest_file` сразу после `choose_cut_level`), затем `level=ctx.cut_level + 1`.

### BUG 3: `--verbose` принимается, но не используется (спец §16 требует полный traceback в stderr)
- **Файл:** `src/librarian/cli.py:57` (объявлен) против тела `52–68`; `src/librarian/pipeline.py:52–53`
- **Severity:** Medium
- **Type:** cli
- **Симптом:** `lib ingest foo.txt --verbose` ведёт себя идентично запуску без флага. На `failed`-книге юзер получает только `"{ExcType}: {msg}"` (`_safe_ingest` строка 53), никогда — полный traceback, обещанный спец («плюс полный traceback в stderr при `--verbose`», §16). Флаг мёртвый.
- **Root cause:** Параметр `verbose` связан в сигнатуре `ingest`, но нигде не используется; `_safe_ingest` безусловно теряет traceback (`f"{type(e).__name__}: {e}"`) без ветки с `traceback.format_exc()`.
- **Fix sketch:** Передать `verbose` в `run_ingest`/`_safe_ingest`; при set — добавлять `traceback.format_exc()` в сообщение (или писать в `_err`). Callback Typer уже реконфигурирует stderr, так что traceback будет UTF-8/LF-чистым.

### BUG 4: `--config` с отсутствующим/битым файлом бросает сырой traceback юзеру
- **Файл:** `src/librarian/cli.py:58` (`cfg = load_config(config, ...)` вне try/except); `src/librarian/config.py:136`
- **Severity:** Medium
- **Type:** cli / config
- **Симптом:** Проверено эмпирически: `lib ingest x.txt --config /no/such.toml` → непойманный `FileNotFoundError`, битый TOML → непойманный `tomllib.TOMLDecodeError`. Typer в standalone-mode сбрасывает полный traceback (exit 1). Спец §16/§15 хотят человекочитаемое сообщение, не Python-traceback.
- **Root cause:** `load_config` вызывает `path.read_text(...)` / `tomllib.loads(...)` и пропускает `FileNotFoundError`/`TOMLDecodeError` наверх; `ingest` зовёт его без `except`.
- **Fix sketch:** Обернуть read/parse в `load_config` и кидать `LibError(f"не удалось прочитать конфиг {path}: {e}")`; либо обернуть вызов `load_config` в `ingest` и конвертировать в `typer.Exit(1)` после печати сообщения в `_err`.

### BUG 5: Подкоманда `get` не имеет спец-опций `--budget`/`--from` (и exit-2 при конфликте `spec`×`--budget`)
- **Файл:** `src/librarian/cli.py:97–108`
- **Severity:** Medium
- **Type:** cli (spec-deviation)
- **Симптом:** Спец §15 определяет `lib get <book-id> --budget 12000 [--from K]` и требует: «`<spec>` и `--budget` взаимоисключающие: заданы оба → exit 2». Реализована сигнатура `get(book_id, spec)` без `--budget`/`--from`, поэтому `lib get id --budget 12000` — это unknown-option usage error вместо жадного budget-режима, а exit-2 при мьютексе в принципе нельзя получить.
- **Root cause:** `get` не расширяли за пределы формы `<spec>`. (Замечание: спец M5 ставит `--budget` в свой DoD, т.е. это пока-не-реализованная фича, а не регрессия, но это активное отклонение от задокументированной §15 грамматики.)
- **Fix sketch:** Добавить `budget: int|None = typer.Option(None)` и `--from`; если заданы и `spec`-арг, и `--budget` — `raise typer.Exit(2)`; иначе реализовать жадное накопление по §15.

---

## Low

### BUG 6: `detect()` течёт файловыми дескрипторами (open без `with`)
- **Файл:** `src/librarian/detect.py:17` и `src/librarian/detect.py:55`
- **Severity:** Low
- **Type:** resource-leak
- **Симптом:** `head = path.open("rb").read(1024)` и `data = path.open("rb").read(4096)` открывают файл без `with`/`close`. На CPython дескриптор закрывается быстро по refcount-у (проверено: 2000 вызовов `detect()` → 0 удержанных fd), т.е. сегодня латентно, не активно. На PyPy/любом non-refcount runtime дескрипторы копятся. Плюс `detect()` открывает один файл до 3 раз за вызов.
- **Root cause:** Голый `path.open(...)` без context-manager.
- **Fix sketch:** `with path.open("rb") as f: data = f.read(N)` (или один read и переиспользование буфера в magic/tag/texty-проверках).

### BUG 7: `ingested_at()` падает на некорректном `SOURCE_DATE_EPOCH`
- **Файл:** `src/librarian/emit.py:94–97`
- **Severity:** Low
- **Type:** logic / robustness
- **Симптом:** Если `SOURCE_DATE_EPOCH` выставлен в не-integer (пустая строка, `garbage`, `1.5`), `ingest` падает с непойманным `ValueError: invalid literal for int()`. Поскольку `ingested_at()` вызывается внутри `emit_book` после всей дорогой работы extract/normalize/structure/validate, одна плохая env-var убивает весь батч (исключение не в per-file `try/except`, конвертирующем ошибки экстрактора в `failed`). Проверено: `SOURCE_DATE_EPOCH="not-a-number"` → `ValueError`.
- **Root cause:** `ts = int(sde) if sde else int(time.time())` — truthiness-проверка ловит только unset/empty; любая нечисловая непустая строка доходит до `int()` и бросает.
- **Fix sketch:** Обернуть парс в `try/except (TypeError, ValueError)`, на плохое значение падать в `int(time.time())` (опционально с warning).

### BUG 8: Дегифенизация убивает дефис для частицы «ка», вопреки §6.1.2 и `keep_hyphen_suffixes`
- **Файл:** `src/librarian/extractors/textrules.py:37`
- **Severity:** Low (data-correctness; осознанное, но **недокументированное** отклонение)
- **Type:** dehyphenation / spec-conformance
- **Симптом:** Спец §6.1.2 и `[clean] keep_hyphen_suffixes = ["то","либо","нибудь","ка","таки"]` требуют: перенос, чей следующий фрагмент в списке, сращивать **с сохранением дефиса**. Для `ка` код делает обратное: `ну-` + `ка пошёл` → `нука пошёл` (дефис удалён), проверено. Word-break `нау-` + `ка` → `наука` — корректен, но легитимная частица `ну-ка`/`давай-ка` молча портится. Inline-комментарий открыто признаёт отклонение (проза-переносы типа `нау-ка`/`ру-ка` чаще), но **в спец его нет** (§0-bis строка 0.24 описывает только suffix-list решение, без исключения для «ка»).
- **Root cause:** `if suffix in cfg.clean.keep_hyphen_suffixes and suffix != "ка":` — клауза `and suffix != "ка"` гасит keep-запись ровно для одного суффикса.
- **Fix sketch:** Judgment call. Если отклонение предполагалось — занести в спец в список «принятый дефект» и задокументировать асимметрию; если нет — убрать `and suffix != "ка"`, чтобы «ка» хранила дефис как остальные частицы. (`test_textrules.py` кейс «ка»-keep не покрывает, отклонение сейчас не охраняется.)

### BUG 9: `smoke_wheel.sh` течёт временными venv/data-директориями (нет cleanup)
- **Файл:** `scripts/smoke_wheel.sh:6–9`
- **Severity:** Low
- **Type:** shell / test-cleanup
- **Симптом:** `VENV=$(mktemp -d)/venv` создаёт temp-директорию, чей *родитель* (`/tmp/tmp.XXXX/`) никогда не удаляется; `TMP=$(mktemp -d)` (строка 9) — тоже. Каждый smoke-run (и каждый `RUN_INSTALL_TESTS=1` CI-запуск) оставляет два temp-дерева, копясь бесконечно.
- **Root cause:** Нет `trap 'rm -rf …' EXIT`; оба `mktemp -d`-корня осиротены.
- **Fix sketch:** Сохранить оба корня в переменные и добавить `trap 'rm -rf "$VENV_ROOT" "$TMP"' EXIT` (родителя venv держать отдельно от `$VENV`).

### BUG 10: `rm` принимает произвольный `book_id` без защиты от path-traversal (только проверка существования `book.json`)
- **Файл:** `src/librarian/cli.py:132–141` (`target = lib / book_id; ... shutil.rmtree(target)`)
- **Severity:** Low
- **Type:** cli
- **Симптом:** `book_id` джойнится в путь и `rmtree`'ится. Значение типа `../sibling` резолвится за пределами корня библиотеки; единственный барьер — проверка `(target/"book.json").is_file()` на строке 139. Если по этому пути реально лежит `book.json` (напр. соседняя библиотека под тем же родителем), `rm` снёс бы чужое дерево. Против самой библиотеки сейчас не эксплуатируется, но хрупко.
- **Root cause:** Нет валидации, что `book_id` — один сегмент пути / что `(lib / book_id).resolve()` остаётся внутри `lib.resolve()`.
- **Fix sketch:** Резать id с path-сепараторами или точками, напр. требовать `^[A-Za-z0-9._-]+$` и `"/" not in book_id`, либо `assert (lib/book_id).resolve().is_relative_to(lib.resolve())` перед любым удалением.

---

## Проверено и осознанно НЕ отмечено как баг

Перечислено для прозрачности охвата (агенты это явно проверили и отвергли):

- **Crash-recovery / атомарность (§12.4, С-8):** порядок `publish()` (target→`.trash`, staging→target, rmtree `.trash`) и `recover()` соответствуют спец. `index.json` пишется атомарно через tmp + `os.replace`. Сценарии within-batch / stale-trash / окна краша на шаге 2/3 восстанавливаются. `test_recovery.py` проходит и его ассерты осмысленны.
- **Идемпотентность / identity (§13, С-1, К-1):** `cache_key = sha:PIPELINE_VERSION:config_hash` корректен; повторный non-force ingest — истинный no-op (`test_cache`); `--force` переиспользует id через `find_by_sha256`; суффикс коллизии `-{sha[:6]}` соответствует §12.1 и стабилен. `meta_locked` (С-2) соблюдается.
- **Детерминизм (С-10):** никаких несортированных set/dict-итераций на выходном пути; `config_hash` стабилен; `SOURCE_DATE_EPOCH` управляет `ingested_at`. Тест на детерминизм (два `PYTHONHASHSEED`) удовлетворяется.
- **Кодировки/детект (cp1251/koi8):** `_read_text` → charset_normalizer + Cyrillic vowel-score fallback по фиксированному порядку с детерминированной сортировкой; BOM-обработка корректна; CRLF нормализуется; decode-ошибки не глотаются.
- **Токены (`tokens.py`):** o200k_base вендорен с sha256-проверкой, `pat_str`/`special_tokens` корректны, `disallowed_special=()` считает specials как текст. Нет cl100k/o200k-путаницы.
- **Render/emit:** `_render_code`/`_render_table`, `canonical_json` (sort_keys + trailing `\n`), `chapter_filename`/`_PART_SUFFIX`, `build_summary`/`_cut_300` соответствуют §12.2–12.5 и проходят тесты.
- **xmlsafe:** `resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False` по спец §6.0; XXE-тест проходит.
- **Normalize:** `_INVISIBLE`/`_CONTROL` корректны по спец N1; идемпотентность проверена.
- **Quality:** деления на ноль нет (empty-chapters под защитой); веса суммируются в 1.0 → score ∈ [0,1]; coverage/garbage/encoding/dehyphen-сабскорсы захардкожены в 1.0 — это задокументированный M1-стаб (§18 «заглушка»), не баг.
- **Упаковка (К-4):** НЕ баг. Несмотря на отсутствие явного `package-data` в `pyproject.toml`, собранные wheel/sdist включают `librarian/assets/o200k_base.tiktoken` и `__main__.py` (hatchling включает всё под package-директорией по умолчанию).
- **Entry point `lib = "librarian.cli:app"`:** НЕ баг. `app` — callable `typer.Typer`; `entry_points.txt` в wheel корректен.
- **stdout/stderr reconfigure (С-6):** НЕ баг. Callback `_main` выполняется до субкоманд и реконфигурирует объект на месте; module-level `_err` держит ссылку на тот же объект.
- **«list table title deviation»:** НЕ баг. Косметическая метка колонки, данные корректны.
- **Exit-коды реализованных команд:** корректны (`ingest` exit 1 только на `failed`; `get`/`list`/`info`/`rm` exit 1 на `LibError`; `parse_spec` режет `1-3-5`/`5-3`/вне-диапазона).
- **Golden/determinism/cache-тесты:** корректны и не флапают (`SOURCE_DATE_EPOCH=0` через `monkeypatch` с авто-откатом; `tmp_path`; нет session-scoped mutable state).
