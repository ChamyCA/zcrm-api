import pytest

from conftest import SENT_CLIENT_ID, SENT_REFRESH, SENT_SECRET
from zcrm import profiles, secrets, ui
from zcrm.lifecycle import setup


def script(monkeypatch, answers, hidden):
    answers, hidden = list(answers), list(hidden)
    shown = []
    monkeypatch.setattr(ui, "ask", lambda prompt, default=None: (answers.pop(0) or default))
    monkeypatch.setattr(ui, "ask_secret", lambda prompt: hidden.pop(0))
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: True)
    monkeypatch.setattr(ui, "say", lambda msg: shown.append(msg))
    return shown


def test_wizard_stores_in_keyring_and_profile(zoho, monkeypatch, keyring_fake):
    shown = script(monkeypatch, [".ca", "demo", "v8", ""], [SENT_CLIENT_ID, SENT_SECRET, SENT_REFRESH])
    assert setup.run("acme-demo") == 0
    p = profiles.get("acme-demo")
    assert p.data_center == ".ca" and p.type == "demo"
    creds = secrets.load_credentials("acme-demo")
    assert creds == {"client_id": SENT_CLIENT_ID, "client_secret": SENT_SECRET, "refresh_token": SENT_REFRESH}
    text = "\n".join(shown)
    assert "https://api-console.zohocloud.ca" in text
    assert "ZohoCRM.modules.ALL" in text


def test_grant_code_exchange_when_refresh_blank(zoho, monkeypatch):
    script(monkeypatch, [".com", "demo", "v8", ""], ["cid-value-12345", "csecret-value-12345", "", "grant-code-value"])
    assert setup.run("p1") == 0
    assert secrets.load_credentials("p1")["refresh_token"] == SENT_REFRESH


def test_non_demo_refused(monkeypatch):
    script(monkeypatch, [".com", "corp"], [])
    with pytest.raises(Exception) as exc:
        setup.run("p1")
    assert exc.value.code == "profile_not_demo"
    assert profiles.load_profiles() == {}


def test_non_tty_refused(run_cli):
    code, out, _ = run_cli("setup", "p1")
    assert code == 2
    assert out["error"]["code"] == "interactive_only"
    assert "own terminal" in out["error"]["fix"]


def test_unknown_dc_reprompts(zoho, monkeypatch):
    script(monkeypatch, [".zz", ".com", "demo", "v8", ""], ["cid-value-12345", "csecret-value-12345", SENT_REFRESH])
    assert setup.run("p1") == 0
