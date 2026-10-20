import json

from zcrm import audit

URL = "https://www.zohoapis.com/crm/v8"


def test_profile_filter_and_last_n(zoho, add_profile, run_cli):
    add_profile("a1")
    add_profile("b2")
    zoho.get(f"{URL}/Leads", json={"data": []})
    for name in ("a1", "b2", "a1", "a1"):
        run_cli(name, "GET", "/Leads")
    code, out, _ = run_cli("log", "--profile", "a1")
    assert code == 0 and len(out["entries"]) == 3 and {e["profile"] for e in out["entries"]} == {"a1"}
    code, out, _ = run_cli("log", "--last", "2")
    assert len(out["entries"]) == 2
    code, out, _ = run_cli("log", "--profile", "b2", "--last", "5")
    assert len(out["entries"]) == 1


def test_entries_have_no_bodies_or_secrets(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    body = tmp_path / "b.json"
    body.write_text(json.dumps({"data": [{"Last_Name": "PrivateName"}]}))
    zoho.post(f"{URL}/Leads", json={"data": [{"status": "success", "details": {"id": "1"}}]})
    run_cli("demo1", "POST", "/Leads", str(body), "--approved")
    code, out, cap = run_cli("log")
    entry = out["entries"][-1]
    assert set(entry) == {"ts", "profile", "method", "path", "status", "outcome"}
    assert "PrivateName" not in cap.out


def test_reads_across_rotated_files(zoho, add_profile, run_cli, monkeypatch):
    monkeypatch.setattr(audit, "MAX_BYTES", 250)
    for i in range(12):
        audit.log_call("p1", "GET", f"/Leads/{i}", 200, "ok")
    code, out, _ = run_cli("log", "--profile", "p1")
    assert len(out["entries"]) == 12 and out["entries"][0]["path"] == "/Leads/0"


def test_bad_arguments(run_cli):
    assert run_cli("log", "--last", "x")[0] == 2
    assert run_cli("log", "--last", "0")[0] == 2
    assert run_cli("log", "extra")[0] == 2
    assert run_cli("log", "--last=3")[0] == 2
