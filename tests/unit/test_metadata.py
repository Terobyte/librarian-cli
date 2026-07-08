from pathlib import Path

from librarian.ir import Format, RawDoc
from librarian.metadata import repair_metadata


def _raw(title, author=""):
    return RawDoc(fmt=Format.FB2, blocks=[], title=title, author=author,
                  lang="ru", ref_text="")


P = Path("dir/some_book.fb2")          # repair_metadata путь не читает (чистая)


def test_r1_get_placeholder_repaired():
    title, author, repaired, reason = repair_metadata(_raw("GET", "Иван Хвостов"), P)
    assert title is None
    assert author == "Иван Хвостов"                 # автор сохранён
    assert repaired is True
    assert reason == "metadata_repaired (имя файла)"


def test_r1_item_not_available_with_trailing_punct():
    title, _, repaired, _ = repair_metadata(_raw("Item not available."), P)
    assert repaired is True and title is None


def test_r1_curly_apostrophe_annas_archive():
    # U+2019 (curly) → slugify → "anna-s-archive" ∈ блоклиста
    title, _, repaired, _ = repair_metadata(_raw("Anna’s Archive"), P)
    assert repaired is True and title is None


def test_r1_len_lt_2_repaired():
    title, _, repaired, _ = repair_metadata(_raw("A"), P)
    assert repaired is True and title is None


def test_clean_title_passthrough():
    title, author, repaired, reason = repair_metadata(_raw("Сказка о ките", "Иван Хвостов"), P)
    assert title == "Сказка о ките" and author == "Иван Хвостов"
    assert repaired is False and reason is None


def test_empty_title_passthrough():
    # пустой title не «чинится» (R3) — A2 решается id-унификацией, не репарацией
    title, author, repaired, reason = repair_metadata(_raw(None, "Uploader X"), P)
    assert title is None and author == "Uploader X"
    assert repaired is False and reason is None


def test_whitespace_only_title_passthrough():
    title, _, repaired, _ = repair_metadata(_raw("   "), P)
    assert repaired is False and title == "   "
