import argparse
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

SCRIBE = ROOT / "03_ListingRoom"
RESEARCH = ROOT / "01_ResearchLab"
FORGE = ROOT / "02_ForgeFactory"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"

AGENT_FILE = SCRIBE / "AGENT.md"
LOG_DIR = SCRIBE / "logs"
SPECS_DIR = SCRIBE / "specs"

DEFAULT_MODEL = "qwen2.5-coder:7b"


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def append_file(path: Path, content: str) -> None:
    existing = read_file(path)
    new_content = existing.rstrip() + "\n\n" + content.strip() + "\n"
    path.write_text(new_content, encoding="utf-8")


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


def build_prompt(request: str) -> str:
    agent_rules = read_file(AGENT_FILE)

    nova_briefs = read_file(RESEARCH / "product_briefs.md")
    forge_concepts = read_file(FORGE / "dashboard_concepts.md")
    room_layouts = read_file(FORGE / "room_layouts.md")
    component_ideas = read_file(FORGE / "component_ideas.md")
    approved_items = read_file(QA / "approved_items.md")
    qa_checklist = read_file(QA / "qa_checklist.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    return f'''
You are Scribe, the specification and copywriting agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Nova briefs:
{nova_briefs}

Forge concepts:
{forge_concepts}

Forge room layouts:
{room_layouts}

Forge component ideas:
{component_ideas}

Sentinel approved items:
{approved_items}

Sentinel QA checklist:
{qa_checklist}

SpaceCommand memory:
decisions.md:
{decisions}

style_preferences.md:
{style}

approved_patterns.md:
{approved_patterns}

rejected_patterns.md:
{rejected_patterns}

User request:
{request}

Task:
Create a clean local-only SpaceCommand written specification.

Required format:

# SpaceCommand Dashboard Specification

## Overview
Explain what the dashboard is.

## Core User Flow
Explain how the user moves through the dashboard.

## Rooms
For each room, provide:
- Purpose:
- Main screen:
- Inputs:
- Outputs:
- Status indicators:

Rooms:
- Bridge
- ResearchLab
- ForgeFactory
- ListingRoom
- QARoom
- Archives
- Treasury
- WarRoom
- Armory
- MediaBay
- CommsHub

## UI Components
List the concrete dashboard components needed.

## Local Data Files
List the markdown/data files the dashboard should read or write.

## Safety Boundaries
Explain what the system must not do without human approval.

## Build Requirements
List practical requirements for a future Next.js or local app build.

## Sentinel Review Notes
List what Sentinel should review.

Rules:
- Do not browse.
- Do not access accounts.
- Do not post, upload, message, buy, sell, publish, scrape, or install tools.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"scribe_{stamp}.md"
    path.write_text(
        f"# Scribe Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_spec(response: str, title: str = "Scribe Spec") -> Path:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "scribe_spec"
    path = SPECS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Scribe spec agent.")
    parser.add_argument("request", nargs="*", help="Request for Scribe")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save-spec", action="store_true", help="Save response into Scribe specs")
    parser.add_argument("--title", default="Scribe Spec", help="Spec title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Scribe: ").strip()

    prompt = build_prompt(request)
    response = call_ollama(args.model, prompt)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_spec:
        spec_path = save_spec(response, args.title)
        append_file(SCRIBE / "dashboard_spec.md", f"## Saved Spec - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(SCRIBE / "build_requirements.md", f"## Build Requirements Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[spec saved] {spec_path}")
        print(f"[dashboard_spec updated] {SCRIBE / 'dashboard_spec.md'}")
        print(f"[build_requirements updated] {SCRIBE / 'build_requirements.md'}")


if __name__ == "__main__":
    main()
