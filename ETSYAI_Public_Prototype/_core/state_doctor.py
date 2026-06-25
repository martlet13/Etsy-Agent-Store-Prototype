import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
REPORTS_FILE = STATE / "state_doctor_reports.json"

JSON_DEFAULTS = {
    "evidence_cards.json": [],
    "opportunity_cards.json": [],
    "design_packages.json": [],
    "unit_economics_cards.json": [],
    "listing_drafts.json": [],
    "agent_handoffs.json": [],
    "connector_runs.json": [],
    "public_source_snapshots.json": [],
    "image_generation_requests.json": [],
    "image_assets.json": [],
    "image_generation_runs.json": [],
    "publish_packages.json": [],
    "publish_runs.json": [],
    "visual_qa_reports.json": [],
    "spacecommand_cycle_reports.json": [],
    "api_connector_status_checks.json": [],
    "supplier_catalog_checks.json": [],
    "image_file_inspections.json": [],
    "scribe_listing_runs.json": [],
    "dashboard_reports.json": [],
    "dedupe_reports.json": [],
    "scheduler_reports.json": [],
    "state_doctor_reports.json": [],
    "artifact_lifecycle_events.json": [],
    "backup_reports.json": [],
    "ui_action_runs.json": [],
    "product_candidate_board.json": [],
    "decision_queue.json": [],
}


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any):
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, data: Any):
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


def diagnose_state():
    issues = []
    repairs_available = []

    for filename, default in JSON_DEFAULTS.items():
        path = STATE / filename
        if not path.exists():
            issues.append({"code": "missing_state_file", "file": filename})
            repairs_available.append({"code": "create_missing_state_file", "file": filename})
            continue

        try:
            load_json(path, default)
        except Exception as exc:
            issues.append({"code": "invalid_json", "file": filename, "error": repr(exc)})

    image_runs = load_json(STATE / "image_generation_runs.json", [])
    seen_gate = set()
    duplicate_runs = []

    for run in image_runs:
        key = (
            run.get("image_request_id"),
            run.get("status"),
            run.get("candidate_bucket"),
            run.get("counts_against_budget", False),
        )
        if run.get("status") in {"blocked_live_api_disabled", "blocked_budget_or_eligibility"}:
            if key in seen_gate:
                duplicate_runs.append(run.get("id"))
            seen_gate.add(key)

        if run.get("live_generation_allowed", False) and not run.get("counts_against_budget", False):
            if run.get("status") != "live_generation_completed":
                issues.append({
                    "code": "stale_live_allowed_image_run",
                    "artifact_id": run.get("id"),
                })
                repairs_available.append({
                    "code": "repair_stale_live_allowed_image_run",
                    "artifact_id": run.get("id"),
                })

    if duplicate_runs:
        issues.append({"code": "duplicate_non_counting_image_runs", "artifact_ids": duplicate_runs})
        repairs_available.append({"code": "dedupe_non_counting_image_runs"})

    packages = load_json(STATE / "publish_packages.json", [])
    for package in packages:
        if package.get("status") == "manual_upload_package_blocked" and package.get("notes", "").lower().find("test") >= 0:
            repairs_available.append({
                "code": "mark_test_publish_package_ignored",
                "artifact_id": package.get("id"),
            })

    handoffs = load_json(STATE / "agent_handoffs.json", [])
    known_ids = set()
    for filename in [
        "evidence_cards.json", "opportunity_cards.json", "design_packages.json",
        "unit_economics_cards.json", "listing_drafts.json", "image_generation_requests.json",
        "image_assets.json", "publish_packages.json"
    ]:
        for item in load_json(STATE / filename, []):
            if item.get("id"):
                known_ids.add(item.get("id"))

    orphan_handoffs = []
    for handoff in handoffs:
        artifact_id = handoff.get("artifact_id")
        if artifact_id and artifact_id not in known_ids:
            orphan_handoffs.append(handoff.get("id"))

    if orphan_handoffs:
        issues.append({"code": "orphan_handoffs", "artifact_ids": orphan_handoffs})

    return issues, repairs_available


