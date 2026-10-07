"""Terminal banner, boxes and step tree for `zcrm init` and `zcrm setup`. No dependencies."""

import os
import re
import shutil

from zcrm.output import stream_is_tty

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_GLYPHS = {
    "Z": ["█████", "   █ ", "  █  ", " █   ", "█████"],
    "C": [" ████", "█    ", "█    ", "█    ", " ████"],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
}
_GRADIENT = [75, 81, 80, 116, 254]


def color_on() -> bool:
    if os.environ.get("ZCRM_COLOR") == "1":
        return True
    return stream_is_tty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def c(text: str, code) -> str:
    if not color_on():
        return text
    seq = f"38;5;{code}" if isinstance(code, int) else code
    return f"\033[{seq}m{text}\033[0m"


def vlen(text: str) -> int:
    return len(_ANSI.sub("", text))


def logo() -> str:
    rows = []
    for r in range(5):
        line = "   ".join("".join("██" if ch == "█" else "  " for ch in _GLYPHS[letter][r]) for letter in "ZCRM")
        rows.append(c(line.rstrip(), _GRADIENT[r]))
    return "\n".join(rows)


def tagline() -> str:
    return c("Zoho CRM API for Claude Code - demo orgs only, no tokens in chat", "3;33")


def width() -> int:
    return max(60, min(shutil.get_terminal_size((100, 24)).columns - 2, 100))


def box(title: str, rows: list, color=37) -> str:
    inner = width() - 2
    label = f" {title} "
    left = (inner - vlen(label)) // 2
    top = "┌" + "─" * left + c(label, color) + "─" * (inner - left - vlen(label)) + "┐"
    body = ["│" + " " * inner + "│"]
    for row in rows:
        body.append("│  " + row + " " * max(0, inner - 2 - vlen(row)) + "│")
    body.append("│" + " " * inner + "│")
    bottom = "└" + "─" * inner + "┘"
    return "\n".join([c(top, color)] + [c(b[0], color) + b[1:-1] + c(b[-1], color) for b in body] + [c(bottom, color)])


def heading(text: str) -> str:
    return "\n" + c(text, "1;36")


def step(label: str, detail: str = "", last: bool = False, ok: bool = True) -> str:
    branch = "└──" if last else "├──"
    dot = c("●", 32 if ok else 31)
    extra = " " + c(f"({detail})", 90) if detail else ""
    return f"{c(branch, 90)} {dot} {label}{extra}"


def kv(key: str, value: str) -> str:
    return f"{key:<16}{c(value, 90)}"
