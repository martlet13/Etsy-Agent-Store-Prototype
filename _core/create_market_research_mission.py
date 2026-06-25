import argparse

from spacecommand_task_manager import create_mission


def create_market_research_plan(theme: str, window: str):
    return {
        "title": f"Market Research Pipeline: {theme}",
        "description": f"Run a V6 evidence-first market research pipeline for {theme}. Window: {window}.",
        "tasks": [
            {
                "title": "Collect market evidence cards",
                "description": f"Nova must collect or create evidence cards for {theme}. Use public/read-only sources only unless the user has approved a login/API connector. If no real data source is available, create evidence_missing cards and mark opportunities as hypothesis-only. Do not claim popularity, best-selling status, or demand without evidence cards.",
                "assigned_agent": "Nova",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Create opportunity cards from evidence",
                "description": f"Nova must turn valid evidence cards for {theme} into opportunity cards. Each opportunity card must reference source_evidence_ids. If evidence is missing, status must remain hypothesis_only and recommended action must be evidence collection, not production.",
                "assigned_agent": "Nova",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Audit evidence and opportunity handoffs",
                "description": "Overseer must audit the V6 pipeline. Check that evidence_cards.json, opportunity_cards.json, and agent_handoffs.json exist and that no opportunity claims demand without evidence. Run or reference run_pipeline_audit.py. Stop the pipeline if blockers exist.",
                "assigned_agent": "Overseer",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Review market evidence truthfulness",
                "description": "Sentinel must review the evidence and opportunity chain. Reject unsupported demand claims, fake sales claims, missing evidence, protected IP risks, or any attempt to move to production without evidence.",
                "assigned_agent": "Sentinel",
                "priority": "high",
                "requires_review": False,
            },
            {
                "title": "Store market research lessons",
                "description": "Archivist must store approved evidence rules, rejected unsupported claims, source quality notes, and safe handoff patterns.",
                "assigned_agent": "Archivist",
                "priority": "medium",
                "requires_review": False,
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Create a V6 market research pipeline mission.")
    parser.add_argument("--theme", required=True)
    parser.add_argument("--window", choices=["daily", "weekly", "monthly"], default="weekly")
    args = parser.parse_args()

    plan = create_market_research_plan(args.theme, args.window)

    mission = create_mission(
        title=plan["title"],
        description=plan["description"],
        tasks_to_create=plan["tasks"],
    )

    print()
    print("# V6 Market Research Mission Created")
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
