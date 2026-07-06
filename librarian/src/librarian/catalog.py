from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from librarian import PIPELINE_VERSION
from librarian.emit import canonical_json
from librarian.errors import UnknownBookError


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


def read_book(lib_root: Path, book_id: str) -> dict:
    bj = lib_root / book_id / "book.json"
    if not bj.is_file():
        raise UnknownBookError(f"книга «{book_id}» не найдена")
    return json.loads(bj.read_text(encoding="utf-8"))


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
