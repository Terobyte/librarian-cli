from __future__ import annotations

import re
import unicodedata

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(s: str, max_len: int) -> str:
    s = unicodedata.normalize("NFC", s).casefold()
    s = "".join(_TRANSLIT.get(ch, ch) for ch in s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > max_len:
        cut = s.rfind("-", 1, max_len + 1)
        s = s[:cut] if cut > 0 else s[:max_len]
        s = s.strip("-")
    return s or "text"


def make_id(title: str | None, author: str | None, source_stem: str, max_len: int) -> str:
    base = " ".join(p for p in (author, title) if p)
    return slugify(base or source_stem, max_len)
