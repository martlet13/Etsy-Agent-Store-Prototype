import argparse
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
RESEARCH = ROOT / "01_ResearchLab"
ARCHIVES = ROOT / "05_Archives"
QA = ROOT / "04_QARoom"

AGENT_FILE = RESEARCH / "AGENT.md"
LOG_DIR = RESEARCH / "logs"
BRIEFS_DIR = RESEARCH / "briefs"

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


def build_prompt(theme: str) -> str:
    agent_rules = read_file(AGENT_FILE)

    decisions = read_file(ARCHIVES / "decisions.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    lessons = read_file(ARCHIVES / "lessons_learned.md")
    approved_patterns = read_file(ARCHIVES / "approved_patterns.md")
    rejected_patterns = read_file(ARCHIVES / "rejected_patterns.md")
    qa_checklist = read_file(QA / "qa_checklist.md")

    return f'''
You are Nova, the Research Lab agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

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

Sentinel QA checklist:
{qa_checklist}

User-provided theme or research request:
{theme}

Task:
Create an original local-only research output.

Required format:

# Nova Research Output

## Theme
Restate the theme.

## Summary
Briefly explain the opportunity.

## Original Niche Ideas
Provide 10 original niche ideas.

## Best 3 Opportunities
For each:
- Name:
- Audience:
- Why it could work:
- Risk:
- Safe next step:

## Product / Content Brief
Create one structured brief that ForgeFactory could later use.

## Sentinel Notes
List anything Sentinel should review before this moves forward.

Rules:
- Do not browse.
- Do not scrape.
- Do not access accounts.
- Do not copy protected brands, logos, characters, creators, shops, or trademarked styles.
- Do not output JSON.
- Do not say only "no."
- Keep everything local-only and draft-only.
- Output markdown only.
'''


def save_log(theme: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"nova_{stamp}.md"
    path.write_text(
        f"# Nova Run {stamp}\n\n"
        f"## Theme\n\n{theme}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


def save_brief(response: str, title: str = "Nova Brief") -> Path:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "nova_brief"
    path = BRIEFS_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(response, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Nova research agent.")
    parser.add_argument("theme", nargs="*", help="Theme or research request for Nova")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save-brief", action="store_true", help="Save response into ResearchLab briefs")
    parser.add_argument("--title", default="Nova Brief", help="Brief title when saving")
    args = parser.parse_args()

    theme = " ".join(args.theme).strip()
    if not theme:
        theme = input("Theme for Nova: ").strip()

    prompt = build_prompt(theme)
    response = call_ollama(args.model, prompt)

    log_path = save_log(theme, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_brief:
        brief_path = save_brief(response, args.title)
        append_file(RESEARCH / "product_briefs.md", f"## Saved Brief - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{response}")
        print(f"[brief saved] {brief_path}")
        print(f"[product_briefs updated] {RESEARCH / 'product_briefs.md'}")


if __name__ == "__main__":
    main()
