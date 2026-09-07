import argparse

from publishing_dock import create_etsy_draft_listing


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
    parser.add_argument("--taxonomy-id", type=int, required=True, help="Etsy taxonomy id for this listing (see run_next_task.py / taxonomy lookup helpers).")
    parser.add_argument("--who-made", default="i_did", choices=["i_did", "someone_else", "collective"])
    parser.add_argument("--when-made", default="made_to_order")
    parser.add_argument("--quantity", type=int, default=999)
    parser.add_argument("--digital", action="store_true", help="Mark this as a digital listing (skips shipping profile).")
    parser.add_argument("--shipping-profile-id", type=int, default=None)
    parser.add_argument("--return-policy-id", type=int, default=None)
    parser.add_argument("--readiness-state-id", type=int, default=None,
                         help="Etsy processing-profile id, required for physical listings since Etsy's readiness-state migration. See get_readiness_state_definitions()/create_readiness_state_definition() in etsy_api_client.py.")
    parser.add_argument("--shop-section-id", type=int, default=None)

    args = parser.parse_args()

    if not args.approved:
        print()
        print("# Etsy Draft Create Blocked")
        print()
        print("Re-run with --i-approve-this-live-etsy-action to confirm you want this")
        print("script to make a real (draft-only) write call to your Etsy shop.")
        print()
        return

    run = create_etsy_draft_listing(
        publish_package_id=args.publish_package_id,
        user_approved_live_action=True,
        taxonomy_id=args.taxonomy_id,
        who_made=args.who_made,
        when_made=args.when_made,
        quantity=args.quantity,
        is_digital=args.digital,
        shipping_profile_id=args.shipping_profile_id,
        return_policy_id=args.return_policy_id,
        readiness_state_id=args.readiness_state_id,
        shop_section_id=args.shop_section_id,
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
