import argparse
from spacecommand_task_manager import create_mission


def route_custom_mission(goal: str):
    lower = goal.lower()

    if any(word in lower for word in ["drift", "hallucination", "hallucinate", "stability", "wrong agent", "fake room"]):
        return {
            "title": goal,
            "description": "Reduce agent drift, hallucinations, fake room/agent claims, and misdirected outputs.",
            "tasks": [
                {
                    "title": "Identify current drift patterns",
                    "description": "Review known SpaceCommand drift issues and produce a concise report of the most common failure patterns. Focus on fake rooms, wrong task interpretation, stale next tasks, invented tools, and over-approval.",
                    "assigned_agent": "Strategist",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Write anti-drift agent rules",
                    "description": "Write clear anti-drift rules that can be added to agents and runners. Include rules for exact task matching, deterministic registries, no fake teams, no stale missions, and no dashboard drift when the task is launcher-specific.",
                    "assigned_agent": "Scribe",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Create deterministic prompt-injection blueprint",
                    "description": "Create a local-only technical blueprint for injecting deterministic task context, room registry, current mission status, and forbidden drift patterns into agent prompts.",
                    "assigned_agent": "Smith",
                    "priority": "medium",
                    "requires_review": True,
                },
                {
                    "title": "Store approved anti-drift lessons",
                    "description": "Store the approved drift patterns, anti-drift rules, and deterministic prompt lessons for future SpaceCommand runs.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    if any(word in lower for word in ["launcher", "menu", "powershell", "start-spacecommand"]):
        return {
            "title": goal,
            "description": "Improve the local Start-SpaceCommand.ps1 launcher and control flow.",
            "tasks": [
                {
                    "title": "Audit requested launcher upgrade",
                    "description": f"Audit the launcher upgrade request: {goal}. Identify safe local improvements, reliability issues, and user-flow risks. Draft-only. Do not modify files.",
                    "assigned_agent": "Smith",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Write launcher upgrade specification",
                    "description": f"Write a precise launcher specification for this goal: {goal}. Include save behavior, Sentinel review behavior, task manager integration, error handling, confirmation rules, and local-only boundaries.",
                    "assigned_agent": "Scribe",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Create launcher upgrade plan",
                    "description": f"Create an implementation plan for the launcher goal: {goal}. Do not execute changes.",
                    "assigned_agent": "Command",
                    "priority": "medium",
                    "requires_review": True,
                },
                {
                    "title": "Store launcher upgrade lessons",
                    "description": "Store the approved launcher upgrade lessons and safety boundaries.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    if any(word in lower for word in ["media", "video", "tiktok", "youtube", "short", "caption", "thumbnail"]):
        return {
            "title": goal,
            "description": "Create local-only media planning drafts for SpaceCommand.",
            "tasks": [
                {
                    "title": "Research media direction",
                    "description": f"Create a local-only research brief for this media goal: {goal}. Do not browse, post, upload, or schedule anything.",
                    "assigned_agent": "Nova",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Create media package",
                    "description": f"Create a local-only media package for this goal: {goal}. Include concepts, captions, thumbnail ideas, script outline, local filenames, and intended use.",
                    "assigned_agent": "Signal",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Write communication draft",
                    "description": "Create local-only status/update copy for the media package. Do not send messages.",
                    "assigned_agent": "Echo",
                    "priority": "medium",
                    "requires_review": True,
                },
                {
                    "title": "Store media lessons",
                    "description": "Store approved media planning lessons and reusable patterns.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    if any(word in lower for word in ["cost", "budget", "money", "treasury", "spend", "api", "subscription"]):
        return {
            "title": goal,
            "description": "Analyze local costs, budget risk, and approval gates.",
            "tasks": [
                {
                    "title": "Create cost impact report",
                    "description": f"Create a local-only cost impact report for this goal: {goal}. Do not buy anything or access accounts.",
                    "assigned_agent": "Ledger",
                    "priority": "high",
                    "requires_review": True,
                },
                {
                    "title": "Create budget-safe implementation plan",
                    "description": "Create a plan that separates free/local steps from approval-required paid steps.",
                    "assigned_agent": "Command",
                    "priority": "medium",
                    "requires_review": True,
                },
                {
                    "title": "Store cost-control lessons",
                    "description": "Store approved cost-control rules and spending approval lessons.",
                    "assigned_agent": "Archivist",
                    "priority": "medium",
                    "requires_review": False,
                },
            ],
        }

    return {
        "title": goal,
        "description": "General local-only SpaceCommand mission created from a user goal.",
        "tasks": [
            {
                "title": "Break mission into local tasks",
                "description": f"Analyze this user goal and create a practical local-only task breakdown: {goal}. Do not execute anything.",
                "assigned_agent": "Overseer",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Create implementation plan",
                "description": f"Create a local-only implementation plan for this mission: {goal}. Assign follow-up work to known SpaceCommand rooms only.",
                "assigned_agent": "Command",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Review mission risks",
                "description": f"Review this mission for safety, external-action risks, unclear scope, and approval gates: {goal}.",
                "assigned_agent": "Sentinel",
                "priority": "medium",
                "requires_review": False,
            },
            {
                "title": "Store mission lessons",
                "description": "Store approved mission lessons and reusable patterns.",
                "assigned_agent": "Archivist",
                "priority": "medium",
                "requires_review": False,
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Create a custom SpaceCommand mission from a plain-language goal.")
    parser.add_argument("goal", nargs="+", help="Mission goal")
    args = parser.parse_args()

    goal = " ".join(args.goal).strip()
    mission_plan = route_custom_mission(goal)

    mission = create_mission(
        title=mission_plan["title"],
        description=mission_plan["description"],
        tasks_to_create=mission_plan["tasks"],
    )

    print()
    print("# Custom Mission Created")
    print()
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
