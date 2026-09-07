import argparse

from pipeline_contracts import PUBLISH_PACKAGES_FILE, load_json
from publishing_dock import create_etsy_draft_listing
from etsy_listing_settings import get_or_prepare_settings


def find_by_id(records, record_id):
    for record in records:
        if record.get("id") == record_id:
            return record
    return None


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a real DRAFT listing on YOUR OWN Etsy shop from a local publish package. "
            "Never activates the listing — you finish that yourself in Etsy Seller Manager."
        )
    )
    parser.add_argument("--publish-package-id", required=True)
    parser.add_argument("--i-approve-this-live-etsy-action", action="store_true", dest="approved",
                         help="Required. Explicit acknowledgement that this will call the real Etsy API.")

    # Category + shop settings. All optional now: if omitted, this script
    # auto-resolves them via etsy_listing_settings.py (the "Selected
    # category" plus shipping/return/readiness-state settings), using a
    # cached result from prepare_etsy_listing_settings.py when one exists,
    # or computing it fresh on the spot otherwise. Pass any of these flags
    # explicitly to override the auto-resolved value.
    parser.add_argument("--taxonomy-id", type=int, default=None,
                         help="Etsy taxonomy id ('Selected category'). Auto-resolved from the design package if omitted — see etsy_listing_settings.py / prepare_etsy_listing_settings.py.")
    parser.add_argument("--shipping-profile-id", type=int, default=None,
                         help="Auto-resolved to the shop's default shipping profile if omitted.")
    parser.add_argument("--return-policy-id", type=int, default=None,
                         help="Auto-resolved to the shop's return policy if omitted.")
    parser.add_argument("--readiness-state-id", type=int, default=None,
                         help="Etsy processing-profile id, required for physical listings since Etsy's readiness-state migration. Auto-resolved (reused or created) if omitted.")
    parser.add_argument("--shop-section-id", type=int, default=None,
                         help="Auto-resolved by matching the design's keywords against the shop's section titles, if a confident match exists.")
    parser.add_argument("--refresh-settings", action="store_true",
                         help="Ignore any cached etsy_listing_settings.json entry and re-resolve category/shipping/return/readiness-state from Etsy now.")

    parser.add_argument("--who-made", default="i_did", choices=["i_did", "someone_else", "collective"])
    parser.add_argument("--when-made", default="made_to_order")
    parser.add_argument("--quantity", type=int, default=999)
    parser.add_argument("--digital", action="store_true", help="Mark this as a digital listing (skips shipping profile / readiness state).")

    # Previously supported by etsy_api_client.py but never exposed here.
    parser.add_argument("--materials", default="", help="Comma-separated list, e.g. 'paper,ink'. Max 13.")
    parser.add_argument("--item-weight", type=float, default=None)
    parser.add_argument("--item-weight-unit", default=None, choices=[None, "oz", "lb", "g", "kg"])
    parser.add_argument("--item-length", type=float, default=None)
    parser.add_argument("--item-width", type=float, default=None)
    parser.add_argument("--item-height", type=float, default=None)
    parser.add_argument("--item-dimensions-unit", default=None, choices=[None, "in", "ft", "mm", "cm", "m"])
    parser.add_argument("--personalizable", action="store_true", help="Buyers can add custom personalization text.")
    parser.add_argument("--personalization-required", action="store_true")
    parser.add_argument("--personalization-instructions", default=None)

    args = parser.parse_args()

    if not args.approved:
        print()
        print("# Etsy Draft Create Blocked")
        print()
        print("Re-run with --i-approve-this-live-etsy-action to confirm you want this")
        print("script to make a real (draft-only) write call to your Etsy shop.")
        print()
        return

    packages = load_json(PUBLISH_PACKAGES_FILE, [])
    package = find_by_id(packages, args.publish_package_id)

    taxonomy_id = args.taxonomy_id
    shipping_profile_id = args.shipping_profile_id
    return_policy_id = args.return_policy_id
    readiness_state_id = args.readiness_state_id
    shop_section_id = args.shop_section_id

    needs_auto_resolve = not args.digital and any(
        value is None for value in (taxonomy_id, shipping_profile_id, return_policy_id, readiness_state_id)
    )

    if needs_auto_resolve and package and package.get("design_package_id"):
        settings = get_or_prepare_settings(
            design_package_id=package["design_package_id"],
            force_refresh=args.refresh_settings,
        )

        print()
        print("# Auto-Resolved Etsy Listing Settings")
        print(f"(from {settings['id']}, design package {settings['design_package_id']})")
        print()

        if taxonomy_id is None:
            taxonomy_id = settings.get("taxonomy_id")
            print(f"Selected category (auto): {taxonomy_id} — {settings.get('taxonomy_path')}")
        if shipping_profile_id is None:
            shipping_profile_id = settings.get("shipping_profile_id")
            print(f"Shipping profile (auto): {shipping_profile_id} — {settings.get('shipping_profile_title')}")
        if return_policy_id is None:
            return_policy_id = settings.get("return_policy_id")
            print(f"Return policy (auto): {return_policy_id}")
        if readiness_state_id is None:
            readiness_state_id = settings.get("readiness_state_id")
            print(f"Readiness state / processing profile (auto): {readiness_state_id} — {settings.get('readiness_state')}")
        if shop_section_id is None and settings.get("shop_section_id"):
            shop_section_id = settings.get("shop_section_id")
            print(f"Shop section (auto): {shop_section_id} — {settings.get('shop_section_title')}")

        if settings.get("issues"):
            print(f"Issues: {', '.join(settings['issues'])}")

        print()

    if taxonomy_id is None:
        print()
        print("# Etsy Draft Create Blocked")
        print()
        print("No taxonomy_id ('Selected category') available. Pass --taxonomy-id, or run")
        print("prepare_etsy_listing_settings.py --design-package-id <id> first so this")
        print("script can auto-resolve one.")
        print()
        return

    run = create_etsy_draft_listing(
        publish_package_id=args.publish_package_id,
        user_approved_live_action=True,
        taxonomy_id=taxonomy_id,
        who_made=args.who_made,
        when_made=args.when_made,
        quantity=args.quantity,
        is_digital=args.digital,
        shipping_profile_id=shipping_profile_id,
        return_policy_id=return_policy_id,
        readiness_state_id=readiness_state_id,
        shop_section_id=shop_section_id,
        materials=csv_list(args.materials),
        item_weight=args.item_weight,
        item_length=args.item_length,
        item_width=args.item_width,
        item_height=args.item_height,
        item_weight_unit=args.item_weight_unit,
        item_dimensions_unit=args.item_dimensions_unit,
        is_personalizable=args.personalizable,
        personalization_is_required=args.personalization_required,
        personalization_instructions=args.personalization_instructions,
    )

    print()
    print("# Etsy Draft Create Result")
    print()
    print(f"Status: {run.get('status')}")
    print(f"Publish Package: {run.get('publish_package_id')}")

    if run.get("etsy_draft_created"):
        print(f"Etsy Listing ID: {run.get('etsy_listing_id')}")
        print(f"Etsy Listing State: {run.get('etsy_listing_state')}")
        print(f"Review/finish it here: {run.get('etsy_draft_url')}")
    else:
        print(f"Issues: {', '.join(run.get('issues', [])) or 'none'}")
        if run.get("error"):
            print(f"Error: {run.get('error')}")

    print()


if __name__ == "__main__":
    main()
