"""Ядро `lib verify` (docs/superpowers/specs/2026-07-08-librarian-verify-quote-design.md).

Чистые функции, без состояния, по образцу catalog.py: нормализация текста с картой
смещений, оконный матчер (префильтр/ratio/hill-climb), вердикты, word-diff, passage.
Доступ к библиотеке (verify_quote) — за пределами этого файла в T1.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from librarian.catalog import chapter_text, read_book
from librarian.search import chapter_candidates

# --- пороги (§3.3) ----------------------------------------------------------

CLOSE = 0.95
DISTORTED = 0.75
PREFILTER = 0.6

# --- стоп-слова (§3.4, состав дословно из спеки) ----------------------------

STOP_RU = frozenset(
    "а бы в вы да для до же за и из к как ли мы на не но о об он она они оно "
    "от по при с со так то ты у что это я".split())
STOP_EN = frozenset(
    "a an and are as at be but by for from he i in is it no not of on or she "
    "so that the they this to was we were with you".split())

# --- нормализация с картой смещений (§3.1) ----------------------------------

_HEADER_RE = re.compile(r"^#{1,6} ")
_QUOTE_MARKER_RE = re.compile(r"^> ")
_LIST_MARKER_RE = re.compile(r"^- ")
_NUM_MARKER_RE = re.compile(r"^\d+\. ")
_MARKERS = (_QUOTE_MARKER_RE, _LIST_MARKER_RE, _NUM_MARKER_RE)

# внутрисловные апострофы/тире (§3.1 п.5) — свёрнуты в канонические ' и -
_APOSTROPHES = "’‘′"          # ’ ‘ ′
# ‑ (non-breaking, U+2011) − (minus, U+2212); NFKC(U+2011) → U+2010 (HYPHEN) —
# канон-шаг идёт ПОСЛЕ NFKC (§3.1), поэтому пост-NFKC форма тоже в карте.
_HYPHENS = "‐‑−"
_TOKEN_EXTRA = set("'-" + _APOSTROPHES + _HYPHENS)

_SENT_BOUNDARY = re.compile(r"[.!?…](?=\s)")


@dataclass
class Norm:
    """Результат нормализации: канон-строка ↔ токены ↔ span'ы в ОРИГИНАЛЕ.

    segs — id сегмента на каждый токен: инкрементируется на каждой выброшенной
    структурной строке (заголовок `#…`, `---`); пустые строки сегмент не рвут.
    Используется passage() для запрета расширения через заголовки/разделители.
    """
    canon: str
    tokens: list[str]
    spans: list[tuple[int, int]]
    segs: list[int]


def _is_word_char(ch: str) -> bool:
    if ch in _TOKEN_EXTRA:
        return True
    return unicodedata.category(ch)[0] in ("L", "N")


def _strip_markers(line: str) -> int:
    """Снимает лидирующие `> `/`- `/`N. ` повторно (вложенные `> > `);
    возвращает сдвиг начала строки (число снятых символов)."""
    shift = 0
    while True:
        rest = line[shift:]
        for pat in _MARKERS:
            m = pat.match(rest)
            if m:
                shift += m.end()
                break
        else:
            return shift


def _tokenize_line(text: str, offset: int) -> list[tuple[int, int]]:
    """Максимальные прогоны словных символов в `text` → абсолютные (start,end)."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        if _is_word_char(text[i]):
            j = i + 1
            while j < n and _is_word_char(text[j]):
                j += 1
            spans.append((offset + i, offset + j))
            i = j
        else:
            i += 1
    return spans


def _is_footnote_marker(full_text: str, raw: str, s: int, e: int) -> bool:
    """Токен из одних цифр с соседями `[`/`]` в ОРИГИНАЛЕ — инлайн-сноска (§3.1 п.3)."""
    if not raw.isdigit():
        return False
    return s > 0 and full_text[s - 1] == "[" and e < len(full_text) and full_text[e] == "]"


