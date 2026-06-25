import argparse
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
QA = ROOT / "04_QARoom"
ARCHIVES = ROOT / "05_Archives"

AGENT_FILE = QA / "AGENT.md"
LOG_DIR = QA / "logs"
REVIEWS_DIR = QA / "reviews"

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


def build_prompt(item_to_review: str) -> str:
    agent_rules = read_file(AGENT_FILE)
    qa_checklist = read_file(QA / "qa_checklist.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    lessons = read_file(ARCHIVES / "lessons_learned.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    return f'''
You are Sentinel, the QA agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

QA checklist:
{qa_checklist}

Relevant SpaceCommand memory:

decisions.md:
{decisions}

style_preferences.md:
{style}

lessons_learned.md:
{lessons}

approved_patterns.md:
{approved_patterns}

rejected_patterns.md:
{rejected_patterns}

Item to review:
{item_to_review}

Task:
Review the item.

Required format:

# Sentinel Review

## Verdict
Choose exactly one:
APPROVED
NEEDS_REVISION
REJECTED
REQUIRES_HUMAN_APPROVAL

## Summary
Briefly explain the result.

## Strengths
- ...

## Issues
- ...

## Required Fixes
- ...

## Safe Next Step
Give one safe local-only next step.

Rules:
- Do not use tools.
- Do not browse.
- Do not access accounts.
- Do not output JSON.
- Do not say only "no."
- Do not perform external actions.
- Output markdown only.
'''


def save_log(item: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"sentinel_{stamp}.md"
    path.write_text(
        f"# Sentinel Run {stamp}\n\n"
        f"## Item Reviewed\n\n{item}\n\n"
        f"## Review\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_review(response: str) -> Path:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REVIEWS_DIR / f"review_{stamp}.md"
    path.write_text(response, encoding="utf-8")
    return path


def route_verdict(response: str) -> Path:
    upper = response.upper()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"## Review Entry - {stamp}\n\n{response}\n"

    if "REQUIRES_HUMAN_APPROVAL" in upper:
        path = QA / "approval_required.md"
    elif "NEEDS_REVISION" in upper:
        path = QA / "revision_requests.md"
    elif "REJECTED" in upper:
        path = QA / "rejected_items.md"
    elif "APPROVED" in upper:
        path = QA / "approved_items.md"
    else:
        path = QA / "revision_requests.md"

    append_file(path, entry)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Sentinel QA agent.")
    parser.add_argument("item", nargs="*", help="Item to review")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save-review", action="store_true", help="Save review into QA review files")
    args = parser.parse_args()

    item = " ".join(args.item).strip()
    if not item:
        print("Paste the item Sentinel should review. Press Ctrl+Z then Enter on Windows when done:")
        chunks = []
        try:
            while True:
                chunks.append(input())
        except EOFError:
            pass
        item = "\n".join(chunks).strip()

    prompt = build_prompt(item)
    response = call_ollama(args.model, prompt)

    log_path = save_log(item, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_review:
        review_path = save_review(response)
        routed_path = route_verdict(response)
        print(f"[review saved] {review_path}")
        print(f"[verdict routed] {routed_path}")


if __name__ == "__main__":
    main()
