import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_wheel_contains_skill_and_console_script(tmp_path):
    pytest.importorskip("hatchling")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "--no-build-isolation", "-w", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-500:]
    wheel = next(tmp_path.glob("zcrm_api-*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        assert "zcrm/skill/SKILL.md" in names and "zcrm/skill/reference.md" in names
        entry = next(n for n in names if n.endswith("entry_points.txt"))
        assert "zcrm = zcrm.cli:main" in zf.read(entry).decode()
        meta = zf.read(next(n for n in names if n.endswith("METADATA"))).decode()
        for dep in ("requests", "keyring", "pyyaml"):
            assert f"Requires-Dist: {dep}" in meta
