from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from librarian import PIPELINE_VERSION
from librarian.config import Config, config_hash
from librarian.ir import Chapter, DocContext

_MEDIAN_LO, _MEDIAN_HI = 300, 20000


@dataclass
class Metrics:
    structure: float
    chapters_found: bool
    median_tokens: float


def compute_metrics(chapters: list[Chapter], ctx: DocContext) -> Metrics:
    found = bool(chapters) and not ctx.report.structure_fallback
    med = float(median(c.tokens for c in chapters)) if chapters else 0.0
    if not found:
        s = 0.3
    elif _MEDIAN_LO <= med <= _MEDIAN_HI:
        s = 1.0
    else:
        s = 0.7
    return Metrics(structure=s, chapters_found=found, median_tokens=med)


def score_and_status(m: Metrics, cfg: Config) -> tuple[float, str, dict, list[str]]:
    subscores = {"coverage": 1.0, "garbage": 1.0, "encoding": 1.0,
                 "dehyphen": 1.0, "structure": m.structure}
    w = cfg.quality.weights
    score = round(sum(w[k] * subscores[k] for k in sorted(subscores)), 4)
    triggers = [] if m.chapters_found else ["главы не найдены (fallback-раскрой)"]
    if score < cfg.quality.failed_max:
        status = "failed"
    elif score < cfg.quality.ok_min or triggers:
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
        "metrics": {"structure": m.structure, "median_tokens": m.median_tokens},
        "subscores": subscores,
        "hard_triggers": triggers,
        "oversize_blocks_split": ctx.report.oversize_blocks_split,
        "control_chars": ctx.report.control_chars,
        "removed": ctx.report.removed,
        "warnings": ctx.report.warnings,
    }
