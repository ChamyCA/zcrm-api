import json

from conftest import SENTINELS
from plan_helpers import mock_zoho, plan_file
from zcrm import paths


def test_state_has_only_allowed_fields(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    run_cli("run", "demo1", p, "--approve-steps", "s2,s3")
    files = list(paths.runs_dir().glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert set(data) == {"version", "plan_sha256", "plan_path", "profile", "run_id", "started", "steps", "variables"}
    for entry in data["steps"].values():
        assert set(entry) <= {"status", "response_id", "ts"}
    assert data["variables"] == {"account_id": "111"}
    text = files[0].read_text()
    for s in SENTINELS:
        assert s not in text
    assert "Acme Demo" not in text and "Smith" not in text
