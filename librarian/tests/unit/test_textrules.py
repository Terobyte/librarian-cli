from librarian.config import Config
from librarian.extractors.textrules import compile_patterns, line_rank, merge_lines

CFG = Config()

def test_merge_plain_hyphen():
    assert merge_lines(["нау-", "ка победила"], CFG) == "наука победила"

def test_merge_particle_keeps_hyphen():
    assert merge_lines(["кто-", "то пришёл"], CFG) == "кто-то пришёл"
    assert merge_lines(["как-", "нибудь потом"], CFG) == "как-нибудь потом"

def test_merge_capital_next_is_space_join():
    assert merge_lines(["тире-", "Москва"], CFG) == "тире- Москва"

def test_merge_cross_alphabet_no_glue():
    assert merge_lines(["сло-", "world"], CFG) == "сло- world"

def test_plain_join():
    assert merge_lines(["первая строка", "вторая строка"], CFG) == "первая строка вторая строка"

def test_ranks():
    pats = compile_patterns(CFG)
    assert line_rank("Том первый", pats) == 1
    assert line_rank("ЧАСТЬ ВТОРАЯ", pats) == 2
    assert line_rank("Глава 3. Встреча", pats) == 3
    assert line_rank("XIV.", pats) == 3
    assert line_rank("ЭПИЛОГ", pats) == 3
    assert line_rank("Обычное предложение.", pats) is None
