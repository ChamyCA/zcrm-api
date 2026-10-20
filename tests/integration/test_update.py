import json

import pytest

from zcrm import paths, secrets, ui
from zcrm.lifecycle import install_info, settings, skillfiles, update


class Result:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


@pytest.fixture
def harness(env, monkeypatch, add_profile):
    (env["home"] / ".claude").mkdir()
    add_profile()
    skillfiles.install()
    settings.apply(lambda r: False)
    calls, said = [], []
    tags = {"out": "abc\trefs/tags/v1.0.0\ndef\trefs/tags/v1.2.0\nghi\trefs/tags/v1.10.0\nxyz\trefs/tags/nightly\n"}

    def fake_run(cmd):
        calls.append(cmd)
        if cmd[:2] == ["git", "ls-remote"]:
            return Result(tags["out"])
        return Result()

    monkeypatch.setattr(install_info, "run", fake_run)
    monkeypatch.setattr(install_info, "source", lambda: ("https://github.com/org/zcrm-api", "v1.0.0"))
    monkeypatch.setattr(ui, "say", lambda m: said.append(m))
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: True)
    monkeypatch.setattr(update.sys, "platform", "linux")
    return calls, said, tags


def test_versions_compare_numerically():
    assert update.parse_version("v1.10.0") > update.parse_version("v1.2.0")
    assert update.parse_version("nightly") is None


def test_latest_tag_picked(harness):
    assert update.latest_tag("https://github.com/org/zcrm-api") == "v1.10.0"


def test_update_runs_pinned_installer_then_refresh_and_keeps_data(harness):
    calls, said, _ = harness
    cfg_before = paths.profiles_file().read_text()
    creds_before = secrets.load_credentials("demo1")
    manifest_before = paths.manifest_file().read_text()
    assert update.run() == 0
    install_cmd = [c for c in calls if c[0] != "git" and c[-1] != "_refresh"][0]
    assert "git+https://github.com/org/zcrm-api@v1.10.0" in install_cmd
    assert calls[-1] == ["zcrm", "_refresh"]
    assert paths.profiles_file().read_text() == cfg_before and secrets.load_credentials("demo1") == creds_before
    assert paths.manifest_file().read_text() == manifest_before
    assert any("Updated to v1.10.0" in m for m in said)


def test_already_latest_does_nothing(harness):
    calls, said, tags = harness
    tags["out"] = "abc\trefs/tags/v1.0.0\n"
    assert update.run() == 0
    assert calls == [["git", "ls-remote", "--tags", "--refs", "https://github.com/org/zcrm-api"]]
    assert any("Already up to date" in m for m in said)


def test_declined_changes_nothing(harness, monkeypatch):
    calls, said, _ = harness
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: False)
    assert update.run() == 0
    assert len(calls) == 1


def test_installer_failure_reported(harness, monkeypatch):
    calls, said, _ = harness
    base = install_info.run

    def failing(cmd):
        return Result(returncode=1) if cmd[0] != "git" else base(cmd)

    monkeypatch.setattr(install_info, "run", failing)
    assert update.run() == 5 and any("installer failed" in m for m in said)


def test_windows_hands_off_commands(harness, monkeypatch):
    calls, said, _ = harness
    monkeypatch.setattr(update.sys, "platform", "win32")
    assert update.run() == 0
    assert len(calls) == 1 and any("zcrm _refresh" in m for m in said)


def test_never_runs_without_the_user(env, run_cli):
    code, out, _ = run_cli("update")
    assert code == 2 and out["error"]["code"] == "interactive_only"


def test_refresh_restores_skill_and_rules_without_removing(harness):
    paths.skill_dir().joinpath("SKILL.md").write_text("tampered")
    data = json.loads(paths.settings_file().read_text())
    data["permissions"]["allow"].append("Bash(zcrm:*)")
    paths.settings_file().write_text(json.dumps(data))
    assert update.refresh() == 0
    assert "tampered" not in paths.skill_dir().joinpath("SKILL.md").read_text()
    assert "Bash(zcrm:*)" in json.loads(paths.settings_file().read_text())["permissions"]["allow"]
