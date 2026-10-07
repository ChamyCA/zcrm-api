"""Plan execution: discovery reads, approved writes, capture, resume and verification."""

from contextlib import ExitStack
from pathlib import Path

from zcrm import client, policy, profiles
from zcrm.output import EXIT_APPROVAL, EXIT_OK, EXIT_PLAN, EXIT_REFUSED, EXIT_STOPPED, EXIT_USAGE, ZcrmError
from zcrm.plan import parser, preflight, report, scan, state as state_mod
from zcrm.plan.util import MISSING, find_id, jpath, substitute

NAME_KEYS = ("api_name", "singular_label", "plural_label", "field_label", "display_label", "name")
SAFE_TYPES = (str, int, float, bool)


class _Stop(Exception):
    def __init__(self, code, message, step_id=None):
        super().__init__(message)
        self.code, self.message, self.step_id = code, message, step_id


def _usage(code, message):
    return ZcrmError(code, message, exit_code=EXIT_USAGE)


def _late_ids(plan) -> set:
    """Steps that belong to the write phase: writes, and reads that depend on one."""
    late = set()
    for step in plan.steps:
        if step.kind != "read" or any(d in late for d in step.depends_on):
            late.add(step.id)
    return late


def _names(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in NAME_KEYS and isinstance(value, str):
                out.append(value)
            _names(value, out)
    elif isinstance(node, list):
        for value in node:
            _names(value, out)
    return out


def _discovery_report(responses, plan, late):
    modules, layouts, field_names = set(), set(), set()
    known = set()
    for data in responses.values():
        if not isinstance(data, dict):
            continue
        for m in data.get("modules", []) if isinstance(data.get("modules"), list) else []:
            if isinstance(m, dict) and m.get("api_name"):
                modules.add(m["api_name"])
        for f in data.get("fields", []) if isinstance(data.get("fields"), list) else []:
            if isinstance(f, dict) and f.get("api_name"):
                field_names.add(f["api_name"])
        for lay in data.get("layouts", []) if isinstance(data.get("layouts"), list) else []:
            if isinstance(lay, dict) and lay.get("name"):
                layouts.add(lay["name"])
        known.update(n.lower() for n in _names(data, []))
    conflicts, planned = [], {}
    for step in plan.steps:
        if step.id in late and step.kind == "create" and step.body:
            for name in _names(step.body, []):
                low = name.lower()
                if "{{" in name:
                    continue
                if low in known:
                    conflicts.append({"step": step.id, "name": name, "problem": "already exists in the org"})
                if low in planned and planned[low] != step.id:
                    conflicts.append({"step": step.id, "name": name, "problem": f"also created by step {planned[low]}"})
                planned.setdefault(low, step.id)
    return {
        "modules": sorted(modules),
        "field_count": len(field_names),
        "fields": sorted(field_names)[:200],
        "layouts": sorted(layouts),
    }, conflicts


def _resolve_position(plan, value):
    if value is None:
        return 0
    ids = [s.id for s in plan.steps]
    if value in ids:
        return ids.index(value)
    if value.isdigit() and 1 <= int(value) <= len(ids):
        return int(value) - 1
    raise _usage("step_unknown", f"--from-step {value!r} is not a step id or position in this plan.")


def _check_ids(plan, ids, label, kinds=None):
    known = {s.id: s for s in plan.steps}
    for sid in ids:
        if sid not in known:
            raise _usage("step_unknown", f"{label}: {sid!r} is not a step in this plan.")
        if kinds is not None and known[sid].kind not in kinds:
            raise _usage("step_not_write", f"{label}: step {sid!r} is a read and needs no approval.")


def run_plan(profile_name, plan_path, *, dry_run=False, only_reads=False, fresh=False, from_step=None, approve_steps=(), skip_steps=()):
    profile = profiles.require_demo(profiles.get(profile_name))
    path = Path(plan_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise ZcrmError("plan_parse_error", f"Cannot read plan file {str(plan_path)!r}.", exit_code=EXIT_PLAN)
    hits = scan.find_credentials(text)
    if hits:
        raise ZcrmError(
            "plan_credential_found",
            f"The plan appears to contain {len(hits)} credential(s) and was refused. The values are not shown.",
            fix="Remove credentials from the plan. If they are real, revoke them in the Zoho API Console and re-enter with `zcrm setup <profile>`.",
            exit_code=EXIT_PLAN,
            locations=[{"line": line, "kind": kind} for line, kind in hits],
        )
    plan = parser.parse(text)
    approve_steps, skip_steps = list(dict.fromkeys(approve_steps)), list(dict.fromkeys(skip_steps))
    _check_ids(plan, approve_steps, "--approve-steps", kinds={"create", "update", "delete"})
    _check_ids(plan, skip_steps, "--skip-step", kinds={"create", "update", "delete"})
    kinds = {s.id: s.kind for s in plan.steps}
    if len(approve_steps) > 1 and any(kinds[s] == "delete" for s in approve_steps):
        raise ZcrmError(
            "delete_not_batchable",
            "Deletes can never be batch-approved. Approve and run each delete step on its own.",
            exit_code=EXIT_REFUSED,
        )
    start = _resolve_position(plan, from_step)
    pf = preflight.run(profile, plan, text)
    persist = not dry_run
    run_state = state_mod.resolve(plan, profile_name, path, fresh, from_step is not None, persist)
    with ExitStack() as stack:
        if persist:
            stack.enter_context(state_mod.lock(plan.sha256[:8], profile_name))
        return _execute(profile, plan, run_state, pf, dry_run, only_reads, start, approve_steps, skip_steps)


def _execute(profile, plan, st, pf, dry_run, only_reads, start, approve_steps, skip_steps):
    late = _late_ids(plan)
    ctx = {"run_id": st.run_id}
    warnings = list(pf["warnings"])
    responses = {}

    def deps_ok(step):
        return all(st.status(d) in state_mod.DONE for d in step.depends_on)

    def send(step, method, path, body):
        return client.request(profile, method, path, body, ctx={**ctx, "step_id": step.id})

    def capture(step, data):
        for var, expr in step.capture.items():
            value = jpath(data, expr)
            if value is MISSING or not isinstance(value, SAFE_TYPES):
                warnings.append(f"Step {step.id}: capture {var!r} found no usable value at {expr!r}.")
                continue
            if scan.find_credentials(f"{var}: {value}"):
                raise _Stop("captured_secret", f"Step {step.id}: captured value for {var!r} looks like a credential and was not stored.", step.id)
            st.variables[var] = value
        st.save()

    def run_read(step):
        try:
            method, path = step.method, substitute(step.path, st.variables)
            body = substitute(step.body, st.variables) if step.body else None
        except KeyError as exc:
            st.set(step.id, "failed")
            warnings.append(f"Step {step.id}: variable {exc.args[0]!r} is not available.")
            return False
        try:
            resp = send(step, method, path, body)
        except ZcrmError as exc:
            st.set(step.id, "failed")
            warnings.append(f"Step {step.id}: read failed ({exc.code}).")
            return False
        responses[step.id] = resp.data
        st.set(step.id, "done")
        capture(step, resp.data)
        return True

    # --- apply skips chosen by the user
    for sid in skip_steps:
        st.set(sid, "skipped")

    # --- discovery reads (every invocation; safe to repeat)
    for step in plan.steps:
        if step.id in late or step.position - 1 < start:
            continue
        if not deps_ok(step):
            warnings.append(f"Step {step.id}: skipped because a dependency is not done.")
            continue
        run_read(step)

    discovery, conflicts = _discovery_report(responses, plan, late)
    base = {"profile": profile.name, "preflight": {"org_id": pf["org_id"], "warnings": pf["warnings"]}, "flags": pf["flags"], "discovery": discovery, "conflicts": conflicts}

    write_steps = [s for s in plan.steps if s.id in late and s.position - 1 >= start]

    if dry_run:
        previews = []
        for step in write_steps:
            if step.kind == "read":
                continue
            try:
                path = substitute(step.path, st.variables)
                body = substitute(step.body, st.variables) if step.body else None
                unresolved = []
            except KeyError:
                path, body, unresolved = step.path, step.body, True
            previews.append(
                {
                    "step": step.id,
                    "description": step.description,
                    "kind": step.kind,
                    "method": step.method,
                    "url": client.build_url(profile, path),
                    "body_summary": policy.body_summary(body),
                    "status": st.status(step.id),
                    **({"unresolved_variables": True} if unresolved else {}),
                }
            )
        env = {"ok": True, "mode": "dry_run", **base, "would_send": previews, "report": report.build(plan, st, warnings)}
        return env, EXIT_OK

    if only_reads:
        return {"ok": True, "mode": "only_reads", **base, "report": report.build(plan, st, warnings)}, EXIT_OK

    # --- verify steps whose outcome was lost in an interruption
    for step in write_steps:
        if st.status(step.id) == "unknown" and step.verify:
            _verify(profile, step, st, send, warnings)

    approve = set(approve_steps)
    pending = []
    stop = None
    try:
        for step in write_steps:
            status = st.status(step.id)
            if step.kind == "read":
                if deps_ok(step):
                    run_read(step)
                else:
                    warnings.append(f"Step {step.id}: waiting on a dependency.")
                continue
            if status in state_mod.DONE:
                continue
            if step.id in approve:
                if not deps_ok(step):
                    raise _Stop("dependency_not_done", f"Step {step.id} depends on a step that is not done.", step.id)
                _write(profile, step, st, send, capture, warnings)
                continue
            if status in ("failed", "unknown"):
                raise _Stop(
                    "step_outcome_unknown" if status == "unknown" else "step_failed",
                    f"Step {step.id} is {status} and needs a decision before later steps run.",
                    step.id,
                )
            pending.append(step.id)
    except _Stop as exc:
        stop = exc

    env_base = {**base}
    rep = report.build(plan, st, warnings)
    if stop:
        error = {
            "code": stop.code,
            "message": stop.message,
            "fix": "Options: retry (rerun with --approve-steps <id>), skip (--skip-step <id>), or abort (stop here).",
        }
        return {"ok": False, "error": error, "stopped_at": stop.step_id, "options": ["retry", "skip", "abort"], **env_base, "report": rep}, EXIT_STOPPED

    remaining = [s for s in write_steps if s.kind != "read" and st.status(s.id) not in state_mod.DONE]
    if remaining and not approve_steps:
        listing = [
            {"step": s.id, "kind": s.kind, "method": s.method, "url": client.build_url(profile, s.path), "description": s.description}
            for s in remaining
        ]
        err = {
            "code": "approval_required",
            "message": "No writes were sent. Show these requests to the user and rerun with --approve-steps for the steps they approve.",
        }
        return {"ok": False, "error": err, **env_base, "pending_writes": listing, "report": rep}, EXIT_APPROVAL
    return {"ok": True, "mode": "run", **env_base, "pending": pending, "report": rep}, EXIT_OK


def _verify(profile, step, st, send, warnings):
    try:
        path = substitute(step.verify["path"], st.variables)
    except KeyError:
        return
    match = step.verify["match"]
    try:
        resp = send(step, "GET", path, None)
    except ZcrmError as exc:
        status = exc.extra.get("status")
        if "status" in match and status == match["status"]:
            st.set(step.id, "done")
            warnings.append(f"Step {step.id}: confirmed by lookup after an interruption.")
        else:
            st.set(step.id, "pending")
            warnings.append(f"Step {step.id}: not found after an interruption; it can be retried with approval.")
        return
    found = False
    if "path" in match:
        value = jpath(resp.data, match["path"])
        found = value is not MISSING and value not in (None, "", [], {}) and ("equals" not in match or value == match["equals"])
    elif "status" in match:
        found = resp.status == match["status"]
    if found:
        st.set(step.id, "done")
        warnings.append(f"Step {step.id}: confirmed by lookup after an interruption; not repeated.")
    else:
        st.set(step.id, "pending")
        warnings.append(f"Step {step.id}: not found after an interruption; it can be retried with approval.")


def _write(profile, step, st, send, capture, warnings):
    try:
        path = substitute(step.path, st.variables)
        body = substitute(step.body, st.variables) if step.body else None
    except KeyError as exc:
        st.set(step.id, "failed")
        raise _Stop("variable_unresolved", f"Step {step.id}: variable {exc.args[0]!r} has no value.", step.id)
    st.set(step.id, "unknown")  # write-ahead: an interruption leaves this marker
    try:
        resp = send(step, step.method, path, body)
    except ZcrmError as exc:
        status = exc.extra.get("status")
        definitive = isinstance(status, int) and status < 500
        st.set(step.id, "failed" if definitive else "unknown")
        raise _Stop(
            "step_failed" if definitive else "step_outcome_unknown",
            f"Step {step.id} did not complete: {exc.message}",
            step.id,
        )
    errors = client.embedded_errors(resp.data)
    if errors:
        st.set(step.id, "failed")
        detail = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errors[:3])
        raise _Stop("step_failed", f"Step {step.id}: Zoho reported {detail}", step.id)
    rid = find_id(resp.data)
    if rid and scan.find_credentials(f"id: {rid}"):
        rid = None  # never persist anything credential-shaped, even as an ID
    st.set(step.id, "done", response_id=rid)
    capture(step, resp.data)
