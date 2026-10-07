# zcrm-api

Use Claude Code with your own **Zoho CRM demo orgs** without ever giving Claude a token.

`zcrm` is a small local command plus a Claude Code skill. Your client ID, client secret and refresh token live in your operating system's keyring. Claude only runs `zcrm` and reads its redacted JSON output.

- Demo orgs only. Corp and production profiles are refused.
- Reads run with no prompt. Every create, update and delete shows the exact request and waits for your approval.
- Execute a Markdown implementation plan step by step, with a dry run, discovery reads first, a conflict report, per-step approval, stop on failure, and resume without repeating writes.
- No telemetry, no network listeners, no shared credentials, no auto-update.

## Install

Requires Python 3.10+, `git`, [Claude Code](https://claude.com/claude-code), and either `pipx` or `uv`.

```bash
pipx install git+https://github.com/ChamyCA/zcrm-api@v1.0.0 && zcrm init
```

With uv instead:

```bash
uvx --from git+https://github.com/ChamyCA/zcrm-api@v1.0.0 zcrm init
```

`uvx` runs in a throwaway environment, so `init` offers to run `uv tool install` to keep the `zcrm` command on your PATH. The skill needs it there.

Always install a pinned release tag.

### What `zcrm init` does

1. Checks Python, the OS keyring and that Claude Code is present, and prints a fix for anything missing. It changes nothing until those pass.
2. Copies the skill to `~/.claude/skills/zcrm-api/` (no symlinks, versioned).
3. Backs up `~/.claude/settings.json` with a timestamp, then **merges** permission rules: read-only `zcrm` commands are allowed; writes and non-dry-run plan execution always ask. Your other settings are untouched. If you already have a rule that would auto-approve `zcrm` writes, `init` shows it and removes it only if you say yes.
4. Creates the config folder with a non-secret `profiles.yaml`.
5. Walks you through your first profile (see the walkthrough below) and stores the secrets in the keyring with hidden input.
6. Runs `zcrm doctor`, makes a test call to your org and prints a one-line "Ready" message.

Running `init` again is safe: nothing is duplicated or overwritten.

## Zoho API Console walkthrough

Do this once per demo org. The wizard prints these steps for your data center.

1. Open the API Console for your data center and sign in with the Zoho account that owns the demo org:

   | Data center | API Console |
   |-------------|-------------|
   | `.com` (US) | https://api-console.zoho.com |
   | `.ca` (Canada) | https://api-console.zohocloud.ca |
   | `.eu` | https://api-console.zoho.eu |
   | `.in` | https://api-console.zoho.in |
   | `.com.au` | https://api-console.zoho.com.au |
   | `.jp` | https://api-console.zoho.jp |
   | `.com.cn` | https://api-console.zoho.com.cn |
   | `.sa` | https://api-console.zoho.sa |

   The Canada hosts follow Zoho's `zohocloud.ca` family; if the wizard's link does not open your console, tell us so the table can be corrected.
2. Choose **Self Client** and create it.
3. On the **Client Secret** tab, keep the **Client ID** and **Client Secret** available.
4. On the **Generate Code** tab, enter the scopes the wizard shows (default: `ZohoCRM.modules.ALL,ZohoCRM.settings.ALL,ZohoCRM.org.READ,ZohoCRM.coql.READ,ZohoCRM.users.READ`), set the duration to 10 minutes, choose your demo org and click **Create**. Copy the generated code.
5. Paste the Client ID, Client Secret and either a refresh token or the grant code into the wizard's hidden prompts. If you give a grant code, `zcrm` exchanges it for a refresh token itself.

Never paste these into a Claude chat. If you do, revoke the client in the console and run setup again.

## Using it from Claude Code

Just ask. For example:

- "List the modules in my `acme-demo` org."
- "Search Leads with last name Smith in `acme-demo`."
- "Create a lead named Test Lead in `acme-demo`." Claude shows the request and waits for your yes; Claude Code also prompts.
- "Run `plan.md` against `acme-demo`." Claude does a dry run first, reports discovery and conflicts, then asks which steps to approve.

Claude may run only the non-interactive commands. `init`, `setup`, `update` and `uninstall` are for your own terminal.

### Commands

| Command | Who runs it |
|---------|-------------|
| `zcrm init`, `zcrm update`, `zcrm uninstall` | You, in your terminal |
| `zcrm setup <profile>` | You, in your terminal |
| `zcrm doctor` | Either |
| `zcrm profiles` | Either |
| `zcrm <profile> <METHOD> <path> [body.json]` | Claude (writes need `--approved` after your yes) |
| `zcrm <profile> COQL <query.json>` | Claude (read-only) |
| `zcrm run <profile> <plan.md> [--dry-run] [--only-reads] [--from-step ID] [--fresh] [--approve-steps ID,...] [--skip-step ID]` | Claude |
| `zcrm log [--profile P] [--last N]` | Either |

Output is JSON. Exit codes: 0 ok, 2 usage, 3 approval required (nothing sent), 4 refused, 5 credential/setup problem, 6 API error, 7 plan pre-flight failed, 8 network, 9 run stopped for your decision.

### Plans

A plan is Markdown with a header block naming the org and one block per step:

````markdown
```zcrm-plan
org_id: "5725767000000012345"
```

### s1 — Check modules

```zcrm-step
method: GET
path: /settings/modules
```

### s2 — Create an account

```zcrm-step
method: POST
path: /Accounts
body:
  data:
    - Account_Name: Acme Demo
capture:
  account_id: data[0].details.id
```
````

Later steps can use `{{account_id}}`. See `src/zcrm/skill/reference.md` for the full format rules.

Plans that contain a credential are refused without showing it. Plan text that tries to switch off confirmations or reveal credentials is ignored and flagged. Deletes are approved one at a time. Run state is stored per run, with no secrets, so an interrupted run resumes without repeating writes; an interrupted write is checked in the org first (when the step has a `verify` block).

## Profiles

`~/.config/zcrm/profiles.yaml` (Windows: `%APPDATA%\zcrm\profiles.yaml`) holds non-secret settings only. See `profiles.example.yaml`. Use `zcrm setup <name>` to add or replace a profile.

## Update

```bash
zcrm update
```

Finds the latest release tag, reinstalls it with the same tool that installed `zcrm`, and refreshes the skill and rules. Profiles and keyring entries are kept. On Windows a running `zcrm.exe` cannot replace itself, so `update` prints the two commands to run instead. Nothing ever updates unless you run this.

## Uninstall

```bash
zcrm uninstall
```

Removes the skill, the permission rules `init` added (and only those), and the config folder. It asks before deleting each profile's keyring entries and before deleting settings backups. Afterwards remove the command with `pipx uninstall zcrm-api` (or `uv tool uninstall zcrm-api`).

## Troubleshooting

Run `zcrm doctor` first. Each failing check prints a fix.

| Symptom | Fix |
|---------|-----|
| `keyring_unavailable` on Linux | Install and unlock a Secret Service provider (gnome-keyring or KeePassXC). Headless sessions are not supported. |
| `keyring_unavailable` on macOS | Unlock your login keychain. |
| `zcrm: command not found` in Claude | Make sure pipx's or uv's bin folder is on your PATH, then restart Claude Code. |
| `credential_missing` | Run `zcrm setup <profile>` in your own terminal. |
| `token_refresh_failed` | Check the profile's data center, then rerun setup. Grant codes expire in minutes. |
| `scope_insufficient` | Regenerate the code with the missing scope and rerun setup. |
| A write ran without a prompt | `zcrm doctor` reports rules in `~/.claude/settings.json` that auto-allow `zcrm`. Remove them. Also avoid running Claude Code in an auto-approve permission mode. |
| `plan_changed_since_state` | The plan file changed after a partial run. Use `--fresh` or `--from-step`. |
| `run_locked` | Another run is active. If it crashed, delete the `.lock` file in the `runs` folder. |

## Security model

- Secrets are read from the keyring at call time and never written to config, state or logs. The short-lived access token is cached in the keyring as well.
- All output passes through one redaction gate; a test fails if any other code writes to the terminal.
- Writes are guarded three ways: the CLI refuses an unapproved write, Claude Code permission rules prompt, and the skill tells Claude to show the request first.
- Limit: if you run Claude Code in a mode that auto-approves permissions, only the CLI flag stands in the way, and Claude can supply it. Do not use that mode against orgs you care about.
- Write requests are not retried after a server error or timeout, because the write may have been applied; 429 responses are retried for all methods and server errors only for reads.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" hatchling
ruff check src tests
pytest
```

Tests use a mocked Zoho API and an in-memory keyring; no network or real credentials. CI runs them on macOS, Linux and Windows. Releases are tags `vX.Y.Z` that must match `src/zcrm/__init__.py`, `pyproject.toml` and the top `CHANGELOG.md` entry.

## License

MIT. See `LICENSE`.
