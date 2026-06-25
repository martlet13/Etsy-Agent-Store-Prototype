import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

SCHEDULE_PLAN_FILE = STATE / "schedule_plan.json"
SCHEDULER_REPORTS_FILE = STATE / "scheduler_reports.json"


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


def review_schedule():
    plan = load_json(SCHEDULE_PLAN_FILE, {})
    reports = load_json(SCHEDULER_REPORTS_FILE, [])

    issues = []
    warnings = []

    if not plan.get("automation_enabled", False):
        warnings.append("automation_disabled")

    if not plan.get("windows_task_scheduler_enabled", False):
        warnings.append("windows_task_scheduler_disabled")

    enabled_items = [x for x in plan.get("planned_schedule", []) if x.get("enabled")]

    report = {
        "id": next_id("SCHEDREPORT", reports),
        "type": "scheduler_report",
        "status": "manual_only" if warnings and not issues else "ready",
        "automation_enabled": plan.get("automation_enabled", False),
        "windows_task_scheduler_enabled": plan.get("windows_task_scheduler_enabled", False),
        "planned_items": len(plan.get("planned_schedule", [])),
        "enabled_items": len(enabled_items),
        "issues": issues,
        "warnings": warnings,
        "created_at": now_stamp()
    }

    reports.append(report)
    save_json(SCHEDULER_REPORTS_FILE, reports)
    return report


def main():
    report = review_schedule()
    print()
    print("# Scheduler Prep Report")
    print()
    print(f"ID: {report['id']}")
    print(f"Status: {report['status']}")
    print(f"Automation Enabled: {report['automation_enabled']}")
    print(f"Windows Task Scheduler Enabled: {report['windows_task_scheduler_enabled']}")
    print(f"Planned Items: {report['planned_items']}")
    print(f"Enabled Items: {report['enabled_items']}")
    print(f"Issues: {', '.join(report.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(report.get('warnings', [])) or 'none'}")
    print()


if __name__ == "__main__":
    main()
