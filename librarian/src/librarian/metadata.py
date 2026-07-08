from __future__ import annotations

from librarian.slug import slugify

# Правка этого множества ⇒ поднять PIPELINE_VERSION: блоклист захардкожен и
# НЕ входит в cache_key, иначе изменение фильтра пройдёт мимо реингеста (§9 P1).
_SLUG_BLOCKLIST = {"untitled", "unknown", "no-title", "title", "na", "n-a",
                   "none", "item-not-available", "anna-s-archive", "get"}


def _is_placeholder(t: str) -> bool:
    return slugify(t, 80) in _SLUG_BLOCKLIST or len(t.strip()) < 2


def repair_metadata(raw, path) -> tuple[str | None, str | None, bool, str | None]:
    """R1: непустой placeholder-заголовок → сбросить title (пайплайн возьмёт имя
    файла) и провести книгу через review. Пусто/чисто — не трогаем (§9 P1)."""
    t = (raw.title or "").strip()
    if t and _is_placeholder(t):
        return None, raw.author, True, "metadata_repaired (имя файла)"
    return raw.title, raw.author, False, None
