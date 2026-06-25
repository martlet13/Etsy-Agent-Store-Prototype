import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

DESIGN_FILE = STATE / "design_packages.json"
IMAGE_REQUESTS_FILE = STATE / "image_generation_requests.json"
IMAGE_ASSETS_FILE = STATE / "image_assets.json"
IMAGE_PROVIDER_REGISTRY_FILE = STATE / "image_provider_registry.json"


REQUIRED_ACCURACY_FIELDS = [
    "subject",
    "composition",
    "style",
    "color_palette",
    "text_rules",
    "negative_constraints",
    "product_use",
    "aspect_ratio",
    "quality_bar",
]


FORBIDDEN_PROMPT_TERMS = [
    "disney",
    "marvel",
    "star wars",
    "pokemon",
    "harry potter",
    "stranger things",
    "the office",
    "yellowstone",
    "taylor swift",
    "nfl",
    "nba",
    "mlb",
    "nike",
    "adidas",
]


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def next_id(prefix: str, records: List[Dict[str, Any]]) -> str:
    highest = 0
    for item in records:
        raw = str(item.get("id", ""))
        if raw.startswith(prefix + "-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass
    return f"{prefix}-{highest + 1:04d}"


def provider_available(provider_id: str) -> bool:
    registry = load_json(IMAGE_PROVIDER_REGISTRY_FILE, {"providers": []})
    for provider in registry.get("providers", []):
        if provider.get("id") == provider_id:
            return provider.get("status") == "available_local_safe"
    return False


def get_design(design_package_id: str) -> Dict[str, Any] | None:
    designs = load_json(DESIGN_FILE, [])
    for design in designs:
        if design.get("id") == design_package_id:
            return design
    return None


def build_accuracy_prompt(
    design: Dict[str, Any],
    subject: str,
    composition: str,
    style: str,
    color_palette: str,
    text_rules: str,
    product_use: str,
    aspect_ratio: str,
    required_elements: List[str],
    forbidden_elements: List[str],
    negative_constraints: str,
    quality_bar: str,
) -> str:
    required_line = ", ".join(required_elements) if required_elements else "none"
    forbidden_line = ", ".join(forbidden_elements) if forbidden_elements else "none"

    prompt = f"""
Create an original print-on-demand image based on this strict visual specification.

DESIGN PACKAGE:
- ID: {design.get("id")}
- Title: {design.get("title")}
- Design Concept: {design.get("design_concept")}
- Safety Notes: {design.get("safety_notes")}

IMAGE SPEC:
- Subject: {subject}
- Composition: {composition}
- Style: {style}
- Color Palette: {color_palette}
- Text Rules: {text_rules}
- Product Use: {product_use}
- Aspect Ratio: {aspect_ratio}
- Required Elements: {required_line}
- Forbidden Elements: {forbidden_line}

NEGATIVE CONSTRAINTS:
{negative_constraints}

QUALITY BAR:
{quality_bar}

Hard rules:
- Original design only.
- No logos.
- No brand names.
- No characters from existing media.
- No celebrity likeness.
- No direct TV/movie/game/anime references.
- No copied art style from a living artist.
- No protected quotes or slogans.
- If text is included, it must be exactly described by Text Rules.
- Do not add extra words.
- Do not add watermarks.
- Do not add signatures.
""".strip()

    return prompt


def check_prompt_safety(prompt: str) -> List[str]:
    lower = prompt.lower()
    issues = []
    for term in FORBIDDEN_PROMPT_TERMS:
        if term in lower:
            issues.append(f"forbidden_reference:{term}")
    return issues


def create_image_request(
    design_package_id: str,
    provider_id: str,
    subject: str,
    composition: str,
    style: str,
    color_palette: str,
    text_rules: str,
    product_use: str,
    aspect_ratio: str,
    required_elements: List[str],
    forbidden_elements: List[str],
    negative_constraints: str,
    quality_bar: str,
    size: str,
    seed: str,
    notes: str,
) -> Dict[str, Any]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    design = get_design(design_package_id)

    if not design:
        request = {
            "id": next_id("IMGREQ", requests),
            "type": "image_generation_request",
            "status": "blocked_missing_design_package",
            "design_package_id": design_package_id,
            "created_at": now_stamp(),
            "issues": ["missing_design_package"],
        }
        requests.append(request)
        save_json(IMAGE_REQUESTS_FILE, requests)
        return request

    prompt = build_accuracy_prompt(
        design=design,
        subject=subject,
        composition=composition,
        style=style,
        color_palette=color_palette,
        text_rules=text_rules,
        product_use=product_use,
        aspect_ratio=aspect_ratio,
        required_elements=required_elements,
        forbidden_elements=forbidden_elements,
        negative_constraints=negative_constraints,
        quality_bar=quality_bar,
    )

    issues = []
    issues.extend(check_prompt_safety(prompt))

    if not provider_available(provider_id):
        issues.append("provider_not_available_local_safe")

    if design.get("listing_allowed", False):
        pass

    # Image concepting is allowed for concept-only designs, but generated assets cannot become production assets
    # until evidence and Ledger gates pass.
    status = "ready_manual_generation" if not issues or issues == ["provider_not_available_local_safe"] else "blocked_prompt_safety"

    if provider_id != "manual_image_generation" and "provider_not_available_local_safe" in issues:
        status = "blocked_provider_requires_approval"

    request = {
        "id": next_id("IMGREQ", requests),
        "type": "image_generation_request",
        "status": status,
        "design_package_id": design_package_id,
        "design_status": design.get("status"),
        "design_evidence_level": design.get("evidence_level"),
        "provider_id": provider_id,
        "provider_local_safe": provider_available(provider_id),
        "subject": subject,
        "composition": composition,
        "style": style,
        "color_palette": color_palette,
        "text_rules": text_rules,
        "product_use": product_use,
        "aspect_ratio": aspect_ratio,
        "required_elements": required_elements,
        "forbidden_elements": forbidden_elements,
        "negative_constraints": negative_constraints,
        "quality_bar": quality_bar,
        "size": size,
        "seed": seed,
        "prompt": prompt,
        "issues": issues,
        "production_allowed": False,
        "listing_allowed": False,
        "notes": notes,
        "created_at": now_stamp(),
    }

    requests.append(request)
    save_json(IMAGE_REQUESTS_FILE, requests)
    return request


def record_image_asset(
    image_request_id: str,
    file_path: str,
    provider_id: str,
    generation_notes: str,
) -> Dict[str, Any]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    request_by_id = {x.get("id"): x for x in requests}
    assets = load_json(IMAGE_ASSETS_FILE, [])

    if image_request_id not in request_by_id:
        asset = {
            "id": next_id("IMGASSET", assets),
            "type": "image_asset",
            "status": "blocked_missing_image_request",
            "image_request_id": image_request_id,
            "file_path": file_path,
            "issues": ["missing_image_request"],
            "created_at": now_stamp(),
        }
        assets.append(asset)
        save_json(IMAGE_ASSETS_FILE, assets)
        return asset

    request = request_by_id[image_request_id]

    asset = {
        "id": next_id("IMGASSET", assets),
        "type": "image_asset",
        "status": "generated_pending_visual_qa",
        "image_request_id": image_request_id,
        "design_package_id": request.get("design_package_id"),
        "provider_id": provider_id,
        "file_path": file_path,
        "generation_notes": generation_notes,
        "visual_qa": None,
        "approved_for_mockup": False,
        "approved_for_product": False,
        "external_action_allowed": False,
        "created_at": now_stamp(),
    }

    assets.append(asset)
    save_json(IMAGE_ASSETS_FILE, assets)
    return asset


def audit_image_assets() -> Dict[str, Any]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    assets = load_json(IMAGE_ASSETS_FILE, [])
    designs = load_json(DESIGN_FILE, [])

    request_by_id = {x.get("id"): x for x in requests}
    design_by_id = {x.get("id"): x for x in designs}

    findings = []
    warnings = []

    for request in requests:
        req_id = request.get("id")

        if request.get("status") == "blocked_provider_requires_approval":
            warnings.append({
                "code": "image_provider_requires_approval",
                "artifact_id": req_id,
                "message": "Image provider is not available in local-safe mode.",
            })

        if request.get("issues"):
            safety_issues = [x for x in request.get("issues", []) if x.startswith("forbidden_reference")]
            if safety_issues:
                findings.append({
                    "severity": "blocker",
                    "code": "image_prompt_forbidden_reference",
                    "artifact_id": req_id,
                    "message": f"Image prompt contains forbidden references: {safety_issues}",
                })

    for asset in assets:
        asset_id = asset.get("id")
        req_id = asset.get("image_request_id")
        request = request_by_id.get(req_id)

        if not request:
            findings.append({
                "severity": "blocker",
                "code": "image_asset_missing_request",
                "artifact_id": asset_id,
                "message": "Image asset does not reference a valid image generation request.",
            })
            continue

        design = design_by_id.get(request.get("design_package_id"))

        if not design:
            findings.append({
                "severity": "blocker",
                "code": "image_asset_missing_design",
                "artifact_id": asset_id,
                "message": "Image asset traces to a missing design package.",
            })
            continue

        if asset.get("approved_for_product", False):
            if not design.get("production_allowed", False):
                findings.append({
                    "severity": "blocker",
                    "code": "image_asset_product_approved_without_production_gate",
                    "artifact_id": asset_id,
                    "message": "Image asset is approved for product while design production gate is false.",
                })

        if asset.get("external_action_allowed", False):
            findings.append({
                "severity": "blocker",
                "code": "image_asset_external_action_allowed",
                "artifact_id": asset_id,
                "message": "Image asset should not allow external action in local testing.",
            })

    status = "blocked" if findings else "pass"

    return {
        "status": status,
        "summary": {
            "image_generation_requests": len(requests),
            "image_assets": len(assets),
            "blockers": len(findings),
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
        "created_at": now_stamp(),
    }


def format_image_audit(audit: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Forge Image Accuracy Audit")
    lines.append("")
    lines.append(f"Status: {audit.get('status')}")
    lines.append(f"Created: {audit.get('created_at')}")
    lines.append("")
    lines.append("## Summary")
    for key, value in audit.get("summary", {}).items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Blockers")
    if not audit.get("findings"):
        lines.append("- None")
    else:
        for item in audit.get("findings", []):
            lines.append(f"- [{item.get('code')}] {item.get('artifact_id')}: {item.get('message')}")

    lines.append("")
    lines.append("## Warnings")
    if not audit.get("warnings"):
        lines.append("- None")
    else:
        for item in audit.get("warnings", []):
            lines.append(f"- [{item.get('code')}] {item.get('artifact_id')}: {item.get('message')}")

    return "\n".join(lines)
