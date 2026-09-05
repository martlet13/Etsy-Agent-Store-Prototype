import argparse
from datetime import datetime
from pathlib import Path

from llm_backend import call_llm

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

MEDIA = ROOT / "09_MediaBay"
RESEARCH = ROOT / "01_ResearchLab"
FORGE = ROOT / "02_ForgeFactory"
SCRIBE = ROOT / "03_ListingRoom"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"
WARROOM = ROOT / "07_WarRoom"

AGENT_FILE = MEDIA / "AGENT.md"
LOG_DIR = MEDIA / "logs"
PACKAGES_DIR = MEDIA / "packages"



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

    nova_briefs = read_file(RESEARCH / "product_briefs.md")
    forge_concepts = read_file(FORGE / "dashboard_concepts.md")
    scribe_spec = read_file(SCRIBE / "dashboard_spec.md")
    approved_items = read_file(QA / "approved_items.md")
    qa_checklist = read_file(QA / "qa_checklist.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    next_mission = read_file(WARROOM / "next_mission.md")

    return f'''
You are Signal, the MediaBay agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Nova briefs:
{nova_briefs}

Forge concepts:
{forge_concepts}

Scribe dashboard spec:
{scribe_spec}

Sentinel approved items:
{approved_items}

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

WarRoom next mission:
{next_mission}

User request:
{request}

Task:
Create a local-only media draft package.

Required format:

# Signal Media Package

## Purpose
Explain what this media package is for.

## Audience
Define who the content is for.

## Video Ideas
Create 5 local draft video ideas.

## Script Outline
Create one short script outline.

## Caption Drafts
Create 3 caption drafts.

## Thumbnail Concepts
Create 3 thumbnail concepts.

## Content Calendar Draft
Create a simple 5-item draft calendar. Do not claim anything is scheduled.

## Local Files To Create
List markdown files this package should save into.

## Safety Boundaries
State what Signal must not do without human approval.

## Sentinel Review Notes
List what Sentinel should review.

Rules:
- Do not browse.
- Do not access accounts.
- Do not post, upload, schedule, message, buy, sell, publish, scrape, or install tools.
- Do not claim anything was posted, scheduled, uploaded, or published.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"signal_{stamp}.md"
    path.write_text(
        f"# Signal Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_package(response: str, title: str = "Signal Media Package") -> Path:
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "signal_media_package"
    path = PACKAGES_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Signal MediaBay agent.")
    parser.add_argument("request", nargs="*", help="Request for Signal")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    parser.add_argument("--save-package", action="store_true", help="Save response into MediaBay packages")
    parser.add_argument("--title", default="Signal Media Package", help="Package title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Signal: ").strip()

    prompt = build_prompt(request)
    response = call_llm(prompt, backend=args.backend, ollama_model=args.model, claude_model=args.claude_model)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_package:
        package_path = save_package(response, args.title)
        append_file(MEDIA / "media_package.md", f"## Saved Media Package - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(MEDIA / "video_ideas.md", f"## Video Ideas Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(MEDIA / "caption_drafts.md", f"## Caption Drafts - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(MEDIA / "thumbnail_concepts.md", f"## Thumbnail Concepts - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(MEDIA / "content_calendar.md", f"## Content Calendar Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[package saved] {package_path}")
        print(f"[media_package updated] {MEDIA / 'media_package.md'}")


if __name__ == "__main__":
    main()
