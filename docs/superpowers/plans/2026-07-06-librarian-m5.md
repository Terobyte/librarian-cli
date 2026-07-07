# Librarian M5 «полировка» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** довести инструмент до DoD спеки: `lib get --budget` (§15), `lib reingest --all` (§13), таймаут извлечения `extract_timeout_s` (§6.0), тесты без сети, перф-смоук (§17), CI-матрица 3 ОС × Python 3.11/3.13 с офлайн-установкой из wheel (§17/§18), README. `meta_locked` реализован в M1 (pipeline шаг 12) — здесь закрывается e2e-тестом через reingest. Этап M5 из §18.

**Architecture:** Всё — обвязка вокруг готового конвейера, выходные байты книг не меняются → `PIPELINE_VERSION` не трогаем, golden не регенерируются (это проверка каждой задачи). `reingest` переиспользует `ingest_file` с явным `book_id` (К-1: id стабилен). Таймаут — отдельный процесс-исполнитель (`multiprocessing`, spawn) на файл: единственный кроссплатформенный способ убить зависший нативный парсер; в тестах отключается через env `LIB_EXTRACT_INPROCESS=1` (отклонение 22), сам guard тестируется явно.

**Tech Stack:** stdlib (`multiprocessing`), pytest-socket (новый dev-dep — блокировка сети в тестах), GitHub Actions + uv.

**Скоуп:** только M5 (§18). Вне скоупа: OCR, MOBI, MCP-сервер (§20, v3).

## Global Constraints

- **Предусловие M5 (проверить ДО Task 1):** M3 и M4 полностью выполнены, закоммичены и зелёные. Критично для Task 4: перф-смоук ингестит PDF — без M4 `get_extractor(Format.PDF)` даёт `LibError «формат pdf будет поддержан…»` → outcome `failed`, и тест падает не по той причине, которую проверяет.
- **Выходные байты не меняются:** после каждой задачи `uv run pytest -q` зелёный **без** регенерации golden. Изменение байтов = дефект задачи.
- **Детерминизм (§2)** прежний; wall-clock в перф-смоуке разрешён (тестовый код, не выходной путь).
- **Коды выхода (§15):** 0 — успех (включая review); 1 — ошибка выполнения; 2 — ошибка использования (spec×budget, typer).
- **Данные — stdout, диагностика — stderr (§15).**
- **Ошибки по-русски (§16); пакет не падает.**
- **Коммиты:** короткие, lowercase, без префиксов и Co-Authored-By.
- Рабочая директория: `/Users/terobyte/Desktop/Projects/Active/scripts/libby/librarian/`. Запуск: `uv run pytest`. Git-корень репозитория — уровнем выше (`libby/`), там живёт `.github/`.

---

## File Structure (дельта M5)

```
libby/                              # git-корень
  .github/workflows/ci.yml         # CREATE: матрица ОС × Python + wheel-offline job
  librarian/
    pyproject.toml                 # MODIFY: dev-deps + pytest-socket, addopts, markers
    README.md                      # CREATE
    src/librarian/
      cli.py                       # MODIFY: get --budget/--from, spec×budget; + reingest
      pipeline.py                  # MODIFY: ingest_file(book_id=…), run_reingest, guard
      extractors/guard.py          # CREATE: run_with_timeout, guarded_extract
    tests/
      conftest.py                  # MODIFY: LIB_EXTRACT_INPROCESS=1 для скорости
      unit/_guard_targets.py       # CREATE: picklable-мишени для guard-тестов
      unit/test_guard.py           # CREATE
      unit/test_cli.py             # MODIFY: + budget/exit-коды
      unit/test_pipeline.py        # MODIFY: + reingest, meta_locked e2e
      test_perf.py                 # CREATE: перф-смоук 500 страниц (маркер perf)
```

---

### Task 1: `lib get --budget N [--from K]` и взаимоисключение со `<spec>` (§15)

**Files:**
- Modify: `src/librarian/cli.py` (команда `get`)
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `get(book_id, spec=None, --budget N=None, --from K=1)`. Ровно одно из `spec`/`--budget`, иначе exit 2. Бюджет: жадно подряд главы с K, пока сумма `tokens` ≤ N; не вошедшие — сообщением в stderr; не влезла даже первая → stderr + exit 1. `--from` вне 1..N → stderr + exit 1.
- Consumes: `read_book`, `parse_spec` — уже в cli.py.

- [ ] **Step 1: Красный тест** — дописать в `tests/unit/test_cli.py`:

