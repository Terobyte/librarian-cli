# src/librarian/passes/pdf_layout.py
from __future__ import annotations

import math
import re
import unicodedata

from librarian.config import Config
from librarian.extractors.textrules import (apply_patterns_to_blocks,
                                            compile_patterns, line_rank,
                                            merge_lines)
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


_NO_MERGE_END = tuple(".!?…:;»\")")


def _nlines(b: Block) -> int:
    """Число строк блока до склейки — экстрактор кодирует его в origin="pdf:N"."""
    if b.origin.startswith("pdf:"):
        try:
            return int(b.origin.split(":", 1)[1])
        except ValueError:
            pass
    return b.text.count("\n") + 1


def _line_h(b: Block) -> float:
    return (b.bbox[3] - b.bbox[1]) / max(1, _nlines(b))


# _body_size уже в модуле — создан в задаче 2 (нужен P1); здесь только используется.


def _merge_split_headings(blocks: list[Block], cfg: Config) -> list[Block]:
    """§7.2 P5.6: два подряд HEADING одного уровня на одной странице
    с зазором по y < 1.5 высоты строки — один многострочный заголовок.
    Guard (отклонение 27): если ОБЕ строки сами по себе — полноценные
    заголовки по паттернам 6.1.3, это две РАЗНЫЕ короткие главы на одной
    странице, а не перенос — не сливать (иначе теряется граница главы)."""
    patterns = compile_patterns(cfg)
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (prev is not None and b.kind is BlockKind.HEADING
                and prev.kind is BlockKind.HEADING and prev.level == b.level
                and prev.page == b.page and prev.bbox and b.bbox
                and b.bbox[1] - prev.bbox[3] < _line_h(prev)    # откл. 31
                and not (line_rank(prev.text, patterns) is not None
                         and line_rank(b.text, patterns) is not None)):
            n = _nlines(prev) + _nlines(b)              # ДО перезаписи origin
            prev.text = f"{prev.text} {b.text}"
            prev.bbox = (min(prev.bbox[0], b.bbox[0]), prev.bbox[1],
                         max(prev.bbox[2], b.bbox[2]), b.bbox[3])
            prev.origin = f"pdf:{n}"                    # иначе _line_h деградирует каскадно
            b.kind, b.level = BlockKind.PARA, None      # не оставлять фантомный HEADING
            continue                                    # в ctx.raw.blocks (его читает r2_toc)
        out.append(b)
    return out


