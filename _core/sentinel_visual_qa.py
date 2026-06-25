import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

IMAGE_ASSETS_FILE = STATE / "image_assets.json"
IMAGE_REQUESTS_FILE = STATE / "image_generation_requests.json"
DESIGN_FILE = STATE / "design_packages.json"
VISUAL_QA_FILE = STATE / "visual_qa_reports.json"


BLOCKING_FAILS = {
    "contains_logo",
    "contains_brand_name",
    "contains_protected_character",
    "contains_celebrity_likeness",
    "contains_watermark",
    "contains_signature",
    "contains_accidental_readable_text",
    "wrong_product_format",
    "low_resolution_or_blurry",
    "malformed_core_subject",
    "does_not_match_prompt",
    "unsafe_or_disallowed_content",
    "ip_or_trademark_risk",
}


WARNINGS = {
    "minor_composition_issue",
    "minor_color_drift",
    "needs_background_cleanup",
    "may_need_upscale",
    "mockup_only_not_product_ready",
    "text_legibility_uncertain",
}


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


def find_by_id(records: List[Dict[str, Any]], record_id: str) -> Dict[str, Any] | None:
    for record in records:
        if record.get("id") == record_id:
            return record

    return None


def csv_list(raw: str) -> List[str]:
    if not raw:
        return []

    return [x.strip() for x in raw.split(",") if x.strip()]


def normalize_flags(flags: List[str]) -> List[str]:
    clean = []

    for flag in flags:
        value = str(flag).strip().lower().replace(" ", "_")

        if value:
            clean.append(value)

    return clean


def evaluate_visual_qa(
    asset: Dict[str, Any],
    request: Dict[str, Any] | None,
    design: Dict[str, Any] | None,
    passed_checks: List[str],
    failed_checks: List[str],
    warning_flags: List[str],
    prompt_match_score: int,
    product_readiness_score: int,
    qa_notes: str,
) -> Dict[str, Any]:
    issues = []
    warnings = []

    failed_set = set(normalize_flags(failed_checks))
    warning_set = set(normalize_flags(warning_flags))

    for flag in failed_set:
        if flag in BLOCKING_FAILS:
            issues.append(flag)
        else:
            warnings.append(f"unrecognized_failed_check:{flag}")

    for flag in warning_set:
        if flag in WARNINGS:
            warnings.append(flag)
        else:
            warnings.append(f"unrecognized_warning:{flag}")

    if prompt_match_score < 80:
        issues.append("prompt_match_score_below_80")

    if product_readiness_score < 80:
        warnings.append("product_readiness_score_below_80")

    if not request:
        issues.append("missing_image_request")

    if not design:
        issues.append("missing_design_package")

    if design and not design.get("production_allowed", False):
        warnings.append("design_production_gate_false")

    approved_for_mockup = not issues and prompt_match_score >= 80
    approved_for_product = (
        not issues
        and prompt_match_score >= 90
        and product_readiness_score >= 90
        and design is not None
        and design.get("production_allowed", False)
    )

    if approved_for_product and not design.get("production_allowed", False):
        issues.append("product_approval_without_design_production_gate")
        approved_for_product = False

    status = "pass_mockup_only" if approved_for_mockup and not approved_for_product else "pass_product"
    if issues:
        status = "blocked"
    elif warnings and approved_for_mockup:
        status = "pass_with_warnings_mockup_only"

    return {
        "status": status,
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "approved_for_mockup": approved_for_mockup,
        "approved_for_product": approved_for_product,
        "passed_checks": passed_checks,
        "failed_checks": sorted(failed_set),
        "warning_flags": sorted(warning_set),
        "prompt_match_score": prompt_match_score,
        "product_readiness_score": product_readiness_score,
        "qa_notes": qa_notes,
    }


