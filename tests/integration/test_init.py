import json
import shutil
import sys

import pytest

from conftest import ORG_ID, SENT_CLIENT_ID, SENT_REFRESH, SENT_SECRET
from zcrm import paths, profiles, secrets, ui
from zcrm.lifecycle import init, install_info, settings, skillfiles


@pytest.fixture
def ready_env(env, monkeypatch):
    (env["home"] / ".claude").mkdir(exist_ok=True)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/local/bin/{name}")
    shown = []
    monkeypatch.setattr(ui, "say", lambda m: shown.append(m))
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: default if "another profile" in prompt else True)
    answers = {"Name for your first profile": "acme", "Data center": ".com", "Profile type": "demo", "API version": "v8"}

    def ask(prompt, default=None):
        for key, value in answers.items():
            if prompt.startswith(key):
                return value
        return default or ""

    secrets_in = iter([SENT_CLIENT_ID, SENT_SECRET, SENT_REFRESH])
    monkeypatch.setattr(ui, "ask", ask)
    monkeypatch.setattr(ui, "ask_secret", lambda prompt: next(secrets_in))
    return shown


def test_fresh_init_end_to_end(zoho, ready_env):
    assert init.run() == 0
    assert (paths.skill_dir() / "SKILL.md").is_file()
    assert (paths.skill_dir() / ".zcrm-version").read_text() == "1.1.1"
    assert not any(p.is_symlink() for p in paths.skill_dir().rglob("*"))
    data = json.loads(paths.settings_file().read_text())
    assert data["permissions"]["ask"] == settings.ASK_RULES
    assert paths.profiles_file().exists() and "acme" in profiles.load_profiles()
    assert secrets.has_credentials("acme")
    ready = [m for m in ready_env if m.startswith("Ready:")]
    assert len(ready) == 1 and ORG_ID in ready[0] and "\n" not in ready[0]
    assert any("Next Steps" in m for m in ready_env) and any("Step 3 of 3" in m for m in ready_env)


def test_second_init_changes_nothing(zoho, ready_env):
    init.run()
    settings_before = paths.settings_file().read_text()
    profiles_before = paths.profiles_file().read_text()
    skill_before = {p.name: p.read_bytes() for p in paths.skill_dir().rglob("*") if p.is_file()}
    creds_before = secrets.load_credentials("acme")
    assert init.run() == 0
    assert paths.settings_file().read_text() == settings_before
    assert paths.profiles_file().read_text() == profiles_before
    assert {p.name: p.read_bytes() for p in paths.skill_dir().rglob("*") if p.is_file()} == skill_before
    assert secrets.load_credentials("acme") == creds_before
    assert len(list(paths.claude_dir().glob("settings.json.zcrm-backup-*"))) == 0  # settings did not exist before init
    assert any(m.startswith("Ready:") for m in ready_env)


def test_prerequisite_failures_stop_without_changes(env, monkeypatch):
    shown = []
    monkeypatch.setattr(ui, "say", lambda m: shown.append(m))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert init.run() == 5
    text = "\n".join(shown)
    assert "Claude Code was not found" in text and "Fix:" in text
    assert not paths.skill_dir().exists() and not paths.settings_file().exists()


def test_no_keyring_backend_reported(env, monkeypatch):
    import keyring
    from keyring.backends.fail import Keyring as FailKeyring

    (env["home"] / ".claude").mkdir()
    keyring.set_keyring(FailKeyring())
    shown = []
    monkeypatch.setattr(ui, "say", lambda m: shown.append(m))
    assert init.run() == 5
    assert "keyring" in "\n".join(shown).lower()
    assert not paths.skill_dir().exists()


def test_old_python_reported(env, monkeypatch):
    import sys

    (env["home"] / ".claude").mkdir()
    shown = []
    monkeypatch.setattr(ui, "say", lambda m: shown.append(m))
    monkeypatch.setattr(sys, "version_info", (3, 9, 0))
    assert init.run() == 5
    assert "Python 3.10" in "\n".join(shown)


def test_conflicting_rule_prompt_and_decline(zoho, ready_env, monkeypatch, env):
    paths.settings_file().parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file().write_text(json.dumps({"permissions": {"allow": ["Bash(zcrm:*)"]}}))
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: "Remove it" not in prompt and (default if "another" in prompt else True))
    init.run()
    assert "Bash(zcrm:*)" in json.loads(paths.settings_file().read_text())["permissions"]["allow"]
    assert any("WARNING" in m for m in ready_env)
    assert not any(m.startswith("Ready:") for m in ready_env)
    assert init.run() == 5


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_skill_install_replaces_symlink_and_is_idempotent(env):
    target = env["tmp"] / "elsewhere"
    target.mkdir()
    paths.skill_dir().parent.mkdir(parents=True)
    paths.skill_dir().symlink_to(target, target_is_directory=True)
    assert skillfiles.install() == "updated"
    assert not paths.skill_dir().is_symlink()
    assert skillfiles.install() == "unchanged"


def test_uvx_handoff_offers_tool_install(env, monkeypatch):
    calls = []
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(install_info, "source", lambda: ("https://github.com/org/zcrm-api", "v1.0.0"))

    class R:
        returncode = 0

    monkeypatch.setattr(install_info, "run", lambda cmd: calls.append(cmd) or R())
    monkeypatch.setattr(ui, "say", lambda m: None)
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: True)
    init.ensure_persistent()
    assert calls == [["uv", "tool", "install", "--force", "--from", "git+https://github.com/org/zcrm-api@v1.0.0", "zcrm-api"]]