```python
def _mklib(tmp_path, monkeypatch):
    """Библиотека из инлайн-книги на 4 плоских «Глава N».
    roman_cp1251.txt НЕ годится: резак §8 берёт уровень «Том» → всего 2 главы
    (см. golden/roman_cp1251/index.json), а budget-тестам нужно ≥ 3."""
    from librarian.config import load_config
    from librarian.pipeline import run_ingest
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    src_dir = tmp_path / "_src"
    src_dir.mkdir(exist_ok=True)
    src = src_dir / "chetyre_glavy.txt"
    src.write_text("".join(
        f"Глава {n}\n\n"
        + f"Ровный спокойный абзац главы номер {n} про море и маяк. " * 12
        + "\n\n"
        for n in range(1, 5)), encoding="utf-8")
    out = run_ingest([src], load_config(None), tmp_path)[0]
    assert out.status == "ok" and out.book_id, out.message
    return out.book_id


def test_get_spec_and_budget_mutually_exclusive(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from librarian.cli import app
    bid = _mklib(tmp_path, monkeypatch)
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "get", bid,
                                 "1", "--budget", "1000"])
    assert r.exit_code == 2
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "get", bid])
    assert r.exit_code == 2                                    # ни spec, ни budget
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "get", bid,
                                 "1", "--from", "2"])
    assert r.exit_code == 2                                    # --from только с --budget


def test_get_budget_greedy_consecutive(tmp_path, monkeypatch):
    import json
    from typer.testing import CliRunner
    from librarian.cli import app
    bid = _mklib(tmp_path, monkeypatch)
    book = json.loads((tmp_path / bid / "book.json").read_text(encoding="utf-8"))
    toks = [c["tokens"] for c in book["chapters"]]
    budget = toks[0] + toks[1]                                 # ровно первые две
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "get", bid,
                                 "--budget", str(budget)])
    assert r.exit_code == 0
    assert book["chapters"][0]["title"] in r.stdout
    assert book["chapters"][1]["title"] in r.stdout
    assert book["chapters"][2]["title"] not in r.stdout


def test_get_budget_from_k(tmp_path, monkeypatch):
    import json
    from typer.testing import CliRunner
    from librarian.cli import app
    bid = _mklib(tmp_path, monkeypatch)
    book = json.loads((tmp_path / bid / "book.json").read_text(encoding="utf-8"))
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "get", bid,
                                 "--budget", str(book["chapters"][2]["tokens"]),
                                 "--from", "3"])
    assert r.exit_code == 0
    assert book["chapters"][2]["title"] in r.stdout
    assert book["chapters"][0]["title"] not in r.stdout


def test_get_budget_first_chapter_too_big(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from librarian.cli import app
    bid = _mklib(tmp_path, monkeypatch)
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "get", bid,
                                 "--budget", "1"])
    assert r.exit_code == 1 and r.stdout == ""                 # stdout не загрязняем
```

Про потоки: typer ≥ 0.26 вендорит click, его `CliRunner` **всегда** разделяет `stdout`/`stderr` (параметра `mix_stderr` не существует) — ассерты на `r.stdout` валидны; переиспользовать модульный `runner = CliRunner()` из шапки файла.

В `tests/unit/test_cli.py` уже лежат заготовки `test_get_budget_spec_conflict` и `test_get_budget_and_from_options` с маркером `@pytest.mark.xfail(..., strict=False)` («фича M5»): снять с них xfail; если их ассерты дублируют новые тесты — удалить заготовки в пользу новых (XPASS-мусор в прогоне не оставлять).

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: FAIL — `--budget` неизвестная опция (exit 2 там, где ждём 0) и/или spec обязателен.

- [ ] **Step 3: Реализация** — заменить команду `get` в `src/librarian/cli.py`:

```python
@app.command()
def get(book_id: str,
        spec: str = typer.Argument(None),
        budget: int = typer.Option(None, "--budget", help="лимит токенов"),
        from_: int = typer.Option(1, "--from", help="первая глава для --budget")) -> None:
    if (spec is None) == (budget is None):                    # §15: ровно одно из двух
        _err.print("нужно ровно одно из: <spec> или --budget")
        raise typer.Exit(2)
    if spec is not None and from_ != 1:                       # молчаливый игнор — ловушка
        _err.print("--from работает только вместе с --budget")
        raise typer.Exit(2)
    try:
        book = read_book(_lib_root(), book_id)
        chaps = sorted(book["chapters"], key=lambda c: c["n"])
        if spec is not None:
            nums = parse_spec(spec, len(chaps))
        else:
            if not 1 <= from_ <= len(chaps):
                raise ValueError(f"--from {from_} вне 1..{len(chaps)}")
            nums, total = [], 0
            for ch in chaps[from_ - 1:]:
                if total + ch["tokens"] > budget:
                    break
                nums.append(ch["n"])
                total += ch["tokens"]
            if not nums:
                raise ValueError(
                    f"глава {from_} ({chaps[from_ - 1]['tokens']} токенов) "
                    f"не влезает в бюджет {budget}")
            if from_ - 1 + len(nums) < len(chaps):
                first_skipped = chaps[from_ - 1 + len(nums)]["n"]
                _err.print(f"не вошли в бюджет: главы {first_skipped}–{chaps[-1]['n']}")
        by_n = {ch["n"]: ch for ch in chaps}
        texts = [(_lib_root() / book_id / by_n[n]["file"])
                 .read_text(encoding="utf-8") for n in nums]
        sys.stdout.write("\n\n".join(t.rstrip("\n") for t in texts) + "\n")
    except (LibError, ValueError) as e:
        _err.print(str(e))
        raise typer.Exit(1)
```

- [ ] **Step 4: Зелёный**

