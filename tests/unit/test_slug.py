from librarian.slug import make_id, slugify

def test_translit_casefold_order():
    assert slugify("Война и Мир", 60) == "voyna-i-mir"
    assert slugify("Щёлкин съел объём", 60) == "schelkin-sel-obem"

def test_specials_collapse():
    assert slugify("a---b  c!!!", 60) == "a-b-c"
    assert slugify("«Привет»", 60) == "privet"

def test_truncate_on_dash_no_hanging():
    assert slugify("aaa-bbb-ccc", 7) == "aaa-bbb"
    assert slugify("aaaaaaaaaa", 5) == "aaaaa"
    assert not slugify("aaa-bbb", 4).endswith("-")

def test_empty_fallback():
    assert slugify("!!!", 60) == "text"

def test_make_id():
    assert make_id("Война и мир", "Лев Толстой", "voyna", 60) == "lev-tolstoy-voyna-i-mir"
    assert make_id(None, None, "Мой Файл", 60) == "moy-fayl"
