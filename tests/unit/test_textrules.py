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


def test_apply_patterns_to_blocks_mixed():
    # DOCX/PDF-fallback (§6.5, §7.2 P5.5): PARA-однострочники через паттерны 6.1.3,
    # ранги сжимаются в плотные уровни; QUOTE и многострочные PARA не трогаются.
    from librarian.config import load_config
    from librarian.extractors.textrules import apply_patterns_to_blocks
    from librarian.ir import Block, BlockKind

    cfg = load_config(None)
    blocks = [
        Block(BlockKind.PARA, "Часть первая"),                    # rank2
        Block(BlockKind.PARA, "Обычный абзац текста, спокойный и длинный."),
        Block(BlockKind.PARA, "Глава 1"),                         # rank3
        Block(BlockKind.QUOTE, "Глава 2"),                        # не PARA — не трогаем
        Block(BlockKind.PARA, "Глава 3\nвторая строка"),          # многострочный — не трогаем
    ]
    out = apply_patterns_to_blocks(blocks, cfg)
    assert [b.kind for b in out] == [BlockKind.HEADING, BlockKind.PARA,
                                     BlockKind.HEADING, BlockKind.QUOTE,
                                     BlockKind.PARA]
    assert out[0].level == 1 and out[2].level == 2                # ранги {2,3} → уровни {1,2}
    assert out[2].origin == "pattern:rank3"


def test_apply_patterns_to_blocks_no_match():
    from librarian.config import load_config
    from librarian.extractors.textrules import apply_patterns_to_blocks
    from librarian.ir import Block, BlockKind

    blocks = [Block(BlockKind.PARA, "Просто текст без намёка на главы.")]
    out = apply_patterns_to_blocks(blocks, load_config(None))
    assert [b.kind for b in out] == [BlockKind.PARA]