def _canon_token(raw: str) -> str | None:
    """NFKC → casefold → ё→е → апострофы/тире → канон; без буквы/цифры — None."""
    t = unicodedata.normalize("NFKC", raw)
    t = t.casefold()
    t = t.replace("ё", "е")
    for ch in _APOSTROPHES:
        t = t.replace(ch, "'")
    for ch in _HYPHENS:
        t = t.replace(ch, "-")
    if not any(unicodedata.category(c)[0] in ("L", "N") for c in t):
        return None
    return t


def normalize(text: str) -> Norm:
    """Один построчный проход по ОРИГИНАЛЬНОМУ тексту: заголовки/`---` выброшены
    целиком (инкремент сегмента), маркеры `> `/`- `/`N. ` сняты сдвигом начала,
    токенизация по классам символов, канон — per-token NFKC (спаны не съезжают)."""
    tokens: list[str] = []
    spans: list[tuple[int, int]] = []
    segs: list[int] = []
    seg = 0
    pos = 0
    for line in text.split("\n"):
        line_start = pos
        pos += len(line) + 1                 # +1 за съеденный split() символ \n
        if _HEADER_RE.match(line) or line == "---":
            seg += 1
            continue
        shift = _strip_markers(line)
        content_start = line_start + shift
        for s, e in _tokenize_line(line[shift:], content_start):
            raw = text[s:e]
            if _is_footnote_marker(text, raw, s, e):
                continue
            canon = _canon_token(raw)
            if canon is None:
                continue
            tokens.append(canon)
            spans.append((s, e))
            segs.append(seg)
    return Norm(canon=" ".join(tokens), tokens=tokens, spans=spans, segs=segs)


def significant_tokens(tokens: list[str]) -> list[str]:
    """Значимые токены — канон-токены минус STOP_RU/STOP_EN (§3.4). Порог «<5» —
    забота вызывающего кода (verify_quote, T2); здесь только фильтр."""
    return [t for t in tokens if t not in STOP_RU and t not in STOP_EN]


# --- оконный матчер (§3.2) --------------------------------------------------

@dataclass
class Window:
    """Лучшее окно главы под цитату: [lo,hi) — токенные индексы главы, ratio —
    точный char-ratio (после hill-climb, если запускался), exact — совпадение
    канон-строк уточнённого окна и цитаты."""
    lo: int
    hi: int
    ratio: float
    exact: bool


def _hill_climb(chapter: Norm, quote_canon: str, lo: int, hi: int, L: int,
                n: int) -> tuple[int, int, float]:
    """Цикл расш-влево→расш-вправо→суж-влево→суж-вправо, шаг 1 токен; приём
    только при строгом росте char-ratio; стоп — круг без единого приёма;
    границы не дальше ±L токенов от сида (seed_lo, seed_hi)."""
    seed_lo, seed_hi = lo, hi

    def ratio_of(a: int, b: int) -> float:
        return SequenceMatcher(None, " ".join(chapter.tokens[a:b]), quote_canon,
                               autojunk=False).ratio()

    best = ratio_of(lo, hi)
    moves = (
        lambda l, h: (l - 1, h) if l > 0 else None,          # расширить влево
        lambda l, h: (l, h + 1) if h < n else None,           # расширить вправо
        lambda l, h: (l + 1, h) if h - l > 1 else None,       # сузить слева
        lambda l, h: (l, h - 1) if h - l > 1 else None,       # сузить справа
    )
    while True:
        accepted = False
        for move in moves:
            cand = move(lo, hi)
            if cand is None:
                continue
            cl, ch = cand
            if cl < seed_lo - L or ch > seed_hi + L:
                continue
            r = ratio_of(cl, ch)
            if r > best:
                lo, hi, best = cl, ch, r
                accepted = True
        if not accepted:
            return lo, hi, best


