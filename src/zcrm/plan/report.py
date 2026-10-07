"""Final run report."""

from zcrm.plan.state import DONE


def build(plan, state, extra_warnings=None) -> dict:
    by = {"completed": [], "skipped": [], "failed": [], "pending": [], "unknown": []}
    created = []
    for step in plan.steps:
        status = state.status(step.id)
        key = {"done": "completed", "skipped": "skipped", "failed": "failed", "unknown": "unknown"}.get(status, "pending")
        by[key].append(step.id)
        if status == "done" and step.kind == "create" and state.response_id(step.id):
            created.append({"step": step.id, "id": state.response_id(step.id)})
    report = dict(by)
    report["created_record_ids"] = created
    report["run_id"] = state.run_id
    report["finished"] = all(state.status(s.id) in DONE for s in plan.steps)
    if extra_warnings:
        report["warnings"] = extra_warnings
    return report
