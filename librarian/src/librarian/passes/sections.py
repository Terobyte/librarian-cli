from __future__ import annotations

import re

from librarian.ir import Block, BlockKind, Chapter, DocContext
from librarian.tokens import block_tokens, draft_count

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _chapter_text(ch: Chapter) -> str:
    return "\n\n".join(b.text for b in ch.blocks)


def r1_meta_sections(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.clean
    markers = tuple(m.casefold() for m in cfg.meta_markers)
    kept: list[Chapter] = []
    removed: list[dict] = []
    for ch in chapters:
        text = _chapter_text(ch)
        low = text.casefold()
        if (draft_count(ch.blocks) < cfg.meta_max_tokens
                and any(m in low for m in markers)):
            removed.append({"title": ch.title,
                            "tokens": draft_count(ch.blocks), "text": text})
        else:
            kept.append(ch)
    if removed:
        ctx.report.removed.setdefault("meta_sections", []).extend(removed)
    return kept


_WS_RUN = re.compile(r"\s+")


def _canon(s: str) -> str:
    return _WS_RUN.sub(" ", s.casefold()).strip()


def r2_toc(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.clean
    headings = {_canon(b.text) for b in ctx.raw.blocks
                if b.kind is BlockKind.HEADING and b.text.strip()}
    kept: list[Chapter] = []
    removed: list[dict] = []
    for ch in chapters:
        tokens = draft_count(ch.blocks)
        lines = [ln for b in ch.blocks for ln in b.text.split("\n") if ln.strip()]
        if tokens > cfg.toc_max_tokens or not lines:
            kept.append(ch)
            continue
        others = headings - {_canon(ch.title)}          # заголовки ДРУГИХ глав
        numeric = sum(1 for ln in lines if ln.rstrip()[-1:].isdigit())
        dup = sum(1 for ln in lines if _canon(ln) in others)
        if (numeric / len(lines) > cfg.toc_numeric_line_ratio
                or dup / len(lines) >= cfg.toc_heading_dup_ratio):
            removed.append({"title": ch.title, "tokens": tokens,
                            "text": _chapter_text(ch)})
        else:
            kept.append(ch)
    if removed:
        ctx.report.removed.setdefault("toc", []).extend(removed)
    return kept


def r3_merge_tiny(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    tiny = ctx.cfg.chapters.tiny_tokens
    chs = list(chapters)
    i = 0
    while i < len(chs):
        ch = chs[i]
        if len(chs) > 1 and draft_count(ch.blocks) < tiny:
            demoted = [Block(BlockKind.HEADING, ch.title, level=1, origin="r3")] + ch.blocks
            if i + 1 < len(chs):
                chs[i + 1].blocks = demoted + chs[i + 1].blocks
            else:
                chs[i - 1].blocks = chs[i - 1].blocks + demoted
            del chs[i]
        else:
            i += 1
    return chs


def r4_split_giants(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.chapters
    out = []
    for ch in chapters:
        if draft_count(ch.blocks) <= cfg.max_tokens:
            out.append(ch)
            continue
        pieces = _split_by_headings(ch, cfg.max_tokens) or [ch]
        for p in pieces:
            if draft_count(p.blocks) > cfg.max_tokens:
                out.extend(_mechanical_split(p, ctx))
            else:
                out.append(p)
    return out


def _split_by_headings(ch: Chapter, max_tokens: int) -> list[Chapter] | None:
    depths = sorted({b.level for b in ch.blocks if b.kind is BlockKind.HEADING})
    if not depths:
        return None
    pieces: list[Chapter] = []
    for k in depths:
        pieces = _cut_at(ch, k)
        if all(draft_count(p.blocks) <= max_tokens for p in pieces):
            return pieces
    return pieces


def _cut_at(ch: Chapter, k: int) -> list[Chapter]:
    pieces: list[Chapter] = []
    cur_title = ch.title
    cur: list[Block] = []
    for b in ch.blocks:
        if b.kind is BlockKind.HEADING and b.level is not None and b.level <= k:
            if cur:
                pieces.append(Chapter(0, cur_title, cur))
            cur_title, cur = f"{ch.title} · {b.text}", []
        else:
            nb = b
            if b.kind is BlockKind.HEADING and b.level is not None:
                nb = Block(b.kind, b.text, level=b.level - k, origin=b.origin)
            cur.append(nb)
    if cur:
        pieces.append(Chapter(0, cur_title, cur))
    return pieces


def _mechanical_split(ch: Chapter, ctx: DocContext) -> list[Chapter]:
    cfg = ctx.cfg.chapters
    blocks: list[Block] = []
    for b in ch.blocks:
        if block_tokens(b) > cfg.max_tokens and b.kind in (
                BlockKind.PARA, BlockKind.QUOTE, BlockKind.CODE, BlockKind.TABLE):
            blocks.extend(_force_split(b, cfg.part_target_tokens))
            ctx.report.oversize_blocks_split += 1
        else:
            blocks.append(b)
    parts: list[list[Block]] = []
    cur: list[Block] = []
    cur_tokens = 0
    for b in blocks:
        t = block_tokens(b)
        if cur and cur_tokens + t > cfg.part_target_tokens:
            parts.append(cur)
            cur, cur_tokens = [], 0
        cur.append(b)
        cur_tokens += t
    if cur:
        parts.append(cur)
    k = len(parts)
    if k == 1:
        return [Chapter(0, ch.title, parts[0])]
    return [Chapter(0, f"{ch.title} ({i}/{k})", p, part=i)
            for i, p in enumerate(parts, 1)]


def _force_split(b: Block, target: int) -> list[Block]:
    if b.kind in (BlockKind.CODE, BlockKind.TABLE):
        units = b.text.split("\n")
        glue = "\n"
    else:
        units = _SENT_SPLIT.split(b.text)
        glue = " "
    out: list[Block] = []
    cur: list[str] = []
    cur_tokens = 0
    from librarian.tokens import count
    for u in units:
        t = count(u)
        if cur and cur_tokens + t > target:
            out.append(Block(b.kind, glue.join(cur), origin=b.origin))
            cur, cur_tokens = [], 0
        cur.append(u)
        cur_tokens += t
    if cur:
        out.append(Block(b.kind, glue.join(cur), origin=b.origin))
    return out


def r5_drop_empty(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    return [c for c in chapters if c.blocks]


def renumber(chapters: list[Chapter]) -> list[Chapter]:
    for i, c in enumerate(chapters, 1):
        c.n = i
    return chapters


SECTION_PASSES = [r1_meta_sections, r2_toc, r3_merge_tiny,
                  r4_split_giants, r5_drop_empty]


def apply_section_passes(chapters: list[Chapter], ctx: DocContext) -> list[Chapter]:
    for p in SECTION_PASSES:
        chapters = p(chapters, ctx)
    return renumber(chapters)
