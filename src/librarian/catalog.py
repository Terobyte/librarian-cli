from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from librarian import PIPELINE_VERSION
from librarian.emit import canonical_json
from librarian.errors import LibError, UnknownBookError


def scan_books(lib_root: Path) -> list[tuple[str, dict]]:
    if not lib_root.is_dir():
        return []
    out: list[tuple[str, dict]] = []
    for d in sorted(p for p in lib_root.iterdir()
                    if p.is_dir() and not p.name.startswith(".")):
        bj = d / "book.json"
        if not bj.is_file():
            continue
        try:
            out.append((d.name, json.loads(bj.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError) as e:
            print(f"предупреждение: {d.name}/book.json повреждён ({e}), книга пропущена",
                  file=sys.stderr)
    return out


def rebuild_index(lib_root: Path) -> None:
    books = [{"id": bid,
              "title": b.get("title"),
              "author": b.get("author"),
              "chapters": len(b.get("chapters", [])),
              "total_tokens": b.get("total_tokens", 0),
              "status": b.get("quality", {}).get("status")}
             for bid, b in scan_books(lib_root)]
    index = {"pipeline_version": PIPELINE_VERSION,
             "books": sorted(books, key=lambda x: x["id"])}
    lib_root.mkdir(parents=True, exist_ok=True)
    tmp = lib_root / "index.json.tmp"
    tmp.write_text(canonical_json(index), encoding="utf-8", newline="\n")
    os.replace(tmp, lib_root / "index.json")


def validate_book_id(lib_root: Path, book_id: str) -> None:
    """Правила rm (cli.py, дословно) — единая проверка для всех читателей."""
    resolved = (lib_root / book_id).resolve()
    if ("/" in book_id or "\\" in book_id
            or resolved == lib_root.resolve()
            or not resolved.is_relative_to(lib_root.resolve())):
        raise LibError(f"недопустимый id книги: «{book_id}»")


def read_book(lib_root: Path, book_id: str) -> dict:
    validate_book_id(lib_root, book_id)
    bj = lib_root / book_id / "book.json"
    if not bj.is_file():
        raise UnknownBookError(f"книга «{book_id}» не найдена")
    return json.loads(bj.read_text(encoding="utf-8"))


def read_index(lib_root: Path) -> list[dict]:
    """Проекция каталога для `lib list` и MCP list_books."""
    idx_path = lib_root / "index.json"
    if not idx_path.is_file():
        return []
    return json.loads(idx_path.read_text(encoding="utf-8"))["books"]


def info_projection(lib_root: Path, book_id: str) -> dict:
    """Проекция для `lib info` и MCP book_info: book.json + report.json."""
    book = read_book(lib_root, book_id)
    report_path = lib_root / book_id / "report.json"
    report = (json.loads(report_path.read_text(encoding="utf-8"))
              if report_path.is_file() else {})
    return {"book": book,
            "metrics": report.get("metrics", {}),
            "subscores": report.get("subscores", {}),
            "score": report.get("score"),
            "hard_triggers": report.get("hard_triggers", [])}


def chapter_text(lib_root: Path, book_id: str, file: str) -> str:
    """Читает текст одной главы; traversal-чек как search._chapter_path (§6 спеки:
    хелпер общий для get_chapters_core и verify, третья копия проверки не заводится)."""
    book_dir = (lib_root / book_id).resolve()
    ch_path = (lib_root / book_id / file).resolve()
    if not ch_path.is_relative_to(book_dir):
        raise LibError(f"недопустимый путь главы: {file}")
    return ch_path.read_text(encoding="utf-8")


def get_chapters_core(lib_root: Path, book_id: str, *, spec: str | None = None,
                       budget: int | None = None, from_: int = 1) -> dict:
    """Выбор глав по spec/budget — общее ядро `lib get` и MCP get_chapters.

    Возвращает {"text", "chapters", "next_from", "message"}. Budget-режим:
    первая глава не влезает в бюджет → НЕ исключение, пустой результат с message.
    """
    if (spec is None) == (budget is None):
        raise ValueError("нужно ровно одно из: spec или budget")

    book = read_book(lib_root, book_id)
    chaps = sorted(book["chapters"], key=lambda c: c["n"])
    message: str | None = None
    next_from: int | None = None
    if spec is not None:
        from librarian.cli import parse_spec        # локальный импорт: cli импортирует catalog на верхнем уровне
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
            message = (f"глава {from_} ({chaps[from_ - 1]['tokens']} токенов) "
                        f"не влезает в бюджет {budget}")
            return {"text": "", "chapters": [], "next_from": from_, "message": message}
        if from_ - 1 + len(nums) < len(chaps):
            first_skipped = chaps[from_ - 1 + len(nums)]["n"]
            next_from = first_skipped
            message = f"не вошли в бюджет: главы {first_skipped}–{chaps[-1]['n']}"
    by_n = {ch["n"]: ch for ch in chaps}
    texts = [chapter_text(lib_root, book_id, by_n[n]["file"]) for n in nums]
    text = "\n\n".join(t.rstrip("\n") for t in texts) + "\n"
    return {"text": text, "chapters": nums, "next_from": next_from, "message": message}


def find_by_sha256(lib_root: Path, sha: str) -> str | None:
    for bid, b in scan_books(lib_root):
        if b.get("source", {}).get("sha256") == sha:
            return bid
    return None


def find_by_cache_key(lib_root: Path, key: str) -> str | None:
    for bid, b in scan_books(lib_root):
        if b.get("provenance", {}).get("cache_key") == key:
            return bid
    return None


def broken_dirs(lib_root: Path) -> list[str]:
    """Каталоги книг с нечитаемым book.json (С-4) — для doctor."""
    out: list[str] = []
    if not lib_root.is_dir():
        return out
    for d in sorted(p for p in lib_root.iterdir()
                    if p.is_dir() and not p.name.startswith(".")):
        bj = d / "book.json"
        if not bj.is_file():
            continue
        try:
            json.loads(bj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            out.append(d.name)
    return out
