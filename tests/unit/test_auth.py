import time

import pytest

from conftest import SENT_ACCESS, SENT_REFRESH, SENT_SECRET
from zcrm import auth, profiles, secrets
from zcrm.output import ZcrmError


def test_refresh_stores_and_reuses(zoho, add_profile):
    add_profile()
    prof = profiles.get("demo1")
    assert auth.get_access_token(prof) == SENT_ACCESS
    assert auth.get_access_token(prof) == SENT_ACCESS
    posts = [r for r in zoho.request_history if r.method == "POST"]
    assert len(posts) == 1


def test_credentials_in_body_not_url(zoho, add_profile):
    add_profile()
    auth.get_access_token(profiles.get("demo1"))
    req = zoho.request_history[0]
    assert req.url == "https://accounts.zoho.com/oauth/v2/token"
    assert SENT_REFRESH not in req.url and SENT_SECRET not in req.url
    assert "grant_type=refresh_token" in req.text


def test_refresh_when_expired(zoho, add_profile):
    add_profile()
    secrets.set_cached_token("demo1", "old-token-value", time.time() + 10)
    assert auth.get_access_token(profiles.get("demo1")) == SENT_ACCESS


def test_refresh_failure_message_has_no_secret(zoho, add_profile):
    add_profile()
    zoho.post("https://accounts.zoho.com/oauth/v2/token", json={"error": "invalid_client"})
    with pytest.raises(ZcrmError) as exc:
        auth.get_access_token(profiles.get("demo1"))
    assert exc.value.code == "token_refresh_failed"
    assert "invalid_client" in exc.value.message
    assert SENT_SECRET not in exc.value.message and SENT_REFRESH not in exc.value.message
    assert ".com" in exc.value.fix


def test_exchange_grant_code(zoho, add_profile):
    add_profile()
    refresh = auth.exchange_grant_code(profiles.get("demo1"), "cid-value-123", "csecret-value-123", "grantcode-value-123")
    assert refresh == SENT_REFRESH


def test_readonly_keychain_refresh_and_api_call_succeed(zoho, add_profile, monkeypatch, run_cli):
    from keyring.errors import PasswordSetError

    from zcrm import paths

    add_profile()
    secrets._memory_cache.clear()

    def boom(*a, **k):
        raise PasswordSetError("(100001, 'Unknown Error')")

    monkeypatch.setattr("keyring.set_password", boom)
    code, out, _ = run_cli("demo1", "GET", "/org")
    assert code == 0 and out["ok"] is True
    assert paths.audit_file().exists() and paths.audit_file().read_text().strip()
    posts = [r for r in zoho.request_history if r.method == "POST"]
    run_cli("demo1", "GET", "/org")
    assert len([r for r in zoho.request_history if r.method == "POST"]) == len(posts)  # cache reused


def test_token_cache_read_failure_falls_back_to_refresh(zoho, add_profile, monkeypatch):
    from keyring.errors import KeyringError

    add_profile()
    secrets._memory_cache.clear()
    real = __import__("keyring").get_password

    def flaky(service, user):
        if user.endswith("/access_token"):
            raise KeyringError("denied")
        return real(service, user)

    monkeypatch.setattr("keyring.get_password", flaky)
    assert auth.get_access_token(profiles.get("demo1")) == SENT_ACCESS
