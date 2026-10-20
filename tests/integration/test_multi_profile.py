from zcrm import secrets, ui
from zcrm.lifecycle import setup

import helpers


def test_each_request_uses_its_own_host_and_credentials(zoho, add_profile, run_cli):
    add_profile("us-demo", ".com")
    add_profile("ca-demo", ".ca")
    zoho.get("https://www.zohoapis.ca/crm/v8/Leads", json={"data": [{"id": "ca"}]})
    zoho.get("https://www.zohoapis.com/crm/v8/Leads", json={"data": [{"id": "us"}]})
    _, out_ca, _ = run_cli("ca-demo", "GET", "/Leads")
    _, out_us, _ = run_cli("us-demo", "GET", "/Leads")
    assert out_ca["data"]["data"][0]["id"] == "ca" and out_us["data"]["data"][0]["id"] == "us"
    hosts = [r.hostname for r in zoho.request_history]
    assert "accounts.zohocloud.ca" in hosts and "accounts.zoho.com" in hosts
    assert "www.zohoapis.ca" in hosts and "www.zohoapis.com" in hosts


def test_profiles_listed_and_unknown_refused(add_profile, run_cli):
    add_profile("a1", ".com")
    add_profile("b2", ".eu")
    _, out, _ = run_cli("profiles")
    assert {p["name"]: p["data_center"] for p in out["profiles"]} == {"a1": ".com", "b2": ".eu"}
    code, out, _ = run_cli("zzz", "GET", "/Leads")
    assert code == 2 and out["error"]["code"] == "profile_unknown"


def test_setup_for_second_profile_leaves_first_untouched(zoho, add_profile, monkeypatch):
    add_profile("a1", ".com")
    before = secrets.load_credentials("a1")
    helpers.script(monkeypatch, [".com", "demo", "v8", ""], ["cid-value-12345", "csecret-value-12345", "1000." + "a1" * 16 + "." + "b2" * 16])
    monkeypatch.setattr(ui, "say", lambda m: None)
    assert setup.run("b2") == 0
    assert secrets.load_credentials("a1") == before
    assert secrets.load_credentials("b2")["client_id"] == "cid-value-12345"


def test_setup_existing_profile_asks_first(add_profile, monkeypatch):
    add_profile("a1", ".com")
    before = secrets.load_credentials("a1")
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: False)
    monkeypatch.setattr(ui, "say", lambda m: None)
    assert setup.run("a1") == 0
    assert secrets.load_credentials("a1") == before
