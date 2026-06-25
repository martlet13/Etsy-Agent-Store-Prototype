import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

API_CONNECTOR_REGISTRY_FILE = STATE / "api_connector_registry.json"
API_CONNECTOR_STATUS_CHECKS_FILE = STATE / "api_connector_status_checks.json"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()

    if not text:
        return fallback

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, data: Any) -> None:
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


def get_registry() -> Dict[str, Any]:
    return load_json(API_CONNECTOR_REGISTRY_FILE, {"version": "unknown", "connectors": []})


def save_registry(registry: Dict[str, Any]) -> None:
    save_json(API_CONNECTOR_REGISTRY_FILE, registry)


def get_connector(connector_id: str) -> Dict[str, Any] | None:
    registry = get_registry()

    for connector in registry.get("connectors", []):
        if connector.get("id") == connector_id:
            return connector

    return None


def secret_exists(env_var: str) -> bool:
    value = os.environ.get(env_var, "")
    return bool(value and value.strip())


def masked_secret_state(env_var: str) -> str:
    value = os.environ.get(env_var, "")

    if not value:
        return "missing"

    if len(value) < 8:
        return "present_short"

    return f"present:{value[:3]}...{value[-4:]}"


def evaluate_connector(connector: Dict[str, Any]) -> Dict[str, Any]:
    env_var = connector.get("env_var", "")
    has_secret = secret_exists(env_var)

    user_approved = bool(connector.get("user_approved", False))
    live_actions_enabled = bool(connector.get("live_actions_enabled", False))

    if not has_secret:
        computed_status = "missing_api_key"
    elif not user_approved:
        computed_status = "key_present_waiting_for_user_approval"
    elif not live_actions_enabled:
        computed_status = "approved_but_live_actions_disabled"
    else:
        computed_status = "live_enabled"

    return {
        "connector_id": connector.get("id"),
        "name": connector.get("name"),
        "env_var": env_var,
        "secret_state": masked_secret_state(env_var),
        "has_secret": has_secret,
        "user_approved": user_approved,
        "live_actions_enabled": live_actions_enabled,
        "computed_status": computed_status,
        "notes": connector.get("notes", ""),
    }


def check_all_connectors() -> Dict[str, Any]:
    registry = get_registry()
    checks = load_json(API_CONNECTOR_STATUS_CHECKS_FILE, [])

    results = []

    for connector in registry.get("connectors", []):
        results.append(evaluate_connector(connector))

    check = {
        "id": next_id("APICHECK", checks),
        "type": "api_connector_status_check",
        "created_at": now_stamp(),
        "results": results,
        "summary": {
            "connectors": len(results),
            "missing_api_key": len([x for x in results if x["computed_status"] == "missing_api_key"]),
            "waiting_for_user_approval": len([x for x in results if x["computed_status"] == "key_present_waiting_for_user_approval"]),
            "approved_but_live_disabled": len([x for x in results if x["computed_status"] == "approved_but_live_actions_disabled"]),
            "live_enabled": len([x for x in results if x["computed_status"] == "live_enabled"]),
        },
    }

    checks.append(check)
    save_json(API_CONNECTOR_STATUS_CHECKS_FILE, checks)

    return check


def set_connector_approval(
    connector_id: str,
    user_approved: bool | None = None,
    live_actions_enabled: bool | None = None,
) -> Dict[str, Any]:
    registry = get_registry()
    found = None

    for connector in registry.get("connectors", []):
        if connector.get("id") == connector_id:
            found = connector
            break

    if not found:
        return {
            "ok": False,
            "message": f"Unknown connector: {connector_id}",
            "connector": None,
        }

    if user_approved is not None:
        found["user_approved"] = user_approved

    if live_actions_enabled is not None:
        found["live_actions_enabled"] = live_actions_enabled

    if found.get("live_actions_enabled") and not found.get("user_approved"):
        found["live_actions_enabled"] = False

    save_registry(registry)

    return {
        "ok": True,
        "message": "Connector updated.",
        "connector": found,
        "evaluation": evaluate_connector(found),
    }


def format_connector_check(check: Dict[str, Any]) -> str:
    lines = []
    lines.append("# API Connector Status")
    lines.append("")
    lines.append(f"Check ID: {check.get('id')}")
    lines.append(f"Created: {check.get('created_at')}")
    lines.append("")
    lines.append("## Summary")

    for key, value in check.get("summary", {}).items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Connectors")

    for result in check.get("results", []):
        lines.append("")
        lines.append(f"### {result.get('name')} ({result.get('connector_id')})")
        lines.append(f"- Status: {result.get('computed_status')}")
        lines.append(f"- Env Var: {result.get('env_var')}")
        lines.append(f"- Secret: {result.get('secret_state')}")
        lines.append(f"- User Approved: {result.get('user_approved')}")
        lines.append(f"- Live Actions Enabled: {result.get('live_actions_enabled')}")
        lines.append(f"- Notes: {result.get('notes')}")

    return "\n".join(lines)
