import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
CORE = ROOT / "_core"
STATE = ROOT / "_spacecommand_state"
CONTRACTS_FILE = STATE / "ui_action_contracts.json"
RUNS_FILE = STATE / "ui_action_runs.json"


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


def get_action(action_id):
    contracts = load_json(CONTRACTS_FILE, {"actions": []})
    for action in contracts.get("actions", []):
        if action.get("id") == action_id:
            return action
    return None


def run_action(action_id, confirmed=False, extra_args=""):
    runs = load_json(RUNS_FILE, [])
    action = get_action(action_id)

    if not action:
        run = {
            "id": next_id("UIRUN", runs),
            "action_id": action_id,
            "status": "blocked_unknown_action",
            "created_at": now_stamp(),
        }
        runs.append(run)
        save_json(RUNS_FILE, runs)
        return run

    if action.get("requires_confirmation") and not confirmed:
        run = {
            "id": next_id("UIRUN", runs),
            "action_id": action_id,
            "status": "blocked_confirmation_required",
            "can_cost_money": action.get("can_cost_money"),
            "can_upload": action.get("can_upload"),
            "can_publish": action.get("can_publish"),
            "created_at": now_stamp(),
        }
        runs.append(run)
        save_json(RUNS_FILE, runs)
        return run

    command = action.get("command", "")
    parts = command.split()
    script = parts[0]
    base_args = parts[1:]

    cmd = [sys.executable, str(CORE / script)] + base_args
    if extra_args:
        cmd += extra_args.split()

    try:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        status = "completed" if result.returncode == 0 else "failed"
        stdout = result.stdout[-6000:]
        stderr = result.stderr[-4000:]
    except Exception as exc:
        status = "failed_exception"
        stdout = ""
        stderr = repr(exc)

    run = {
        "id": next_id("UIRUN", runs),
        "action_id": action_id,
        "status": status,
        "command": " ".join(cmd),
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "created_at": now_stamp(),
    }

    runs.append(run)
    save_json(RUNS_FILE, runs)
    return run


def main():
    parser = argparse.ArgumentParser(description="UI action router.")
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--confirmed", choices=["true", "false"], default="false")
    parser.add_argument("--extra-args", default="")
    args = parser.parse_args()

    run = run_action(
        action_id=args.action_id,
        confirmed=args.confirmed == "true",
        extra_args=args.extra_args,
    )

    print()
    print("# UI Action Run")
    print()
    print(f"ID: {run['id']}")
    print(f"Action: {run.get('action_id')}")
    print(f"Status: {run.get('status')}")
    if run.get("stdout_tail"):
        print()
        print("## Output")
        print(run.get("stdout_tail"))
    if run.get("stderr_tail"):
        print()
        print("## Error")
        print(run.get("stderr_tail"))
    print()


if __name__ == "__main__":
    main()
