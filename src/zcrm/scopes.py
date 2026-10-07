"""Built-in map from API path + method to the Zoho scope a request needs.

VERIFY: exact Zoho scope names against current Zoho documentation.
Unmapped paths return "unknown": a warning, never a block.
"""

DEFAULT_SCOPES = [
    "ZohoCRM.modules.ALL",
    "ZohoCRM.settings.ALL",
    "ZohoCRM.org.READ",
    "ZohoCRM.coql.READ",
    "ZohoCRM.users.READ",
]

_OPS = {"GET": "READ", "POST": "CREATE", "PUT": "UPDATE", "PATCH": "UPDATE", "DELETE": "DELETE"}


def _segments(path: str) -> list[str]:
    return [s for s in path.split("?", 1)[0].split("/") if s]


def required_scope(method: str, path: str):
    """Return (needed_scope, acceptable_scopes) or None when the path is not mapped."""
    segs = _segments(path)
    if not segs:
        return None
    method = method.upper()
    op = _OPS.get(method, "READ")
    head = segs[0]
    low = head.lower()
    if low == "org":
        needed = "ZohoCRM.org.READ" if method == "GET" else "ZohoCRM.org.ALL"
        return needed, {needed, "ZohoCRM.org.ALL"}
    if low == "coql":
        return "ZohoCRM.coql.READ", {"ZohoCRM.coql.READ", "ZohoCRM.coql.ALL"}
    if low == "users":
        needed = "ZohoCRM.users.READ" if method == "GET" else "ZohoCRM.users.ALL"
        return needed, {needed, "ZohoCRM.users.ALL"}
    if low == "settings":
        if len(segs) < 2:
            return None
        area = segs[1].lower()
        needed = f"ZohoCRM.settings.{area}.{op}"
        return needed, {needed, f"ZohoCRM.settings.{area}.ALL", "ZohoCRM.settings.ALL"}
    if head[0].isupper():
        mod = head.lower()
        needed = f"ZohoCRM.modules.{mod}.{op}"
        return needed, {needed, f"ZohoCRM.modules.{mod}.ALL", "ZohoCRM.modules.ALL"}
    return None


def check(profile_scopes, method: str, path: str):
    """Return ("ok"|"missing"|"unknown", needed_scope_or_None)."""
    found = required_scope(method, path)
    if found is None:
        return "unknown", None
    needed, acceptable = found
    have = {s.strip() for s in profile_scopes}
    return ("ok" if have & acceptable else "missing"), needed
