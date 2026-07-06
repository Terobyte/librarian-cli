from __future__ import annotations

from pathlib import Path
from typing import Protocol

from librarian.config import Config
from librarian.errors import LibError
from librarian.ir import Format, RawDoc


class Extractor(Protocol):
    format: Format
    def extract(self, path: Path, cfg: Config) -> RawDoc: ...


EXTRACTORS: dict[Format, Extractor] = {}


def register(extractor: Extractor) -> None:
    EXTRACTORS[extractor.format] = extractor


def get_extractor(fmt: Format) -> Extractor:
    if fmt not in EXTRACTORS:
        raise LibError(f"формат {fmt.value} будет поддержан в следующих этапах")
    return EXTRACTORS[fmt]
