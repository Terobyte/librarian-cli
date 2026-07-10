from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import snowballstemmer

from librarian.catalog import scan_books
from librarian.errors import LibError

SCHEMA_VERSION = "1"

_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_RU_STEMMER = snowballstemmer.stemmer("russian")
_EN_STEMMER = snowballstemmer.stemmer("english")

_LOCKED_MSG = "индекс занят другим процессом — повторите"


def _check_fts5() -> None:
    """FTS5 — расширение SQLite, не гарантировано в любой сборке (§3 спеки)."""
    try:
        c = sqlite3.connect(":memory:")
        try:
            c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        finally:
            c.close()
    except sqlite3.OperationalError:
        raise LibError("sqlite без поддержки FTS5 — поиск недоступен") from None


def _connect(lib_root: Path) -> sqlite3.Connection:
    _check_fts5()
    lib_root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(lib_root / ".search.db")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _begin(conn: sqlite3.Connection, immediate: bool) -> None:
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    except sqlite3.OperationalError as e:
        raise LibError(_LOCKED_MSG) from e


def _create_schema(conn: sqlite3.Connection) -> None:
    """DDL через execute() (не executescript — оно коммитит открытую транзакцию)."""
    conn.execute("DROP TABLE IF EXISTS chapters")
    conn.execute("DROP TABLE IF EXISTS books")
    conn.execute("DROP TABLE IF EXISTS meta")
    conn.execute(
        "CREATE VIRTUAL TABLE chapters USING fts5("
        "book_id UNINDEXED, n UNINDEXED, title, text, "
        "tokenize = 'unicode61 remove_diacritics 2')")
    conn.execute(
        "CREATE VIRTUAL TABLE books USING fts5("
        "book_id UNINDEXED, title, author, "
        "tokenize = 'unicode61 remove_diacritics 2')")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                 (SCHEMA_VERSION,))


def _chapter_path(lib_root: Path, book_id: str, file: str) -> Path:
    book_dir = (lib_root / book_id).resolve()
    ch_path = (lib_root / book_id / file).resolve()
    if not ch_path.is_relative_to(book_dir):
        raise LibError(f"недопустимый путь главы: {file}")
    return ch_path


def _fingerprint(lib_root: Path, book_id: str, book: dict) -> str:
    """sha256(book.json) + (size, mtime_ns) каждой главы (§3: ловит реингест,
    ручную правку book.json/meta_locked и прямую правку .md по stat)."""
    bj_bytes = (lib_root / book_id / "book.json").read_bytes()
    h = hashlib.sha256(bj_bytes)
    for ch in sorted(book.get("chapters", []), key=lambda c: c["n"]):
        ch_path = _chapter_path(lib_root, book_id, ch["file"])
        try:
            st = ch_path.stat()
            h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        except OSError:
            h.update(b"MISSING")
    return h.hexdigest()


def _do_sync(conn: sqlite3.Connection, lib_root: Path, *, force: bool) -> None:
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        row = None
    need_rebuild = force or row is None or row[0] != SCHEMA_VERSION
    if need_rebuild:
        _create_schema(conn)
        known: dict[str, str] = {}
    else:
        known = {k[len("book:"):]: v for k, v in conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE 'book:%'")}

    current = dict(scan_books(lib_root))
    fingerprints = {bid: _fingerprint(lib_root, bid, book)
                     for bid, book in current.items()}

    for bid in set(known) - set(current):
        conn.execute("DELETE FROM chapters WHERE book_id = ?", (bid,))
        conn.execute("DELETE FROM books WHERE book_id = ?", (bid,))
        conn.execute("DELETE FROM meta WHERE key = ?", (f"book:{bid}",))

    for bid, book in current.items():
        if known.get(bid) == fingerprints[bid]:
            continue
        conn.execute("DELETE FROM chapters WHERE book_id = ?", (bid,))
        conn.execute("DELETE FROM books WHERE book_id = ?", (bid,))
        conn.execute("INSERT INTO books(book_id, title, author) VALUES (?, ?, ?)",
                     (bid, book.get("title") or "", book.get("author") or ""))
        for ch in book.get("chapters", []):
            ch_path = _chapter_path(lib_root, bid, ch["file"])
            text = ch_path.read_text(encoding="utf-8")
            conn.execute(
                "INSERT INTO chapters(book_id, n, title, text) VALUES (?, ?, ?, ?)",
                (bid, ch["n"], ch.get("title") or "", text))
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                     (f"book:{bid}", fingerprints[bid]))


def sync(lib_root: Path, *, force: bool = False) -> None:
    """Ленивая синхронизация .search.db с library/: fingerprint-сверка,
    переиндексация изменённого, весь write-путь — одна транзакция (§3)."""
    conn = _connect(lib_root)
    try:
        _begin(conn, immediate=True)
        try:
            _do_sync(conn, lib_root, force=force)
        except Exception:
            conn.rollback()
            raise
        conn.commit()
    finally:
        conn.close()


