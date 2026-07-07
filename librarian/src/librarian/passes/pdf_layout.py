# src/librarian/passes/pdf_layout.py
from __future__ import annotations

import math
import re
import unicodedata

from librarian.ir import Block, BlockKind, DocContext

_PAGENUM_FRAME = " \t\n—–-.()[]"
_ROMAN = re.compile(r"[ivxlcdm]+", re.IGNORECASE)
_DIGIT = re.compile(r"\d+")   # вся последовательность цифр → один '#' (отклонение 30)
_WS = re.compile(r"\s+")


def _page_rect(ctx: DocContext, page: int) -> tuple:
    return ctx.raw.page_rects[page - 1]


def _page_h(ctx: DocContext, page: int) -> float:
    r = _page_rect(ctx, page)
    return r[3] - r[1]


def _page_w(ctx: DocContext, page: int) -> float:
    r = _page_rect(ctx, page)
    return r[2] - r[0]


def _zone(b: Block, ctx: DocContext) -> str | None:
    """'top'/'bottom', если центр bbox в зоне колонтитула (§7.2), иначе None."""
    if b.page is None or b.bbox is None:
        return None
    h = _page_h(ctx, b.page)
    cy = (b.bbox[1] + b.bbox[3]) / 2
    if cy < ctx.cfg.pdf.hf_zone * h:
        return "top"
    if cy > (1 - ctx.cfg.pdf.hf_zone) * h:
        return "bottom"
    return None


def _body_size(blocks: list[Block]) -> float | None:
    """Размер тела B (§7.2 P5.1): максимум символов, при равенстве — меньший.
    Нужен уже P1 (guard крупного кегля) и позже P5/P7."""
    hist: dict[float, int] = {}
    for b in blocks:
        if b.kind is BlockKind.PARA and b.font_size is not None:
            hist[b.font_size] = hist.get(b.font_size, 0) + len(b.text)
    if not hist:
        return None
    return min(sorted(hist.items()), key=lambda kv: (-kv[1], kv[0]))[0]


def p1_page_numbers(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    B = _body_size(blocks)
    out: list[Block] = []
    removed = 0
    for b in blocks:
        core = b.text.strip(_PAGENUM_FRAME)
        big = (B is not None and b.font_size is not None            # отклонение 25:
               and b.font_size >= cfg.heading_size_ratio * B)       # крупный кегль — не номер
        if (b.kind is BlockKind.PARA and not big and _zone(b, ctx) is not None
                and core and len(core) <= cfg.pagenum_max_chars
                and (core.isdigit() or _ROMAN.fullmatch(core))):
            removed += 1
            continue
        out.append(b)
    if removed:
        ctx.report.removed["page_numbers"] = (
            ctx.report.removed.get("page_numbers", 0) + removed)
    return out
p1_page_numbers.name = "P1 page numbers"


def _signature(text: str) -> str:
    return _WS.sub(" ", _DIGIT.sub("#", text)).strip().casefold()


def p2_headers_footers(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    pages = ctx.raw.pages or 0
    threshold = max(cfg.hf_min_pages, math.ceil(cfg.hf_page_ratio * pages))
    keys: dict[int, tuple[str, str]] = {}
    sig_pages: dict[tuple[str, str], set[int]] = {}
    for i, b in enumerate(blocks):
        z = _zone(b, ctx)
        if z is not None and b.page is not None:
            key = (z, _signature(b.text))
            keys[i] = key
            sig_pages.setdefault(key, set()).add(b.page)
    doomed = {k for k, ps in sig_pages.items() if len(ps) >= threshold}
    if doomed:
        ctx.report.removed.setdefault("headers_footers", []).extend(
            {"signature": sig, "pages": sorted(sig_pages[(z, sig)])}
            for z, sig in sorted(doomed))
    return [b for i, b in enumerate(blocks) if keys.get(i) not in doomed]
p2_headers_footers.name = "P2 headers/footers"


def _yx(b: Block) -> tuple:
    return (b.bbox[1], b.bbox[0])


def _split_pages(blocks: list[Block]) -> list[tuple[int | None, list[Block]]]:
    groups: list[tuple[int | None, list[Block]]] = []
    for b in blocks:
        if not groups or groups[-1][0] != b.page:
            groups.append((b.page, []))
        groups[-1][1].append(b)
    return groups


def p3_reading_order(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    out: list[Block] = []
    for page, group in _split_pages(blocks):
        if page is None:
            out.extend(group)
            continue
        flags = [_zone(b, ctx) is None and b.bbox is not None for b in group]
        body = [b for b, f in zip(group, flags) if f]
        if len(body) >= 2:
            w = _page_w(ctx, page)
            xs = sorted((b.bbox[0] + b.bbox[2]) / 2 for b in body)
            cuts = [k for k in range(len(xs) - 1)
                    if xs[k + 1] - xs[k] >= cfg.column_gap_ratio * w
                    and (k + 1) >= cfg.column_min_share * len(body)
                    and (len(body) - k - 1) >= cfg.column_min_share * len(body)]
            if len(cuts) == 1:                                   # §7.2 P3.2
                split_x = (xs[cuts[0]] + xs[cuts[0] + 1]) / 2
                left = sorted((b for b in body
                               if (b.bbox[0] + b.bbox[2]) / 2 < split_x), key=_yx)
                right = sorted((b for b in body
                                if (b.bbox[0] + b.bbox[2]) / 2 >= split_x), key=_yx)
                it = iter(left + right)
                group = [next(it) if f else b for b, f in zip(group, flags)]
            elif len(cuts) >= 2:                                 # §7.2 P3.3 / С-11
                ctx.report.multi_column_pages.append(page)
        out.extend(group)
    return out
p3_reading_order.name = "P3 reading order"


def p4_defect_pages(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    stats: dict[int, list[int]] = {}                             # page → [bad, total]
    for b in blocks:
        if b.page is None:
            continue
        st = stats.setdefault(b.page, [0, 0])
        for ch in b.text:
            st[1] += 1
            if ch == "�" or (ch not in "\n\t"                       # Co = PUA: типичный
                                  and unicodedata.category(ch)      # битый шрифт-маппинг
                                  in ("Cc", "Cn", "Co")):
                st[0] += 1
    for page in sorted(stats):
        bad, total = stats[page]
        if total and bad / total > cfg.defect_char_ratio:
            ctx.report.pages_flagged.append(page)
            ctx.report.warnings.append(
                f"страница {page}: дефектный текстовый слой "
                f"({bad / total:.1%} нечитаемых символов)")
    return blocks
p4_defect_pages.name = "P4 defect pages"
