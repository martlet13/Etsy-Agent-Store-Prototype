"""
Preparation script: auto-resolve and cache the Etsy "Selected category"
(taxonomy_id) plus the other shop-level settings a physical Etsy draft
listing needs — shipping profile, return policy, processing/"readiness
state" profile, and (if a good match exists) a shop section.

Run this once per design package, ideally right after Ledger PASS and
before Scribe/Publisher, so create_etsy_draft.py never has to be run
with hand-looked-up Etsy IDs again:

    python prepare_etsy_listing_settings.py --design-package-id DESIGN-0001

This only reads from Etsy (seller-taxonomy, shipping profiles, return
policies, shop sections) and — if the shop doesn't have one yet — makes
one narrow, idempotent write to register a reusable processing profile
(createShopReadinessStateDefinition). It never creates or touches a
listing. It is gated on the same "etsy" connector approval as
create_etsy_draft.py, since it still makes real calls to api.etsy.com.
"""

import argparse
import json

from api_connector_manager import evaluate_connector, get_connector

from etsy_listing_settings import prepare_listing_settings, keywords_for_design_package


def main():
    parser = argparse.ArgumentParser(
        description="Auto-resolve Etsy category/shipping/return/readiness-state settings for a design package."
    )
    parser.add_argument("--design-package-id", required=True)
    parser.add_argument("--readiness-state", default="made_to_order", choices=["made_to_order", "ready_to_ship"])
    parser.add_argument("--min-processing-days", type=int, default=3)
    parser.add_argument("--max-processing-days", type=int, default=5)
    parser.add_argument("--show-keywords-only", action="store_true",
                         help="Print the derived keyword list without calling Etsy (no connector needed).")

    args = parser.parse_args()

    if args.show_keywords_only:
        keywords = keywords_for_design_package(args.design_package_id)
        print()
        print("# Derived Taxonomy-Matching Keywords")
        print()
        print(", ".join(keywords) or "(none found — check the design_package_id)")
        print()
        return

    connector = get_connector("etsy")
    evaluation = evaluate_connector(connector) if connector else None
    connector_live_ready = bool(evaluation and evaluation.get("computed_status") == "live_enabled")

    if not connector_live_ready:
        print()
        print("# Etsy Listing Settings Preparation Blocked")
        print()
        print("The 'etsy' connector isn't live-approved yet (needs a stored API key,")
        print("user_approved=true, and live_actions_enabled=true).")
        print("Run set_api_connector_approval.py first — see check_api_connectors.py")
        print("for current status.")
        print()
        return

    record = prepare_listing_settings(
        design_package_id=args.design_package_id,
        readiness_state=args.readiness_state,
        min_processing_days=args.min_processing_days,
        max_processing_days=args.max_processing_days,
    )

    print()
    print("# Etsy Listing Settings Prepared")
    print()
    print(f"ID: {record['id']}")
    print(f"Design Package: {record['design_package_id']}")
    print()
    print("## Selected Category (best guess — please confirm)")
    print(f"taxonomy_id: {record['taxonomy_id']}")
    print(f"path: {record['taxonomy_path']}")

    if record["taxonomy_alternatives"]:
        print()
        print("Alternatives, if the top guess looks wrong:")
        for alt in record["taxonomy_alternatives"]:
            print(f"  - {alt['id']}: {alt['path']} (score {alt['score']})")

    print()
    print("## Shipping / Return / Processing")
    print(f"shipping_profile_id: {record['shipping_profile_id']} ({record['shipping_profile_title']})")
    print(f"return_policy_id: {record['return_policy_id']}")
    print(f"readiness_state_id: {record['readiness_state_id']} ({record['readiness_state']})")

    if record["shop_section_id"]:
        print(f"shop_section_id: {record['shop_section_id']} ({record['shop_section_title']})")
    else:
        print("shop_section_id: none matched — will be left unset")

    if record["issues"]:
        print()
        print(f"Issues: {', '.join(record['issues'])}")

    print()
    print("create_etsy_draft.py will now use these automatically for this design")
    print("package unless you pass an explicit override flag (e.g. --taxonomy-id).")
    print()


if __name__ == "__main__":
    main()
