import argparse
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

OVERSEER = ROOT / "_overseer"
LOG_DIR = OVERSEER / "logs"
MISSIONS_DIR = OVERSEER / "missions"

DEFAULT_MODEL = "qwen2.5-coder:7b"

BUILT_ROOMS = [
    ("00_Bridge", "Command", "Bridge coordination, task queues, room status, status reports"),
    ("01_ResearchLab", "Nova", "Research briefs and idea generation"),
    ("02_ForgeFactory", "Forge", "Dashboard concepts, visual direction, design prompts"),
    ("03_ListingRoom", "Scribe", "Dashboard specs, UI copy, build requirements"),
    ("04_QARoom", "Sentinel", "QA reviews, approvals, revisions, safety gates"),
    ("05_Archives", "Archivist", "Memory, decisions, feedback, lessons learned"),
    ("06_Treasury", "Ledger", "Cost tracking, budget notes, approval-required spending"),
    ("07_WarRoom", "Strategist", "Daily reviews, weak spots, next-mission planning"),
    ("08_Armory", "Smith", "Tool inventory, safety rules, automation blueprints"),
    ("09_MediaBay", "Signal", "Media drafts, captions, thumbnails, content packages"),
    ("10_CommsHub", "Echo", "Communication drafts, templates, approval requests"),
    ("_overseer", "Overseer v1", "Planning-only full-system mission orders"),
]

KNOWN_DRIFT = [
    "Strategist previously invented Alpha/Beta/Gamma-style agents.",
    "Command previously invented Alpha/Beta and later said built agents were unassigned.",
    "Smith previously used Linux/bash instructions before being corrected to Windows PowerShell.",
    "Overseer previously said Signal still needed building even though Signal is already built.",
    "Overseer previously skipped built rooms and misdescribed agent roles.",
    "Sentinel sometimes over-approves flawed local plans or overuses REQUIRES_HUMAN_APPROVAL for drafts.",
]


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def call_ollama(model: str, prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Ollama call failed.")

    return result.stdout.strip()


def built_room_markdown() -> str:
    lines = []
    for room, agent, purpose in BUILT_ROOMS:
        lines.append(f"- **{agent}** `{room}` — {purpose}")
    return "\n".join(lines)


def drift_markdown() -> str:
    return "\n".join(f"- {item}" for item in KNOWN_DRIFT)


def collect_short_context() -> str:
    # Keep this intentionally short. Long messy context was causing Overseer drift.
    files = [
        ("Sentinel approved items", ROOT / "04_QARoom" / "approved_items.md"),
        ("Sentinel revision requests", ROOT / "04_QARoom" / "revision_requests.md"),
        ("Overseer mission order", OVERSEER / "mission_order.md"),
        ("Smith safety rules", ROOT / "08_Armory" / "safety_rules.md"),
        ("Bridge task queue", ROOT / "00_Bridge" / "task_queue.md"),
    ]

    chunks = []
    for label, path in files:
        text = read_file(path)
        if len(text) > 2500:
            text = text[-2500:]
        chunks.append(f"## {label}\n{text}")

    return "\n\n".join(chunks)


def build_prompt(user_request: str) -> str:
    return f'''
You are Overseer v1 for Instance SpaceCommand.

CRITICAL RULES:
- You are planning-only.
- Do not run agents.
- Do not claim agents ran.
- Do not invent rooms, agents, teams, tools, revenue, posts, uploads, sales, or completed work.
- Signal is already built.
- Echo is already built.
- Smith is already built.
- Command is already built.
- Overseer v1 is already built.
- Do not say any built agent is merely "initialized" or "awaiting assignment."
- Do not output fake commands.
- Do not recommend building Signal again.
- Do not recommend external actions.
- Keep everything local-only and draft-only.

BUILT ROOM REGISTRY:
{built_room_markdown()}

KNOWN DRIFT ISSUES:
{drift_markdown()}

SHORT CONTEXT:
{collect_short_context()}

USER REQUEST:
{user_request}

Write ONLY these sections:

## Current Strengths
Give 3-5 bullets.

## Current Weaknesses
Give 3-5 bullets. Include drift issues if relevant.

## Risk Register
Give 3 risks with LOW/MEDIUM/HIGH.

## One Next Safe Local Task
Recommend exactly one next task. The best next task should usually be:
"Create or improve the Start-SpaceCommand.ps1 launcher and then review it with Sentinel."

Do not list built rooms; the runner will insert the built room list deterministically.
Do not output JSON.
Output markdown only.
'''


def deterministic_header(user_request: str) -> str:
    return f'''# SpaceCommand Overseer Mission Order

## Mission Objective
Create a reliable local SpaceCommand control loop: launcher menu, Sentinel review, then improved room coordination.

## User Request
{user_request}

## Confirmed Built Agents
{built_room_markdown()}

## Known Drift Issues
{drift_markdown()}
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"overseer_{stamp}.md"
    path.write_text(
        f"# Overseer Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def append_file(path: Path, content: str) -> None:
    existing = read_file(path)
    new_content = existing.rstrip() + "\n\n" + content.strip() + "\n"
    path.write_text(new_content, encoding="utf-8")


def save_mission(response: str, title: str) -> Path:
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "overseer_mission"
    path = MISSIONS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Overseer planning agent.")
    parser.add_argument("request", nargs="*", help="Request for Overseer")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save-mission", action="store_true")
    parser.add_argument("--title", default="Overseer Mission")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Overseer: ").strip()

    prompt = build_prompt(request)
    model_response = call_ollama(args.model, prompt)

    final_response = deterministic_header(request).rstrip() + "\n\n" + model_response.strip()

    log_path = save_log(request, final_response)

    print()
    print(final_response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_mission:
        mission_path = save_mission(final_response, args.title)
        append_file(OVERSEER / "mission_order.md", f"## Mission Order - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{final_response}")
        append_file(OVERSEER / "system_status.md", f"## System Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{final_response}")
        append_file(OVERSEER / "next_actions.md", f"## Next Actions - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{final_response}")
        append_file(OVERSEER / "risk_register.md", f"## Risk Register - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{final_response}")
        print(f"[mission saved] {mission_path}")
        print(f"[mission_order updated] {OVERSEER / 'mission_order.md'}")


if __name__ == "__main__":
    main()
