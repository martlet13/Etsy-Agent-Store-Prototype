import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

EVIDENCE_FILE = STATE / "evidence_cards.json"
OPPORTUNITY_FILE = STATE / "opportunity_cards.json"
DESIGN_FILE = STATE / "design_packages.json"
ECONOMICS_FILE = STATE / "unit_economics_cards.json"
LISTINGS_FILE = STATE / "listing_drafts.json"
HANDOFFS_FILE = STATE / "agent_handoffs.json"
AUDITS_FILE = STATE / "pipeline_audits.json"
CONNECTOR_RUNS_FILE = STATE / "connector_runs.json"
IMAGE_REQUESTS_FILE = STATE / "image_generation_requests.json"
IMAGE_ASSETS_FILE = STATE / "image_assets.json"
IMAGE_GENERATION_RUNS_FILE = STATE / "image_generation_runs.json"
IMAGE_API_BUDGET_FILE = STATE / "image_api_budget.json"
PUBLIC_SOURCE_SNAPSHOTS_FILE = STATE / "public_source_snapshots.json"
PUBLISH_PACKAGES_FILE = STATE / "publish_packages.json"
PUBLISH_RUNS_FILE = STATE / "publish_runs.json"
VISUAL_QA_FILE = STATE / "visual_qa_reports.json"
CYCLE_REPORTS_FILE = STATE / "spacecommand_cycle_reports.json"
API_CONNECTOR_REGISTRY_FILE = STATE / "api_connector_registry.json"
API_CONNECTOR_STATUS_CHECKS_FILE = STATE / "api_connector_status_checks.json"
SUPPLIER_CATALOG_CHECKS_FILE = STATE / "supplier_catalog_checks.json"
IMAGE_FILE_INSPECTIONS_FILE = STATE / "image_file_inspections.json"
SCRIBE_LISTING_RUNS_FILE = STATE / "scribe_listing_runs.json"
DASHBOARD_REPORTS_FILE = STATE / "dashboard_reports.json"
DEDUPE_REPORTS_FILE = STATE / "dedupe_reports.json"
SCHEDULER_REPORTS_FILE = STATE / "scheduler_reports.json"
STATE_DOCTOR_REPORTS_FILE = STATE / "state_doctor_reports.json"
ARTIFACT_LIFECYCLE_EVENTS_FILE = STATE / "artifact_lifecycle_events.json"
BACKUP_REPORTS_FILE = STATE / "backup_reports.json"
UI_ACTION_RUNS_FILE = STATE / "ui_action_runs.json"
DECISION_QUEUE_FILE = STATE / "decision_queue.json"
PRODUCT_CANDIDATE_BOARD_FILE = STATE / "product_candidate_board.json"
CONTRACTS_FILE = STATE / "pipeline_contracts.json"


