from __future__ import annotations

import hashlib
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from librarian import PIPELINE_VERSION
from librarian.catalog import find_by_cache_key, find_by_sha256, read_book, rebuild_index
from librarian.config import Config, config_hash
from librarian.detect import detect
from librarian.emit import (emit_book, lang_heuristic, library_lock,
                            recover, render_chapter)
from librarian.errors import DetectError, LibError, LimitError
from librarian.extractors.base import get_extractor
from librarian.ir import BlockKind, BookMeta, DocContext, ReportDraft
from librarian.passes.normalize import apply_block_passes
from librarian.passes.sections import apply_section_passes
from librarian.quality import build_report, compute_metrics, score_and_status
from librarian.slug import make_id
from librarian.structure import (build_tree, choose_cut_level, cut_chapters,
                                 fallback_cut, normalize_heading_levels)
from librarian.tokens import count


@dataclass
class IngestOutcome:
    path: Path
    book_id: str | None
    status: str
    score: float | None
    message: str = ""
    traceback: str = ""        # полный трейс для --verbose (§16); пусто на успехе


def run_ingest(paths: list[Path], cfg: Config, lib_root: Path,
               force: bool = False) -> list[IngestOutcome]:
    lib_root.mkdir(parents=True, exist_ok=True)
    with library_lock(lib_root, cfg.general.lock_timeout_s):
        recover(lib_root)
        outcomes = [_safe_ingest(p, cfg, lib_root, force) for p in paths]
        rebuild_index(lib_root)                     # один раз на команду (С-7)
    return outcomes


def _safe_ingest(path: Path, cfg: Config, lib_root: Path, force: bool) -> IngestOutcome:
    try:
        return ingest_file(path, cfg, lib_root, force)
    except DetectError as e:
        return IngestOutcome(path, None, "skipped", None, str(e))
    except LibError as e:
        return IngestOutcome(path, None, "failed", None, str(e), traceback.format_exc())
    except Exception as e:                          # noqa: BLE001 — §16: пакет не падает
        return IngestOutcome(path, None, "failed", None,
                             f"{type(e).__name__}: {e}", traceback.format_exc())


def ingest_file(path: Path, cfg: Config, lib_root: Path,
                force: bool = False) -> IngestOutcome:
    size = path.stat().st_size                                           # 0 — лимит §6.0
    if size > cfg.limits.max_source_mb * 1024 * 1024:
        raise LimitError(f"{path.name}: файл {size // (1024 * 1024)} МБ "
                         f"больше лимита {cfg.limits.max_source_mb} МБ")
    fmt = detect(path)                                                   # 1
    sha = hashlib.sha256(path.read_bytes()).hexdigest()                  # 2
    chash = config_hash(cfg)
    cache_key = f"{sha}:{PIPELINE_VERSION}:{chash}"
    if not force:                                                        # 3
        existing = find_by_cache_key(lib_root, cache_key)
        if existing:
            return IngestOutcome(path, existing, "skipped", None, "уже в библиотеке")
    raw = get_extractor(fmt).extract(path, cfg)                          # 4
    ctx = DocContext(fmt, cfg, raw,
                     ReportDraft(unknown_tags=dict(raw.unknown_tags)))         # 5
    blocks = apply_block_passes(raw.blocks, ctx)                         # 6
    if any(b.kind is BlockKind.HEADING for b in blocks):                 # 7
        blocks = normalize_heading_levels(blocks)
        root = build_tree(blocks, cfg)
        level = choose_cut_level(root, cfg)
        chapters = cut_chapters(root, level, cfg)
    else:
        ctx.report.structure_fallback = True
        chapters = fallback_cut(blocks, raw.title or cfg.general.preface_title, cfg)
    chapters = apply_section_passes(chapters, ctx)                       # 8
    for ch in chapters:                                                  # 9 — финальные токены
        ch.tokens = count(render_chapter(ch))
    metrics = compute_metrics(chapters, ctx)                             # 10
    score, status, subscores, triggers = score_and_status(metrics, cfg)
    report = build_report(ctx, metrics, subscores, triggers, score, status, cfg)
    if status == "failed":                                               # 11
        print(f"{path.name}: failed (score {score}) — книга не сохранена",
              file=sys.stderr)
        return IngestOutcome(path, None, "failed", score, "score ниже порога")
    book_id = _resolve_identity(path, raw, sha, lib_root, cfg)           # 12
    title, author, lang, locked = (raw.title or path.stem), (raw.author or ""), raw.lang, False
    try:
        prev = read_book(lib_root, book_id)
    except LibError:
        prev = None
    if prev and prev.get("meta_locked"):                                 # С-2
        title, author, lang, locked = (prev["title"], prev["author"],
                                       prev["lang"], True)
    if lang is None:
        lang = lang_heuristic("\n".join(b.text for b in blocks))
    meta = BookMeta(id=book_id, title=title, author=author, lang=lang,
                    meta_locked=locked, source_path=path, fmt=fmt, sha256=sha,
                    config_hash=chash, cache_key=cache_key,
                    status=status, score=score, keep_source=cfg.keep_source)
    emit_book(meta, chapters, report, lib_root, cfg)                     # 13
    return IngestOutcome(path, book_id, status, score)                   # 15


def _resolve_identity(path: Path, raw, sha: str, lib_root: Path, cfg: Config) -> str:
    same = find_by_sha256(lib_root, sha)            # переингест того же файла (--force)
    if same:
        return same
    book_id = make_id(raw.title, raw.author, path.stem, cfg.slug.max_len)
    bj = lib_root / book_id / "book.json"
    if bj.is_file():                                # коллизия id с другим файлом (12.1)
        try:
            other = read_book(lib_root, book_id)
            if other.get("source", {}).get("sha256") != sha:
                return f"{book_id}-{sha[:6]}"
        except LibError:
            return f"{book_id}-{sha[:6]}"
    return book_id
