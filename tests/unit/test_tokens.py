import pytest
from librarian import tokens
from librarian.errors import LibError
from librarian.ir import Block, BlockKind

def test_count_basic():
    assert tokens.count("") == 0
    assert tokens.count("Война и мир") > 0
    assert tokens.count("a" * 1000) < 1000          # BPE сжимает

def test_draft_count_joins():
    blocks = [Block(BlockKind.PARA, "раз"), Block(BlockKind.PARA, "два")]
    assert tokens.draft_count(blocks) == tokens.count("раз\n\nдва")

def test_special_tokens_are_plain_text():
    assert tokens.count("<|endoftext|>") > 0

def test_corrupt_asset(monkeypatch):
    tokens._encoder.cache_clear()
    monkeypatch.setattr(tokens, "_read_asset", lambda: b"broken")
    with pytest.raises(LibError):
        tokens.count("x")
    tokens._encoder.cache_clear()
