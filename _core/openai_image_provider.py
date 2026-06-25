import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from forge_image_kernel import IMAGE_REQUESTS_FILE, load_json, record_image_asset
from image_generation_budget import (
    IMAGE_API_BUDGET_FILE,
    IMAGE_GENERATION_RUNS_FILE,
    create_generation_run_decision,
    evaluate_image_request_budget,
    find_by_id,
    save_json,
)


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
GENERATED_ASSETS_DIR = STATE / "generated_assets"


OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename(raw: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(raw))
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:90] or "generated_image"


def get_openai_api_key() -> Optional[str]:
    return os.environ.get("OPENAI_API_KEY")


def get_image_request(image_request_id: str) -> Optional[Dict[str, Any]]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    return find_by_id(requests, image_request_id)


def update_run(run_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])
    updated = None

    for run in runs:
        if run.get("id") == run_id:
            run.update(updates)
            updated = run
            break

    save_json(IMAGE_GENERATION_RUNS_FILE, runs)

    return updated or updates


def call_openai_image_api(
    api_key: str,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    output_format: str,
) -> Dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "n": 1,
    }

    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OPENAI_IMAGES_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status_code": getattr(response, "status", 200),
                "json": json.loads(raw),
                "raw": raw,
            }

    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "error": raw_error,
        }

    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "error": repr(exc),
        }


def extract_b64_image(response_json: Dict[str, Any]) -> Optional[str]:
    data = response_json.get("data", [])

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            if first.get("b64_json"):
                return first.get("b64_json")

    # Some response shapes may include output events/objects.
    output = response_json.get("output", [])
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and item.get("b64_json"):
                return item.get("b64_json")

    return None


def extract_usage(response_json: Dict[str, Any]) -> Dict[str, Any]:
    usage = response_json.get("usage")

    if isinstance(usage, dict):
        return usage

    return {}


def save_image_file(image_request_id: str, b64_image: str, output_format: str) -> str:
    GENERATED_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_filename(image_request_id)}_{timestamp}.{output_format}"
    path = GENERATED_ASSETS_DIR / filename

    image_bytes = base64.b64decode(b64_image)
    path.write_bytes(image_bytes)

    return str(path)


def generate_openai_image_for_request(
    image_request_id: str,
    quality: str = "high",
    output_format: str = "png",
    force_live: bool = False,
) -> Dict[str, Any]:
    budget = load_json(IMAGE_API_BUDGET_FILE, {})
    request = get_image_request(image_request_id)

    decision = evaluate_image_request_budget(image_request_id)

    run = create_generation_run_decision(
        image_request_id=image_request_id,
        mode="live_api",
        result_notes="OpenAI provider live API generation attempt.",
    )

    run_id = run["id"]

    if not request:
        updated = update_run(run_id, {
            "status": "blocked_missing_image_request",
            "issues": sorted(set(run.get("issues", []) + ["missing_image_request"])),
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "Missing image request.",
        }

    if not decision.get("eligible_for_generation"):
        updated = update_run(run_id, {
            "status": "blocked_budget_or_eligibility",
            "issues": decision.get("issues", []),
            "warnings": decision.get("warnings", []),
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "Image request failed budget or eligibility gate.",
        }

    live_api_enabled = bool(budget.get("live_api_enabled", False))

    if not live_api_enabled and not force_live:
        updated = update_run(run_id, {
            "status": "blocked_live_api_disabled",
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "Live API is disabled. No image was generated.",
        }

    api_key = get_openai_api_key()

    if not api_key:
        updated = update_run(run_id, {
            "status": "blocked_missing_openai_api_key",
            "issues": sorted(set(run.get("issues", []) + ["missing_openai_api_key"])),
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "OPENAI_API_KEY environment variable is missing.",
        }

    prompt = request.get("prompt", "")

    if not prompt:
        updated = update_run(run_id, {
            "status": "blocked_missing_prompt",
            "issues": sorted(set(run.get("issues", []) + ["missing_prompt"])),
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "Image request prompt is missing.",
        }

    model = budget.get("model", "gpt-image-2")
    size = request.get("size", "1024x1536")

    api_result = call_openai_image_api(
        api_key=api_key,
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        output_format=output_format,
    )

    if not api_result.get("ok"):
        updated = update_run(run_id, {
            "status": "openai_api_failed",
            "issues": sorted(set(run.get("issues", []) + ["openai_api_failed"])),
            "openai_status_code": api_result.get("status_code"),
            "openai_error": api_result.get("error"),
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "OpenAI image API call failed.",
        }

    response_json = api_result.get("json", {})
    b64_image = extract_b64_image(response_json)

    if not b64_image:
        updated = update_run(run_id, {
            "status": "openai_api_no_image_returned",
            "issues": sorted(set(run.get("issues", []) + ["openai_api_no_image_returned"])),
            "openai_status_code": api_result.get("status_code"),
            "openai_response_preview": json.dumps(response_json)[:2000],
            "completed_at": now_stamp(),
        })
        return {
            "ok": False,
            "run": updated,
            "asset": None,
            "message": "OpenAI response did not contain b64_json image data.",
        }

    file_path = save_image_file(
        image_request_id=image_request_id,
        b64_image=b64_image,
        output_format=output_format,
    )

    usage = extract_usage(response_json)

    asset = record_image_asset(
        image_request_id=image_request_id,
        file_path=file_path,
        provider_id="openai_images_gpt_image_2",
        generation_notes=(
            f"Generated by OpenAI Images provider. Model={model}. "
            f"Quality={quality}. Size={size}. Output={output_format}. "
            "Pending Sentinel Visual QA. No upload/publish action allowed."
        ),
    )

    updated = update_run(run_id, {
        "status": "live_generation_completed",
        "counts_against_budget": True,
        "generated_asset_id": asset.get("id"),
        "generated_file_path": file_path,
        "openai_status_code": api_result.get("status_code"),
        "openai_usage": usage,
        "quality": quality,
        "size": size,
        "output_format": output_format,
        "completed_at": now_stamp(),
    })

    return {
        "ok": True,
        "run": updated,
        "asset": asset,
        "message": "OpenAI image generated, saved, and recorded as image asset.",
    }
