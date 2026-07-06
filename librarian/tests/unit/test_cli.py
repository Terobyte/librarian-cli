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
