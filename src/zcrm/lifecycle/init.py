"""`zcrm init`: prerequisites, skill, settings merge, config, wizard, doctor, test call."""

import shutil
import sys

from zcrm import client, paths, profiles, scopes, secrets, ui
from zcrm.lifecycle import doctor, install_info, settings, setup, skillfiles
from zcrm.output import EXIT_CREDENTIAL, EXIT_OK, ZcrmError


def check_prerequisites() -> list:
    problems = []
    if sys.version_info < (3, 10):
        problems.append(("Python 3.10 or newer is required.", "Install a newer Python (https://www.python.org/downloads/) and reinstall zcrm."))
    try:
        secrets.probe()
    except ZcrmError as exc:
        problems.append((exc.message, exc.fix))
    if not (shutil.which("claude") or paths.claude_dir().exists()):
        problems.append(
            (
                "Claude Code was not found.",
                "Install Claude Code (https://claude.com/claude-code), run it once, then rerun `zcrm init`.",
            )
        )
    return problems


def ensure_persistent() -> None:
    if shutil.which("zcrm"):
        return
    url, rev = install_info.source()
    ui.say("`zcrm` is not on your PATH (uvx runs are temporary), so the skill could not call it later.")
    if url and shutil.which("uv") and ui.confirm("Install it permanently with `uv tool install`?", default=True):
        spec = f"git+{url}" + (f"@{rev}" if rev else "")
        result = install_info.run(["uv", "tool", "install", "--force", "--from", spec, "zcrm-api"])
        if result.returncode == 0:
            ui.say("Installed. Make sure `uv tool dir --bin` is on your PATH.")
            return
        ui.say("uv tool install failed; install zcrm with pipx or `uv tool install` yourself.")
        return
    ui.say("Install it with `pipx install git+<repo>@<tag>` or `uv tool install --from git+<repo>@<tag> zcrm-api`.")


def run() -> int:
    ui.say("Checking prerequisites...")
    problems = check_prerequisites()
    if problems:
        for message, fix in problems:
            ui.say(f"  FAIL: {message}\n        Fix: {fix}")
        ui.say("Nothing was changed. Fix the items above and rerun `zcrm init`.")
        return EXIT_CREDENTIAL
    ensure_persistent()

    state = skillfiles.install()
    ui.say(f"Skill {state}: {paths.skill_dir()}")

    def consent(rule: str) -> bool:
        ui.say(f"Your Claude settings already contain the rule {rule!r}, which would auto-approve zcrm writes.")
        return ui.confirm("Remove it so writes always ask for approval?")

    merged = settings.apply(consent)
    if merged["changed"]:
        ui.say(
            f"Permission rules merged (+{len(merged['added']['allow'])} allow, +{len(merged['added']['ask'])} ask)."
            + (f" Backup: {merged['backup']}" if merged["backup"] else "")
        )
    else:
        ui.say("Permission rules already in place.")
    for rule in merged["declined"]:
        ui.say(f"WARNING: {rule!r} still auto-approves zcrm writes. `zcrm doctor` will report this until you remove it.")

    if profiles.ensure_file():
        ui.say(f"Created {paths.profiles_file()}")

    existing = profiles.load_profiles()
    if not existing:
        name = ui.ask("Name for your first profile", "demo1")
        setup.run(name)
    elif ui.confirm("Add another profile?"):
        setup.run(ui.ask("Name for the new profile"))

    checks = doctor.run_checks()
    failed = [c for c in checks if not c["ok"]]
    for c in checks:
        ui.say(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}" + ("" if c["ok"] else f"\n        Fix: {c.get('fix', '')}"))
    if failed:
        ui.say("Not ready: fix the items above, then run `zcrm doctor`.")
        return EXIT_CREDENTIAL

    profile = next(iter(profiles.load_profiles().values()))
    try:
        resp = client.request(profile, "GET", "/org")
        org = (resp.data or {}).get("org", [{}])[0] if isinstance(resp.data, dict) else {}
        ui.say(f"Ready: profile '{profile.name}' reached org '{org.get('company_name', '?')}' (id {org.get('id', '?')}). Ask Claude to use the zcrm-api skill.")
        return EXIT_OK
    except ZcrmError as exc:
        scope_hint = "" if scopes.check(profile.scopes, "GET", "/org")[0] == "ok" else " The profile may lack ZohoCRM.org.READ."
        ui.say(f"Not ready: the test call failed: {exc.message}{scope_hint}")
        return EXIT_CREDENTIAL
