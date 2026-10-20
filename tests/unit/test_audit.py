import json

from zcrm import audit, paths


def test_entry_shape_and_query_stripped():
    audit.log_call("p1", "GET", "/Leads/search?criteria=(Last_Name:equals:Secret)&page=2", 200, "ok", run_id="r1", step_id="s1")
    entry = json.loads(paths.audit_file().read_text().splitlines()[0])
    assert set(entry) == {"ts", "profile", "method", "path", "status", "outcome", "run_id", "step_id"}
    assert entry["path"] == "/Leads/search?criteria=*&page=*"
    assert "Secret" not in paths.audit_file().read_text()


def test_rotation(monkeypatch):
    monkeypatch.setattr(audit, "MAX_BYTES", 300)
    for i in range(30):
        audit.log_call("p1", "GET", f"/Leads/{i}", 200, "ok")
    base = paths.audit_file()
    assert base.with_name("audit.log.1").exists()
    assert not base.with_name("audit.log.4").exists()


def test_read_filters():
    audit.log_call("a", "GET", "/x", 200, "ok")
    audit.log_call("b", "GET", "/y", 200, "ok")
    audit.log_call("a", "GET", "/z", 200, "ok")
    assert [e["path"] for e in audit.read_entries("a")] == ["/x", "/z"]
    assert [e["path"] for e in audit.read_entries(last=1)] == ["/z"]
