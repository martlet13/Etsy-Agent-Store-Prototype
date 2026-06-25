import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
BACKUPS = STATE / "backups"
REPORTS_FILE = STATE / "backup_reports.json"


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_stamp():
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


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


def backup_state():
    BACKUPS.mkdir(parents=True, exist_ok=True)
    reports = load_json(REPORTS_FILE, [])
    backup_path = BACKUPS / f"spacecommand_state_{file_stamp()}.zip"

    count = 0
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in STATE.rglob("*"):
            if path.is_file() and BACKUPS not in path.parents:
                zf.write(path, path.relative_to(STATE))
                count += 1

    report = {
        "id": next_id("BACKUP", reports),
        "type": "backup_report",
        "status": "created",
        "path": str(backup_path),
        "files": count,
        "created_at": now_stamp(),
    }

    reports.append(report)
    save_json(REPORTS_FILE, reports)
    return report


def main():
    report = backup_state()
    print()
    print("# SpaceCommand State Backup")
    print()
    print(f"ID: {report['id']}")
    print(f"Status: {report['status']}")
    print(f"Files: {report['files']}")
    print(f"Path: {report['path']}")
    print()


if __name__ == "__main__":
    main()
