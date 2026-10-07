"""Markdown plan parser. Only the zcrm-plan header and zcrm-step blocks are parsed."""

import hashlib
import re
from dataclasses import dataclass, field

import yaml

from zcrm import policy
from zcrm.output import EXIT_PLAN, ZcrmError
from zcrm.plan.util import VAR_RE, find_vars

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
STEP_KEYS = {"method", "path", "body", "depends_on", "capture", "verify"}
HEADER_KEYS = {"org_id", "title"}
_OPEN = re.compile(r"^(`{3,})\s*(\S*)\s*$")
_HEADING = re.compile(r"^###\s+(\S+)(?:\s*[—–-]+\s*(.*))?\s*$")
_BRACES_SPACE = re.compile(r"\{\{\s+|\s+\}\}")


@dataclass
class Step:
    id: str
    description: str
    method: str
    path: str
    body: object
    depends_on: list
    capture: dict
    verify: dict
    kind: str
    line: int
    position: int


@dataclass
class Plan:
    org_id: str
    title: str
    steps: list
    sha256: str
    text: str = field(repr=False, default="")


def _blocks(text: str):
    """Return ([(info, content, start_line)], [(line, heading_text)]) skipping fenced regions for headings."""
    lines = text.splitlines()
    blocks, headings = [], []
    i = 0
    while i < len(lines):
        m = _OPEN.match(lines[i])
        if m:
            ticks, info = len(m.group(1)), m.group(2)
            start = i + 1
            j = i + 1
            while j < len(lines):
                close = re.match(r"^(`{3,})\s*$", lines[j])
                if close and len(close.group(1)) >= ticks:
                    break
                j += 1
            blocks.append((info, "\n".join(lines[start:j]), i + 1))
            i = j + 1
            continue
        if lines[i].startswith("###"):
            headings.append((i + 1, lines[i]))
        i += 1
    return blocks, headings


def parse(text: str) -> Plan:
    errors = []

    def err(line, message):
        errors.append({"line": line, "message": message})

    blocks, headings = _blocks(text)
    header_blocks = [b for b in blocks if b[0] == "zcrm-plan"]
    org_id, title = None, ""
    if not header_blocks:
        err(1, "missing ```zcrm-plan header block with org_id")
    else:
        info, content, line = header_blocks[0]
        try:
            data = yaml.safe_load(content) or {}
        except yaml.YAMLError:
            data = None
            err(line, "zcrm-plan header is not valid YAML")
        if isinstance(data, dict):
            for key in data:
                if key not in HEADER_KEYS:
                    err(line, f"unknown header key {key!r}")
            if not data.get("org_id"):
                err(line, "header needs org_id")
            else:
                org_id = str(data["org_id"])
            title = str(data.get("title", ""))
        elif data is not None:
            err(line, "zcrm-plan header must be a mapping")

    steps, seen, captured = [], {}, set()
    step_blocks = [b for b in blocks if b[0] == "zcrm-step"]
    owners = {}
    for info, content, line in step_blocks:
        heading = None
        for hline, htext in headings:
            if hline < line:
                heading = (hline, htext)
        if heading is None:
            err(line, "zcrm-step block has no ### heading before it")
            continue
        if heading[0] in owners:
            err(line, "more than one zcrm-step block under the same heading")
            continue
        owners[heading[0]] = True
        m = _HEADING.match(heading[1])
        sid = m.group(1) if m else heading[1][3:].strip().split()[0] if heading[1][3:].strip() else ""
        desc = (m.group(2) or "").strip() if m else ""
        if not ID_RE.match(sid):
            err(heading[0], f"invalid step id {sid!r} (use letters, digits, - and _; write '### s1 — description')")
            continue
        if sid in seen:
            err(heading[0], f"duplicate step id {sid!r}")
            continue
        try:
            raw = yaml.safe_load(content) or {}
        except yaml.YAMLError:
            err(line, f"step {sid}: block is not valid YAML")
            continue
        if not isinstance(raw, dict):
            err(line, f"step {sid}: block must be a mapping")
            continue
        bad = False
        for key in raw:
            if key not in STEP_KEYS:
                err(line, f"step {sid}: unknown key {key!r}")
                bad = True
        method, path = raw.get("method"), raw.get("path")
        try:
            policy.validate_method(method if isinstance(method, str) else "")
            if not isinstance(path, str):
                raise ZcrmError("usage", "path must be a string")
            if _BRACES_SPACE.search(path):
                raise ZcrmError("usage", "write variables as {{name}} without spaces")
            policy.normalize_path(path)
            policy.check_bulk_delete(method, path)
        except ZcrmError as exc:
            err(line, f"step {sid}: {exc.message}")
            continue
        body = raw.get("body")
        if body is not None and not isinstance(body, dict):
            err(line, f"step {sid}: body must be an object")
            bad = True
        deps = raw.get("depends_on", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            err(line, f"step {sid}: depends_on must be a list of step ids")
            deps, bad = [], True
        for d in deps:
            if d not in seen:
                err(line, f"step {sid}: depends_on {d!r} is not an earlier step")
                bad = True
        capture = raw.get("capture", {}) or {}
        if not isinstance(capture, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in capture.items()):
            err(line, f"step {sid}: capture must map variable names to JSON paths")
            capture, bad = {}, True
        verify = raw.get("verify") or {}
        if verify:
            vp = verify.get("path") if isinstance(verify, dict) else None
            match = verify.get("match") if isinstance(verify, dict) else None
            ok = (
                isinstance(verify, dict)
                and set(verify) <= {"path", "match"}
                and isinstance(vp, str)
                and isinstance(match, dict)
                and set(match) <= {"path", "equals", "status"}
                and (isinstance(match.get("path"), str) or isinstance(match.get("status"), int))
            )
            if ok:
                try:
                    policy.normalize_path(vp)
                except ZcrmError as exc:
                    err(line, f"step {sid}: verify {exc.message}")
                    ok = False
            if not ok:
                err(line, f"step {sid}: verify needs a GET 'path' and a 'match' with 'path' (optional 'equals') or 'status'")
                bad = True
        used = find_vars(path) | find_vars(body) | (find_vars(verify) if verify else set())
        for var in sorted(used - captured):
            err(line, f"step {sid}: variable {{{{{var}}}}} is not captured by an earlier step")
            bad = True
        if bad:
            continue
        seen[sid] = True
        captured |= set(capture)
        steps.append(
            Step(sid, desc, method, path, body, deps, capture, verify, policy.classify(method, path), line, len(steps) + 1)
        )
    if not step_blocks:
        err(1, "plan has no zcrm-step blocks")
    if errors:
        raise ZcrmError(
            "plan_parse_error",
            f"The plan has {len(errors)} problem(s); see 'errors' for line numbers.",
            fix="Fix the plan (see reference.md) and retry.",
            exit_code=EXIT_PLAN,
            errors=errors,
        )
    return Plan(org_id, title, steps, hashlib.sha256(text.encode("utf-8")).hexdigest(), text)


__all__ = ["Plan", "Step", "parse", "VAR_RE"]
