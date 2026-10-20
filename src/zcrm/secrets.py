"""Keyring wrapper. Credentials and the cached access token live only here."""

import json
import os

import keyring
from keyring.errors import KeyringError

from zcrm import paths
from zcrm.output import EXIT_CREDENTIAL, ZcrmError, register_secret

SERVICE = "zcrm-api"
CRED_NAMES = ("client_id", "client_secret", "refresh_token")


def _key(profile: str, name: str) -> str:
    return f"{profile}/{name}"


def _check_backend() -> None:
    backend = keyring.get_keyring()
    module = type(backend).__module__
    if module.startswith("keyring.backends.fail") or module.startswith("keyring.backends.null"):
        raise ZcrmError(
            "keyring_unavailable",
            "No usable OS keyring backend was found.",
            fix=(
                "macOS: unlock your login keychain. Windows: Credential Manager should work by default. "
                "Linux: install and unlock a Secret Service provider such as gnome-keyring or KeePassXC."
            ),
            exit_code=EXIT_CREDENTIAL,
        )


def probe() -> None:
    """Write, read and delete a probe entry; fail closed when the backend is unusable."""
    _check_backend()
    try:
        keyring.set_password(SERVICE, "__probe__", "ok")
        value = keyring.get_password(SERVICE, "__probe__")
        keyring.delete_password(SERVICE, "__probe__")
    except KeyringError as exc:
        raise ZcrmError(
            "keyring_unavailable",
            f"The OS keyring failed the read/write probe ({type(exc).__name__}).",
            fix="Unlock the keyring or fix its configuration, then run `zcrm doctor`.",
            exit_code=EXIT_CREDENTIAL,
        )
    if value != "ok":
        raise ZcrmError("keyring_unavailable", "The OS keyring did not return the probe value.", exit_code=EXIT_CREDENTIAL)


def probe_read() -> None:
    """Raise keyring_unavailable when stored credentials cannot be read."""
    _check_backend()
    _get("__probe__", "client_id")


def probe_write() -> bool:
    """True when the keychain accepts writes (needed by `zcrm setup`, not by normal calls)."""
    try:
        keyring.set_password(SERVICE, "__probe__", "ok")
    except Exception:
        return False
    try:
        keyring.delete_password(SERVICE, "__probe__")
    except Exception:
        pass
    return True


def _get(profile: str, name: str):
    try:
        return keyring.get_password(SERVICE, _key(profile, name))
    except KeyringError as exc:
        raise ZcrmError(
            "keyring_unavailable",
            f"The OS keyring could not be read ({type(exc).__name__}).",
            fix=(
                "Unlock the keyring, then retry. If zcrm is running inside a sandbox (such as the Claude Code "
                "sandbox) without keychain access, exclude `zcrm` from the sandbox or run it outside it."
            ),
            exit_code=EXIT_CREDENTIAL,
        )


def set_credential(profile: str, name: str, value: str) -> None:
    register_secret(value)
    try:
        keyring.set_password(SERVICE, _key(profile, name), value)
    except KeyringError as exc:
        raise ZcrmError(
            "keyring_unavailable",
            f"The OS keyring could not be written ({type(exc).__name__}).",
            fix="Unlock the keyring, then retry.",
            exit_code=EXIT_CREDENTIAL,
        )


def missing_error(profile: str) -> ZcrmError:
    return ZcrmError(
        "credential_missing",
        f"No stored credentials for profile {profile!r}.",
        fix=f'Run `zcrm setup {profile}` in your own terminal.',
        exit_code=EXIT_CREDENTIAL,
    )


def load_credentials(profile: str) -> dict:
    creds = {}
    for name in CRED_NAMES:
        value = _get(profile, name)
        if not value:
            raise missing_error(profile)
        register_secret(value)
        creds[name] = value
    return creds


def has_credentials(profile: str) -> bool:
    try:
        return all(_get(profile, name) for name in CRED_NAMES)
    except ZcrmError:
        return False


# Process-local fallback so one `zcrm run` does not refresh on every step.
_memory_cache: dict = {}


def _token_file():
    return paths.config_dir() / "token-cache.json"


def _read_file_cache() -> dict:
    try:
        data = json.loads(_token_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_file_cache(data: dict) -> None:
    """Best-effort 0600 write. Holds only short-lived access tokens, never credentials."""
    target = _token_file()
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data))
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except OSError:
        pass


def _parse_cached(raw):
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data["token"], float(data["expires_at"])
    except (ValueError, KeyError, TypeError):
        return None


def get_cached_token(profile: str):
    """Latest-expiring entry from keychain, file or memory. Never raises."""
    candidates = []
    try:
        candidates.append(_parse_cached(keyring.get_password(SERVICE, _key(profile, "access_token"))))
    except Exception:
        pass
    candidates.append(_parse_cached(_read_file_cache().get(profile)))
    candidates.append(_memory_cache.get(profile))
    candidates = [c for c in candidates if c]
    if not candidates:
        return None
    token, expires_at = max(candidates, key=lambda c: c[1])
    register_secret(token)
    return token, expires_at


def set_cached_token(profile: str, token: str, expires_at: float) -> None:
    """Best-effort: a failed cache write must never fail the command."""
    register_secret(token)
    _memory_cache[profile] = (token, expires_at)
    try:
        keyring.set_password(SERVICE, _key(profile, "access_token"), json.dumps({"token": token, "expires_at": expires_at}))
        return
    except Exception:
        pass
    data = _read_file_cache()
    data[profile] = {"token": token, "expires_at": expires_at}
    _write_file_cache(data)


def clear_cached_token(profile: str) -> None:
    _memory_cache.pop(profile, None)
    data = _read_file_cache()
    if data.pop(profile, None) is not None:
        _write_file_cache(data)
    _delete(profile, "access_token")


def _delete(profile: str, name: str) -> None:
    try:
        keyring.delete_password(SERVICE, _key(profile, name))
    except Exception:
        pass


def delete_profile(profile: str) -> None:
    for name in (*CRED_NAMES, "access_token"):
        _delete(profile, name)
