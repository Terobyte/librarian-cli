import dataclasses
from librarian.config import Config, config_hash, load_config

def test_defaults_match_spec():
    cfg = Config()
    assert cfg.chapters.max_tokens == 8000
    assert cfg.chapters.tiny_tokens == 30
    assert cfg.clean.keep_hyphen_suffixes == ("то", "либо", "нибудь", "ка", "таки")
    assert cfg.general.preface_title == "Начало"
    assert cfg.quality.weights == {"coverage": 0.30, "structure": 0.25,
                                   "garbage": 0.20, "encoding": 0.15, "dehyphen": 0.10}
    assert cfg.keep_source is True

def test_toml_overlay(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[chapters]\nmax_tokens = 4000\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.chapters.max_tokens == 4000
    assert cfg.chapters.tiny_tokens == 30

def test_hash_stable_and_sensitive(tmp_path):
    h1, h2 = config_hash(Config()), config_hash(Config())
    assert h1 == h2 and len(h1) == 64
    assert config_hash(load_config(None, keep_source=False)) != h1
