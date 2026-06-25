import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "_spacecommand_state"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(file_name: str, fallback: Any) -> Any:
    path = STATE / file_name
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(file_name: str, data: Any) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / file_name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def as_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("items", "records", "connectors", "products", "runs"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def latest(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return records[-1] if records else None


def text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value if value.strip() else default
    return str(value)


def money(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def money_text(value: Any) -> str:
    number = money(value)
    return f"${number:.2f}" if number is not None else "missing"


def first_present(item: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def count_status(records: List[Dict[str, Any]], *needles: str) -> int:
    lowered = [needle.lower() for needle in needles]
    count = 0
    for record in records:
        status = text(first_present(record, ["status", "ledger_decision", "decision"], "")).lower()
        if any(needle in status for needle in lowered):
            count += 1
    return count


def simple_view(
    title: str,
    status: str,
    summary: str,
    current_job: str,
    metrics: Dict[str, Any],
    plain_updates: List[str],
    needs_user_action: List[str],
) -> Dict[str, Any]:
    return {
        "title": title,
        "status": status,
        "summary": summary,
        "current_job": current_job,
        "metrics": metrics,
        "plain_updates": plain_updates,
        "needs_user_action": needs_user_action,
    }


def blocked_reasons(item: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    for key in ("issues", "warnings", "blocked_reasons", "failed_checks", "warning_flags"):
        value = item.get(key)
        if isinstance(value, list):
            reasons.extend(text(entry) for entry in value)
    gate_reason = item.get("gate_reason")
    if gate_reason:
        reasons.append(text(gate_reason))
    return reasons


def is_connected(connector: Dict[str, Any]) -> bool:
    status = text(connector.get("status"), "").lower()
    allowed = connector.get("allowed_actions")
    return any(word in status for word in ("connected", "available", "approved", "enabled")) and bool(allowed)
