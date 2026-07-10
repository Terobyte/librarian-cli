import json
import sqlite3
import time

import pytest

from conftest import _mkbook
from librarian.errors import LibError
from librarian.search import search, sync


def _meta_rows(lib):
    conn = sqlite3.connect(lib / ".search.db")
    try:
        return dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()


# --- build/sync -------------------------------------------------------------

def test_search_builds_index_and_finds_chapter(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов",
            [("Глава 1", "Кит шёл на юг, раздвигая тяжёлую воду.")])
    res = search(lib, "кит")
    assert res["partial"] is False
    chapter_hits = [h for h in res["hits"] if h["n"] is not None]
    assert len(chapter_hits) == 1
    hit = chapter_hits[0]
    assert hit["book_id"] == "kit"
    assert hit["n"] == 1
    assert hit["chapter_title"] == "Глава 1"
    assert "«" in hit["snippet"]


def test_search_empty_library_returns_empty(tmp_path):
    lib = tmp_path / "library"
    res = search(lib, "что-нибудь")
    assert res == {"hits": [], "partial": False}


def test_search_empty_query_returns_empty_without_sync(tmp_path):
    lib = tmp_path / "library"
    res = search(lib, "   ")
    assert res == {"hits": [], "partial": False}
    assert not (lib / ".search.db").exists()


# --- incremental sync ---------------------------------------------------

def test_incremental_sync_add_and_remove_book(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "one", "Один", "А", [("Гл1", "текст про уникальныйтермин раз")])
    sync(lib)
    assert search(lib, "уникальныйтермин")["hits"]

    _mkbook(lib, "two", "Два", "Б", [("Гл1", "текст про другойуникальныйтермин два")])
    assert search(lib, "другойуникальныйтермин")["hits"]
    assert search(lib, "уникальныйтермин")["hits"]          # первая книга всё ещё в индексе

    import shutil
    shutil.rmtree(lib / "one")
    res = search(lib, "уникальныйтермин")
    assert res["hits"] == []
    assert "book:one" not in _meta_rows(lib)
    assert "book:two" in _meta_rows(lib)


def test_direct_md_edit_caught_by_stat(tmp_path):
    lib = tmp_path / "library"
    d = _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов",
                [("Глава 1", "исходный текст главы")])
    sync(lib)
    assert search(lib, "свежепереписанословобезаналогов")["hits"] == []

    md = d / "chapters" / "001.md"
    time.sleep(0.01)                                        # гарантируем другой mtime_ns
    md.write_text("текст переписан: свежепереписанословобезаналогов", encoding="utf-8")
    res = search(lib, "свежепереписанословобезаналогов")
    assert res["hits"], "прямая правка .md должна ловиться по (size, mtime_ns)"


def test_manual_book_json_edit_meta_locked_reflected(tmp_path):
    lib = tmp_path / "library"
    d = _mkbook(lib, "kit", "Старое название", "Автор",
                [("Гл1", "текст главы про кита")])
    sync(lib)
    assert search(lib, "Старое")["hits"]

    book = json.loads((d / "book.json").read_text(encoding="utf-8"))
    book["title"] = "Новое уникальное название"
    book["meta_locked"] = True
    (d / "book.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")

    res = search(lib, "уникальное")
    assert any(h["book_title"] == "Новое уникальное название" for h in res["hits"])


def test_reingest_detection_with_different_source_date_epoch(tmp_path, monkeypatch):
    """book.json с SOURCE_DATE_EPOCH=0 в обоих прогонах побайтово идентичен —
    ветка sha256(book.json) в fingerprint не покрывается. Нужны РАЗНЫЕ epoch."""
    from librarian.config import load_config
    from librarian.pipeline import run_ingest

    lib = tmp_path / "library"
    src_dir = tmp_path / "_src"; src_dir.mkdir()
    src = src_dir / "roman.txt"
    src.write_text(
        "Глава 1\n\n" + "Ровный спокойный абзац про маятники и облака. " * 10 + "\n\n"
        "Глава 2\n\n" + "Второй абзац про рыб и корабли совсем другой длины. " * 10,
        encoding="utf-8")

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    out = run_ingest([src], load_config(None), lib)[0]
    assert out.status in ("ok", "review"), out.message
    bid = out.book_id
    sync(lib)
    fp1 = _meta_rows(lib)[f"book:{bid}"]

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "999999999")
    out2 = run_ingest([src], load_config(None), lib, force=True)[0]
    assert out2.book_id == bid
    sync(lib)
    fp2 = _meta_rows(lib)[f"book:{bid}"]

    assert fp1 != fp2, "разный ingested_at должен менять sha256(book.json) → fingerprint"
    assert search(lib, "маятники")["hits"]


