import json
import os
from pathlib import Path


# Тесты гоняют экстракцию в текущем процессе: spawn-guard (§6.0 таймаут) добавлял бы
# ~1с на каждый ingest. Сам guard тестируется явно в unit/test_guard.py (откл. 22).
os.environ.setdefault("LIB_EXTRACT_INPROCESS", "1")


def _mkbook(lib: Path, bid: str, title: str, author: str,
            chapters: list[tuple[str, str]], status: str = "ok", summary=None) -> Path:
    """chapters: list of (title, text). Пишет book.json + chapters/NNN.md напрямую,
    без прогона пайплайна — быстрый и точный контроль над содержимым для юнитов
    (общий хелпер test_search.py/test_serve.py, T2 конформанс: вынос без изменения
    поведения). summary — значение поля summary у каждой главы: константа (по
    умолчанию None, как в test_search.py) или callable(n) -> str для per-chapter
    значения (test_serve.py передаёт своё: "summary {n}")."""
    d = lib / bid
    (d / "chapters").mkdir(parents=True, exist_ok=True)
    entries = []
    for n, (ctitle, text) in enumerate(chapters, 1):
        fname = f"chapters/{n:03d}.md"
        (d / fname).write_text(text, encoding="utf-8")
        entries.append({"n": n, "file": fname, "title": ctitle,
                        "tokens": len(text.split()),
                        "summary": summary(n) if callable(summary) else summary})
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


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Recursive {relative_path: file_bytes} excluding .lock and .search.db (derived
    cache, M6), for golden/determinism/cache tests."""
    return {str(p.relative_to(root)).replace(os.sep, "/"): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name not in (".lock", ".search.db")}
