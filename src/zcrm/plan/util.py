"""JSON path lookup and {{variable}} substitution."""

import re

MISSING = object()
VAR_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def jpath(obj, expr: str):
    """Look up 'a.b[0].c' in parsed JSON. Returns MISSING when absent."""
    cur = obj
    for name, index in _TOKEN.findall(expr or ""):
        if name:
            if not isinstance(cur, dict) or name not in cur:
                return MISSING
            cur = cur[name]
        else:
            i = int(index)
            if not isinstance(cur, list) or i >= len(cur):
                return MISSING
            cur = cur[i]
    return cur


def find_vars(obj) -> set:
    found = set()
    if isinstance(obj, str):
        found.update(VAR_RE.findall(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.update(find_vars(k))
            found.update(find_vars(v))
    elif isinstance(obj, list):
        for v in obj:
            found.update(find_vars(v))
    return found


def substitute(obj, variables: dict):
    """Replace {{var}}. Raises KeyError(name) for an unresolved variable."""
    if isinstance(obj, str):
        whole = VAR_RE.fullmatch(obj)
        if whole:
            return variables[whole.group(1)]
        return VAR_RE.sub(lambda m: str(variables[m.group(1)]), obj)
    if isinstance(obj, dict):
        return {substitute(k, variables): substitute(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, variables) for v in obj]
    return obj


def find_id(data):
    """First created/updated record or metadata ID in a Zoho response."""
    if isinstance(data, dict):
        details = data.get("details")
        if isinstance(details, dict) and "id" in details:
            return str(details["id"])
        for v in data.values():
            found = find_id(v)
            if found:
                return found
    elif isinstance(data, list):
        for v in data:
            found = find_id(v)
            if found:
                return found
    return None
