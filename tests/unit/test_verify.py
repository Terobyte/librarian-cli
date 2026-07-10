from librarian.verify import (
    CLOSE,
    DISTORTED,
    STOP_EN,
    STOP_RU,
    find_window,
    normalize,
    passage,
    round_similarity,
    significant_tokens,
    verdict_for,
    word_diff,
)


# --- нормализация: типографика/пунктуация не в счёт ------------------------

def test_quotes_and_punctuation_ignored():
    assert normalize('«Рукописи не горят»').canon == normalize('Рукописи не горят.').canon


def test_yo_folds_to_e():
    assert normalize("шёл").canon == normalize("шел").canon == "шел"


def test_em_and_en_dash_are_separators():
    assert normalize("Рукописи — не горят").canon == normalize("Рукописи не горят").canon
    assert normalize("Рукописи – не горят").canon == normalize("Рукописи не горят").canon


def test_non_breaking_and_minus_hyphen_normalize_inside_word():
    assert normalize("кто‑то").tokens == ["кто-то"]      # ‑ non-breaking hyphen
    assert normalize("A−B").tokens == ["a-b"]              # − minus sign


def test_nbsp_and_narrow_nbsp_are_separators():
    plain = normalize("Рукописи не горят").canon
    assert normalize("Рукописи не горят").canon == plain
    assert normalize("Рукописи не горят").canon == plain


def test_ligature_nfkc_fold():
    assert normalize("ﬁle").tokens == ["file"]             # ﬁle → file


def test_apostrophe_variants_equal():
    straight = normalize("don't").canon
    assert normalize("don’t").canon == straight            # ’
    assert normalize("don‘t").canon == straight            # ‘
    assert normalize("don′t").canon == straight            # ′


# --- markdown-обвязка --------------------------------------------------------

def test_headers_h1_to_h6_all_dropped():
    for level in range(1, 7):
        n = normalize(f"{'#' * level} Heading {level}\n\nBody text stays.")
        assert n.canon == "body text stays"


def test_seven_hashes_not_treated_as_heading():
    n = normalize("####### seven hashes\n\nBody stays.")
    assert n.canon == "seven hashes body stays"


def test_hr_line_dropped():
    assert normalize("Body one.\n\n---\n\nBody two.").canon == "body one body two"


def test_blockquote_marker_stripped_repeatedly():
    assert normalize("> > Quoted line.").canon == "quoted line"


def test_list_marker_stripped():
    assert normalize("- item one").canon == "item one"


def test_numbered_marker_stripped():
    assert normalize("12. item two").canon == "item two"


def test_footnote_marker_dropped():
    n = normalize("Кит[1].")
    assert n.canon == "кит"
    assert "1" not in n.tokens


def test_bracketed_number_without_brackets_is_kept():
    n = normalize("В 1 главе.")                                 # не сноска — нет [ ]
    assert "1" in n.tokens


# --- карта смещений (спаны, сегменты) ---------------------------------------

def test_spans_point_back_to_original_text():
    text = "Рукописи не горят."
    n = normalize(text)
    assert [text[s:e] for s, e in n.spans] == ["Рукописи", "не", "горят"]


def test_spans_shift_after_marker_stripped():
    text = "> Quoted words here"
    n = normalize(text)
    assert n.spans[0] == (2, 8)
    assert text[n.spans[0][0]:n.spans[0][1]] == "Quoted"


def test_segments_increment_on_dropped_lines_not_on_blank_lines():
    text = "Para one.\n\n# Heading\n\nPara two."
    n = normalize(text)
    assert n.tokens == ["para", "one", "para", "two"]
    assert n.segs == [0, 0, 1, 1]

    text2 = "Para one.\n\n\nPara two still same segment."
    assert len(set(normalize(text2).segs)) == 1


# --- пороги вердиктов и округление -------------------------------------------

def test_verdict_exact_by_string_equality():
    assert verdict_for(1.0, True) == "exact"


def test_verdict_close_threshold():
    assert verdict_for(CLOSE, False) == "close"
    assert verdict_for(round(CLOSE - 0.0001, 4), False) == "distorted"


def test_verdict_distorted_threshold():
    assert verdict_for(DISTORTED, False) == "distorted"
    assert verdict_for(round(DISTORTED - 0.0001, 4), False) == "not_found"


def test_round_similarity_four_digits():
    assert round_similarity(0.949999) == 0.95
    assert round_similarity(1 / 3) == 0.3333


# --- стоп-слова, состав и порог «5 значимых» --------------------------------

