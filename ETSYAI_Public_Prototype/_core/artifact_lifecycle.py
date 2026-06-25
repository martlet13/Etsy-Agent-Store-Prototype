import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
EVENTS_FILE = STATE / "artifact_lifecycle_events.json"

FILE_MAP = {
    "opportunity": "opportunity_cards.json",
    "design": "design_packages.json",
    "image_request": "image_generation_requests.json",
    "image_asset": "image_assets.json",
    "publish_package": "publish_packages.json",
    "listing": "listing_drafts.json",
    "economics": "unit_economics_cards.json",
}


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any):
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def next_id(prefix: str, records: List[Dict[str, Any]]) -> str:
    highest = 0
    for item in records:
        raw = str(item.get("id", ""))
        if raw.startswith(prefix + "-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass
    return f"{prefix}-{highest + 1:04d}"


def lifecycle_action(artifact_type, artifact_id, action, reason=""):
    events = load_json(EVENTS_FILE, [])
    filename = FILE_MAP.get(artifact_type)

    if not filename:
        event = {
            "id": next_id("LIFE", events),
            "status": "blocked_unknown_artifact_type",
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "action": action,
            "reason": reason,
            "created_at": now_stamp(),
        }
        events.append(event)
        save_json(EVENTS_FILE, events)
        return event

    path = STATE / filename
    records = load_json(path, [])
    found = None

    for item in records:
        if item.get("id") == artifact_id:
            found = item
            break

    if not found:
        event = {
            "id": next_id("LIFE", events),
            "status": "blocked_missing_artifact",
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "action": action,
            "reason": reason,
            "created_at": now_stamp(),
        }
        events.append(event)
        save_json(EVENTS_FILE, events)
        return event

    previous_status = found.get("status")

    if action == "archive":
        found["status"] = "archived"
        found["archived"] = True
    elif action == "ignore_test":
        found["status"] = "ignored_test"
        found["ignored_by_cycle"] = True
    elif action == "supersede":
        found["status"] = "superseded"
    elif action == "reactivate":
        found["status"] = "active"
        found["archived"] = False
        found["ignored_by_cycle"] = False
    else:
        pass

    found.setdefault("lifecycle_notes", [])
    found["lifecycle_notes"].append({
        "action": action,
        "reason": reason,
        "created_at": now_stamp()
    })

    save_json(path, records)

    event = {
        "id": next_id("LIFE", events),
        "status": "applied",
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "action": action,
        "previous_status": previous_status,
        "new_status": found.get("status"),
        "reason": reason,
        "created_at": now_stamp(),
    }

    events.append(event)
    save_json(EVENTS_FILE, events)
    return event


def main():
    parser = argparse.ArgumentParser(description="Artifact lifecycle controls.")
    parser.add_argument("--artifact-type", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--action", choices=["archive", "ignore_test", "supersede", "reactivate"], required=True)
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    event = lifecycle_action(args.artifact_type, args.artifact_id, args.action, args.reason)

    print()
    print("# Artifact Lifecycle Event")
    print()
    print(f"ID: {event['id']}")
    print(f"Status: {event['status']}")
    print(f"Artifact: {event.get('artifact_type')} / {event.get('artifact_id')}")
    print(f"Action: {event.get('action')}")
    print(f"Previous: {event.get('previous_status')}")
    print(f"New: {event.get('new_status')}")
    print()


if __name__ == "__main__":
    main()
