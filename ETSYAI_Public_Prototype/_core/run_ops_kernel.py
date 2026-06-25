import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from spacecommand_task_manager import (
    load_tasks,
    load_missions,
    status_summary,
)


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
CORE = ROOT / "_core"
STATE = ROOT / "_spacecommand_state"
REPORTS = STATE / "ops_reports"

CREATE_SELF_MISSION = CORE / "create_self_mission.py"
RUN_MISSION_CYCLE = CORE / "run_mission_cycle.py"
SHOW_STATUS = CORE / "show_status.py"


BLOCKING_STATUSES = {
    "human_approval_required",
    "failed",
    "rejected",
    "review_unknown",
}

REVISION_STATUSES = {
    "pending_revision",
}

ACTIVE_PENDING_STATUSES = {
    "pending",
    "pending_revision",
}


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_command(command):
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\n\n[stderr]\n" + result.stderr

    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output.strip(),
        "command": " ".join(str(x) for x in command),
    }


def classify_system_state():
    tasks = load_tasks()
    missions = load_missions()

    active_missions = [m for m in missions if m.get("status") == "active"]
    pending_tasks = [t for t in tasks if t.get("status") in ACTIVE_PENDING_STATUSES]
    blockers = [t for t in tasks if t.get("status") in BLOCKING_STATUSES]
    revisions = [t for t in tasks if t.get("status") in REVISION_STATUSES]

    if blockers:
        return {
            "state": "blocked",
            "reason": "One or more tasks require human attention or failed.",
            "active_missions": active_missions,
            "pending_tasks": pending_tasks,
            "blockers": blockers,
            "revisions": revisions,
        }

    if revisions:
        return {
            "state": "revision_needed",
            "reason": "One or more tasks need revision and can be retried by the cycle.",
            "active_missions": active_missions,
            "pending_tasks": pending_tasks,
            "blockers": blockers,
            "revisions": revisions,
        }

    if pending_tasks:
        return {
            "state": "work_available",
            "reason": "Pending tasks are available.",
            "active_missions": active_missions,
            "pending_tasks": pending_tasks,
            "blockers": blockers,
            "revisions": revisions,
        }

    return {
        "state": "idle",
        "reason": "No pending tasks found.",
        "active_missions": active_missions,
        "pending_tasks": pending_tasks,
        "blockers": blockers,
        "revisions": revisions,
    }


def summarize_tasks(tasks, limit=10):
    if not tasks:
        return "- None"

    lines = []
    for task in tasks[:limit]:
        verdict = task.get("sentinel_verdict") or "not reviewed"
        lines.append(
            f"- {task.get('id')} — {task.get('title')} "
            f"[{task.get('status')}] / Agent: {task.get('assigned_agent')} / Sentinel: {verdict}"
        )
    return "\n".join(lines)


def summarize_missions(missions, limit=10):
    if not missions:
        return "- None"

    lines = []
    for mission in missions[-limit:]:
        lines.append(
            f"- {mission.get('id')} — {mission.get('title')} [{mission.get('status')}]"
        )
    return "\n".join(lines)