def test_stop_word_lists_composition():
    assert STOP_RU == frozenset(
        "а бы в вы да для до же за и из к как ли мы на не но о об он она они "
        "оно от по при с со так то ты у что это я".split())
    assert STOP_EN == frozenset(
        "a an and are as at be but by for from he i in is it no not of on or "
        "she so that the they this to was we were with you".split())


def test_significant_tokens_filters_stopwords():
    n = normalize("это был маятник и он качался")
    sig = significant_tokens(n.tokens)
    assert sig == ["был", "маятник", "качался"]


def test_significant_tokens_threshold_5():
    few = normalize("маятник и он качался")
    assert len(significant_tokens(few.tokens)) < 5

    enough = normalize("маятник качался медленно над старым прудом")
    assert len(significant_tokens(enough.tokens)) >= 5


# --- пустая цитата / пустая после нормализации -------------------------------

def test_normalize_empty_string():
    n = normalize("")
    assert n == normalize("")
    assert (n.canon, n.tokens, n.spans, n.segs) == ("", [], [], [])


def test_normalize_only_markup_is_empty():
    assert normalize("# Title\n\n---\n").canon == ""


def test_find_window_none_for_empty_quote():
    chapter = normalize("some content words here")
    assert find_window(chapter, normalize("")) is None


def test_find_window_none_for_empty_chapter():
    assert find_window(normalize(""), normalize("some words")) is None


# --- оконный матчер: tie-break, рефрен, hill-climb, «глава длиннее» ---------

def test_tie_break_picks_smaller_offset():
    quote = normalize("the quick fox")
    chapter = normalize("we saw the quick fox jump and later the quick fox ran away")
    w = find_window(chapter, quote)
    assert w.exact
    assert w.lo == 2 and w.hi == 5


def test_refrain_repeated_many_times_returns_single_earliest_window():
    phrase = "кит нырнул в холодное море"
    filler = "тут был другой текст без повторов"
    chapter = normalize(" ".join([phrase, filler, phrase, filler, phrase]))
    w = find_window(chapter, normalize(phrase))
    assert w.exact
    assert w.lo == 0


def test_hill_climb_refines_sampled_offset_to_exact_and_is_deterministic():
    quote_text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
    chapter_text = ("zz1 zz2 zz3 zz4 zz5 " + quote_text + " zz6 zz7 zz8")
    quote = normalize(quote_text)
    chapter = normalize(chapter_text)
    w1 = find_window(chapter, quote)
    w2 = find_window(chapter, quote)
    assert w1 == w2                     # детерминизм двух прогонов
    assert w1.exact
    assert w1.lo == 5 and w1.hi == 17
    assert w1.ratio == 1.0


def test_quote_longer_than_chapter_uses_whole_chapter_as_window():
    chapter = normalize("the quick brown fox jumps")
    quote = normalize("the quick brown fox jumps well today")   # 2 лишних токена
    w = find_window(chapter, quote)
    assert w is not None
    assert w.lo == 0 and w.hi == len(chapter.tokens)
    assert not w.exact                                          # длины не равны


# --- word-diff ----------------------------------------------------------------

def test_word_diff_single_word_replacement_yields_one_pair():
    source_text = "Рукописи не горят никогда"
    quote_text = "Рукописи не горят вообще"
    source = normalize(source_text)
    quote = normalize(quote_text)
    diff = word_diff(source_text, source.spans, source.tokens,
                     quote_text, quote.spans, quote.tokens)
    assert diff == [{"quoted": "вообще", "source": "никогда"}]


def test_word_diff_empty_for_identical_tokens():
    text = "Рукописи не горят"
    n = normalize(text)
    assert word_diff(text, n.spans, n.tokens, text, n.spans, n.tokens) == []


# --- passage: сегментные границы --------------------------------------------

def test_passage_excludes_heading_and_hr():
    text = ("# Chapter One\n\n"
            "First sentence here. Second sentence follows the match word here. "
            "Third one.\n\n"
            "---\n\n"
            "More text after separator.")
    norm = normalize(text)
    idx = norm.tokens.index("match")
    p = passage(text, norm, idx, idx + 1)
    assert "#" not in p
    assert "---" not in p
    assert "match" in p


def test_passage_is_verbatim_slice_of_original():
    text = "Рукописи не горят. Это все знают."
    norm = normalize(text)
    idx = norm.tokens.index("горят")
    p = passage(text, norm, idx, idx + 1)
    assert p in text                    # вербатим-срез оригинала, не канон
