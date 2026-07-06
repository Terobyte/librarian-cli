import os
from pathlib import Path
import pytest
from librarian.emit import ingested_at, library_lock, publish, recover
from librarian.errors import LibError


def _mkbook(d: Path, marker: str):
    d.mkdir(parents=True)
    (d / "book.json").write_text(marker, encoding="utf-8")


def test_publish_replaces_and_cleans(tmp_path):
    lib = tmp_path
    _mkbook(lib / "my-book", "old")
    _mkbook(lib / ".staging" / "my-book", "new")
    publish(lib / ".staging" / "my-book", lib, "my-book")
    assert (lib / "my-book" / "book.json").read_text(encoding="utf-8") == "new"
    assert not (lib / ".trash").exists() and not (lib / ".staging" / "my-book").exists()


def test_recover_restores_trash_first(tmp_path):
    lib = tmp_path
    _mkbook(lib / ".trash" / "lost-book", "precious")
    _mkbook(lib / ".staging" / "lost-book", "half-built")
    recover(lib)
    assert (lib / "lost-book" / "book.json").read_text(encoding="utf-8") == "precious"
    assert not (lib / ".staging").exists() and not (lib / ".trash").exists()


def test_recover_keeps_existing_target(tmp_path):
    lib = tmp_path
    _mkbook(lib / "b", "current")
    _mkbook(lib / ".trash" / "b", "older")
    recover(lib)
    assert (lib / "b" / "book.json").read_text(encoding="utf-8") == "current"


def test_lock_times_out(tmp_path):
    with library_lock(tmp_path, 5):
        with pytest.raises(LibError):
            with library_lock(tmp_path, 0.3):
                pass


def test_ingested_at_source_date_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert ingested_at() == "1970-01-01T00:00:00Z"
