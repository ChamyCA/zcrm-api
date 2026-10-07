"""Interactive profile wizard. Secrets are read with hidden input and stored only in the keyring."""

from zcrm import auth, datacenters, profiles, scopes, secrets, ui
from zcrm.lifecycle import banner
from zcrm.output import EXIT_OK, EXIT_REFUSED, EXIT_CREDENTIAL, ZcrmError


def instructions(profile) -> str:
    dc = profile.dc
    return "\n".join(
        [
            "",
            f"Create a Self Client for profile '{profile.name}' ({dc.suffix} data center):",
            f"  1. Open https://{dc.console_host} and sign in with the Zoho account that owns your DEMO org.",
            "  2. Choose 'Self Client' (Get Started / Add Client), then create it.",
            "  3. Open the 'Client Secret' tab and keep the Client ID and Client Secret handy.",
            "  4. Open the 'Generate Code' tab and enter these scopes:",
            f"       {','.join(profile.scopes)}",
            "     Set the time duration to 10 minutes, add a description (for example 'zcrm'),",
            "     choose your demo org, then click Create and copy the generated code.",
            "  5. Back here, paste the Client ID, Client Secret and the code when asked.",
            "     Input is hidden. Never paste these into a Claude chat.",
            "     (If you already have a refresh token, paste it when asked for one instead.)",
            "",
        ]
    )


def collect_profile(name: str) -> profiles.Profile:
    ui.say(banner.heading("Step 1 of 3 - Name and data center"))
    ui.say(f"Setting up profile '{name}'. Only DEMO orgs are supported.")
    ui.say("Data centers: " + ", ".join(datacenters.suffixes()))
    while True:
        dc = ui.ask("Data center", ".com")
        if datacenters.is_known(dc):
            dc = datacenters.normalize(dc)
            break
        ui.say(f"Unknown data center {dc!r}.")
    ptype = ui.ask("Profile type (only 'demo' is supported)", "demo")
    if ptype != "demo":
        raise ZcrmError(
            "profile_not_demo",
            "zcrm only works with demo orgs. Corp and production orgs are refused.",
            fix="Use a demo org.",
            exit_code=EXIT_REFUSED,
        )
    version = ui.ask("API version", "v8")
    raw_scopes = ui.ask("Scopes (comma-separated)", ",".join(scopes.DEFAULT_SCOPES))
    scope_list = [s.strip() for s in raw_scopes.split(",") if s.strip()]
    return profiles.Profile(name, dc, version, ptype, scope_list)


def run(name: str) -> int:
    profiles.validate_name(name)
    secrets.probe()
    if name in profiles.load_profiles() and not ui.confirm(f"Profile '{name}' already exists. Replace its settings and credentials?"):
        ui.say("Nothing changed.")
        return EXIT_OK
    profile = collect_profile(name)
    # validate before asking for secrets
    profiles._build(
        profile.name,
        {"data_center": profile.data_center, "api_version": profile.api_version, "type": profile.type, "scopes": profile.scopes},
    )
    ui.say(banner.heading("Step 2 of 3 - Create a Self Client in the Zoho API Console"))
    ui.say(instructions(profile))
    ui.say(banner.heading("Step 3 of 3 - Paste your credentials (hidden)"))
    client_id = ui.ask_secret("Client ID")
    client_secret = ui.ask_secret("Client secret")
    refresh = ui.ask_secret("Refresh token (leave blank to paste a grant code instead)")
    if not client_id or not client_secret:
        raise ZcrmError("setup_incomplete", "Client ID and client secret are required.", exit_code=EXIT_CREDENTIAL)
    if not refresh:
        code = ui.ask_secret("Grant code")
        if not code:
            raise ZcrmError("setup_incomplete", "A refresh token or a grant code is required.", exit_code=EXIT_CREDENTIAL)
        ui.say("Exchanging the grant code for a refresh token...")
        refresh = auth.exchange_grant_code(profile, client_id, client_secret, code)
    secrets.clear_cached_token(name)
    secrets.set_credential(name, "client_id", client_id)
    secrets.set_credential(name, "client_secret", client_secret)
    secrets.set_credential(name, "refresh_token", refresh)
    profiles.save_profile(profile)
    ui.say(f"Stored credentials for '{name}' in your OS keyring. Verifying...")
    try:
        auth.get_access_token(profile, force=True)
    except ZcrmError as exc:
        ui.say(f"Credentials are stored, but verification failed: {exc.message} {exc.fix or ''}")
        return EXIT_CREDENTIAL
    ui.say(banner.step("Credentials verified", f"profile '{name}' is ready", last=True))
    return EXIT_OK
