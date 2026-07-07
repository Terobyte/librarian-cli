# bugs.md — найденные баги `librarian`

Дата ревью: 2026-07-06.
Три параллельных агента (pipeline, extractors/emit, CLI/tests/config), область действия непересекающаяся.
Каждый баг свернут с конкретным симптомом, первопричиной и наброском фикса.
Спецификация — `librarian-spec-v2.2.md`. Документированные-как-принятые отклонения в список не входят (кроме случаев, явно отмеченных как «недокументированное отклонение»).

Всего: **10 багов** (0 Critical / 1 High / 5 Medium / 4 Low).

---

## Ревью №2 (5 параллельных агентов, 2026-07-07)

Пять доменов с непересекающейся областью действия: **A** экстракторы, **B** ядро/IR (structure/passes/tokens/detect), **C** пайплайн/вывод/качество, **D** CLI/config/упаковка, **E** тесты + сквозные (безопасность/детерминизм/edge-cases). Повторного прогона потребовали упавшие на первом проходе агенты B и C.

Каждая находка **подтверждена эмпирически** (запуском кода на сконструированном входе); ложные срабатывания отброшены явно в конце секции. Сводка верификации:

| BUG | Агент | Severity | Эмпирическая верификация |
|-----|-------|----------|--------------------------|
| F-1 path traversal в `get` через `book.json:file` | E | **High** | ✅ прочитан `/tmp/.../secret.txt` («TOP SECRET LEAK») из библиотеки |
| F-2 R2 ложно удаляет главу, повторяющую свой заголовок | B | **High** | ✅ глава «Часть первая · Вступление» исчезла из результата |
| F-3 `[quality.weights]` partial-override → `KeyError`, весь батч падает | C | **High** | ✅ `cfg.quality.weights == {'coverage': 0.5}` (4 ключа потеряны) |
| F-4 TXT: разделитель абзацев игнорирует whitespace-only строки | A | **High** | ✅ 3 абзаца + заголовок склеились в 1 PARA |
| F-5 MD fallback сплющивает иерархию заголовков в level=1 | A | **High** | ✅ MD даёт 1/1, TXT-эталон §6.1.3 даёт 1/2 |
| F-6 MD fence закрывается по префиксу, теряя контент | A | Medium | ✅ `` ```text `` внутри кода обрезает блок |
| F-7 `lib list` роняет сырой traceback на битом `index.json` | D | Medium | ✅ `KeyError: 'books'` и `JSONDecodeError` (exit 1, traceback) |
| F-8 `[chapters.patterns]` overlay заменяет словарь целиком | D | Medium | ✅ override `rank1` обнуляет `rank3` (главы не детектятся) |
| F-9 зашифрованная zip-запись → сырой `RuntimeError` (не `BrokenFileError`) | E | Medium | ✅ `RuntimeError: File ... is encrypted` прошёл мимо `except BadZipFile` |
| F-10 `extract_timeout_s` объявлен, но не применяется (§6.0) | E | Medium | ✅ grep: 0 использований вне `config.py:25` |
| F-11 R4.3 `_force_split` не режет блок без границ предложений/строк | B | Medium | ✅ 35k-токенный блок возвращён как 1 кусок |
| F-12 `normalize_heading_levels` падает на `HEADING(level=None)` | B | Low | ✅ `TypeError: '<' not supported int × NoneType` |
| F-13 `report.json` без полей `pages_flagged`/`multi_column_pages` | C | (M4) | ✅ полей нет ни в `ReportDraft`, ни в `build_report` |

**Итого: 13 багов** (0 Critical / 5 High / 6 Medium / 1 Low / 1 вне-scope-M1). См. секции ниже по severity.

---

## Итог фазы фиксов №2 (2026-07-07)

Каждый фикс закрыт собственным тестом. Итог сюиты: **197 passed, 1 skipped, 2 xfailed, 1 xpassed, 0 failed**.

| BUG | Вердикт | Действие |
|-----|---------|----------|
| F-1 path traversal в `get` | ✅ пофикшен | `cli.get`: `resolve()` пути главы + `is_relative_to(book_dir)` → `LibError` на выход за пределы. Тест `test_get_path_traversal_protection` |
| F-2 R2 ложно удаляет self-repeating главу | ✅ пофикшен | вычитаются все сегменты path-title (`ch.title.split(" · ")`), не путь целиком. Тест `test_r2_toc_does_not_drop_self_repeating_chapter` |
| F-3 `[quality.weights]` partial-override → `KeyError` | ✅ пофикшен | `load_config` мёрджит weights с `_default_weights()` (dict-update, §14 overlay). Тест `test_config_quality_weights_partial_override` |
| F-4 TXT: whitespace-only строки не разделяют абзацы | ✅ пофикшен | split по `_PARA_SEP = r"\n[ \t]*\n"` вместо литерального `"\n\n"`. Тест `test_txt_whitespace_only_paragraph_separator` |
| F-5 MD fallback сплющивает иерархию | ✅ пофикшен | `_fallback_patterns` → общий `apply_patterns_to_blocks` (как DOCX): глобальное сжатие рангов. Тест `test_md_fallback_retains_hierarchy` |
| F-6 MD fence закрывается по префиксу | ✅ пофикшен | закрывающий fence — только бэктики, длина ≥ opening (CommonMark). Тест `test_md_code_block_fence_prefix_safety` |
| F-7 `lib list` traceback на битом `index.json` | ✅ пофикшен | `except (LibError, KeyError, ValueError)` → «индекс библиотеки повреждён: …», exit 1. Тест `test_list_corrupted_index_json` |
| F-8 `[chapters.patterns]` overlay заменяет словарь | ✅ пофикшен | мёрдж с `_default_patterns()` перед заменой. Тест `test_config_patterns_partial_override` |
| F-9 зашифрованная zip-запись → `RuntimeError` | ✅ пофикшен | явная проверка `flag_bits & 0x1` в `check_zip`/`read_entry` + `except RuntimeError` → `BrokenFileError`. Тест `test_encrypted_zip_raises_broken_file_error` |
| F-10 `extract_timeout_s` не применяется | ✅ пофикшен | `_extract_with_timeout` (`signal.alarm`, POSIX) вокруг `extract()` → `LimitError("извлечение зависло")`. Тест `test_extract_timeout_enforcement` |
| F-11 `_force_split` не режет блок без границ | ✅ пофикшен | единственный юнит > target → фолбэк на пословный разрез. Тест `test_force_split_no_boundaries` |
| F-12 `normalize_heading_levels` падает на `level=None` | ✅ пофикшен | фильтр `None` в сборе уровней + fallback-уровень через `remap.get`. Тест `test_normalize_heading_levels_none_level` |
| F-13 `report.json` без `pages_flagged`/`multi_column_pages` | ⏸ **вне scope M1** | отложен — поля заполняют PDF-проходы P3/P4 этапа **M4** (§18). Тест → `xfail(reason=M4)` как броня: `test_report_has_required_m4_pdf_fields` |

**Итог:** 12 из 13 багов пофикшено (5 High / 6 Medium / 1 Low), 1 отложен как фича этапа M4 с xfail-бронёй. Ложноположительных в этом ревью не было (кандидаты отброшены на этапе верификации, см. «отброшенные гипотезы»).

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

# Ревью №2 — детальные находки (2026-07-07, 5 агентов)

## High

### BUG F-1: Path traversal в `get` через поле `file` в `book.json` — чтение произвольных файлов вне библиотеки
- **Файл:** `src/librarian/cli.py:107–111` (команда `get`); ср. с защитой в `rm` (`cli.py:144–149`)
- **Severity:** High
- **Type:** security (path traversal / arbitrary file read)
- **Симптом:** Команда `get` читает главу как `(lib_root / book_id / by_n[n]["file"]).read_text(...)`, где `file` берётся **из `book.json` без какой-либо валидации**. Эмпирически подтверждено: `book.json` с `"file": "../../secret.txt"` → `lib get <id> 1` печатает содержимое файла за пределами библиотеки. В тесте прочитан `/tmp/.../secret.txt` («TOP SECRET LEAK CONTENT HERE») из библиотеки `…/library/evil/`. Exit 0, без ошибок.
- **Root cause:** В `rm` есть защита (`resolved.is_relative_to(lib.resolve())`, проверка на `/`/`\\` в `book_id`), но в `get` её нет, и сам путь файла из `book.json` не проверяется. `read_book` (`catalog.py:46`) тоже собирает `lib_root / book_id` без проверки `book_id`. Вектор: скомпрометированный/враждебный `book.json` (или атакующий, который может писать в `library/<id>/book.json`) читает любые файлы под пользователем, запускающим `lib get`.
- **Fix sketch:** В `get`/`info` валидировать `book_id` (как в `rm`) и проверять, что `(lib_root / book_id / file).resolve()` остаётся внутри `lib_root.resolve()`; иначе `LibError("недопустимый путь главы")`. Вынести в общую helper-функцию и применить ко всем командам чтения.

### BUG F-2: R2 (TOC) ложно удаляет главу, тело которой повторяет её собственный заголовок
- **Файл:** `src/librarian/passes/sections.py:53` (`others = headings - {_canon(ch.title)}`)
- **Severity:** High
- **Type:** logic / spec-deviation (§9 R2b) / потеря контента
- **Симптом:** Глава, тело которой состоит из строк, совпадающих с её **собственным** заголовком (≥80% строк), ложно удаляется как «печатное оглавление». Эмпирически: глава `Часть первая · Вступление` с телом из 5 строк `Вступление` исчезает из результата (`len(result) < 2`), хотя ни одна строка не совпадает с заголовками **других** глав. Теряется легитимный контент.
- **Root cause:** Намерение строки 53 — исключить заголовок **текущей** главы из множества `headings`. Но `ch.title` — это **заголовок-путь** (§8.4, напр. `«Часть первая · Вступление»`), а `headings` (строки 43–44) содержит **исходные** тексты HEADING-блоков (напр. `«Вступление»`). `_canon(path-title) == 'часть первая · вступление'` никогда не равен `_canon('Вступление') == 'вступление'`, поэтому вычитание холостое: собственный заголовок главы остаётся в `others`, и повторяющие его строки засчитываются как `dup` → ложное срабатывание R2. Спека §9 R2(b) прямо требует сопоставлять с заголовками **других** глав и уточняет «не с заголовками-путями — печатное оглавление содержит именно исходные названия».
- **Fix sketch:** Вычитать исходные заголовки, принадлежащие именно этой главе. Варианты: (а) хранить на главе ссылку на её сырые HEADING-тексты и вычитать это множество; (б) быстрый приближённый фикс — `_canon(ch.title.split(" · ")[-1])` (последний сегмент пути = исходный заголовок уровня разреза).

### BUG F-3: Частичное переопределение `[quality.weights]` в config.toml валит весь батч (`KeyError`)
- **Файл:** `src/librarian/quality.py:36` (`sum(w[k] * subscores[k] …)`); первопричина в `src/librarian/config.py:159–160` (полная замена dict)
- **Severity:** High
- **Type:** config / crash (spec-deviation)
- **Симптом:** Любой `config.toml`, переопределяющий хотя бы один вес в `[quality.weights]`, вызывает `KeyError` внутри `score_and_status` → ingest падает с traceback для каждого файла пакета. Эмпирически: `[quality.weights]\ncoverage = 0.5` → `cfg.quality.weights == {'coverage': 0.5}` (4 ключа потеряны), затем `quality.py:36` падает на первом отсутствующем ключе.
- **Root cause:** `load_config` не мёрджит `weights`, а полностью заменяет dict тем, что пришло из TOML. Спека §14 описывает `[quality.weights]` как таблицу с пятью независимыми ключами — пользователь ожидает partial-override семантику (как у скалярных полей). Та же болезнь у сестёр-полей `garbage`/`encoding`/`dehyphen`, если они когда-либо станут dict'ами.
- **Fix sketch:** Слить `weights` с дефолтами в `load_config` (dict-update вместо замены): `merged = _default_weights(); merged.update(section[...]); cfg.quality.weights = merged`. Дополнительно в `score_and_status` использовать `w.get(k, 0.0)` как защиту в глубину.

### BUG F-4: TXT-разделитель абзацев игнорирует строки из одних пробелов/табов
- **Файл:** `src/librarian/extractors/txt.py:64` (`text.split("\n\n")`)
- **Severity:** High
- **Type:** logic / edge case (потеря структуры)
- **Симптом:** Два абзаца, разделённые «пустой» строкой из пробелов/табов, склеиваются в один. Эмпирически: `'Вступительный текст…\n \nГлава 1\n\t\nТекст первой главы…'` → **1 PARA** `'Вступительный текст… Глава 1 Текст первой главы…'` (3 абзаца + заголовок стали одним блоком; заголовок «Глава 1» не детектится).
- **Root cause:** `text.split("\n\n")` разбивает только по точно двум подряд идущим `\n`. Разделитель `\n \n` или `\n\t\n` не содержит подстроки `\n\n`, поэтому не разбивается. Спека §6.1.2 говорит «разделитель — одна и более **пустых** строк»; строка из пробелов/табов семантически пуста. Примечательно, что экстрактор *уже* фильтрует whitespace-строки внутри чанка (`if ln.strip()`, строка 65), но на этапе разбиения это не используется.
- **Fix sketch:** Нормализовать разделители перед split: `re.split(r"\n[ \t]*\n", text)` или `re.sub(r"(?:[ \t]*\n){2,}", "\n\n", text)` — тогда whitespace-only строки корректно становятся границами абзацев.

### BUG F-5: MD fallback сплющивает иерархию заголовков в level=1 (расхождение с TXT-эталоном §6.1.3)
- **Файл:** `src/librarian/extractors/md.py:43–52` (`_fallback_patterns` вызывает `apply_heading_patterns` по одному блоку)
- **Severity:** High
- **Type:** logic / spec-deviation (§6.1.3)
- **Симптом:** MD-файл без markdown-заголовков (`#`/setext), но с текстовыми паттернами глав, теряет иерархию. Эмпирически: `'Том 1\n\nГлава первая\n\n…\n\nГлава вторая\n\n…'` → MD даёт **все level=1** (`Том 1`/`Глава первая`/`Глава вторая`), тогда как TXT-эталон §6.1.3 даёт корректную иерархию **1/2/2** (ранги 1,3 сжаты в уровни 1,2).
- **Root cause:** `_fallback_patterns` вызывает `apply_heading_patterns` **по одному блоку за раз**. Внутри `apply_heading_patterns` сжатие рангов в уровни (`level_of = {r: i+1 for i, r in enumerate(present)}`) делается по множеству рангов *текущего вызова* — а в каждом вызове ровно один ранг, поэтому он всегда становится уровнем 1. Контраст: DOCX-экстрактор использует `apply_patterns_to_blocks` (`textrules.py:78`), который обрабатывает **все** блоки вместе с общим сжатием рангов (`sorted(set(ranks.values()))`, строка 88) — и работает правильно.
- **Fix sketch:** Заменить тело `_fallback_patterns` одним вызовом `apply_patterns_to_blocks(blocks, cfg)` (той же функции, что использует DOCX) — это даст корректное глобальное сжатие рангов и уберёт дублирование логики.

