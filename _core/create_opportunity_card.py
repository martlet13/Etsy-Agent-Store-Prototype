import argparse

from pipeline_contracts import create_opportunity_card, create_handoff


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V6 opportunity card.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--evidence-ids", default="")
    parser.add_argument("--product-category", required=True)
    parser.add_argument("--design-lane", required=True)
    parser.add_argument("--design-style", required=True)
    parser.add_argument("--emotional-angle", required=True)
    parser.add_argument("--buyer-moment", required=True)
    parser.add_argument("--seasonal-timing", default="unknown")
    parser.add_argument("--product-fit", default="")
    parser.add_argument("--copyright-trademark-risk", default="unknown")
    parser.add_argument("--original-safe-angle", required=True)
    parser.add_argument("--confidence", choices=["low", "medium-low", "medium", "high"], default="low")
    parser.add_argument("--recommended-action", default="Collect evidence and Ledger costs before production.")
    parser.add_argument("--notes", default="")
    parser.add_argument("--create-handoff", action="store_true")

    args = parser.parse_args()

    card = create_opportunity_card(
        title=args.title,
        source_evidence_ids=csv_list(args.evidence_ids),
        product_category=args.product_category,
        design_lane=args.design_lane,
        design_style=args.design_style,
        emotional_angle=args.emotional_angle,
        buyer_moment=args.buyer_moment,
        seasonal_timing=args.seasonal_timing,
        product_fit=csv_list(args.product_fit),
        copyright_trademark_risk=args.copyright_trademark_risk,
        original_safe_angle=args.original_safe_angle,
        confidence=args.confidence,
        recommended_action=args.recommended_action,
        notes=args.notes,
    )

    handoff = None
    if args.create_handoff:
        handoff = create_handoff(
            from_agent="Nova",
            to_agent="Forge",
            artifact_type="opportunity_card",
            artifact_id=card["id"],
            summary=f"Opportunity card ready for Forge only if status allows: {card['status']}",
            required_next_action="Forge may create design packages only for evidence-backed or explicitly approved hypothesis opportunities.",
        )

    print()
    print("# Opportunity Card Created")
    print()
    print(f"ID: {card['id']}")
    print(f"Title: {card['title']}")
    print(f"Status: {card['status']}")
    print(f"Evidence IDs: {', '.join(card['source_evidence_ids']) or 'none'}")
    print(f"Confidence: {card['confidence']}")

    if handoff:
        print()
        print("# Handoff Created")
        print(f"ID: {handoff['id']}")
        print(f"From: {handoff['from_agent']}")
        print(f"To: {handoff['to_agent']}")
        print(f"Artifact: {handoff['artifact_id']}")

    print()


if __name__ == "__main__":
    main()
