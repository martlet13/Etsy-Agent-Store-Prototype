import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
CORE = ROOT / "_core"
STATE = ROOT / "_spacecommand_state"

AGENTS_FILE = STATE / "agents.json"
TASKS_FILE = STATE / "tasks.json"
MISSIONS_FILE = STATE / "missions.json"

SENTINEL_RUNNER = CORE / "run_sentinel.py"
ARCHIVIST_RUNNER = CORE / "run_archivist.py"


DEFAULT_AGENTS = [
    {
        "name": "Command",
        "room": "00_Bridge",
        "runner": "run_command.py",
        "save_flag": "--save-plan",
        "default_title": "Task Command Plan",
        "review_type": "Bridge coordination plan",
        "role": "Bridge coordination, task queues, room status, status reports",
    },
    {
        "name": "Nova",
        "room": "01_ResearchLab",
        "runner": "run_nova.py",
        "save_flag": "--save-brief",
        "default_title": "Task Nova Brief",
        "review_type": "research brief",
        "role": "Research briefs and idea generation",
    },
    {
        "name": "Forge",
        "room": "02_ForgeFactory",
        "runner": "run_forge.py",
        "save_flag": "--save-concept",
        "default_title": "Task Forge Concept",
        "review_type": "design concept",
        "role": "Dashboard concepts, visual direction, design prompts",
    },
    {
        "name": "Scribe",
        "room": "03_ListingRoom",
        "runner": "run_scribe.py",
        "save_flag": "--save-spec",
        "default_title": "Task Scribe Spec",
        "review_type": "written specification",
        "role": "Dashboard specs, UI copy, build requirements",
    },
    {
        "name": "Sentinel",
        "room": "04_QARoom",
        "runner": "run_sentinel.py",
        "save_flag": "--save-review",
        "default_title": "Task Sentinel Review",
        "review_type": "Sentinel review",
        "role": "QA reviews, approvals, revisions, safety gates",
    },
    {
        "name": "Archivist",
        "room": "05_Archives",
        "runner": "run_archivist.py",
        "save_flag": "--save-memory",
        "default_title": "Task Archivist Memory",
        "review_type": "memory entry",
        "role": "Memory, decisions, feedback, lessons learned",
    },
    {
        "name": "Ledger",
        "room": "06_Treasury",
        "runner": "run_ledger.py",
        "save_flag": "--save-report",
        "default_title": "Task Ledger Report",
        "review_type": "cost or budget report",
        "role": "Cost tracking, budget notes, approval-required spending",
    },
    {
        "name": "Strategist",
        "room": "07_WarRoom",
        "runner": "run_strategist.py",
        "save_flag": "--save-review",
        "default_title": "Task Strategist Review",
        "review_type": "WarRoom strategy review",
        "role": "Daily reviews, weak spots, next-mission planning",
    },
    {
        "name": "Smith",
        "room": "08_Armory",
        "runner": "run_smith.py",
        "save_flag": "--save-blueprint",
        "default_title": "Task Smith Blueprint",
        "review_type": "Armory tool or automation blueprint",
        "role": "Tool inventory, safety rules, automation blueprints",
    },
    {
        "name": "Signal",
        "room": "09_MediaBay",
        "runner": "run_signal.py",
        "save_flag": "--save-package",
        "default_title": "Task Signal Package",
        "review_type": "media package",
        "role": "Media drafts, captions, thumbnails, content packages",
    },
    {
        "name": "Echo",
        "room": "10_CommsHub",
        "runner": "run_echo.py",
        "save_flag": "--save-draft",
        "default_title": "Task Echo Draft",
        "review_type": "communication draft",
        "role": "Communication drafts, templates, approval requests",
    },
    {
        "name": "Overseer",
        "room": "_overseer",
        "runner": "run_overseer.py",
        "save_flag": "--save-mission",
        "default_title": "Task Overseer Mission",
        "review_type": "Overseer mission order",
        "role": "Planning-only full-system mission orders",
    },
]


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)

    if not AGENTS_FILE.exists():
        AGENTS_FILE.write_text(json.dumps(DEFAULT_AGENTS, indent=2), encoding="utf-8")

    if not TASKS_FILE.exists():
        TASKS_FILE.write_text("[]", encoding="utf-8")

    if not MISSIONS_FILE.exists():
        MISSIONS_FILE.write_text("[]", encoding="utf-8")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + f".broken_{file_stamp()}.bak")
        backup.write_text(text, encoding="utf-8")
        path.write_text(json.dumps(fallback, indent=2), encoding="utf-8")
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def normalize_name(value: Any) -> str:
    return str(value).replace("\ufeff", "").strip().lower()


def repair_agents_file() -> None:
    existing = load_json(AGENTS_FILE, [])
    if not isinstance(existing, list):
        existing = []

    merged: Dict[str, Dict[str, Any]] = {}

    for agent in DEFAULT_AGENTS:
        merged[normalize_name(agent["name"])] = dict(agent)

    for agent in existing:
        if isinstance(agent, dict) and agent.get("name"):
            key = normalize_name(agent["name"])
            # Keep known defaults authoritative so runner/save flags stay correct.
            if key not in merged:
                merged[key] = agent

    repaired = list(merged.values())
    save_json(AGENTS_FILE, repaired)


def load_agents() -> List[Dict[str, Any]]:
    ensure_state()
    repair_agents_file()
    agents = load_json(AGENTS_FILE, DEFAULT_AGENTS)
    if not isinstance(agents, list) or not agents:
        save_json(AGENTS_FILE, DEFAULT_AGENTS)
        return DEFAULT_AGENTS
    return agents


def load_tasks() -> List[Dict[str, Any]]:
    ensure_state()
    tasks = load_json(TASKS_FILE, [])
    if not isinstance(tasks, list):
        save_json(TASKS_FILE, [])
        return []
    return tasks


def save_tasks(tasks: List[Dict[str, Any]]) -> None:
    save_json(TASKS_FILE, tasks)


def load_missions() -> List[Dict[str, Any]]:
    ensure_state()
    missions = load_json(MISSIONS_FILE, [])
    if not isinstance(missions, list):
        save_json(MISSIONS_FILE, [])
        return []
    return missions


def save_missions(missions: List[Dict[str, Any]]) -> None:
    save_json(MISSIONS_FILE, missions)


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    wanted = normalize_name(name)
    for agent in load_agents():
        if normalize_name(agent.get("name", "")) == wanted:
            return agent

    # Absolute fallback from built-in registry.
    for agent in DEFAULT_AGENTS:
        if normalize_name(agent.get("name", "")) == wanted:
            return agent

    return None


def next_id(prefix: str, existing: List[Dict[str, Any]]) -> str:
    highest = 0
    for item in existing:
        raw_id = str(item.get("id", ""))
        if raw_id.startswith(prefix + "-"):
            try:
                number = int(raw_id.split("-")[1])
                highest = max(highest, number)
            except Exception:
                pass

    return f"{prefix}-{highest + 1:04d}"


def create_mission(title: str, description: str, tasks_to_create: List[Dict[str, Any]]) -> Dict[str, Any]:
    missions = load_missions()
    tasks = load_tasks()

    mission_id = next_id("MISSION", missions)

    mission = {
        "id": mission_id,
        "title": title,
        "description": description,
        "status": "active",
        "created_at": now_stamp(),
        "completed_at": None,
        "task_ids": [],
    }

    for draft in tasks_to_create:
        agent_name = draft["assigned_agent"]
        agent = get_agent(agent_name)
        if agent is None:
            known = ", ".join(agent["name"] for agent in load_agents())
            raise ValueError(f"Unknown agent: {agent_name}. Known agents: {known}")

        task_id = next_id("TASK", tasks)
        task = {
            "id": task_id,
            "mission_id": mission_id,
            "mission_title": title,
            "title": draft["title"],
            "description": draft["description"],
            "assigned_agent": agent["name"],
            "priority": draft.get("priority", "medium"),
            "status": "pending",
            "requires_review": draft.get("requires_review", True),
            "created_at": now_stamp(),
            "started_at": None,
            "completed_at": None,
            "result_output": None,
            "result_log_hint": None,
            "sentinel_verdict": None,
            "sentinel_output": None,
            "archived": False,
            "notes": [],
        }

        tasks.append(task)
        mission["task_ids"].append(task_id)

    missions.append(mission)

    save_missions(missions)
    save_tasks(tasks)

    return mission