---

## Medium

### BUG F-6: MD fence закрывается по префиксу, теряя контент code-блока
- **Файл:** `src/librarian/extractors/md.py:79` (`not lines[i].strip().startswith(fence)`)
- **Severity:** Medium
- **Type:** logic / edge case (потеря контента)
- **Симптом:** Строка вида `` ```text `` (3+ бэктика **с текстом**) внутри code-блока ошибочно закрывает его. Эмпирически: `` ```\ncode line\n```text\nmore code\n``` `` → блоки `CODE('code line')`, `PARA('more code')`, `CODE('')`; строка `text` поглощена как info-строка несуществующего внутреннего fence, а `more code` выпал в PARA. По CommonMark закрывающий fence обязан состоять только из бэктиков (+ опц. пробелы).
- **Root cause:** Условие цикла срабатывает на любую строку, *начинающуюся* с открывающей fence-строки, включая строки с добавочным текстом. Спека §6.2.2 говорит «содержимое дословно»; некорректное раннее закрытие нарушает это для triple-backtick-подобных строк.
- **Fix sketch:** Проверять, что stripped-строка состоит *только* из бэктиков и её длина ≥ длины открывающего fence: извлечь голые бэктики из `m.group(1)` и сравнивать `lines[i].strip() == fence_backticks` (с учётом длины).

