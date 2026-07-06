import os
from pathlib import Path


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Recursive {relative_path: file_bytes} excluding .lock, for golden/determinism/cache tests."""
    return {str(p.relative_to(root)).replace(os.sep, "/"): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != ".lock"}