Run: `uv run pytest tests/unit/test_cli.py -q` → PASS; `uv run pytest -q` → все зелёные, golden не тронуты.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/cli.py tests/unit/test_cli.py
git commit -m "get --budget: greedy consecutive chapters, spec exclusivity"
```

---

### Task 2: `lib reingest --all` (§13) + e2e `meta_locked` (С-2)

**Files:**
- Modify: `src/librarian/pipeline.py` (`ingest_file(book_id=…)`, `run_reingest`)
- Modify: `src/librarian/cli.py` (+`reingest`)
- Test: `tests/unit/test_pipeline.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `ingest_file(path, cfg, lib_root, force=False, book_id: str | None = None)` — явный id пропускает `_resolve_identity` (К-1: reingest знает id заранее); `run_reingest(cfg, lib_root) -> list[IngestOutcome]` — под одним lock, книги без `source/` пропускаются с предупреждением, кэш-совпадение → `skipped` (сообщение M1-кэша «уже в библиотеке» — байты и так идентичны, §2); индекс пересобирается один раз. CLI: `lib reingest --all [--config cfg.toml] [--verbose]`; без `--all` → exit 2.
- Consumes: `scan_books`, `library_lock`, `recover`, `rebuild_index`, `_safe_ingest`.

- [ ] **Step 1: Красный тест** — дописать в `tests/unit/test_pipeline.py`:

```python
def _lib_with_book(tmp_path, monkeypatch):
    from pathlib import Path
    from librarian.config import load_config
    from librarian.pipeline import run_ingest
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    fx = Path(__file__).parent.parent / "fixtures" / "txt" / "roman_cp1251.txt"
    out = run_ingest([fx], load_config(None), tmp_path)[0]
    return out.book_id


def test_reingest_noop_when_cache_key_matches(tmp_path, monkeypatch):
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    from conftest import tree_bytes
    bid = _lib_with_book(tmp_path, monkeypatch)
    before = tree_bytes(tmp_path)
    outcomes = run_reingest(load_config(None), tmp_path)
    assert [o.status for o in outcomes] == ["skipped"]
    assert tree_bytes(tmp_path) == before                     # ни байта не изменилось


def test_reingest_rebuilds_on_config_change_keeps_id(tmp_path, monkeypatch):
    import json
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    bj = tmp_path / bid / "book.json"
    hash_before = json.loads(bj.read_text(encoding="utf-8"))["provenance"]["config_hash"]
    cfg_toml = tmp_path / "cfg.toml"
    cfg_toml.write_text('[general]\npreface_title = "Пролог"\n', encoding="utf-8")
    cfg = load_config(cfg_toml)                               # другой config_hash
    outcomes = run_reingest(cfg, tmp_path)
    assert [o.status for o in outcomes] == ["ok"]
    assert outcomes[0].book_id == bid                         # К-1: id стабилен
    book = json.loads(bj.read_text(encoding="utf-8"))
    assert book["provenance"]["config_hash"] != hash_before   # новый cfg дошёл до provenance


def test_reingest_preserves_meta_locked(tmp_path, monkeypatch):
    # С-2: ручные правки title/author/lang переживают реингест
    import json
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    bj = tmp_path / bid / "book.json"
    book = json.loads(bj.read_text(encoding="utf-8"))
    book["title"], book["meta_locked"] = "Моё название", True
    bj.write_text(json.dumps(book, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")
    cfg_toml = tmp_path / "cfg.toml"
    cfg_toml.write_text('[general]\npreface_title = "Пролог"\n', encoding="utf-8")
    run_reingest(load_config(cfg_toml), tmp_path)
    after = json.loads(bj.read_text(encoding="utf-8"))
    assert after["title"] == "Моё название" and after["meta_locked"] is True


def test_reingest_skips_book_without_source(tmp_path, monkeypatch):
    import shutil
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    shutil.rmtree(tmp_path / bid / "source")
    outcomes = run_reingest(load_config(None), tmp_path)
    assert outcomes[0].status == "skipped"
    assert "исходник" in outcomes[0].message


def test_reingest_failed_book_keeps_id(tmp_path, monkeypatch):
    # К-1, путь (a) — исключение: порча байтов source меняет sha → кэш мимо,
    # detect() падает на PK-магии (BrokenFileError) → except-ветка _safe_ingest.
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    src = next((tmp_path / bid / "source").iterdir())
    src.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    outcomes = run_reingest(load_config(None), tmp_path)
    assert outcomes[0].status == "failed"
    assert outcomes[0].book_id == bid


def test_reingest_failed_by_score_keeps_id(tmp_path, monkeypatch):
    # К-1, путь (b) — failed по score, НЕ исключение: бьёт в ветку
    # `if status == "failed"` внутри ingest_file (она правится отдельно от
    # except-веток — оба пути обязаны сохранять id). Мусорный, но валидный
    # utf-8 текст: garbage- и dehyphen-субоценки 0, структуры нет → score
    # ≈ 0.525 < 0.60 (полный quality — M4).
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    src = next((tmp_path / bid / "source").iterdir())
    src.write_text(
        ("Обычная спокойная строка про море и маяк, ровная и достаточно длинная.\n\n"
         "аб\n\n"
         "и снова про море, но эта строка обрывается на самом инте-\n\n") * 60,
        encoding="utf-8")
    outcomes = run_reingest(load_config(None), tmp_path)
    assert outcomes[0].status == "failed"
    assert outcomes[0].score is not None and outcomes[0].score < 0.60
    assert outcomes[0].book_id == bid
```

И в `tests/unit/test_cli.py`:

```python
def test_reingest_requires_all_flag(tmp_path):
    from typer.testing import CliRunner
    from librarian.cli import app
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "reingest"])
    assert r.exit_code == 2
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_pipeline.py tests/unit/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_reingest'`.

- [ ] **Step 3: Реализация.** В `src/librarian/pipeline.py`:

сигнатуры и шаг 12:

```python
def _safe_ingest(path: Path, cfg: Config, lib_root: Path, force: bool,
                 book_id: str | None = None) -> IngestOutcome:
    try:
        return ingest_file(path, cfg, lib_root, force, book_id=book_id)
    ...


def ingest_file(path: Path, cfg: Config, lib_root: Path,
                force: bool = False, book_id: str | None = None) -> IngestOutcome:
    ...
    if book_id is None:                            # 12: reingest знает id заранее (К-1)
        book_id = _resolve_identity(path, raw, sha, lib_root, cfg)
    ...
```

Плюс правка существующих веток (К-1: упавшая при реингесте книга обязана сохранить
свой id в отчёте, иначе таблица покажет `— failed —`, а stderr — «None: …»):

- в **каждой** `except`-ветке `_safe_ingest` заменить `IngestOutcome(path, None, ...)`
  на `IngestOutcome(path, book_id, ...)` — для обычного ingest параметр и так `None`;
- в `ingest_file` ветка `if status == "failed": return IngestOutcome(path, None, "failed",
  score, ...)` выполняется ДО шага 12 (параметр ещё не переприсвоен) — тоже `book_id`
  вместо жёсткого `None`.

новая функция:

```python
def run_reingest(cfg: Config, lib_root: Path) -> list[IngestOutcome]:
    """§13: пересборка библиотеки из source/ текущим кодом/конфигом.
    Совпавший cache_key → skipped (выход и так побайтово идентичен, §2)."""
    outcomes: list[IngestOutcome] = []
    with library_lock(lib_root, cfg.general.lock_timeout_s):
        recover(lib_root)
        from librarian.catalog import scan_books
        for bid, book in scan_books(lib_root):
            fname = book.get("source", {}).get("file")
            src = lib_root / bid / "source" / fname if fname else None
            if src is None or not src.is_file():
                outcomes.append(IngestOutcome(
                    lib_root / bid, bid, "skipped", None,
                    "нет сохранённого исходника (--no-keep-source?)"))
                continue
            outcomes.append(_safe_ingest(src, cfg, lib_root, force=False, book_id=bid))
        rebuild_index(lib_root)                    # один раз на команду (С-7)
    return outcomes
```

(Импорт `scan_books` поднять к остальным импортам из `librarian.catalog`.)

В `src/librarian/cli.py`:

```python
@app.command()
def reingest(all_: bool = typer.Option(False, "--all"),
             config: Path | None = typer.Option(None, "--config"),
             verbose: bool = typer.Option(False, "--verbose")) -> None:
    if not all_:
        _err.print("поддерживается только пакетный режим: lib reingest --all")
        raise typer.Exit(2)
    try:
        cfg = load_config(config)
    except LibError as e:
        _err.print(str(e))
        raise typer.Exit(1)
    outcomes = run_reingest(cfg, _lib_root())
    table = Table("id", "статус", "score")
    for o in outcomes:
        table.add_row(o.book_id or "—", o.status,
                      f"{o.score:.2f}" if o.score is not None else "—")
        if o.message:
            _err.print(f"  {o.book_id}: {o.message}")
        if verbose and o.traceback:
            _err.print(o.traceback, markup=False, highlight=False, soft_wrap=True)
    _err.print(table)
    if any(o.status == "failed" for o in outcomes):
        raise typer.Exit(1)
```

(`run_reingest` импортировать в верхнем `from librarian.pipeline import ...` рядом
с `run_ingest`, не внутри функции — стиль соседних команд.)

- [ ] **Step 4: Зелёный**

Run: `uv run pytest -q` → все зелёные, golden не тронуты.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/pipeline.py src/librarian/cli.py tests/unit/test_pipeline.py tests/unit/test_cli.py
git commit -m "reingest --all: rebuild from sources, stable ids, meta_locked e2e"
```

---

### Task 3: таймаут извлечения `extract_timeout_s` (§6.0, С-5)

**Files:**
- Create: `src/librarian/extractors/guard.py`
- Create: `tests/unit/_guard_targets.py`
- Modify: `src/librarian/pipeline.py` (шаг 4 через guard)
- Modify: `tests/conftest.py`
- Test: `tests/unit/test_guard.py`

**Interfaces:**
- Produces: `guard.run_with_timeout(target, args, timeout_s)` — target выполняется в spawn-процессе; результат/исключение переправляются через Pipe; по таймауту процесс убивается и поднимается `LimitError`; `guard.guarded_extract(fmt, path, cfg) -> RawDoc` — обёртка шага 4; при `timeout_s <= 0` **или** env `LIB_EXTRACT_INPROCESS` — прямой вызов (отклонение 22: тестовый обход, guard не влияет на выходные байты). `target` и аргументы должны пиклиться (наши — module-level функция + `Format`/`Path`/`Config` — пиклятся).
- Consumes: `get_extractor`, реестр экстракторов (в дочернем процессе регистрация — импортом `librarian.extractors`).

- [ ] **Step 1: Красный тест.** Создать `tests/unit/_guard_targets.py` (module-level мишени — пиклятся по ссылке):

```python
# tests/unit/_guard_targets.py — мишени для test_guard (spawn пиклит по имени модуля).
# Резолвится в дочернем процессе потому, что pytest в дефолтном import-mode=prepend
# кладёт tests/unit в sys.path, а spawn наследует sys.path родителя; при переходе
# на --import-mode=importlib эта связка сломается (ModuleNotFoundError в ребёнке).
import time