### BUG F-7: `lib list` роняет сырой traceback на битом/неполном `index.json`
- **Файл:** `src/librarian/cli.py:84` (`json.loads(idx_path.read_text(...))["books"]` внутри `try/except LibError`)
- **Severity:** Medium
- **Type:** cli / error-handling (spec §16)
- **Симптом:** Эмпирически подтверждено: `index.json` = `{"notbooks": 1}` → непойманный `KeyError: 'books'` + полный traceback, exit 1; `index.json` = `NOT JSON` → `JSONDecodeError` + traceback. Спека §16 требует человекочитаемое сообщение, не Python-traceback.
- **Root cause:** `KeyError` и `json.JSONDecodeError` — не подклассы `LibError`, поэтому проходят мимо `except LibError`. Путь `scan_books` для `rebuild_index` работает корректно (warning + пропуск), но прямое чтение `index.json` в `list` не защищено.
- **Fix sketch:** Расширить `except` в `list_cmd` до `(LibError, KeyError, ValueError)` (`JSONDecodeError` — подкласс `ValueError`) и печатать `f"индекс библиотеки повреждён: {e}"` + exit 1. Лучше — валидировать форму внутри `try`.

### BUG F-8: `[chapters.patterns]` overlay заменяет словарь целиком — частичное переопределение теряет дефолт-паттерны
- **Файл:** `src/librarian/config.py:159–160` (`{k: tuple(v) for k, v in sorted(section[f.name].items())}`)
- **Severity:** Medium
- **Type:** config / spec-deviation
- **Симптом:** TOML `[chapters.patterns]` с любым одним рангом удаляет стандартные шаблоны для всех остальных. Эмпирически: `[chapters.patterns]\nrank1 = ["^томь?"]` → `rank1` имеет 1 паттерн, `rank3` — **0** → «Глава N», римские цифры, числовые заголовки больше не детектятся. Модель оверлея спеки §14 («config.toml — оверлей») подразумевает слияние для каждого ранга.
- **Root cause:** Полная замена таблицы без объединения с `_default_patterns()`. Сестринский баг F-3 (та же первопричина для `weights`).
- **Fix sketch:** Начать с `dict(_default_patterns())`, затем `merged.update({k: tuple(v) for k, v in section["patterns"].items()})`. Либо задокументировать поведение полной замены в спецификации.