def test_traversal_chapter_path_rejected(tmp_path):
    lib = tmp_path / "library"
    d = lib / "evil"
    (d / "chapters").mkdir(parents=True)
    secret = lib / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    book = {
        "id": "evil", "title": "Evil", "author": "A", "lang": "ru",
        "meta_locked": False,
        "source": {"file": "f.txt", "format": "txt", "sha256": "x"},
        "provenance": {"cache_key": "x"},
        "quality": {"status": "ok", "score": 1.0},
        "total_tokens": 1,
        "chapters": [{"n": 1, "file": "../secret.txt", "title": "T",
                      "tokens": 1, "summary": None}],
    }
    (d / "book.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LibError):
        search(lib, "secret")


# --- schema / reindex ----------------------------------------------------

def test_schema_version_mismatch_triggers_rebuild(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов",
            [("Глава 1", "текст про кита")])
    sync(lib)
    conn = sqlite3.connect(lib / ".search.db")
    conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    res = search(lib, "кита")
    assert res["hits"]
    assert _meta_rows(lib)["schema_version"] != "999"


def test_reindex_flag_forces_rebuild(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "kit", "Сказка о ките", "Иван Хвостов",
            [("Глава 1", "текст про кита")])
    sync(lib)
    fp_before = _meta_rows(lib)["book:kit"]
    res = search(lib, "кита", reindex=True)
    assert res["hits"]
    assert _meta_rows(lib)["book:kit"] == fp_before   # содержимое не менялось, но пересборка не упала


# --- stemming --------------------------------------------------------------

def test_ru_stemming_recall(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "poe", "Сборник", "Автор",
            [("Гл1", "Это была поэзия чистой воды, все восхищались поэзией.")])
    for q in ("поэзию", "поэзии", "поэзия"):
        res = search(lib, q)
        assert res["hits"], f"query {q!r} должен найти «поэзия» через RU-стем"


def test_en_stemming_recall(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "clock", "Clockwork", "Author",
            [("Ch1", "The pendulum swung all night long.")])
    res = search(lib, "pendulums")
    assert res["hits"], "«pendulums» должен найти «pendulum» через EN-стем"


def test_en_stem_not_prefix_falls_back_to_word(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Book", "Author",
            [("Ch1", "This chapter is about poetry and prose.")])
    # snowball стем «poetry» -> «poetri» — НЕ префикс «poetry», страховка обязана
    # использовать слово как есть, а не «poetri» (которого нет в тексте).
    res = search(lib, "poetry")
    assert res["hits"]


# --- curious queries ---------------------------------------------------

def test_quote_inside_word_does_not_crash(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Irish Tales", "O'Brien",
            [("Ch1", "A story mentioning o'brien somewhere in the text.")])
    res = search(lib, 'o"brien')
    assert isinstance(res["hits"], list)                     # не падает


def test_parens_do_not_crash(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Book", "Author", [("Ch1", "some (parenthetical) text here")])
    res = search(lib, "(parenthetical)")
    assert isinstance(res["hits"], list)


def test_hyphen_word_matches_as_phrase(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Book", "Author",
            [("Ch1", "this is a well-known fact about the world")])
    res = search(lib, "well-known")
    assert res["hits"]


# --- OR fallback -------------------------------------------------------

def test_or_fallback_sets_partial_when_and_finds_nothing(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Book", "Author",
            [("Ch1", "текст содержит только маятники и больше ничего важного")])
    res = search(lib, "маятники совершенноневстречающеесяслово")
    assert res["partial"] is True
    assert res["hits"]
    assert any(h["book_id"] == "book1" for h in res["hits"])


def test_no_or_fallback_for_single_word(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Book", "Author", [("Ch1", "какой-то текст")])
    res = search(lib, "совершенноневстречающеесяслово")
    assert res == {"hits": [], "partial": False}


# --- book hits: n=None, ordering, cap<=3 --------------------------------

def test_book_hit_has_null_n_and_chapter_title(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "pelevin", "Уникальнотайтл Книга", "Виктор Пелевин",
            [("Гл1", "текст никак не связан с запросом")])
    res = search(lib, "Уникальнотайтл")
    assert res["hits"]
    hit = res["hits"][0]
    assert hit["n"] is None
    assert hit["chapter_title"] is None
    assert hit["book_title"] == "Уникальнотайтл Книга"


def test_book_hits_capped_at_three_and_come_before_chapters(tmp_path):
    lib = tmp_path / "library"
    for i in range(5):
        _mkbook(lib, f"book{i}", f"Редкийтерм Книга {i}", "Автор",
                [("Гл1", "редкийтерм встречается и в тексте главы тоже")])
    res = search(lib, "редкийтерм")
    book_hits = [h for h in res["hits"] if h["n"] is None]
    chapter_hits = [h for h in res["hits"] if h["n"] is not None]
    assert len(book_hits) <= 3
    assert res["hits"].index(book_hits[-1]) < res["hits"].index(chapter_hits[0])


def test_book_id_filter_scopes_results(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "book1", "Первая", "Автор", [("Гл1", "общееслово текст один")])
    _mkbook(lib, "book2", "Вторая", "Автор", [("Гл1", "общееслово текст два")])
    res = search(lib, "общееслово", book_id="book1")
    assert res["hits"]
    assert all(h["book_id"] == "book1" for h in res["hits"])


def test_limit_applies_to_combined_hits(tmp_path):
    lib = tmp_path / "library"
    for i in range(5):
        _mkbook(lib, f"book{i}", f"Книга {i}", "Автор",
                [("Гл1", "лимитноеслово встречается тут")])
    res = search(lib, "лимитноеслово", limit=2)
    assert len(res["hits"]) == 2


def test_review_status_book_is_indexed(tmp_path):
    lib = tmp_path / "library"
    _mkbook(lib, "reviewbook", "Ревьюкнига", "Автор",
            [("Гл1", "особыйревьютермин в тексте главы")], status="review")
    res = search(lib, "особыйревьютермин")
    assert res["hits"]


def test_no_fts5_raises_russian_liberror(tmp_path, monkeypatch):
    import librarian.search as search_mod
    real_connect = sqlite3.connect

    class _FakeConn:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, *a, **kw):
            if "fts5" in sql.lower():
                raise sqlite3.OperationalError("no such module: fts5")
            return self._real.execute(sql, *a, **kw)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def fake_connect(target, *a, **kw):
        return _FakeConn(real_connect(target, *a, **kw))

    monkeypatch.setattr(search_mod.sqlite3, "connect", fake_connect)
    lib = tmp_path / "library"
    with pytest.raises(LibError, match="FTS5"):
        search(lib, "что угодно")