def p5_headings(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    B = _body_size(blocks)
    levels: dict[float, int] = {}
    if B is not None:
        counts: dict[float, int] = {}
        for b in blocks:
            if b.kind is BlockKind.PARA and b.font_size is not None:
                counts[b.font_size] = counts.get(b.font_size, 0) + 1
        sizes = sorted((s for s, n in sorted(counts.items())
                        if s >= cfg.heading_size_ratio * B and n >= 2), reverse=True)
        levels = {s: i + 1 for i, s in enumerate(sizes[:cfg.heading_max_levels])}
        for b in blocks:
            if b.kind is not BlockKind.PARA or b.font_size is None:  # откл. 31
                continue
            lvl = levels.get(b.font_size)
            if (lvl is not None and _nlines(b) <= 2
                    and len(b.text) <= cfg.heading_max_chars
                    and not b.text.rstrip().endswith((".", ","))):
                b.kind, b.level = BlockKind.HEADING, lvl
                # origin НЕ трогаем: "pdf:N" — единственный носитель числа строк,
                # он нужен _line_h в _merge_split_headings ниже
            elif (b.font_size == B and b.bold and _nlines(b) == 1
                    and len(b.text) <= cfg.bold_heading_max_chars
                    and not b.text.rstrip().endswith(".")):
                b.kind = BlockKind.HEADING
                b.level = min(len(levels) + 1, 4)
        blocks = _merge_split_headings(blocks, ctx.cfg)
    if not levels:                       # §7.2 P5.5 буквально: размерных уровней
        blocks = apply_patterns_to_blocks(blocks, ctx.cfg)   # не нашлось вовсе
    return blocks
p5_headings.name = "P5 headings"


def p6_cross_page(blocks: list[Block], ctx: DocContext) -> list[Block]:
    """Кандидат на склейку — последний PARA страницы и СЛЕДУЮЩИЙ ЗА НИМ блок
    порядка чтения (PARA более поздней страницы). Adjacency-правило переживает
    страницы без текста, не сшивает через заголовок и, с переносом page/bbox на
    хвост, домерджирует цепочки из 3+ страниц (отклонение 26).
    Guard (отклонение 28): P6 идёт ДО P7 (§7), поэтому сноска внизу страницы —
    ещё PARA и в sort-порядке стоит последней; без фильтра она срослась бы
    с телом следующей страницы (или утащила его в сноски). Кандидат,
    похожий на сноску геометрией и кеглем, пропускается — им займётся P7."""
    cfg = ctx.cfg.pdf
    out = list(blocks)
    B = _body_size(out)

    def _footnotish(b: Block) -> bool:
        return (B is not None and b.font_size is not None
                and b.font_size < cfg.footnote_size_ratio * B
                and b.page is not None and b.bbox is not None
                and b.bbox[1] >= (1 - cfg.footnote_zone) * _page_h(ctx, b.page))

    changed = True
    while changed:
        changed = False
        last_para: dict[int, int] = {}
        for idx, b in enumerate(out):
            if b.kind is BlockKind.PARA and b.page is not None:
                last_para[b.page] = idx
        for page in sorted(last_para):
            i = last_para[page]
            if _footnotish(out[i]):                      # откл. 28
                continue
            j = i + 1
            if j >= len(out):
                continue
            nb = out[j]
            if (nb.kind is not BlockKind.PARA or nb.page is None
                    or nb.page <= page):                 # не начало более поздней страницы
                continue
            tail = out[i].text.rstrip()
            head = nb.text.lstrip()
            if (tail and head and not tail.endswith(_NO_MERGE_END)
                    and (head[0].islower() or head[0] in "—–-")):
                out[i].text = merge_lines([out[i].text, nb.text], ctx.cfg)
                out[i].page = nb.page                    # хвост блока теперь на этой
                out[i].bbox = nb.bbox                    # странице — zone/B-логика P7
                del out[j]                               # смотрит на согласованную геометрию
                changed = True
                break                       # индексы поплыли — пересчитать карту
    return out
p6_cross_page.name = "P6 cross-page merge"


def p7_footnotes(blocks: list[Block], ctx: DocContext) -> list[Block]:
    cfg = ctx.cfg.pdf
    B = _body_size(blocks)
    if B is None:
        return blocks
    moved = 0
    for b in blocks:
        if (b.kind is BlockKind.PARA and b.font_size is not None
                and b.font_size < cfg.footnote_size_ratio * B
                and b.page is not None and b.bbox is not None
                and b.bbox[1] >= (1 - cfg.footnote_zone) * _page_h(ctx, b.page)
                and b.text[:1] and (b.text[0].isdigit() or b.text[0] == "*")):
            b.kind = BlockKind.FOOTNOTE
            moved += 1
    if not moved:
        return blocks
    if cfg.footnotes == "drop":
        ctx.report.removed["footnotes_dropped"] = (
            ctx.report.removed.get("footnotes_dropped", 0) + moved)
        return [b for b in blocks if b.kind is not BlockKind.FOOTNOTE]
    ctx.report.removed["footnotes_moved"] = (
        ctx.report.removed.get("footnotes_moved", 0) + moved)
    return blocks
p7_footnotes.name = "P7 footnotes"


PDF_PASSES = [p1_page_numbers, p2_headers_footers, p3_reading_order,
              p4_defect_pages, p5_headings, p6_cross_page, p7_footnotes]
