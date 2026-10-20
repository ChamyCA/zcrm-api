import pytest
import requests

from conftest import SENT_ACCESS
from zcrm import client, profiles
from zcrm.output import ZcrmError

URL = "https://www.zohoapis.com/crm/v8"


def prof(add_profile):
    add_profile()
    return profiles.get("demo1")


def test_get_ok(zoho, add_profile):
    zoho.get(f"{URL}/Leads", json={"data": [{"id": "1"}]})
    resp = client.request(prof(add_profile), "GET", "/Leads")
    assert resp.status == 200 and resp.data["data"][0]["id"] == "1"
    assert zoho.last_request.headers["Authorization"] == f"Zoho-oauthtoken {SENT_ACCESS}"


def test_204_returns_none(zoho, add_profile):
    zoho.get(f"{URL}/Leads/search", status_code=204)
    assert client.request(prof(add_profile), "GET", "/Leads/search?word=x").data is None


def test_429_retries_then_succeeds(zoho, add_profile, sleeps):
    zoho.get(f"{URL}/Leads", [{"status_code": 429, "headers": {"Retry-After": "2"}, "json": {}}, {"json": {"ok": 1}}])
    assert client.request(prof(add_profile), "GET", "/Leads").data == {"ok": 1}
    assert sleeps == [2.0]


def test_429_exhausted(zoho, add_profile):
    zoho.get(f"{URL}/Leads", status_code=429, json={})
    with pytest.raises(ZcrmError) as exc:
        client.request(prof(add_profile), "GET", "/Leads")
    assert exc.value.code == "rate_limited"
    assert len([r for r in zoho.request_history if r.method == "GET" and r.path == "/crm/v8/leads"]) == 4


def test_503_retried_for_reads(zoho, add_profile):
    zoho.get(f"{URL}/Leads", [{"status_code": 503, "json": {}}, {"status_code": 502, "json": {}}, {"json": {"ok": 1}}])
    assert client.request(prof(add_profile), "GET", "/Leads").status == 200


def test_503_not_retried_for_writes(zoho, add_profile):
    zoho.post(f"{URL}/Leads", status_code=503, json={})
    with pytest.raises(ZcrmError) as exc:
        client.request(prof(add_profile), "POST", "/Leads", {"data": []})
    assert exc.value.code == "api_error"
    assert len([r for r in zoho.request_history if r.method == "POST" and "crm" in r.url]) == 1


def test_429_retried_for_writes(zoho, add_profile):
    zoho.post(f"{URL}/Leads", [{"status_code": 429, "json": {}}, {"json": {"data": []}}])
    assert client.request(prof(add_profile), "POST", "/Leads", {"data": []}).status == 200


def test_write_not_retried_on_network_error(zoho, add_profile):
    zoho.post(f"{URL}/Leads", exc=requests.ConnectTimeout)
    with pytest.raises(ZcrmError) as exc:
        client.request(prof(add_profile), "POST", "/Leads", {"data": []})
    assert exc.value.code == "network_error" and exc.value.exit_code == 8


def test_401_invalid_token_refreshes_once(zoho, add_profile):
    zoho.get(f"{URL}/Leads", [{"status_code": 401, "json": {"code": "INVALID_TOKEN"}}, {"json": {"ok": 1}}])
    assert client.request(prof(add_profile), "GET", "/Leads").data == {"ok": 1}
    assert len([r for r in zoho.request_history if r.method == "POST"]) == 2


def test_scope_mismatch_maps(zoho, add_profile):
    zoho.get(f"{URL}/Leads", status_code=401, json={"code": "OAUTH_SCOPE_MISMATCH"})
    with pytest.raises(ZcrmError) as exc:
        client.request(prof(add_profile), "GET", "/Leads")
    assert exc.value.code == "scope_insufficient"


def test_embedded_errors():
    data = {"data": [{"status": "error", "code": "DUPLICATE_DATA", "message": "dup"}, {"status": "success"}]}
    assert client.embedded_errors(data) == [{"code": "DUPLICATE_DATA", "message": "dup"}]
    assert client.embedded_errors({"data": [{"status": "success"}]}) == []
