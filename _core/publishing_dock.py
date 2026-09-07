import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from api_connector_manager import evaluate_connector, get_connector as get_api_connector


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

PUBLISHING_CONNECTORS_FILE = STATE / "publishing_connectors.json"
PUBLISH_PACKAGES_FILE = STATE / "publish_packages.json"
PUBLISH_RUNS_FILE = STATE / "publish_runs.json"

IMAGE_ASSETS_FILE = STATE / "image_assets.json"
IMAGE_REQUESTS_FILE = STATE / "image_generation_requests.json"
DESIGN_FILE = STATE / "design_packages.json"
ECONOMICS_FILE = STATE / "unit_economics_cards.json"
LISTINGS_FILE = STATE / "listing_drafts.json"


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


def get_connector(connector_id: str) -> Dict[str, Any] | None:
    registry = load_json(PUBLISHING_CONNECTORS_FILE, {"connectors": []})

    for connector in registry.get("connectors", []):
        if connector.get("id") == connector_id:
            return connector

    return None


def connector_live_allowed(connector: Dict[str, Any] | None) -> bool:
    if not connector:
        return False

    return (
        connector.get("status") == "available_live_approved"
        and connector.get("permission_level") in {"approved_api", "approved_account_connection"}
    )


def manual_connector_available(connector: Dict[str, Any] | None) -> bool:
    if not connector:
        return False

    return connector.get("id") == "manual_browser_upload" and connector.get("status") == "available_local_safe"


def find_by_id(records: List[Dict[str, Any]], record_id: str) -> Dict[str, Any] | None:
    for record in records:
        if record.get("id") == record_id:
            return record

    return None


def latest_listing_for_design(design_package_id: str) -> Dict[str, Any] | None:
    listings = load_json(LISTINGS_FILE, [])
    matches = [x for x in listings if x.get("design_package_id") == design_package_id]

    if not matches:
        return None

    return matches[-1]


def latest_economics_for_design(design_package_id: str) -> Dict[str, Any] | None:
    economics = load_json(ECONOMICS_FILE, [])
    matches = [x for x in economics if x.get("design_package_id") == design_package_id]

    if not matches:
        return None

    return matches[-1]


