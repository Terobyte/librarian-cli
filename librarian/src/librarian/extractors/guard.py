# src/librarian/extractors/guard.py
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

from librarian.config import Config
from librarian.errors import LimitError
from librarian.ir import Format, RawDoc


def _call(conn, target, args) -> None:
    try:
        conn.send((True, target(*args)))
    except BaseException as e:                      # noqa: BLE001 — переправляем родителю
        conn.send((False, e))
    finally:
        conn.close()


def run_with_timeout(target, args: tuple, timeout_s: float):
    """target(*args) в spawn-процессе; дольше timeout_s → kill + LimitError.
    timeout_s <= 0 — прямой вызов (guard выключен)."""
    if timeout_s <= 0:
        return target(*args)
    ctx = multiprocessing.get_context("spawn")      # одинаково на всех ОС
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_call, args=(child, target, args), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout_s):
            proc.kill()
            proc.join()
            raise LimitError(f"извлечение зависло (> {timeout_s:g} с)")
        try:
            ok, payload = parent.recv()
        except EOFError:                                # ребёнок умер молча:
            proc.join()                                 # segfault/OOM/os._exit
            raise LimitError(
                "извлечение аварийно завершилось (процесс умер без ответа)") from None
        proc.join()
        if ok:
            return payload
        raise payload
    finally:
        parent.close()


def _extract_entry(fmt_value: str, path_str: str, cfg: Config) -> RawDoc:
    import librarian.extractors                     # noqa: F401 — регистрация в дочернем
    from librarian.extractors.base import get_extractor
    return get_extractor(Format(fmt_value)).extract(Path(path_str), cfg)


def guarded_extract(fmt: Format, path: Path, cfg: Config) -> RawDoc:
    """Шаг 4 конвейера под лимитом §6.0. Операционный guard: на выходные
    байты не влияет; env LIB_EXTRACT_INPROCESS=1 — обход для тестов (откл. 22)."""
    if cfg.limits.extract_timeout_s <= 0 or os.environ.get("LIB_EXTRACT_INPROCESS"):
        from librarian.extractors.base import get_extractor
        return get_extractor(fmt).extract(path, cfg)
    try:
        return run_with_timeout(_extract_entry, (fmt.value, str(path), cfg),
                                cfg.limits.extract_timeout_s)
    except LimitError:
        raise LimitError(f"{path.name}: извлечение зависло "
                         f"(> {cfg.limits.extract_timeout_s} с)") from None
