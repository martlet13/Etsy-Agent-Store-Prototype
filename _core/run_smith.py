import argparse
from datetime import datetime
from pathlib import Path

from llm_backend import call_llm

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

ARMORY = ROOT / "08_Armory"
RESEARCH = ROOT / "01_ResearchLab"
FORGE = ROOT / "02_ForgeFactory"
SCRIBE = ROOT / "03_ListingRoom"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"
TREASURY = ROOT / "06_Treasury"
WARROOM = ROOT / "07_WarRoom"
MEDIA = ROOT / "09_MediaBay"
COMMS = ROOT / "10_CommsHub"

AGENT_FILE = ARMORY / "AGENT.md"
LOG_DIR = ARMORY / "logs"
BLUEPRINTS_DIR = ARMORY / "blueprints"



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

    tool_inventory = read_file(ARMORY / "tool_inventory.md")
    skill_ideas = read_file(ARMORY / "skill_ideas.md")
    safety_rules = read_file(ARMORY / "safety_rules.md")
    automation_blueprints = read_file(ARMORY / "automation_blueprints.md")

    scribe_spec = read_file(SCRIBE / "dashboard_spec.md")
    build_requirements = read_file(SCRIBE / "build_requirements.md")
    approved_items = read_file(QA / "approved_items.md")
    revision_requests = read_file(QA / "revision_requests.md")
    qa_checklist = read_file(QA / "qa_checklist.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    cost_report = read_file(TREASURY / "cost_report.md")
    warroom_next = read_file(WARROOM / "next_mission.md")
    media_package = read_file(MEDIA / "media_package.md")
    comms_status = read_file(COMMS / "status_updates.md")

    return f'''
You are Smith, the Armory agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Armory files:

tool_inventory.md:
{tool_inventory}

skill_ideas.md:
{skill_ideas}

safety_rules.md:
{safety_rules}

automation_blueprints.md:
{automation_blueprints}

SpaceCommand context:

Scribe dashboard spec:
{scribe_spec}

Scribe build requirements:
{build_requirements}

Sentinel approved items:
{approved_items}

Sentinel revision requests:
{revision_requests}

Sentinel QA checklist:
{qa_checklist}

Archivist decisions:
{decisions}

Style preferences:
{style}

Approved patterns:
{approved_patterns}

Rejected patterns:
{rejected_patterns}

Ledger cost report:
{cost_report}

WarRoom next mission:
{warroom_next}

Signal media package:
{media_package}

Echo status updates:
{comms_status}

User request:
{request}

Task:
Create a local-only Armory tool/safety output.

Required format:

# Smith Armory Output

## Purpose
Explain what this Armory output is for.

## Current Tool Inventory
Summarize known tools and their risk level.

## Safety Rules
List the rules that apply before any tool is installed, connected, or automated.

## Automation Blueprint
Draft one safe local-only automation blueprint.

## Approval-Required Items
List anything that would need human approval.

## Recommended Next Tooling Step
Give one safe local-only next step.

## Sentinel Review Notes
List what Sentinel should review.

Rules:
- Do not browse.
- Do not install tools.
- Do not run shell commands.
- Do not access accounts.
- Do not post, upload, schedule, message, buy, sell, publish, scrape, or install integrations.
- Do not claim anything was installed, run, posted, uploaded, scheduled, or connected.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"smith_{stamp}.md"
    path.write_text(
        f"# Smith Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_blueprint(response: str, title: str = "Smith Blueprint") -> Path:
    BLUEPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "smith_blueprint"
    path = BLUEPRINTS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Smith Armory agent.")
    parser.add_argument("request", nargs="*", help="Request for Smith")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    parser.add_argument("--save-blueprint", action="store_true", help="Save response into Armory blueprints")
    parser.add_argument("--title", default="Smith Blueprint", help="Blueprint title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Smith: ").strip()

    prompt = build_prompt(request)
    response = call_llm(prompt, backend=args.backend, ollama_model=args.model, claude_model=args.claude_model)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_blueprint:
        blueprint_path = save_blueprint(response, args.title)
        append_file(ARMORY / "automation_blueprints.md", f"## Saved Blueprint - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(ARMORY / "skill_ideas.md", f"## Skill / Tool Idea Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(ARMORY / "experiment_log.md", f"## Armory Draft Experiment - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[blueprint saved] {blueprint_path}")
        print(f"[automation_blueprints updated] {ARMORY / 'automation_blueprints.md'}")


if __name__ == "__main__":
    main()
