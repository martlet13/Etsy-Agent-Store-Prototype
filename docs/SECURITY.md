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
