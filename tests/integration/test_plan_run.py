
from plan_helpers import URL, mock_zoho, ok, plan_file, request_json, writes
from zcrm import paths


def runs():
    return sorted(paths.runs_dir().glob("*.json"))


def test_no_approval_means_reads_only_and_pending_list(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path))
    assert code == 3 and out["error"]["code"] == "approval_required"
    assert [p["step"] for p in out["pending_writes"]] == ["s2", "s3", "s4"]
    assert out["pending_writes"][0]["url"] == f"{URL}/Accounts"
    assert out["discovery"]["modules"] == ["Leads"]
    assert writes(zoho) == []
    assert any(r.path == "/crm/v8/settings/modules" for r in zoho.request_history)


def test_only_approved_steps_run_and_capture_feeds_next(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s2")
    assert code == 0 and out["pending"] == ["s3", "s4"] and out["report"]["completed"] == ["s1", "s2"] and len(writes(zoho)) == 1
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s3")
    assert len(writes(zoho, "POST")) == 2
    body = request_json(writes(zoho, "POST")[-1])
    assert body["data"][0]["Account_Name"] == {"id": "111"}
    assert out["report"]["created_record_ids"] == [{"step": "s2", "id": "111"}, {"step": "s3", "id": "222"}]


def test_delete_never_batched_but_runs_alone(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s3,s4")
    assert code == 4 and out["error"]["code"] == "delete_not_batchable" and writes(zoho) == []
    assert run_cli("run", "demo1", p, "--approve-steps", "s2,s3")[0] in (0, 3)
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s4")
    assert code == 0 and len(writes(zoho, "DELETE")) == 1
    assert out["report"]["finished"] is True and out["report"]["failed"] == []


def test_failed_write_stops_with_options_then_retry_and_skip(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    zoho.post(f"{URL}/Contacts", status_code=400, json={"code": "INVALID_DATA", "message": "bad"})
    p = plan_file(tmp_path)
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s2,s3")
    assert code == 9 and out["stopped_at"] == "s3" and out["options"] == ["retry", "skip", "abort"]
    assert out["report"]["failed"] == ["s3"] and out["report"]["completed"] == ["s1", "s2"]
    # without a decision the next run stops again and sends nothing
    n = len(writes(zoho))
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s4")
    assert code == 9 and len(writes(zoho)) == n
    # retry after the problem is fixed
    zoho.post(f"{URL}/Contacts", json=ok("222"))
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s3")
    assert code == 0 and out["report"]["completed"] == ["s1", "s2", "s3"]
    # skip path
    zoho.post(f"{URL}/Contacts", status_code=400, json={"code": "X", "message": "bad"})
    code, out, _ = run_cli("run", "demo1", p, "--fresh", "--approve-steps", "s2,s3")
    assert code == 9
    code, out, _ = run_cli("run", "demo1", p, "--skip-step", "s3")
    assert out["report"]["skipped"] == ["s3"]


def test_embedded_record_error_fails_step(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    zoho.post(f"{URL}/Accounts", status_code=202, json={"data": [{"status": "error", "code": "DUPLICATE_DATA", "message": "dup"}]})
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path), "--approve-steps", "s2")
    assert code == 9 and out["error"]["code"] == "step_failed" and "DUPLICATE_DATA" in out["error"]["message"]


def test_conflict_report(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    plan = """```zcrm-plan
org_id: "5725767000000012345"
```

### m1 — Check modules

```zcrm-step
method: GET
path: /settings/modules
```

### m2 — Create module Leads again

```zcrm-step
method: POST
path: /settings/modules
body:
  modules:
    - api_name: Leads
      plural_label: Dossiers
```

### m3 — Create the same new label twice

```zcrm-step
method: POST
path: /settings/modules
body:
  modules:
    - plural_label: dossiers
```
"""
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path, plan, "mods.md"))
    problems = {(c["step"], c["problem"]) for c in out["conflicts"]}
    assert ("m2", "already exists in the org") in problems
    assert ("m3", "also created by step m2") in problems


def test_captured_secret_like_value_not_stored(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    zoho.post(f"{URL}/Accounts", json=ok("1000." + "ab" * 16 + "." + "cd" * 16))
    code, out, cap = run_cli("run", "demo1", plan_file(tmp_path), "--approve-steps", "s2")
    assert code == 9 and out["error"]["code"] == "captured_secret"
    assert "abab" not in cap.out
    assert "abab" not in "".join(p.read_text() for p in runs())
