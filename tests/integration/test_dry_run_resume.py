import os
import sys

from plan_helpers import URL, mock_zoho, ok, plan_file, writes
from zcrm import paths
from zcrm.plan import parser


def runs():
    return sorted(paths.runs_dir().glob("*.json")) if paths.runs_dir().exists() else []


def test_dry_run_sends_zero_writes_and_creates_no_state(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path), "--dry-run")
    assert code == 0 and out["mode"] == "dry_run"
    assert [w["step"] for w in out["would_send"]] == ["s2", "s3", "s4"]
    assert out["would_send"][0]["method"] == "POST" and out["would_send"][0]["body_summary"]
    assert out["would_send"][2].get("unresolved_variables") is True
    assert writes(zoho) == [] and runs() == []


def test_only_reads(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path), "--only-reads")
    assert code == 0 and out["mode"] == "only_reads" and out["report"]["completed"] == ["s1"]
    assert writes(zoho) == []


def test_automatic_resume_never_repeats_completed_writes(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    run_cli("run", "demo1", p, "--approve-steps", "s2")
    run_cli("run", "demo1", p, "--approve-steps", "s2,s3")
    assert len(writes(zoho, "POST")) == 2 and len([r for r in writes(zoho) if r.path.endswith("/accounts")]) == 1
    assert len(runs()) == 1


def test_fresh_creates_new_state_and_resends(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    run_cli("run", "demo1", p, "--approve-steps", "s2")
    run_cli("run", "demo1", p, "--fresh", "--approve-steps", "s2")
    assert len(runs()) == 2 and len([r for r in writes(zoho) if r.path.endswith("/accounts")]) == 2


def test_from_step_uses_persisted_variables(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    run_cli("run", "demo1", p, "--approve-steps", "s2")
    code, out, _ = run_cli("run", "demo1", p, "--from-step", "s3", "--approve-steps", "s3")
    assert out["report"]["completed"] == ["s1", "s2", "s3"]
    assert run_cli("run", "demo1", p, "--from-step", "nope")[1]["error"]["code"] == "step_unknown"
    assert run_cli("run", "demo1", p, "--from-step", "2")[0] in (0, 3)


def test_changed_plan_refuses_auto_resume(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    run_cli("run", "demo1", p, "--approve-steps", "s2")
    open(p, "a").write("\nExtra prose.\n")
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s2")
    assert code == 7 and out["error"]["code"] == "plan_changed_since_state"
    assert run_cli("run", "demo1", p, "--fresh", "--dry-run")[0] == 0
    code, out, _ = run_cli("run", "demo1", p, "--fresh", "--approve-steps", "s2")
    assert code == 0 and out["pending"] == ["s3", "s4"]


def interrupt(zoho, path):
    def cb(request, context):
        raise KeyboardInterrupt

    zoho.post(f"{URL}{path}", json=cb)


VERIFY_PLAN = """```zcrm-plan
org_id: "5725767000000012345"
```

### c1 — Create contact

```zcrm-step
method: POST
path: /Contacts
body:
  data:
    - Last_Name: Smith
verify:
  path: /Contacts/search?criteria=(Last_Name:equals:Smith)
  match:
    path: data[0].id
```
"""


def test_interrupted_write_verified_by_lookup_not_repeated(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path, VERIFY_PLAN, "v.md")
    interrupt(zoho, "/Contacts")
    code, _, _ = run_cli("run", "demo1", p, "--approve-steps", "c1")
    assert code == 130
    state = [__import__("json").loads(f.read_text()) for f in runs()][0]
    assert state["steps"]["c1"]["status"] == "unknown"
    assert not [f for f in paths.runs_dir().glob("*.lock")]
    zoho.get(f"{URL}/Contacts/search", json={"data": [{"id": "222"}]})
    before = len(writes(zoho))
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "c1")
    assert code == 0 and out["report"]["completed"] == ["c1"] and len(writes(zoho)) == before
    assert any("confirmed by lookup" in w for w in out["report"]["warnings"])


def test_interrupted_write_not_found_is_retried_with_approval(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path, VERIFY_PLAN, "v.md")
    interrupt(zoho, "/Contacts")
    run_cli("run", "demo1", p, "--approve-steps", "c1")
    zoho.get(f"{URL}/Contacts/search", status_code=204)
    zoho.post(f"{URL}/Contacts", json=ok("333"))
    before = len(writes(zoho))
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "c1")
    assert code == 0 and len(writes(zoho)) == before + 1


def test_unverifiable_unknown_step_needs_user_decision(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    interrupt(zoho, "/Accounts")
    run_cli("run", "demo1", p, "--approve-steps", "s2")
    zoho.post(f"{URL}/Accounts", json=ok("111"))
    before = len(writes(zoho))
    code, out, _ = run_cli("run", "demo1", p)
    assert code == 9 and out["error"]["code"] == "step_outcome_unknown" and len(writes(zoho)) == before
    code, out, _ = run_cli("run", "demo1", p, "--skip-step", "s2")
    assert out["report"]["skipped"] == ["s2"]


def test_network_error_mid_write_leaves_unknown(zoho, add_profile, run_cli, tmp_path):
    import requests

    add_profile()
    mock_zoho(zoho)
    zoho.post(f"{URL}/Accounts", exc=requests.ConnectTimeout)
    code, out, _ = run_cli("run", "demo1", plan_file(tmp_path), "--approve-steps", "s2")
    assert code == 9 and out["error"]["code"] == "step_outcome_unknown" and len(writes(zoho)) == 1


def test_concurrent_run_locked(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    mock_zoho(zoho)
    p = plan_file(tmp_path)
    sha = parser.parse(open(p).read()).sha256[:8]
    paths.runs_dir().mkdir(parents=True, exist_ok=True)
    lock = paths.runs_dir() / f"{sha}-demo1.lock"
    lock.write_text(str(os.getpid()))
    code, out, _ = run_cli("run", "demo1", p, "--approve-steps", "s2")
    assert code == 7 and out["error"]["code"] == "run_locked" and writes(zoho) == []
    if sys.platform != "win32":  # stale-PID takeover needs a PID probe, unavailable on Windows
        lock.write_text("99999999")
        code, _, _ = run_cli("run", "demo1", p, "--approve-steps", "s2")
        assert code == 0
