"""
Claude (vision) as a Sentinel Visual QA reviewer.

Claude cannot generate images (no Anthropic image-generation API), but it
can look at one and judge it against the same checklist a human reviewer
would use — see docs/AGENTS_BUILD_NOTES.md and the earlier build notes for
why this is a separate concern from art generation.

This module NEVER writes a visual_qa_report by itself. It only produces a
*proposal* (the same fields a human types into create_visual_qa_report.py):
passed_checks / failed_checks / warning_flags / scores / notes. Turning a
proposal into a real report — which sets approved_for_mockup /
approved_for_product and can gate a real publish — always goes through one
of two explicit paths, mirroring the rest of this repo's approval model
(the Etsy connector gate, --i-approve-this-live-etsy-action, etc.):

  - finalize_autonomous(): writes immediately, no human in the loop. Only
    call this when the caller has already accepted that up front (the CLI
    requires --i-accept-autonomous-visual-qa). Reviewer is recorded as
    "Claude (autonomous)" so it's always traceable later who/what approved
    an asset.
  - finalize_with_client_confirmation(): the caller (a human, via the CLI's
    interactive prompt, or a UI you build) must explicitly confirm — and
    may edit any field — before anything is written. Reviewer is recorded
    as "Claude (human-confirmed)".

Either way, the actual pass/fail gate logic (score thresholds, the
BLOCKING_FAILS/WARNINGS vocabulary, the design production-gate check) is
still entirely sentinel_visual_qa.evaluate_visual_qa() — this module only
supplies inputs to that same gate, it does not weaken or bypass it.
"""

import json
from typing import Any, Dict, List, Optional

from llm_backend import DEFAULT_CLAUDE_MODEL, call_claude_vision
from sentinel_visual_qa import (
    BLOCKING_FAILS,
    WARNINGS,
    IMAGE_ASSETS_FILE,
    IMAGE_REQUESTS_FILE,
    DESIGN_FILE,
    create_visual_qa_report,
    find_by_id,
    load_json,
)


REVIEWER_AUTONOMOUS = "Claude (autonomous)"
REVIEWER_CLIENT_CONFIRMED = "Claude (human-confirmed)"

REQUIRED_PROPOSAL_KEYS = {
    "passed_checks",
    "failed_checks",
    "warning_flags",
    "prompt_match_score",
    "product_readiness_score",
    "qa_notes",
}


def _build_qa_prompt(asset: Dict[str, Any], request: Optional[Dict[str, Any]], design: Optional[Dict[str, Any]]) -> str:
    request_prompt = (request or {}).get("prompt", "(no image_generation_request prompt on file)")
    design_summary = json.dumps(
        {k: design.get(k) for k in ("id", "concept", "safety_notes", "production_allowed") if design and k in design},
        indent=2,
    ) if design else "(no linked design_package)"

    return f"""You are Sentinel, the visual QA reviewer for an Etsy print-on-demand pipeline.
Look at the attached image and evaluate it against the brief below. Be strict —
this gate blocks real listings from going out with wrong, low-quality, or
IP-risky art.

## Original image generation prompt/spec
{request_prompt}

## Linked design package
{design_summary}

## Your task
Return ONLY a single JSON object (no markdown fences, no commentary before or
after it) with exactly these keys:

- "passed_checks": array of short strings describing what looks correct.
- "failed_checks": array of zero or more of EXACTLY these values (use none if none apply) — {sorted(BLOCKING_FAILS)}
- "warning_flags": array of zero or more of EXACTLY these values (use none if none apply) — {sorted(WARNINGS)}
- "prompt_match_score": integer 0-100, how well the image matches the prompt/spec above.
- "product_readiness_score": integer 0-100, how ready this is to print/list as-is (resolution, cropping, cleanliness).
- "qa_notes": one short paragraph explaining your reasoning, especially any failed_checks or warning_flags.

Do not invent check names outside the two lists given. If you are unsure whether
something is a trademark/IP risk, err toward flagging "ip_or_trademark_risk" or
"contains_protected_character" rather than staying silent — a human still
confirms every result this produces."""


