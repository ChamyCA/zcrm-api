"""Copy the packaged skill into ~/.claude/skills/zcrm-api (symlink-free, versioned)."""

import shutil
from pathlib import Path

from zcrm import __version__, paths

VERSION_FILE = ".zcrm-version"


def _desired() -> dict:
    src = paths.packaged_skill_dir()
    files = {}
    for path in sorted(src.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files[path.relative_to(src).as_posix()] = path.read_bytes()
    files[VERSION_FILE] = __version__.encode()
    return files


def _current(dst: Path):
    if not dst.exists() and not dst.is_symlink():
        return None
    if dst.is_symlink():
        return {"<symlink>": b""}
    files = {}
    for path in sorted(dst.rglob("*")):
        if path.is_symlink():
            return {"<symlink>": b""}
        if path.is_file():
            files[path.relative_to(dst).as_posix()] = path.read_bytes()
    return files


def install() -> str:
    """Return 'installed', 'updated' or 'unchanged'."""
    dst = paths.skill_dir()
    desired = _desired()
    current = _current(dst)
    if current == desired:
        return "unchanged"
    if dst.is_symlink():
        dst.unlink()
    elif dst.exists():
        shutil.rmtree(dst)
    for rel, data in desired.items():
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return "installed" if current is None else "updated"


def installed_version():
    f = paths.skill_dir() / VERSION_FILE
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def remove() -> bool:
    dst = paths.skill_dir()
    if dst.is_symlink():
        dst.unlink()
        return True
    if dst.exists():
        shutil.rmtree(dst)
        return True
    return False
