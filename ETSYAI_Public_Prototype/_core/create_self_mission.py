import argparse
import json
from pathlib import Path
from spacecommand_task_manager import create_mission, load_tasks, load_missions


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"


def read_text(path: Path, limit: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[-limit:]
    return text


def detect_self_mission_type() -> str:
    tasks = load_tasks()

    pending_revision = [t for t in tasks if t.get("status") == "pending_revision"]
    failed = [t for t in tasks if t.get("status") == "failed"]
    human_approval = [t for t in tasks if t.get("status") == "human_approval_required"]

    revision_text = read_text(ROOT / "04_QARoom" / "revision_requests.md")
    approved_text = read_text(ROOT / "04_QARoom" / "approved_items.md")
    overseer_text = read_text(ROOT / "_overseer" / "mission_order.md")
    command_text = read_text(ROOT / "00_Bridge" / "room_status.md")
    scribe_text = read_text(ROOT / "03_ListingRoom" / "dashboard_spec.md")

    combined = "\n".join([revision_text, approved_text, overseer_text, command_text, scribe_text]).lower()

    if failed:
        return "repair_failed_tasks"

    if pending_revision:
        return "resolve_pending_revisions"

    if any(word in combined for word in ["alpha", "beta", "gamma", "dashboard specification", "signal needs building", "unassigned", "troops", "weapons", "combat"]):
        return "reduce_drift"

    if human_approval:
        return "review_human_approval_items"

    return "routine_self_improvement"


def build_self_mission(kind: str):
    if kind == "repair_failed_tasks":
        return {
            "title": "Self Mission: Repair Failed Tasks",
            "description": "SpaceCommand detected failed task cards and needs a local-only repair pass.",
            "tasks": [
                {
                    "title": "Analyze failed tasks",
                    "description": "Review failed tasks and identify why they failed. Focus on runner errors, missing files, invalid agents, or bad prompts.",
                    "assigned_agent": "Strategist",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Create repair blueprint",
                    "description": "Create a local-only repair blueprint for failed task causes. Do not modify files.",
                    "assigned_agent": "Smith",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Store failed-task lessons",
                    "description": "Store approved failed-task repair lessons.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    if kind == "resolve_pending_revisions":
        return {
            "title": "Self Mission: Resolve Pending Revisions",
            "description": "SpaceCommand detected tasks stuck in pending_revision and needs to summarize fixes.",
            "tasks": [
                {
                    "title": "Summarize pending revisions",
                    "description": "Review all pending_revision tasks and Sentinel revision notes. Summarize what each task needs to become approvable.",
                    "assigned_agent": "Command",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Write revision rules",
                    "description": "Write concise rules for agents to avoid repeating the current pending_revision mistakes.",
                    "assigned_agent": "Scribe",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Store revision lessons",
                    "description": "Store approved revision lessons for future runs.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    if kind == "reduce_drift":
        return {
            "title": "Self Mission: Reduce Agent Drift",
            "description": "SpaceCommand detected drift markers in its own outputs and needs anti-drift hardening.",
            "tasks": [
                {
                    "title": "Identify drift markers",
                    "description": "Review recent SpaceCommand outputs for drift markers: Alpha/Beta/Gamma, fake teams, wrong room status, dashboard drift, Signal already-built confusion, troops/weapons/combat, and fake commands.",
                    "assigned_agent": "Strategist",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Draft anti-drift patch rules",
                    "description": "Write exact anti-drift rules for affected agents and runners. Include deterministic registry injection and exact-task matching.",
                    "assigned_agent": "Scribe",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Create anti-drift implementation blueprint",
                    "description": "Create a local-only blueprint for implementing anti-drift guards in runners. Do not modify files.",
                    "assigned_agent": "Smith",
                    "priority": "medium",
                    "requires_review": True,
                },
                {
                    "title": "Store anti-drift lessons",
                    "description": "Store approved anti-drift lessons and known forbidden drift patterns.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    if kind == "review_human_approval_items":
        return {
            "title": "Self Mission: Review Human Approval Items",
            "description": "SpaceCommand detected tasks requiring human approval and needs a clear approval summary.",
            "tasks": [
                {
                    "title": "Summarize approval-required items",
                    "description": "Summarize all human_approval_required tasks and explain exactly what approval would be needed before proceeding.",
                    "assigned_agent": "Echo",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Review approval risks",
                    "description": "Review the approval-required items for safety, external action risk, account access risk, spending risk, and data-sharing risk.",
                    "assigned_agent": "Sentinel",
                    "priority": "high",
                    "requires_review": False,
                },
                {
                    "title": "Store approval-gate lessons",
                    "description": "Store approved approval-gate lessons.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    return {
        "title": "Self Mission: Routine SpaceCommand Improvement",
        "description": "SpaceCommand found no blockers and will perform a safe local self-improvement pass.",
        "tasks": [
            {
                "title": "Review current system status",
                "description": "Review missions, tasks, approved items, revision requests, and known drift issues. Recommend one safe local improvement.",
                "assigned_agent": "Overseer",
                "priority": "medium",
                "requires_review": True,
            },
            {
                "title": "Create improvement task plan",
                "description": "Create a concise local-only improvement plan based on the status review.",
                "assigned_agent": "Command",
                "priority": "medium",
                "requires_review": True,
            },
            {
                "title": "Store self-improvement lessons",
                "description": "Store approved self-improvement lessons.",
                "assigned_agent": "Archivist",
                "priority": "low",
                "requires_review": False,
            },
        ],
    }


def active_similar_mission_exists(kind: str) -> bool:
    missions = load_missions()

    kind_terms = {
        "reduce_drift": ["drift", "hallucination", "stability"],
        "resolve_pending_revisions": ["revision", "pending"],
        "repair_failed_tasks": ["failed", "repair"],
        "review_human_approval_items": ["approval"],
        "routine_self_improvement": ["improvement", "self"],
    }

    terms = kind_terms.get(kind, [kind.replace("_", " ")])

    for mission in missions:
        if mission.get("status") != "active":
            continue

        text = (mission.get("title", "") + " " + mission.get("description", "")).lower()

        if any(term in text for term in terms):
            return True

    return False


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand self-maintenance mission.")
    parser.add_argument("--kind", default="auto", choices=[
        "auto",
        "repair_failed_tasks",
        "resolve_pending_revisions",
        "reduce_drift",
        "review_human_approval_items",
        "routine_self_improvement",
    ])
    args = parser.parse_args()

    kind = detect_self_mission_type() if args.kind == "auto" else args.kind
    if active_similar_mission_exists(kind):
        print()
        print("# Self Mission Skipped")
        print()
        print(f"Detected Kind: {kind}")
        print("Reason: A similar active mission already exists.")
        print("Safe Next Step: Run pending tasks from the existing mission instead.")
        print()
        return

    mission_plan = build_self_mission(kind)

    mission = create_mission(
        title=mission_plan["title"],
        description=mission_plan["description"],
        tasks_to_create=mission_plan["tasks"],
    )

    print()
    print("# Self Mission Created")
    print()
    print(f"Detected Kind: {kind}")
    print(f"Mission ID: {mission['id']}")
    print(f"Title: {mission['title']}")
    print(f"Status: {mission['status']}")
    print()
    print("Tasks:")
    for task_id in mission["task_ids"]:
        print(f"- {task_id}")
    print()


if __name__ == "__main__":
    main()

