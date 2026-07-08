"""Регенерация golden-библиотек. Любой diff в git — осознанное решение ревью (§17)."""
import os
import shutil
from pathlib import Path

os.environ["SOURCE_DATE_EPOCH"] = "0"

from librarian.config import load_config          # noqa: E402
from librarian.pipeline import run_ingest         # noqa: E402

ROOT = Path(__file__).parent.parent
GOLDEN = ROOT / "tests" / "golden"
FIXTURES = sorted((ROOT / "tests" / "fixtures").rglob("*.*"))

for fx in FIXTURES:
    name = fx.stem
    out = GOLDEN / name
    if out.exists():
        shutil.rmtree(out)
    outcomes = run_ingest([fx], load_config(None), out)
    print(name, "->", [(o.status, o.book_id) for o in outcomes])
