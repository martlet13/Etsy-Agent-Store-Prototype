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

## Generating art without ComfyUI/a GPU

The dashboard's automatic "Products Being Worked On" loop calls ComfyUI at
`http://127.0.0.1:8188` for art and will show "Waiting for setup" until
that's reachable. If you don't have a GPU for ComfyUI, generate art
manually instead (CLI-only, not wired into the dashboard loop yet):

```bash
cd _core
python create_image_generation_request.py --design-package-id DESIGN-0001 \
  --subject "..." --composition "..." --style "..." --color-palette "..." \
  --text-rules "..." --product-use "..." --aspect-ratio "3:4" \
  --negative-constraints "..." --quality-bar "..."

python run_image_generation_provider.py --image-request-id IMGREQ-0001 --mode live_api
```

This uses OpenAI's Images API (`openai_image_provider.py`) — set
`OPENAI_API_KEY` in `.env.local` and enable the live image budget flag
(see `image_generation_budget.py` / `_spacecommand_state/image_api_budget.json`)
first. It has no GPU requirement and doesn't depend on ComfyUI at all.

### Optional: restyle an existing photo with a community Hugging Face Space

If you already have a product photo and just want to restyle it (anime,
polaroid, pixar, studio relight, upscale, etc.), `run_qwen_edit_style_transfer.py`
calls the public community Space
[prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast](https://huggingface.co/spaces/prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast).
This edits an existing image — it does not generate art from scratch, so
it's a style pass on top of art you already have, not a ComfyUI/OpenAI
replacement.

```bash
pip install gradio_client
cd _core
python run_qwen_edit_style_transfer.py \
  --image-request-id IMGREQ-0001 \
  --input-image /path/to/your/photo.png \
  --prompt "Transform into anime." \
  --lora-adapter Photo-to-Anime
```

This calls a free third-party community demo (shared HF ZeroGPU) — it can
queue, rate-limit, change its API, or go away without notice. It is not a
paid/guaranteed API like OpenAI Images or your own ComfyUI, so don't rely
on it as your only art source or wire it into an unattended loop. Every
result still lands as a normal `image_asset` pending Sentinel Visual QA,
exactly like any other image source in this repo.

## Using Claude to review generated art (Visual QA)

Claude has no image-generation API (Anthropic doesn't offer a
text-to-image model), so it cannot replace ComfyUI/OpenAI/the Qwen-Edit
Space above. It *can* look at an already-generated image (vision) and
judge it against the same checklist a human Sentinel reviewer uses.
`_core/run_claude_visual_qa.py` does this — it never writes a QA report by
itself; you choose how its proposal gets finalized:

```bash
cd _core
# 1. See what Claude thinks, without writing anything:
python run_claude_visual_qa.py --image-asset-id IMGASSET-0001

# 2a. Autonomous — writes immediately, no human step. Requires an explicit
#     accept flag so this is never the accidental default:
python run_claude_visual_qa.py --image-asset-id IMGASSET-0001 \
  --mode autonomous --i-accept-autonomous-visual-qa

# 2b. Client-confirmed — shows the proposal, lets you edit any field, then
#     asks for a typed YES before writing (recommended for real listings):
python run_claude_visual_qa.py --image-asset-id IMGASSET-0001 --mode client_confirm
```

Either way, the actual pass/fail gate (score thresholds, the
blocking-checks list, the design production-gate check) is the same
`sentinel_visual_qa.py` logic a manual `create_visual_qa_report.py` run
uses — Claude only supplies the inputs a human would have typed, it does
not weaken the gate. The written report always records which path was
used (`reviewer: "Claude (autonomous)"` or `"Claude (human-confirmed)"`)
so it's traceable later who/what approved an asset.

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