def create_visual_qa_report(
    image_asset_id: str,
    reviewer: str,
    passed_checks: List[str],
    failed_checks: List[str],
    warning_flags: List[str],
    prompt_match_score: int,
    product_readiness_score: int,
    qa_notes: str,
) -> Dict[str, Any]:
    assets = load_json(IMAGE_ASSETS_FILE, [])
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    designs = load_json(DESIGN_FILE, [])
    reports = load_json(VISUAL_QA_FILE, [])

    asset = find_by_id(assets, image_asset_id)

    if not asset:
        report = {
            "id": next_id("VQA", reports),
            "type": "visual_qa_report",
            "status": "blocked",
            "image_asset_id": image_asset_id,
            "reviewer": reviewer,
            "issues": ["missing_image_asset"],
            "warnings": [],
            "approved_for_mockup": False,
            "approved_for_product": False,
            "created_at": now_stamp(),
        }

        reports.append(report)
        save_json(VISUAL_QA_FILE, reports)
        return report

    request = find_by_id(requests, asset.get("image_request_id", ""))
    design = None

    if request:
        design = find_by_id(designs, request.get("design_package_id", ""))

    evaluation = evaluate_visual_qa(
        asset=asset,
        request=request,
        design=design,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        warning_flags=warning_flags,
        prompt_match_score=prompt_match_score,
        product_readiness_score=product_readiness_score,
        qa_notes=qa_notes,
    )

    report = {
        "id": next_id("VQA", reports),
        "type": "visual_qa_report",
        "status": evaluation["status"],
        "image_asset_id": image_asset_id,
        "image_request_id": asset.get("image_request_id"),
        "design_package_id": design.get("id") if design else None,
        "reviewer": reviewer,
        "file_path": asset.get("file_path"),
        "prompt_match_score": evaluation["prompt_match_score"],
        "product_readiness_score": evaluation["product_readiness_score"],
        "passed_checks": evaluation["passed_checks"],
        "failed_checks": evaluation["failed_checks"],
        "warning_flags": evaluation["warning_flags"],
        "issues": evaluation["issues"],
        "warnings": evaluation["warnings"],
        "approved_for_mockup": evaluation["approved_for_mockup"],
        "approved_for_product": evaluation["approved_for_product"],
        "qa_notes": evaluation["qa_notes"],
        "created_at": now_stamp(),
    }

    reports.append(report)
    save_json(VISUAL_QA_FILE, reports)

    for item in assets:
        if item.get("id") == image_asset_id:
            item["visual_qa"] = report["id"]
            item["approved_for_mockup"] = report["approved_for_mockup"]
            item["approved_for_product"] = report["approved_for_product"]
            item["visual_qa_status"] = report["status"]
            item["visual_qa_issues"] = report["issues"]
            item["visual_qa_warnings"] = report["warnings"]
            item["external_action_allowed"] = False
            break

    save_json(IMAGE_ASSETS_FILE, assets)

    return report


def audit_visual_qa() -> Dict[str, Any]:
    assets = load_json(IMAGE_ASSETS_FILE, [])
    reports = load_json(VISUAL_QA_FILE, [])

    report_by_id = {x.get("id"): x for x in reports}

    findings = []
    warnings = []

    for asset in assets:
        asset_id = asset.get("id")

        report_id = asset.get("visual_qa")

        if not report_id:
            warnings.append({
                "code": "image_asset_missing_visual_qa",
                "artifact_id": asset_id,
                "message": "Image asset has not been reviewed by Sentinel Visual QA.",
            })
            continue

        report = report_by_id.get(report_id)

        if not report:
            findings.append({
                "severity": "blocker",
                "code": "image_asset_visual_qa_report_missing",
                "artifact_id": asset_id,
                "message": "Image asset references a missing Sentinel Visual QA report.",
            })
            continue

        if report.get("issues"):
            warnings.append({
                "code": "visual_qa_blocked_asset",
                "artifact_id": asset_id,
                "message": f"Visual QA found blocking issues: {report.get('issues')}",
            })

        if asset.get("approved_for_product", False) and not report.get("approved_for_product", False):
            findings.append({
                "severity": "blocker",
                "code": "image_asset_product_approved_without_visual_qa_pass",
                "artifact_id": asset_id,
                "message": "Image asset is product-approved but Visual QA did not approve product use.",
            })

        if asset.get("external_action_allowed", False):
            findings.append({
                "severity": "blocker",
                "code": "image_asset_external_action_allowed_after_qa",
                "artifact_id": asset_id,
                "message": "Image asset external action must remain false after QA until Publisher approval gates pass.",
            })

    return {
        "status": "blocked" if findings else "pass",
        "summary": {
            "visual_qa_reports": len(reports),
            "reviewed_image_assets": len([x for x in assets if x.get("visual_qa")]),
            "blockers": len(findings),
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
        "created_at": now_stamp(),
    }
