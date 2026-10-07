"""`zcrm init`: prerequisites, skill, settings merge, config, wizard, doctor, test call."""

import shutil
import sys

from zcrm import __version__, client, paths, profiles, scopes, secrets, ui
from zcrm.lifecycle import banner, doctor, install_info, settings, setup, skillfiles
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


def _fail_lines(problems) -> list:
    out = []
    for message, fix in problems:
        out.append(f"  FAIL: {message}\n        Fix: {fix}")
    return out


def run() -> int:
    ui.say(banner.logo())
    ui.say("")
    ui.say(banner.tagline())
    ui.say("")
    ui.say(
        banner.box(
            "zcrm Setup",
            [
                banner.kv("Version", __version__),
                banner.kv("Skill path", str(paths.skill_dir())),
                banner.kv("Config path", str(paths.config_dir())),
                banner.kv("Claude settings", str(paths.settings_file())),
            ],
            36,
        )
    )
    ui.say(banner.heading("Initialize zcrm"))

    problems = check_prerequisites()
    if problems:
        ui.say(banner.step("Check prerequisites", "failed", last=True, ok=False))
        for line in _fail_lines(problems):
            ui.say(line)
        ui.say("Nothing was changed. Fix the items above and rerun `zcrm init`.")
        return EXIT_CREDENTIAL
    ui.say(banner.step("Check prerequisites", "ok"))
    ensure_persistent()

    state = skillfiles.install()
    ui.say(banner.step("Install Claude skill", f"{state}, {paths.skill_dir()}"))

    def consent(rule: str) -> bool:
        ui.say(f"Your Claude settings already contain the rule {rule!r}, which would auto-approve zcrm writes.")
        return ui.confirm("Remove it so writes always ask for approval?")

    merged = settings.apply(consent)
    if merged["changed"]:
        detail = f"+{len(merged['added']['allow'])} allow, +{len(merged['added']['ask'])} ask"
        if merged["backup"]:
            detail += f", backup: {merged['backup']}"
        ui.say(banner.step("Merge permission rules", detail))
    else:
        ui.say(banner.step("Merge permission rules", "already in place"))
    for rule in merged["declined"]:
        ui.say(banner.c(f"WARNING: {rule!r} still auto-approves zcrm writes. `zcrm doctor` will report this until you remove it.", 33))

    created = profiles.ensure_file()
    ui.say(banner.step("Create config folder", "created" if created else "already there"))

    existing = profiles.load_profiles()
    if not existing:
        ui.say(
            banner.box(
                "Add your first profile",
                [
                    "Step 1  Pick a profile name and your Zoho data center",
                    "Step 2  Create a Self Client in the Zoho API Console",
                    "Step 3  Paste your credentials (hidden, stored in your keyring)",
                ],
                33,
            )
        )
        name = ui.ask("Name for your first profile", "demo1")
        setup.run(name)
    elif ui.confirm("Add another profile?"):
        setup.run(ui.ask("Name for the new profile"))
    ui.say(banner.step("Add profile", "ok" if profiles.load_profiles() else "none yet"))

    checks = doctor.run_checks()
    failed = [c for c in checks if not c["ok"]]
    if failed:
        ui.say(banner.step("Health check", f"{len(failed)} problem(s)", last=True, ok=False))
        for c in failed:
            ui.say(f"  FAIL {c['name']}: {c['detail']}\n        Fix: {c.get('fix', '')}")
        ui.say("Not ready: fix the items above, then run `zcrm doctor`.")
        return EXIT_CREDENTIAL
    ui.say(banner.step("Health check", f"{len(checks)} checks passed"))

    profile = next(iter(profiles.load_profiles().values()))
    try:
        resp = client.request(profile, "GET", "/org")
    except ZcrmError as exc:
        scope_hint = "" if scopes.check(profile.scopes, "GET", "/org")[0] == "ok" else " The profile may lack ZohoCRM.org.READ."
        ui.say(banner.step("Test call", "failed", last=True, ok=False))
        ui.say(f"Not ready: the test call failed: {exc.message}{scope_hint}")
        return EXIT_CREDENTIAL
    org = (resp.data or {}).get("org", [{}])[0] if isinstance(resp.data, dict) else {}
    ui.say(banner.step("Test call", f"GET /org on '{profile.name}'"))
    ui.say(banner.step("Finalize", "ready", last=True))
    ui.say("")
    ui.say(banner.c(f"Ready: profile '{profile.name}' reached org '{org.get('company_name', '?')}' (id {org.get('id', '?')}). Ask Claude to use the zcrm-api skill.", "1;32"))
    ui.say("")
    ui.say(
        banner.box(
            "Next Steps",
            [
                "1. Open Claude Code in any folder",
                f"2. Ask: {banner.c(chr(34) + 'List the modules in my ' + profile.name + ' org' + chr(34), 36)}",
                "3. Reads run instantly; creates, updates and deletes show the request and wait for your yes",
                f"4. Add another org: {banner.c('zcrm setup <name>', 36)}   Check health: {banner.c('zcrm doctor', 36)}",
            ],
            36,
        )
    )
    return EXIT_OK
