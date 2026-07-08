import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.environ.get("RUN_INSTALL_TESTS"),
                    reason="медленный: включается RUN_INSTALL_TESTS=1 (CI и перед релизом)")
def test_wheel_smoke():
    script = Path(__file__).parent.parent / "scripts" / "smoke_wheel.sh"
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                       cwd=str(Path(__file__).parent.parent))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SMOKE OK" in r.stdout
