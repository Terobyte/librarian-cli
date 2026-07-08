# src/librarian/quality.py
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from librarian import PIPELINE_VERSION
from librarian.config import Config, config_hash
from librarian.ir import Chapter, DocContext, Format
from librarian.tokens import count

_MEDIAN_LO, _MEDIAN_HI = 300, 20000
_OK_SHORT = {"—", "–", "*", "―"}                       # §11.2 garbage-исключения
_DEHYPHEN_FMTS = (Format.TXT, Format.MD, Format.PDF)   # §11.2 / М-минор


@dataclass
class Metrics:
    coverage: float
    garbage_ratio: float
    encoding_score: float
    structure: float
    dehyphen_residue: float
    median_tokens: float
    chapters_found: bool
    layout_flag: bool


def compute_metrics(chapters: list[Chapter], ctx: DocContext,
                    rendered: list[str]) -> Metrics:
    found = bool(chapters) and not ctx.report.structure_fallback
    med = float(median(c.tokens for c in chapters)) if chapters else 0.0
    structure = 0.3 if not found else (1.0 if _MEDIAN_LO <= med <= _MEDIAN_HI else 0.7)

    removed_tokens = sum(e.get("tokens", 0)                       # §11.1
                         for key in ("meta_sections", "toc")
                         for e in ctx.report.removed.get(key, []))
    denom = max(1, count(ctx.raw.ref_text) - removed_tokens)
    coverage = sum(ch.tokens for ch in chapters) / denom

    total_lines = garbage = residue = 0
    for text in rendered:
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            s = ln.strip()
            if not s:
                continue
            total_lines += 1
            if len(s) <= 2 and s not in _OK_SHORT:
                garbage += 1
            elif (s.isdigit() and len(s) <= 4
                    and (i == 0 or not lines[i - 1].strip())
                    and (i + 1 == len(lines) or not lines[i + 1].strip())):
                garbage += 1                                       # одинокое число
            r = ln.rstrip()
            if len(r) >= 2 and r.endswith("-") and r[-2].isalpha():
                residue += 1
    garbage_ratio = garbage / total_lines if total_lines else 0.0
    dehyphen = (residue / total_lines
                if ctx.fmt in _DEHYPHEN_FMTS and total_lines else 0.0)

    total_chars = sum(len(t) for t in rendered)
    bad = sum(t.count("�") for t in rendered) + ctx.report.control_chars
    for marker in ctx.cfg.quality.mojibake_markers:
        bad += sum(t.count(marker) for t in rendered)
    encoding = bad / total_chars if total_chars else 0.0

    pages = ctx.raw.pages or 0
    layout_flag = (pages > 0 and len(ctx.report.multi_column_pages)
                   > ctx.cfg.pdf.multi_column_page_ratio * pages)
    return Metrics(coverage, garbage_ratio, encoding, structure, dehyphen,
                   med, found, layout_flag)


def _down(x: float, full: float, zero: float) -> float:
    """1 при x ≤ full, 0 при x ≥ zero, между — линейно (§11.3)."""
    if x <= full:
        return 1.0
    if x >= zero:
        return 0.0
    return (zero - x) / (zero - full)


def _coverage_sub(c: float, pts: tuple[float, ...]) -> float:
    z_lo, f_lo, f_hi, z_hi = pts
    if f_lo <= c <= f_hi:
        return 1.0
    if c <= z_lo or c >= z_hi:
        return 0.0
    if c < f_lo:
        return (c - z_lo) / (f_lo - z_lo)
    return (z_hi - c) / (z_hi - f_hi)


def score_and_status(m: Metrics, cfg: Config) -> tuple[float, str, dict, list[str]]:
    q = cfg.quality
    subscores = {
        "coverage": round(_coverage_sub(m.coverage, q.coverage_points), 4),
        "garbage": round(_down(m.garbage_ratio, q.garbage["full"], q.garbage["zero"]), 4),
        "encoding": round(_down(m.encoding_score, q.encoding["full"], q.encoding["zero"]), 4),
        "dehyphen": round(_down(m.dehyphen_residue, q.dehyphen["full"], q.dehyphen["zero"]), 4),
        "structure": m.structure,
    }
    score = round(sum(q.weights[k] * subscores[k] for k in sorted(subscores)), 4)
    triggers: list[str] = []                                       # §11.2, порядок фиксирован
    lo, hi = q.coverage_review
    if m.coverage < lo:
        triggers.append(f"coverage {m.coverage:.2f} < {lo:.2f}")
    elif m.coverage > hi:
        triggers.append(f"coverage {m.coverage:.2f} > {hi:.2f}")
    if m.garbage_ratio > q.garbage["review"]:
        triggers.append(f"garbage_ratio {m.garbage_ratio:.4f} > {q.garbage['review']}")
    if m.encoding_score > q.encoding["review"]:
        triggers.append(f"encoding_score {m.encoding_score:.4f} > {q.encoding['review']}")
    if not m.chapters_found:
        triggers.append("главы не найдены (fallback-раскрой)")
    if m.dehyphen_residue > q.dehyphen["review"]:
        triggers.append(f"dehyphen_residue {m.dehyphen_residue:.4f} > {q.dehyphen['review']}")
    if m.layout_flag:
        triggers.append("многоколоночная вёрстка (3+ колонки) на более чем 10% страниц")
    if score < q.failed_max:
        status = "failed"
    elif score < q.ok_min or triggers:
        status = "review"
    else:
        status = "ok"
    return score, status, subscores, triggers


def build_report(ctx: DocContext, m: Metrics, subscores: dict, triggers: list[str],
                 score: float, status: str, cfg: Config) -> dict:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "config_hash": config_hash(cfg),
        "status": status,
        "score": score,
        "metrics": {"coverage": round(m.coverage, 4),
                    "garbage_ratio": round(m.garbage_ratio, 4),
                    "encoding_score": round(m.encoding_score, 4),
                    "structure": m.structure,
                    "dehyphen_residue": round(m.dehyphen_residue, 4)},
        "subscores": subscores,
        "hard_triggers": triggers,
        "pages_flagged": ctx.report.pages_flagged,
        "multi_column_pages": ctx.report.multi_column_pages,
        "oversize_blocks_split": ctx.report.oversize_blocks_split,
        "unknown_tags": dict(sorted(ctx.report.unknown_tags.items())),
        "removed": ctx.report.removed,
        "warnings": ctx.report.warnings,
    }
