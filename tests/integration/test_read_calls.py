import json

from conftest import SENT_ACCESS

URL = "https://www.zohoapis.com/crm/v8"


def test_modules_records_and_metadata(zoho, add_profile, run_cli):
    add_profile()
    zoho.get(f"{URL}/settings/modules", json={"modules": [{"api_name": "Leads"}]})
    zoho.get(f"{URL}/Leads", json={"data": [{"id": "1"}]})
    zoho.get(f"{URL}/settings/fields?module=Leads", json={"fields": []})
    for path in ("/settings/modules", "/Leads", "/settings/fields?module=Leads"):
        code, out, _ = run_cli("demo1", "GET", path)
        assert code == 0 and out["ok"] is True and out["status"] == 200 and out["profile"] == "demo1"


def test_search_and_coql(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    zoho.get(f"{URL}/Leads/search", json={"data": []})
    zoho.post(f"{URL}/coql", json={"data": [{"id": "9"}]})
    body = tmp_path / "q.json"
    body.write_text(json.dumps({"select_query": "select Last_Name from Leads limit 1"}))
    assert run_cli("demo1", "GET", "/Leads/search?word=abc")[0] == 0
    code, out, _ = run_cli("demo1", "POST", "/coql", str(body))
    assert code == 0 and out["data"]["data"][0]["id"] == "9"
    code, out, _ = run_cli("demo1", "COQL", str(body))
    assert code == 0 and out["data"]["data"][0]["id"] == "9"
    assert zoho.last_request.method == "POST" and zoho.last_request.path == "/crm/v8/coql"
    assert run_cli("demo1", "COQL")[0] == 2


def test_one_call_no_approval_for_reads(zoho, add_profile, run_cli):
    add_profile()
    zoho.get(f"{URL}/Leads", json={"data": []})
    code, out, _ = run_cli("demo1", "GET", "/Leads")
    assert code == 0
    assert zoho.last_request.headers["Authorization"].endswith(SENT_ACCESS)


def test_expired_token_refreshed(zoho, add_profile, run_cli):
    add_profile()
    from zcrm import secrets

    secrets.set_cached_token("demo1", "stale-token-value", 1.0)
    zoho.get(f"{URL}/Leads", json={"data": []})
    assert run_cli("demo1", "GET", "/Leads")[0] == 0
    assert zoho.last_request.headers["Authorization"].endswith(SENT_ACCESS)


def test_retry_then_success_and_exhausted(zoho, add_profile, run_cli):
    add_profile()
    zoho.get(f"{URL}/Leads", [{"status_code": 429, "json": {}}, {"status_code": 503, "json": {}}, {"json": {"data": []}}])
    assert run_cli("demo1", "GET", "/Leads")[0] == 0
    zoho.get(f"{URL}/Contacts", status_code=429, json={})
    code, out, _ = run_cli("demo1", "GET", "/Contacts")
    assert code == 6 and out["error"]["code"] == "rate_limited"


def test_missing_credentials_message(zoho, add_profile, run_cli):
    add_profile(creds=False)
    code, out, _ = run_cli("demo1", "GET", "/Leads")
    assert code == 5 and out["error"]["code"] == "credential_missing"
    assert "zcrm setup demo1" in out["error"]["fix"] and "own terminal" in out["error"]["fix"]


def test_scope_warning_and_scope_error(zoho, add_profile, run_cli):
    add_profile(scopes=["ZohoCRM.org.READ"])
    zoho.get(f"{URL}/Leads", status_code=401, json={"code": "OAUTH_SCOPE_MISMATCH"})
    code, out, _ = run_cli("demo1", "GET", "/Leads")
    assert code == 6 and out["error"]["code"] == "scope_insufficient"
    zoho.get(f"{URL}/org", json={"org": []})
    code, out, _ = run_cli("demo1", "GET", "/org")
    assert code == 0 and "warnings" not in out


def test_missing_scope_warns(zoho, add_profile, run_cli):
    add_profile(scopes=["ZohoCRM.org.READ"])
    zoho.get(f"{URL}/Leads", json={"data": []})
    code, out, _ = run_cli("demo1", "GET", "/Leads")
    assert code == 0 and "ZohoCRM.modules.leads.READ" in out["warnings"][0]


def test_usage_errors(zoho, add_profile, run_cli):
    add_profile()
    assert run_cli("demo1", "get", "/Leads")[0] == 2
    assert run_cli("demo1", "GET")[0] == 2
    assert run_cli("demo1", "GET", "/Leads", "--last=3")[0] == 2
    assert run_cli("nope", "GET", "/Leads")[1]["error"]["code"] == "profile_unknown"
    code, out, _ = run_cli("demo1", "GET", "/a/../b")
    assert code == 4 and out["error"]["code"] == "unsafe_path"


def test_embedded_record_error(zoho, add_profile, run_cli, tmp_path):
    add_profile()
    zoho.post(f"{URL}/Leads", status_code=202, json={"data": [{"status": "error", "code": "DUPLICATE_DATA", "message": "dup"}]})
    body = tmp_path / "b.json"
    body.write_text(json.dumps({"data": [{"Last_Name": "x"}]}))
    code, out, _ = run_cli("demo1", "POST", "/Leads", str(body), "--approved")
    assert code == 6 and out["error"]["code"] == "record_error"
