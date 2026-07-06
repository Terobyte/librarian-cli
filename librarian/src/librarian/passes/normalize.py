from __future__ import annotations

import re
import unicodedata

from librarian.ir import Block, BlockKind, DocContext

_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"))
_MULTISPACE = re.compile(r"[ \t]+")
_MULTIBREAK = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")


def n1_unicode(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for b in blocks:
        t = unicodedata.normalize("NFC", b.text)
        t = t.translate(_INVISIBLE)
        b.text = t.replace("\r\n", "\n").replace("\r", "\n")
    return blocks
n1_unicode.name = "N1 unicode"


def n2_whitespace(blocks: list[Block], ctx: DocContext) -> list[Block]:
    out = []
    for b in blocks:
        if b.kind not in (BlockKind.CODE, BlockKind.TABLE):
            lines = [_MULTISPACE.sub(" ", ln).rstrip() for ln in b.text.split("\n")]
            b.text = _MULTIBREAK.sub("\n\n", "\n".join(lines)).strip("\n")
        if b.text.strip():
            out.append(b)
    return out
n2_whitespace.name = "N2 whitespace"


def n3_controls(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for b in blocks:
        cleaned, n = _CONTROL.subn("", b.text)
        ctx.report.control_chars += n
        b.text = cleaned
    return blocks
n3_controls.name = "N3 controls"


COMMON_PASSES = [n1_unicode, n2_whitespace, n3_controls]


def apply_block_passes(blocks: list[Block], ctx: DocContext) -> list[Block]:
    for p in COMMON_PASSES:
        blocks = p(blocks, ctx)
    return blocks