def find_window(chapter: Norm, quote: Norm) -> Window | None:
    """Скользящее окно шириной L=len(quote.tokens) по chapter.tokens, шаг
    max(1, L//4), последнее окно прижато к концу; quick_ratio-префильтр (≥
    PREFILTER) → точный ratio() → argmax (ничья — меньшее смещение, за счёт
    строгого `>` при обходе слева направо) → hill-climb при ratio ≥ DISTORTED.
    None — если глава/цитата пусты или ни одно окно не прошло префильтр."""
    n, L = len(chapter.tokens), len(quote.tokens)
    if n == 0 or L == 0:
        return None
    if L >= n:
        starts, width = [0], n
    else:
        step = max(1, L // 4)
        starts = list(range(0, n - L + 1, step))
        if starts[-1] != n - L:
            starts.append(n - L)
        width = L

    sm = SequenceMatcher(None, autojunk=False)
    sm.set_seq2(quote.canon)                  # b=цитата — кэши переживают set_seq1
    best_start, best_ratio = None, -1.0
    for s in starts:
        sm.set_seq1(" ".join(chapter.tokens[s:s + width]))
        if sm.quick_ratio() < PREFILTER:
            continue
        r = sm.ratio()
        if r > best_ratio:
            best_start, best_ratio = s, r
    if best_start is None:
        return None

    lo, hi = best_start, best_start + width
    if best_ratio >= DISTORTED:
        lo, hi, best_ratio = _hill_climb(chapter, quote.canon, lo, hi, L, n)
    exact = " ".join(chapter.tokens[lo:hi]) == quote.canon
    return Window(lo, hi, best_ratio, exact)


def round_similarity(ratio: float) -> float:
    """similarity = round(char_ratio, 4) — в ЯДРЕ, до dict (прецедент quality.py);
    вердикт/сортировка/вывод обязаны использовать одно и то же округлённое значение."""
    return round(ratio, 4)


def verdict_for(similarity: float, exact: bool) -> str:
    """§3.3. `similarity` — уже округлённое значение (round_similarity). exact —
    тест равенства канон-строк (не сравнение float), передаётся вызывающим кодом."""
    if exact:
        return "exact"
    if similarity >= CLOSE:
        return "close"
    if similarity >= DISTORTED:
        return "distorted"
    return "not_found"


# --- word-diff (§3.5) --------------------------------------------------------

def _join_spans(text: str, spans: list[tuple[int, int]]) -> str:
    return " ".join(text[s:e] for s, e in spans)


def word_diff(source_text: str, source_spans: list[tuple[int, int]],
             source_tokens: list[str], quote_text: str,
             quote_spans: list[tuple[int, int]], quote_tokens: list[str]) -> list[dict]:
    """opcodes SequenceMatcher(None, source_tokens, quote_tokens) по спискам
    токенов; каждая не-equal группа → {"quoted","source"} оригинальными словами
    через спаны, склейка одиночным пробелом. `source_*` — уже СРЕЗ окна совпадения
    (chapter.tokens[lo:hi] / chapter.spans[lo:hi]), не вся глава."""
    sm = SequenceMatcher(None, source_tokens, quote_tokens, autojunk=False)
    diff = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        diff.append({"quoted": _join_spans(quote_text, quote_spans[j1:j2]),
                    "source": _join_spans(source_text, source_spans[i1:i2])})
    return diff


# --- passage (§4.1) ----------------------------------------------------------

def _segment_bounds(text: str, pos: int) -> tuple[int, int]:
    """Границы (в символах text) непрерывного блока НЕ выброшенных строк,
    содержащего смещение pos: до/после ближайших заголовка/`---` (или краёв
    текста). Пустые строки внутрь блока входят (сегмент не рвут)."""
    lines = text.split("\n")
    offsets = []
    p = 0
    for ln in lines:
        offsets.append(p)
        p += len(ln) + 1

    idx = 0
    for i, off in enumerate(offsets):
        if off <= pos:
            idx = i
        else:
            break

    def dropped(i: int) -> bool:
        return bool(_HEADER_RE.match(lines[i])) or lines[i] == "---"

    lo_i = idx
    while lo_i > 0 and not dropped(lo_i - 1):
        lo_i -= 1
    hi_i = idx
    while hi_i < len(lines) - 1 and not dropped(hi_i + 1):
        hi_i += 1
    return offsets[lo_i], offsets[hi_i] + len(lines[hi_i])


def _clip_to_limit(text: str, start: int, stop: int, span_start: int, span_end: int,
                   limit: int) -> tuple[int, int, bool, bool]:
    """Обрезка [start,stop) до <=limit символов, приоритет — видимость окна
    совпадения [span_start,span_end); подравнивание к границе слова (пробелу)."""
    match_lo, match_hi = max(span_start, start), min(span_end, stop)
    match_len = max(match_hi - match_lo, 0)
    rest = max(limit - match_len, 0)
    left_budget = rest // 2
    right_budget = rest - left_budget
    new_start = max(start, match_lo - left_budget)
    new_end = min(stop, match_hi + right_budget)
    if new_end - new_start > limit:               # само совпадение длиннее лимита
        new_start, new_end = match_lo, min(stop, match_lo + limit)
    cut_left = new_start > start
    cut_right = new_end < stop
    if cut_left:
        sp = text.find(" ", new_start, stop)
        if sp != -1 and sp < new_end:
            new_start = sp + 1
    if cut_right:
        sp = text.rfind(" ", start, new_end)
        if sp != -1 and sp > new_start:
            new_end = sp
    return new_start, new_end, cut_left, cut_right


def passage(text: str, norm: Norm, lo: int, hi: int, *, limit: int = 400) -> str:
    """§4.1: от спана совпадения [lo,hi) — расширение до границ предложений
    (`[.!?…]` + пробел) ВНУТРИ сегмента первого совпавшего токена; совпадение,
    пересёкшее сегменты, — обрезается на границе сегмента; жёсткий лимит limit
    символов, обрезка по границе слова + маркер `[…]` на обрезанном крае.
    Возвращает вербатим-срез ОРИГИНАЛА (может содержать `\\n`)."""
    seg = norm.segs[lo]
    hi_eff = hi
    crossed = False
    for i in range(lo, hi):
        if norm.segs[i] != seg:
            hi_eff = i
            crossed = True
            break
    span_start = norm.spans[lo][0]
    span_end = norm.spans[hi_eff - 1][1]
    seg_start, seg_end = _segment_bounds(text, span_start)

    start = seg_start
    for m in _SENT_BOUNDARY.finditer(text, seg_start, span_start):
        start = m.end()
    # 9b (амендмент T2): _SENT_BOUNDARY — лукахед `(?=\s)`, не поглощает пробел;
    # start иначе указывает НА пробел ("\n\n"/" "), passage начинался бы с него.
    # Прогон пробельных ограничен span_start — он всегда символ слова (не пробел).
    while start < span_start and text[start].isspace():
        start += 1

    stop = seg_end
    m = _SENT_BOUNDARY.search(text, span_end, seg_end)
    if m:
        stop = m.end()

    # маркер […] — ТОЛЬКО реальная потеря контента: пересечение сегментов или
    # упор в лимит длины (ниже). Естественная остановка на границе предложения
    # или конце сегмента без урезания — не потеря, маркер не нужен.
    left_cut = False
    right_cut = crossed

    if stop - start > limit:
        start, stop, extra_l, extra_r = _clip_to_limit(text, start, stop, span_start,
                                                        span_end, limit)
        left_cut = left_cut or extra_l
        right_cut = right_cut or extra_r

    out = text[start:stop]
    if left_cut:
        out = "[…] " + out.lstrip()
    if right_cut:
        out = out.rstrip() + " […]"
    return out


# --- verify_quote: режим книги + режим полки (§3, §4.1, T2) ------------------

_EMPTY_QUOTE_MSG = "пустая цитата (или пустая после нормализации) — нечего проверять"
_SHORT_QUOTE_MSG = ("слишком короткая цитата для поиска по библиотеке — "
                    "укажи книгу через --book")
_NOT_FOUND_MSG = "цитата не найдена — совпадений выше порога нет"
_NOT_FOUND_SHELF_HINT = (" FTS5-кандидаты могли не покрыть сильно искажённую "
                         "цитату — попробуй --book.")


def _yo_variants(word: str) -> list[str]:
    """MAJOR-1/Plan v2 (отклонение 39): FTS5 unicode61 remove_diacritics не сворачивает
    ё→е для кириллицы, а канон-токен уже ё-сложен — без расширения shelf-поиск
    промахивается мимо дословной цитаты с е/ё-разницей. Варианты: сам токен, затем
    подстановка е→ё в каждой позиции слева направо, кап 8 вариантов/слово всего.
    chapter_candidates остаётся спека-чистым OR-match; расширение — забота verify."""
    variants = [word]
    for i, ch in enumerate(word):
        if len(variants) >= 8:
            break
        if ch == "е":
            variants.append(word[:i] + "ё" + word[i + 1:])
    return variants


def _null(message: str) -> dict:
    return {"verdict": None, "matches": [], "message": message}


def _match_entry(book: dict, book_id: str, ch: dict, text: str, norm: Norm,
                 window: Window, quote: str, quote_norm: Norm) -> tuple[float, bool, dict]:
    """similarity, exact, match-dict (§4.1, ключи и порядок — как в спеке) для окна
    попадания в одной главе."""
    similarity = round_similarity(window.ratio)
    diff = word_diff(text, norm.spans[window.lo:window.hi], norm.tokens[window.lo:window.hi],
                     quote, quote_norm.spans, quote_norm.tokens)
    entry = {
        "book_id": book_id,
        "book_title": book.get("title"),
        "author": book.get("author"),
        "n": ch["n"],
        "chapter_title": ch.get("title"),
        "similarity": similarity,
        "passage": passage(text, norm, window.lo, window.hi),
        "diff": diff,
    }
    return similarity, window.exact, entry


def _below_distorted(window: Window | None) -> bool:
    return window is None or (not window.exact and round_similarity(window.ratio) < DISTORTED)


def verify_quote(lib_root: Path, quote: str, *, book_id: str | None = None,
                 limit: int = 3) -> dict:
    """§3, §4.1: вердикт + локация + word-diff цитаты против library/. book_id задан —
    режим книги (полный скан, главы по n); иначе — режим полки (FTS5-кандидаты,
    chapter_candidates, топ-20). Ядро ВСЕГДА возвращает структуру: исключения —
    только LibError (неизвестный book_id, нет FTS5, занят индекс) и ValueError (limit<1)."""
    if limit < 1:
        raise ValueError(f"limit должен быть >= 1, получено {limit}")

    quote_norm = normalize(quote)
    if not quote_norm.tokens:
        return _null(_EMPTY_QUOTE_MSG)

    book_cache: dict[str, dict] = {}

    def get_book(bid: str) -> dict:
        if bid not in book_cache:
            book_cache[bid] = read_book(lib_root, bid)
        return book_cache[bid]

    ranked: list[tuple[float, bool, dict]] = []

    if book_id is not None:
        book = get_book(book_id)
        for ch in sorted(book.get("chapters", []), key=lambda c: c["n"]):
            text = chapter_text(lib_root, book_id, ch["file"])
            norm = normalize(text)
            window = find_window(norm, quote_norm)
            if _below_distorted(window):
                continue
            ranked.append(_match_entry(book, book_id, ch, text, norm, window,
                                       quote, quote_norm))
    else:
        significant = significant_tokens(quote_norm.tokens)
        if len(significant) < 5:
            return _null(_SHORT_QUOTE_MSG)
        words = [v for tok in significant for v in _yo_variants(tok)]
        for cbid, cn in chapter_candidates(lib_root, words, k=20):
            book = get_book(cbid)
            ch = next((c for c in book.get("chapters", []) if c["n"] == cn), None)
            if ch is None:
                continue
            text = chapter_text(lib_root, cbid, ch["file"])
            norm = normalize(text)
            window = find_window(norm, quote_norm)
            if _below_distorted(window):
                continue
            ranked.append(_match_entry(book, cbid, ch, text, norm, window,
                                       quote, quote_norm))

    ranked.sort(key=lambda c: (-c[0], c[2]["book_id"], c[2]["n"]))
    matches = [c[2] for c in ranked[:limit]]
    if not matches:
        msg = _NOT_FOUND_MSG + (_NOT_FOUND_SHELF_HINT if book_id is None else "")
        return {"verdict": "not_found", "matches": [], "message": msg}

    verdict = verdict_for(ranked[0][0], ranked[0][1])
    return {"verdict": verdict, "matches": matches, "message": None}
