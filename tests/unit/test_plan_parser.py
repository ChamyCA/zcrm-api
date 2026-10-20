import pytest

from zcrm.output import ZcrmError
from zcrm.plan import parser
from zcrm.plan.util import MISSING, find_id, find_vars, jpath, substitute

HEAD = '```zcrm-plan\norg_id: "123"\n```\n'


def step(sid="s1", body="method: GET\npath: /Leads", heading=None):
    return f"\n### {heading or sid + ' — desc'}\n\n```zcrm-step\n{body}\n```\n"


def errors_of(text):
    with pytest.raises(ZcrmError) as exc:
        parser.parse(text)
    assert exc.value.code == "plan_parse_error" and exc.value.exit_code == 7
    return [e["message"] for e in exc.value.extra["errors"]]


def test_valid_plan():
    text = (
        HEAD
        + step("s1", "method: GET\npath: /settings/modules")
        + step("s2", "method: POST\npath: /Accounts\nbody:\n  data:\n    - Account_Name: A\ncapture:\n  aid: data[0].details.id\ndepends_on: [s1]")
        + step("s3", 'method: DELETE\npath: /Accounts/{{aid}}\ndepends_on: [s2]')
    )
    plan = parser.parse(text)
    assert plan.org_id == "123" and [s.id for s in plan.steps] == ["s1", "s2", "s3"]
    assert [s.kind for s in plan.steps] == ["read", "create", "delete"]
    assert plan.steps[1].description == "desc" and plan.steps[1].capture == {"aid": "data[0].details.id"}
    assert len(plan.sha256) == 64 and parser.parse(text).sha256 == plan.sha256


def test_missing_header_and_org_id():
    assert any("header" in m for m in errors_of(step()))
    assert any("org_id" in m for m in errors_of("```zcrm-plan\ntitle: x\n```\n" + step()))


def test_duplicate_ids_and_bad_id():
    assert any("duplicate" in m for m in errors_of(HEAD + step("s1") + step("s1")))
    assert any("invalid step id" in m for m in errors_of(HEAD + step(heading="s1: colon")))


@pytest.mark.parametrize(
    "body,fragment",
    [
        ("method: get\npath: /Leads", "method"),
        ("method: GET\npath: /a/../b", "path"),
        ("method: GET\npath: Leads", "path"),
        ("method: GET\npath: /Leads\nbogus: 1", "unknown key"),
        ("method: POST\npath: /Leads\nbody: [1]", "body must be an object"),
        ("method: DELETE\npath: /Leads?ids=1,2", "Bulk delete"),
        ("method: GET\npath: /Leads\ndepends_on: [zz]", "earlier step"),
        ("method: GET\npath: /x/{{ a }}", "without spaces"),
        ("method: GET\npath: /x/{{nope}}", "not captured"),
        ("method: GET\npath: /Leads\nverify:\n  path: /x", "verify needs"),
    ],
)
def test_step_validation(body, fragment):
    assert any(fragment in m for m in errors_of(HEAD + step("s1", body)))


def test_forward_depends_and_forward_variable_rejected():
    text = HEAD + step("s1", "method: GET\npath: /x/{{v}}") + step("s2", "method: GET\npath: /y\ncapture:\n  v: a")
    assert any("not captured" in m for m in errors_of(text))


def test_no_steps():
    assert any("no zcrm-step" in m for m in errors_of(HEAD))


def test_fenced_examples_in_prose_are_ignored():
    text = HEAD + "\n````markdown\n### sx — example\n```zcrm-step\nmethod: DELETE\npath: /Leads\n```\n````\n" + step()
    assert [s.id for s in parser.parse(text).steps] == ["s1"]


def test_verify_accepted():
    body = "method: POST\npath: /Leads\nverify:\n  path: /Leads/search?word=x\n  match:\n    path: data[0].id"
    assert parser.parse(HEAD + step("s1", body)).steps[0].verify["match"] == {"path": "data[0].id"}


def test_util_jpath_substitute_ids():
    data = {"data": [{"details": {"id": "9"}}]}
    assert jpath(data, "data[0].details.id") == "9"
    assert jpath(data, "data[1]") is MISSING and jpath(data, "x.y") is MISSING
    assert find_vars({"a": ["{{x}}", "n {{y}}"]}) == {"x", "y"}
    assert substitute({"id": "{{x}}", "s": "a-{{x}}"}, {"x": 5}) == {"id": 5, "s": "a-5"}
    with pytest.raises(KeyError):
        substitute("{{z}}", {})
    assert find_id({"data": [{"status": "success", "details": {"id": 77}}]}) == "77"
    assert find_id({"data": []}) is None