def create_publish_package(
    image_asset_id: str,
    connector_id: str,
    target_platforms: List[str],
    product_type: str,
    listing_draft_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    packages = load_json(PUBLISH_PACKAGES_FILE, [])
    assets = load_json(IMAGE_ASSETS_FILE, [])
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    designs = load_json(DESIGN_FILE, [])
    listings = load_json(LISTINGS_FILE, [])

    connector = get_connector(connector_id)
    asset = find_by_id(assets, image_asset_id)

    issues = []
    warnings = []

    if not connector:
        issues.append("missing_publishing_connector")
    elif not manual_connector_available(connector) and not connector_live_allowed(connector):
        issues.append("connector_not_live_approved")

    if not asset:
        issues.append("missing_image_asset")

        package = {
            "id": next_id("PUBPKG", packages),
            "type": "publish_package",
            "status": "blocked_missing_image_asset",
            "image_asset_id": image_asset_id,
            "connector_id": connector_id,
            "target_platforms": target_platforms,
            "issues": issues,
            "warnings": warnings,
            "created_at": now_stamp(),
        }

        packages.append(package)
        save_json(PUBLISH_PACKAGES_FILE, packages)
        return package

    request = find_by_id(requests, asset.get("image_request_id", ""))
    design = None

    if request:
        design = find_by_id(designs, request.get("design_package_id", ""))

    if not request:
        issues.append("missing_image_request")

    if not design:
        issues.append("missing_design_package")

    if not asset.get("approved_for_mockup", False):
        warnings.append("image_asset_not_approved_for_mockup")

    if not asset.get("approved_for_product", False):
        issues.append("image_asset_not_approved_for_product")

    if design and not design.get("production_allowed", False):
        issues.append("design_production_gate_false")

    economics = latest_economics_for_design(design.get("id")) if design else None

    if not economics:
        issues.append("missing_unit_economics")
    elif economics.get("ledger_decision") != "PASS":
        issues.append(f"ledger_not_passed:{economics.get('ledger_decision')}")

    listing = None

    if listing_draft_id:
        listing = find_by_id(listings, listing_draft_id)

        if not listing:
            issues.append("missing_listing_draft")
    elif design:
        listing = latest_listing_for_design(design.get("id"))

    if not listing:
        issues.append("missing_listing_draft")
    elif not listing.get("listing_allowed", False):
        issues.append("listing_draft_not_allowed")

    is_manual = connector and manual_connector_available(connector)

    if is_manual:
        status = "manual_upload_package_ready" if not issues else "manual_upload_package_blocked"
    else:
        status = "live_publish_ready" if not issues and connector_live_allowed(connector) else "blocked_live_publish_not_approved"

    package = {
        "id": next_id("PUBPKG", packages),
        "type": "publish_package",
        "status": status,
        "image_asset_id": image_asset_id,
        "image_request_id": asset.get("image_request_id"),
        "design_package_id": design.get("id") if design else None,
        "unit_economics_card_id": economics.get("id") if economics else None,
        "listing_draft_id": listing.get("id") if listing else None,
        "connector_id": connector_id,
        "target_platforms": target_platforms,
        "product_type": product_type,
        "file_path": asset.get("file_path"),
        "copy_paste_fields": {
            "title": listing.get("title") if listing else "",
            "description": listing.get("description") if listing else "",
            "tags": listing.get("tags") if listing else [],
            "price": economics.get("item_price") if economics else None,
            "sku": f"{design.get('id')}-{asset.get('id')}" if design else "",
        },
        "upload_checklist": [
            "Confirm image asset is visually correct.",
            "Confirm Sentinel/IP QA has approved the image.",
            "Confirm Ledger decision is PASS.",
            "Confirm listing draft is allowed.",
            "Confirm product type and print area match the supplier template.",
            "Upload manually first or approve live connector before API upload.",
            "Do not publish to Etsy until final user approval.",
        ],
        "issues": issues,
        "warnings": warnings,
        "live_upload_allowed": False,
        "live_publish_allowed": False,
        "etsy_sync_allowed": False,
        "notes": notes,
        "created_at": now_stamp(),
    }

    packages.append(package)
    save_json(PUBLISH_PACKAGES_FILE, packages)
    return package


def create_publish_run(
    publish_package_id: str,
    connector_id: str,
    action: str,
    user_approved_live_action: bool = False,
    result_notes: str = "",
) -> Dict[str, Any]:
    runs = load_json(PUBLISH_RUNS_FILE, [])
    packages = load_json(PUBLISH_PACKAGES_FILE, [])
    package = find_by_id(packages, publish_package_id)
    connector = get_connector(connector_id)

    issues = []

    if not package:
        issues.append("missing_publish_package")

    if not connector:
        issues.append("missing_publishing_connector")

    live_action = action in {
        "upload_to_printify",
        "upload_to_printful",
        "create_etsy_listing",
        "publish_to_etsy",
        "sync_to_etsy",
    }

    if live_action and not user_approved_live_action:
        issues.append("missing_user_approval_for_live_action")

    if live_action and not connector_live_allowed(connector):
        issues.append("connector_not_live_approved")

    if package and package.get("issues"):
        issues.append("publish_package_has_blocking_issues")

    if action == "record_manual_upload_result":
        status = "manual_result_recorded" if not issues else "blocked_manual_result"
    else:
        status = "blocked_live_action" if issues else "live_action_ready"

    run = {
        "id": next_id("PUBRUN", runs),
        "type": "publish_run",
        "status": status,
        "publish_package_id": publish_package_id,
        "connector_id": connector_id,
        "action": action,
        "user_approved_live_action": user_approved_live_action,
        "issues": issues,
        "result_notes": result_notes,
        "created_at": now_stamp(),
    }

    runs.append(run)
    save_json(PUBLISH_RUNS_FILE, runs)
    return run


def create_etsy_draft_listing(
    publish_package_id: str,
    user_approved_live_action: bool = False,
    taxonomy_id: int = None,
    who_made: str = "i_did",
    when_made: str = "made_to_order",
    quantity: int = 999,
    is_digital: bool = False,
    shipping_profile_id: int = None,
    return_policy_id: int = None,
    readiness_state_id: int = None,
    shop_section_id: int = None,
    materials: List[str] = None,
    item_weight: float = None,
    item_length: float = None,
    item_width: float = None,
    item_height: float = None,
    item_weight_unit: str = None,
    item_dimensions_unit: str = None,
    is_personalizable: bool = False,
    personalization_is_required: bool = False,
    personalization_instructions: str = None,
) -> Dict[str, Any]:
    """
    Turn a local publish_package into a real DRAFT listing on the
    seller's own Etsy shop, via etsy_api_client.py.

    This is the only function in the repo that is allowed to make a
    live write call to Etsy, and it is gated on three independent
    things, all of which must hold:
      1. The "etsy" connector must be present, have a secret, be marked
         user_approved, and have live_actions_enabled — i.e. the seller
         explicitly turned it on (see set_api_connector_approval.py).
      2. The caller must pass user_approved_live_action=True for this
         specific call (defense in depth against an automated loop
         quietly flipping a switch and publishing unattended).
      3. The publish_package itself must be clean: no issues, and it
         must trace back through Sentinel-approved copy and a Ledger
         PASS (create_publish_package() already enforces this when
         building the package).

    The resulting Etsy listing is always created in `draft` state.
    Nothing here — or anywhere else in this repo — activates a listing.
    """
    runs = load_json(PUBLISH_RUNS_FILE, [])
    packages = load_json(PUBLISH_PACKAGES_FILE, [])
    package = find_by_id(packages, publish_package_id)

    issues: List[str] = []

    if not package:
        issues.append("missing_publish_package")
    elif package.get("issues"):
        issues.append("publish_package_has_blocking_issues")

    connector = get_api_connector("etsy")
    evaluation = evaluate_connector(connector) if connector else None
    connector_live_ready = bool(evaluation and evaluation.get("computed_status") == "live_enabled")

    if not connector_live_ready:
        issues.append("etsy_connector_not_live_enabled")

    if not user_approved_live_action:
        issues.append("missing_user_approval_for_live_action")

    if issues:
        run = {
            "id": next_id("PUBRUN", runs),
            "type": "publish_run",
            "status": "blocked_etsy_draft_create",
            "publish_package_id": publish_package_id,
            "connector_id": "etsy",
            "action": "create_etsy_listing",
            "user_approved_live_action": user_approved_live_action,
            "etsy_draft_created": False,
            "issues": issues,
            "created_at": now_stamp(),
        }
        runs.append(run)
        save_json(PUBLISH_RUNS_FILE, runs)
        return run

    # Import here (not at module load) so this module still imports cleanly
    # on machines that haven't installed the `cryptography` package yet —
    # only a live Etsy draft-create call needs it.
    import etsy_api_client as etsy

    fields = package.get("copy_paste_fields", {})
    title = fields.get("title") or "Untitled listing"
    description = fields.get("description") or ""
    tags = fields.get("tags") or []
    price = fields.get("price") or 0

    try:
        listing = etsy.create_draft_listing(
            title=title,
            description=description,
            price=price,
            quantity=quantity,
            who_made=who_made,
            when_made=when_made,
            taxonomy_id=taxonomy_id,
            shipping_profile_id=shipping_profile_id,
            return_policy_id=return_policy_id,
            readiness_state_id=readiness_state_id,
            tags=tags,
            is_digital=is_digital,
            shop_section_id=shop_section_id,
            materials=materials,
            item_weight=item_weight,
            item_length=item_length,
            item_width=item_width,
            item_height=item_height,
            item_weight_unit=item_weight_unit,
            item_dimensions_unit=item_dimensions_unit,
            is_personalizable=is_personalizable,
            personalization_is_required=personalization_is_required,
            personalization_instructions=personalization_instructions,
        )

        listing_id = listing.get("listing_id")
        image_upload_result = None
        file_path = package.get("file_path")

        if listing_id and file_path:
            try:
                image_upload_result = etsy.upload_listing_image(listing_id, file_path)
            except Exception as exc:  # noqa: BLE001 - surfaced in result_notes below
                image_upload_result = {"error": repr(exc)}

        run = {
            "id": next_id("PUBRUN", runs),
            "type": "publish_run",
            "status": "etsy_draft_created",
            "publish_package_id": publish_package_id,
            "connector_id": "etsy",
            "action": "create_etsy_listing",
            "user_approved_live_action": True,
            "etsy_draft_created": True,
            "etsy_listing_id": listing_id,
            "etsy_listing_state": listing.get("state", "draft"),
            "etsy_draft_url": etsy.draft_listing_url(listing_id) if listing_id else None,
            "image_upload_result": image_upload_result,
            "issues": [],
            "created_at": now_stamp(),
        }

    except Exception as exc:  # noqa: BLE001 - we want this recorded, not raised, for the UI/CLI
        run = {
            "id": next_id("PUBRUN", runs),
            "type": "publish_run",
            "status": "etsy_draft_create_failed",
            "publish_package_id": publish_package_id,
            "connector_id": "etsy",
            "action": "create_etsy_listing",
            "user_approved_live_action": True,
            "etsy_draft_created": False,
            "issues": ["etsy_api_call_failed"],
            "error": repr(exc),
            "created_at": now_stamp(),
        }

    runs.append(run)
    save_json(PUBLISH_RUNS_FILE, runs)
    return run


def audit_publishing() -> Dict[str, Any]:
    packages = load_json(PUBLISH_PACKAGES_FILE, [])
    runs = load_json(PUBLISH_RUNS_FILE, [])
    findings = []
    warnings = []

    for package in packages:
        package_id = package.get("id")

        if package.get("live_upload_allowed", False):
            findings.append({
                "severity": "blocker",
                "code": "publish_package_live_upload_allowed",
                "artifact_id": package_id,
                "message": "Publish package allows live upload. Live upload must stay false until explicit approval workflow is added.",
            })

        if package.get("live_publish_allowed", False):
            findings.append({
                "severity": "blocker",
                "code": "publish_package_live_publish_allowed",
                "artifact_id": package_id,
                "message": "Publish package allows live publishing. Live publishing must stay false until explicit approval workflow is added.",
            })

        if package.get("etsy_sync_allowed", False):
            findings.append({
                "severity": "blocker",
                "code": "publish_package_etsy_sync_allowed",
                "artifact_id": package_id,
                "message": "Publish package allows Etsy sync. Etsy sync must stay false until explicit approval workflow is added.",
            })

        if package.get("issues"):
            warnings.append({
                "code": "publish_package_blocked",
                "artifact_id": package_id,
                "message": f"Publish package has blocking issues: {package.get('issues')}",
            })

    for run in runs:
        run_id = run.get("id")

        if run.get("action") in {
            "upload_to_printify",
            "upload_to_printful",
            "create_etsy_listing",
            "publish_to_etsy",
            "sync_to_etsy",
        }:
            if not run.get("user_approved_live_action", False):
                findings.append({
                    "severity": "blocker",
                    "code": "publish_run_live_action_without_user_approval",
                    "artifact_id": run_id,
                    "message": "Publish run attempted a live action without explicit user approval.",
                })

            if run.get("status") == "live_action_ready":
                findings.append({
                    "severity": "blocker",
                    "code": "publish_run_live_action_ready_before_connector_build",
                    "artifact_id": run_id,
                    "message": "Live publish run should not be ready before a dedicated approved connector is implemented.",
                })

    return {
        "status": "blocked" if findings else "pass",
        "summary": {
            "publish_packages": len(packages),
            "publish_runs": len(runs),
            "blockers": len(findings),
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
        "created_at": now_stamp(),
    }
