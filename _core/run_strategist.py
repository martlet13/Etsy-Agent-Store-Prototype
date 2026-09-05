import argparse
from datetime import datetime
from pathlib import Path

from llm_backend import call_llm

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

WARROOM = ROOT / "07_WarRoom"
RESEARCH = ROOT / "01_ResearchLab"
FORGE = ROOT / "02_ForgeFactory"
SCRIBE = ROOT / "03_ListingRoom"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"
TREASURY = ROOT / "06_Treasury"

AGENT_FILE = WARROOM / "AGENT.md"
LOG_DIR = WARROOM / "logs"
REVIEWS_DIR = WARROOM / "reviews"



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
    build_requirements = read_file(SCRIBE / "build_requirements.md")

    qa_approved = read_file(QA / "approved_items.md")
    qa_revisions = read_file(QA / "revision_requests.md")
    qa_rejected = read_file(QA / "rejected_items.md")
    qa_approval_required = read_file(QA / "approval_required.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    lessons = read_file(ARCHIVES / "lessons_learned.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    cost_report = read_file(TREASURY / "cost_report.md")
    tool_budget = read_file(TREASURY / "tool_budget.md")

    return f'''
You are Strategist, the WarRoom agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Current SpaceCommand evidence:

Nova briefs:
{nova_briefs}

Forge concepts:
{forge_concepts}

Scribe dashboard spec:
{scribe_spec}

Scribe build requirements:
{build_requirements}

Sentinel approved items:
{qa_approved}

Sentinel revision requests:
{qa_revisions}

Sentinel rejected items:
{qa_rejected}

Sentinel approval-required items:
{qa_approval_required}

Archivist decisions:
{decisions}

Archivist lessons learned:
{lessons}

Style preferences:
{style}

Approved patterns:
{approved_patterns}

Rejected patterns:
{rejected_patterns}

Ledger cost report:
{cost_report}

Ledger tool budget:
{tool_budget}

User request:
{request}

Task:
Create a local-only WarRoom strategic review.

Required format:

# SpaceCommand WarRoom Review

## Review Type
Daily or weekly.

## Confirmed Progress
Only list work supported by the provided evidence.

## What Is Working
List strengths.

## Weak Spots
List problems, gaps, or drift.

## Risks
List project risks. Mark external-action risks clearly.

## Recommended Fixes
List practical fixes.

## Next Mission
Give one focused next mission.

## Agent Assignments
Assign next tasks to existing rooms.

## Sentinel Review Notes
List what Sentinel should review next.

Rules:
- Do not browse.
- Do not access accounts.
- Do not post, upload, message, buy, sell, publish, scrape, or install tools.
- Do not invent results.
- Do not invent revenue.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"strategist_{stamp}.md"
    path.write_text(
        f"# Strategist Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_review(response: str, title: str = "WarRoom Review") -> Path:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "warroom_review"
    path = REVIEWS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Strategist WarRoom agent.")
    parser.add_argument("request", nargs="*", help="Request for Strategist")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    parser.add_argument("--save-review", action="store_true", help="Save response into WarRoom reviews")
    parser.add_argument("--title", default="WarRoom Review", help="Review title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Strategist: ").strip()

    prompt = build_prompt(request)
    response = call_llm(prompt, backend=args.backend, ollama_model=args.model, claude_model=args.claude_model)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_review:
        review_path = save_review(response, args.title)
        append_file(WARROOM / "daily_review.md", f"## Daily Review - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        append_file(WARROOM / "next_mission.md", f"## Next Mission Draft - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[review saved] {review_path}")
        print(f"[daily_review updated] {WARROOM / 'daily_review.md'}")
        print(f"[next_mission updated] {WARROOM / 'next_mission.md'}")


if __name__ == "__main__":
    main()
