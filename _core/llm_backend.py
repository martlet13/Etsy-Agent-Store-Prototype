"""
Shared LLM backend dispatcher for SpaceCommand room agents.

Room agents (Nova, Forge, Scribe, Sentinel, Ledger, Strategist, Smith,
Signal, Echo, Command, Archivist, Overseer) previously called a local
Ollama model directly. This module adds a second, optional backend that
calls Claude (Anthropic's official Messages API) using the seller's own
ANTHROPIC_API_KEY, so a seller who has a Claude account/API key can run
the whole room-agent system against Claude instead of installing Ollama
or automating a ChatGPT web session.

Design principles carried over from the rest of this repo:
- Local-first: this file makes one outbound HTTPS call per invocation,
  directly from the seller's machine, using only the seller's own key.
- No vendor proxy: nothing is routed through any SpaceCommand/vendor
  server. The only network calls are to api.anthropic.com (Claude) or
  to the local Ollama daemon (127.0.0.1).
- Fail loud: missing keys or failed calls raise a clear error rather
  than silently falling back to a different backend.
"""

import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"

# A Claude model alias. Aliases such as this track the latest snapshot of
# that model family, so this does not need to be updated as new dated
# snapshots ship. Override with the ANTHROPIC_MODEL env var, or the
# --claude-model flag on any room-agent runner, if your account needs a
# specific dated model id instead (see docs.claude.com/en/docs/about-claude/models).
DEFAULT_CLAUDE_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def get_anthropic_api_key() -> Optional[str]:
    return os.environ.get("ANTHROPIC_API_KEY")


def resolve_backend(requested: Optional[str] = None) -> str:
    """
    Decide which backend to use for this call.

    Priority: explicit --backend flag > LLM_BACKEND env var > auto-detect
    (Claude if a key is present, otherwise Ollama).
    """
    if requested in {"claude", "ollama"}:
        return requested

    env_choice = os.environ.get("LLM_BACKEND", "").strip().lower()
    if env_choice in {"claude", "ollama"}:
        return env_choice

    if get_anthropic_api_key():
        return "claude"

    return "ollama"


def call_ollama(model: str, prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Ollama call failed.")

    return result.stdout.strip()


def _require_api_key() -> str:
    api_key = get_anthropic_api_key()

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your local .env.local "
            "(see docs/SETUP.md) to use the Claude backend, or pass "
            "--backend ollama to use a local Ollama model instead."
        )

    return api_key


def _call_anthropic_messages(payload: Dict[str, Any], api_key: str) -> str:
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Claude API call failed ({exc.code}): {raw_error}") from exc
    except Exception as exc:
        raise RuntimeError(f"Claude API call failed: {exc!r}") from exc

    parts = data.get("content", [])
    text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]

    if not text_parts:
        raise RuntimeError(f"Claude API returned no text content: {json.dumps(data)[:2000]}")

    return "\n".join(text_parts).strip()


def call_claude(model: str, prompt: str, max_tokens: int = 4096) -> str:
    api_key = _require_api_key()

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    return _call_anthropic_messages(payload, api_key)


_IMAGE_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def call_claude_vision(model: str, prompt: str, image_path: str, max_tokens: int = 2048) -> str:
    """
    Send one image plus a text prompt to Claude (vision) and return its text
    response. Used for QA/evaluation of an image, not for generating one -
    Claude has no image generation API (see qwen_edit_style_transfer.py /
    openai_image_provider.py / ComfyUI for that).
    """
    api_key = _require_api_key()

    path = Path(image_path)
    if not path.exists():
        raise RuntimeError(f"Image file not found: {image_path}")

    ext = path.suffix.lower().lstrip(".")
    media_type = _IMAGE_MEDIA_TYPES.get(ext)
    if not media_type:
        raise RuntimeError(f"Unsupported image type '{ext}' for Claude vision: {image_path}")

    image_b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }

    return _call_anthropic_messages(payload, api_key)


def call_llm(
    prompt: str,
    backend: Optional[str] = None,
    ollama_model: Optional[str] = None,
    claude_model: Optional[str] = None,
) -> str:
    resolved = resolve_backend(backend)

    if resolved == "claude":
        return call_claude(claude_model or DEFAULT_CLAUDE_MODEL, prompt)

    return call_ollama(ollama_model or DEFAULT_OLLAMA_MODEL, prompt)
