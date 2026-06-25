import argparse
from spacecommand_task_manager import create_mission


def pod_batch(theme: str, count: int):
    return {
        "title": f"POD Product Batch: {theme}",
        "description": f"Create a profit-gated print-on-demand product batch for theme: {theme}. Count target: {count}.",
        "tasks": [
            {
                "title": "Create market hypotheses for POD batch",
                "description": f"Create {count} market hypotheses for a print-on-demand batch around this theme: {theme}. Include target buyer, product type candidates, buyer intent, keyword/listing angle, and trademark/copyright risk flags. Do not browse or claim current market data unless provided by the user.",
                "assigned_agent": "Nova",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Create product design packages",
                "description": f"Create {count} original product design packages for theme: {theme}. Include design concept, image prompt, product fit, print-area notes, aspect ratio, transparent background requirement, color limitations, mockup placement notes, and filenames. Do not create or upload actual products.",
                "assigned_agent": "Forge",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Run Ledger unit economics gate",
                "description": "Evaluate draft products using products.json, supplier_costs.json, and pricing_rules.json. Calculate production cost, shipping, Etsy fees, processing, return/reprint allowance, optional offsite ads, profit, margin, break-even, recommended minimum price, and PASS/FAIL/NEEDS_PRICE_CHANGE. Products without verified cost and shipping data must FAIL.",
                "assigned_agent": "Ledger",
                "priority": "high",
                "requires_review": True,
            },
            {
                "title": "Review product economics gate",
                "description": "Review Ledger's product economics output. Reject or require revision if there is no Ledger PASS, missing supplier costs, unknown shipping, price below break-even, trademark/copyright risk, or fake external action claims.",
                "assigned_agent": "Sentinel",
                "priority": "high",
                "requires_review": False,
            },
            {
                "title": "Write listing drafts for Ledger PASS products only",
                "description": "Write Etsy-style listing drafts only for products with Ledger PASS. Include title, description, tags, materials/production notes, shipping disclaimer draft, return/reprint wording draft, and image alt text. Do not write listings for FAIL or NEEDS_PRICE_CHANGE products.",
                "assigned_agent": "Scribe",
                "priority": "medium",
                "requires_review": True,
            },
            {
                "title": "Create promo drafts for Ledger PASS products only",
                "description": "Create local-only promo captions, short video hooks, thumbnail concepts, and content notes only for Ledger PASS products. Do not post, upload, or schedule anything.",
                "assigned_agent": "Signal",
                "priority": "medium",
                "requires_review": True,
            },
            {
                "title": "Store approved production batch lessons",
                "description": "Store approved product batch lessons, profit-gate rules, failed-product reasons, and reusable production patterns.",
                "assigned_agent": "Archivist",
                "priority": "medium",
                "requires_review": False,
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V5 production mission.")
    parser.add_argument("--type", choices=["pod_batch"], default="pod_batch")
    parser.add_argument("--theme", required=True)
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    if args.type == "pod_batch":
        plan = pod_batch(args.theme, args.count)
    else:
        raise ValueError(f"Unsupported production mission type: {args.type}")

    mission = create_mission(
        title=plan["title"],
        description=plan["description"],
        tasks_to_create=plan["tasks"],
    )

    print()
    print("# Production Mission Created")
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
