# tests/unit/_guard_targets.py — мишени для test_guard (spawn пиклит по имени модуля).
# Резолвится в дочернем процессе потому, что pytest в дефолтном import-mode=prepend
# кладёт tests/unit в sys.path, а spawn наследует sys.path родителя; при переходе
# на --import-mode=importlib эта связка сломается (ModuleNotFoundError в ребёнке).
import time

from librarian.errors import BrokenFileError


def slow(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


def boom() -> None:
    raise BrokenFileError("файл битый изнутри дочернего процесса")


def die() -> None:
    import os
    os._exit(1)          # жёсткая смерть без exception — модель segfault нативного парсера
