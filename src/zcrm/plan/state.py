"""Per-run state files (no secrets) and run locks."""

import contextlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from zcrm import paths
from zcrm.output import EXIT_PLAN, ZcrmError

STALE_LOCK_SECONDS = 6 * 3600
DONE = ("done", "skipped")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunState:
    def __init__(self, path, data, persist=True):
        self.path, self.data, self.persist = path, data, persist

    @property
    def run_id(self):
        return self.data["run_id"]

    @property
    def variables(self) -> dict:
        return self.data["variables"]

    def status(self, sid: str) -> str:
        return self.data["steps"].get(sid, {}).get("status", "pending")

    def response_id(self, sid: str):
        return self.data["steps"].get(sid, {}).get("response_id")

    def set(self, sid: str, status: str, response_id=None) -> None:
        entry = {"status": status, "ts": _now()}
        keep = response_id or self.data["steps"].get(sid, {}).get("response_id")
        if keep:
            entry["response_id"] = keep
        self.data["steps"][sid] = entry
        self.save()

    def save(self) -> None:
        if not self.persist:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def complete(self) -> bool:
        return all(self.status(sid) in DONE for sid in self.data["steps"])


def _new(plan, profile: str, plan_path: Path, persist: bool) -> RunState:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{random.randrange(16**4):04x}"
    data = {
        "version": 1,
        "plan_sha256": plan.sha256,
        "plan_path": str(plan_path),
        "profile": profile,
        "run_id": run_id,
        "started": _now(),
        "steps": {s.id: {"status": "pending"} for s in plan.steps},
        "variables": {},
    }
    path = paths.runs_dir() / f"{plan.sha256[:8]}-{profile}-{run_id}.json"
    state = RunState(path, data, persist)
    state.save()
    return state


def _existing(profile: str, plan_path: Path) -> list:
    found = []
    folder = paths.runs_dir()
    if folder.exists():
        for file in folder.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if data.get("profile") == profile and data.get("plan_path") == str(plan_path):
                found.append((data.get("started", ""), file, data))
    return [(f, d) for _, f, d in sorted(found, key=lambda t: t[0])]


def resolve(plan, profile: str, plan_path: Path, fresh: bool, from_step_given: bool, persist: bool) -> RunState:
    plan_path = Path(plan_path).resolve()
    if fresh:
        return _new(plan, profile, plan_path, persist)
    candidates = _existing(profile, plan_path)
    same = [(f, d) for f, d in candidates if d.get("plan_sha256") == plan.sha256]
    if same:
        file, data = same[-1]
        for s in plan.steps:
            data["steps"].setdefault(s.id, {"status": "pending"})
        return RunState(file, data, persist)
    if candidates and not from_step_given:
        _, latest = candidates[-1]
        incomplete = any(v.get("status") not in DONE for v in latest["steps"].values())
        if incomplete:
            raise ZcrmError(
                "plan_changed_since_state",
                "This plan changed since its last partial run, so automatic resume was refused.",
                fix="Use --fresh to start a new run, or --from-step <id> to continue from a step.",
                exit_code=EXIT_PLAN,
            )
    return _new(plan, profile, plan_path, persist)


def _pid_alive(pid: int):
    if sys.platform == "win32":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def lock(plan_hash8: str, profile: str):
    folder = paths.runs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{plan_hash8}-{profile}.lock"
    for attempt in range(2):
        try:
            fd = os.open(file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                pid = int(file.read_text() or 0)
            except (ValueError, OSError):
                pid = 0
            age = time.time() - file.stat().st_mtime if file.exists() else 0
            alive = _pid_alive(pid) if pid else False
            stale = alive is False or age > STALE_LOCK_SECONDS
            if stale and attempt == 0:
                with contextlib.suppress(OSError):
                    file.unlink()
                continue
            raise ZcrmError(
                "run_locked",
                "Another run of this plan on this profile is in progress.",
                fix="Wait for it to finish. If it crashed, delete the .lock file in the runs folder.",
                exit_code=EXIT_PLAN,
            )
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            file.unlink()
