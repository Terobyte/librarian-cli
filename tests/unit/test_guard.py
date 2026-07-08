# tests/unit/test_guard.py
import pytest

import _guard_targets as tg
from librarian.errors import BrokenFileError, LimitError
from librarian.extractors.guard import run_with_timeout


def test_timeout_kills_child():
    with pytest.raises(LimitError, match="зависло"):
        run_with_timeout(tg.slow, (30.0,), timeout_s=1.0)


def test_fast_call_returns_value():
    assert run_with_timeout(tg.slow, (0.0,), timeout_s=15.0) == "done"


def test_child_exception_reraised():
    with pytest.raises(BrokenFileError, match="изнутри дочернего"):
        run_with_timeout(tg.boom, (), timeout_s=15.0)


def test_child_hard_crash_reported():
    # ребёнок умер, не написав в Pipe (segfault/OOM/os._exit) → внятная ошибка,
    # а не голый EOFError в отчёте
    with pytest.raises(LimitError, match="аварийно"):
        run_with_timeout(tg.die, (), timeout_s=15.0)


def test_zero_timeout_runs_inprocess():
    assert run_with_timeout(tg.slow, (0.0,), timeout_s=0) == "done"


def test_guarded_extract_end_to_end(tmp_path, monkeypatch):
    # реальный экстрактор в дочернем процессе — регистрация импортом.
    # Известное ограничение: pytest-socket (задача 4) не патчит socket в
    # spawn-ребёнке — этот тест выполняется вне сетевого периметра.
    monkeypatch.delenv("LIB_EXTRACT_INPROCESS", raising=False)
    from librarian.config import load_config
    from librarian.extractors.guard import guarded_extract
    from librarian.ir import Format
    f = tmp_path / "b.txt"
    f.write_text("Глава 1\n\nТекст главы про море и маяк.\n", encoding="utf-8")
    raw = guarded_extract(Format.TXT, f, load_config(None))
    assert raw.blocks and raw.fmt is Format.TXT
