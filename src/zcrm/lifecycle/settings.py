"""Merge zcrm permission rules into ~/.claude/settings.json (backup first, never overwrite)."""

import copy
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from zcrm import __version__, paths
from zcrm.output import EXIT_CREDENTIAL, ZcrmError

ALLOW_RULES = [
    "Bash(zcrm profiles)",
    "Bash(zcrm doctor)",
    "Bash(zcrm log *)",
    "Bash(zcrm --version)",
    "Bash(zcrm * GET *)",
    "Bash(zcrm * COQL *)",
    "Bash(zcrm run * --dry-run)",
    "Bash(zcrm run * --only-reads)",
]
ASK_RULES = [
    "Bash(zcrm * POST *)",
    "Bash(zcrm * PUT *)",
    "Bash(zcrm * PATCH *)",
    "Bash(zcrm * DELETE *)",
    "Bash(zcrm run * --approve-steps *)",
    "Bash(zcrm run * --skip-step *)",
]
_WRITE_SAMPLES = [
    "zcrm demo POST /Leads",
    "zcrm demo PUT /Leads/1",
    "zcrm demo PATCH /Leads/1",
    "zcrm demo DELETE /Leads/1",
    "zcrm run demo plan.md --approve-steps s1",
]


def rule_matches(rule: str, command: str) -> bool:
    if rule == "Bash":
        return True
    m = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    if not m:
        return False
    pattern = m.group(1)
    if pattern.endswith(":*"):
        prefix = pattern[:-2]
        return command == prefix or command.startswith(prefix + " ")
    regex = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$"
    return re.match(regex, command) is not None


def conflicting_rules(settings) -> list:
    allow = (settings or {}).get("permissions", {}).get("allow", [])
    if not isinstance(allow, list):
        return []
    return [
        rule
        for rule in allow
        if isinstance(rule, str)
        and rule not in ALLOW_RULES
        and any(rule_matches(rule, sample) for sample in _WRITE_SAMPLES)
    ]


def load(path=None):
    """Return the parsed settings, {} for an empty file, or None when the file is missing."""
    path = Path(path or paths.settings_file())
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        raise ZcrmError(
            "settings_invalid",
            f"{path} is not valid JSON, so it was left untouched.",
            fix="Fix or remove the file, then rerun `zcrm init`.",
            exit_code=EXIT_CREDENTIAL,
        )
    if not isinstance(data, dict):
        raise ZcrmError("settings_invalid", f"{path} must contain a JSON object.", exit_code=EXIT_CREDENTIAL)
    return data


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def backup(path: Path):
    if not path.exists() or path.stat().st_size == 0:
        return None
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    target = path.with_name(f"{path.name}.zcrm-backup-{stamp}")
    n = 1
    while target.exists():
        target = path.with_name(f"{path.name}.zcrm-backup-{stamp}-{n}")
        n += 1
    target.write_bytes(path.read_bytes())
    return target


def load_manifest() -> dict:
    file = paths.manifest_file()
    base = {
        "version": 1,
        "zcrm_version": __version__,
        "skill_path": str(paths.skill_dir()),
        "settings_path": str(paths.settings_file()),
        "settings_backups": [],
        "rules_added": {"allow": [], "ask": []},
        "rules_removed_by_user_consent": [],
    }
    if file.exists():
        try:
            base.update(json.loads(file.read_text(encoding="utf-8")))
        except ValueError:
            pass
    return base


def save_manifest(manifest: dict) -> None:
    file = paths.manifest_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    manifest["zcrm_version"] = __version__
    file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _perms(settings: dict) -> dict:
    perms = settings.setdefault("permissions", {})
    if not isinstance(perms, dict):
        raise ZcrmError("settings_invalid", "settings.json 'permissions' must be an object.", exit_code=EXIT_CREDENTIAL)
    for key in ("allow", "ask"):
        value = perms.setdefault(key, [])
        if not isinstance(value, list):
            raise ZcrmError("settings_invalid", f"settings.json permissions.{key} must be a list.", exit_code=EXIT_CREDENTIAL)
    return perms


def apply(consent) -> dict:
    """Merge rules. `consent(rule) -> bool` decides whether to remove a conflicting allow rule."""
    path = paths.settings_file()
    existing = load(path)
    settings = copy.deepcopy(existing) if existing is not None else {}
    conflicts = conflicting_rules(settings)
    perms = _perms(settings)
    removed, declined = [], []
    for rule in conflicts:
        if consent(rule):
            perms["allow"] = [r for r in perms["allow"] if r != rule]
            removed.append(rule)
        else:
            declined.append(rule)
    added_allow = [r for r in ALLOW_RULES if r not in perms["allow"]]
    added_ask = [r for r in ASK_RULES if r not in perms["ask"]]
    perms["allow"].extend(added_allow)
    perms["ask"].extend(added_ask)
    changed = bool(added_allow or added_ask or removed)
    result = {"changed": changed, "added": {"allow": added_allow, "ask": added_ask}, "removed": removed, "declined": declined, "backup": None}
    if not changed:
        return result
    made = backup(path)
    _write_atomic(path, settings)
    manifest = load_manifest()
    if made:
        manifest["settings_backups"].append(str(made))
        result["backup"] = str(made)
    for key, items in (("allow", added_allow), ("ask", added_ask)):
        for rule in items:
            if rule not in manifest["rules_added"][key]:
                manifest["rules_added"][key].append(rule)
    for rule in removed:
        if rule not in manifest["rules_removed_by_user_consent"]:
            manifest["rules_removed_by_user_consent"].append(rule)
    save_manifest(manifest)
    return result


def rules_present() -> dict:
    settings = load() or {}
    perms = settings.get("permissions", {}) if isinstance(settings.get("permissions"), dict) else {}
    allow, ask = perms.get("allow", []), perms.get("ask", [])
    return {
        "allow_missing": [r for r in ALLOW_RULES if r not in allow],
        "ask_missing": [r for r in ASK_RULES if r not in ask],
    }


def remove_added(manifest: dict) -> list:
    """Remove exactly the rules init added. Returns the rules removed."""
    path = paths.settings_file()
    settings = load(path)
    if not settings:
        return []
    perms = settings.get("permissions")
    if not isinstance(perms, dict):
        return []
    removed = []
    for key in ("allow", "ask"):
        current = perms.get(key)
        if not isinstance(current, list):
            continue
        mine = set(manifest.get("rules_added", {}).get(key, []))
        kept = [r for r in current if r not in mine]
        removed.extend(r for r in current if r in mine)
        if kept:
            perms[key] = kept
        else:
            del perms[key]
    if not removed:
        return []
    if not perms:
        del settings["permissions"]
    made = backup(path)
    if made:
        manifest.setdefault("settings_backups", []).append(str(made))
    _write_atomic(path, settings)
    return removed
