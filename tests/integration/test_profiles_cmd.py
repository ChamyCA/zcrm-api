def test_profiles_lists_non_secret_only(run_cli, add_profile):
    add_profile("a1", ".com")
    add_profile("b2", ".ca", creds=False)
    code, out, cap = run_cli("profiles")
    assert code == 0
    rows = {p["name"]: p for p in out["profiles"]}
    assert rows["a1"]["credentials_stored"] is True and rows["b2"]["credentials_stored"] is False
    assert rows["b2"]["data_center"] == ".ca"
    assert "client_secret" not in cap.out
