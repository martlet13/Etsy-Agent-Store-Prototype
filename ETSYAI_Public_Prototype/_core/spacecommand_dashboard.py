import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
DASHBOARD_FILE = STATE / "dashboard_report_latest.md"
DASHBOARD_REPORTS_FILE = STATE / "dashboard_reports.json"


FILES = {
    "evidence_cards": "evidence_cards.json",
    "opportunity_cards": "opportunity_cards.json",
    "design_packages": "design_packages.json",
    "unit_economics_cards": "unit_economics_cards.json",
    "listing_drafts": "listing_drafts.json",
    "connector_runs": "connector_runs.json",
    "public_source_snapshots": "public_source_snapshots.json",
    "image_generation_requests": "image_generation_requests.json",
    "image_assets": "image_assets.json",
    "image_generation_runs": "image_generation_runs.json",
    "visual_qa_reports": "visual_qa_reports.json",
    "publish_packages": "publish_packages.json",
    "publish_runs": "publish_runs.json",
    "spacecommand_cycle_reports": "spacecommand_cycle_reports.json",
    "api_connector_status_checks": "api_connector_status_checks.json",
    "supplier_catalog_checks": "supplier_catalog_checks.json",
    "image_file_inspections": "image_file_inspections.json",
    "scribe_listing_runs": "scribe_listing_runs.json",
    "dedupe_reports": "dedupe_reports.json",
    "scheduler_reports": "scheduler_reports.json"
}


def now_stamp():
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


def generate_dashboard():
    counts = {}
    latest = {}

    for label, filename in FILES.items():
        data = load_json(STATE / filename, [])
        counts[label] = len(data) if isinstance(data, list) else 1
        if isinstance(data, list) and data:
            latest[label] = data[-1]

    lines = []
    lines.append("# SpaceCommand Local Dashboard")
    lines.append("")
    lines.append(f"Generated: {now_stamp()}")
    lines.append("")
    lines.append("## Counts")
    for key, value in counts.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Latest Cycle")
    cycle = latest.get("spacecommand_cycle_reports")
    if cycle:
        lines.append(f"- ID: {cycle.get('id')}")
        lines.append(f"- Audit Status: {cycle.get('audit_status')}")
        lines.append(f"- Warnings: {cycle.get('audit_warning_count')}")
        lines.append(f"- Blockers: {cycle.get('audit_blocker_count')}")
    else:
        lines.append("- No cycle report yet.")

    lines.append("")
    lines.append("## Latest Image Generation")
    run = latest.get("image_generation_runs")
    if run:
        lines.append(f"- ID: {run.get('id')}")
        lines.append(f"- Status: {run.get('status')}")
        lines.append(f"- Model: {run.get('model')}")
        lines.append(f"- Counts Against Budget: {run.get('counts_against_budget')}")
    else:
        lines.append("- No image generation run yet.")

    lines.append("")
    lines.append("## Latest Publish Package")
    pkg = latest.get("publish_packages")
    if pkg:
        lines.append(f"- ID: {pkg.get('id')}")
        lines.append(f"- Status: {pkg.get('status')}")
        lines.append(f"- Issues: {pkg.get('issues')}")
    else:
        lines.append("- No publish package yet.")

    text = "\n".join(lines)
    DASHBOARD_FILE.write_text(text, encoding="utf-8")

    reports = load_json(DASHBOARD_REPORTS_FILE, [])
    report = {
        "id": next_id("DASH", reports),
        "type": "dashboard_report",
        "path": str(DASHBOARD_FILE),
        "counts": counts,
        "created_at": now_stamp()
    }
    reports.append(report)
    save_json(DASHBOARD_REPORTS_FILE, reports)

    return report, text


def main():
    report, text = generate_dashboard()
    print()
    print(text)
    print()
    print(f"Dashboard saved to: {report['path']}")
    print()


if __name__ == "__main__":
    main()
