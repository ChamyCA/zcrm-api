"""Credential and injection-phrase detection. Reports line and kind only, never the matched text."""

import math
import re

_CREDENTIAL_PATTERNS = [
    ("zoho_token", re.compile(r"1000\.[0-9a-fA-F]{32}\.[0-9a-fA-F]{32}")),
    ("zoho_client_id", re.compile(r"1000\.[A-Z0-9]{20,}")),
    ("auth_header", re.compile(r"(?i)(authorization\s*:|zoho-oauthtoken\s+\S|\bbearer\s+[A-Za-z0-9._\-]{16,})")),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(client_secret|refresh_token|access_token|api[_-]?key|password|secret)\b[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9._\-/+]{12,}"
        ),
    ),
]
_SECRET_WORDS = re.compile(r"(?i)token|secret|key|password")
_LONG_STRING = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")

_INJECTION_PATTERNS = [
    ("skip_confirmation", re.compile(r"(?i)\bskip(?:ping)?\s+(?:all\s+)?(?:the\s+)?(?:confirm\w*|approv\w*)")),
    ("disable_confirmation", re.compile(r"(?i)\b(?:disable|turn\s+off|bypass|remove)\s+(?:all\s+)?(?:the\s+)?(?:confirm\w*|approv\w*|permission\w*|prompt\w*)")),
    ("without_asking", re.compile(r"(?i)\bwithout\s+(?:asking|confirm\w*|approv\w*|prompt\w*)")),
    ("do_not_ask", re.compile(r"(?i)\b(?:do\s+not|don't|never)\s+(?:ask|prompt|confirm)\b")),
    ("auto_approve", re.compile(r"(?i)\bauto[- ]?approv\w*")),
    ("reveal_credentials", re.compile(r"(?i)\b(?:print|show|reveal|display|echo|output|send|share|paste|leak)\s+(?:\w+\s+){0,3}(?:token|secret|credential|password|refresh|keyring)")),
    ("ignore_instructions", re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+instructions")),
    ("approval_flag", re.compile(r"--approved\b|--approve-steps\b")),
]


def _entropy(text: str) -> float:
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((n / len(text)) * math.log2(n / len(text)) for n in counts.values())


def find_credentials(text: str) -> list:
    """Return [(line_number, kind)]. Never includes the matched text."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        kinds = [kind for kind, pattern in _CREDENTIAL_PATTERNS if pattern.search(line)]
        if not kinds and _SECRET_WORDS.search(line):
            for match in _LONG_STRING.finditer(line):
                if _entropy(match.group(0)) > 4.0:
                    kinds.append("high_entropy_string")
                    break
        hits.extend((number, kind) for kind in kinds)
    return hits


def find_injection(text: str) -> list:
    """Return [{line, kind, phrase}] for prose that tries to steer approvals or credentials."""
    flags = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in _INJECTION_PATTERNS:
            match = pattern.search(line)
            if match:
                flags.append({"line": number, "kind": kind, "phrase": match.group(0)})
    return flags
