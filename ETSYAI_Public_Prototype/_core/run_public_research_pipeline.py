import argparse
from pathlib import Path

from fetch_public_source import create_snapshot
from pipeline_contracts import create_evidence_card, create_opportunity_card, create_handoff
from research_connector_registry import create_connector_run


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(description="Run Nova V6.6 public research pipeline.")

    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--time-window", choices=["daily", "weekly", "monthly", "unknown"], default="weekly")

    parser.add_argument("--keyword", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--evidence-strength", choices=["missing", "hypothesis", "weak", "provided", "verified"], default="weak")
    parser.add_argument("--trend-direction", default="unknown")
    parser.add_argument("--confidence", choices=["low", "medium-low", "medium", "high"], default="medium-low")

    parser.add_argument("--create-opportunity", action="store_true")
    parser.add_argument("--opportunity-title", default="")
    parser.add_argument("--product-category", default="")
    parser.add_argument("--design-lane", default="")
    parser.add_argument("--design-style", default="")
    parser.add_argument("--emotional-angle", default="")
    parser.add_argument("--buyer-moment", default="")
    parser.add_argument("--seasonal-timing", default="unknown")
    parser.add_argument("--product-fit", default="")
    parser.add_argument("--copyright-trademark-risk", default="unknown")
    parser.add_argument("--original-safe-angle", default="")
    parser.add_argument("--recommended-action", default="Collect stronger marketplace evidence and verified Ledger costs before production.")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    print()
    print("# Nova Public Research Pipeline")
    print()

    snapshot = create_snapshot(
        connector_id=args.connector_id,
        url=args.url,
        query=args.query,
        theme=args.theme,
        time_window=args.time_window,
        max_chars=8000,
    )

    print(f"Snapshot ID: {snapshot['id']}")
    print(f"Snapshot Status: {snapshot['status']}")
    print(f"Snapshot Success: {snapshot['success']}")

    if snapshot.get("source_title"):
        print(f"Source Title: {snapshot.get('source_title')}")

    if not snapshot.get("success"):
        print()
        print("Pipeline stopped because public source fetch failed or connector was blocked.")
        if snapshot.get("error"):
            print(f"Error: {snapshot.get('error')}")
        print()
        return

    summary = snapshot.get("text_excerpt", "")
    title = snapshot.get("source_title") or args.url

    connector_run = create_connector_run(
        connector_id=args.connector_id,
        query=args.query,
        theme=args.theme,
        time_window=args.time_window,
        raw_summary=summary,
        source_url=args.url,
        source_title=title,
        metrics={
            "snapshot_id": snapshot["id"],
            "status_code": snapshot.get("status_code"),
            "text_char_count": snapshot.get("text_char_count"),
        },
        notes=args.notes or "Created by V6.6 public research pipeline.",
    )

    print(f"Connector Run ID: {connector_run['id']}")
    print(f"Connector Run Status: {connector_run['status']}")
    print(f"Connector Run Success: {connector_run.get('success')}")

    if not connector_run.get("success"):
        print()
        print("Pipeline stopped because connector run was not successful.")
        print()
        return

    evidence = create_evidence_card(
        source=connector_run.get("connector_name") or connector_run.get("connector_id"),
        source_type=connector_run.get("source_type", "public_source"),
        collection_method=f"connector:{connector_run.get('connector_id')}",
        permission_level=connector_run.get("permission_level", "unknown"),
        time_window=args.time_window,
        keyword=args.keyword,
        category=args.category,
        evidence_strength=args.evidence_strength,
        trend_direction=args.trend_direction,
        confidence=args.confidence,
        metrics={
            "connector_run_id": connector_run["id"],
            "snapshot_id": snapshot["id"],
            "source_url": args.url,
            "source_title": title,
            "text_char_count": snapshot.get("text_char_count"),
        },
        raw_snapshot_path=None,
        notes=(
            "Public source evidence created by Nova V6.6 public research pipeline. "
            "This is not private Etsy sales data and is not enough for production by itself. "
            + (args.notes or "")
        ),
    )

    print(f"Evidence ID: {evidence['id']}")
    print(f"Evidence Strength: {evidence['evidence_strength']}")
    print(f"Evidence Confidence: {evidence['confidence']}")

    if args.create_opportunity:
        required_fields = [
            args.opportunity_title,
            args.product_category,
            args.design_lane,
            args.design_style,
            args.emotional_angle,
            args.buyer_moment,
            args.original_safe_angle,
        ]

        if not all(required_fields):
            print()
            print("Opportunity creation skipped because required opportunity fields are missing.")
        else:
            opportunity = create_opportunity_card(
                title=args.opportunity_title,
                source_evidence_ids=[evidence["id"]],
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
                notes="Created from V6.6 public research pipeline.",
            )

            handoff = create_handoff(
                from_agent="Nova",
                to_agent="Forge",
                artifact_type="opportunity_card",
                artifact_id=opportunity["id"],
                summary=f"Public-source opportunity created with evidence strength {args.evidence_strength}.",
                required_next_action="Forge may create concept/design packages. Production remains blocked until stronger evidence and Ledger PASS.",
                status="ready_for_concept_design",
            )

            print(f"Opportunity ID: {opportunity['id']}")
            print(f"Opportunity Status: {opportunity['status']}")
            print(f"Handoff ID: {handoff['id']}")

    print()
    print("# Pipeline Complete")
    print()


if __name__ == "__main__":
    main()
