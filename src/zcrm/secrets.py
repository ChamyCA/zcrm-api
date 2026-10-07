"""Keyring wrapper. Credentials and the cached access token live only here."""

import json

import keyring
from keyring.errors import KeyringError

from zcrm.output import EXIT_CREDENTIAL, ZcrmError, register_secret

SERVICE = "zcrm-api"
CRED_NAMES = ("client_id", "client_secret", "refresh_token")


def _key(profile: str, name: str) -> str:
    return f"{profile}/{name}"


def probe() -> None:
    """Write, read and delete a probe entry; fail closed when the backend is unusable."""
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


def _get(profile: str, name: str):
    try:
        return keyring.get_password(SERVICE, _key(profile, name))
    except KeyringError as exc:
        raise ZcrmError(
            "keyring_unavailable",
            f"The OS keyring could not be read ({type(exc).__name__}).",
            fix="Unlock the keyring, then retry.",
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


def get_cached_token(profile: str):
    raw = _get(profile, "access_token")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        token, expires_at = data["token"], float(data["expires_at"])
    except (ValueError, KeyError, TypeError):
        return None
    register_secret(token)
    return token, expires_at


def set_cached_token(profile: str, token: str, expires_at: float) -> None:
    register_secret(token)
    keyring.set_password(SERVICE, _key(profile, "access_token"), json.dumps({"token": token, "expires_at": expires_at}))


def clear_cached_token(profile: str) -> None:
    _delete(profile, "access_token")


def _delete(profile: str, name: str) -> None:
    try:
        keyring.delete_password(SERVICE, _key(profile, name))
    except KeyringError:
        pass


def delete_profile(profile: str) -> None:
    for name in (*CRED_NAMES, "access_token"):
        _delete(profile, name)
