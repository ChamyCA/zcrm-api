"""Where this copy of zcrm was installed from (for update and the uvx hand-off)."""

import json
import os
import subprocess
from importlib import metadata


def source():
    """Return (repo_url, requested_revision) or (None, None)."""
    env = os.environ.get("ZCRM_INSTALL_URL")
    if env:
        return env, None
    try:
        raw = metadata.distribution("zcrm-api").read_text("direct_url.json")
        data = json.loads(raw) if raw else {}
    except (metadata.PackageNotFoundError, ValueError):
        return None, None
    url = data.get("url")
    if not url or url.startswith("file:"):
        return None, None
    return url, data.get("vcs_info", {}).get("requested_revision")


def run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)
