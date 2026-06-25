# Desktop Packaging Notes

SpaceCommand is being prepared as a local desktop operator app. The current app remains a Vite UI plus local Node server; this file is a planning note only and does not change the current build scripts.

## Future EXE Direction

- Package the UI and local server as a Windows desktop EXE using Electron or Tauri.
- Start the local server automatically when the desktop app opens.
- Keep generated art, production data, sales data, and package files on the local machine.
- Keep secrets local and server-side. Do not expose API keys or tokens to the browser client.
- Add a tray icon later so SpaceCommand can keep working while minimized.
- Add tray actions later for Start Shift and Stop.
- Preserve the browser UI during development until the desktop wrapper is stable.

## Local Dependencies

- ComfyUI must remain installed and reachable locally for Forge artwork generation.
- Forge should keep producing PNG artwork only.
- Printify, Printful, and Etsy credentials should continue to live in local secret/env files.
- The desktop wrapper should document how to start or detect ComfyUI before starting a shift.

## Packaging Candidates

- Electron: easiest path for bundling the existing Vite UI and Node server together.
- Tauri: smaller desktop shell, but requires additional Rust/toolchain setup and a careful local-server strategy.

## Current Scripts

No package scripts were added in this patch. Current development and build commands remain unchanged:

- `npm run dev`
- `npm run build`
- `npm run server`
- `npm run ui`
