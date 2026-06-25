import argparse
import json
from pathlib import Path

from run_public_research_pipeline import main as unused_main
from fetch_public_source import create_snapshot
from research_connector_registry import create_connector_run
from pipeline_contracts import create_evidence_card, create_opportunity_card, create_handoff


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
TARGETS_FILE = STATE / "public_source_targets.json"


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


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def find_next_target(targets, connector_id=None):
    for target in targets:
        if target.get("status") != "pending":
            continue
        if connector_id and target.get("connector_id") != connector_id:
            continue
        return target
    return None


def run_target(target):
    snapshot = create_snapshot(
        connector_id=target["connector_id"],
        url=target["url"],
        query=target["query"],
        theme=target["theme"],
        time_window=target.get("time_window", "weekly"),
        max_chars=8000,
    )

    target["last_snapshot_id"] = snapshot.get("id")
    target["last_snapshot_status"] = snapshot.get("status")
    target["last_snapshot_success"] = snapshot.get("success")

    if not snapshot.get("success"):
        target["status"] = "fetch_failed"
        target["last_error"] = snapshot.get("error") or snapshot.get("notes") or snapshot.get("status")
        return {
            "target": target,
            "snapshot": snapshot,
            "connector_run": None,
            "evidence": None,
            "opportunity": None,
            "handoff": None,
        }

    title = snapshot.get("source_title") or target["url"]
    summary = snapshot.get("text_excerpt", "")

    connector_run = create_connector_run(
        connector_id=target["connector_id"],
        query=target["query"],
        theme=target["theme"],
        time_window=target.get("time_window", "weekly"),
        raw_summary=summary,
        source_url=target["url"],
        source_title=title,
        metrics={
            "snapshot_id": snapshot["id"],
            "status_code": snapshot.get("status_code"),
            "text_char_count": snapshot.get("text_char_count"),
        },
        notes=target.get("notes", "Created by public source target runner."),
    )

    target["last_connector_run_id"] = connector_run.get("id")
    target["last_connector_run_status"] = connector_run.get("status")

    if not connector_run.get("success"):
        target["status"] = "connector_failed"
        return {
            "target": target,
            "snapshot": snapshot,
            "connector_run": connector_run,
            "evidence": None,
            "opportunity": None,
            "handoff": None,
        }

    evidence = create_evidence_card(
        source=connector_run.get("connector_name") or connector_run.get("connector_id"),
        source_type=connector_run.get("source_type", "public_source"),
        collection_method=f"connector:{connector_run.get('connector_id')}",
        permission_level=connector_run.get("permission_level", "unknown"),
        time_window=target.get("time_window", "weekly"),
        keyword=target["keyword"],
        category=target["category"],
        evidence_strength=target.get("evidence_strength", "weak"),
        trend_direction=target.get("trend_direction", "unknown"),
        confidence=target.get("confidence", "medium-low"),
        metrics={
            "connector_run_id": connector_run["id"],
            "snapshot_id": snapshot["id"],
            "source_url": target["url"],
            "source_title": title,
            "text_char_count": snapshot.get("text_char_count"),
        },
        raw_snapshot_path=None,
        notes=(
            "Public source evidence created by Nova target runner. "
            "Not private marketplace sales data; not enough for production by itself. "
            + target.get("notes", "")
        ),
    )

    target["last_evidence_id"] = evidence["id"]

    opportunity = None
    handoff = None

    if target.get("create_opportunity", False):
        opportunity = create_opportunity_card(
            title=target.get("opportunity_title", f"Opportunity from {evidence['id']}"),
            source_evidence_ids=[evidence["id"]],
            product_category=target.get("product_category", target.get("category", "unknown")),
            design_lane=target.get("design_lane", "source-derived design lane"),
            design_style=target.get("design_style", "to be refined"),
            emotional_angle=target.get("emotional_angle", "to be refined"),
            buyer_moment=target.get("buyer_moment", "to be refined"),
            seasonal_timing=target.get("seasonal_timing", "unknown"),
            product_fit=csv_list(target.get("product_fit", "")),
            copyright_trademark_risk=target.get("copyright_trademark_risk", "unknown"),
            original_safe_angle=target.get("original_safe_angle", "original safe angle required"),
            confidence=target.get("confidence", "medium-low"),
            recommended_action=target.get("recommended_action", "Collect stronger marketplace evidence and verified Ledger costs before production."),
            notes="Created by Nova public source target runner.",
        )

        handoff = create_handoff(
            from_agent="Nova",
            to_agent="Forge",
            artifact_type="opportunity_card",
            artifact_id=opportunity["id"],
            summary=f"Public-source opportunity created from {evidence['id']} with evidence strength {evidence.get('evidence_strength')}.",
            required_next_action="Forge may create concept/design packages only. Production remains blocked until stronger evidence and Ledger PASS.",
            status="ready_for_concept_design",
        )

        target["last_opportunity_id"] = opportunity["id"]
        target["last_handoff_id"] = handoff["id"]

    target["status"] = "completed"

    return {
        "target": target,
        "snapshot": snapshot,
        "connector_run": connector_run,
        "evidence": evidence,
        "opportunity": opportunity,
        "handoff": handoff,
    }


def main():
    parser = argparse.ArgumentParser(description="Run the next pending Nova public source target.")
    parser.add_argument("--connector-id", default="")
    parser.add_argument("--target-id", default="")
    args = parser.parse_args()

    targets = load_json(TARGETS_FILE, [])

    if not targets:
        print()
        print("# No Public Source Targets")
        print()
        return

    target = None

    if args.target_id:
        for item in targets:
            if item.get("id") == args.target_id:
                target = item
                break
    else:
        target = find_next_target(targets, connector_id=args.connector_id or None)

    if not target:
        print()
        print("# No Matching Pending Target")
        print()
        print("No pending public source target matched your request.")
        print()
        return

    result = run_target(target)

    for index, item in enumerate(targets):
        if item.get("id") == target.get("id"):
            targets[index] = result["target"]
            break

    save_json(TARGETS_FILE, targets)

    print()
    print("# Nova Public Source Target Run")
    print()
    print(f"Target ID: {target.get('id')}")
    print(f"Target Status: {target.get('status')}")
    print(f"URL: {target.get('url')}")
    print(f"Snapshot: {target.get('last_snapshot_id')} / {target.get('last_snapshot_status')}")

    if target.get("last_error"):
        print(f"Error: {target.get('last_error')}")

    if target.get("last_connector_run_id"):
        print(f"Connector Run: {target.get('last_connector_run_id')}")

    if target.get("last_evidence_id"):
        print(f"Evidence: {target.get('last_evidence_id')}")

    if target.get("last_opportunity_id"):
        print(f"Opportunity: {target.get('last_opportunity_id')}")

    print()


if __name__ == "__main__":
    main()
