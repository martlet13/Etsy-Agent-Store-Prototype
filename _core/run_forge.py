import argparse
from datetime import datetime
from pathlib import Path

from llm_backend import call_llm

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
FORGE = ROOT / "02_ForgeFactory"
RESEARCH = ROOT / "01_ResearchLab"
ARCHIVES = ROOT / "05_Archives"
QA = ROOT / "04_QARoom"

AGENT_FILE = FORGE / "AGENT.md"
LOG_DIR = FORGE / "logs"
CONCEPTS_DIR = FORGE / "concepts"



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

    product_briefs = read_file(RESEARCH / "product_briefs.md")
    opportunity_report = read_file(RESEARCH / "opportunity_report.md")

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")

    qa_checklist = read_file(QA / "qa_checklist.md")
    approved_items = read_file(QA / "approved_items.md")

    return f'''
You are Forge, the ForgeFactory agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Nova research / briefs:
{product_briefs}

Opportunity report:
{opportunity_report}

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
Create an original local-only Forge concept output.

Required format:

# Forge Concept Output

## Source Brief
Summarize the brief or request being used.

## Core Concept
Describe the main concept.

## Visual Direction
Describe the style, mood, colors, layout, and sci-fi command-center feel.

## Room Layout Concepts
Give concepts for these rooms:
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
List specific interface components to build.

## Design Prompts
Write 5 original visual prompts for mockups or image generation.

## Build Notes
List practical notes for later implementation.

## Sentinel Review Notes
List what Sentinel should review before this moves forward.

Rules:
- Do not browse.
- Do not access accounts.
- Do not copy protected brands, logos, characters, creators, shops, or trademarked styles.
- Do not post, upload, message, buy, sell, or publish.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(request: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"forge_{stamp}.md"
    path.write_text(
        f"# Forge Run {stamp}\n\n"
        f"## Request\n\n{request}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_concept(response: str, title: str = "Forge Concept") -> Path:
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "forge_concept"
    path = CONCEPTS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Forge concept agent.")
    parser.add_argument("request", nargs="*", help="Request for Forge")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    parser.add_argument("--save-concept", action="store_true", help="Save response into Forge concepts")
    parser.add_argument("--title", default="Forge Concept", help="Concept title when saving")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("Request for Forge: ").strip()

    prompt = build_prompt(request)
    response = call_llm(prompt, backend=args.backend, ollama_model=args.model, claude_model=args.claude_model)

    log_path = save_log(request, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_concept:
        concept_path = save_concept(response, args.title)
        append_file(FORGE / "dashboard_concepts.md", f"## Saved Concept - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[concept saved] {concept_path}")
        print(f"[dashboard_concepts updated] {FORGE / 'dashboard_concepts.md'}")


if __name__ == "__main__":
    main()
