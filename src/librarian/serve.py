from __future__ import annotations

import functools
from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP

from librarian.catalog import get_chapters_core, info_projection, read_book, read_index
from librarian.search import search as run_search
from librarian.search import sync as sync_index
from librarian.verify import verify_quote as run_verify_quote

DEFAULT_BUDGET = 12000


# --- тонкие адаптеры над ядром (catalog.py / search.py) — plain-функции, зовутся
# напрямую из юнитов синхронно; регистрируются как MCP-тулы в build_server() ---

def list_books(lib_root: Path) -> list[dict]:
    """Список всех книг библиотеки: id, автор, название, число глав, токенов, статус."""
    return read_index(lib_root)


def list_chapters(lib_root: Path, book_id: str) -> list[dict]:
    """Оглавление книги: номер, заголовок, число токенов и summary каждой главы."""
    book = read_book(lib_root, book_id)
    return [{"n": ch["n"], "title": ch["title"], "tokens": ch["tokens"],
             "summary": ch.get("summary")}
            for ch in sorted(book["chapters"], key=lambda c: c["n"])]


def find(lib_root: Path, query: str, limit: int = 10, book_id: str | None = None) -> dict:
    """Полнотекстовый поиск по главам и названиям/авторам всей библиотеки."""
    return run_search(lib_root, query, limit=limit, book_id=book_id)


def get_chapters(lib_root: Path, book_id: str, spec: str | None = None,
                  budget: int | None = None, from_: int = 1) -> dict:
    """Текст глав книги — по номерам (spec) или по токен-бюджету (budget). Ни spec,
    ни budget не заданы → budget по умолчанию 12000. Оба заданы → ошибка тула
    (пробрасывается ядром). Первая глава не влезает в бюджет — не исключение,
    а структурированный пустой результат с next_from/message."""
    if spec is None and budget is None:
        budget = DEFAULT_BUDGET
    return get_chapters_core(lib_root, book_id, spec=spec, budget=budget, from_=from_)


def book_info(lib_root: Path, book_id: str) -> dict:
    """Метаданные и метрики качества книги — та же проекция, что `lib info`."""
    return info_projection(lib_root, book_id)


def verify_quote(lib_root: Path, quote: str, book_id: str | None = None,
                  limit: int = 3) -> dict:
    """Проверка цитаты против библиотеки: вердикт, локация, similarity, passage,
    word-diff. book_id задан — режим проверки (полный скан книги); не задан —
    режим полки (FTS5-кандидаты по всей библиотеке). verdict:null/not_found —
    валидные структурные ответы; LibError/ValueError пробрасываются ядром."""
    return run_verify_quote(lib_root, quote, book_id=book_id, limit=limit)


def build_server(lib_root: Path) -> FastMCP:
    """Собирает MCP-сервер: 6 read-only тулов поверх общего ридерского ядра."""
    server = FastMCP("librarian")

    def _list_books() -> list[dict]:
        return list_books(lib_root)

    def _list_chapters(book_id: str) -> list[dict]:
        return list_chapters(lib_root, book_id)

    def _find(query: str, limit: int = 10, book_id: str | None = None) -> dict:
        return find(lib_root, query, limit=limit, book_id=book_id)

    def _get_chapters(book_id: str, spec: str | None = None, budget: int | None = None,
                       from_: int = 1) -> dict:
        return get_chapters(lib_root, book_id, spec=spec, budget=budget, from_=from_)

    def _book_info(book_id: str) -> dict:
        return book_info(lib_root, book_id)

    async def _verify_quote(quote: str, book_id: str | None = None,
                             limit: int = 3) -> dict:
        # MAJOR-3/Plan v2: FastMCP зовёт sync-тулы инлайн в event loop — полный
        # скан большой книги блокировал бы весь stdio-сервер; выносим в поток.
        call = functools.partial(verify_quote, lib_root, quote, book_id=book_id,
                                  limit=limit)
        return await anyio.to_thread.run_sync(call)

    server.add_tool(
        _list_books, name="list_books",
        description="List of all books in the library: id, author, title, "
                     "chapter count, token count, quality status.")
    server.add_tool(
        _list_chapters, name="list_chapters",
        description="Table of contents for a book by its id: chapter number, "
                     "title, token count, and a short summary for each chapter.")
    server.add_tool(
        _find, name="find",
        description="Full-text search across chapters and book titles/authors "
                     "in the whole library (bm25 ranking, snippets, RU/EN "
                     "stemming). The book_id parameter restricts the search to "
                     "one book.")
    server.add_tool(
        _get_chapters, name="get_chapters",
        description="Chapter text of a book: by chapter numbers (spec, e.g. "
                     "\"1-3,5\") or by token budget (budget). If neither spec "
                     "nor budget is given, the default budget of 12000 tokens "
                     "is used. Passing both parameters at once is an error. If "
                     "even the first chapter doesn't fit the budget, an empty "
                     "text with an explanation in message is returned instead "
                     "of an error — retry with a larger budget or use spec.")
    server.add_tool(
        _book_info, name="book_info",
        description="Metadata and quality metrics for a book: book, metrics, "
                     "subscores, score, hard_triggers — the same projection as "
                     "`lib info`.")
    server.add_tool(
        _verify_quote, name="verify_quote",
        description="Verify a quote against the library: an exact/close/"
                     "distorted/not_found verdict, the book/chapter location, "
                     "similarity, a passage of surrounding text, and a "
                     "word-level diff against the source. Provide book_id to "
                     "check one specific book (full scan, no FTS5 needed); "
                     "omit it to search the whole library via FTS5 candidates. "
                     "Use this whenever you quote a book to the user.")
    return server


def serve(lib_root: Path) -> None:
    """Точка входа `lib serve`: синхронизирует индекс поиска один раз при старте
    (холодная сборка не платится в первом RPC), затем поднимает stdio MCP-сервер."""
    sync_index(lib_root)
    build_server(lib_root).run(transport="stdio")
