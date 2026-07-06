# src/librarian/extractors/zipsafe.py
from __future__ import annotations

import zipfile
from pathlib import Path

from librarian.config import Config
from librarian.errors import BrokenFileError

_CHUNK = 1 << 20            # 1 МБ — шаг потокового чтения


def check_zip(path: Path, cfg: Config) -> None:
    """Защита от zip-bomb (§6.0): сначала по заявленным размерам записей,
    затем потоковой распаковкой с контролем фактических байтов (заголовки
    zip умеют врать — overlapping-записи, кривой file_size)."""
    max_total = cfg.limits.zip_max_uncompressed_mb * 1024 * 1024
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            declared = sum(i.file_size for i in infos)
            compressed = max(1, sum(i.compress_size for i in infos))
            if declared > max_total or declared / compressed > cfg.limits.zip_ratio_max:
                raise BrokenFileError(f"{path.name}: похоже на zip-bomb")
            total = 0
            for info in infos:
                with z.open(info) as f:
                    while chunk := f.read(_CHUNK):
                        total += len(chunk)
                        if total > max_total:
                            raise BrokenFileError(f"{path.name}: похоже на zip-bomb")
    except zipfile.BadZipFile as e:
        raise BrokenFileError(f"{path.name}: битый zip: {e}") from None


def read_entry(path: Path, name: str, cfg: Config) -> bytes:
    """Потоковое чтение одной записи; фактический размер под лимитом."""
    max_total = cfg.limits.zip_max_uncompressed_mb * 1024 * 1024
    out = bytearray()
    try:
        with zipfile.ZipFile(path) as z, z.open(name) as f:
            while chunk := f.read(_CHUNK):
                out += chunk
                if len(out) > max_total:
                    raise BrokenFileError(f"{path.name}: похоже на zip-bomb")
    except zipfile.BadZipFile as e:
        raise BrokenFileError(f"{path.name}: битый zip: {e}") from None
    except KeyError:
        raise BrokenFileError(f"{path.name}: в архиве нет записи {name}") from None
    return bytes(out)
