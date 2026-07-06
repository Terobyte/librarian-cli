import os
import subprocess
import sys
from pathlib import Path

from conftest import tree_bytes

ROOT = Path(__file__).parent


def _run(seed: str, lib: Path, fixture: Path) -> None:
    env = {**os.environ, "PYTHONHASHSEED": seed, "SOURCE_DATE_EPOCH": "0"}
    r = subprocess.run(
        [sys.executable, "-m", "librarian", "--library", str(lib),
         "ingest", str(fixture)],
        env=env, capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent))
    assert r.returncode == 0, r.stderr


def test_determinism_across_hashseeds(tmp_path):
    fixture = ROOT / "fixtures" / "txt" / "roman_cp1251.txt"
    lib_a, lib_b = tmp_path / "a", tmp_path / "b"
    _run("0", lib_a, fixture)
    _run("42", lib_b, fixture)
    ta, tb = tree_bytes(lib_a), tree_bytes(lib_b)
    assert sorted(ta) == sorted(tb)
    for rel in sorted(ta):
        assert ta[rel] == tb[rel], f"недетерминизм: {rel}"
