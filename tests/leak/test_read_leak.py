from conftest import SENT_ACCESS, SENT_REFRESH, SENTINELS, all_files_text

URL = "https://www.zohoapis.com/crm/v8"


def test_echoed_tokens_redacted_in_output_and_logs(zoho, add_profile, run_cli, env):
    add_profile()
    zoho.get(f"{URL}/Leads", json={"data": [{"note": f"token {SENT_ACCESS} and refresh_token={SENT_REFRESH}"}]})
    code, out, cap = run_cli("demo1", "GET", "/Leads")
    assert code == 0
    for s in SENTINELS:
        assert s not in cap.out and s not in cap.err
        assert s not in all_files_text(env["tmp"] / "zcrm-home")


def test_error_text_echoing_token_is_redacted(zoho, add_profile, run_cli):
    add_profile()
    zoho.get(f"{URL}/Leads", status_code=400, json={"code": "BAD", "message": f"bad {SENT_ACCESS}"})
    code, out, cap = run_cli("demo1", "GET", "/Leads")
    assert code == 6 and SENT_ACCESS not in cap.out


def test_missing_credential_output_clean(zoho, add_profile, run_cli):
    add_profile(creds=False)
    _, _, cap = run_cli("demo1", "GET", "/Leads")
    for s in SENTINELS:
        assert s not in cap.out
