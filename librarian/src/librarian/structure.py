from __future__ import annotations

from statistics import median

from librarian.config import Config
from librarian.ir import Block, BlockKind, Chapter, Section
from librarian.tokens import draft_count


def normalize_heading_levels(blocks: list[Block]) -> list[Block]:
    levels = sorted({b.level for b in blocks if b.kind is BlockKind.HEADING})
    remap = {lvl: i + 1 for i, lvl in enumerate(levels)}
    for b in blocks:
        if b.kind is BlockKind.HEADING:
            b.level = remap[b.level]
    return blocks


def build_tree(blocks: list[Block], cfg: Config) -> Section:
    root = Section(title="", level=0, blocks=[], children=[])
    stack = [root]
    for b in blocks:
        if b.kind is BlockKind.HEADING:
            while stack[-1].level >= b.level:
                stack.pop()
            sec = Section(title=b.text, level=b.level, blocks=[], children=[])
            stack[-1].children.append(sec)
            stack.append(sec)
        else:
            if stack[-1] is root:
                pre = Section(title=cfg.general.preface_title, level=1,
                              blocks=[], children=[])
                root.children.append(pre)
                stack.append(pre)
            stack[-1].blocks.append(b)
    return root


def _max_level(sec: Section) -> int:
    return max([sec.level] + [_max_level(c) for c in sec.children])


def _segments(root: Section, level: int) -> list[list[Block]]:
    out: list[list[Block]] = []

    def collect_deep(sec: Section, acc: list[Block]) -> None:
        acc.extend(sec.blocks)
        for c in sec.children:
            acc.append(Block(BlockKind.HEADING, c.title, level=c.level))
            collect_deep(c, acc)

    def walk(sec: Section) -> None:
        for c in sec.children:
            if c.level < level:
                if c.blocks:
                    out.append(list(c.blocks))
                walk(c)
            else:
                acc: list[Block] = []
                collect_deep(c, acc)
                out.append(acc)

    walk(root)
    return out


def choose_cut_level(root: Section, cfg: Config) -> int:
    top = _max_level(root)
    if top == 0:
        return cfg.chapters.cut_level_start
    L = min(cfg.chapters.cut_level_start, top)
    while True:
        segs = _segments(root, L) or [[]]
        med = median(draft_count(s) for s in segs)
        if med > cfg.chapters.deepen_median and L + 1 <= top and L < 4:
            L += 1
            continue
        break
    if L == cfg.chapters.cut_level_start and med < cfg.chapters.shallow_median and L > 1:
        L = 1
    return L


def cut_chapters(root: Section, level: int, cfg: Config) -> list[Chapter]:
    chapters: list[Chapter] = []

    def path_title(path: list[str]) -> str:
        dedup: list[str] = []
        for t in path:
            if not dedup or dedup[-1] != t:
                dedup.append(t)
        return " · ".join(dedup)

    def collect_deep(sec: Section, acc: list[Block]) -> None:
        acc.extend(sec.blocks)
        for c in sec.children:
            acc.append(Block(BlockKind.HEADING, c.title,
                             level=c.level - level, origin="inner"))
            collect_deep(c, acc)

    def walk(sec: Section, path: list[str]) -> None:
        for c in sec.children:
            p = path + [c.title]
            if c.level < level:
                if c.blocks:
                    chapters.append(Chapter(0, path_title(p), list(c.blocks)))
                walk(c, p)
            else:
                acc: list[Block] = []
                collect_deep(c, acc)
                chapters.append(Chapter(0, path_title(p), acc))

    walk(root, [])
    return chapters


def fallback_cut(blocks: list[Block], title: str, cfg: Config) -> list[Chapter]:
    parts: list[list[Block]] = []
    cur: list[Block] = []
    cur_tokens = 0
    for b in blocks:
        t = draft_count([b])
        if cur and cur_tokens + t > cfg.chapters.fallback_part_tokens:
            parts.append(cur)
            cur, cur_tokens = [], 0
        cur.append(b)
        cur_tokens += t
    if cur:
        parts.append(cur)
    k = len(parts)
    if k == 1:
        return [Chapter(0, title, parts[0])]
    return [Chapter(0, f"{title} ({i}/{k})", p, part=i)
            for i, p in enumerate(parts, 1)]
