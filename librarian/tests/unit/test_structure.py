from librarian.config import Config
from librarian.ir import Block, BlockKind
from librarian.structure import (build_tree, choose_cut_level, cut_chapters,
                                 fallback_cut, normalize_heading_levels)

CFG = Config()
H, P = BlockKind.HEADING, BlockKind.PARA

def _h(text, level): return Block(H, text, level=level)
def _p(text="абзац текста для объёма"): return Block(P, text)

def test_normalize_levels_dense():
    blocks = [_h("a", 2), _h("b", 4), _h("c", 2)]
    out = normalize_heading_levels(blocks)
    assert [b.level for b in out] == [1, 2, 1]

def test_tree_and_preface():
    blocks = [_p("до заголовка"), _h("Том 1", 1), _h("Глава 1", 2), _p(), _h("Глава 2", 2), _p()]
    root = build_tree(blocks, CFG)
    assert [s.title for s in root.children] == ["Начало", "Том 1"]
    assert [s.title for s in root.children[1].children] == ["Глава 1", "Глава 2"]

def test_cut_titles_are_paths():
    blocks = [_h("Том первый", 1), _h("Часть первая", 2), _p(), _h("Часть вторая", 2), _p()]
    root = build_tree(blocks, CFG)
    chapters = cut_chapters(root, 2, CFG)
    assert [c.title for c in chapters] == ["Том первый · Часть первая",
                                           "Том первый · Часть вторая"]

def test_cut_inner_headings_relative():
    blocks = [_h("Глава", 1), _p(), _h("Сцена", 2), _p()]
    root = build_tree(blocks, CFG)
    ch = cut_chapters(root, 1, CFG)[0]
    inner = [b for b in ch.blocks if b.kind is H]
    assert [b.level for b in inner] == [1]

def test_choose_level_deepens(monkeypatch):
    import librarian.structure as st
    monkeypatch.setattr(st, "draft_count",
                        lambda blocks: 20000 if any(b.level == 3 and b.kind is H for b in blocks) else 100)
    blocks = [_h("Том", 1), _h("Часть", 2), _h("Гл 1", 3), _p(), _h("Гл 2", 3), _p()]
    root = build_tree(blocks, CFG)
    assert choose_cut_level(root, CFG) == 3

def test_fallback_parts():
    blocks = [_p("слово " * 700) for _ in range(10)]
    chapters = fallback_cut(blocks, "Роман", CFG)
    assert len(chapters) >= 2
    assert chapters[0].title == f"Роман (1/{len(chapters)})"
    assert sum(len(c.blocks) for c in chapters) == 10


def test_normalize_heading_levels_none_level():
    # BUG F-12: normalize_heading_levels падает на HEADING с level=None
    blocks = [
        Block(BlockKind.HEADING, "Заголовок 1", level=None),
        Block(BlockKind.HEADING, "Заголовок 2", level=2),
    ]
    out = normalize_heading_levels(blocks)
    assert len(out) == 2
    # Проверяем, что HEADING-блоки получили числовые уровни
    assert all(b.level is not None for b in out if b.kind is BlockKind.HEADING)
    # Проверяем, что дерево строится без крашей
    root = build_tree(out, CFG)
    assert len(root.children) > 0


