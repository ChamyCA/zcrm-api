"""Health checks. Each check reports pass/fail with a fix; exits non-zero on any failure."""

import shutil
import sys

from zcrm import __version__, auth, paths, profiles, secrets
from zcrm.lifecycle import settings, skillfiles
from zcrm.output import ZcrmError
from zcrm.plan import scan


def _check(name, ok, detail, fix=None) -> dict:
    out = {"name": name, "ok": bool(ok), "detail": detail}
    if not ok and fix:
        out["fix"] = fix
    return out


def _config_secret_check(loaded_profiles) -> dict:
    root = paths.config_dir()
    exact = []
    for name in loaded_profiles:
        try:
            exact.extend(secrets.load_credentials(name).values())
        except ZcrmError:
            pass
    bad = []
    if root.exists():
        for file in root.rglob("*"):
            if not file.is_file():
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            if scan.find_credentials(text) or any(value in text for value in exact):
                bad.append(file.name)
    return _check(
        "no_secrets_in_config",
        not bad,
        "no secrets found in config files" if not bad else "secret-like content found in: " + ", ".join(sorted(set(bad))),
        "Remove the secret from that file, rotate it in the Zoho API Console and run `zcrm setup <profile>` in your own terminal.",
    )


def run_checks() -> list:
    checks = [
        _check("python", sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Install Python 3.10 or newer."),
    ]
    try:
        secrets.probe()
        checks.append(_check("keyring", True, "OS keyring read/write works"))
    except ZcrmError as exc:
        checks.append(_check("keyring", False, exc.message, exc.fix))
    checks.append(
        _check("zcrm_on_path", shutil.which("zcrm") is not None, "zcrm is on PATH", "Install with `pipx install` or `uv tool install` so the `zcrm` command stays on PATH.")
    )
    version = skillfiles.installed_version()
    checks.append(
        _check(
            "skill_present",
            version == __version__,
            f"skill version {version}" if version else "skill not installed",
            "Run `zcrm init` in your own terminal.",
        )
    )
    try:
        missing = settings.rules_present()
        absent = missing["allow_missing"] + missing["ask_missing"]
        checks.append(
            _check("permission_rules", not absent, "permission rules present" if not absent else f"{len(absent)} rule(s) missing", "Run `zcrm init` in your own terminal.")
        )
        conflicts = settings.conflicting_rules(settings.load())
        checks.append(
            _check(
                "no_conflicting_rules",
                not conflicts,
                "no rule auto-allows zcrm writes" if not conflicts else "rule(s) auto-allow zcrm writes: " + ", ".join(conflicts),
                "Remove those rules from ~/.claude/settings.json (or rerun `zcrm init` and answer yes to removal).",
            )
        )
    except ZcrmError as exc:
        checks.append(_check("permission_rules", False, exc.message, exc.fix))
    try:
        loaded = profiles.load_profiles()
    except ZcrmError as exc:
        checks.append(_check("profiles", False, exc.message, exc.fix))
        loaded = {}
    else:
        if not loaded:
            checks.append(_check("profiles", False, "no profiles configured", "Run `zcrm setup <profile>` in your own terminal."))
    checks.append(_config_secret_check(loaded))
    for name, profile in loaded.items():
        label = f"profile:{name}"
        if profile.type != "demo":
            checks.append(_check(label, False, f"type is {profile.type!r}; only demo is supported", "Use a demo profile."))
            continue
        if not secrets.has_credentials(name):
            checks.append(_check(label, False, "credentials missing", f"Run `zcrm setup {name}` in your own terminal."))
            continue
        try:
            auth.get_access_token(profile, force=True)
            checks.append(_check(label, True, "token refresh works"))
        except ZcrmError as exc:
            checks.append(_check(label, False, exc.message, exc.fix))
    return checks
