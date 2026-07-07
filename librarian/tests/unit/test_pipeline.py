import dataclasses
import json
from librarian.config import Config, LimitsCfg, load_config
from librarian.pipeline import run_ingest

BOOK = """Глава 1

Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.
Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.
Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.
Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.
Первый абзац достаточно длинный, чтобы глава не была крошечной по правилу R3.
Продолжение первого абзаца, ещё десяток слов для веса и объёма текста.

Глава 2

Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога.
Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога.
Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога.
Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога.
Второй абзац тоже вполне достаточной длины для полноценной главы книги.
И ещё одно предложение, чтобы черновой счёт токенов был заметно больше порога."""

def _write(tmp_path, name="роман.txt", text=BOOK):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p

def test_ingest_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    out = run_ingest([_write(tmp_path)], Config(), lib)
    assert [o.status for o in out] == ["ok"]
    bid = out[0].book_id
    book = json.loads((lib / bid / "book.json").read_text(encoding="utf-8"))
    assert len(book["chapters"]) == 2
    assert book["lang"] == "ru"
    assert book["provenance"]["ingested_at"] == "1970-01-01T00:00:00Z"
    idx = json.loads((lib / "index.json").read_text(encoding="utf-8"))
    assert idx["books"][0]["id"] == bid

def test_ingest_cache_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    src = _write(tmp_path)
    run_ingest([src], Config(), lib)
    out2 = run_ingest([src], Config(), lib)
    assert out2[0].status == "skipped"

