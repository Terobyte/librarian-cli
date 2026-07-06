from __future__ import annotations

import json
import re
import unicodedata

from librarian.config import Config
from librarian.ir import Block, BlockKind, Chapter
from librarian.slug import slugify

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
