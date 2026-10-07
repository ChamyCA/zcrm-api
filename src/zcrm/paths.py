"""Filesystem locations. Evaluated at call time so tests can redirect HOME / ZCRM_HOME."""

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("ZCRM_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "zcrm"
    return Path.home() / ".config" / "zcrm"


def profiles_file() -> Path:
    return config_dir() / "profiles.yaml"


def manifest_file() -> Path:
    return config_dir() / "install-manifest.json"


def runs_dir() -> Path:
    return config_dir() / "runs"


def audit_file() -> Path:
    return config_dir() / "audit.log"


def claude_dir() -> Path:
    return Path.home() / ".claude"


def skill_dir() -> Path:
    return claude_dir() / "skills" / "zcrm-api"


def settings_file() -> Path:
    return claude_dir() / "settings.json"


def packaged_skill_dir() -> Path:
    return Path(__file__).parent / "skill"
