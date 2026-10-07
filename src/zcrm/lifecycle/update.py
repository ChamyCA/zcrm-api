"""`zcrm update`: reinstall from the latest release tag, keeping config and keyring entries."""

import re
import shutil
import sys

from zcrm import __version__, ui
from zcrm.lifecycle import install_info, settings, skillfiles
from zcrm.output import EXIT_CREDENTIAL, EXIT_OK

_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(tag: str):
    m = _TAG.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def latest_tag(url: str):
    result = install_info.run(["git", "ls-remote", "--tags", "--refs", url])
    if result.returncode != 0:
        return None
    best = None
    for line in result.stdout.splitlines():
        ref = line.split("\t")[-1].strip()
        tag = ref.rsplit("/", 1)[-1]
        version = parse_version(tag)
        if version and (best is None or version > best[0]):
            best = (version, tag)
    return best[1] if best else None


def installer_command(spec: str) -> list:
    prefix = sys.prefix.lower()
    if "pipx" in prefix and shutil.which("pipx"):
        return ["pipx", "install", "--force", spec]
    if "uv" in prefix and "tools" in prefix and shutil.which("uv"):
        return ["uv", "tool", "install", "--force", "--from", spec, "zcrm-api"]
    return [sys.executable, "-m", "pip", "install", "--upgrade", spec]


def refresh() -> int:
    """Run by the newly installed version: refresh the skill and merge rules. Never removes rules."""
    state = skillfiles.install()
    merged = settings.apply(lambda rule: False)
    ui.say(f"Skill {state}. Permission rules {'updated' if merged['changed'] else 'already in place'}.")
    for rule in merged["declined"]:
        ui.say(f"WARNING: {rule!r} still auto-approves zcrm writes. Run `zcrm doctor`.")
    return EXIT_OK


def run() -> int:
    url, _ = install_info.source()
    if not url:
        ui.say("Cannot tell which repository zcrm was installed from. Set ZCRM_INSTALL_URL to the repo URL and retry.")
        return EXIT_CREDENTIAL
    tag = latest_tag(url)
    if not tag:
        ui.say("Could not read release tags (is git installed and the repository reachable?).")
        return EXIT_CREDENTIAL
    if parse_version(tag) <= parse_version(__version__):
        ui.say(f"Already up to date (zcrm {__version__}).")
        return EXIT_OK
    spec = f"git+{url}@{tag}"
    cmd = installer_command(spec)
    if sys.platform == "win32":
        ui.say(f"zcrm {tag} is available. Windows cannot replace a running zcrm.exe, so run these two commands yourself:")
        ui.say("  " + " ".join(cmd))
        ui.say("  zcrm _refresh")
        return EXIT_OK
    if not ui.confirm(f"Update zcrm from {__version__} to {tag}? Your profiles and stored credentials are kept."):
        ui.say("Nothing changed.")
        return EXIT_OK
    result = install_info.run(cmd)
    if result.returncode != 0:
        ui.say("The installer failed; zcrm was not changed.")
        return EXIT_CREDENTIAL
    result = install_info.run(["zcrm", "_refresh"])
    if result.stderr:
        ui.say(result.stderr.strip())
    ui.say(f"Updated to {tag}." if result.returncode == 0 else f"Updated to {tag}, but the skill refresh failed. Run `zcrm _refresh`.")
    return EXIT_OK if result.returncode == 0 else EXIT_CREDENTIAL