def test_force_reuses_id_k1(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    src = _write(tmp_path)
    id1 = run_ingest([src], Config(), lib)[0].book_id
    id2 = run_ingest([src], Config(), lib, force=True)[0].book_id
    assert id1 == id2

def test_meta_locked_survives_force(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    lib = tmp_path / "library"
    src = _write(tmp_path)
    bid = run_ingest([src], Config(), lib)[0].book_id
    bj = lib / bid / "book.json"
    data = json.loads(bj.read_text(encoding="utf-8"))
    data["title"], data["meta_locked"] = "Ручное имя", True
    bj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run_ingest([src], Config(), lib, force=True)
    after = json.loads(bj.read_text(encoding="utf-8"))
    assert after["title"] == "Ручное имя" and after["meta_locked"] is True

def test_broken_file_does_not_kill_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    bad = tmp_path / "bad.dat"; bad.write_bytes(bytes(range(256)) * 4)
    good = _write(tmp_path)
    out = run_ingest([bad, good], Config(), tmp_path / "library")
    assert out[0].status == "skipped" and "формат" in out[0].message
    assert out[1].status == "ok"

def test_fallback_review(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    p = _write(tmp_path, "плоский.txt", "Просто длинный текст без заголовков. " * 40)
    out = run_ingest([p], Config(), tmp_path / "library")
    assert out[0].status == "review"


def test_source_size_limit(tmp_path):
    src = tmp_path / "big.txt"
    src.write_text("Глава 1\n\nТекст главы про лимиты.\n", encoding="utf-8")
    cfg = dataclasses.replace(load_config(None), limits=LimitsCfg(max_source_mb=0))
    outcomes = run_ingest([src], cfg, tmp_path / "lib")
    assert outcomes[0].status == "failed"
    assert "больше лимита" in outcomes[0].message
    assert not (tmp_path / "lib" / "big").exists()


def test_extract_timeout_enforcement(monkeypatch, tmp_path):
    # BUG F-10: extract_timeout_s объявлен, но не применяется
    import time
    import pytest
    from librarian.ir import Format
    from librarian.extractors.base import EXTRACTORS
    from librarian.pipeline import ingest_file
    from librarian.config import load_config, LimitsCfg
    from librarian.errors import LibError
    import dataclasses

    orig_txt_extractor = EXTRACTORS[Format.TXT]

    class SlowExtractor:
        format = Format.TXT
        def extract(self, path, cfg):
            time.sleep(2.0)
            return orig_txt_extractor.extract(path, cfg)

    monkeypatch.setitem(EXTRACTORS, Format.TXT, SlowExtractor())

    cfg = load_config(None)
    cfg = dataclasses.replace(
        cfg,
        limits=LimitsCfg(
            max_source_mb=cfg.limits.max_source_mb,
            zip_max_uncompressed_mb=cfg.limits.zip_max_uncompressed_mb,
            zip_ratio_max=cfg.limits.zip_ratio_max,
            extract_timeout_s=1
        )
    )

    p = tmp_path / "note.txt"
    p.write_text("Глава 1\n\nНекоторый текст.", encoding="utf-8")

    with pytest.raises(LibError, match="извлечение зависло|timeout"):
        ingest_file(p, cfg, tmp_path / "lib")



def _lib_with_book(tmp_path, monkeypatch):
    from pathlib import Path
    from librarian.config import load_config
    from librarian.pipeline import run_ingest
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    fx = Path(__file__).parent.parent / "fixtures" / "txt" / "roman_cp1251.txt"
    out = run_ingest([fx], load_config(None), tmp_path)[0]
    return out.book_id


def test_reingest_noop_when_cache_key_matches(tmp_path, monkeypatch):
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    from conftest import tree_bytes
    bid = _lib_with_book(tmp_path, monkeypatch)
    before = tree_bytes(tmp_path)
    outcomes = run_reingest(load_config(None), tmp_path)
    assert [o.status for o in outcomes] == ["skipped"]
    assert tree_bytes(tmp_path) == before                     # ни байта не изменилось


def test_reingest_rebuilds_on_config_change_keeps_id(tmp_path, monkeypatch):
    import json
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    bj = tmp_path / bid / "book.json"
    hash_before = json.loads(bj.read_text(encoding="utf-8"))["provenance"]["config_hash"]
    cfg_toml = tmp_path / "cfg.toml"
    cfg_toml.write_text('[general]\npreface_title = "Пролог"\n', encoding="utf-8")
    cfg = load_config(cfg_toml)                               # другой config_hash
    outcomes = run_reingest(cfg, tmp_path)
    assert [o.status for o in outcomes] == ["ok"]
    assert outcomes[0].book_id == bid                         # К-1: id стабилен
    book = json.loads(bj.read_text(encoding="utf-8"))
    assert book["provenance"]["config_hash"] != hash_before   # новый cfg дошёл до provenance


def test_reingest_preserves_meta_locked(tmp_path, monkeypatch):
    # С-2: ручные правки title/author/lang переживают реингест
    import json
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    bj = tmp_path / bid / "book.json"
    book = json.loads(bj.read_text(encoding="utf-8"))
    book["title"], book["meta_locked"] = "Моё название", True
    bj.write_text(json.dumps(book, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")
    cfg_toml = tmp_path / "cfg.toml"
    cfg_toml.write_text('[general]\npreface_title = "Пролог"\n', encoding="utf-8")
    run_reingest(load_config(cfg_toml), tmp_path)
    after = json.loads(bj.read_text(encoding="utf-8"))
    assert after["title"] == "Моё название" and after["meta_locked"] is True


def test_reingest_skips_book_without_source(tmp_path, monkeypatch):
    import shutil
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    shutil.rmtree(tmp_path / bid / "source")
    outcomes = run_reingest(load_config(None), tmp_path)
    assert outcomes[0].status == "skipped"
    assert "исходник" in outcomes[0].message


def test_reingest_failed_book_keeps_id(tmp_path, monkeypatch):
    # К-1, путь (a) — исключение: порча байтов source меняет sha → кэш мимо,
    # detect() падает на PK-магии (BrokenFileError) → except-ветка _safe_ingest.
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    src = next((tmp_path / bid / "source").iterdir())
    src.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    outcomes = run_reingest(load_config(None), tmp_path)
    assert outcomes[0].status == "failed"
    assert outcomes[0].book_id == bid


def test_reingest_failed_by_score_keeps_id(tmp_path, monkeypatch):
    # К-1, путь (b) — failed по score, НЕ исключение: бьёт в ветку
    # `if status == "failed"` внутри ingest_file (она правится отдельно от
    # except-веток — оба пути обязаны сохранять id). Мусорный, но валидный
    # utf-8 текст: garbage- и dehyphen-субоценки 0, структуры нет → score
    # ≈ 0.525 < 0.60 (полный quality — M4).
    from librarian.config import load_config
    from librarian.pipeline import run_reingest
    bid = _lib_with_book(tmp_path, monkeypatch)
    src = next((tmp_path / bid / "source").iterdir())
    src.write_text(
        ("Обычная спокойная строка про море и маяк, ровная и достаточно длинная.\n\n"
         "аб\n\n"
         "и снова про море, но эта строка обрывается на самом инте-\n\n") * 60,
        encoding="utf-8")
    outcomes = run_reingest(load_config(None), tmp_path)
    assert outcomes[0].status == "failed"
    assert outcomes[0].score is not None and outcomes[0].score < 0.60
    assert outcomes[0].book_id == bid
