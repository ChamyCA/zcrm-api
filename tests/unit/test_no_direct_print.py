import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "zcrm"


def test_only_output_module_writes_to_streams():
    pattern = re.compile(r"\bprint\(|sys\.stdout|sys\.stderr")
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "output.py":
            continue
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == []
