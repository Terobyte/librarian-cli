from __future__ import annotations

import dataclasses
import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from librarian.errors import LibError


@dataclass(frozen=True)
class GeneralCfg:
    preface_title: str = "Начало"
    notes_chapter_title: str = "Примечания"
    lock_timeout_s: int = 30


@dataclass(frozen=True)
class LimitsCfg:
    max_source_mb: int = 256
    zip_max_uncompressed_mb: int = 512
    zip_ratio_max: int = 100
    extract_timeout_s: int = 120


@dataclass(frozen=True)
class TokensCfg:
    encoding: str = "o200k_base"


def _default_patterns() -> dict[str, tuple[str, ...]]:
    tail = r"([.:—\-]\s*.{0,80})?$"
    return {
        "rank1": (r"^(том|книга|book|volume)\s+([0-9ivxlc]+|[а-яёa-z]+)" + tail,),
        "rank2": (r"^(часть|part|раздел)\s+([0-9ivxlc]+|[а-яёa-z]+)" + tail,),
        "rank3": (r"^(глава|chapter)\s+([0-9ivxlc]+|[а-яёa-z]+)" + tail,
                  r"^([0-9]{1,4}|[IVXLC]{1,7})\.?$"),
    }


@dataclass(frozen=True)
class ChaptersCfg:
    cut_level_start: int = 2
    deepen_median: int = 12000
    shallow_median: int = 500
    max_tokens: int = 8000
    part_target_tokens: int = 6000
    fallback_part_tokens: int = 6000
    tiny_tokens: int = 30
    patterns: dict[str, tuple[str, ...]] = field(default_factory=_default_patterns)


@dataclass(frozen=True)
class CleanCfg:
    meta_max_tokens: int = 150
    meta_markers: tuple[str, ...] = ("ISBN", "©", "Все права защищены",
                                     "All rights reserved", "Литагент")
    toc_numeric_line_ratio: float = 0.60
    toc_heading_dup_ratio: float = 0.80
    toc_max_tokens: int = 2000
    keep_hyphen_suffixes: tuple[str, ...] = ("то", "либо", "нибудь", "ка", "таки")


@dataclass(frozen=True)
class PdfCfg:
    scan_chars_per_page: int = 20
    size_round: float = 0.5
    hf_zone: float = 0.10
    hf_page_ratio: float = 0.30
    hf_min_pages: int = 5
    pagenum_max_chars: int = 4
    column_gap_ratio: float = 0.15
    column_min_share: float = 0.25
    multi_column_page_ratio: float = 0.10
    heading_size_ratio: float = 1.15
    heading_max_levels: int = 3
    heading_max_chars: int = 120
    bold_heading_max_chars: int = 60
    footnote_size_ratio: float = 0.85
    footnote_zone: float = 0.33
    footnotes: str = "keep"
    defect_char_ratio: float = 0.02


def _default_weights() -> dict[str, float]:
    return {"coverage": 0.30, "structure": 0.25, "garbage": 0.20,
            "encoding": 0.15, "dehyphen": 0.10}


@dataclass(frozen=True)
class QualityCfg:
    mojibake_markers: tuple[str, ...] = ("Ð", "Ñ", "Ã", "â€", "пїЅ")
    weights: dict[str, float] = field(default_factory=_default_weights)
    ok_min: float = 0.90
    failed_max: float = 0.60
    coverage_points: tuple[float, ...] = (0.40, 0.70, 1.02, 1.15)
    coverage_review: tuple[float, ...] = (0.60, 1.02)
    garbage: dict[str, float] = field(default_factory=lambda: {"full": 0.005, "zero": 0.05, "review": 0.02})
    encoding: dict[str, float] = field(default_factory=lambda: {"full": 0.0, "zero": 0.02, "review": 0.005})
    dehyphen: dict[str, float] = field(default_factory=lambda: {"full": 0.002, "zero": 0.03, "review": 0.01})


@dataclass(frozen=True)
class SlugCfg:
    max_len: int = 60
    chapter_len: int = 50


@dataclass(frozen=True)
class Config:
    general: GeneralCfg = field(default_factory=GeneralCfg)
    limits: LimitsCfg = field(default_factory=LimitsCfg)
    tokens: TokensCfg = field(default_factory=TokensCfg)
    chapters: ChaptersCfg = field(default_factory=ChaptersCfg)
    clean: CleanCfg = field(default_factory=CleanCfg)
    pdf: PdfCfg = field(default_factory=PdfCfg)
    quality: QualityCfg = field(default_factory=QualityCfg)
    slug: SlugCfg = field(default_factory=SlugCfg)
    keep_source: bool = True        # §13: --no-keep-source → False, входит в config_hash


_SECTIONS = {"general": GeneralCfg, "limits": LimitsCfg, "tokens": TokensCfg,
             "chapters": ChaptersCfg, "clean": CleanCfg, "pdf": PdfCfg,
             "quality": QualityCfg, "slug": SlugCfg}

# TOML §14 кладёт status/subscore-точки во вложенные таблицы — маппинг в плоские поля:
_QUALITY_TABLES = {"status": {"ok_min": "ok_min", "failed_max": "failed_max"},
                   "coverage": {"points": "coverage_points", "review": "coverage_review"}}


def load_config(path: Path | None = None, *, keep_source: bool = True) -> Config:
    overrides: dict = {}
    if path is not None:
        try:
            overrides = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LibError(f"конфиг не найден: {path}") from None
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise LibError(f"не удалось прочитать конфиг {path}: {e}") from None
    kwargs: dict = {"keep_source": keep_source}
    for name, cls in sorted(_SECTIONS.items()):
        section = dict(overrides.get(name, {}))
        if name == "quality":
            for table, mapping in _QUALITY_TABLES.items():
                for toml_key, attr in mapping.items():
                    if table in section and toml_key in section[table]:
                        section[attr] = section[table][toml_key]
                section.pop(table, None)
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(section) - known)
        if unknown:
            raise LibError(f"неизвестные ключи в [{name}]: {', '.join(unknown)}")
        # tuple-поля: TOML отдаёт list — приводим для frozen-каноничности
        for f in dataclasses.fields(cls):
            if f.name in section and isinstance(section[f.name], list):
                section[f.name] = tuple(section[f.name])
            if f.name == "patterns" and f.name in section:
                section[f.name] = {k: tuple(v) for k, v in sorted(section[f.name].items())}
        kwargs[name] = cls(**section)
    return Config(**kwargs)


def config_hash(cfg: Config) -> str:
    payload = json.dumps(dataclasses.asdict(cfg), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
