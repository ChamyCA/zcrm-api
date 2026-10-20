import json

from conftest import SENTINELS, all_files_text


def test_preview_and_audit_have_no_secrets_or_bodies(zoho, add_profile, run_cli, tmp_path, env):
    add_profile()
    body = tmp_path / "b.json"
    body.write_text(json.dumps({"data": [{"Last_Name": "Smith", "Description": "private text"}]}))
    zoho.post("https://www.zohoapis.com/crm/v8/Leads", json={"data": [{"status": "success", "details": {"id": "1"}}]})
    _, _, cap1 = run_cli("demo1", "POST", "/Leads", str(body))
    _, _, cap2 = run_cli("demo1", "POST", "/Leads", str(body), "--approved")
    blob = cap1.out + cap2.out + cap1.err + cap2.err + all_files_text(env["tmp"] / "zcrm-home")
    for s in SENTINELS:
        assert s not in blob
    assert "private text" not in all_files_text(env["tmp"] / "zcrm-home")
    assert "private text" not in cap1.out
