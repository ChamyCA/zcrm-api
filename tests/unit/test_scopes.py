from zcrm import scopes


def test_mappings():
    assert scopes.required_scope("GET", "/org")[0] == "ZohoCRM.org.READ"
    assert scopes.required_scope("POST", "/coql")[0] == "ZohoCRM.coql.READ"
    assert scopes.required_scope("GET", "/users")[0] == "ZohoCRM.users.READ"
    assert scopes.required_scope("POST", "/users")[0] == "ZohoCRM.users.ALL"
    assert scopes.required_scope("POST", "/settings/modules")[0] == "ZohoCRM.settings.modules.CREATE"
    assert scopes.required_scope("GET", "/Leads/123")[0] == "ZohoCRM.modules.leads.READ"
    assert scopes.required_scope("DELETE", "/Leads/123")[0] == "ZohoCRM.modules.leads.DELETE"


def test_all_variant_satisfies():
    assert scopes.check(["ZohoCRM.modules.ALL"], "POST", "/Leads")[0] == "ok"
    assert scopes.check(["ZohoCRM.settings.ALL"], "GET", "/settings/fields?module=Leads")[0] == "ok"
    assert scopes.check(["ZohoCRM.modules.leads.READ"], "GET", "/Leads")[0] == "ok"


def test_missing_and_unknown():
    state, needed = scopes.check(["ZohoCRM.org.READ"], "GET", "/Leads")
    assert (state, needed) == ("missing", "ZohoCRM.modules.leads.READ")
    assert scopes.check(["ZohoCRM.org.READ"], "GET", "/functions/x")[0] == "unknown"
