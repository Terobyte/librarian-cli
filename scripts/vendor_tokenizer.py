"""Разовый скрипт: скачивает o200k_base через tiktoken и вшивает в пакет.
Запуск: uv run python scripts/vendor_tokenizer.py  (нужна сеть)."""
import base64
import hashlib
from pathlib import Path

import tiktoken

enc = tiktoken.get_encoding("o200k_base")
lines = b"".join(
    base64.b64encode(tok) + b" " + str(rank).encode() + b"\n"
    for tok, rank in sorted(enc._mergeable_ranks.items(), key=lambda kv: kv[1])
)
out = Path(__file__).parent.parent / "src" / "librarian" / "assets" / "o200k_base.tiktoken"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(lines)
print("sha256 =", hashlib.sha256(lines).hexdigest())
print("pat_str =", enc._pat_str)
print("special_tokens =", enc._special_tokens)