### BUG F-9: Зашифрованная zip-запись → сырой `RuntimeError` вместо `BrokenFileError`
- **Файл:** `src/librarian/extractors/zipsafe.py:13–34` (`check_zip`) и `:36–50` (`read_entry`)
- **Severity:** Medium
- **Type:** resource / error-handling (spec §6.0)
- **Симптом:** Эмпирически: zip с записью, помеченной флагом шифрования (`flag_bits & 0x1`), проходит `detect._detect_zip` (который проверяет флаг только на верхнем уровне архива), а `check_zip` вызывает `z.open(info)` → `RuntimeError: File '...' is encrypted, password required for extraction` выходит **мимо** `except zipfile.BadZipFile`. Сообщение в `IngestOutcome.message` становится английским `RuntimeError: …`, а не локализованным/специфичным. Затрагивает FB2-inside-zip и XHTML-inside-EPUB, где шифрование может быть на отдельной внутренней записи.
- **Root cause:** `check_zip`/`read_entry` ловят только `BadZipFile` и `KeyError`, не дублируя проверку `flag_bits & 0x1`, которая есть в `detect._detect_zip` (detect.py:39).
- **Fix sketch:** В `check_zip` добавить явную проверку `if any(i.flag_bits & 0x1 for i in infos): raise BrokenFileError(f"{path.name}: зашифрованная запись")` до цикла `z.open`; в `read_entry` ловить `RuntimeError` → `BrokenFileError`.

