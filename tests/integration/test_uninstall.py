import json

import pytest

from zcrm import paths, secrets, ui
from zcrm.lifecycle import settings, skillfiles, uninstall


@pytest.fixture
def installed(env, add_profile, monkeypatch):
    (env["home"] / ".claude").mkdir()
    paths.settings_file().write_text(json.dumps({"model": "opus", "permissions": {"allow": ["Bash(ls)", settings.ALLOW_RULES[0]]}}))
    add_profile("p1")
    add_profile("p2")
    skillfiles.install()
    settings.apply(lambda r: False)
    (paths.runs_dir()).mkdir(parents=True)
    (paths.runs_dir() / "x.json").write_text("{}")
    said = []
    monkeypatch.setattr(ui, "say", lambda m: said.append(m))
    return said


def answers(monkeypatch, mapping):
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: next((v for k, v in mapping.items() if k in prompt), False))


def test_full_uninstall(installed, monkeypatch, keyring_fake):
    answers(monkeypatch, {"Continue?": True, "credentials for profile": True, "settings backup": True})
    assert uninstall.run() == 0
    assert not paths.skill_dir().exists() and not paths.config_dir().exists()
    data = json.loads(paths.settings_file().read_text())
    assert data == {"model": "opus", "permissions": {"allow": ["Bash(ls)", settings.ALLOW_RULES[0]]}}
    assert keyring_fake.store == {}
    assert list(paths.claude_dir().glob("settings.json.zcrm-backup-*")) == []


def test_keyring_kept_when_declined(installed, monkeypatch, keyring_fake):
    answers(monkeypatch, {"Continue?": True})
    uninstall.run()
    assert secrets.has_credentials("p1") and secrets.has_credentials("p2")
    assert any("Keyring entries kept" in m for m in installed)
    assert not paths.config_dir().exists()


def test_per_profile_keyring_choice(installed, monkeypatch):
    answers(monkeypatch, {"Continue?": True, "profile 'p1'": True})
    uninstall.run()
    assert not secrets.has_credentials("p1") and secrets.has_credentials("p2")


def test_declining_changes_nothing(installed, monkeypatch):
    answers(monkeypatch, {})
    assert uninstall.run() == 0
    assert paths.skill_dir().exists() and paths.config_dir().exists()


def test_idempotent(installed, monkeypatch):
    answers(monkeypatch, {"Continue?": True, "credentials for profile": True, "settings backup": True})
    uninstall.run()
    installed.clear()
    assert uninstall.run() == 0 and installed == ["Nothing to uninstall."]


def test_non_tty_refused(env, run_cli):
    assert run_cli("uninstall")[0] == 2
