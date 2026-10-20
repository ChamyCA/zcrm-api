import json

import keyring
import pytest

from zcrm import secrets
from zcrm.output import ZcrmError


def test_roundtrip_and_missing():
    with pytest.raises(ZcrmError) as exc:
        secrets.load_credentials("p")
    assert exc.value.code == "credential_missing"
    assert "zcrm setup p" in exc.value.fix and "own terminal" in exc.value.fix
    for name in secrets.CRED_NAMES:
        secrets.set_credential("p", name, f"value-{name}-123456")
    assert secrets.load_credentials("p")["client_secret"] == "value-client_secret-123456"
    assert secrets.has_credentials("p")


def test_probe_ok():
    secrets.probe()


def test_probe_fails_closed_on_fail_backend():
    from keyring.backends.fail import Keyring as FailKeyring

    keyring.set_keyring(FailKeyring())
    with pytest.raises(ZcrmError) as exc:
        secrets.probe()
    assert exc.value.code == "keyring_unavailable"


def test_token_cache_shape_and_delete(keyring_fake):
    secrets.set_cached_token("p", "tok-value-123456", 123.0)
    raw = keyring_fake.store[("zcrm-api", "p/access_token")]
    assert json.loads(raw) == {"token": "tok-value-123456", "expires_at": 123.0}
    assert secrets.get_cached_token("p") == ("tok-value-123456", 123.0)
    secrets.set_credential("p", "client_id", "abcdef123")
    secrets.delete_profile("p")
    assert keyring_fake.store == {}


def test_set_credential_still_fails_loudly(monkeypatch):
    from keyring.errors import PasswordSetError

    def boom(*a, **k):
        raise PasswordSetError("nope")

    monkeypatch.setattr(keyring, "set_password", boom)
    with pytest.raises(ZcrmError) as exc:
        secrets.set_credential("p", "client_secret", "value-secret-123456")
    assert exc.value.code == "keyring_unavailable"


def test_token_cache_tolerates_keyring_errors(monkeypatch):
    from keyring.errors import KeyringError, PasswordSetError

    def set_boom(*a, **k):
        raise PasswordSetError("ro")

    def get_boom(*a, **k):
        raise KeyringError("denied")

    monkeypatch.setattr(keyring, "set_password", set_boom)
    monkeypatch.setattr(keyring, "get_password", get_boom)
    monkeypatch.setattr(keyring, "delete_password", get_boom)
    secrets.set_cached_token("p", "tok-value-123456", 9e12)
    assert secrets.get_cached_token("p") == ("tok-value-123456", 9e12)
    secrets.clear_cached_token("p")
    assert secrets.get_cached_token("p") is None


def test_file_fallback_is_0600_and_holds_only_token(monkeypatch):
    import os
    import stat

    from keyring.errors import PasswordSetError
    from zcrm import paths

    secrets.set_credential("p", "refresh_token", "refresh-secret-123456")
    monkeypatch.setattr(keyring, "set_password", lambda *a, **k: (_ for _ in ()).throw(PasswordSetError("ro")))
    secrets._memory_cache.clear()
    secrets.set_cached_token("p", "tok-value-123456", 9e12)
    f = paths.config_dir() / "token-cache.json"
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    text = f.read_text()
    assert "tok-value-123456" in text and "refresh-secret-123456" not in text
    secrets._memory_cache.clear()
    assert secrets.get_cached_token("p") == ("tok-value-123456", 9e12)
