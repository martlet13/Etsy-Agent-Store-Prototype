import argparse
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

COMMS = ROOT / "10_CommsHub"
RESEARCH = ROOT / "01_ResearchLab"
FORGE = ROOT / "02_ForgeFactory"
SCRIBE = ROOT / "03_ListingRoom"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"
TREASURY = ROOT / "06_Treasury"
WARROOM = ROOT / "07_WarRoom"
MEDIA = ROOT / "09_MediaBay"

AGENT_FILE = COMMS / "AGENT.md"
LOG_DIR = COMMS / "logs"
DRAFTS_DIR = COMMS / "drafts"

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
    scribe_spec = read_file(SCRIBE / "dashboard_spec.md")
    media_package = read_file(MEDIA / "media_package.md")
    warroom_review = read_file(WARROOM / "daily_review.md")
    cost_report = read_file(TREASURY / "cost_report.md")

    approved_items = read_file(QA / "approved_items.md")
    revision_requests = read_file(QA / "revision_requests.md")
    qa_checklist = read_file(QA / "qa_checklist.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    return f'''
You are Echo, the CommsHub agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Current SpaceCommand context:

Nova briefs:
{nova_briefs}

Forge concepts:
{forge_concepts}

Scribe dashboard spec:
{scribe_spec}

Signal media package:
{media_package}

WarRoom daily review:
{warroom_review}

Ledger cost report:
{cost_report}

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

User request:
{request}

Task:
Create a local-only communication draft package.

Required format:

# Echo Communication Draft Package

## Purpose
Explain what the communication package is for.

## Intended Use
Explain where this draft could be used locally.

## Status Update Draft
Write one internal status update.

## Approval Request Draft
Write one human-approval request for any future external action.

## Short Summary Draft
Write a short summary of current SpaceCommand progress.

## Reply Templates
Create 3 draft-only reply templates.

## Local Files To Create
List markdown files this package should save into.

## Safety Boundaries
State what Echo must not do without human approval.

## Sentinel Review Notes
List what Sentinel should review.

Rules:
- Do not browse.
- Do not access accounts or inboxes.
- Do not send messages.
- Do not post, upload, schedule, buy, sell, publish, scrape, or install tools.
- Do not claim anything was sent, posted, uploaded, scheduled, or published.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"echo_{stamp}.md"
    path.write_text(
        f"# Echo Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_draft(response: str, title: str = "Echo Draft") -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "echo_draft"
    path = DRAFTS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Echo CommsHub agent.")
    parser.add_argument("request", nargs="*", help="Request for Echo")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save-draft", action="store_true", help="Save response into CommsHub drafts")
    parser.add_argument("--title", default="Echo Draft", help="Draft title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Echo: ").strip()

    prompt = build_prompt(request)
    response = call_ollama(args.model, prompt)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_draft:
        draft_path = save_draft(response, args.title)
        append_file(COMMS / "status_updates.md", f"## Status Update Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(COMMS / "reply_templates.md", f"## Reply Templates Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(COMMS / "approval_needed.md", f"## Approval Request Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[draft saved] {draft_path}")
        print(f"[status_updates updated] {COMMS / 'status_updates.md'}")


if __name__ == "__main__":
    main()
