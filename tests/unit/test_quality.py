# tests/unit/test_quality.py
from librarian.config import load_config
from librarian.ir import (Block, BlockKind, Chapter, DocContext, Format,
                          RawDoc, ReportDraft)
from librarian.quality import (Metrics, build_report, compute_metrics,
                               score_and_status)
from librarian.tokens import count

CFG = load_config(None)


def _ctx(fmt=Format.TXT, ref_text="", pages=None, **report_kw):
    raw = RawDoc(fmt=fmt, blocks=[], title=None, author=None, lang=None,
                 ref_text=ref_text, pages=pages)
    return DocContext(fmt, CFG, raw, ReportDraft(**report_kw))


def _chapter(text, n=1):
    ch = Chapter(n, f"Глава {n}", [Block(BlockKind.PARA, text)])
    ch.tokens = count(f"# Глава {n}\n\n{text}\n")
    return ch


def _rendered(ch):
    return f"# {ch.title}\n\n{ch.blocks[0].text}\n"


BODY = ("Ровный длинный абзац основного текста, в котором достаточно слов, "
        "чтобы глава не была крошечной и метрики имели смысл. ") * 30


def test_coverage_subtracts_legit_removed():
    # §11.1: токены секций, удалённых R1/R2, вычитаются из знаменателя
    ch = _chapter(BODY)
    removed_text = "ISBN 5-1234. Все права защищены. " * 20
    ctx = _ctx(ref_text=BODY + "\n\n" + removed_text)
    ctx.report.removed["meta_sections"] = [
        {"title": "х", "tokens": count(removed_text), "text": removed_text}]
    m = compute_metrics([ch], ctx, [_rendered(ch)])
    assert 0.90 < m.coverage <= 1.05                    # без вычета было бы ~0.6


def test_garbage_counts_short_and_lone_numbers():
    ch = _chapter(BODY)
    junk = "# Глава 1\n\n" + BODY + "\n\nаб\n\n1234\n\n— \n"
    # «аб» (≤2), «1234» (одинокое число), «—» — легитимный短 не считается
    m = compute_metrics([ch], _ctx(ref_text=BODY), [junk])
    lines = [ln for ln in junk.split("\n") if ln.strip()]
    assert m.garbage_ratio == 2 / len(lines)


def test_encoding_counts_fffd_mojibake_and_controls():
    ch = _chapter(BODY)
    bad = "# Глава 1\n\n" + BODY + "��" + "â€" + "\n"
    ctx = _ctx(ref_text=BODY, control_chars=3)
    m = compute_metrics([ch], ctx, [bad])
    assert m.encoding_score == (2 + 1 + 3) / len(bad)


def test_dehyphen_only_for_merge_formats():
    ch = _chapter(BODY)
    hy = "# Глава 1\n\nстрока с пере-\nносом\n" + BODY + "\n"
    m_txt = compute_metrics([ch], _ctx(fmt=Format.TXT, ref_text=BODY), [hy])
    m_fb2 = compute_metrics([ch], _ctx(fmt=Format.FB2, ref_text=BODY), [hy])
    assert m_txt.dehyphen_residue > 0 and m_fb2.dehyphen_residue == 0


def test_layout_flag_multicolumn_ratio():
    ch = _chapter(BODY)
    ctx = _ctx(fmt=Format.PDF, ref_text=BODY, pages=10,
               multi_column_pages=[1, 2])                # 20% > 10%
    m = compute_metrics([ch], ctx, [_rendered(ch)])
    assert m.layout_flag is True


def test_layout_flag_alone_forces_review():
    # С-11 изолированно: многоколоночность — жёсткий триггер review даже при
    # идеальных остальных метриках (golden kolonki3 сам по себе это не докажет)
    m = Metrics(coverage=1.0, garbage_ratio=0.0, encoding_score=0.0,
                structure=1.0, dehyphen_residue=0.0, median_tokens=5000,
                chapters_found=True, layout_flag=True)
    score, status, _, triggers = score_and_status(m, CFG)
    assert status == "review"
    assert any("колон" in t for t in triggers)


def test_subscores_piecewise_and_example_from_spec():
    # §11.6: coverage 0.55 → субоценка 0.5, score ≈ 0.85, триггер «< 0.60»
    m = Metrics(coverage=0.55, garbage_ratio=0.004, encoding_score=0.0002,
                structure=1.0, dehyphen_residue=0.001, median_tokens=5000,
                chapters_found=True, layout_flag=False)
    score, status, subs, triggers = score_and_status(m, CFG)
    assert subs["coverage"] == 0.5
    assert 0.84 < score < 0.87
    assert status == "review"
    assert any("coverage" in t and "< 0.60" in t for t in triggers)


def test_status_boundaries():
    def mk(cov, structure=1.0, chapters_found=True):
        return Metrics(coverage=cov, garbage_ratio=0.0, encoding_score=0.0,
                       structure=structure, dehyphen_residue=0.0, median_tokens=5000,
                       chapters_found=chapters_found, layout_flag=False)
    assert score_and_status(mk(1.0), CFG)[1] == "ok"
    # провал одной coverage НЕ роняет в failed: 0.30·0 + 0.25 + 0.20 + 0.15 + 0.10 = 0.70
    assert score_and_status(mk(0.15), CFG)[1] == "review"
    # failed достижим только совокупно: 0.30·0 + 0.25·0.3 + 0.20 + 0.15 + 0.10 = 0.525 < 0.60
    assert score_and_status(mk(0.15, structure=0.3, chapters_found=False),
                            CFG)[1] == "failed"
    m_fallback = Metrics(coverage=1.0, garbage_ratio=0.0, encoding_score=0.0,
                         structure=0.3, dehyphen_residue=0.0, median_tokens=0,
                         chapters_found=False, layout_flag=False)
    score, status, _, triggers = score_and_status(m_fallback, CFG)
    assert round(score, 3) == 0.825 and status == "review"          # §8.5


def test_report_full_schema():
    ch = _chapter(BODY)
    ctx = _ctx(ref_text=BODY)
    m = compute_metrics([ch], ctx, [_rendered(ch)])
    score, status, subs, trig = score_and_status(m, CFG)
    rep = build_report(ctx, m, subs, trig, score, status, CFG)
    assert set(rep) == {"pipeline_version", "config_hash", "status", "score",
                        "metrics", "subscores", "hard_triggers", "pages_flagged",
                        "multi_column_pages", "oversize_blocks_split",
                        "unknown_tags", "removed", "warnings"}
    assert set(rep["metrics"]) == {"coverage", "garbage_ratio", "encoding_score",
                                   "structure", "dehyphen_residue"}
    assert rep["unknown_tags"] == {}                     # теперь безусловный ключ


def test_failed_by_score_prints_triggers_to_stderr(tmp_path, capsys):
    # раскладка: coverage 0.30 + structure 0.25·0.3 + encoding 0.15
    #            + garbage 0 (треть строк ≤2 симв.) + dehyphen 0 (треть строк
    #            с висячим дефисом) = 0.525 < 0.60 → failed
    from librarian.pipeline import run_ingest
    junk = tmp_path / "musor.txt"
    junk.write_text(
        ("Обычная спокойная строка про море и маяк, ровная и достаточно длинная.\n\n"
         "аб\n\n"
         "и снова про море, но эта строка обрывается на самом инте-\n\n") * 60,
        encoding="utf-8")
    out = run_ingest([junk], CFG, tmp_path / "lib")[0]
    assert out.status == "failed"
    assert out.score is not None and out.score < 0.60
    err = capsys.readouterr().err
    assert "garbage_ratio" in err and "не сохранена" in err
