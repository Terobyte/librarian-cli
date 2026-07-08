from pathlib import Path

import pytest

from librarian.config import load_config
from librarian.pipeline import run_ingest
from conftest import tree_bytes

ROOT = Path(__file__).parent
FIXTURES = sorted((ROOT / "fixtures").rglob("*.*"))


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
