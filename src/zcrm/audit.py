"""Audit log: JSON Lines with no secrets and no bodies."""

import json
import os
from datetime import datetime, timezone

from zcrm import paths

MAX_BYTES = 1024 * 1024
KEEP = 3


def strip_query(path: str) -> str:
    base, _, query = path.partition("?")
    if not query:
        return base
    keys = [pair.split("=", 1)[0] for pair in query.split("&") if pair]
    return base + "?" + "&".join(f"{k}=*" for k in keys)


def _rotate(file) -> None:
    try:
        if file.stat().st_size < MAX_BYTES:
            return
    except OSError:
        return
    oldest = file.with_name(f"{file.name}.{KEEP}")
    if oldest.exists():
        oldest.unlink()
    for i in range(KEEP - 1, 0, -1):
        src = file.with_name(f"{file.name}.{i}")
        if src.exists():
            os.replace(src, file.with_name(f"{file.name}.{i + 1}"))
    os.replace(file, file.with_name(f"{file.name}.1"))


def log_call(profile, method, path, status, outcome, run_id=None, step_id=None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile": profile,
        "method": method,
        "path": strip_query(path),
        "status": status,
        "outcome": outcome,
    }
    if run_id:
        entry["run_id"] = run_id
    if step_id:
        entry["step_id"] = step_id
    file = paths.audit_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    _rotate(file)
    with open(file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def read_entries(profile=None, last=None) -> list:
    file = paths.audit_file()
    files = [file.with_name(f"{file.name}.{i}") for i in range(KEEP, 0, -1)] + [file]
    entries = []
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if profile and entry.get("profile") != profile:
                continue
            entries.append(entry)
    return entries[-last:] if last else entries
