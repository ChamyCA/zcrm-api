import pytest

from zcrm import datacenters
from zcrm.output import ZcrmError


def test_table_pinned():
    assert datacenters.suffixes() == [".com", ".ca", ".eu", ".in", ".com.au", ".jp", ".com.cn", ".sa"]
    ca = datacenters.get(".ca")
    assert ca.accounts_host == "accounts.zohocloud.ca"
    assert ca.api_host == "www.zohoapis.ca"
    assert datacenters.get(".com").console_host == "api-console.zoho.com"


def test_normalize_and_unknown():
    assert datacenters.get("eu").suffix == ".eu"
    with pytest.raises(ZcrmError) as exc:
        datacenters.get(".xx")
    assert exc.value.code == "data_center_unknown"
