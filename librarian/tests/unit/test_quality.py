from librarian.config import Config
from librarian.ir import Chapter, DocContext, Format, RawDoc, ReportDraft
from librarian.quality import build_report, compute_metrics, score_and_status

def _ctx(fallback=False):
    r = ReportDraft(structure_fallback=fallback)
    return DocContext(Format.TXT, Config(),
                      RawDoc(Format.TXT, [], None, None, None, ""), r)

def _chapters(tokens_list):
    return [Chapter(i + 1, f"Гл {i+1}", [], tokens=t) for i, t in enumerate(tokens_list)]

def test_structure_ok():
    m = compute_metrics(_chapters([1000, 2000, 3000]), _ctx())
    assert m.structure == 1.0
    score, status, subs, triggers = score_and_status(m, Config())
    assert (score, status, triggers) == (1.0, "ok", [])

def test_structure_median_out_of_range():
    m = compute_metrics(_chapters([50, 60, 70]), _ctx())
    assert m.structure == 0.7
    score, status, _, triggers = score_and_status(m, Config())
    assert abs(score - 0.925) < 1e-9 and status == "ok" and triggers == []

def test_fallback_forces_review():
    m = compute_metrics(_chapters([5000]), _ctx(fallback=True))
    assert m.structure == 0.3
    score, status, _, triggers = score_and_status(m, Config())
    assert status == "review" and abs(score - 0.825) < 1e-9 and triggers

def test_report_schema():
    ctx = _ctx()
    m = compute_metrics(_chapters([1000]), ctx)
    score, status, subs, trig = score_and_status(m, Config())
    rep = build_report(ctx, m, subs, trig, score, status, Config())
    assert set(rep) >= {"pipeline_version", "config_hash", "status", "score",
                        "metrics", "subscores", "hard_triggers", "removed", "warnings"}
    assert rep["hard_triggers"] == trig
