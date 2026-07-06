import os
from pathlib import Path

import pytest

from librarian.config import load_config
from librarian.pipeline import run_ingest

ROOT = Path(__file__).parent
FIXTURES = sorted((ROOT / "fixtures").rglob("*.*"))


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)).replace(os.sep, "/"): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != ".lock"}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_golden(fixture, tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    golden = ROOT / "golden" / fixture.stem
    assert golden.is_dir(), f"нет golden для {fixture.stem}: запусти scripts/update_golden.py"
    run_ingest([fixture], load_config(None), tmp_path)
    actual, expected = tree_bytes(tmp_path), tree_bytes(golden)
    assert sorted(actual) == sorted(expected)
    for rel in sorted(expected):
        assert actual[rel] == expected[rel], f"байтовое расхождение: {rel}"
