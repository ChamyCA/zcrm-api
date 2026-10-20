import json
from pathlib import Path

URL = "https://www.zohoapis.com/crm/v8"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample-plan.md"


def ok(rid):
    return {"data": [{"code": "SUCCESS", "status": "success", "details": {"id": rid}}]}


def mock_zoho(zoho):
    zoho.get(f"{URL}/settings/modules", json={"modules": [{"api_name": "Leads"}]})
    zoho.post(f"{URL}/Accounts", json=ok("111"))
    zoho.post(f"{URL}/Contacts", json=ok("222"))
    zoho.delete(f"{URL}/Accounts/111", json=ok("111"))


def writes(zoho, method=None):
    return [r for r in zoho.request_history if "/crm/" in r.url and r.method in ("POST", "PUT", "PATCH", "DELETE") and (method is None or r.method == method)]


def plan_file(tmp_path, text=None, name="plan.md"):
    p = tmp_path / name
    p.write_text(text if text is not None else FIXTURE.read_text())
    return str(p)


def request_json(req):
    return json.loads(req.text)
