"""The only module that writes to stdout/stderr. Everything passes through redaction."""

import json
import re
import sys

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_APPROVAL = 3
EXIT_REFUSED = 4
EXIT_CREDENTIAL = 5
EXIT_API = 6
EXIT_PLAN = 7
EXIT_NETWORK = 8
EXIT_STOPPED = 9

REDACTED = "[REDACTED]"

_secrets: set[str] = set()

_PATTERNS = [
    (re.compile(r"1000\.[0-9a-fA-F]{32}\.[0-9a-fA-F]{32}"), REDACTED),
    (re.compile(r"1000\.[A-Z0-9]{20,}"), REDACTED),
    (re.compile(r"(?i)\b(zoho-oauthtoken|bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 " + REDACTED),
    (
        re.compile(
            r"(?i)\b(client_secret|refresh_token|access_token)([\"']?\s*[:=]\s*[\"']?)[^\s\"',&}]{8,}"
        ),
        r"\1\2" + REDACTED,
    ),
]


class ZcrmError(Exception):
    def __init__(self, code, message, fix=None, exit_code=EXIT_API, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix
        self.exit_code = exit_code
        self.extra = extra

    def envelope(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.fix:
            err["fix"] = self.fix
        out = {"ok": False, "error": err}
        out.update(self.extra)
        return out


def register_secret(value) -> None:
    if isinstance(value, str) and len(value) >= 6:
        _secrets.add(value)


def clear_secrets() -> None:
    _secrets.clear()


def redact(text: str) -> str:
    for secret in sorted(_secrets, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact_obj(obj):
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {redact(str(k)): redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj


def emit_json(obj) -> None:
    sys.stdout.write(json.dumps(redact_obj(obj), indent=2, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def stream_is_tty(stream: str = "stderr") -> bool:
    target = sys.stderr if stream == "stderr" else sys.stdout
    try:
        return target.isatty()
    except (AttributeError, ValueError):
        return False


def emit_text(message: str, *, stream: str = "stderr") -> None:
    target = sys.stderr if stream == "stderr" else sys.stdout
    target.write(redact(message) + "\n")
    target.flush()
