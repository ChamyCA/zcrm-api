"""Refresh-token flow. Credentials go in the POST body, never the URL."""

import time

import requests

from zcrm import secrets
from zcrm.output import EXIT_CREDENTIAL, EXIT_NETWORK, ZcrmError, register_secret

SKEW = 60
TIMEOUT = 30


def _token_request(profile, data: dict) -> dict:
    url = f"https://{profile.dc.accounts_host}/oauth/v2/token"
    try:
        resp = requests.post(url, data=data, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ZcrmError(
            "network_error",
            f"Could not reach {profile.dc.accounts_host} ({type(exc).__name__}).",
            fix="Check your network connection and the profile's data center.",
            exit_code=EXIT_NETWORK,
        )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400 or not isinstance(body, dict) or "error" in body or "access_token" not in body:
        reason = body.get("error") if isinstance(body, dict) else None
        raise ZcrmError(
            "token_refresh_failed",
            f"Zoho rejected the token request for profile {profile.name!r}"
            + (f" ({reason})." if reason else f" (HTTP {resp.status_code})."),
            fix=(
                f"Check that profile {profile.name!r} uses the right data center ({profile.data_center}) "
                f"and re-enter credentials with `zcrm setup {profile.name}` in your own terminal."
            ),
            exit_code=EXIT_CREDENTIAL,
        )
    return body


def _store(profile, body: dict) -> str:
    token = body["access_token"]
    register_secret(token)
    expires_at = time.time() + float(body.get("expires_in", 3600))
    secrets.set_cached_token(profile.name, token, expires_at)
    return token


def get_access_token(profile, force: bool = False) -> str:
    if not force:
        cached = secrets.get_cached_token(profile.name)
        if cached and cached[1] - SKEW > time.time():
            return cached[0]
    creds = secrets.load_credentials(profile.name)
    body = _token_request(
        profile,
        {
            "grant_type": "refresh_token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
        },
    )
    return _store(profile, body)


def exchange_grant_code(profile, client_id: str, client_secret: str, code: str) -> str:
    """Exchange a Self Client grant code for a refresh token. Returns the refresh token."""
    register_secret(code)
    url = f"https://{profile.dc.accounts_host}/oauth/v2/token"
    try:
        resp = requests.post(
            url,
            data={"grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret, "code": code},
            timeout=TIMEOUT,
        )
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise ZcrmError(
            "token_refresh_failed",
            f"Could not exchange the grant code ({type(exc).__name__}).",
            fix="Generate a fresh code (valid a few minutes) and retry.",
            exit_code=EXIT_CREDENTIAL,
        )
    if not isinstance(body, dict) or "refresh_token" not in body:
        reason = body.get("error") if isinstance(body, dict) else None
        raise ZcrmError(
            "token_refresh_failed",
            "Zoho did not return a refresh token" + (f" ({reason})." if reason else "."),
            fix="Generate a fresh code in the API Console and retry.",
            exit_code=EXIT_CREDENTIAL,
        )
    register_secret(body["refresh_token"])
    if "access_token" in body:
        _store(profile, body)
    return body["refresh_token"]