def get_next_pending_task() -> Optional[Dict[str, Any]]:
    tasks = load_tasks()
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    pending = [
        task for task in tasks
        if task.get("status") in ("pending", "pending_revision")
    ]

    if not pending:
        return None

    pending.sort(
        key=lambda task: (
            priority_order.get(str(task.get("priority", "medium")).lower(), 2),
            task.get("created_at", ""),
            task.get("id", ""),
        )
    )

    return pending[0]


def update_task(updated_task: Dict[str, Any]) -> None:
    tasks = load_tasks()
    for index, task in enumerate(tasks):
        if task["id"] == updated_task["id"]:
            tasks[index] = updated_task
            save_tasks(tasks)
            return

    raise ValueError(f"Task not found: {updated_task['id']}")


def run_python_runner(agent: Dict[str, Any], message: str, title: str) -> Dict[str, Any]:
    runner = CORE / agent["runner"]

    if not runner.exists():
        return {
            "success": False,
            "exit_code": 1,
            "output": f"Runner not found: {runner}",
        }

    command = [
        "python",
        str(runner),
        message,
        agent["save_flag"],
        "--title",
        title,
    ]

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\n\n[stderr]\n" + result.stderr

    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output.strip(),
    }


def parse_sentinel_verdict(output: str) -> str:
    upper = output.upper()

    if "REQUIRES_HUMAN_APPROVAL" in upper:
        return "REQUIRES_HUMAN_APPROVAL"
    if "NEEDS_REVISION" in upper:
        return "NEEDS_REVISION"
    if "REJECTED" in upper:
        return "REJECTED"
    if "APPROVED" in upper:
        return "APPROVED"

    return "UNKNOWN"


