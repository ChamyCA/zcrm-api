import pytest
import yaml

from zcrm import paths, profiles
from zcrm.output import ZcrmError


def _write(data):
    paths.profiles_file().parent.mkdir(parents=True, exist_ok=True)
    paths.profiles_file().write_text(yaml.safe_dump(data))


def good(**over):
    base = {"data_center": ".ca", "api_version": "v8", "type": "demo", "scopes": ["ZohoCRM.modules.ALL"]}
    base.update(over)
    return base


def test_roundtrip_save_and_load():
    profiles.save_profile(profiles.Profile("acme-demo", ".ca", "v8", "demo", ["ZohoCRM.org.READ"]))
    loaded = profiles.get("acme-demo")
    assert loaded.data_center == ".ca" and loaded.scopes == ["ZohoCRM.org.READ"]


@pytest.mark.parametrize("name", ["Bad", "-x", "a" * 41, "has space", "init", "run", "log", "setup"])
def test_invalid_and_reserved_names(name):
    with pytest.raises(ZcrmError):
        profiles.validate_name(name)


@pytest.mark.parametrize(
    "over",
    [{"data_center": ".zz"}, {"api_version": "8"}, {"scopes": []}, {"scopes": "x"}, {"bogus": 1}],
)
def test_invalid_fields(over):
    _write({"version": 1, "profiles": {"p1": good(**over)}})
    with pytest.raises(ZcrmError):
        profiles.load_profiles()


def test_secret_like_key_rejected():
    _write({"version": 1, "profiles": {"p1": good(client_secret="abc")}})
    with pytest.raises(ZcrmError) as exc:
        profiles.load_profiles()
    assert exc.value.code == "config_has_secret"


def test_non_demo_refused():
    _write({"version": 1, "profiles": {"p1": good(type="corp")}})
    with pytest.raises(ZcrmError) as exc:
        profiles.require_demo(profiles.get("p1"))
    assert exc.value.code == "profile_not_demo" and exc.value.exit_code == 4


def test_unknown_profile():
    with pytest.raises(ZcrmError) as exc:
        profiles.get("nope")
    assert exc.value.code == "profile_unknown"