FINAL_BLOCKERS = {
    "missing_required_artifact",
    "invalid_handoff",
    "ledger_fail",
    "ledger_missing",
    "evidence_missing_for_validated_claim",
    "listing_without_ledger_pass",
    "design_without_opportunity",
    "unsafe_external_action",
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


def ensure_state_files() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    defaults = {
        EVIDENCE_FILE: [],
        OPPORTUNITY_FILE: [],
        DESIGN_FILE: [],
        ECONOMICS_FILE: [],
        LISTINGS_FILE: [],
        HANDOFFS_FILE: [],
        AUDITS_FILE: [],
        CONTRACTS_FILE: {
            "version": "V6",
            "name": "Evidence + Handoff Kernel",
            "core_rule": "No agent may skip its required input artifact.",
        },
    }

    for path, value in defaults.items():
        if not path.exists():
            save_json(path, value)


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


def create_evidence_card(
    source: str,
    source_type: str,
    collection_method: str,
    permission_level: str,
    time_window: str,
    keyword: str,
    category: str,
    evidence_strength: str,
    trend_direction: str = "unknown",
    confidence: str = "low",
    metrics: Optional[Dict[str, Any]] = None,
    raw_snapshot_path: Optional[str] = None,
    notes: str = "",
) -> Dict[str, Any]:
    ensure_state_files()
    cards = load_json(EVIDENCE_FILE, [])

    card = {
        "id": next_id("EVID", cards),
        "type": "evidence_card",
        "status": "active",
        "source": source,
        "source_type": source_type,
        "collection_method": collection_method,
        "permission_level": permission_level,
        "time_window": time_window,
        "keyword": keyword,
        "category": category,
        "evidence_strength": evidence_strength,
        "trend_direction": trend_direction,
        "confidence": confidence,
        "metrics": metrics or {},
        "raw_snapshot_path": raw_snapshot_path,
        "notes": notes,
        "created_at": now_stamp(),
    }

    cards.append(card)
    save_json(EVIDENCE_FILE, cards)
    return card


def create_opportunity_card(
    title: str,
    source_evidence_ids: List[str],
    product_category: str,
    design_lane: str,
    design_style: str,
    emotional_angle: str,
    buyer_moment: str,
    seasonal_timing: str,
    product_fit: List[str],
    copyright_trademark_risk: str,
    original_safe_angle: str,
    confidence: str,
    recommended_action: str,
    notes: str = "",
) -> Dict[str, Any]:
    ensure_state_files()
    cards = load_json(OPPORTUNITY_FILE, [])

    evidence_cards = load_json(EVIDENCE_FILE, [])
    evidence_by_id = {e.get("id"): e for e in evidence_cards}

    missing = [eid for eid in source_evidence_ids if eid not in evidence_by_id]
    evidence_strengths = [
        evidence_by_id[eid].get("evidence_strength", "missing")
        for eid in source_evidence_ids
        if eid in evidence_by_id
    ]

    if missing:
        status = "blocked_missing_evidence"
    elif not source_evidence_ids:
        status = "hypothesis_only"
    elif all(x in {"missing", "hypothesis"} for x in evidence_strengths):
        status = "hypothesis_only"
    else:
        status = "evidence_backed"

    card = {
        "id": next_id("OPP", cards),
        "type": "opportunity_card",
        "status": status,
        "title": title,
        "source_evidence_ids": source_evidence_ids,
        "missing_evidence_ids": missing,
        "product_category": product_category,
        "design_lane": design_lane,
        "design_style": design_style,
        "emotional_angle": emotional_angle,
        "buyer_moment": buyer_moment,
        "seasonal_timing": seasonal_timing,
        "product_fit": product_fit,
        "copyright_trademark_risk": copyright_trademark_risk,
        "original_safe_angle": original_safe_angle,
        "confidence": confidence,
        "recommended_action": recommended_action,
        "notes": notes,
        "created_at": now_stamp(),
    }

    cards.append(card)
    save_json(OPPORTUNITY_FILE, cards)
    return card


def create_handoff(
    from_agent: str,
    to_agent: str,
    artifact_type: str,
    artifact_id: str,
    summary: str,
    required_next_action: str,
    status: str = "ready_for_next_agent",
) -> Dict[str, Any]:
    ensure_state_files()
    handoffs = load_json(HANDOFFS_FILE, [])
    connector_runs = load_json(CONNECTOR_RUNS_FILE, [])
    image_requests = load_json(IMAGE_REQUESTS_FILE, [])
    image_assets = load_json(IMAGE_ASSETS_FILE, [])
    image_generation_runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])
    image_api_budget = load_json(IMAGE_API_BUDGET_FILE, {})
    public_snapshots = load_json(PUBLIC_SOURCE_SNAPSHOTS_FILE, [])
    publish_packages = load_json(PUBLISH_PACKAGES_FILE, [])
    publish_runs = load_json(PUBLISH_RUNS_FILE, [])
    visual_qa_reports = load_json(VISUAL_QA_FILE, [])
    cycle_reports = load_json(CYCLE_REPORTS_FILE, [])
    api_connector_registry = load_json(API_CONNECTOR_REGISTRY_FILE, {})
    api_connector_status_checks = load_json(API_CONNECTOR_STATUS_CHECKS_FILE, [])
    supplier_catalog_checks = load_json(SUPPLIER_CATALOG_CHECKS_FILE, [])
    image_file_inspections = load_json(IMAGE_FILE_INSPECTIONS_FILE, [])
    scribe_listing_runs = load_json(SCRIBE_LISTING_RUNS_FILE, [])
    dashboard_reports = load_json(DASHBOARD_REPORTS_FILE, [])
    dedupe_reports = load_json(DEDUPE_REPORTS_FILE, [])
    scheduler_reports = load_json(SCHEDULER_REPORTS_FILE, [])
    state_doctor_reports = load_json(STATE_DOCTOR_REPORTS_FILE, [])
    artifact_lifecycle_events = load_json(ARTIFACT_LIFECYCLE_EVENTS_FILE, [])
    backup_reports = load_json(BACKUP_REPORTS_FILE, [])
    ui_action_runs = load_json(UI_ACTION_RUNS_FILE, [])
    decision_queue = load_json(DECISION_QUEUE_FILE, [])
    product_candidate_board = load_json(PRODUCT_CANDIDATE_BOARD_FILE, [])

    handoff = {
        "id": next_id("HANDOFF", handoffs),
        "type": "agent_handoff",
        "from_agent": from_agent,
        "to_agent": to_agent,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "summary": summary,
        "required_next_action": required_next_action,
        "status": status,
        "created_at": now_stamp(),
    }

    handoffs.append(handoff)
    save_json(HANDOFFS_FILE, handoffs)
    return handoff


