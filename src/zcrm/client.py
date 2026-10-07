"""One Zoho CRM request with token refresh, retry and backoff."""

import random
import time
from dataclasses import dataclass

import requests

from zcrm import audit, auth, policy
from zcrm.output import EXIT_API, EXIT_NETWORK, ZcrmError

MAX_ATTEMPTS = 4
TIMEOUT = 60
_sleep = time.sleep


@dataclass
class Response:
    status: int
    data: object


def build_url(profile, path: str) -> str:
    return f"https://{profile.dc.api_host}/crm/{profile.api_version}{path}"


def _backoff(attempt: int, retry_after=None) -> float:
    if retry_after is not None:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(2 ** attempt, 30) + random.uniform(0, 0.25)


def embedded_errors(data) -> list:
    """Zoho returns HTTP 2xx with per-item failures; collect them."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if str(node.get("status", "")).lower() == "error":
                found.append({"code": node.get("code"), "message": node.get("message")})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def _error_for(status: int, body) -> ZcrmError:
    code = body.get("code") if isinstance(body, dict) else None
    message = body.get("message") if isinstance(body, dict) else None
    detail = " ".join(str(x) for x in (code, message) if x)
    if code == "OAUTH_SCOPE_MISMATCH" or (status == 401 and code and "SCOPE" in str(code)):
        return ZcrmError(
            "scope_insufficient",
            "Zoho says the token does not have the scope this request needs.",
            fix="Add the missing scope to the profile and regenerate the refresh token (`zcrm setup <profile>`).",
            exit_code=EXIT_API,
            status=status,
        )
    if status == 429:
        return ZcrmError("rate_limited", "Zoho rate limit reached and retries were exhausted.", fix="Wait a minute and retry.", exit_code=EXIT_API, status=status)
    return ZcrmError("api_error", f"Zoho returned HTTP {status}" + (f": {detail}" if detail else "."), exit_code=EXIT_API, status=status)


def request(profile, method: str, path: str, body=None, ctx=None) -> Response:
    ctx = ctx or {}
    kind = policy.classify(method, path)
    is_read = kind == "read"
    url = build_url(profile, path)

    def log(status, outcome):
        audit.log_call(profile.name, method, path, status, outcome, ctx.get("run_id"), ctx.get("step_id"))

    token = auth.get_access_token(profile)
    refreshed = False
    attempt = 0
    while True:
        try:
            resp = requests.request(
                method,
                url,
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                json=body if body is not None else None,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            if is_read and attempt < MAX_ATTEMPTS - 1:
                _sleep(_backoff(attempt))
                attempt += 1
                continue
            log(None, "network_error")
            raise ZcrmError(
                "network_error",
                f"Network failure calling Zoho ({type(exc).__name__}).",
                fix="Check your connection and retry." if is_read else "The write may or may not have been applied; check the org before retrying.",
                exit_code=EXIT_NETWORK,
            )
        status = resp.status_code
        try:
            data = resp.json() if resp.content else None
        except ValueError:
            data = None
        code = data.get("code") if isinstance(data, dict) else None
        if status == 401 and code in ("INVALID_TOKEN", "AUTHENTICATION_FAILURE") and not refreshed:
            token = auth.get_access_token(profile, force=True)
            refreshed = True
            continue
        if status == 429 and attempt < MAX_ATTEMPTS - 1:
            _sleep(_backoff(attempt, resp.headers.get("Retry-After")))
            attempt += 1
            continue
        if status in (502, 503, 504) and is_read and attempt < MAX_ATTEMPTS - 1:
            _sleep(_backoff(attempt))
            attempt += 1
            continue
        break
    if status >= 400:
        log(status, "error")
        raise _error_for(status, data)
    log(status, "ok")
    return Response(status, data)
