from __future__ import annotations

from pathlib import Path

import charset_normalizer

from librarian.config import Config
from librarian.errors import BrokenFileError
from librarian.extractors import base
from librarian.extractors.textrules import apply_heading_patterns, merge_lines
from librarian.ir import Format, RawDoc

# Кодировки, способные дать кириллицу — для fallback-аудита при моёбаке.
_CYR_ENCODINGS = ("utf-8", "cp1251", "koi8-r", "cp866", "maccyrillic", "iso8859-5")
_VOWELS = frozenset("аеёиоуыэюя")
_CONSONANTS = frozenset("бвгджзйклмнпрстфхцчшщ")


def _vowel_score(s: str) -> float:
    """0 — нет кириллицы; ~1 — правдоподобное соотношение гласных (~0.40)."""
    vl = [c for c in s.lower() if c in _VOWELS]
    cl = [c for c in s.lower() if c in _CONSONANTS]
    total = len(vl) + len(cl)
    if total == 0:
        return -1.0
    return 1.0 - abs(len(vl) / total - 0.40)


def _has_cyrillic(s: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in s)


def _read_text(data: bytes, name: str) -> str:
    """Декодируем bytes. charset_normalizer — основной путь; если его выбор
    даёт моёбаку (плохое соотношение гласных/согласных), пересобираем среди
    кириллических кодировок по vowel-score. Нужно для коротких русских
    образцов, где charset_normalizer 3.4 ошибается (koi8-r→shift_jis)."""
    best = charset_normalizer.from_bytes(data).best()
    if best is None:
        raise BrokenFileError(f"{name}: не удалось определить кодировку")
    pick = str(best)
    if _has_cyrillic(pick) and _vowel_score(pick) >= 0.85:
        return pick
    scored: list[tuple[float, str]] = []
    for enc in _CYR_ENCODINGS:
        try:
            s = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if _has_cyrillic(s):
            scored.append((_vowel_score(s), s))
    if scored:
        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[0][1]
    return pick


class TxtExtractor:
    format = Format.TXT

    def extract(self, path: Path, cfg: Config) -> RawDoc:
        text = _read_text(path.read_bytes(), path.name)
        paras: list[tuple[str, bool]] = []
        for chunk in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
            lines = [ln for ln in chunk.split("\n") if ln.strip()]
            if lines:
                paras.append((merge_lines(lines, cfg), len(lines) == 1))
        blocks = apply_heading_patterns(paras, cfg)
        return RawDoc(fmt=Format.TXT, blocks=blocks, title=None, author=None,
                      lang=None, ref_text=text)


base.register(TxtExtractor())
