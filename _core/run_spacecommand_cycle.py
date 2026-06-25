import json
from datetime import datetime
from pathlib import Path

from pipeline_contracts import audit_pipeline, format_audit
from run_forge_on_next_opportunity import run_forge_on_next_opportunity
from run_next_public_source_target import (
    TARGETS_FILE,
    find_next_target,
    load_json as load_target_json,
    run_target,
    save_json as save_target_json,
)


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

CYCLE_REPORTS_FILE = STATE / "spacecommand_cycle_reports.json"
IMAGE_ASSETS_FILE = STATE / "image_assets.json"
PUBLISH_PACKAGES_FILE = STATE / "publish_packages.json"


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path, fallback):
    if not path.exists():
        return fallback

    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()

    if not text:
        return fallback

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def next_id(prefix, records):
    highest = 0

    for item in records:
        raw = str(item.get("id", ""))

        if raw.startswith(prefix + "-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass

    return f"{prefix}-{highest + 1:04d}"


def run_nova_step():
    targets = load_target_json(TARGETS_FILE, [])
    target = find_next_target(targets)

    if not target:
        return {
            "status": "no_pending_public_source_target",
            "target_id": None,
            "message": "Nova found no pending public source target.",
        }

    result = run_target(target)

    for index, item in enumerate(targets):
        if item.get("id") == target.get("id"):
            targets[index] = result["target"]
            break

    save_target_json(TARGETS_FILE, targets)

    return {
        "status": result["target"].get("status"),
        "target_id": result["target"].get("id"),
        "snapshot_id": result["target"].get("last_snapshot_id"),
        "connector_run_id": result["target"].get("last_connector_run_id"),
        "evidence_id": result["target"].get("last_evidence_id"),
        "opportunity_id": result["target"].get("last_opportunity_id"),
        "error": result["target"].get("last_error"),
        "message": "Nova ran one public source target.",
    }


def run_forge_step():
    result = run_forge_on_next_opportunity(include_weak=True)

    return {
        "status": result.get("status"),
        "opportunity_id": result.get("opportunity", {}).get("id") if result.get("opportunity") else None,
        "design_package_id": result.get("design", {}).get("id") if result.get("design") else None,
        "design_status": result.get("design", {}).get("status") if result.get("design") else None,
        "image_request_id": result.get("image_request", {}).get("id") if result.get("image_request") else None,
        "image_request_status": result.get("image_request", {}).get("status") if result.get("image_request") else None,
        "message": result.get("message"),
    }


def run_sentinel_step():
    assets = load_json(IMAGE_ASSETS_FILE, [])

    pending = [
        asset for asset in assets
        if asset.get("status") == "generated_pending_visual_qa" and not asset.get("visual_qa")
    ]

    if not pending:
        return {
            "status": "no_unreviewed_image_asset",
            "asset_id": None,
            "message": "Sentinel found no image asset waiting for Visual QA.",
        }

    return {
        "status": "waiting_for_manual_or_vision_qa",
        "asset_id": pending[0].get("id"),
        "message": "Sentinel found an asset needing QA. Manual/vision review must run before product approval.",
    }


def run_publisher_step():
    packages = load_json(PUBLISH_PACKAGES_FILE, [])

    blocked = [pkg for pkg in packages if pkg.get("issues")]

    if blocked:
        return {
            "status": "blocked_packages_exist",
            "publish_package_id": blocked[-1].get("id"),
            "issues": blocked[-1].get("issues"),
            "message": "Publisher has blocked packages; no live upload allowed.",
        }

    return {
        "status": "no_publish_action_ready",
        "publish_package_id": None,
        "message": "Publisher found no package eligible for live/manual upload.",
    }


def run_cycle():
    reports = load_json(CYCLE_REPORTS_FILE, [])

    cycle = {
        "id": next_id("CYCLE", reports),
        "type": "spacecommand_cycle_report",
        "created_at": now_stamp(),
        "steps": {},
    }

    cycle["steps"]["nova"] = run_nova_step()
    cycle["steps"]["forge"] = run_forge_step()
    cycle["steps"]["sentinel"] = run_sentinel_step()
    cycle["steps"]["publisher"] = run_publisher_step()

    audit = audit_pipeline()

    cycle["audit_id"] = audit.get("id")
    cycle["audit_status"] = audit.get("status")
    cycle["audit_summary"] = audit.get("summary")
    cycle["audit_warning_count"] = len(audit.get("warnings", []))
    cycle["audit_blocker_count"] = len(audit.get("findings", []))

    reports.append(cycle)
    save_json(CYCLE_REPORTS_FILE, reports)

    return cycle, audit


def print_cycle_report(cycle, audit):
    print()
    print("# SpaceCommand Cycle")
    print()
    print(f"Cycle ID: {cycle.get('id')}")
    print(f"Created: {cycle.get('created_at')}")
    print(f"Audit ID: {cycle.get('audit_id')}")
    print(f"Audit Status: {cycle.get('audit_status')}")
    print()

    print("## Steps")
    for name, step in cycle.get("steps", {}).items():
        print(f"- {name}: {step.get('status')}")

        details = []

        for key in [
            "target_id",
            "snapshot_id",
            "connector_run_id",
            "evidence_id",
            "opportunity_id",
            "design_package_id",
            "image_request_id",
            "asset_id",
            "publish_package_id",
        ]:
            if step.get(key):
                details.append(f"{key}={step.get(key)}")

        if details:
            print(f"  {', '.join(details)}")

        if step.get("error"):
            print(f"  error={step.get('error')}")

        if step.get("issues"):
            print(f"  issues={step.get('issues')}")

    print()
    print("## Audit Summary")
    for key, value in cycle.get("audit_summary", {}).items():
        print(f"- {key}: {value}")

    print()
    print(format_audit(audit))
    print()


def main():
    cycle, audit = run_cycle()
    print_cycle_report(cycle, audit)


if __name__ == "__main__":
    main()
