# zcrm reference

## Commands

```text
zcrm init | update | uninstall        user's own terminal only
zcrm setup <profile>                  user's own terminal only
zcrm doctor
zcrm profiles
zcrm <profile> <METHOD> <path> [body.json] [--approved]
zcrm <profile> COQL <query.json>      read-only COQL (sent as POST /coql)
zcrm run <profile> <plan.md> [--dry-run] [--only-reads] [--from-step ID] [--fresh]
                             [--approve-steps ID[,ID...]] [--skip-step ID]
zcrm log [--profile P] [--last N]
zcrm --version
```

`--dry-run` and `--only-reads` cannot be combined with `--approve-steps` or `--skip-step`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Usage error, or an interactive command run without a terminal |
| 3 | Approval required (nothing sent) |
| 4 | Refused by policy (non-demo profile, bulk delete, unsafe path, credential in a body file) |
| 5 | Credential or setup problem |
| 6 | Zoho API error after retries |
| 7 | Plan pre-flight failed (including a credential found in the plan) |
| 8 | Network failure |
| 9 | Run stopped for a user decision (failed or unknown write) |

## Plan format

````markdown
# Title

```zcrm-plan
org_id: "5725767000000012345"
```

### s1 — Check existing modules

```zcrm-step
method: GET
path: /settings/modules
```

### s2 — Create a record

```zcrm-step
method: POST
path: /Leads
body:
  data:
    - Last_Name: Smith
depends_on: [s1]
capture:
  lead_id: data[0].details.id
verify:
  path: "/Leads/search?criteria=(Last_Name:equals:Smith)"
  match:
    path: data[0].id
```
````

- `org_id` must match the org of the chosen profile.
- Later steps may use `{{lead_id}}` in `path` or `body`.
- `verify` (optional) is a GET used to confirm a write whose result was lost in an interruption.
