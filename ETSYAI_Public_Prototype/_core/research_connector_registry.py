import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

CONNECTORS_FILE = STATE / "research_connectors.json"
CONNECTOR_RUNS_FILE = STATE / "connector_runs.json"


PUBLIC_SAFE_PERMISSION_LEVELS = {
    "public_read_only",
    "local_only",
}


BLOCKED_PERMISSION_LEVELS = {
    "approved_browser_login",
    "approved_api",
}


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


def ensure_connector_files() -> None:
    STATE.mkdir(parents=True, exist_ok=True)

    if not CONNECTORS_FILE.exists():
        save_json(CONNECTORS_FILE, {"version": "V6.5", "connectors": []})

    if not CONNECTOR_RUNS_FILE.exists():
        save_json(CONNECTOR_RUNS_FILE, [])


def load_registry() -> Dict[str, Any]:
    ensure_connector_files()
    return load_json(CONNECTORS_FILE, {"version": "V6.5", "connectors": []})


def load_connector_runs() -> List[Dict[str, Any]]:
    ensure_connector_files()
    return load_json(CONNECTOR_RUNS_FILE, [])


def save_connector_runs(runs: List[Dict[str, Any]]) -> None:
    save_json(CONNECTOR_RUNS_FILE, runs)


def next_run_id(runs: List[Dict[str, Any]]) -> str:
    highest = 0
    for run in runs:
        raw = str(run.get("id", ""))
        if raw.startswith("CONNRUN-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass
    return f"CONNRUN-{highest + 1:04d}"


def get_connector(connector_id: str) -> Optional[Dict[str, Any]]:
    registry = load_registry()
    for connector in registry.get("connectors", []):
        if connector.get("id") == connector_id:
            return connector
    return None


def list_connectors() -> List[Dict[str, Any]]:
    return load_registry().get("connectors", [])


def connector_is_available(connector: Dict[str, Any]) -> bool:
    if not connector:
        return False

    permission_level = connector.get("permission_level")
    status = connector.get("status")

    if permission_level in BLOCKED_PERMISSION_LEVELS:
        return False

    if status not in {"available_local_safe", "available"}:
        return False

    return permission_level in PUBLIC_SAFE_PERMISSION_LEVELS


def create_connector_run(
    connector_id: str,
    query: str,
    theme: str,
    time_window: str,
    raw_summary: str,
    source_url: str = "",
    source_title: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    ensure_connector_files()

    connector = get_connector(connector_id)
    runs = load_connector_runs()

    if connector is None:
        run = {
            "id": next_run_id(runs),
            "type": "connector_run",
            "connector_id": connector_id,
            "status": "blocked_unknown_connector",
            "success": False,
            "query": query,
            "theme": theme,
            "time_window": time_window,
            "raw_summary": raw_summary,
            "source_url": source_url,
            "source_title": source_title,
            "metrics": metrics or {},
            "notes": "Unknown connector.",
            "created_at": now_stamp(),
        }
        runs.append(run)
        save_connector_runs(runs)
        return run

    available = connector_is_available(connector)

    if not available:
        run = {
            "id": next_run_id(runs),
            "type": "connector_run",
            "connector_id": connector_id,
            "connector_name": connector.get("name"),
            "status": "blocked_permission_required",
            "success": False,
            "permission_level": connector.get("permission_level"),
            "query": query,
            "theme": theme,
            "time_window": time_window,
            "raw_summary": raw_summary,
            "source_url": source_url,
            "source_title": source_title,
            "metrics": metrics or {},
            "notes": "Connector requires explicit approval or is not available for local-safe use.",
            "blocked_actions": connector.get("blocked_actions", []),
            "created_at": now_stamp(),
        }
        runs.append(run)
        save_connector_runs(runs)
        return run

    run = {
        "id": next_run_id(runs),
        "type": "connector_run",
        "connector_id": connector_id,
        "connector_name": connector.get("name"),
        "source_type": connector.get("source_type"),
        "status": "completed_local_safe",
        "success": True,
        "permission_level": connector.get("permission_level"),
        "query": query,
        "theme": theme,
        "time_window": time_window,
        "raw_summary": raw_summary,
        "source_url": source_url,
        "source_title": source_title,
        "metrics": metrics or {},
        "notes": notes,
        "created_at": now_stamp(),
    }

    runs.append(run)
    save_connector_runs(runs)
    return run


def format_connectors(connectors: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# SpaceCommand V6.5 Research Connectors")
    lines.append("")

    if not connectors:
        lines.append("No connectors registered.")
        return "\n".join(lines)

    for connector in connectors:
        available = connector_is_available(connector)
        lines.append(f"## {connector.get('id')}")
        lines.append(f"- Name: {connector.get('name')}")
        lines.append(f"- Owner: {connector.get('agent_owner')}")
        lines.append(f"- Source Type: {connector.get('source_type')}")
        lines.append(f"- Permission Level: {connector.get('permission_level')}")
        lines.append(f"- Status: {connector.get('status')}")
        lines.append(f"- Local Safe Available: {available}")
        lines.append(f"- Notes: {connector.get('notes')}")
        lines.append("")

    return "\n".join(lines)
