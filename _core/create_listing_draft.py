import argparse
from datetime import datetime

from pipeline_contracts import (
    ECONOMICS_FILE,
    LISTINGS_FILE,
    load_json,
    save_json,
    next_id,
    create_handoff,
)


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V6 listing draft from a Ledger PASS unit economics card.")
    parser.add_argument("--unit-economics-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--tags", default="")
    parser.add_argument("--materials", default="")
    parser.add_argument("--shipping-disclaimer", default="")
    parser.add_argument("--return-reprint-wording", default="")
    parser.add_argument("--image-alt-text", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--create-handoff", action="store_true")

    args = parser.parse_args()

    economics_cards = load_json(ECONOMICS_FILE, [])
    economics_ids = {x.get("id") for x in economics_cards}

    if args.unit_economics_id not in economics_ids:
        print()
        print("# Listing Draft Blocked")
        print()
        print(f"Missing unit economics card: {args.unit_economics_id}")
        print("Scribe cannot create a listing draft without a valid unit_economics_id.")
        return

    econ = next(x for x in economics_cards if x.get("id") == args.unit_economics_id)

    if econ.get("ledger_decision") != "PASS" or not econ.get("listing_allowed", False):
        print()
        print("# Listing Draft Blocked")
        print()
        print(f"Unit Economics ID: {args.unit_economics_id}")
        print(f"Ledger Decision: {econ.get('ledger_decision')}")
        print(f"Listing Allowed: {econ.get('listing_allowed')}")
        print("Scribe cannot write listing drafts until Ledger PASS exists.")
        return

    listings = load_json(LISTINGS_FILE, [])

    listing = {
        "id": next_id("LISTING", listings),
        "type": "listing_draft",
        "status": "draft_pending_sentinel_review",
        "unit_economics_id": args.unit_economics_id,
        "design_package_id": econ.get("design_package_id"),
        "ledger_decision": econ.get("ledger_decision"),
        "supplier": econ.get("supplier"),
        "product_type": econ.get("product_type"),
        "variant": econ.get("variant"),
        "title": args.title,
        "description": args.description,
        "tags": csv_list(args.tags),
        "materials": args.materials,
        "shipping_disclaimer": args.shipping_disclaimer,
        "return_reprint_wording": args.return_reprint_wording,
        "image_alt_text": args.image_alt_text,
        "notes": args.notes,
        "external_action_allowed": False,
        "published": False,
        "created_at": now_stamp(),
    }

    listings.append(listing)
    save_json(LISTINGS_FILE, listings)

    handoff = None
    if args.create_handoff:
        handoff = create_handoff(
            from_agent="Scribe",
            to_agent="Sentinel",
            artifact_type="listing_draft",
            artifact_id=listing["id"],
            summary="Listing draft created from Ledger PASS unit economics card. External action remains blocked.",
            required_next_action="Sentinel must review listing claims, tags, trademark/copyright risk, pricing consistency, and external-action safety before any live testing.",
            status="pending_sentinel_review",
        )

    print()
    print("# Listing Draft Created")
    print()
    print(f"ID: {listing['id']}")
    print(f"Title: {listing['title']}")
    print(f"Unit Economics ID: {listing['unit_economics_id']}")
    print(f"Status: {listing['status']}")
    print(f"External Action Allowed: {listing['external_action_allowed']}")
    print(f"Published: {listing['published']}")

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
