from plan_helpers import mock_zoho, plan_file, writes


def test_corp_profile_refused(zoho, add_profile, run_cli, tmp_path):
    add_profile(ptype="corp")
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path), "--dry-run")
    assert code == 4 and out["error"]["code"] == "profile_not_demo" and zoho.request_history == []


def test_insufficient_scopes(zoho, add_profile, run_cli, tmp_path):
    add_profile(scopes=["ZohoCRM.org.READ"])
    mock_zoho(zoho)
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path), "--dry-run")
    assert code == 7 and out["error"]["code"] == "scope_insufficient"
    assert {e["step"] for e in out["errors"]} >= {"s2", "s3"}
    assert writes(zoho) == []


def test_org_mismatch(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    text = open(plan_file(tmp_path)).read().replace("5725767000000012345", "999")
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path, text, "other.md"), "--dry-run")
    assert code == 7 and out["error"]["code"] == "plan_org_mismatch"
    assert "999" in out["error"]["message"] and "5725767000000012345" in out["error"]["message"]


def test_missing_org_id_and_parse_errors(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    text = open(plan_file(tmp_path)).read().replace('org_id: "5725767000000012345"', "title: x")
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path, text, "noorg.md"), "--dry-run")
    assert code == 7 and out["error"]["code"] == "plan_parse_error"
    assert any("org_id" in e["message"] for e in out["errors"])
    code, out, _ = run_cli("run", "demo1", str(tmp_path / "missing.md"), "--dry-run")
    assert code == 7 and out["error"]["code"] == "plan_parse_error"


def test_unknown_unapprovable_ids(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    assert run_cli("run", "demo1", p, "--approve-steps", "zz")[0] == 2
    assert run_cli("run", "demo1", p, "--approve-steps", "s1")[1]["error"]["code"] == "step_not_write"
    assert run_cli("run", "demo1", p, "--dry-run", "--approve-steps", "s2")[0] == 2
    assert run_cli("run", "demo1", p, "--only-reads", "--skip-step", "s2")[0] == 2
