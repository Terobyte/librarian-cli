from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from librarian.catalog import get_chapters_core, info_projection, read_book, read_index
from librarian.search import search as run_search
from librarian.search import sync as sync_index

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


def build_server(lib_root: Path) -> FastMCP:
    """Собирает MCP-сервер: 5 read-only тулов поверх общего ридерского ядра."""
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

    server.add_tool(
        _list_books, name="list_books",
        description="Список всех книг в библиотеке: id, автор, название, число глав, "
                     "токенов, статус качества.")
    server.add_tool(
        _list_chapters, name="list_chapters",
        description="Оглавление книги по её id: номер, заголовок, число токенов и "
                     "краткое summary каждой главы.")
    server.add_tool(
        _find, name="find",
        description="Полнотекстовый поиск по главам и названиям/авторам всей "
                     "библиотеки (bm25, сниппеты, стемминг RU/EN). Параметр book_id "
                     "ограничивает поиск одной книгой.")
    server.add_tool(
        _get_chapters, name="get_chapters",
        description="Текст глав книги: по номерам (spec, например «1-3,5») или по "
                     "токен-бюджету (budget). Если не задать ни spec, ни budget — "
                     "используется бюджет по умолчанию 12000 токенов. Указывать оба "
                     "параметра одновременно нельзя. Если первая же глава не влезает "
                     "в бюджет — вернётся пустой текст с пояснением в message, а не "
                     "ошибка: можно повторить с бóльшим budget или указать spec.")
    server.add_tool(
        _book_info, name="book_info",
        description="Метаданные и метрики качества книги: book, metrics, subscores, "
                     "score, hard_triggers — та же проекция, что `lib info`.")
    return server


def serve(lib_root: Path) -> None:
    """Точка входа `lib serve`: синхронизирует индекс поиска один раз при старте
    (холодная сборка не платится в первом RPC), затем поднимает stdio MCP-сервер."""
    sync_index(lib_root)
    build_server(lib_root).run(transport="stdio")
