import json
from librarian.catalog import (find_by_sha256, get_chapters_core, read_book,
                                rebuild_index, scan_books, validate_book_id)
from librarian.errors import LibError, UnknownBookError
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


def test_broken_dirs_lists_unreadable_book_json(tmp_path):
    from librarian.catalog import broken_dirs
    good = tmp_path / "good-book"; good.mkdir()
    (good / "book.json").write_text('{"id": "good-book"}', encoding="utf-8")
    bad = tmp_path / "bad-book"; bad.mkdir()
    (bad / "book.json").write_text("{оборвано…", encoding="utf-8")
    nojson = tmp_path / "no-json"; nojson.mkdir()
    assert broken_dirs(tmp_path) == ["bad-book"]


@pytest.mark.parametrize("bad_id", ["../x", "a/b", "/etc/passwd", ""])
def test_validate_book_id_rejects_traversal(tmp_path, bad_id):
    with pytest.raises(LibError):
        validate_book_id(tmp_path, bad_id)
    with pytest.raises(LibError):
        read_book(tmp_path, bad_id)


def test_validate_book_id_accepts_valid_slug(tmp_path):
    _book(tmp_path, "valid-slug")
    validate_book_id(tmp_path, "valid-slug")          # не бросает
    assert read_book(tmp_path, "valid-slug")["id"] == "valid-slug"


def test_get_chapters_core_budget_first_chapter_too_big(tmp_path):
    d = tmp_path / "big"
    (d / "chapters").mkdir(parents=True)
    (d / "chapters" / "001.md").write_text("текст главы", encoding="utf-8")
    (d / "book.json").write_text(json.dumps({
        "id": "big", "title": "BIG", "author": "A", "lang": "ru",
        "meta_locked": False,
        "source": {"file": "f.txt", "format": "txt", "sha256": "x"},
        "provenance": {"cache_key": "x:2.2:c"},
        "quality": {"status": "ok", "score": 1.0},
        "total_tokens": 500,
        "chapters": [{"n": 1, "title": "Глава 1", "tokens": 500,
                       "file": "chapters/001.md", "summary": None}],
    }, ensure_ascii=False), encoding="utf-8")
    res = get_chapters_core(tmp_path, "big", budget=1)
    assert res["chapters"] == []
    assert res["next_from"] == 1
    assert res["message"]