### BUG F-10: `extract_timeout_s` объявлен, но нигде не применяется (зависший парсер валит ingest)
- **Файл:** `src/librarian/config.py:25` (определение); отсутствие — `src/librarian/pipeline.py`/`extractors/*`
- **Severity:** Medium
- **Type:** resource / spec-deviation (§6.0)
- **Симптом:** Спека §6.0 (строка 335) требует: «`extract()` одного файла ограничен `limits.extract_timeout_s` (120 с); по истечении — `failed` с сообщением "извлечение зависло"». В коде лимит **не реализован** — `grep extract_timeout` находит только декларацию поля и текст спеки. Зависший парсер (цикл в trafilatura, рекурсивный XML) повесит ingest навсегда вместо того, чтобы дать `failed` одному файлу и продолжить пакет.
- **Root cause:** M1-каркас не дотянул таймаут; есть `max_source_mb`/`zip_max_uncompressed_mb`/zip-ratio, а таймаут забыли.
- **Fix sketch:** Обернуть вызов `get_extractor(fmt).extract(...)` в `_safe_ingest` в таймаут (`signal.alarm` на POSIX / `threading.Timer` fallback), по срабатыванию → `LimitError("извлечение зависло")` → обычный путь `failed`.

### BUG F-11: R4.3 `_force_split` не режет блок без границ предложений/строк — нарушается потолок `part_target_tokens`
- **Файл:** `src/librarian/passes/sections.py:161–181` (`_force_split`)
- **Severity:** Medium
- **Type:** logic / spec-deviation (§9 R4.3) / edge case
- **Симптом:** Одиночный блок PARA/QUOTE/CODE/TABLE > `max_tokens` (8000), не содержащий ни одного `. ! ?` (PARA/QUOTE) или ни одного `\n` (CODE/TABLE), принудительно **не режется** и остаётся одним куском > `part_target_tokens` (6000). Эмпирически: блок в 35000 токенов без знаков препинания возвращается из `_force_split` как 1 кусок.
- **Root cause:** `_SENT_SPLIT.split(...)` / `text.split("\n")` порождают ровно один юнит (весь текст). Жадный накопитель сбрасывает буфер только **между** юнитами — условие `if cur and cur_tokens + t > target` (строки 174, 178) не срабатывает для единственного юнита (`cur` пуст на первой итерации, юнит просто добавляется). Внутри юнита разрез никогда не происходит.
- **Fix sketch:** Добавить хвостовой разрез для юнита, превышающего `target`: если после `_force_split` остался блок > `target`, резать его по символам/токенам на части ≤ `target` (с пометкой `origin` и инкрементом `oversize_blocks_split`), чтобы гарантировать инвариант §9 R4.3 «на куски ≤ `part_target_tokens`».

