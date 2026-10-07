"""Command routing for `zcrm`."""

import json
import sys

from zcrm import __version__, audit, client, policy, profiles, scopes, ui
from zcrm.output import (
    EXIT_APPROVAL,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    ZcrmError,
    emit_json,
    emit_text,
)

USAGE = """usage: zcrm <command>

  zcrm init | update | uninstall      (run in your own terminal)
  zcrm setup <profile>                (run in your own terminal)
  zcrm doctor
  zcrm profiles
  zcrm <profile> <METHOD> <path> [body.json] [--approved]
  zcrm <profile> COQL <query.json>      (read-only COQL query)
  zcrm run <profile> <plan.md> [--dry-run] [--only-reads] [--from-step ID] [--fresh]
                               [--approve-steps ID[,ID...]] [--skip-step ID]
  zcrm log [--profile P] [--last N]
  zcrm --version
"""

COMMANDS = {"init", "update", "uninstall", "setup", "doctor", "profiles", "run", "log", "_refresh"}


def usage_error(message: str) -> ZcrmError:
    return ZcrmError("usage", message, fix="Run `zcrm --help` for usage.", exit_code=EXIT_USAGE)


def parse_flags(args, spec):
    """spec: {flag: takes_value}. Only the space-separated form is accepted."""
    positional, options = [], {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            if "=" in arg:
                raise usage_error(f"Use `{arg.split('=')[0]} VALUE` (space-separated), not `{arg.split('=')[0]}=...`.")
            if arg not in spec:
                raise usage_error(f"Unknown option {arg}.")
            if spec[arg]:
                i += 1
                if i >= len(args) or args[i].startswith("--"):
                    raise usage_error(f"{arg} needs a value.")
                options[arg] = args[i]
            else:
                options[arg] = True
        else:
            positional.append(arg)
        i += 1
    return positional, options


def _load_body(path):
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        raise usage_error(f"Cannot read body file {path!r}.")
    from zcrm.plan import scan

    if scan.find_credentials(text):
        raise ZcrmError(
            "body_credential_found",
            "The body file appears to contain a credential, so it was not sent.",
            fix="Remove the credential from the body file.",
            exit_code=EXIT_REFUSED,
        )
    try:
        return json.loads(text)
    except ValueError:
        raise usage_error(f"Body file {path!r} is not valid JSON.")


def single_call(args) -> int:
    positional, options = parse_flags(args, {"--approved": False})
    if len(positional) == 3 and positional[1] == "COQL":
        name, method, path, body_path = positional[0], "POST", "/coql", positional[2]
    elif len(positional) in (3, 4):
        name, method, path = positional[:3]
        body_path = positional[3] if len(positional) == 4 else None
    else:
        raise usage_error("Expected: zcrm <profile> <METHOD> <path> [body.json]  or  zcrm <profile> COQL <query.json>")
    profile = profiles.require_demo(profiles.get(name))
    policy.validate_method(method)
    path = policy.normalize_path(path)
    kind = policy.classify(method, path)
    policy.check_bulk_delete(method, path)
    body = _load_body(body_path)
    warnings = []
    state, needed = scopes.check(profile.scopes, method, path)
    if state == "missing":
        warnings.append(f"Profile {name!r} may lack scope {needed}.")
    if policy.is_write(kind) and not options.get("--approved"):
        preview = {"method": method, "url": client.build_url(profile, path), "body_summary": policy.body_summary(body)}
        if ui.is_interactive():
            emit_text(f"About to send: {method} {preview['url']} ({preview['body_summary']})")
            if not ui.confirm("Send this request?"):
                raise ZcrmError("approval_declined", "Request not sent.", exit_code=EXIT_APPROVAL, request=preview)
        else:
            raise ZcrmError(
                "approval_required",
                "This request changes data and was not sent. It needs the user's approval.",
                fix="Show the exact request to the user; after they approve, rerun with --approved.",
                exit_code=EXIT_APPROVAL,
                request=preview,
            )
    resp = client.request(profile, method, path, body)
    errors = client.embedded_errors(resp.data)
    if errors:
        raise ZcrmError(
            "record_error",
            "Zoho accepted the request but reported errors for one or more items.",
            exit_code=6,
            status=resp.status,
            data=resp.data,
        )
    envelope = {"ok": True, "profile": name, "status": resp.status, "data": resp.data}
    if warnings:
        envelope["warnings"] = warnings
    emit_json(envelope)
    return EXIT_OK


def cmd_profiles(args) -> int:
    parse_flags(args, {})
    items = []
    from zcrm import secrets

    for p in profiles.load_profiles().values():
        entry = p.public()
        entry["credentials_stored"] = secrets.has_credentials(p.name)
        items.append(entry)
    emit_json({"ok": True, "profiles": items})
    return EXIT_OK


def cmd_log(args) -> int:
    positional, options = parse_flags(args, {"--profile": True, "--last": True})
    if positional:
        raise usage_error("zcrm log takes only --profile and --last.")
    last = None
    if "--last" in options:
        try:
            last = int(options["--last"])
            if last < 1:
                raise ValueError
        except ValueError:
            raise usage_error("--last needs a positive number.")
    emit_json({"ok": True, "entries": audit.read_entries(options.get("--profile"), last)})
    return EXIT_OK


def cmd_run(args) -> int:
    flags = {
        "--dry-run": False,
        "--only-reads": False,
        "--fresh": False,
        "--from-step": True,
        "--approve-steps": True,
        "--skip-step": True,
    }
    positional, options = parse_flags(args, flags)
    if len(positional) != 2:
        raise usage_error("Expected: zcrm run <profile> <plan.md> [options]")
    if (options.get("--dry-run") or options.get("--only-reads")) and (
        "--approve-steps" in options or "--skip-step" in options
    ):
        raise usage_error("--dry-run and --only-reads cannot be combined with --approve-steps or --skip-step.")
    from zcrm.plan import runner

    envelope, code = runner.run_plan(
        positional[0],
        positional[1],
        dry_run=bool(options.get("--dry-run")),
        only_reads=bool(options.get("--only-reads")),
        fresh=bool(options.get("--fresh")),
        from_step=options.get("--from-step"),
        approve_steps=[s for s in options.get("--approve-steps", "").split(",") if s],
        skip_steps=[s for s in options.get("--skip-step", "").split(",") if s],
    )
    emit_json(envelope)
    return code


def cmd_doctor(args) -> int:
    parse_flags(args, {})
    from zcrm.lifecycle import doctor

    checks = doctor.run_checks()
    ok = all(c["ok"] for c in checks)
    emit_json({"ok": ok, "checks": checks})
    return EXIT_OK if ok else 5


def dispatch(argv) -> int:
    if not argv:
        emit_text(USAGE)
        return EXIT_USAGE
    head = argv[0]
    if head in ("-h", "--help", "help"):
        emit_text(USAGE)
        return EXIT_OK
    if head == "--version":
        emit_json({"ok": True, "version": __version__})
        return EXIT_OK
    if head in COMMANDS:
        rest = argv[1:]
        if head == "profiles":
            return cmd_profiles(rest)
        if head == "log":
            return cmd_log(rest)
        if head == "run":
            return cmd_run(rest)
        if head == "doctor":
            return cmd_doctor(rest)
        ui.require_interactive(head)
        if head == "init":
            from zcrm.lifecycle import init

            parse_flags(rest, {})
            return init.run()
        if head == "setup":
            from zcrm.lifecycle import setup

            positional, _ = parse_flags(rest, {})
            if len(positional) != 1:
                raise usage_error("Expected: zcrm setup <profile>")
            return setup.run(positional[0])
        if head == "_refresh":
            from zcrm.lifecycle import update

            return update.refresh()
        if head == "update":
            from zcrm.lifecycle import update

            parse_flags(rest, {})
            return update.run()
        from zcrm.lifecycle import uninstall

        parse_flags(rest, {})
        return uninstall.run()
    return single_call(argv)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return dispatch(argv)
    except ZcrmError as exc:
        emit_json(exc.envelope())
        return exc.exit_code
    except KeyboardInterrupt:
        emit_text("Interrupted.")
        return 130
    except Exception as exc:  # last resort: never show a traceback, always redact
        emit_json({"ok": False, "error": {"code": "internal_error", "message": f"{type(exc).__name__}: {exc}"}})
        return 1