def _stem_word(word: str) -> str:
    """Стем вместо слова, только если он префикс исходного слова и len>=3
    (§3: страховка от en «poetry»→«poetri» — не префикс)."""
    wl = word.lower()
    stemmer = _RU_STEMMER if _CYRILLIC_RE.search(word) else _EN_STEMMER
    stemmed = stemmer.stemWord(wl)
    if len(stemmed) >= 3 and wl.startswith(stemmed):
        return stemmed
    return word


def _escape(word: str) -> str:
    return '"' + word.replace('"', '""') + '"*'


def _build_match(words: list[str], joiner: str) -> str:
    return f" {joiner} ".join(_escape(_stem_word(w)) for w in words)


def _book_hits(conn: sqlite3.Connection, match: str, book_id: str | None) -> list[dict]:
    sql = ("SELECT book_id, title, author, "
           "highlight(books, 1, '«', '»'), highlight(books, 2, '«', '»'), "
           "bm25(books, 0, 2.0, 1.0) AS rank "
           "FROM books WHERE books MATCH ?")
    params: list = [match]
    if book_id is not None:
        sql += " AND book_id = ?"
        params.append(book_id)
    sql += " ORDER BY rank LIMIT 3"
    hits = []
    for bid, title, author, h_title, h_author, _rank in conn.execute(sql, params):
        snippet = f"{h_title} — {h_author}" if author else h_title
        hits.append({"book_id": bid, "book_title": title, "author": author,
                     "n": None, "chapter_title": None, "snippet": snippet})
    return hits


def _chapter_hits(conn: sqlite3.Connection, match: str, book_id: str | None,
                   limit: int) -> list[dict]:
    sql = ("SELECT book_id, n, title, snippet(chapters, 3, '«', '»', '…', 12), "
           "bm25(chapters, 0, 0, 5.0, 1.0) AS rank "
           "FROM chapters WHERE chapters MATCH ?")
    params: list = [match]
    if book_id is not None:
        sql += " AND book_id = ?"
        params.append(book_id)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []
    ids = sorted({r[0] for r in rows})
    meta = {bid: (title, author) for bid, title, author in conn.execute(
        f"SELECT book_id, title, author FROM books WHERE book_id IN "
        f"({','.join('?' * len(ids))})", ids)}
    hits = []
    for bid, n, ch_title, snippet, _rank in rows:
        title, author = meta.get(bid, (None, None))
        hits.append({"book_id": bid, "book_title": title, "author": author,
                     "n": n, "chapter_title": ch_title, "snippet": snippet})
    return hits


def _run_query(conn: sqlite3.Connection, match: str, *, limit: int,
                book_id: str | None) -> list[dict]:
    hits = _book_hits(conn, match, book_id) + _chapter_hits(conn, match, book_id, limit)
    return hits[:limit]


def chapter_candidates(lib_root: Path, words: list[str], *, k: int = 20
                        ) -> list[tuple[str, int]]:
    """Кандидатные главы для verify shelf-режима (§3.4): OR-match по `words`, топ-k
    (book_id, n) по bm25, без сниппетов/highlight — search() не подходит: подмешивает
    книжные хиты с n=None и платит за snippet. Тот же паттерн синка/транзакции."""
    sync(lib_root)
    conn = _connect(lib_root)
    try:
        _begin(conn, immediate=False)
        try:
            rows = conn.execute(
                "SELECT book_id, n FROM chapters WHERE chapters MATCH ? "
                "ORDER BY bm25(chapters, 0, 0, 5.0, 1.0), book_id, n LIMIT ?",
                (_build_match(words, "OR"), k)).fetchall()
        finally:
            conn.commit()
    finally:
        conn.close()
    return [(bid, n) for bid, n in rows]


def search(lib_root: Path, query: str, *, limit: int = 10, book_id: str | None = None,
           reindex: bool = False) -> dict:
    """Синхронизирует индекс, затем ищет. Хит: {book_id, book_title, author, n,
    chapter_title, snippet}; книжный хит — n=None, chapter_title=None."""
    words = query.split()
    if not words:
        return {"hits": [], "partial": False}
    sync(lib_root, force=reindex)
    conn = _connect(lib_root)
    try:
        _begin(conn, immediate=False)
        try:
            hits = _run_query(conn, _build_match(words, "AND"), limit=limit,
                              book_id=book_id)
            partial = False
            if not hits and len(words) >= 2:
                hits = _run_query(conn, _build_match(words, "OR"), limit=limit,
                                  book_id=book_id)
                partial = True
        finally:
            conn.commit()
    finally:
        conn.close()
    return {"hits": hits, "partial": partial}
