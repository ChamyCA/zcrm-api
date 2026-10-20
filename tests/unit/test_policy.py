import pytest

from zcrm import policy
from zcrm.output import ZcrmError


@pytest.mark.parametrize(
    "method,path,kind",
    [
        ("GET", "/Leads", "read"),
        ("POST", "/coql", "read"),
        ("POST", "/Leads", "create"),
        ("PUT", "/Leads/1", "update"),
        ("PATCH", "/Leads/1", "update"),
        ("DELETE", "/Leads/1", "delete"),
        ("POST", "/coql/other", "create"),
    ],
)
def test_classify(method, path, kind):
    assert policy.classify(method, path) == kind


@pytest.mark.parametrize("method", ["get", "Get", "FETCH", ""])
def test_method_must_be_uppercase(method):
    with pytest.raises(ZcrmError) as exc:
        policy.validate_method(method)
    assert exc.value.exit_code == 2


@pytest.mark.parametrize(
    "path",
    ["Leads", "/a/../b", "/a/./b", "//x", "/a%2e%2e/b", "/a%2Fb", "/a\\b", "/a b", "/x\n", "https://evil/x"],
)
def test_unsafe_paths(path):
    with pytest.raises(ZcrmError) as exc:
        policy.normalize_path(path)
    assert exc.value.code == "unsafe_path" and exc.value.exit_code == 4


def test_safe_paths():
    assert policy.normalize_path("/Leads/search?criteria=(Last_Name:equals:Smith)") .startswith("/Leads")
    assert policy.normalize_path("/Leads/{{lead_id}}")


@pytest.mark.parametrize("path", ["/Leads?ids=1,2", "/Leads", "/Leads?ids=1&ids=2"])
def test_bulk_delete_refused(path):
    with pytest.raises(ZcrmError) as exc:
        policy.check_bulk_delete("DELETE", path)
    assert exc.value.code == "bulk_delete_refused"


def test_single_delete_allowed():
    policy.check_bulk_delete("DELETE", "/Leads/123")
    policy.check_bulk_delete("DELETE", "/Leads?ids=123")
    policy.check_bulk_delete("GET", "/Leads")


def test_body_summary():
    assert "2 item(s)" in policy.body_summary({"data": [{"Last_Name": "x", "Company": "y"}, {"Last_Name": "z"}]})
    assert "Company, Last_Name" in policy.body_summary({"data": [{"Last_Name": "x", "Company": "y"}]})
