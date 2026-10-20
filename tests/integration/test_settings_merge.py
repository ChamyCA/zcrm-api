import json

import pytest

from zcrm import paths
from zcrm.lifecycle import settings
from zcrm.output import ZcrmError


def write(data):
    f = paths.settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data) if not isinstance(data, str) else data)


def read():
    return json.loads(paths.settings_file().read_text())


def backups():
    return sorted(paths.claude_dir().glob("settings.json.zcrm-backup-*"))


def test_missing_file_created():
    res = settings.apply(lambda r: False)
    assert res["changed"] and res["backup"] is None
    data = read()
    assert data["permissions"]["allow"] == settings.ALLOW_RULES
    assert data["permissions"]["ask"] == settings.ASK_RULES


def test_empty_file_treated_as_missing():
    write("")
    assert settings.apply(lambda r: False)["changed"]
    assert read()["permissions"]["ask"] == settings.ASK_RULES
    assert backups() == []


def test_invalid_json_aborts_untouched():
    write("{not json")
    with pytest.raises(ZcrmError) as exc:
        settings.apply(lambda r: False)
    assert exc.value.code == "settings_invalid"
    assert paths.settings_file().read_text() == "{not json"
    assert backups() == []


def test_backup_and_preserve_unrelated_keys_and_order():
    original = {"model": "opus", "permissions": {"allow": ["Bash(ls)"], "deny": ["Bash(rm *)"]}, "env": {"A": "1"}}
    write(original)
    res = settings.apply(lambda r: False)
    assert res["backup"] and len(backups()) == 1
    assert json.loads(backups()[0].read_text()) == original
    data = read()
    assert list(data) == ["model", "permissions", "env"]
    assert data["model"] == "opus" and data["env"] == {"A": "1"}
    assert data["permissions"]["deny"] == ["Bash(rm *)"]
    assert data["permissions"]["allow"][0] == "Bash(ls)"


def test_idempotent_no_duplicates_no_new_backup():
    write({"permissions": {"allow": ["Bash(ls)"]}})
    settings.apply(lambda r: False)
    before = paths.settings_file().read_text()
    res = settings.apply(lambda r: False)
    assert res["changed"] is False
    assert paths.settings_file().read_text() == before
    assert len(backups()) == 1


@pytest.mark.parametrize("rule", ["Bash(zcrm:*)", "Bash(zcrm *)", "Bash(*)", "Bash", "Bash(zcrm * POST *)", "Bash(zcrm run *)"])
def test_conflicts_detected(rule):
    assert settings.conflicting_rules({"permissions": {"allow": [rule]}}) == [rule]


def test_our_rules_and_unrelated_are_not_conflicts():
    assert settings.conflicting_rules({"permissions": {"allow": settings.ALLOW_RULES + ["Bash(ls)", "Bash(git status)"]}}) == []


def test_conflict_removed_only_on_yes():
    write({"permissions": {"allow": ["Bash(zcrm:*)", "Bash(ls)"]}})
    res = settings.apply(lambda r: True)
    assert res["removed"] == ["Bash(zcrm:*)"]
    assert "Bash(zcrm:*)" not in read()["permissions"]["allow"]
    assert "Bash(ls)" in read()["permissions"]["allow"]


def test_conflict_kept_when_declined_and_doctor_sees_it():
    write({"permissions": {"allow": ["Bash(zcrm:*)"]}})
    res = settings.apply(lambda r: False)
    assert res["declined"] == ["Bash(zcrm:*)"]
    assert "Bash(zcrm:*)" in read()["permissions"]["allow"]
    assert settings.conflicting_rules(settings.load()) == ["Bash(zcrm:*)"]


def test_manifest_lists_only_rules_actually_added():
    mine = settings.ALLOW_RULES[0]
    write({"permissions": {"allow": [mine]}})
    settings.apply(lambda r: False)
    manifest = settings.load_manifest()
    assert mine not in manifest["rules_added"]["allow"]
    assert set(manifest["rules_added"]["allow"]) == set(settings.ALLOW_RULES) - {mine}
    assert manifest["rules_added"]["ask"] == settings.ASK_RULES
    assert "secret" not in json.dumps(manifest).lower()


def test_remove_added_keeps_users_identical_rule():
    mine = settings.ALLOW_RULES[0]
    write({"permissions": {"allow": [mine, "Bash(ls)"]}, "model": "x"})
    settings.apply(lambda r: False)
    removed = settings.remove_added(settings.load_manifest())
    assert mine not in removed
    data = read()
    assert data["permissions"]["allow"] == [mine, "Bash(ls)"]
    assert "ask" not in data["permissions"] and data["model"] == "x"


def test_no_allow_rule_overlaps_an_ask_rule():
    """If ask outranks allow, an overlap would turn a read into a prompt (or hide a write behind an allow)."""
    for rule in settings.ALLOW_RULES:
        command = rule[len("Bash("):-1].replace("*", "demo")
        assert not any(settings.rule_matches(ask, command) for ask in settings.ASK_RULES), (rule, command)


def test_write_shapes_hit_ask_and_no_allow():
    writes = [
        "zcrm demo POST /Leads body.json --approved",
        "zcrm demo PUT /Leads/1 b.json --approved",
        "zcrm demo PATCH /Leads/1 b.json --approved",
        "zcrm demo DELETE /Leads/1 --approved",
        "zcrm run demo plan.md --approve-steps s2",
        "zcrm run demo plan.md --skip-step s2",
    ]
    for command in writes:
        assert any(settings.rule_matches(r, command) for r in settings.ASK_RULES), command
        assert not any(settings.rule_matches(r, command) for r in settings.ALLOW_RULES), command


def test_read_shapes_hit_allow_and_no_ask():
    reads = [
        "zcrm demo GET /Leads",
        "zcrm demo GET /Leads/search?word=x",
        "zcrm demo COQL q.json",
        "zcrm run demo plan.md --dry-run",
        "zcrm run demo plan.md --only-reads",
        "zcrm profiles",
        "zcrm doctor",
        "zcrm log --last 5",
    ]
    for command in reads:
        assert any(settings.rule_matches(r, command) for r in settings.ALLOW_RULES), command
        assert not any(settings.rule_matches(r, command) for r in settings.ASK_RULES), command