def _parse_proposal(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude did not return valid JSON for visual QA: {exc}. Raw response: {raw_text[:1500]}")

    missing = REQUIRED_PROPOSAL_KEYS - set(data.keys())
    if missing:
        raise RuntimeError(f"Claude's visual QA JSON is missing keys {sorted(missing)}. Raw response: {raw_text[:1500]}")

    return {
        "passed_checks": [str(x) for x in data.get("passed_checks", [])],
        "failed_checks": [str(x) for x in data.get("failed_checks", [])],
        "warning_flags": [str(x) for x in data.get("warning_flags", [])],
        "prompt_match_score": int(data.get("prompt_match_score", 0)),
        "product_readiness_score": int(data.get("product_readiness_score", 0)),
        "qa_notes": str(data.get("qa_notes", "")),
    }


def propose_claude_visual_qa(image_asset_id: str, claude_model: Optional[str] = None) -> Dict[str, Any]:
    """
    Ask Claude to look at an already-generated image asset and propose a
    visual_qa_report's inputs. Writes nothing. Raises RuntimeError on any
    failure (missing asset/file, missing ANTHROPIC_API_KEY, bad JSON, etc.)
    — this is a QA gate, so a broken call must never be swallowed into a
    silent pass.
    """
    assets = load_json(IMAGE_ASSETS_FILE, [])
    asset = find_by_id(assets, image_asset_id)

    if not asset:
        raise RuntimeError(f"No image_asset found with id {image_asset_id}.")

    file_path = asset.get("file_path")
    if not file_path:
        raise RuntimeError(f"Image asset {image_asset_id} has no file_path.")

    requests = load_json(IMAGE_REQUESTS_FILE, [])
    request = find_by_id(requests, asset.get("image_request_id", ""))

    designs = load_json(DESIGN_FILE, [])
    design = find_by_id(designs, request.get("design_package_id", "")) if request else None

    prompt = _build_qa_prompt(asset, request, design)
    raw_response = call_claude_vision(
        model=claude_model or DEFAULT_CLAUDE_MODEL,
        prompt=prompt,
        image_path=file_path,
    )
    proposal = _parse_proposal(raw_response)

    return {
        "image_asset_id": image_asset_id,
        "file_path": file_path,
        "model": claude_model or DEFAULT_CLAUDE_MODEL,
        "proposal": proposal,
        "raw_response": raw_response,
    }


def _finalize(image_asset_id: str, proposal: Dict[str, Any], reviewer: str) -> Dict[str, Any]:
    return create_visual_qa_report(
        image_asset_id=image_asset_id,
        reviewer=reviewer,
        passed_checks=proposal["passed_checks"],
        failed_checks=proposal["failed_checks"],
        warning_flags=proposal["warning_flags"],
        prompt_match_score=proposal["prompt_match_score"],
        product_readiness_score=proposal["product_readiness_score"],
        qa_notes=proposal["qa_notes"],
    )


def finalize_autonomous(image_asset_id: str, proposal: Dict[str, Any], accepted_autonomous_review: bool) -> Dict[str, Any]:
    """
    Write Claude's proposal as a real visual_qa_report with no human in the
    loop. Requires accepted_autonomous_review=True — the caller (the CLI's
    --i-accept-autonomous-visual-qa flag, or your own code) must have
    already made that an explicit, intentional choice.
    """
    if not accepted_autonomous_review:
        raise RuntimeError(
            "Autonomous finalization requires explicit acceptance "
            "(accepted_autonomous_review=True / --i-accept-autonomous-visual-qa)."
        )

    return _finalize(image_asset_id, proposal, REVIEWER_AUTONOMOUS)


def finalize_with_client_confirmation(
    image_asset_id: str,
    proposal: Dict[str, Any],
    confirmed: bool,
) -> Dict[str, Any]:
    """
    Write Claude's proposal as a real visual_qa_report only after a human
    (via the CLI's interactive prompt, or a UI) has confirmed it. Pass the
    (possibly edited) proposal dict back in — this function does not ask
    for input itself so it can be reused from a non-terminal UI too.
    """
    if not confirmed:
        raise RuntimeError("Client confirmation was not given — nothing was written.")

    return _finalize(image_asset_id, proposal, REVIEWER_CLIENT_CONFIRMED)
