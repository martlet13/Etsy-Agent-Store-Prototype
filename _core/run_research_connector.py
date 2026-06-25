import argparse
import json

from research_connector_registry import create_connector_run


def parse_metrics(raw):
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_metrics": raw}


def main():
    parser = argparse.ArgumentParser(description="Run/register a SpaceCommand V6.5 research connector result.")

    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--time-window", choices=["daily", "weekly", "monthly", "unknown"], default="unknown")
    parser.add_argument("--raw-summary", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-title", default="")
    parser.add_argument("--metrics", default="")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    run = create_connector_run(
        connector_id=args.connector_id,
        query=args.query,
        theme=args.theme,
        time_window=args.time_window,
        raw_summary=args.raw_summary,
        source_url=args.source_url,
        source_title=args.source_title,
        metrics=parse_metrics(args.metrics),
        notes=args.notes,
    )

    print()
    print("# Connector Run Recorded")
    print()
    print(f"ID: {run['id']}")
    print(f"Connector: {run.get('connector_id')}")
    print(f"Connector Name: {run.get('connector_name', 'unknown')}")
    print(f"Status: {run.get('status')}")
    print(f"Success: {run.get('success')}")
    print(f"Permission Level: {run.get('permission_level', 'unknown')}")

    if not run.get("success"):
        print(f"Notes: {run.get('notes')}")

    print()


if __name__ == "__main__":
    main()