def run_sentinel_review(task: Dict[str, Any], agent: Dict[str, Any], agent_output: str) -> Dict[str, Any]:
    if not SENTINEL_RUNNER.exists():
        return {
            "success": False,
            "exit_code": 1,
            "output": f"Sentinel runner not found: {SENTINEL_RUNNER}",
            "verdict": "UNKNOWN",
        }

    review_prompt = f"""
Review {agent['name']}'s completed task output.

Task ID:
{task['id']}

Mission:
{task['mission_title']}

Task title:
{task['title']}

Task description:
{task['description']}

Assigned agent:
{agent['name']}

Agent role:
{agent['role']}

Review type:
{agent['review_type']}

Actual agent output:
{agent_output}

Review goals:
- Confirm the output is local-only and draft-only.
- Check whether it directly completes the exact task title and task description.
- If the output answers a different project, different room, dashboard, website, unrelated specification, or generic SpaceCommand overview instead of the assigned task, mark NEEDS_REVISION.
- Check whether it matches the assigned agent's role.
- Check for hallucinated rooms, agents, teams, tools, external actions, fake commands, or false claims.
- Check for safety issues.
- If safe, useful, and directly responsive to the task, mark APPROVED.
- If local-only but flawed, generic, misdirected, incomplete, or not directly responsive to the task, mark NEEDS_REVISION.
- Only mark REQUIRES_HUMAN_APPROVAL if it proposes a real external action such as account access, publishing, messaging, buying, selling, scraping, browser automation, payment access, tool installation, or sending data outside the local project.
- Local anti-drift rules, prompt rules, deterministic registry rules, task-manager retry rules, and agent behavior rules do NOT require human approval. If flawed, mark NEEDS_REVISION. If useful, mark APPROVED.
""".strip()

    result = subprocess.run(
        ["python", str(SENTINEL_RUNNER), review_prompt, "--save-review"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\n\n[stderr]\n" + result.stderr

    verdict = parse_sentinel_verdict(output)

    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output.strip(),
        "verdict": verdict,
    }


def run_archivist_memory(task: Dict[str, Any], agent: Dict[str, Any]) -> Dict[str, Any]:
    if not ARCHIVIST_RUNNER.exists():
        return {
            "success": False,
            "exit_code": 1,
            "output": f"Archivist runner not found: {ARCHIVIST_RUNNER}",
        }

    memory_prompt = f"""
Record this SpaceCommand task result.

Task ID:
{task['id']}

Mission:
{task['mission_title']}

Task:
{task['title']}

Assigned agent:
{agent['name']}

Final status:
{task['status']}

Sentinel verdict:
{task.get('sentinel_verdict')}

Important note:
This was a local-only SpaceCommand task. Store the result, verdict, and any useful lesson for future coordination.
""".strip()

    result = subprocess.run(
        [
            "python",
            str(ARCHIVIST_RUNNER),
            memory_prompt,
            "--save-memory",
            "--title",
            f"{task['id']} {task['title']}",
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\n\n[stderr]\n" + result.stderr

    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output.strip(),
    }


def run_next_task(review: bool = True, archive_on_approved: bool = True) -> Dict[str, Any]:
    task = get_next_pending_task()

    if task is None:
        return {
            "success": True,
            "message": "No pending tasks.",
            "task": None,
        }

    agent = get_agent(task["assigned_agent"])
    if agent is None:
        task["status"] = "failed"
        task["notes"].append(f"{now_stamp()} Unknown assigned agent: {task['assigned_agent']}")
        update_task(task)
        return {
            "success": False,
            "message": f"Unknown assigned agent: {task['assigned_agent']}",
            "task": task,
        }

    task["status"] = "running"
    task["started_at"] = now_stamp()
    update_task(task)

    previous_output = task.get("result_output") or ""
    previous_sentinel = task.get("sentinel_output") or ""
    previous_verdict = task.get("sentinel_verdict") or "not reviewed"

    revision_context = ""
    if task.get("status") == "pending_revision":
        revision_context = f"""
Previous attempt needs revision.

Previous Sentinel verdict:
{previous_verdict}

Previous Sentinel feedback:
{previous_sentinel}

Previous agent output:
{previous_output}

Revision instruction:
Do not repeat the previous output. Address Sentinel required fixes directly.
""".strip()

    message = f"""
Mission:
{task['mission_title']}

Task ID:
{task['id']}

Task title:
{task['title']}

Task description:
{task['description']}

Revision context:
{revision_context}

Instructions:
Complete this task as a local-only SpaceCommand output. Do not browse, access accounts, post, upload, message, buy, sell, publish, scrape, install tools, or claim external actions happened.

Special routing guard:
If this task is assigned to Scribe and the task title or description mentions launcher, Start-SpaceCommand.ps1, save flags, Sentinel review, task manager integration, confirmation rules, encoding rules, or error handling, then write ONLY a launcher specification. Do not write a dashboard specification. Do not mention login/authentication, Next.js, sidebar UI, troops, weapons, combat, listings, or financial transactions.

If this task is assigned to Scribe and the task title or description mentions anti-drift, drift, hallucination, deterministic registry, fake rooms, fake teams, exact-task matching, or prompt rules, then write ONLY anti-drift rules. Do not write a dashboard specification, launcher specification, login flow, web app plan, combat system, room UI, or media package.
""".strip()

    title = f"{task['id']} {task['title']}"
    run_result = run_python_runner(agent, message, title)

    task["result_output"] = run_result["output"]
    task["completed_at"] = now_stamp()

    if not run_result["success"]:
        task["status"] = "failed"
        task["notes"].append(f"{now_stamp()} Runner failed with exit code {run_result['exit_code']}")
        update_task(task)
        return {
            "success": False,
            "message": "Agent runner failed.",
            "task": task,
            "agent_output": run_result["output"],
        }

    if review and task.get("requires_review", True):
        sentinel = run_sentinel_review(task, agent, run_result["output"])
        task["sentinel_output"] = sentinel["output"]
        task["sentinel_verdict"] = sentinel["verdict"]

        if sentinel["verdict"] == "APPROVED":
            task["status"] = "approved"
        elif sentinel["verdict"] == "NEEDS_REVISION":
            task["status"] = "pending_revision"
        elif sentinel["verdict"] == "REQUIRES_HUMAN_APPROVAL":
            task["status"] = "human_approval_required"
        elif sentinel["verdict"] == "REJECTED":
            task["status"] = "rejected"
        else:
            task["status"] = "review_unknown"

        update_task(task)

        if archive_on_approved and task["status"] == "approved":
            archive = run_archivist_memory(task, agent)
            task["archived"] = archive["success"]
            if not archive["success"]:
                task["notes"].append(f"{now_stamp()} Archivist archive failed.")
            update_task(task)

        update_mission_completion()

        return {
            "success": True,
            "message": "Task completed and reviewed.",
            "task": task,
            "agent_output": run_result["output"],
            "sentinel_output": sentinel["output"],
        }

    task["status"] = "completed_unreviewed"
    update_task(task)

    update_mission_completion()

    return {
        "success": True,
        "message": "Task completed without review.",
        "task": task,
        "agent_output": run_result["output"],
    }



def update_mission_completion() -> None:
    missions = load_missions()
    tasks = load_tasks()

    final_statuses = {
        "approved",
        "completed_unreviewed",
        "rejected",
        "human_approval_required",
        "failed",
        "review_unknown",
    }

    changed = False

    for mission in missions:
        task_ids = mission.get("task_ids", [])
        if not task_ids:
            continue

        mission_tasks = [
            task for task in tasks
            if task.get("id") in task_ids
        ]

        if not mission_tasks:
            continue

        all_done = all(
            task.get("status") in final_statuses
            for task in mission_tasks
        )

        has_blocker = any(
            task.get("status") in {"failed", "rejected", "human_approval_required", "review_unknown"}
            for task in mission_tasks
        )

        if all_done and mission.get("status") == "active":
            mission["status"] = "blocked" if has_blocker else "completed"
            mission["completed_at"] = now_stamp()
            changed = True

    if changed:
        save_missions(missions)

def status_summary() -> str:
    update_mission_completion()
    tasks = load_tasks()
    missions = load_missions()

    counts: Dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    lines = []
    lines.append("# SpaceCommand Task Status")
    lines.append("")
    lines.append(f"Generated: {now_stamp()}")
    lines.append("")
    lines.append("## Missions")
    if not missions:
        lines.append("- No missions yet.")
    else:
        for mission in missions[-10:]:
            lines.append(f"- {mission['id']} — {mission['title']} [{mission['status']}]")

    lines.append("")
    lines.append("## Task Counts")
    if not counts:
        lines.append("- No tasks yet.")
    else:
        for status, count in sorted(counts.items()):
            lines.append(f"- {status}: {count}")

    lines.append("")
    lines.append("## Next Pending Task")
    next_task = get_next_pending_task()
    if next_task is None:
        lines.append("- No pending task.")
    else:
        lines.append(f"- {next_task['id']} — {next_task['title']}")
        lines.append(f"  - Agent: {next_task['assigned_agent']}")
        lines.append(f"  - Priority: {next_task['priority']}")
        lines.append(f"  - Status: {next_task['status']}")

    lines.append("")
    lines.append("## Recent Tasks")
    if not tasks:
        lines.append("- No tasks yet.")
    else:
        for task in tasks[-10:]:
            verdict = task.get("sentinel_verdict") or "not reviewed"
            lines.append(f"- {task['id']} — {task['title']} [{task['status']}] / Sentinel: {verdict}")

    return "\n".join(lines)