def audit_pipeline() -> Dict[str, Any]:
    ensure_state_files()

    evidence = load_json(EVIDENCE_FILE, [])
    opportunities = load_json(OPPORTUNITY_FILE, [])
    designs = load_json(DESIGN_FILE, [])
    economics = load_json(ECONOMICS_FILE, [])
    listings = load_json(LISTINGS_FILE, [])
    handoffs = load_json(HANDOFFS_FILE, [])
    connector_runs = load_json(CONNECTOR_RUNS_FILE, [])
    image_requests = load_json(IMAGE_REQUESTS_FILE, [])
    image_assets = load_json(IMAGE_ASSETS_FILE, [])
    image_generation_runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])
    image_api_budget = load_json(IMAGE_API_BUDGET_FILE, {})
    public_snapshots = load_json(PUBLIC_SOURCE_SNAPSHOTS_FILE, [])
    publish_packages = load_json(PUBLISH_PACKAGES_FILE, [])
    publish_runs = load_json(PUBLISH_RUNS_FILE, [])
    visual_qa_reports = load_json(VISUAL_QA_FILE, [])
    cycle_reports = load_json(CYCLE_REPORTS_FILE, [])
    api_connector_registry = load_json(API_CONNECTOR_REGISTRY_FILE, {})
    api_connector_status_checks = load_json(API_CONNECTOR_STATUS_CHECKS_FILE, [])
    supplier_catalog_checks = load_json(SUPPLIER_CATALOG_CHECKS_FILE, [])
    image_file_inspections = load_json(IMAGE_FILE_INSPECTIONS_FILE, [])
    scribe_listing_runs = load_json(SCRIBE_LISTING_RUNS_FILE, [])
    dashboard_reports = load_json(DASHBOARD_REPORTS_FILE, [])
    dedupe_reports = load_json(DEDUPE_REPORTS_FILE, [])
    scheduler_reports = load_json(SCHEDULER_REPORTS_FILE, [])
    state_doctor_reports = load_json(STATE_DOCTOR_REPORTS_FILE, [])
    artifact_lifecycle_events = load_json(ARTIFACT_LIFECYCLE_EVENTS_FILE, [])
    backup_reports = load_json(BACKUP_REPORTS_FILE, [])
    ui_action_runs = load_json(UI_ACTION_RUNS_FILE, [])
    decision_queue = load_json(DECISION_QUEUE_FILE, [])
    product_candidate_board = load_json(PRODUCT_CANDIDATE_BOARD_FILE, [])

    evidence_ids = {x.get("id") for x in evidence}
    opportunity_ids = {x.get("id") for x in opportunities}
    design_ids = {x.get("id") for x in designs}
    economics_by_product = {}
    economics_by_design = {}

    for econ in economics:
        if econ.get("product_id"):
            economics_by_product[econ.get("product_id")] = econ
        if econ.get("design_package_id"):
            economics_by_design[econ.get("design_package_id")] = econ

    findings = []
    warnings = []

    for opp in opportunities:
        opp_id = opp.get("id")
        evidence_list = opp.get("source_evidence_ids", [])

        if not evidence_list:
            warnings.append({
                "code": "opportunity_hypothesis_only",
                "artifact_id": opp_id,
                "message": "Opportunity has no evidence cards and must remain hypothesis-only.",
            })

        missing = [eid for eid in evidence_list if eid not in evidence_ids]
        if missing:
            findings.append({
                "severity": "blocker",
                "code": "missing_required_artifact",
                "artifact_id": opp_id,
                "message": f"Opportunity references missing evidence cards: {missing}",
            })

        if opp.get("status") == "hypothesis_only":
            warnings.append({
                "code": "opportunity_hypothesis_only",
                "artifact_id": opp_id,
                "message": "Opportunity is hypothesis-only. Forge may explore concepts, but production/listing/pricing must stay blocked until evidence and Ledger costs exist.",
            })

            action_text = str(opp.get("recommended_action", "")).lower()

            blocked_action_words = [
                "develop",
                "produce",
                "publish",
                "list",
                "upload",
                "sell",
                "price this product",
                "create listing",
            ]

            if any(word in action_text for word in blocked_action_words):
                findings.append({
                    "severity": "blocker",
                    "code": "evidence_missing_for_validated_claim",
                    "artifact_id": opp_id,
                    "message": "Hypothesis-only opportunity recommends production/listing/pricing action instead of evidence collection.",
                })

    for design in designs:
        design_id = design.get("id")
        opp_id = design.get("opportunity_id")
        if not opp_id or opp_id not in opportunity_ids:
            findings.append({
                "severity": "blocker",
                "code": "design_without_opportunity",
                "artifact_id": design_id,
                "message": "Design package is missing a valid opportunity_id.",
            })

        if design.get("production_allowed", False) and design.get("evidence_level") in {"missing", "hypothesis", "weak"}:
            findings.append({
                "severity": "blocker",
                "code": "production_allowed_with_weak_evidence",
                "artifact_id": design_id,
                "message": "Design package allows production even though evidence is missing, hypothesis-level, or weak.",
            })

        if design.get("status") == "ready_for_ledger" and design.get("production_allowed", False):
            warnings.append({
                "code": "design_ready_for_ledger_not_production",
                "artifact_id": design_id,
                "message": "Design package is ready for Ledger, but production should remain false until Ledger PASS.",
            })
    for econ in economics:
        econ_id = econ.get("id")
        decision = econ.get("ledger_decision")
        issues = econ.get("issues", [])

        if decision == "COST_DATA_MISSING":
            warnings.append({
                "code": "ledger_cost_data_missing",
                "artifact_id": econ_id,
                "message": "Ledger cannot approve this product yet. Verified item price, production cost, supplier shipping cost, and cost verification are required before production/listing.",
            })

        elif decision == "NEEDS_PRICE_CHANGE":
            warnings.append({
                "code": "ledger_needs_price_change",
                "artifact_id": econ_id,
                "message": "Ledger found positive profit but the price does not meet required profit or margin targets.",
            })

        elif decision == "FAIL":
            findings.append({
                "severity": "blocker",
                "code": "ledger_fail",
                "artifact_id": econ_id,
                "message": f"Ledger failed this product. Issues: {issues}",
            })

        elif decision == "PASS":
            if not econ.get("listing_allowed", False):
                findings.append({
                    "severity": "blocker",
                    "code": "ledger_pass_listing_flag_mismatch",
                    "artifact_id": econ_id,
                    "message": "Ledger decision is PASS but listing_allowed is false.",
                })

    economics_ids = {econ.get("id") for econ in economics}
    economics_by_id = {econ.get("id"): econ for econ in economics}

    for listing in listings:
        listing_id = listing.get("id")
        econ_id = listing.get("unit_economics_card_id")
        listing_allowed = listing.get("listing_allowed", False)
        publish_allowed = listing.get("publish_allowed", False)

        if not econ_id or econ_id not in economics_ids:
            if listing_allowed or publish_allowed:
                findings.append({
                    "severity": "blocker",
                    "code": "ledger_missing",
                    "artifact_id": listing_id,
                    "message": "Listing is allowed/publishable without a matching unit economics card.",
                })
            else:
                warnings.append({
                    "code": "blocked_listing_missing_ledger",
                    "artifact_id": listing_id,
                    "message": "Blocked listing draft exists without Ledger economics. This is allowed as a safe Scribe refusal record.",
                })
        elif listing_allowed:
            econ = economics_by_id.get(econ_id, {})
            if econ.get("ledger_decision") != "PASS":
                findings.append({
                    "severity": "blocker",
                    "code": "listing_allowed_without_ledger_pass",
                    "artifact_id": listing_id,
                    "message": "Listing is allowed even though Ledger has not passed.",
                })

    valid_artifacts = set()
    for collection in [evidence, opportunities, designs, economics, listings]:
        for item in collection:
            valid_artifacts.add(item.get("id"))

    for handoff in handoffs:
        artifact_id = handoff.get("artifact_id")
        if artifact_id not in valid_artifacts:
            findings.append({
                "severity": "blocker",
                "code": "invalid_handoff",
                "artifact_id": handoff.get("id"),
                "message": f"Handoff points to missing artifact: {artifact_id}",
            })

    blocker_count = len([f for f in findings if f.get("severity") == "blocker"])
    status = "blocked" if blocker_count else "pass"

    audit = {
        "id": None,
        "type": "pipeline_audit",
        "status": status,
        "created_at": now_stamp(),
        "summary": {
            "evidence_cards": len(evidence),
            "opportunity_cards": len(opportunities),
            "design_packages": len(designs),
            "unit_economics_cards": len(economics),
            "listing_drafts": len(listings),
            "agent_handoffs": len(handoffs),
            "connector_runs": len(connector_runs),
            "public_source_snapshots": len(public_snapshots),
            "image_generation_requests": len(image_requests),
            "image_assets": len(image_assets),
            "image_generation_runs": len(image_generation_runs),
            "monthly_image_cap": image_api_budget.get("monthly_image_cap", 10),
            "monthly_trend_image_cap": image_api_budget.get("monthly_trend_image_cap", 5),
            "weekly_trend_image_cap": image_api_budget.get("weekly_trend_image_cap", 1),
            "image_model": image_api_budget.get("model", "gpt-image-2"),
            "image_live_api_enabled": image_api_budget.get("live_api_enabled", False),
            "publish_packages": len(publish_packages),
            "publish_runs": len(publish_runs),
            "visual_qa_reports": len(visual_qa_reports),
            "spacecommand_cycle_reports": len(cycle_reports),
            "api_connectors": len(api_connector_registry.get("connectors", [])),
            "api_connector_status_checks": len(api_connector_status_checks),
            "supplier_catalog_checks": len(supplier_catalog_checks),
            "image_file_inspections": len(image_file_inspections),
            "scribe_listing_runs": len(scribe_listing_runs),
            "dashboard_reports": len(dashboard_reports),
            "dedupe_reports": len(dedupe_reports),
            "scheduler_reports": len(scheduler_reports),
            "state_doctor_reports": len(state_doctor_reports),
            "artifact_lifecycle_events": len(artifact_lifecycle_events),
            "backup_reports": len(backup_reports),
            "ui_action_runs": len(ui_action_runs),
            "decision_queue_items": len(decision_queue),
            "product_candidate_board_items": len(product_candidate_board),
            "blockers": blocker_count,
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
    }

    audits = load_json(AUDITS_FILE, [])
    audit["id"] = next_id("AUDIT", audits)
    audits.append(audit)
    save_json(AUDITS_FILE, audits)

    return audit


def format_audit(audit: Dict[str, Any]) -> str:
    lines = []
    lines.append("# SpaceCommand V6 Pipeline Audit")
    lines.append("")
    lines.append(f"Audit ID: {audit.get('id')}")
    lines.append(f"Status: {audit.get('status')}")
    lines.append(f"Created: {audit.get('created_at')}")
    lines.append("")
    lines.append("## Summary")

    for key, value in audit.get("summary", {}).items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Blockers")

    blockers = audit.get("findings", [])
    if not blockers:
        lines.append("- None")
    else:
        for item in blockers:
            lines.append(f"- [{item.get('code')}] {item.get('artifact_id')}: {item.get('message')}")

    lines.append("")
    lines.append("## Warnings")

    warnings = audit.get("warnings", [])
    if not warnings:
        lines.append("- None")
    else:
        for item in warnings:
            lines.append(f"- [{item.get('code')}] {item.get('artifact_id')}: {item.get('message')}")

    return "\n".join(lines)



