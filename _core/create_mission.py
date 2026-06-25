import argparse
from spacecommand_task_manager import create_mission


MISSION_TEMPLATES = {
    "launcher_reliability": {
        "title": "Improve SpaceCommand Launcher Reliability",
        "description": "Strengthen the launcher, review its safety, document rules, and store approved patterns.",
        "tasks": [
            {
                "title": "Audit launcher weaknesses",
                "description": "Review the current Start-SpaceCommand.ps1 launcher and identify reliability, usability, encoding, confirmation, and Sentinel-review weaknesses. Draft-only. Do not modify files.",
                "assigned_agent": "Smith",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Write launcher v2 specification",
                "description": "Write a clear specification for the next launcher upgrade based on Smith's audit. Include user flow, safety gates, save behavior, Sentinel review behavior, and error handling.",
                "assigned_agent": "Scribe",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Create launcher improvement plan",
                "description": "Create a local-only implementation plan for improving the launcher after the spec is approved. Do not execute changes.",
                "assigned_agent": "Command",
                "priority": "medium",
                "requires_review": True,
            },
            {
                "title": "Store launcher lessons",
                "description": "Record the approved launcher reliability lessons, safety boundaries, and known drift issues for future SpaceCommand coordination.",
                "assigned_agent": "Archivist",
                "priority": "medium",
                "requires_review": False,
            },
        ],
    },
    "agent_stability": {
        "title": "Improve Agent Stability",
        "description": "Reduce hallucination and drift across SpaceCommand agents.",
        "tasks": [
            {
                "title": "Identify agent drift patterns",
                "description": "Review known drift issues for Strategist, Command, Smith, Overseer, and Sentinel. Create a concise drift pattern report.",
                "assigned_agent": "Strategist",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Draft anti-drift rules",
                "description": "Create agent prompt rules that prevent invented rooms, fake teams, fake tools, wrong built-status claims, and fake commands.",
                "assigned_agent": "Scribe",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Create anti-drift safety blueprint",
                "description": "Create a local-only blueprint for how the launcher and runners should inject deterministic registries into agent prompts.",
                "assigned_agent": "Smith",
                "priority": "medium",
                "requires_review": True,
            },
            {
                "title": "Store anti-drift lessons",
                "description": "Record approved anti-drift rules as permanent SpaceCommand lessons.",
                "assigned_agent": "Archivist",
                "priority": "medium",
                "requires_review": False,
            },
        ],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a SpaceCommand mission with queued tasks.")
    parser.add_argument("--template", choices=MISSION_TEMPLATES.keys(), default="launcher_reliability")
    parser.add_argument("--title", default=None)
    parser.add_argument("--description", default=None)
    args = parser.parse_args()

    template = MISSION_TEMPLATES[args.template]

    mission = create_mission(
        title=args.title or template["title"],
        description=args.description or template["description"],
        tasks_to_create=template["tasks"],
    )

    print()
    print("# Mission Created")
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
