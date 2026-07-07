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


def test_ingest_verbose_traceback(tmp_path):
    # BUG 3: --verbose должен печатать traceback в stderr при падении
    r = runner.invoke(app, ["--library", str(tmp_path / "lib"), "ingest", str(tmp_path / "non_existent.txt"), "--verbose"])
    assert r.exit_code == 1
    assert "Traceback (most recent call last):" in r.stderr
    
    # Без флага --verbose трейсбека быть не должно, только сообщение об ошибке
    r2 = runner.invoke(app, ["--library", str(tmp_path / "lib"), "ingest", str(tmp_path / "non_existent.txt")])
    assert r2.exit_code == 1
    assert "Traceback" not in r2.stderr


def test_ingest_bad_config(tmp_path):
    # BUG 4: --config с отсутствующим/битым файлом не должен бросать python traceback пользователю
    r1 = runner.invoke(app, ["--library", str(tmp_path / "lib"), "ingest", "some.txt", "--config", str(tmp_path / "no_such_config.toml")])
    assert r1.exit_code == 1
    assert "Traceback (most recent call last)" not in r1.stderr
    assert "конфиг" in r1.stderr

    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("invalid = { [", encoding="utf-8")
    r2 = runner.invoke(app, ["--library", str(tmp_path / "lib"), "ingest", "some.txt", "--config", str(bad_cfg)])
    assert r2.exit_code == 1
    assert "Traceback (most recent call last)" not in r2.stderr
    assert "конфиг" in r2.stderr


def test_rm_path_traversal_protection(lib):
    # BUG 10: rm не должен принимать произвольные book_id с path traversal
    lib_dir, bid = lib
    sibling = lib_dir.parent / "sibling"
    sibling.mkdir(exist_ok=True)
    (sibling / "book.json").write_text("{}", encoding="utf-8")
    
    r = runner.invoke(app, ["--library", str(lib_dir), "rm", "../sibling"])
    assert r.exit_code == 1
    # Проверяем, что соседняя директория НЕ была удалена
    assert (sibling / "book.json").exists()
    import shutil
    shutil.rmtree(sibling, ignore_errors=True)


def test_get_path_traversal_protection(lib, tmp_path):
    # BUG F-1: path traversal в get через book.json:file
    lib_dir, bid = lib
    
    # 1. Секретный файл внутри библиотеки (но вне папки книги)
    secret_file = lib_dir / "secret.txt"
    secret_file.write_text("TOP SECRET CONTENT", encoding="utf-8")
    
    # 2. Секретный файл полностью за пределами корня библиотеки
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("OUTSIDE SECRET CONTENT", encoding="utf-8")
    
    evil_dir = lib_dir / "evil-book"
    evil_dir.mkdir(exist_ok=True)
    
    import json
    evil_book_json = {
        "id": "evil-book",
        "title": "Evil Book",
        "author": "Author",
        "chapters": [
            {
                "n": 1,
                "title": "Chapter 1",
                "tokens": 10,
                "file": "../secret.txt",
                "summary": "Traversing paths"
            },
            {
                "n": 2,
                "title": "Chapter 2",
                "tokens": 10,
                "file": "../../outside.txt",
                "summary": "Traversing paths outside"
            }
        ]
    }
    (evil_dir / "book.json").write_text(json.dumps(evil_book_json), encoding="utf-8")
    
    # Проверка 1: подъем на уровень вверх
    r1 = runner.invoke(app, ["--library", str(lib_dir), "get", "evil-book", "1"])
    assert r1.exit_code == 1
    assert "TOP SECRET CONTENT" not in r1.stdout
    assert "недопустимый" in r1.stderr or "ошибка" in r1.stderr or r1.exit_code == 1
    
    # Проверка 2: подъем полностью за пределы библиотеки
    r2 = runner.invoke(app, ["--library", str(lib_dir), "get", "evil-book", "2"])
    assert r2.exit_code == 1
    assert "OUTSIDE SECRET CONTENT" not in r2.stdout



def test_list_corrupted_index_json(tmp_path):
    # BUG F-7: lib list роняет сырой traceback на битом index.json
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    
    (lib_dir / "index.json").write_text("invalid json {", encoding="utf-8")
    r1 = runner.invoke(app, ["--library", str(lib_dir), "list"])
    assert r1.exit_code == 1
    # Должен быть чистый exit (SystemExit), без сырого traceback
    assert isinstance(r1.exception, SystemExit)
    
    (lib_dir / "index.json").write_text('{"other": []}', encoding="utf-8")
    r2 = runner.invoke(app, ["--library", str(lib_dir), "list"])
    assert r2.exit_code == 1
    assert isinstance(r2.exception, SystemExit)


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




def test_reingest_requires_all_flag(tmp_path):
    from typer.testing import CliRunner
    from librarian.cli import app
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "reingest"])
    assert r.exit_code == 2