---

## Low / вне-scope

### BUG F-12: `normalize_heading_levels` падает на HEADING с `level=None`
- **Файл:** `src/librarian/structure.py:11` (`sorted({b.level for b in blocks if b.kind is BlockKind.HEADING})`)
- **Severity:** Low
- **Type:** robustness / необработанный edge case
- **Симптом:** Эмпирически: любой HEADING-блок с `level=None` → `TypeError: '<' not supported between instances of 'int' and 'NoneType'` в `sorted()`. Затем `remap[b.level]` дал бы `KeyError`.
- **Root cause:** Множество уровней собирается без фильтра `None`. Спека-инвариант (§4) требует, чтобы `level` был заполнен у всех HEADING после NORMALIZE — баг проявляется только если экстрактор нарушит контракт, поэтому Low. Но как необработанный краш-путь внутри ядра заслужен.
- **Fix sketch:** Фильтровать `None`: `levels = sorted({b.level for b in blocks if b.kind is BlockKind.HEADING and b.level is not None})` (и пропускать такие блоки в цикле remap либо назначать fallback-уровень).

### BUG F-13: `report.json` без обязательных полей `pages_flagged` и `multi_column_pages` (вне scope — этап M4)
- **Файл:** `src/librarian/quality.py:47–64` (`build_report`); отсутствуют поля в `src/librarian/ir.py:62` (`ReportDraft`)
- **Severity:** (вне scope M1) — спека §18 ставит полный `report.json` schema и PDF-проходы P3/P4 в этап **M4**
- **Type:** spec-deviation (§11.6, §12.3 schema)
- **Симптом:** Сгенерированный `report.json` никогда не содержит `pages_flagged` и `multi_column_pages`, которые спека §11.6 (строки 620–621) перечисляет как обязательные поля. В `ReportDraft` для них тоже нет полей. Поле `multi_column_pages` критично: §11.2/§7.2 P3 завязывает на него жёсткий триггер review (доля >10%); `pages_flagged` нужно для `lib doctor`.
- **Root cause:** `build_report` собирает словарь вручную и не включает эти поля; PDF-проходы P3/P4 (которые должны их заполнять) — часть нереализованного этапа M4.
- **Fix sketch:** На этапе M4: добавить поля `pages_flagged: list[int]` и `multi_column_pages: list[int]` в `ReportDraft`, заполнять в P3/P4, всегда эмитить в `build_report` (дефолт `[]`).

