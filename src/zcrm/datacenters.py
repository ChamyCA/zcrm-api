"""Zoho data centers. This table is authoritative; hosts are never built from user input.

VERIFY: the .ca hosts (zohocloud.ca family) against current Zoho documentation.
"""

from dataclasses import dataclass

from zcrm.output import EXIT_USAGE, ZcrmError


@dataclass(frozen=True)
class DataCenter:
    suffix: str
    accounts_host: str
    api_host: str
    console_host: str


_TABLE = {
    ".com": DataCenter(".com", "accounts.zoho.com", "www.zohoapis.com", "api-console.zoho.com"),
    ".ca": DataCenter(".ca", "accounts.zohocloud.ca", "www.zohoapis.ca", "api-console.zohocloud.ca"),
    ".eu": DataCenter(".eu", "accounts.zoho.eu", "www.zohoapis.eu", "api-console.zoho.eu"),
    ".in": DataCenter(".in", "accounts.zoho.in", "www.zohoapis.in", "api-console.zoho.in"),
    ".com.au": DataCenter(".com.au", "accounts.zoho.com.au", "www.zohoapis.com.au", "api-console.zoho.com.au"),
    ".jp": DataCenter(".jp", "accounts.zoho.jp", "www.zohoapis.jp", "api-console.zoho.jp"),
    ".com.cn": DataCenter(".com.cn", "accounts.zoho.com.cn", "www.zohoapis.com.cn", "api-console.zoho.com.cn"),
    ".sa": DataCenter(".sa", "accounts.zoho.sa", "www.zohoapis.sa", "api-console.zoho.sa"),
}


def suffixes() -> list[str]:
    return list(_TABLE)


def normalize(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value.startswith(".") else "." + value


def is_known(value: str) -> bool:
    return normalize(value) in _TABLE


def get(value: str) -> DataCenter:
    key = normalize(value)
    if key not in _TABLE:
        raise ZcrmError(
            "data_center_unknown",
            f"Unknown data center {value!r}.",
            fix="Use one of: " + ", ".join(_TABLE),
            exit_code=EXIT_USAGE,
        )
    return _TABLE[key]