from librarian.errors import BrokenFileError


def slow(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


def boom() -> None:
    raise BrokenFileError("файл битый изнутри дочернего процесса")


def die() -> None:
    import os
    os._exit(1)          # жёсткая смерть без exception — модель segfault нативного парсера
```

Создать `tests/unit/test_guard.py`:

```python
# tests/unit/test_guard.py
import pytest

import _guard_targets as tg
from librarian.errors import BrokenFileError, LimitError
from librarian.extractors.guard import run_with_timeout


def test_timeout_kills_child():
    with pytest.raises(LimitError, match="зависло"):
        run_with_timeout(tg.slow, (30.0,), timeout_s=1.0)


def test_fast_call_returns_value():
    assert run_with_timeout(tg.slow, (0.0,), timeout_s=15.0) == "done"


def test_child_exception_reraised():
    with pytest.raises(BrokenFileError, match="изнутри дочернего"):
        run_with_timeout(tg.boom, (), timeout_s=15.0)


def test_child_hard_crash_reported():
    # ребёнок умер, не написав в Pipe (segfault/OOM/os._exit) → внятная ошибка,
    # а не голый EOFError в отчёте
    with pytest.raises(LimitError, match="аварийно"):
        run_with_timeout(tg.die, (), timeout_s=15.0)


def test_zero_timeout_runs_inprocess():
    assert run_with_timeout(tg.slow, (0.0,), timeout_s=0) == "done"


def test_guarded_extract_end_to_end(tmp_path, monkeypatch):
    # реальный экстрактор в дочернем процессе — регистрация импортом.
    # Известное ограничение: pytest-socket (задача 4) не патчит socket в
    # spawn-ребёнке — этот тест выполняется вне сетевого периметра.
    monkeypatch.delenv("LIB_EXTRACT_INPROCESS", raising=False)
    from librarian.config import load_config
    from librarian.extractors.guard import guarded_extract
    from librarian.ir import Format
    f = tmp_path / "b.txt"
    f.write_text("Глава 1\n\nТекст главы про море и маяк.\n", encoding="utf-8")
    raw = guarded_extract(Format.TXT, f, load_config(None))
    assert raw.blocks and raw.fmt is Format.TXT
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/unit/test_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extractors.guard'`

- [ ] **Step 3: Реализация.** Создать `src/librarian/extractors/guard.py`:

```python
# src/librarian/extractors/guard.py
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

from librarian.config import Config
from librarian.errors import LimitError
from librarian.ir import Format, RawDoc


def _call(conn, target, args) -> None:
    try:
        conn.send((True, target(*args)))
    except BaseException as e:                      # noqa: BLE001 — переправляем родителю
        conn.send((False, e))
    finally:
        conn.close()


def run_with_timeout(target, args: tuple, timeout_s: float):
    """target(*args) в spawn-процессе; дольше timeout_s → kill + LimitError.
    timeout_s <= 0 — прямой вызов (guard выключен)."""
    if timeout_s <= 0:
        return target(*args)
    ctx = multiprocessing.get_context("spawn")      # одинаково на всех ОС
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_call, args=(child, target, args), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout_s):
            proc.kill()
            proc.join()
            raise LimitError(f"извлечение зависло (> {timeout_s:g} с)")
        try:
            ok, payload = parent.recv()
        except EOFError:                                # ребёнок умер молча:
            proc.join()                                 # segfault/OOM/os._exit
            raise LimitError(
                "извлечение аварийно завершилось (процесс умер без ответа)") from None
        proc.join()
        if ok:
            return payload
        raise payload
    finally:
        parent.close()


def _extract_entry(fmt_value: str, path_str: str, cfg: Config) -> RawDoc:
    import librarian.extractors                     # noqa: F401 — регистрация в дочернем
    from librarian.extractors.base import get_extractor
    return get_extractor(Format(fmt_value)).extract(Path(path_str), cfg)


def guarded_extract(fmt: Format, path: Path, cfg: Config) -> RawDoc:
    """Шаг 4 конвейера под лимитом §6.0. Операционный guard: на выходные
    байты не влияет; env LIB_EXTRACT_INPROCESS=1 — обход для тестов (откл. 22)."""
    if cfg.limits.extract_timeout_s <= 0 or os.environ.get("LIB_EXTRACT_INPROCESS"):
        from librarian.extractors.base import get_extractor
        return get_extractor(fmt).extract(path, cfg)
    try:
        return run_with_timeout(_extract_entry, (fmt.value, str(path), cfg),
                                cfg.limits.extract_timeout_s)
    except LimitError:
        raise LimitError(f"{path.name}: извлечение зависло "
                         f"(> {cfg.limits.extract_timeout_s} с)") from None
```

В `src/librarian/pipeline.py` шаг 4:

```python
from librarian.extractors.guard import guarded_extract
...
    raw = guarded_extract(fmt, path, cfg)                                # 4, §6.0
```

(Импорт `get_extractor` из pipeline убрать, если больше не используется.)

В `tests/conftest.py` добавить в начало (после существующих импортов):

```python
import os

# Тесты гоняют экстракцию в текущем процессе: spawn-guard (§6.0 таймаут) добавлял бы
# ~1с на каждый ingest. Сам guard тестируется явно в unit/test_guard.py (откл. 22).
os.environ.setdefault("LIB_EXTRACT_INPROCESS", "1")
```

- [ ] **Step 4: Зелёный, включая guard-тесты со spawn**

Run: `uv run pytest tests/unit/test_guard.py -q` → PASS (тесты guard вызывают `run_with_timeout` напрямую — env-обход на них не влияет, кроме e2e, где env снят monkeypatch-ем).
Run: `uv run pytest -q` → все зелёные, время прогона не выросло заметно.

- [ ] **Step 5: Commit**

```bash
git add src/librarian/extractors/guard.py src/librarian/pipeline.py tests/conftest.py tests/unit/_guard_targets.py tests/unit/test_guard.py
git commit -m "extract timeout guard: spawn worker, kill on hang"
```

---

### Task 4: тесты без сети (pytest-socket) + перф-смоук (§17)

**Files:**
- Modify: `pyproject.toml` (dev-deps, addopts, markers)
- Create: `tests/test_perf.py`

**Interfaces:**
- Produces: сетевые вызовы в любом тесте → немедленный fail (`pytest-socket`); маркер `perf`; смоук: PDF 500 страниц → ingest < 30 с, превышение — **warning**, не fail (мягкий порог §17).

- [ ] **Step 1: Красный тест.** Создать `tests/test_perf.py`:

```python
# tests/test_perf.py — перф-смоук §17: мягкий порог, warning вместо fail
import time
import warnings

import pymupdf
import pytest

from librarian.config import load_config
from librarian.pipeline import run_ingest

_PARA = ("The keeper wrote down every light he saw across the strait during "
         "the long night watch while the sea kept counting the hours. ") * 4


@pytest.mark.perf
def test_pdf_500_pages_under_30s(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    # мерим ПРОДОВЫЙ путь: у пользователя env-обхода нет, extract_timeout_s=120 →
    # spawn-guard + pickle RawDoc через Pipe входят в бюджет 30 с (§6.0/§17)
    monkeypatch.delenv("LIB_EXTRACT_INPROCESS", raising=False)
    pdf = tmp_path / "big.pdf"
    doc = pymupdf.open()
    for i in range(500):
        page = doc.new_page(width=595, height=842)
        if i % 10 == 0:
            page.insert_text((72, 90), f"Chapter {i // 10 + 1}",
                             fontsize=16, fontname="helv")
        page.insert_textbox(pymupdf.Rect(72, 120, 520, 780), _PARA * 4,
                            fontsize=10, fontname="helv")
    doc.save(pdf, deflate=True)
    doc.close()
    t0 = time.monotonic()
    outcome = run_ingest([pdf], load_config(None), tmp_path / "lib")[0]
    dt = time.monotonic() - t0
    assert outcome.status in ("ok", "review")
    if dt > 30:
        warnings.warn(f"перф-смоук: 500-страничный PDF за {dt:.1f} с (порог 30 с)")
```

И проверка блокировки сети (туда же):

```python
def test_network_is_blocked():
    import socket
    import pytest_socket
    with pytest.raises(pytest_socket.SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", 9))
```

- [ ] **Step 2: Убедиться, что красный**

Run: `uv run pytest tests/test_perf.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pytest_socket'` / маркер perf не зарегистрирован (warning-as-error нет, но тест сети упадёт: сокет создастся).

- [ ] **Step 3: Реализация** — в `librarian/pyproject.toml`:

```toml
[dependency-groups]
dev = ["pytest>=8", "pytest-socket>=0.7"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--disable-socket --allow-unix-socket"
markers = ["perf: перф-смоук (мягкий порог, §17)"]
```

Затем `uv lock` (обновление lock — dev-группа, рантайм-зависимости не меняются).

- [ ] **Step 4: Зелёный + полный прогон без сети**

Run: `uv run pytest -q`
Expected: PASS. Если что-то в зависимостях тайно полезло в сеть (tiktoken, DTD lxml — §17), оно упадёт здесь — это и есть цель; такой fail = найденный дефект, чинить в источнике, не ослаблять блокировку.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_perf.py
git commit -m "block network in tests, 500-page perf smoke"
```

---

### Task 5: CI-матрица + офлайн-установка из wheel (§17, DoD §18)

**Files:**
- Create: `.github/workflows/ci.yml` (в git-корне `libby/`, не в `librarian/`)

**Interfaces:**
- Produces: job `tests` — {ubuntu, macos, windows} × {3.11, 3.13}, `uv sync --frozen` + `uv run pytest` (golden сравниваются между ОС самим прогоном — §17 «это и есть проверка “между машинами”»); job `wheel-offline` — сборка wheel, скачивание зависимостей заранее, установка в чистый venv с `--no-index` и smoke `lib ingest` (DoD M5: офлайн-контракт установки из локального артефакта).

- [ ] **Step 1: Написать workflow** — создать `.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]

