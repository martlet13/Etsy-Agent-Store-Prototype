import argparse
from spacecommand_task_manager import create_mission


def trend_watch(window: str, theme: str):
    priority = "high" if window == "daily" else "medium"

    return {
        "title": f"{window.capitalize()} Trend Watch: {theme}",
        "description": f"Run a {window} trend intelligence pass for {theme}.",
        "tasks": [
            {
                "title": f"Create {window} trend intelligence report",
                "description": f"Create a {window} Nova trend report for {theme}. Identify what product categories, product styles, and POD formats appear promising. Use only provided/local/public-source notes. If evidence is missing, say evidence_missing.",
                "assigned_agent": "Nova",
                "priority": priority,
                "requires_review": True,
            },
            {
                "title": f"Review {window} trend risks",
                "description": f"Review the {window} trend report for weak evidence, copyright/trademark risk, copied-product risk, unsupported sales claims, and unclear product direction.",
                "assigned_agent": "Sentinel",
                "priority": priority,
                "requires_review": False,
            },
            {
                "title": f"Store {window} trend lessons",
                "description": f"Store approved {window} trend findings, rejected assumptions, and Ledger cost needs.",
                "assigned_agent": "Archivist",
                "priority": "medium",
                "requires_review": False,
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Create a Nova trend-watch mission.")
    parser.add_argument("--window", choices=["daily", "weekly", "monthly"], required=True)
    parser.add_argument("--theme", default="general POD products")
    args = parser.parse_args()

    plan = trend_watch(args.window, args.theme)

    mission = create_mission(
        title=plan["title"],
        description=plan["description"],
        tasks_to_create=plan["tasks"],
    )

    print()
    print("# Trend Mission Created")
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
