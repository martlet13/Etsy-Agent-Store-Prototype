import argparse

from pipeline_contracts import create_handoff


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V6 agent handoff.")
    parser.add_argument("--from-agent", required=True)
    parser.add_argument("--to-agent", required=True)
    parser.add_argument("--artifact-type", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--required-next-action", required=True)
    parser.add_argument("--status", default="ready_for_next_agent")

    args = parser.parse_args()

    handoff = create_handoff(
        from_agent=args.from_agent,
        to_agent=args.to_agent,
        artifact_type=args.artifact_type,
        artifact_id=args.artifact_id,
        summary=args.summary,
        required_next_action=args.required_next_action,
        status=args.status,
    )

    print()
    print("# Agent Handoff Created")
    print()
    print(f"ID: {handoff['id']}")
    print(f"From: {handoff['from_agent']}")
    print(f"To: {handoff['to_agent']}")
    print(f"Artifact Type: {handoff['artifact_type']}")
    print(f"Artifact ID: {handoff['artifact_id']}")
    print(f"Status: {handoff['status']}")
    print()


if __name__ == "__main__":
    main()