def repair_state():
    changes = []

    for filename, default in JSON_DEFAULTS.items():
        path = STATE / filename
        if not path.exists():
            save_json(path, default)
            changes.append({"code": "created_missing_state_file", "file": filename})

    runs_path = STATE / "image_generation_runs.json"
    runs = load_json(runs_path, [])
    repaired_runs = []

    for run in runs:
        if run.get("live_generation_allowed", False) and run.get("status") != "live_generation_completed":
            run["live_generation_allowed"] = False
            run["counts_against_budget"] = False
            run.setdefault("issues", [])
            if "state_doctor_repaired_stale_live_allowed_flag" not in run["issues"]:
                run["issues"].append("state_doctor_repaired_stale_live_allowed_flag")
            if run.get("status") == "approved_waiting_for_provider_implementation":
                run["status"] = "blocked_live_api_disabled"
            repaired_runs.append(run.get("id"))

    seen = set()
    cleaned = []
    removed = []
    for run in runs:
        key = (
            run.get("image_request_id"),
            run.get("status"),
            run.get("candidate_bucket"),
            run.get("counts_against_budget", False),
        )
        if run.get("status") in {"blocked_live_api_disabled", "blocked_budget_or_eligibility"} and key in seen:
            removed.append(run.get("id"))
            continue
        seen.add(key)
        cleaned.append(run)

    save_json(runs_path, cleaned)

    if repaired_runs:
        changes.append({"code": "repaired_stale_image_runs", "artifact_ids": repaired_runs})
    if removed:
        changes.append({"code": "removed_duplicate_non_counting_image_runs", "artifact_ids": removed})

    packages_path = STATE / "publish_packages.json"
    packages = load_json(packages_path, [])
    ignored = []
    for package in packages:
        if package.get("status") == "manual_upload_package_blocked" and package.get("notes", "").lower().find("test") >= 0:
            package["status"] = "ignored_test_package"
            package["ignored_by_cycle"] = True
            ignored.append(package.get("id"))
    save_json(packages_path, packages)

    if ignored:
        changes.append({"code": "marked_test_publish_packages_ignored", "artifact_ids": ignored})

    return changes


def run_state_doctor(repair=False):
    reports = load_json(REPORTS_FILE, [])
    issues_before, repairs_available = diagnose_state()
    changes = []

    if repair:
        changes = repair_state()

    issues_after, repairs_after = diagnose_state()

    report = {
        "id": next_id("DOCTOR", reports),
        "type": "state_doctor_report",
        "mode": "repair" if repair else "diagnose",
        "status": "issues_found" if issues_after else "pass",
        "issues_before": issues_before,
        "repairs_available_before": repairs_available,
        "changes": changes,
        "issues_after": issues_after,
        "repairs_available_after": repairs_after,
        "created_at": now_stamp(),
    }

    reports.append(report)
    save_json(REPORTS_FILE, reports)
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SpaceCommand State Doctor")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()

    report = run_state_doctor(repair=args.repair)

    print()
    print("# SpaceCommand State Doctor")
    print()
    print(f"ID: {report['id']}")
    print(f"Mode: {report['mode']}")
    print(f"Status: {report['status']}")
    print(f"Issues Before: {len(report.get('issues_before', []))}")
    print(f"Changes: {len(report.get('changes', []))}")
    print(f"Issues After: {len(report.get('issues_after', []))}")

    if report.get("issues_after"):
        print()
        print("## Remaining Issues")
        for issue in report["issues_after"]:
            print(f"- {issue}")

    if report.get("changes"):
        print()
        print("## Changes")
        for change in report["changes"]:
            print(f"- {change}")

    print()


if __name__ == "__main__":
    main()
