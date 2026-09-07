import argparse
from datetime import datetime
from pathlib import Path

from llm_backend import call_llm

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"

TREASURY = ROOT / "06_Treasury"
ARCHIVES = ROOT / "05_Archives"
QA = ROOT / "04_QARoom"
SCRIBE = ROOT / "03_ListingRoom"

AGENT_FILE = TREASURY / "AGENT.md"
LOG_DIR = TREASURY / "logs"
REPORTS_DIR = TREASURY / "reports"



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

    monthly_costs = read_file(TREASURY / "monthly_costs.md")
    tool_budget = read_file(TREASURY / "tool_budget.md")
    revenue_notes = read_file(TREASURY / "revenue_notes.md")
    cost_report = read_file(TREASURY / "cost_report.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    qa_checklist = read_file(QA / "qa_checklist.md")
    build_requirements = read_file(SCRIBE / "build_requirements.md")

    return f'''
You are Ledger, the Treasury agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Current Treasury files:

monthly_costs.md:
{monthly_costs}

tool_budget.md:
{tool_budget}

revenue_notes.md:
{revenue_notes}

cost_report.md:
{cost_report}

SpaceCommand build requirements:
{build_requirements}

SpaceCommand memory:
decisions.md:
{decisions}

style_preferences.md:
{style}

approved_patterns.md:
{approved_patterns}

rejected_patterns.md:
{rejected_patterns}

Sentinel QA checklist:
{qa_checklist}

User request:
{request}

Task:
Create a local-only Treasury output.

Required format:

# Ledger Treasury Output

## Summary
Explain the cost/budget situation.

## Confirmed Costs
List only costs explicitly provided by the user.

## Estimated / Unknown Costs
List possible costs that need confirmation.

## Free / Local Resources
List resources that should cost nothing or near-nothing.

## Approval-Required Spending
List anything that would require human approval.

## Monthly Budget Template
Create a simple budget table.

## Safe Next Step
Give one safe local-only next step.

Rules:
- Do not browse.
- Do not access accounts.
- Do not access bank/payment data.
- Do not make purchases.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- If a cost is unknown, say unknown instead of inventing it.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"ledger_{stamp}.md"
    path.write_text(
        f"# Ledger Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_report(response: str, title: str = "Ledger Report") -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "ledger_report"
    path = REPORTS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Ledger treasury agent.")
    parser.add_argument("request", nargs="*", help="Request for Ledger")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    parser.add_argument("--save-report", action="store_true", help="Save response into Treasury reports")
    parser.add_argument("--title", default="Ledger Report", help="Report title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Ledger: ").strip()

    prompt = build_prompt(request)
    response = call_llm(prompt, backend=args.backend, ollama_model=args.model, claude_model=args.claude_model)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_report:
        report_path = save_report(response, args.title)
        append_file(TREASURY / "cost_report.md", f"## Saved Cost Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[report saved] {report_path}")
        print(f"[cost_report updated] {TREASURY / 'cost_report.md'}")


if __name__ == "__main__":
    main()
