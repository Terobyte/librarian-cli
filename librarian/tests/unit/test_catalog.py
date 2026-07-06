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
