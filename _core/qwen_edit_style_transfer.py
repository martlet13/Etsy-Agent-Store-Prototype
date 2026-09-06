"""
Optional style-transfer helper backed by a public community Hugging Face
Space (prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast).

This is NOT a replacement for Forge's normal art generation (ComfyUI or
openai_image_provider.py). Those generate a product image from a text
prompt. This Space edits an image you already have — apply a LoRA style
(anime, polaroid, pixar, studio relight, upscale, etc.) to an existing
product photo/mockup. Use it as an optional creative post-process step,
never as the primary source of listing art.

Important limits, on purpose, not bugs:
- This calls a third-party community demo running on shared/free HF
  ZeroGPU. It can queue, rate-limit, change its API, or disappear at any
  time — nothing here is a guaranteed or paid API, unlike OpenAI Images
  or your own ComfyUI. Do not wire this into an unattended/automated
  loop; run it manually, per image, and expect it to occasionally fail.
- Every result is recorded as a normal image_asset with
  status=generated_pending_visual_qa — it still has to pass Sentinel
  Visual QA before it can be used as a mockup or product image, exactly
  like every other image source in this repo.

Setup: pip install gradio_client (see requirements.txt).
"""

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from forge_image_kernel import IMAGE_REQUESTS_FILE, load_json, record_image_asset
from image_generation_budget import find_by_id


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
GENERATED_ASSETS_DIR = STATE / "generated_assets"

DEFAULT_SPACE_ID = "prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast"

# Keys must match ADAPTER_SPECS in that Space's app.py exactly (as of the
# version this was built against). If the Space owner renames/removes a
# style, pass --lora-adapter with the current name from the Space's UI —
# this list is only used for local validation/help text.
LORA_ADAPTERS = [
    "Multiple-Angles",
    "Photo-to-Anime",
    "Anime-V2",
    "Light-Migration",
    "Upscaler",
    "Style-Transfer",
    "Manga-Tone",
    "Anything2Real",
    "Fal-Multiple-Angles",
    "Polaroid-Photo",
    "Unblur-Anything",
    "Midnight-Noir-Eyes-Spotlight",
    "Hyper-Realistic-Portrait",
    "Ultra-Realistic-Portrait",
    "Pixar-Inspired-3D",
    "Noir-Comic-Book",
    "Any-light",
    "Studio-DeLight",
    "Cinematic-FlatLog",
]


class QwenEditSpaceError(RuntimeError):
    pass


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename(raw: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(raw))
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:90] or "qwen_edit_image"


def _image_path_to_data_uri(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise QwenEditSpaceError(f"Input image not found: {path}")

    ext = file_path.suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/png")
    data = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _get_image_request(image_request_id: str) -> Optional[Dict[str, Any]]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    return find_by_id(requests, image_request_id)


def run_qwen_edit_style_transfer(
    image_request_id: str,
    input_image_paths: List[str],
    prompt: str,
    lora_adapter: str,
    seed: int = 0,
    randomize_seed: bool = True,
    guidance_scale: float = 4.0,
    steps: int = 30,
    space_id: str = DEFAULT_SPACE_ID,
    hf_token: Optional[str] = None,
) -> Dict[str, Any]:
    if lora_adapter not in LORA_ADAPTERS:
        raise QwenEditSpaceError(
            f"Unknown lora_adapter '{lora_adapter}'. Known styles: {', '.join(LORA_ADAPTERS)}. "
            "If the Space added a new one, pass its exact name from the Space's UI."
        )

    if not input_image_paths:
        raise QwenEditSpaceError("At least one input image path is required — this Space edits existing images.")

    request = _get_image_request(image_request_id)
    if not request:
        raise QwenEditSpaceError(f"No image_request found with id {image_request_id}.")

    # Imported here (not at module load) so this file still imports cleanly
    # on machines that haven't installed gradio_client yet.
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise QwenEditSpaceError(
            "gradio_client is not installed. Run: pip install gradio_client (see requirements.txt)."
        ) from exc

    # Anonymous callers share a very small free ZeroGPU quota and will
    # commonly hit "You have exceeded your ZeroGPU runs limit." Passing your
    # own (free) Hugging Face token raises that quota significantly. Get one
    # at https://huggingface.co/settings/tokens and set HF_TOKEN in
    # .env.local, or pass hf_token explicitly.
    resolved_token = hf_token or os.environ.get("HF_TOKEN")
    client = Client(space_id, token=resolved_token)

    safety = client.predict(prompt, api_name="/check_safety")
    if isinstance(safety, dict) and safety.get("status") == "blocked":
        return {
            "ok": False,
            "asset": None,
            "message": safety.get("message", "Prompt was blocked by the Space's safety filter."),
        }

    images_b64_json = json.dumps([_image_path_to_data_uri(p) for p in input_image_paths])

    result = client.predict(
        images_b64_json,
        prompt,
        lora_adapter,
        seed,
        randomize_seed,
        guidance_scale,
        steps,
        api_name="/edit_image",
    )

    if not isinstance(result, dict) or result.get("status") != "success":
        message = result.get("message") if isinstance(result, dict) else None
        return {
            "ok": False,
            "asset": None,
            "message": message or f"Qwen edit Space did not return a successful result: {result!r}",
        }

    image_data_uri = result.get("image", "")
    if not image_data_uri or "," not in image_data_uri:
        return {
            "ok": False,
            "asset": None,
            "message": "Qwen edit Space returned no image data.",
        }

    _, b64_data = image_data_uri.split(",", 1)
    image_bytes = base64.b64decode(b64_data)

    GENERATED_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_filename(image_request_id)}_{safe_filename(lora_adapter)}_{timestamp}.png"
    out_path = GENERATED_ASSETS_DIR / filename
    out_path.write_bytes(image_bytes)

    asset = record_image_asset(
        image_request_id=image_request_id,
        file_path=str(out_path),
        provider_id=f"qwen_image_edit_space:{lora_adapter}",
        generation_notes=(
            f"Style-transferred by community HF Space '{space_id}' with LoRA '{lora_adapter}'. "
            f"Seed={result.get('seed', seed)}. Guidance={guidance_scale}. Steps={steps}. "
            "Third-party demo dependency — not a guaranteed/paid API. "
            "Pending Sentinel Visual QA. No upload/publish action allowed."
        ),
    )

    return {
        "ok": True,
        "asset": asset,
        "message": "Image styled via Qwen edit Space, saved, and recorded as an image asset.",
        "seed_used": result.get("seed", seed),
    }
