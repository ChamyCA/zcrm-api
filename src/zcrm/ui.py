"""Terminal interaction helpers (monkeypatched in tests)."""

import getpass
import sys

from zcrm.output import EXIT_USAGE, ZcrmError, emit_text


def is_interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def require_interactive(command: str) -> None:
    if not is_interactive():
        raise ZcrmError(
            "interactive_only",
            f"`zcrm {command}` is interactive and must not be run through Claude.",
            fix=f"Run `zcrm {command}` in your own terminal.",
            exit_code=EXIT_USAGE,
        )


def say(message: str) -> None:
    emit_text(message)


def ask(prompt: str, default=None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_secret(prompt: str) -> str:
    return getpass.getpass(f"{prompt}: ").strip()


def confirm(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")
