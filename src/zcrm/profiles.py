"""Non-secret profile storage (profiles.yaml)."""

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from zcrm import datacenters, paths
from zcrm.output import EXIT_REFUSED, EXIT_USAGE, ZcrmError

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
VERSION_RE = re.compile(r"^v\d+(\.\d+)?$")
RESERVED = {"init", "update", "uninstall", "doctor", "setup", "profiles", "run", "log"}
_ALLOWED_KEYS = {"data_center", "api_version", "type", "scopes"}
_SECRET_KEY_RE = re.compile(r"(?i)(secret|token|password|client_id|api_key|apikey)")


@dataclass
class Profile:
    name: str
    data_center: str = ".com"
    api_version: str = "v8"
    type: str = "demo"
    scopes: list = field(default_factory=list)

    @property
    def dc(self):
        return datacenters.get(self.data_center)

    def public(self) -> dict:
        return {
            "name": self.name,
            "data_center": self.data_center,
            "api_version": self.api_version,
            "type": self.type,
            "scopes": list(self.scopes),
        }


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ZcrmError(
            "profile_invalid",
            f"Invalid profile name {name!r}.",
            fix="Use lowercase letters, digits and hyphens, starting with a letter or digit (max 40 characters).",
            exit_code=EXIT_USAGE,
        )
    if name in RESERVED:
        raise ZcrmError(
            "profile_invalid",
            f"{name!r} is a zcrm command word and cannot be a profile name.",
            fix="Pick a different profile name.",
            exit_code=EXIT_USAGE,
        )
    return name


def _build(name: str, raw) -> Profile:
    validate_name(name)
    if not isinstance(raw, dict):
        raise ZcrmError("profile_invalid", f"Profile {name!r} must be a mapping.", exit_code=EXIT_USAGE)
    for key in raw:
        if _SECRET_KEY_RE.search(str(key)):
            raise ZcrmError(
                "config_has_secret",
                f"Profile {name!r} has a secret-like key {key!r}. Secrets belong in the keyring only.",
                fix=f"Remove it from profiles.yaml and run `zcrm setup {name}` in your own terminal.",
                exit_code=EXIT_REFUSED,
            )
        if key not in _ALLOWED_KEYS:
            raise ZcrmError("profile_invalid", f"Profile {name!r} has unknown key {key!r}.", exit_code=EXIT_USAGE)
    dc = raw.get("data_center", ".com")
    if not isinstance(dc, str) or not datacenters.is_known(dc):
        raise ZcrmError(
            "profile_invalid",
            f"Profile {name!r} has an unknown data_center {dc!r}.",
            fix="Use one of: " + ", ".join(datacenters.suffixes()),
            exit_code=EXIT_USAGE,
        )
    version = str(raw.get("api_version", "v8"))
    if not VERSION_RE.match(version):
        raise ZcrmError("profile_invalid", f"Profile {name!r} has invalid api_version {version!r}.", exit_code=EXIT_USAGE)
    ptype = raw.get("type", "demo")
    if not isinstance(ptype, str):
        raise ZcrmError("profile_invalid", f"Profile {name!r} has invalid type.", exit_code=EXIT_USAGE)
    scopes = raw.get("scopes")
    if not isinstance(scopes, list) or not scopes or not all(isinstance(s, str) for s in scopes):
        raise ZcrmError("profile_invalid", f"Profile {name!r} needs a non-empty scopes list.", exit_code=EXIT_USAGE)
    return Profile(name, datacenters.normalize(dc), version, ptype, scopes)


def _read_raw() -> dict:
    path = paths.profiles_file()
    if not path.exists():
        return {"version": 1, "profiles": {}}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        raise ZcrmError("profile_invalid", "profiles.yaml is not valid YAML.", exit_code=EXIT_USAGE)
    if not isinstance(data, dict):
        raise ZcrmError("profile_invalid", "profiles.yaml must be a mapping.", exit_code=EXIT_USAGE)
    for key in data:
        if key not in {"version", "default", "profiles"}:
            raise ZcrmError("profile_invalid", f"profiles.yaml has unknown key {key!r}.", exit_code=EXIT_USAGE)
    data.setdefault("version", 1)
    data["profiles"] = data.get("profiles") or {}
    return data


def load_profiles() -> dict:
    raw = _read_raw()
    return {name: _build(name, body) for name, body in raw["profiles"].items()}


def get(name: str) -> Profile:
    profiles = load_profiles()
    if name not in profiles:
        raise ZcrmError(
            "profile_unknown",
            f"No profile named {name!r}.",
            fix="Run `zcrm profiles` to list profiles, or `zcrm setup <profile>` in your own terminal to create one.",
            exit_code=EXIT_USAGE,
        )
    return profiles[name]


def require_demo(profile: Profile) -> Profile:
    if profile.type != "demo":
        raise ZcrmError(
            "profile_not_demo",
            f"Profile {profile.name!r} has type {profile.type!r}. zcrm only works with demo orgs.",
            fix="Use a profile of type demo.",
            exit_code=EXIT_REFUSED,
        )
    return profile


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def save_profile(profile: Profile) -> None:
    validate_name(profile.name)
    raw = _read_raw()
    raw["profiles"][profile.name] = {
        "data_center": profile.data_center,
        "api_version": profile.api_version,
        "type": profile.type,
        "scopes": list(profile.scopes),
    }
    _build(profile.name, raw["profiles"][profile.name])
    _atomic_write(paths.profiles_file(), yaml.safe_dump(raw, sort_keys=False))


def ensure_file() -> bool:
    """Create an empty profiles.yaml when missing. Returns True if created."""
    path = paths.profiles_file()
    if path.exists():
        return False
    _atomic_write(path, yaml.safe_dump({"version": 1, "profiles": {}}, sort_keys=False))
    return True
