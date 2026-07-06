import json
from pathlib import Path
from librarian.config import Config, config_hash
from librarian.emit import build_summary, emit_book, lang_heuristic
from librarian.ir import Block, BlockKind, BookMeta, Chapter, Format

K = BlockKind
LONG_PARA = "Это первый содержательный абзац главы, в нём достаточно слов и токенов. " * 6

def test_summary_rules():
    ch = Chapter(1, "Глава", [Block(K.PARA, "коротко"), Block(K.PARA, LONG_PARA),
                              Block(K.HEADING, "Сцена I", level=1),
                              Block(K.HEADING, "Сцена II", level=1)])
    s = build_summary(ch)
    assert s.startswith("Это первый содержательный")
    assert "…" in s and " — Сцена I · Сцена II" in s
    assert len(s.split(" — ")[0]) <= 301

def test_summary_empty_chapter():
    assert build_summary(Chapter(1, "x", [])) == ""

def test_lang_heuristic():
    assert lang_heuristic("Сплошной русский текст про библиотеку") == "ru"
    assert lang_heuristic("Plain english text about libraries") == "en"
    assert lang_heuristic("12345 --- 67890") is None

def test_emit_book_layout(tmp_path):
    cfg = Config()
    src = tmp_path / "роман.txt"
    src.write_text("исходник", encoding="utf-8")
    meta = BookMeta(id="avtor-roman", title="Роман", author="Автор", lang="ru",
                    meta_locked=False, source_path=src, fmt=Format.TXT,
                    sha256="ab" * 32, config_hash=config_hash(cfg),
                    cache_key=f"{'ab'*32}:2.2:{config_hash(cfg)}",
                    status="ok", score=1.0, keep_source=True)
    chapters = [Chapter(1, "Глава 1", [Block(K.PARA, LONG_PARA)], tokens=120)]
    lib = tmp_path / "library"
    out = emit_book(meta, chapters, {"status": "ok"}, lib, cfg)
    book = json.loads((out / "book.json").read_text(encoding="utf-8"))
    assert book["id"] == "avtor-roman" and book["title"] == "Роман"
    assert book["total_tokens"] == 120
    assert book["chapters"][0]["file"] == "chapters/001-glava-1.md"
    assert book["provenance"]["cache_key"] == meta.cache_key
    assert (out / "chapters" / "001-glava-1.md").exists()
    assert (out / "source" / "роман.txt").read_text(encoding="utf-8") == "исходник"
    assert (out / "report.json").exists()
    assert not (lib / ".staging").exists()
