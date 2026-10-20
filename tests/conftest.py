import json

import keyring
import pytest
import requests_mock as rm
import yaml
from keyring.backend import KeyringBackend

from zcrm import cli, client, output, profiles, secrets, ui

SENT_CLIENT_ID = "1000.SENTINELCLIENTIDABCDEFGHIJ12"
SENT_SECRET = "sentinelsecret0123456789abcdef0123"
SENT_REFRESH = "1000." + "a1b2c3d4" * 4 + "." + "e5f6a7b8" * 4
SENT_ACCESS = "1000." + "0123abcd" * 4 + "." + "4567ef89" * 4
SENTINELS = [SENT_CLIENT_ID, SENT_SECRET, SENT_REFRESH, SENT_ACCESS]
ORG_ID = "5725767000000012345"


class FakeKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        from keyring.errors import PasswordDeleteError

        if (service, username) not in self.store:
            raise PasswordDeleteError("missing")
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData"))
    monkeypatch.setenv("ZCRM_HOME", str(tmp_path / "zcrm-home"))
    monkeypatch.delenv("ZCRM_INSTALL_URL", raising=False)
    fake = FakeKeyring()
    keyring.set_keyring(fake)
    secrets._memory_cache.clear()
    output.clear_secrets()
    sleeps = []
    monkeypatch.setattr(client, "_sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(ui, "is_interactive", lambda: False)
    return {"home": home, "keyring": fake, "sleeps": sleeps, "tmp": tmp_path}


@pytest.fixture
def keyring_fake(env):
    return env["keyring"]


@pytest.fixture
def sleeps(env):
    return env["sleeps"]


@pytest.fixture
def zoho():
    with rm.Mocker() as m:

        def token(request, context):
            body = request.text
            data = dict(p.split("=", 1) for p in body.split("&"))
            out = {"access_token": SENT_ACCESS, "expires_in": 3600, "token_type": "Bearer"}
            if data.get("grant_type") == "authorization_code":
                out["refresh_token"] = SENT_REFRESH
            return out

        m.post("https://accounts.zoho.com/oauth/v2/token", json=token)
        m.post("https://accounts.zohocloud.ca/oauth/v2/token", json=token)
        m.get("https://www.zohoapis.com/crm/v8/org", json={"org": [{"id": ORG_ID, "company_name": "Demo Org"}]})
        m.get("https://www.zohoapis.ca/crm/v8/org", json={"org": [{"id": ORG_ID, "company_name": "Demo Org"}]})
        yield m


@pytest.fixture
def add_profile(env):
    def _add(name="demo1", dc=".com", ptype="demo", scopes=None, creds=True):
        scopes = scopes or [
            "ZohoCRM.modules.ALL",
            "ZohoCRM.settings.ALL",
            "ZohoCRM.org.READ",
            "ZohoCRM.coql.READ",
        ]
        profiles.ensure_file()
        raw = profiles._read_raw()
        raw["profiles"][name] = {"data_center": dc, "api_version": "v8", "type": ptype, "scopes": scopes}
        profiles._atomic_write(profiles.paths.profiles_file(), yaml.safe_dump(raw, sort_keys=False))
        if creds:
            secrets.set_credential(name, "client_id", SENT_CLIENT_ID)
            secrets.set_credential(name, "client_secret", SENT_SECRET)
            secrets.set_credential(name, "refresh_token", SENT_REFRESH)
        output.clear_secrets()
        return name

    return _add


@pytest.fixture
def run_cli(capsys):
    def _run(*argv):
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        try:
            parsed = json.loads(captured.out) if captured.out.strip() else None
        except ValueError:
            parsed = None
        return code, parsed, captured

    return _run


def all_files_text(root):
    text = ""
    for path in root.rglob("*"):
        if path.is_file():
            try:
                text += path.read_text(encoding="utf-8", errors="ignore") + "\n"
            except OSError:
                pass
    return text