jobs:
  tests:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.11", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: ${{ matrix.python }}
      - name: тесты (сеть в тестах блокирует pytest-socket)
        working-directory: librarian
        run: |
          uv sync --frozen
          uv run pytest -q

  wheel-offline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5      # download/venv/install — одним и тем же
        with:                              # интерпретатором, иначе теги платформенных
          python-version: "3.11"           # колёс (pymupdf/lxml) не совпадут при
      - uses: astral-sh/setup-uv@v5        # --no-index; 3.11 = пол матрицы §17.
                                           # (uv build может взять managed-python —
                                           # wheel py3-none-any, это не важно)
      - name: собрать wheel и скачать зависимости (сеть ещё разрешена)
        working-directory: librarian
        run: |
          uv build --wheel
          python -m pip download -d /tmp/wheelhouse dist/*.whl
      - name: установка и smoke строго офлайн (--no-index)
        working-directory: librarian
        run: |
          python -m venv /tmp/clean
          /tmp/clean/bin/pip install --no-index --find-links /tmp/wheelhouse dist/*.whl
          printf 'Глава 1\n\nТекст главы про море и маяк, длинный и спокойный.\n' > /tmp/kniga.txt
          /tmp/clean/bin/lib --library /tmp/lib ingest /tmp/kniga.txt
          /tmp/clean/bin/lib --library /tmp/lib list
```

⚠️ Не `uv run python -m pip ...`: uv-venv создаётся **без** pip («No module named pip» —
проверено), а `uv pip download` не существует. Скачивание и офлайн-установка идут
setup-python-интерпретатором. §18 DoD называет `pipx install ./librarian-*.whl` —
pip+venv с `--no-index` тот же контракт (pipx внутри делает ровно venv+pip;
отклонение 29); pipx-путь документирует README (задача 6).
Известное ограничение: `pip download dist/*.whl` резолвит зависимости по floating `>=`
из METADATA, а не по `uv.lock`, — job может сломаться со временем без единой правки кода
(какой-нибудь транзитивный пакет перестанет публиковать wheel). Осознанно принято.

- [ ] **Step 2: Локальная репетиция офлайн-джоба**

Run (из `librarian/`; download — из stdlib-venv тем же python3, в uv-venv pip нет):
`uv build --wheel && python3 -m venv /tmp/dl && /tmp/dl/bin/python -m pip download -d /tmp/wheelhouse dist/*.whl && python3 -m venv /tmp/clean-lib && /tmp/clean-lib/bin/pip install --no-index --find-links /tmp/wheelhouse dist/*.whl && /tmp/clean-lib/bin/lib --help`
Expected: установка без обращений к PyPI, `lib --help` печатает команды (вендоренный словарь токенизатора в wheel — К-4 уже проверяется `test_install.py`, здесь — офлайн-режим установки). После проверки: `rm -rf /tmp/dl /tmp/clean-lib /tmp/wheelhouse librarian/dist`.

- [ ] **Step 3: Прогнать workflow-синтаксис**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('../.github/workflows/ci.yml').read_text()); print('yaml ok')"`
(pyyaml нет в зависимостях → если ImportError, проверить глазами отступы или `uv run --with pyyaml ...`.)

- [ ] **Step 4: Commit** (пуш и первая зелёная матрица — за пользователем: репозиторий локальный)

```bash
git add ../.github/workflows/ci.yml
git commit -m "ci: os/python matrix, offline wheel install job"
```

---

### Task 6: README

**Files:**
- Create: `librarian/README.md`

- [ ] **Step 1: Написать README** — по этому скелету, заполняя фактическим поведением (сверить каждую команду руками перед записью):

```markdown
# librarian

Детерминированный конвейер «книга → Markdown-главы» для работы с LLM.
Любой входной формат (FB2, EPUB, DOCX, HTML, TXT/MD, PDF с текстовым слоем) →
каталог чистых глав с подсчитанными токенами. Без сети, без LLM, без случайности:
одинаковый вход даёт побайтово идентичный выход.

## Установка

    pipx install ./librarian-*.whl     # или: uv tool install .

Офлайн-контракт: рантайм и установка из локального wheel не требуют сети
(словарь токенизатора вендорен в пакет).

## Быстрый старт

    lib ingest книга.epub роман.fb2 статья.html
    lib list
    lib list <book-id>
    lib get <book-id> 1-3,7
    lib get <book-id> --budget 12000

## Команды
（таблица §15: ingest/list/get/info/doctor/rm/reingest — по строке на команду）

## Качество

Каждая книга получает score из пяти метрик (coverage, structure, garbage,
encoding, dehyphen): ok ≥ 0.90 — молча в библиотеку; review — сохранена
с предупреждением, смотреть `lib doctor <id>`; failed < 0.60 — не сохраняется.
Сканы и PDF под паролем честно дают failed (OCR и DRM — вне задач инструмента).

## Конфигурация

`lib ingest --config cfg.toml`; все пороги — §14 спеки. Правки метаданных руками:
поставить `"meta_locked": true` в book.json — реингест их не перетрёт.
`lib reingest --all` пересобирает библиотеку текущим кодом/конфигом; книги, у которых
ничего не изменилось, пропускаются с сообщением «уже в библиотеке» — выход
и так детерминирован.

## Ограничения

- PDF: типографски обычные книги; сложная вёрстка может уйти в review.
- DRM не обходится; правомерность источников — ответственность пользователя.
- Сетевые ФС (NFS/SMB) не поддерживаются (advisory-lock ненадёжен).
- MOBI/DJVU/сканы — нет (v3: OCR, calibre).
```

- [ ] **Step 2: Проверить команды из README руками**

Run: каждую команду из «Быстрый старт» на любой фикстуре во временной библиотеке; вывод соответствует написанному.

- [ ] **Step 3: Полный финальный прогон DoD M5**

Run: `uv run pytest -q`
Expected: весь набор зелёный; golden не менялись с M4 (git status чист по `tests/golden`).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "readme: install, commands, quality model, limits"
```

---

## Отклонения от спеки (нумерация сквозная; за M4 — 21)

- **22.** Env `LIB_EXTRACT_INPROCESS=1` отключает spawn-guard таймаута — только для тестов (conftest): guard добавлял бы ~1 с на каждый ingest в каждом тесте. Guard не влияет на выходные байты (§6.0 «операционный»), сам тестируется явно в `test_guard.py`.
- **23.** `lib reingest` без `--all` — exit 2: спека определяет только пакетный режим; точечный реингест одной книги не описан и не реализуется (YAGNI).
- **24.** Совпадение `cache_key` при reingest → `skipped` (сообщение M1-кэша «уже в библиотеке»): не новое решение, а прямое следствие кэш-шага `ingest_file` из M1, которое `run_reingest` переиспользует как есть; по §2 пересборка дала бы те же байты. Спека молчит; поведение зафиксировано тестом.
- **29.** DoD §18 дословно называет `pipx install ./librarian-*.whl`; CI-job проверяет офлайн-контракт через `pip install --no-index` в чистый venv — pipx внутри делает ровно venv+pip, офлайн-свойство идентично. Резолюция колёс в job — floating по METADATA, не по `uv.lock` (принятый дрейф-риск). README документирует pipx-путь. (25–28 занял план M4 после ревью.)
- **35.** (Task 3) План не учёл пред-существующий `test_pipeline.py::test_extract_timeout_enforcement` (BUG F-10, M1), написанный под СТАРЫЙ `signal.alarm`: он `monkeypatch.setitem(EXTRACTORS, Format.TXT, SlowExtractor())` in-process и ждёт `LimitError`. Со spawn-guard-ом тест несовместим по двум независимым причинам: (1) conftest `LIB_EXTRACT_INPROCESS=1` → inprocess-ветка → SlowExtractor просто спит и возвращает; (2) даже без env spawn-ребёнок переимпортирует `librarian.extractors` начисто → parent-monkeypatch не пересекает границу процесса → в ребёнке реальный быстрый extractor. Тест проверял *реализацию* удалённого механизма, а не контракт. Удалён (с пояснительным комментарием на его месте). Контракт §6.0 покрыт композицией трёх различимых граней: (1) guard убивает зависание → `test_guard.py::test_timeout_kills_child` (spawn kill → LimitError) + `test_guarded_extract_end_to_end`; (2) `LimitError` даёт outcome `failed`, а не крэш → `test_source_size_limit` (LimitError из size-чека идёт тем же путём `_safe_ingest except LibError → failed`, т.к. `LimitError < ExtractError < LibError`); (3) один сбойный файл не рушит батч → `test_broken_file_does_not_kill_batch`. Байты выхода не затронуты, golden чист.
- **34.** (Task 1) Вербатим-код `get` из плана (строки 179–182) читает главы наивным list-comprehension `(_lib_root() / book_id / by_n[n]["file"]).read_text(...)` — БЕЗ проверки пути. Это выбрасывает существующую path-traversal защиту (BUG F-1) и уронило бы предсуществующий `test_get_path_traversal_protection` (evil book.json с `"file": "../secret.txt"` / `"../../outside.txt"` → ОС резолвит `..` при открытии → секрет утечёт в stdout, exit 0 вместо ожидаемого exit 1). Осознанный фикс: MERGE — budget/spec-логика плана ПЛЮС сохранённый guard `ch_path.resolve().is_relative_to((lib/book_id).resolve())` перед `read_text`, нарушение → `LibError` → exit 1. Байты выхода не затронуты, оба новых budget-теста и traversal-тест зелёные.

## Self-Review (выполнено при написании плана)

1. **Покрытие §18 M5:** `--budget` — T1; `reingest --all` — T2; `meta_locked` — e2e в T2; лимиты/таймауты — T3 (размер и zip — уже M1/M2); перф-смоук — T4 (на продовом guarded-пути); CI-матрица ОС — T5; README — T6; DoD «wheel офлайн» — T5 (локальная репетиция + job; подмена pipx→pip+venv задекларирована откл. 29). ✓
2. **Placeholder-скан:** README-задача даёт скелет с требованием сверки руками — это осознанно: копипаста непроверенных команд хуже; всё остальное — конкретный код. ✓
3. **Типы согласованы:** `run_with_timeout(target, args, timeout_s)` (T3) используется `guarded_extract`-ом там же; `ingest_file(..., book_id=None)` (T2) согласован с `_safe_ingest` и `run_reingest`; `tree_bytes` — из conftest (M1). ✓
