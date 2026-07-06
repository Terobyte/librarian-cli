from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from librarian import PIPELINE_VERSION
from librarian.config import Config
from librarian.errors import LibError
from librarian.ir import Block, BlockKind, BookMeta, Chapter
from librarian.slug import slugify
from librarian.tokens import count as _tok_count

if os.name == "nt":
    import msvcrt
else:
    import fcntl

_PART_SUFFIX = re.compile(r"\s*\(\d+/\d+\)$")


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def chapter_filename(ch: Chapter, cfg: Config) -> str:
    title, suffix = ch.title, ""
    if ch.part is not None:
        title = _PART_SUFFIX.sub("", title)
        suffix = f"-p{ch.part}"
    return f"{ch.n:03d}-{slugify(title, cfg.slug.chapter_len)}{suffix}.md"


def _render_table(text: str) -> str:
    rows = [[c.replace("|", "\\|") for c in r.split("\t")] for r in text.split("\n")]
    width = len(rows[0])
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _render_code(text: str) -> str:
    runs = re.findall(r"`+", text)
    fence = "`" * max(3, max((len(r) for r in runs), default=0) + 1)
    return f"{fence}\n{text}\n{fence}"


def render_chapter(ch: Chapter) -> str:
    body: list[str] = [f"# {ch.title}"]
    footnotes: list[Block] = []
    items: list[str] = []

    def flush_items() -> None:
        if items:
            body.append("\n".join(items))
            items.clear()

    for b in ch.blocks:
        if b.kind is BlockKind.META:
            continue
        if b.kind is BlockKind.FOOTNOTE:
            footnotes.append(b)
            continue
        if b.kind is BlockKind.LIST_ITEM:
            items.append(f"- {b.text}")
            continue
        flush_items()
        if b.kind is BlockKind.HEADING:
            body.append(f"{'#' * min((b.level or 1) + 1, 6)} {b.text}")
        elif b.kind is BlockKind.QUOTE:
            body.append("\n".join(f"> {ln}" if ln else ">" for ln in b.text.split("\n")))
        elif b.kind is BlockKind.CODE:
            body.append(_render_code(b.text))
        elif b.kind is BlockKind.TABLE:
            body.append(_render_table(b.text))
        else:
            body.append(b.text)
    flush_items()
    if footnotes:
        body.append("---")
        body.extend(b.text for b in footnotes)
    text = "\n\n".join(body)
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))
    return unicodedata.normalize("NFC", text).rstrip("\n") + "\n"


def ingested_at() -> str:
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    try:
        ts = int(sde) if sde else int(time.time())
    except (TypeError, ValueError):                 # мусор в SOURCE_DATE_EPOCH не валит батч
        ts = int(time.time())
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def library_lock(lib_root: Path, timeout_s: float):
    lib_root.mkdir(parents=True, exist_ok=True)
    f = open(lib_root / ".lock", "a+b")
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                if os.name == "nt":
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LibError("библиотека занята другим процессом") from None
                time.sleep(0.1)
        yield
    finally:
        try:
            if os.name == "nt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


def recover(lib_root: Path) -> None:
    trash, staging = lib_root / ".trash", lib_root / ".staging"
    if trash.is_dir():
        for d in sorted(p for p in trash.iterdir() if p.is_dir()):
            target = lib_root / d.name
            if not target.exists():
                os.replace(d, target)
                print(f"восстановлена книга {d.name} после прерванной записи",
                      file=sys.stderr)
    if staging.exists():
        shutil.rmtree(staging)
    if trash.exists():
        shutil.rmtree(trash)


def publish(staging_dir: Path, lib_root: Path, book_id: str) -> Path:
    target = lib_root / book_id
    trash = lib_root / ".trash" / book_id
    if target.exists():
        trash.parent.mkdir(exist_ok=True)
        if trash.exists():
            shutil.rmtree(trash)
        os.replace(target, trash)
    os.replace(staging_dir, target)
    shutil.rmtree(lib_root / ".trash", ignore_errors=True)
    return target


def build_summary(ch: Chapter) -> str:
    base = ""
    for b in ch.blocks:
        if b.kind is BlockKind.PARA and _tok_count(b.text) >= 15:
            base = _cut_300(b.text)
            break
    if not base:
        first = next((b for b in ch.blocks if b.text.strip()), None)
        base = _cut_300(first.text) if first else ""
    subs = [b.text for b in ch.blocks if b.kind is BlockKind.HEADING][:8]
    if subs:
        base = (base + " — " if base else "") + " · ".join(subs)
    return base


def _cut_300(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= 300:
        return text
    cut = text[:300].rsplit(" ", 1)[0]
    return cut + "…"


def lang_heuristic(text: str) -> str | None:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    cyr = sum(1 for ch in letters if "а" <= ch.casefold() <= "я" or ch.casefold() == "ё")
    lat = sum(1 for ch in letters if ch.isascii())
    if cyr / len(letters) >= 0.5:
        return "ru"
    if lat / len(letters) >= 0.5:
        return "en"
    return None


def emit_book(meta: BookMeta, chapters: list[Chapter], report: dict,
              lib_root: Path, cfg: Config) -> Path:
    staging = lib_root / ".staging" / meta.id
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "chapters").mkdir(parents=True)
    entries = []
    for ch in chapters:
        fname = chapter_filename(ch, cfg)
        (staging / "chapters" / fname).write_text(render_chapter(ch),
                                                  encoding="utf-8", newline="\n")
        entries.append({"n": ch.n, "file": f"chapters/{fname}", "title": ch.title,
                        "tokens": ch.tokens, "summary": build_summary(ch)})
    book = {
        "id": meta.id, "title": meta.title, "author": meta.author, "lang": meta.lang,
        "meta_locked": meta.meta_locked,
        "source": {"file": meta.source_path.name, "format": meta.fmt.value,
                   "sha256": meta.sha256},
        "provenance": {"ingested_at": ingested_at(),
                       "pipeline_version": PIPELINE_VERSION,
                       "config_hash": meta.config_hash,
                       "cache_key": meta.cache_key},
        "quality": {"status": meta.status, "score": meta.score},
        "total_tokens": sum(ch.tokens for ch in chapters),
        "chapters": entries,
    }
    (staging / "book.json").write_text(canonical_json(book), encoding="utf-8", newline="\n")
    (staging / "report.json").write_text(canonical_json(report), encoding="utf-8", newline="\n")
    if meta.keep_source:
        (staging / "source").mkdir()
        shutil.copyfile(meta.source_path, staging / "source" / meta.source_path.name)
    out = publish(staging, lib_root, meta.id)
    staging_parent = lib_root / ".staging"
    if staging_parent.is_dir() and not any(staging_parent.iterdir()):
        staging_parent.rmdir()
    return out
