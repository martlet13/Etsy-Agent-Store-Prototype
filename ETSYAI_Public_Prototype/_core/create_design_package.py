import argparse
from datetime import datetime

from pipeline_contracts import (
    OPPORTUNITY_FILE,
    EVIDENCE_FILE,
    DESIGN_FILE,
    create_handoff,
    load_json,
    save_json,
    next_id,
)


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def opportunity_evidence_level(opportunity):
    evidence_cards = load_json(EVIDENCE_FILE, [])
    evidence_by_id = {x.get("id"): x for x in evidence_cards}

    evidence_ids = opportunity.get("source_evidence_ids", [])
    strengths = []

    for evidence_id in evidence_ids:
        card = evidence_by_id.get(evidence_id)
        if card:
            strengths.append(str(card.get("evidence_strength", "missing")).lower())

    if not strengths:
        return "missing"

    if any(x == "verified" for x in strengths):
        return "verified"

    if any(x == "provided" for x in strengths):
        return "provided"

    if any(x == "weak" for x in strengths):
        return "weak"

    if any(x == "hypothesis" for x in strengths):
        return "hypothesis"

    return "missing"


def design_status_from_opportunity(opportunity):
    opp_status = opportunity.get("status")
    evidence_level = opportunity_evidence_level(opportunity)

    if opp_status == "hypothesis_only":
        return {
            "status": "concept_only",
            "production_allowed": False,
            "reason": "opportunity_is_hypothesis_only",
            "evidence_level": evidence_level,
        }

    if evidence_level in {"missing", "hypothesis", "weak"}:
        return {
            "status": "concept_only",
            "production_allowed": False,
            "reason": "evidence_not_strong_enough_for_production",
            "evidence_level": evidence_level,
        }

    if evidence_level in {"provided", "verified"}:
        return {
            "status": "ready_for_ledger",
            "production_allowed": False,
            "reason": "ready_for_ledger_but_production_requires_ledger_pass",
            "evidence_level": evidence_level,
        }

    return {
        "status": "concept_only",
        "production_allowed": False,
        "reason": "unknown_evidence_state",
        "evidence_level": evidence_level,
    }


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V6 design package from an opportunity card.")
    parser.add_argument("--opportunity-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--design-concept", required=True)
    parser.add_argument("--image-prompt", required=True)
    parser.add_argument("--product-fit", default="")
    parser.add_argument("--print-area-notes", default="")
    parser.add_argument("--aspect-ratio", default="unknown")
    parser.add_argument("--transparent-background", choices=["true", "false"], default="false")
    parser.add_argument("--mockup-notes", default="")
    parser.add_argument("--filename-stem", required=True)
    parser.add_argument("--copyright-trademark-risk", default="unknown")
    parser.add_argument("--safety-notes", default="")
    parser.add_argument("--create-handoff", action="store_true")

    args = parser.parse_args()

    opportunities = load_json(OPPORTUNITY_FILE, [])
    opportunity_ids = {x.get("id") for x in opportunities}

    designs = load_json(DESIGN_FILE, [])

    if args.opportunity_id not in opportunity_ids:
        print()
        print("# Design Package Blocked")
        print()
        print(f"Missing opportunity card: {args.opportunity_id}")
        print("Forge cannot create a design package without a valid opportunity_id.")
        return

    opportunity = next(x for x in opportunities if x.get("id") == args.opportunity_id)
    gate = design_status_from_opportunity(opportunity)

    design = {
        "id": next_id("DESIGN", designs),
        "type": "design_package",
        "status": gate["status"],
        "opportunity_id": args.opportunity_id,
        "opportunity_status": opportunity.get("status"),
        "evidence_level": gate["evidence_level"],
        "gate_reason": gate["reason"],
        "title": args.title,
        "design_concept": args.design_concept,
        "image_prompt": args.image_prompt,
        "product_fit": csv_list(args.product_fit),
        "print_area_notes": args.print_area_notes,
        "aspect_ratio": args.aspect_ratio,
        "transparent_background": args.transparent_background == "true",
        "mockup_notes": args.mockup_notes,
        "filename_stem": args.filename_stem,
        "copyright_trademark_risk": args.copyright_trademark_risk,
        "safety_notes": args.safety_notes,
        "production_allowed": gate["production_allowed"],
        "listing_allowed": False,
        "created_at": now_stamp(),
    }

    designs.append(design)
    save_json(DESIGN_FILE, designs)

    handoff = None
    if args.create_handoff:
        if design["status"] == "ready_for_ledger":
            required_next_action = "Ledger may calculate unit economics. Production and listing remain blocked until Ledger PASS."
            status = "ready_for_ledger"
        else:
            required_next_action = "This is concept-only. Collect stronger evidence before Ledger/pricing/production."
            status = "concept_only_blocked_from_production"

        handoff = create_handoff(
            from_agent="Forge",
            to_agent="Ledger" if design["status"] == "ready_for_ledger" else "Overseer",
            artifact_type="design_package",
            artifact_id=design["id"],
            summary=f"Design package created with status {design['status']}. Evidence level: {design['evidence_level']}. Production allowed: {design['production_allowed']}",
            required_next_action=required_next_action,
            status=status,
        )

    print()
    print("# Design Package Created")
    print()
    print(f"ID: {design['id']}")
    print(f"Title: {design['title']}")
    print(f"Opportunity ID: {design['opportunity_id']}")
    print(f"Evidence Level: {design['evidence_level']}")
    print(f"Gate Reason: {design['gate_reason']}")
    print(f"Status: {design['status']}")
    print(f"Production Allowed: {design['production_allowed']}")
    print(f"Listing Allowed: {design['listing_allowed']}")

    if handoff:
        print()
        print("# Handoff Created")
        print(f"ID: {handoff['id']}")
        print(f"From: {handoff['from_agent']}")
        print(f"To: {handoff['to_agent']}")
        print(f"Status: {handoff['status']}")
        print(f"Artifact: {handoff['artifact_id']}")

    print()


if __name__ == "__main__":
    main()
