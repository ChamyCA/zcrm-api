"""`zcrm uninstall`: remove the skill, init-added rules and config; offer keyring deletion."""

import shutil
from pathlib import Path

from zcrm import paths, profiles, secrets, ui
from zcrm.lifecycle import settings, skillfiles
from zcrm.output import EXIT_OK, ZcrmError


def run() -> int:
    manifest_present = paths.manifest_file().exists()
    anything = skillfiles.installed_version() or manifest_present or paths.config_dir().exists()
    if not anything:
        ui.say("Nothing to uninstall.")
        return EXIT_OK
    manifest = settings.load_manifest()
    ui.say("This removes:")
    ui.say(f"  - the skill at {paths.skill_dir()}")
    ui.say("  - the permission rules `zcrm init` added to your Claude settings (a backup is made first)")
    ui.say(f"  - zcrm's config folder {paths.config_dir()} (profiles, audit log, run history)")
    if not ui.confirm("Continue?"):
        ui.say("Nothing changed.")
        return EXIT_OK
    names = []
    try:
        names = list(profiles.load_profiles())
    except ZcrmError:
        pass
    removed_rules = settings.remove_added(manifest)
    skill_removed = skillfiles.remove()
    ui.say(f"Removed skill: {'yes' if skill_removed else 'was not present'}. Removed {len(removed_rules)} permission rule(s).")
    kept = []
    for name in names:
        if ui.confirm(f"Delete the stored credentials for profile '{name}' from your OS keyring?"):
            secrets.delete_profile(name)
        else:
            kept.append(name)
    backups = [Path(b) for b in manifest.get("settings_backups", []) if Path(b).exists()]
    if backups and ui.confirm(f"Also delete the {len(backups)} settings backup file(s) zcrm created?"):
        for b in backups:
            b.unlink()
        backups = []
    if paths.config_dir().exists():
        shutil.rmtree(paths.config_dir())
    if kept:
        ui.say("Keyring entries kept for: " + ", ".join(kept) + ". Remove them in your OS keychain manager if you want them gone.")
    if backups:
        ui.say("Settings backups kept: " + ", ".join(str(b) for b in backups))
    ui.say("Uninstalled. To remove the command itself run `pipx uninstall zcrm-api` (or `uv tool uninstall zcrm-api`).")
    return EXIT_OK
