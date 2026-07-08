from pathlib import Path

from conftest import tree_bytes

from librarian.config import Config
from librarian.pipeline import run_ingest

FIXTURE = Path(__file__).parent / "fixtures" / "txt" / "roman_cp1251.txt"


def test_second_ingest_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    assert run_ingest([FIXTURE], Config(), lib)[0].status == "ok"
    before = tree_bytes(lib)
    out = run_ingest([FIXTURE], Config(), lib)
    assert out[0].status == "skipped"
    assert tree_bytes(lib) == before
