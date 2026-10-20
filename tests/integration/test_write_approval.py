import json

import pytest

from zcrm import ui

URL = "https://www.zohoapis.com/crm/v8"


@pytest.fixture
def body(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"data": [{"Last_Name": "Smith", "Company": "Acme"}]}))
    return str(p)


def writes(zoho):
    return [r for r in zoho.request_history if r.method in ("POST", "PUT", "PATCH", "DELETE") and "/crm/" in r.url]


@pytest.mark.parametrize("method,path", [("POST", "/Leads"), ("PUT", "/Leads/1"), ("PATCH", "/Leads/1"), ("DELETE", "/Leads/1")])
def test_bare_write_refused_without_tty(zoho, add_profile, run_cli, body, method, path):
    add_profile()
    args = ["demo1", method, path] + ([body] if method != "DELETE" else [])
    code, out, _ = run_cli(*args)
    assert code == 3 and out["error"]["code"] == "approval_required"
    assert out["request"]["method"] == method and out["request"]["url"].endswith(path)
    assert writes(zoho) == []


def test_preview_summarizes_fields_only(zoho, add_profile, run_cli, body):
    add_profile()
    _, out, cap = run_cli("demo1", "POST", "/Leads", body)
    assert "Company, Last_Name" in out["request"]["body_summary"]
    assert "Smith" not in cap.out and "Acme" not in cap.out


def test_approved_flag_sends(zoho, add_profile, run_cli, body):
    add_profile()
    zoho.post(f"{URL}/Leads", json={"data": [{"status": "success", "details": {"id": "1"}}]})
    code, out, _ = run_cli("demo1", "POST", "/Leads", body, "--approved")
    assert code == 0 and len(writes(zoho)) == 1


def test_tty_confirmation_yes_and_no(zoho, add_profile, run_cli, body, monkeypatch):
    add_profile()
    zoho.post(f"{URL}/Leads", json={"data": [{"status": "success", "details": {"id": "1"}}]})
    monkeypatch.setattr(ui, "is_interactive", lambda: True)
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: False)
    code, out, _ = run_cli("demo1", "POST", "/Leads", body)
    assert code == 3 and out["error"]["code"] == "approval_declined" and writes(zoho) == []
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: True)
    assert run_cli("demo1", "POST", "/Leads", body)[0] == 0 and len(writes(zoho)) == 1


def test_bulk_delete_refused_even_when_approved(zoho, add_profile, run_cli):
    add_profile()
    code, out, _ = run_cli("demo1", "DELETE", "/Leads?ids=1,2", "--approved")
    assert code == 4 and out["error"]["code"] == "bulk_delete_refused" and writes(zoho) == []


def test_corp_profile_refused(zoho, add_profile, run_cli):
    add_profile(ptype="corp")
    for argv in (("demo1", "GET", "/Leads"), ("demo1", "POST", "/Leads", "--approved")):
        code, out, _ = run_cli(*argv)
        assert code == 4 and out["error"]["code"] == "profile_not_demo"
    assert zoho.request_history == []


def test_credential_in_body_refused(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"note": "1000." + "ab" * 16 + "." + "cd" * 16}))
    code, out, cap = run_cli("demo1", "POST", "/Leads", str(p), "--approved")
    assert code == 4 and out["error"]["code"] == "body_credential_found" and "abab" not in cap.out
    assert writes(zoho) == []


def test_audit_records_write_without_body(zoho, add_profile, run_cli, body):
    add_profile()
    zoho.post(f"{URL}/Leads", json={"data": [{"status": "success", "details": {"id": "1"}}]})
    run_cli("demo1", "POST", "/Leads", body, "--approved")
    from zcrm import audit

    entries = audit.read_entries("demo1")
    assert entries[-1]["method"] == "POST" and entries[-1]["outcome"] == "ok"
    assert "Smith" not in json.dumps(entries)
