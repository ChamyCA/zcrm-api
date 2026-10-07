"""Method/path classification and path safety."""

import re
from urllib.parse import parse_qs

from zcrm.output import EXIT_REFUSED, EXIT_USAGE, ZcrmError

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_BAD_ENCODING = re.compile(r"(?i)%2e|%2f|%5c|%00")
_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f\s\\]")


def _unsafe(path, why) -> ZcrmError:
    return ZcrmError("unsafe_path", f"Refused path {path!r}: {why}.", fix="Use a relative API path such as /Leads.", exit_code=EXIT_REFUSED)


def validate_method(method: str) -> str:
    if method not in METHODS:
        raise ZcrmError(
            "usage",
            f"Invalid method {method!r}. Use an uppercase HTTP method: GET, POST, PUT, PATCH or DELETE.",
            exit_code=EXIT_USAGE,
        )
    return method


def normalize_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/"):
        raise _unsafe(path, "must start with /")
    if _BAD_CHARS.search(path):
        raise _unsafe(path, "contains whitespace, control characters or a backslash")
    if _BAD_ENCODING.search(path):
        raise _unsafe(path, "contains encoded traversal characters")
    base = path.split("?", 1)[0]
    if "//" in base or "://" in path.split("?", 1)[0]:
        raise _unsafe(path, "contains // or a scheme")
    if any(seg == ".." or seg == "." for seg in base.split("/")):
        raise _unsafe(path, "contains . or .. segments")
    return path


def classify(method: str, path: str) -> str:
    """Return read, create, update or delete."""
    validate_method(method)
    base = path.split("?", 1)[0].rstrip("/").lower()
    if method == "GET":
        return "read"
    if method == "POST" and base == "/coql":
        return "read"
    return {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}[method]


def is_write(kind: str) -> bool:
    return kind != "read"


def check_bulk_delete(method: str, path: str) -> None:
    if method != "DELETE":
        return
    base, _, query = path.partition("?")
    segs = [s for s in base.split("/") if s]
    ids = parse_qs(query).get("ids", [])
    id_values = [v for raw in ids for v in raw.split(",") if v]
    if len(id_values) > 1 or (len(segs) <= 1 and len(id_values) != 1):
        raise ZcrmError(
            "bulk_delete_refused",
            "Bulk delete is not supported. Delete one record at a time using its ID.",
            fix="Use DELETE /<Module>/<record_id>.",
            exit_code=EXIT_REFUSED,
        )


def body_summary(body) -> str:
    if body is None:
        return "no body"
    if isinstance(body, dict):
        for key, value in body.items():
            if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                fields = sorted({k for v in value for k in v})
                return f"{len(value)} item(s) under {key!r}, fields: {', '.join(fields)}"
        return "fields: " + ", ".join(sorted(body))
    return type(body).__name__
