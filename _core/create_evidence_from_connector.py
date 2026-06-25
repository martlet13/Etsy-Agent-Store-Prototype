import argparse

from pipeline_contracts import create_evidence_card
from research_connector_registry import load_connector_runs


def main():
    parser = argparse.ArgumentParser(description="Create evidence cards from completed connector runs.")

    parser.add_argument("--connector-run-id", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--evidence-strength", choices=["missing", "hypothesis", "weak", "provided", "verified"], default="provided")
    parser.add_argument("--trend-direction", default="unknown")
    parser.add_argument("--confidence", choices=["low", "medium-low", "medium", "high"], default="medium")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    runs = load_connector_runs()
    run_by_id = {x.get("id"): x for x in runs}

    if args.connector_run_id not in run_by_id:
        print()
        print("# Evidence Card Blocked")
        print()
        print(f"Missing connector run: {args.connector_run_id}")
        print()
        return

    run = run_by_id[args.connector_run_id]

    if not run.get("success"):
        print()
        print("# Evidence Card Blocked")
        print()
        print(f"Connector run did not succeed: {args.connector_run_id}")
        print(f"Status: {run.get('status')}")
        print(f"Notes: {run.get('notes')}")
        print()
        return

    card = create_evidence_card(
        source=run.get("connector_name") or run.get("connector_id"),
        source_type=run.get("source_type", "connector_result"),
        collection_method=f"connector:{run.get('connector_id')}",
        permission_level=run.get("permission_level", "unknown"),
        time_window=run.get("time_window", "unknown"),
        keyword=args.keyword,
        category=args.category,
        evidence_strength=args.evidence_strength,
        trend_direction=args.trend_direction,
        confidence=args.confidence,
        metrics=run.get("metrics", {}),
        raw_snapshot_path=None,
        notes=args.notes or run.get("raw_summary", ""),
    )

    print()
    print("# Evidence Card Created From Connector Run")
    print()
    print(f"Evidence ID: {card['id']}")
    print(f"Connector Run ID: {args.connector_run_id}")
    print(f"Source: {card['source']}")
    print(f"Keyword: {card['keyword']}")
    print(f"Category: {card['category']}")
    print(f"Evidence Strength: {card['evidence_strength']}")
    print(f"Trend Direction: {card['trend_direction']}")
    print(f"Confidence: {card['confidence']}")
    print()


if __name__ == "__main__":
    main()
