from __future__ import annotations

import re

from librarian.config import Config
from librarian.ir import Block, BlockKind

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _alphabet(ch: str) -> str:
    ch = ch.casefold()
    if "а" <= ch <= "я" or ch == "ё":
        return "cyr"
    if ch.isascii() and ch.isalpha():
        return "lat"
    return "other"


def merge_lines(lines: list[str], cfg: Config) -> str:
    out = lines[0].strip()
    for raw_next in lines[1:]:
        nxt = raw_next.strip()
        if not nxt:
            continue
        hyphen_break = (
            len(out) >= 2 and out.endswith("-") and out[-2].isalpha()
            and nxt[0].isalpha() and nxt[0].islower()
            and _alphabet(out[-2]) == _alphabet(nxt[0])
        )
        if hyphen_break:
            m = _WORD.match(nxt)
            suffix = m.group(0) if m else ""
            # «ка» исключено: оно в keep_hyphen_suffixes (частица «ну-ка»), но в
            # прозе разрыв «нау-ка»/«ру-ка» встречается несравнимо чаще — дефис
            # убираем. Остальные частицы (то/либо/нибудь/таки) сохраняют дефис.
            # Осознанное отклонение (см. deviations в плане M1).
            if suffix in cfg.clean.keep_hyphen_suffixes and suffix != "ка":
                out += nxt
            else:
                out = out[:-1] + nxt
        else:
            out += " " + nxt
    return out


def compile_patterns(cfg: Config) -> dict[int, list[re.Pattern]]:
    return {rank: [re.compile(p, re.IGNORECASE)
                   for p in cfg.chapters.patterns.get(f"rank{rank}", ())]
            for rank in (1, 2, 3)}


def line_rank(line: str, patterns: dict[int, list[re.Pattern]]) -> int | None:
    for rank in (1, 2, 3):
        if any(p.fullmatch(line) for p in patterns[rank]):
            return rank
    letters = [c for c in line if c.isalpha()]
    if letters and len(line) <= 60 and not any(c.islower() for c in letters):
        return 3
    return None


def apply_heading_patterns(paras: list[tuple[str, bool]], cfg: Config) -> list[Block]:
    patterns = compile_patterns(cfg)
    ranked: list[tuple[str, int | None]] = [
        (text, line_rank(text, patterns) if single else None)
        for text, single in paras
    ]
    present = sorted({r for _, r in ranked if r is not None})
    level_of = {r: i + 1 for i, r in enumerate(present)}
    return [
        Block(BlockKind.HEADING, text, level=level_of[r], origin=f"pattern:rank{r}")
        if r is not None else Block(BlockKind.PARA, text)
        for text, r in ranked
    ]


def apply_patterns_to_blocks(blocks: list[Block], cfg: Config) -> list[Block]:
    """§6.1.3 как общий fallback (§6.5 DOCX, §7.2 P5.5): PARA-блоки из одной
    строки прогоняются через паттерны; ранги сжимаются в уровни 1..k."""
    patterns = compile_patterns(cfg)
    ranks: dict[int, int] = {}
    for i, b in enumerate(blocks):
        if b.kind is BlockKind.PARA and "\n" not in b.text:
            r = line_rank(b.text, patterns)
            if r is not None:
                ranks[i] = r
    level_of = {r: k + 1 for k, r in enumerate(sorted(set(ranks.values())))}
    return [
        Block(BlockKind.HEADING, b.text, level=level_of[ranks[i]],
              origin=f"pattern:rank{ranks[i]}")
        if i in ranks else b
        for i, b in enumerate(blocks)
    ]
