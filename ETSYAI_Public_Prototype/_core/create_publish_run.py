import argparse

from publishing_dock import create_publish_run


def main():
    parser = argparse.ArgumentParser(description="Record or attempt a Publishing Dock run.")
    parser.add_argument("--publish-package-id", required=True)
    parser.add_argument("--connector-id", default="manual_browser_upload")
    parser.add_argument("--action", required=True)
    parser.add_argument("--user-approved-live-action", choices=["true", "false"], default="false")
    parser.add_argument("--result-notes", default="")

    args = parser.parse_args()

    run = create_publish_run(
        publish_package_id=args.publish_package_id,
        connector_id=args.connector_id,
        action=args.action,
        user_approved_live_action=args.user_approved_live_action == "true",
        result_notes=args.result_notes,
    )

    print()
    print("# Publish Run Created")
    print()
    print(f"ID: {run['id']}")
    print(f"Status: {run['status']}")
    print(f"Package: {run.get('publish_package_id')}")
    print(f"Connector: {run.get('connector_id')}")
    print(f"Action: {run.get('action')}")
    print(f"User Approved Live Action: {run.get('user_approved_live_action')}")
    print(f"Issues: {', '.join(run.get('issues', [])) or 'none'}")
    print()


if __name__ == "__main__":
    main()
