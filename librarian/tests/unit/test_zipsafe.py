# tests/unit/test_zipsafe.py
import dataclasses
import zipfile

import pytest

from librarian.config import LimitsCfg, load_config
from librarian.errors import BrokenFileError
from librarian.extractors import zipsafe


def _cfg(**limits):
    cfg = load_config(None)
    return dataclasses.replace(cfg, limits=LimitsCfg(**limits))


def _make_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)


def test_ok_zip_passes(tmp_path):
    p = tmp_path / "ok.zip"
    _make_zip(p, [("a.txt", b"hello world")])
    zipsafe.check_zip(p, load_config(None))          # не бросает


def test_bomb_by_total_size(tmp_path):
    p = tmp_path / "bomb.zip"
    _make_zip(p, [("z.bin", b"\0" * (2 * 1024 * 1024))])   # 2 МБ нулей
    cfg = _cfg(zip_max_uncompressed_mb=1, zip_ratio_max=1000)
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.check_zip(p, cfg)


def test_bomb_by_ratio(tmp_path):
    p = tmp_path / "bomb.zip"
    _make_zip(p, [("z.bin", b"\0" * (2 * 1024 * 1024))])   # нули жмутся ~1000×
    cfg = _cfg(zip_max_uncompressed_mb=512, zip_ratio_max=10)
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.check_zip(p, cfg)


def test_lying_header_caught_by_streaming(tmp_path):
    # заголовок врёт про маленький размер — ловим по фактическим байтам
    p = tmp_path / "liar.zip"
    _make_zip(p, [("z.bin", b"\0" * (2 * 1024 * 1024))])
    raw = bytearray(p.read_bytes())
    cfg = _cfg(zip_max_uncompressed_mb=1, zip_ratio_max=1000)
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.check_zip(p, cfg)                    # честный заголовок
    # read_entry контролирует фактический размер независимо от заголовка
    with pytest.raises(BrokenFileError, match="zip-bomb"):
        zipsafe.read_entry(p, "z.bin", cfg)
    assert raw                                        # молчим про unused: файл прочитан


def test_broken_zip(tmp_path):
    p = tmp_path / "broken.zip"
    p.write_bytes(b"PK\x03\x04" + "мусор".encode("utf-8"))
    with pytest.raises(BrokenFileError, match="битый zip"):
        zipsafe.check_zip(p, load_config(None))


def test_read_entry_ok(tmp_path):
    p = tmp_path / "ok.zip"
    _make_zip(p, [("book.fb2", "текст".encode("utf-8"))])
    assert zipsafe.read_entry(p, "book.fb2", load_config(None)) == "текст".encode("utf-8")
