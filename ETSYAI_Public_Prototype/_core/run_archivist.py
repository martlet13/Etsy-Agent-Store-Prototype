import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
ARCHIVES = ROOT / "05_Archives"
AGENT_FILE = ARCHIVES / "AGENT.md"
LOG_DIR = ARCHIVES / "logs"
MEMORY_DIR = ARCHIVES / "memory"

DEFAULT_MODEL = "qwen2.5-coder:7b"


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_log(prompt: str, response: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"archivist_{stamp}.md"
    path.write_text(
        f"# Archivist Run {stamp}\n\n"
        f"## Prompt\n\n{prompt}\n\n"
        f"## Response\n\n{response}\n",
        encoding="utf-8",
    )
    return path


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


def build_prompt(user_message: str) -> str:
    agent_rules = read_file(AGENT_FILE)

    decisions = read_file(ARCHIVES / "decisions.md")
    feedback = read_file(ARCHIVES / "feedback_log.md")
    style = read_file(ARCHIVES / "style_preferences.md")
    lessons = read_file(ARCHIVES / "lessons_learned.md")
    approved = read_file(ARCHIVES / "approved_patterns.md")
    rejected = read_file(ARCHIVES / "rejected_patterns.md")

    return f'''
You are the Archivist agent for Instance SpaceCommand.

Follow your AGENT.md exactly.

AGENT.md:
{agent_rules}

Current memory context:

decisions.md:
{decisions}

feedback_log.md:
{feedback}

style_preferences.md:
{style}

lessons_learned.md:
{lessons}

approved_patterns.md:
{approved}

rejected_patterns.md:
{rejected}

User message:
{user_message}

Task:
Respond as Archivist.

Rules:
- Do not use tools.
- Do not browse.
- Do not access accounts.
- Do not output JSON.
- Do not say only "no."
- If the request is safe and local, complete it.
- If the request is unsafe, turn it into a safe local memory/draft task.
- Output markdown only.
'''


def append_memory(title: str, content: str) -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_title = safe_title.replace(" ", "_")[:60] or "memory"
    path = MEMORY_DIR / f"{stamp}_{safe_title}.md"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SpaceCommand Archivist agent.")
    parser.add_argument("message", nargs="*", help="Message for Archivist")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--save-memory", action="store_true", help="Save response into memory folder")
    parser.add_argument("--title", default="Archivist Note", help="Memory title when saving")
    args = parser.parse_args()

    user_message = " ".join(args.message).strip()
    if not user_message:
        user_message = input("Message for Archivist: ").strip()

    prompt = build_prompt(user_message)
    response = call_ollama(args.model, prompt)

    log_path = write_log(user_message, response)

    print()
    print(response)
    print()
    print(f"[log saved] {log_path}")

    if args.save_memory:
        memory_path = append_memory(args.title, response)
        print(f"[memory saved] {memory_path}")


if __name__ == "__main__":
    main()
