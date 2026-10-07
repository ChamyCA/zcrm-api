"""Plan pre-flight: scopes, org match and prose flags (credentials are scanned earlier)."""

from zcrm import client, scopes
from zcrm.output import EXIT_PLAN, ZcrmError
from zcrm.plan import scan
from zcrm.plan.util import VAR_RE


def run(profile, plan, text: str) -> dict:
    errors, warnings = [], []
    flags = scan.find_injection(text)
    checked = [("GET", "/org", "pre-flight org check")]
    checked += [(s.method, VAR_RE.sub("x", s.path.split("?", 1)[0]), s.id) for s in plan.steps]
    for method, path, label in checked:
        state, needed = scopes.check(profile.scopes, method, path)
        if state == "missing":
            errors.append({"code": "scope_insufficient", "step": label, "message": f"Profile {profile.name!r} lacks scope {needed}."})
        elif state == "unknown":
            warnings.append(f"Step {label}: scope for {method} {path} is unknown, so it was not checked.")
    actual = None
    if not errors:
        resp = client.request(profile, "GET", "/org")
        try:
            actual = str(resp.data["org"][0]["id"])
        except (KeyError, IndexError, TypeError):
            actual = None
        if actual is None:
            errors.append({"code": "plan_org_mismatch", "message": "Could not read the org ID for this profile."})
        elif actual != plan.org_id:
            errors.append(
                {
                    "code": "plan_org_mismatch",
                    "message": f"The plan targets org {plan.org_id} but profile {profile.name!r} is org {actual}.",
                }
            )
    if errors:
        code = errors[0]["code"] if len({e["code"] for e in errors}) == 1 else "preflight_failed"
        raise ZcrmError(
            code,
            errors[0]["message"] if len(errors) == 1 else f"{len(errors)} pre-flight problems.",
            fix="Use the profile for the org named in the plan, or fix the plan header or profile scopes.",
            exit_code=EXIT_PLAN,
            errors=errors,
            flags=flags,
        )
    return {"org_id": actual, "warnings": warnings, "flags": flags}
