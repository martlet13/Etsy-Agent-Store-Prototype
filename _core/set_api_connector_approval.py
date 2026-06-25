import argparse

from api_connector_manager import set_connector_approval


def parse_bool(raw):
    if raw is None:
        return None

    lowered = str(raw).strip().lower()

    if lowered in {"true", "yes", "1", "on"}:
        return True

    if lowered in {"false", "no", "0", "off"}:
        return False

    return None


def main():
    parser = argparse.ArgumentParser(description="Set SpaceCommand API connector approval switches.")
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--user-approved", choices=["true", "false"], default=None)
    parser.add_argument("--live-actions-enabled", choices=["true", "false"], default=None)

    args = parser.parse_args()

    result = set_connector_approval(
        connector_id=args.connector_id,
        user_approved=parse_bool(args.user_approved),
        live_actions_enabled=parse_bool(args.live_actions_enabled),
    )

    print()
    print("# API Connector Approval Update")
    print()
    print(f"OK: {result.get('ok')}")
    print(f"Message: {result.get('message')}")

    connector = result.get("connector")
    evaluation = result.get("evaluation")

    if connector:
        print(f"Connector: {connector.get('id')} / {connector.get('name')}")
        print(f"User Approved: {connector.get('user_approved')}")
        print(f"Live Actions Enabled: {connector.get('live_actions_enabled')}")

    if evaluation:
        print(f"Computed Status: {evaluation.get('computed_status')}")
        print(f"Secret State: {evaluation.get('secret_state')}")

    print()


if __name__ == "__main__":
    main()
