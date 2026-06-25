# SpaceCommand / ETSYAI Public Prototype

SpaceCommand is a local-first prototype for organizing Etsy / print-on-demand research, product ideas, listing drafts, QA checks, media planning, and optional API-assisted workflows.

This public version is intentionally clean. It does not include private account information, generated customer/order data, old logs, or real API keys.

## What this prototype includes

- React/Vite dashboard in `ui/`
- Local Express API server in `ui/server.mjs`
- Python workflow helpers in `_core/`
- Room-based folders for research, product ideas, QA, listings, media, and strategy
- `.env.example` templates for users to add their own API keys locally
- Starter `_spacecommand_state/` files with no private history

## What this prototype does not include

- No real Etsy, Printify, Printful, OpenAI, eRank, or EverBee keys
- No live publishing enabled by default
- No previous personal work history
- No `node_modules` or build output

## Setup

```bash
cd ui
npm install
npm run dev
```

Copy `.env.example` to `.env.local` and `ui/.env.example` to `ui/.env.local`, then add only the credentials you own.

See `docs/SETUP.md` and `docs/SECURITY.md` before making your own repo public.

## Safety model

This is meant to be local-first and human-approved. Keep live marketplace actions disabled until you personally review and approve what the system is doing.
