import os
from pathlib import Path


# Тесты гоняют экстракцию в текущем процессе: spawn-guard (§6.0 таймаут) добавлял бы
# ~1с на каждый ingest. Сам guard тестируется явно в unit/test_guard.py (откл. 22).
os.environ.setdefault("LIB_EXTRACT_INPROCESS", "1")


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Recursive {relative_path: file_bytes} excluding .lock, for golden/determinism/cache tests."""
    return {str(p.relative_to(root)).replace(os.sep, "/"): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != ".lock"}
