import argparse
from datetime import datetime
from pathlib import Path

from llm_backend import call_llm

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

BRIDGE = ROOT / "00_Bridge"
RESEARCH = ROOT / "01_ResearchLab"
FORGE = ROOT / "02_ForgeFactory"
SCRIBE = ROOT / "03_ListingRoom"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"
TREASURY = ROOT / "06_Treasury"
WARROOM = ROOT / "07_WarRoom"
ARMORY = ROOT / "08_Armory"
MEDIA = ROOT / "09_MediaBay"
COMMS = ROOT / "10_CommsHub"

AGENT_FILE = BRIDGE / "AGENT.md"
LOG_DIR = BRIDGE / "logs"
PLANS_DIR = BRIDGE / "plans"



def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def append_file(path: Path, content: str) -> None:
    existing = read_file(path)
    new_content = existing.rstrip() + "\n\n" + content.strip() + "\n"
    path.write_text(new_content, encoding="utf-8")




def build_prompt(request: str) -> str:
    agent_rules = read_file(AGENT_FILE)

    nova = read_file(RESEARCH / "product_briefs.md")
    forge = read_file(FORGE / "dashboard_concepts.md")
    scribe = read_file(SCRIBE / "dashboard_spec.md")
    qa_approved = read_file(QA / "approved_items.md")
    qa_revisions = read_file(QA / "revision_requests.md")
    qa_required = read_file(QA / "approval_required.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    lessons = read_file(ARCHIVES / "lessons_learned.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    ledger = read_file(TREASURY / "cost_report.md")
    strategist = read_file(WARROOM / "daily_review.md")
    next_mission = read_file(WARROOM / "next_mission.md")
    smith = read_file(ARMORY / "automation_blueprints.md")
    signal = read_file(MEDIA / "media_package.md")
    echo = read_file(COMMS / "status_updates.md")

    return f'''
You are Command, the Bridge coordination agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Current room evidence:

Nova / ResearchLab:
{nova}

Forge / ForgeFactory:
{forge}

Scribe / ListingRoom:
{scribe}

Sentinel approved items:
{qa_approved}

Sentinel revision requests:
{qa_revisions}

Sentinel approval-required items:
{qa_required}

Archivist decisions:
{decisions}

Archivist style preferences:
{style}

Archivist lessons learned:
{lessons}

Approved patterns:
{approved_patterns}

Rejected patterns:
{rejected_patterns}

Ledger / Treasury:
{ledger}

Strategist / WarRoom daily review:
{strategist}

WarRoom next mission:
{next_mission}

Smith / Armory:
{smith}

Signal / MediaBay:
{signal}

Echo / CommsHub:
{echo}

User request:
{request}

Task:
Create a local-only Bridge coordination output.

Required format:

# SpaceCommand Bridge Coordination Plan

## Mission Objective
State the current local mission.

## Confirmed Built Rooms
List only rooms confirmed as built.

## Current Room Status
For each built room:
- Room:
- Agent:
- Confirmed output:
- Current status:
- Next useful task:

## Task Queue
Create a prioritized local-only task queue.

## Approval Queue
List anything that requires human approval before external use.

## Risks / Drift
List hallucinations, weak outputs, or drift that should be corrected.

## Next Mission
Give one focused next mission.

## Sentinel Review Notes
List what Sentinel should review.

Rules:
- Do not browse.
- Do not access accounts.
- Do not run agents.
- Do not claim other agents ran during this response.
- Do not invent completed work.
- Do not invent agents.
- Do not post, upload, schedule, message, buy, sell, publish, scrape, or install tools.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"command_{stamp}.md"
    path.write_text(
        f"# Command Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_plan(response: str, title: str = "Bridge Plan") -> Path:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "bridge_plan"
    path = PLANS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Bridge Command agent.")
    parser.add_argument("request", nargs="*", help="Request for Command")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    parser.add_argument("--save-plan", action="store_true", help="Save response into Bridge plans")
    parser.add_argument("--title", default="Bridge Plan", help="Plan title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Command: ").strip()

    prompt = build_prompt(request)
    response = call_llm(prompt, backend=args.backend, ollama_model=args.model, claude_model=args.claude_model)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_plan:
        plan_path = save_plan(response, args.title)
        append_file(BRIDGE / "daily_plan.md", f"## Daily Plan - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(BRIDGE / "task_queue.md", f"## Task Queue - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(BRIDGE / "room_status.md", f"## Room Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(BRIDGE / "status_report.md", f"## Status Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[plan saved] {plan_path}")
        print(f"[daily_plan updated] {BRIDGE / 'daily_plan.md'}")


if __name__ == "__main__":
    main()