---

## Ревью №2 — проверено и осознанно НЕ отмечено (отброшенные гипотезы)

Для прозрачности охвата: кандидаты, которые агенты выдвинули, но верификация их отвергла.

- **ReDoS в паттернах заголовков `[а-яёa-z]+` (агент E, кандидат E-6):** ❌ **не подтвердилось.** Эмпирически: `re.fullmatch(pattern, 'а'*50000)` — 0.0004 с; с разделителем `—` — 0.0000 с. Якоря `^…$` + `fullmatch` отсекают несовпадение в начале (`том|книга|…`), катастрофического backtracking нет. Низкий риск.
- **Атомарность `recover()` (агент C, кандидат C-3):** ❌ **ложное.** Порядок шагов (trash-rollback → delete `.staging` → delete `.trash`) соответствует §12.4; эмпирические тесты (две книги в trash, одна с отсутствующим таргетом) проходят корректно, data-loss не воспроизводится.
- **Shallow-collapse в `choose_cut_level` §8.3 (агент B):** ❌ **ложное.** Shallow-check ограничен условием `L == cut_level_start`; в этом случае deepen не сработал и `med` действительно равен медиане start-уровня. Корректно.
- **Порядок `os.replace` в `publish()` (агент E, кандидат E-2 — «хрупкий мок»):** замечание о тесте `crashy()` (магический индекс `== 2`), но это замечание о **качестве теста**, не о баге продакшн-кода; `publish()` работает верно.

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
