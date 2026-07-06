import os
from pathlib import Path

import pytest

from librarian.config import Config
from librarian.emit import publish, recover
from librarian.pipeline import run_ingest

FIXTURE = Path(__file__).parent / "fixtures" / "txt" / "roman_cp1251.txt"


def test_crash_between_trash_and_replace(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    bid = run_ingest([FIXTURE], Config(), lib)[0].book_id
    original = (lib / bid / "book.json").read_bytes()

    real_replace = os.replace
    calls = {"n": 0}

    def crashy(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("имитация падения процесса")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", crashy)
    staging = lib / ".staging" / bid
    (staging / "chapters").mkdir(parents=True)
    (staging / "book.json").write_text("новая версия", encoding="utf-8")
    with pytest.raises(RuntimeError):
        publish(staging, lib, bid)
    monkeypatch.setattr(os, "replace", real_replace)

    assert not (lib / bid).exists()
    recover(lib)
    assert (lib / bid / "book.json").read_bytes() == original
    assert not (lib / ".trash").exists() and not (lib / ".staging").exists()
