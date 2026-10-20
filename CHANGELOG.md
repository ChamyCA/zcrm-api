# Changelog

## 1.1.1 - 2026-10-20

- Fix: commands no longer fail with `internal_error` (PasswordSetError) in sandboxes where the keychain is readable but not writable. The access-token cache is best-effort (memory, then a 0600 `token-cache.json`).
- `zcrm doctor` reports keychain read and write status separately; unreadable credentials now hint at sandbox exclusion.

## 1.1.0 - 2026-10-07

- `zcrm init` now shows a ZCRM banner, a setup summary box, a step-by-step install tree, a guided 3-step first-profile wizard and a Next Steps box. Plain text when output is not a terminal or `NO_COLOR` is set.

## 1.0.0 - 2026-10-07

- Initial release: `zcrm` CLI and Claude Code skill for Zoho CRM demo orgs.
