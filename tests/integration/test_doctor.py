import json
import shutil

import pytest

from conftest import SENT_REFRESH
from zcrm import paths, secrets
from zcrm.lifecycle import doctor, settings, skillfiles


@pytest.fixture
def healthy(env, zoho, add_profile, monkeypatch):
    (env["home"] / ".claude").mkdir()
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    add_profile()
    skillfiles.install()
    settings.apply(lambda r: False)


def by_name(checks):
    return {c["name"]: c for c in checks}


def test_all_pass(healthy):
    checks = doctor.run_checks()
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
    names = by_name(checks)
    assert {"python", "keyring_read", "keyring_write", "zcrm_on_path", "skill_present", "permission_rules", "no_conflicting_rules", "no_secrets_in_config", "profile:demo1"} <= set(names)


def test_cli_exit_codes(healthy, run_cli):
    code, out, _ = run_cli("doctor")
    assert code == 0 and out["ok"] is True
    paths.skill_dir().joinpath("SKILL.md").unlink()
    paths.skill_dir().joinpath(".zcrm-version").unlink()
    code, out, _ = run_cli("doctor")
    assert code == 5 and out["ok"] is False
    failed = by_name(out["checks"])["skill_present"]
    assert failed["ok"] is False and "zcrm init" in failed["fix"]


def test_missing_rules_and_conflict(healthy):
    data = json.loads(paths.settings_file().read_text())
    data["permissions"]["ask"].remove("Bash(zcrm * POST *)")
    data["permissions"]["allow"].append("Bash(zcrm:*)")
    paths.settings_file().write_text(json.dumps(data))
    names = by_name(doctor.run_checks())
    assert names["permission_rules"]["ok"] is False
    assert names["no_conflicting_rules"]["ok"] is False and "Bash(zcrm:*)" in names["no_conflicting_rules"]["detail"]


def test_secret_planted_in_profiles_yaml(healthy):
    with open(paths.profiles_file(), "a") as fh:
        fh.write(f"# note {SENT_REFRESH}\n")
    names = by_name(doctor.run_checks())
    assert names["no_secrets_in_config"]["ok"] is False
    assert "profiles.yaml" in names["no_secrets_in_config"]["detail"] and SENT_REFRESH not in names["no_secrets_in_config"]["detail"]


def test_exact_stored_secret_found_in_config_file(healthy):
    secrets.set_credential("demo1", "client_secret", "plainsecretvalue987")
    (paths.config_dir() / "notes.txt").write_text("my secret is plainsecretvalue987")
    assert by_name(doctor.run_checks())["no_secrets_in_config"]["ok"] is False


def test_refresh_token_revoked(healthy, zoho):
    zoho.post("https://accounts.zoho.com/oauth/v2/token", json={"error": "invalid_code"})
    check = by_name(doctor.run_checks())["profile:demo1"]
    assert check["ok"] is False and "invalid_code" in check["detail"] and "zcrm setup demo1" in check["fix"]


def test_missing_credentials_and_non_demo(healthy, add_profile):
    add_profile("nocreds", creds=False)
    add_profile("corp1", ptype="corp")
    names = by_name(doctor.run_checks())
    assert names["profile:nocreds"]["ok"] is False and "zcrm setup nocreds" in names["profile:nocreds"]["fix"]
    assert names["profile:corp1"]["ok"] is False


def test_keyring_failure_and_no_profiles(env, monkeypatch):
    import keyring
    from keyring.backends.fail import Keyring as FailKeyring

    keyring.set_keyring(FailKeyring())
    monkeypatch.setattr(shutil, "which", lambda name: None)
    names = by_name(doctor.run_checks())
    assert names["keyring_read"]["ok"] is False and names["zcrm_on_path"]["ok"] is False
    assert names["profiles"]["ok"] is False


def test_doctor_reports_read_and_write_separately(healthy, monkeypatch):
    from keyring.errors import PasswordSetError

    def boom(*a, **k):
        raise PasswordSetError("ro")

    monkeypatch.setattr("keyring.set_password", boom)
    names = by_name(doctor.run_checks())
    assert names["keyring_read"]["ok"] and "readable" in names["keyring_read"]["detail"]
    assert "not writable" in names["keyring_write"]["detail"]
