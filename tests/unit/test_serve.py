from __future__ import annotations

import builtins
import json
import os
import sys

import pytest

import librarian.serve as serve
from librarian.catalog import rebuild_index
from librarian.errors import LibError


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mkbook(lib, bid, title, author, chapters, status="ok"):
    """chapters: list of (title, text). Пишет book.json + chapters/NNN.md напрямую,
    без прогона пайплайна (как в test_search.py) — быстрый точный контроль над данными."""
    d = lib / bid
    (d / "chapters").mkdir(parents=True, exist_ok=True)
    entries = []
    for n, (ctitle, text) in enumerate(chapters, 1):
        fname = f"chapters/{n:03d}.md"
        (d / fname).write_text(text, encoding="utf-8")
        entries.append({"n": n, "file": fname, "title": ctitle,
                        "tokens": len(text.split()), "summary": f"summary {n}"})
    book = {
        "id": bid, "title": title, "author": author, "lang": "ru",
        "meta_locked": False,
        "source": {"file": f"{bid}.txt", "format": "txt", "sha256": "x" * 8},
        "provenance": {"ingested_at": "1970-01-01T00:00:00Z", "pipeline_version": "2.4",
                       "config_hash": "c", "cache_key": f"{bid}:2.4:c"},
        "quality": {"status": status, "score": 1.0},
        "total_tokens": sum(e["tokens"] for e in entries),
        "chapters": entries,
    }
    (d / "book.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    return d


def _mklib_multi(tmp_path):
    """Библиотека с одной книгой из трёх глав по 100 «токенов» (слов) каждая —
    для budget/next_from тестов."""
    lib = tmp_path / "library"
    chapters = [(f"Глава {n}", "слово " * 100) for n in range(1, 4)]
    _mkbook(lib, "book", "Книга", "Автор", chapters)
    return lib, "book"


# --- list_books / list_chapters / find / book_info roundtrip -----------------

def test_list_books_roundtrip(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов", [("Глава 1", "текст главы")])
    rebuild_index(lib)
    books = serve.list_books(lib)
    assert len(books) == 1
    assert books[0]["id"] == "kit"
    assert books[0]["title"] == "Сказка о ките"


def test_list_chapters_roundtrip(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов",
            [("Глава 1", "текст первой главы"), ("Глава 2", "текст второй главы")])
    chapters = serve.list_chapters(lib, "kit")
    assert [c["n"] for c in chapters] == [1, 2]
    assert chapters[0]["title"] == "Глава 1"
    assert chapters[1]["title"] == "Глава 2"


def test_find_roundtrip(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов",
            [("Глава 1", "Кит шёл на юг, раздвигая тяжёлую воду.")])
    res = serve.find(lib, "кит")
    assert res["hits"]
    assert any(h["book_id"] == "kit" for h in res["hits"])


def test_book_info_roundtrip(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов", [("Глава 1", "текст главы")])
    info = serve.book_info(lib, "kit")
    assert info["book"]["id"] == "kit"
    assert set(info) == {"book", "metrics", "subscores", "score", "hard_triggers"}


# --- get_chapters: spec/budget semantics --------------------------------------

def test_get_chapters_spec_mode(tmp_path):
    lib, bid = _mklib_multi(tmp_path)
    res = serve.get_chapters(lib, bid, spec="2")
    assert res["chapters"] == [2]
    assert res["next_from"] is None


def test_get_chapters_default_budget_when_neither_given(tmp_path):
    lib, bid = _mklib_multi(tmp_path)
    res = serve.get_chapters(lib, bid)
    assert serve.DEFAULT_BUDGET == 12000
    assert res["chapters"] == [1, 2, 3]           # 300 токенов, влезает в дефолт 12000
    assert res["next_from"] is None
    assert res["text"]


def test_get_chapters_spec_and_budget_both_given_is_tool_error(tmp_path):
    lib, bid = _mklib_multi(tmp_path)
    with pytest.raises(ValueError):
        serve.get_chapters(lib, bid, spec="1", budget=100)


def test_get_chapters_next_from_on_multi_chapter_book(tmp_path):
    lib, bid = _mklib_multi(tmp_path)
    res = serve.get_chapters(lib, bid, budget=200)     # ровно первые две главы (100+100)
    assert res["chapters"] == [1, 2]
    assert res["next_from"] == 3
    assert res["message"]


def test_get_chapters_first_chapter_too_big_is_structured_not_exception(tmp_path):
    lib, bid = _mklib_multi(tmp_path)
    res = serve.get_chapters(lib, bid, budget=1)
    assert res["chapters"] == []
    assert res["next_from"] == 1
    assert res["message"]
    assert res["text"] == ""


# --- book_id validation (traversal closed in T1, shared by all readers) ------

@pytest.mark.parametrize("bad_id", ["не-существующая-книга", "../x"])
def test_get_chapters_bad_book_id_raises(tmp_path, bad_id):
    lib = tmp_path / "library"
    lib.mkdir()
    with pytest.raises(LibError):
        serve.get_chapters(lib, bad_id, budget=100)


@pytest.mark.parametrize("bad_id", ["не-существующая-книга", "../x"])
def test_list_chapters_bad_book_id_raises(tmp_path, bad_id):
    lib = tmp_path / "library"
    lib.mkdir()
    with pytest.raises(LibError):
        serve.list_chapters(lib, bad_id)


@pytest.mark.parametrize("bad_id", ["не-существующая-книга", "../x"])
def test_book_info_bad_book_id_raises(tmp_path, bad_id):
    lib = tmp_path / "library"
    lib.mkdir()
    with pytest.raises(LibError):
        serve.book_info(lib, bad_id)


# --- e2e smoke: real subprocess + MCP stdio handshake -------------------------

# на Windows asyncio поднимает внутренний socketpair — pytest-socket его блокирует
@pytest.mark.enable_socket
@pytest.mark.anyio
async def test_e2e_subprocess_handshake_and_list_books(tmp_path):
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов", [("Глава 1", "текст главы")])
    rebuild_index(lib)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "librarian", "serve", "--library", str(lib)],
        env=dict(os.environ),
    )
    with anyio.fail_after(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                assert init_result.serverInfo.name == "librarian"

                result = await session.call_tool("list_books", {})
                assert not result.isError
                books = (result.structuredContent or {}).get("result")
                if books is None:
                    books = [json.loads(c.text) for c in result.content]
                assert any(b["id"] == "kit" for b in books)


# --- missing extra: lazy import of mcp fails cleanly with RU hint ------------

def test_serve_missing_extra_prints_hint_and_exits_1(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("No module named 'mcp'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "librarian.serve", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    from typer.testing import CliRunner
    from librarian.cli import app
    r = CliRunner().invoke(app, ["--library", str(tmp_path), "serve"])
    assert r.exit_code == 1
    assert "переустановите librarian-cli" in r.stderr


def test_serve_entry_help_exits_0(monkeypatch):
    from librarian import cli
    monkeypatch.setattr(sys, "argv", ["librarian-cli", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.serve_entry()
    assert exc.value.code == 0
