import argparse
import json

from pipeline_contracts import create_evidence_card


def parse_metrics(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_metrics": raw}


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V6 evidence card.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-type", default="unknown")
    parser.add_argument("--collection-method", default="manual_or_local")
    parser.add_argument("--permission-level", default="local_only")
    parser.add_argument("--time-window", choices=["daily", "weekly", "monthly", "unknown"], default="unknown")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--evidence-strength", choices=["missing", "hypothesis", "weak", "provided", "verified"], default="missing")
    parser.add_argument("--trend-direction", default="unknown")
    parser.add_argument("--confidence", choices=["low", "medium-low", "medium", "high"], default="low")
    parser.add_argument("--metrics", default="")
    parser.add_argument("--raw-snapshot-path", default="")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    card = create_evidence_card(
        source=args.source,
        source_type=args.source_type,
        collection_method=args.collection_method,
        permission_level=args.permission_level,
        time_window=args.time_window,
        keyword=args.keyword,
        category=args.category,
        evidence_strength=args.evidence_strength,
        trend_direction=args.trend_direction,
        confidence=args.confidence,
        metrics=parse_metrics(args.metrics),
        raw_snapshot_path=args.raw_snapshot_path or None,
        notes=args.notes,
    )

    print()
    print("# Evidence Card Created")
    print()
    print(f"ID: {card['id']}")
    print(f"Source: {card['source']}")
    print(f"Keyword: {card['keyword']}")
    print(f"Category: {card['category']}")
    print(f"Evidence Strength: {card['evidence_strength']}")
    print(f"Confidence: {card['confidence']}")
    print()


if __name__ == "__main__":
    main()
