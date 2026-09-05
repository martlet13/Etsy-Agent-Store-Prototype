# Setup

1. Install Node.js 20 or newer and Python 3.11 or newer.
2. Clone or download this repo.
3. Copy `.env.example` to `.env.local` in the project root.
4. Copy `ui/.env.example` to `ui/.env.local`.
5. Fill in only the API keys and account values you personally own.
6. Install the UI dependencies:

```bash
cd ui
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The local API server uses port `4521` and the UI uses port `4520` by default.

## Important

The public prototype starts with live connectors disabled. Use it as a local tool first. Do not enable posting, publishing, buying, selling, or messaging until you have tested the workflow and understand the API permissions.

## Content generation with Claude (instead of Ollama or a ChatGPT web session)

By default the room agents (Nova, Forge, Scribe, Sentinel, etc. in `_core/run_*.py`)
call a local Ollama model. If you'd rather use Claude:

1. Install the one extra Python dependency: `pip install -r requirements.txt`.
2. Get an API key at https://console.anthropic.com and put it in
   `ANTHROPIC_API_KEY` in your `.env.local`.
3. That's it — `_core/llm_backend.py` automatically prefers Claude once
   a key is present. Every room-agent runner also accepts
   `--backend claude|ollama` and `--claude-model <id>` if you want to
   force one explicitly for a single run.
4. Approve the connector so status checks reflect reality:
   `python _core/set_api_connector_approval.py --connector-id anthropic_content --user-approved true --live-actions-enabled true`

The actual Etsy listing copy (title/description/tags) is generated the
same way — see `_core/run_scribe_on_design.py` — with a deterministic
template as an automatic fallback if the LLM call fails or isn't
configured, so the pipeline never hard-stops on a missing key.

## Connecting your own Etsy shop and creating a real draft listing

1. Create your own app at https://www.etsy.com/developers/your-apps.
   Set its redirect URI to `http://localhost:4522/callback` (or set
   your own value and put it in `ETSY_REDIRECT_URI`).
2. Put the app's keystring in `ETSY_API_KEY` and its shared secret in
   `ETSY_CLIENT_SECRET` in `.env.local`, along with your shop's numeric
   ID in `ETSY_SHOP_ID` (find it via the Etsy API or your shop's admin
   URL).
3. Run the one-time OAuth wizard from the project root:
   ```bash
   cd _core
   python run_etsy_oauth_setup.py
   ```
   This opens a browser tab for you to approve access to your own shop,
   then stores an encrypted token locally (see docs/SECURITY.md).
4. Approve the connector:
   ```bash
   python set_api_connector_approval.py --connector-id etsy --user-approved true --live-actions-enabled true
   ```
5. Run the normal local pipeline (evidence → opportunity → design →
   Ledger PASS → `run_scribe_on_design.py` → `create_publish_package.py`)
   until you have a `publish_package` with no issues.
6. Create the real draft listing (this is the only script in the repo
   that writes to Etsy, and it only ever creates a `draft`):
   ```bash
   python create_etsy_draft.py \
     --publish-package-id PUBPKG-0001 \
     --taxonomy-id <etsy_taxonomy_id> \
     --i-approve-this-live-etsy-action
   ```
   Look up taxonomy IDs for your product type with
   `etsy_api_client.get_seller_taxonomy_nodes()`, and shipping
   profile / return policy / shop section IDs with the matching
   `get_shipping_profiles()` / `get_return_policies()` /
   `get_shop_sections()` helpers in the same file.
7. Open the printed draft URL in Etsy Seller Manager, review it, and
   activate it yourself when you're happy with it. Nothing in this
   repo can do that step for you.
