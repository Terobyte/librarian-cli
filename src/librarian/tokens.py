from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from importlib import resources

import tiktoken

from librarian.errors import LibError
from librarian.ir import Block

_ASSET = "o200k_base.tiktoken"
_ASSET_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
_PAT_STR = "[^\\r\\n\\p{L}\\p{N}]?[\\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M}]*[\\p{Ll}\\p{Lm}\\p{Lo}\\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?|[^\\r\\n\\p{L}\\p{N}]?[\\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M}]+[\\p{Ll}\\p{Lm}\\p{Lo}\\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?|\\p{N}{1,3}| ?[^\\s\\p{L}\\p{N}]+[\\r\\n/]*|\\s*[\\r\\n]+|\\s+(?!\\S)|\\s+"
_SPECIAL_TOKENS = {'<|endoftext|>': 199999, '<|endofprompt|>': 200018}


def _read_asset() -> bytes:
    return resources.files("librarian.assets").joinpath(_ASSET).read_bytes()


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    data = _read_asset()
    if hashlib.sha256(data).hexdigest() != _ASSET_SHA256:
        raise LibError("повреждён словарь токенизатора")
    ranks = {
        base64.b64decode(tok): int(rank)
        for tok, rank in (line.split() for line in data.splitlines() if line)
    }
    return tiktoken.Encoding(name="o200k_base", pat_str=_PAT_STR,
                             mergeable_ranks=ranks, special_tokens=_SPECIAL_TOKENS)


def count(text: str) -> int:
    return len(_encoder().encode(text, disallowed_special=()))


def block_tokens(b: Block) -> int:
    return count(b.text)


def draft_count(blocks: list[Block]) -> int:
    return count("\n\n".join(b.text for b in blocks))
