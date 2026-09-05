# Security Notes

This repository is designed so users provide their own credentials locally.

Never commit:

- `.env.local`
- real API keys
- OAuth access or refresh tokens
- marketplace account IDs you do not want public
- `local_api_keys.json`
- generated customer/order data
- generated output folders

Before pushing, run:

```bash
git status
git check-ignore -v .env.local ui/.env.local local_api_keys.json _spacecommand_state/local_api_keys.json
```

If a secret ever gets committed, rotate the key immediately in the provider dashboard and remove it from git history before making the repo public.

## Etsy OAuth tokens

`_core/etsy_api_client.py` stores your Etsy access/refresh tokens in
`_spacecommand_state/etsy_oauth_tokens.enc`, encrypted at rest with a
locally generated key kept in `_spacecommand_state/.etsy_token_key`
(file permissions set to owner-read/write only where the OS supports
it). Never commit either file. If `cryptography` isn't installed, the
client still writes both files but falls back to simple XOR
obfuscation instead of real encryption — install it
(`pip install -r requirements.txt`) for real encryption at rest.

If you ever need to disconnect Etsy, delete both files and re-run
`python _core/run_etsy_oauth_setup.py`; if you suspect a token leaked,
revoke it from the app permissions screen in your Etsy account settings
first, then reconnect.

## Live-action gating

Two independent scripts control whether any live, real-world call can
happen:

- `_core/api_connector_manager.py` / `set_api_connector_approval.py` —
  a connector (e.g. `etsy`, `anthropic_content`) only reaches
  `live_enabled` once its secret is present in the environment AND you
  have explicitly set both `user_approved` and `live_actions_enabled`
  to true for it.
- The call site itself (e.g. `create_etsy_draft_listing()` in
  `publishing_dock.py`) additionally requires an explicit
  `user_approved_live_action=True` for that specific call — this is
  why `create_etsy_draft.py` requires the
  `--i-approve-this-live-etsy-action` flag.

Both must hold before any listing is created on your Etsy shop, and
even then it is always created in Etsy's `draft` state — nothing in
this repo activates a listing.