def write_report(report_text):
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"ops_report_{file_stamp()}.md"
    path.write_text(report_text, encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Run SpaceCommand V4 Ops Kernel.")
    parser.add_argument("--max-tasks", type=int, default=3, help="Maximum tasks to run if work is available.")
    parser.add_argument("--no-auto-self-mission", action="store_true", help="Do not create a self mission when idle.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and report only. Do not create or run missions.")
    args = parser.parse_args()

    before = classify_system_state()

    actions = []

    if before["state"] == "blocked":
        actions.append({
            "name": "Stop on blocker",
            "result": {
                "success": True,
                "output": "Ops Kernel stopped because a blocking task exists.",
                "exit_code": 0,
            },
        })

    elif before["state"] == "idle":
        if args.no_auto_self_mission:
            actions.append({
                "name": "Idle",
                "result": {
                    "success": True,
                    "output": "No pending tasks. Auto self-mission disabled.",
                    "exit_code": 0,
                },
            })
        elif args.dry_run:
            actions.append({
                "name": "Dry run self mission",
                "result": {
                    "success": True,
                    "output": "Would create a self mission because system is idle.",
                    "exit_code": 0,
                },
            })
        else:
            result = run_command(["python", str(CREATE_SELF_MISSION), "--kind", "auto"])
            actions.append({
                "name": "Create self mission",
                "result": result,
            })

            after_create = classify_system_state()
            if after_create["pending_tasks"]:
                cycle = run_command(["python", str(RUN_MISSION_CYCLE), "--max-tasks", str(args.max_tasks)])
                actions.append({
                    "name": "Run mission cycle",
                    "result": cycle,
                })

    elif before["state"] in {"work_available", "revision_needed"}:
        if args.dry_run:
            actions.append({
                "name": "Dry run cycle",
                "result": {
                    "success": True,
                    "output": f"Would run mission cycle with max tasks: {args.max_tasks}",
                    "exit_code": 0,
                },
            })
        else:
            cycle = run_command(["python", str(RUN_MISSION_CYCLE), "--max-tasks", str(args.max_tasks)])
            actions.append({
                "name": "Run mission cycle",
                "result": cycle,
            })

    after = classify_system_state()
    final_status = status_summary()

    report_lines = []
    report_lines.append("# SpaceCommand V4 Ops Report")
    report_lines.append("")
    report_lines.append(f"Generated: {now_stamp()}")
    report_lines.append("")
    report_lines.append("## Kernel Decision")
    report_lines.append(f"- Initial state: {before['state']}")
    report_lines.append(f"- Initial reason: {before['reason']}")
    report_lines.append(f"- Final state: {after['state']}")
    report_lines.append(f"- Final reason: {after['reason']}")
    report_lines.append(f"- Dry run: {args.dry_run}")
    report_lines.append(f"- Max tasks: {args.max_tasks}")
    report_lines.append("")
    report_lines.append("## Active Missions Before")
    report_lines.append(summarize_missions(before["active_missions"]))
    report_lines.append("")
    report_lines.append("## Pending / Revision Tasks Before")
    report_lines.append(summarize_tasks(before["pending_tasks"]))
    report_lines.append("")
    report_lines.append("## Blocking Tasks Before")
    report_lines.append(summarize_tasks(before["blockers"]))
    report_lines.append("")
    report_lines.append("## Actions Taken")

    if not actions:
        report_lines.append("- No actions taken.")
    else:
        for action in actions:
            result = action["result"]
            report_lines.append("")
            report_lines.append(f"### {action['name']}")
            report_lines.append(f"- Success: {result.get('success')}")
            report_lines.append(f"- Exit code: {result.get('exit_code')}")
            report_lines.append("")
            report_lines.append("```text")
            report_lines.append(result.get("output", ""))
            report_lines.append("```")

    report_lines.append("")
    report_lines.append("## Active Missions After")
    report_lines.append(summarize_missions(after["active_missions"]))
    report_lines.append("")
    report_lines.append("## Pending / Revision Tasks After")
    report_lines.append(summarize_tasks(after["pending_tasks"]))
    report_lines.append("")
    report_lines.append("## Blocking Tasks After")
    report_lines.append(summarize_tasks(after["blockers"]))
    report_lines.append("")
    report_lines.append("## Full Status")
    report_lines.append("")
    report_lines.append(final_status)
    report_lines.append("")
    report_lines.append("## Recommended Human Action")

    if after["state"] == "blocked":
        report_lines.append("Review the blocking task before running another cycle.")
    elif after["state"] == "revision_needed":
        report_lines.append("Run the Ops Kernel again. Revision feedback should be included automatically.")
    elif after["state"] == "work_available":
        report_lines.append("Run another Ops Kernel cycle if you want SpaceCommand to continue local work.")
    elif after["state"] == "idle":
        report_lines.append("No pending work. Create a custom mission or allow another self mission.")
    else:
        report_lines.append("Review system status.")

    report_text = "\n".join(report_lines)
    report_path = write_report(report_text)

    print()
    print(report_text)
    print()
    print(f"[ops report saved] {report_path}")


if __name__ == "__main__":
    main()
