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
