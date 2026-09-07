import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_backend import call_llm


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

DESIGN_FILE = STATE / "design_packages.json"
ECONOMICS_FILE = STATE / "unit_economics_cards.json"
LISTINGS_FILE = STATE / "listing_drafts.json"
SCRIBE_RUNS_FILE = STATE / "scribe_listing_runs.json"


FORBIDDEN_TAGS = {
    "disney", "marvel", "pokemon", "star wars", "harry potter",
    "taylor swift", "nike", "adidas", "nfl", "nba", "mlb"
}


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def next_id(prefix: str, records: List[Dict[str, Any]]) -> str:
    highest = 0
    for item in records:
        raw = str(item.get("id", ""))
        if raw.startswith(prefix + "-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass
    return f"{prefix}-{highest + 1:04d}"


def find_by_id(records, record_id):
    for item in records:
        if item.get("id") == record_id:
            return item
    return None


def latest_economics_for_design(design_id: str):
    cards = load_json(ECONOMICS_FILE, [])
    matches = [x for x in cards if x.get("design_package_id") == design_id]
    return matches[-1] if matches else None


def clean_tag(raw):
    tag = "".join(ch.lower() if ch.isalnum() or ch in {" ", "-"} else " " for ch in str(raw))
    tag = " ".join(tag.split())
    return tag[:20]


def generate_tags(design):
    words = []
    for field in ["title", "design_concept", "image_prompt"]:
        words.extend(str(design.get(field, "")).lower().replace(",", " ").split())

    base = [
        "wall art",
        "poster print",
        "gift idea",
        "home decor",
        "aesthetic print",
        "cozy decor",
        "retro art",
        "minimal decor",
        "printable style",
        "room decor",
        "desk decor",
        "modern poster",
        "unique gift"
    ]

    if "mug" in words:
        base[0] = "coffee mug"
    if "shirt" in words:
        base[0] = "graphic tee"
    if "tote" in words:
        base[0] = "tote bag"

    tags = []
    for tag in base:
        cleaned = clean_tag(tag)
        if cleaned and cleaned not in FORBIDDEN_TAGS and cleaned not in tags:
            tags.append(cleaned)

    return tags[:13]


def clean_tags_list(raw_tags: Any) -> List[str]:
    tags: List[str] = []

    if not isinstance(raw_tags, list):
        return tags

    for raw in raw_tags:
        cleaned = clean_tag(raw)
        if cleaned and cleaned not in FORBIDDEN_TAGS and cleaned not in tags:
            tags.append(cleaned)

    return tags[:13]


def extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Claude/Ollama responses sometimes wrap JSON in prose or markdown code
    fences. Pull out the first {...} block and parse it.
    """
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else None

    if not candidate:
        brace_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        candidate = brace_match.group(0) if brace_match else None

    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def build_copy_prompt(design: Dict[str, Any], product_type: str) -> str:
    return f"""
You are Scribe, the listing-copy agent for an Etsy print-on-demand shop.

Write Etsy listing copy for this original, already-approved design. Do not
invent claims about materials, shipping, or brand names. Do not reference
any real brand, celebrity, franchise, or copyrighted character.

DESIGN:
- Title seed: {design.get("title")}
- Design concept: {design.get("design_concept")}
- Safety notes: {design.get("safety_notes")}
- Product type: {product_type}

Return ONLY a JSON object, no prose before or after, in exactly this shape:
{{
  "title": "<=140 characters, buyer-facing, includes product type>",
  "description": "<3-6 short paragraphs: what it is, why someone would love it, care/print notes, honest disclaimer that this is an original print-on-demand design>",
  "tags": ["<=20 chars each", "... up to 13 tags total, no punctuation-heavy phrases, no brand/IP terms"]
}}
""".strip()


def generate_copy_with_llm(
    design: Dict[str, Any],
    product_type: str,
    backend: Optional[str] = None,
    ollama_model: Optional[str] = None,
    claude_model: Optional[str] = None,
) -> Dict[str, Any]:
    prompt = build_copy_prompt(design, product_type)
    raw_response = call_llm(prompt, backend=backend, ollama_model=ollama_model, claude_model=claude_model)

    parsed = extract_json_object(raw_response)

    if not parsed or "title" not in parsed:
        raise ValueError(f"LLM response did not contain a parseable listing-copy JSON object: {raw_response[:500]}")

    title = str(parsed.get("title", "")).strip()[:140]
    description = str(parsed.get("description", "")).strip()
    tags = clean_tags_list(parsed.get("tags", []))

    if not title or not description:
        raise ValueError("LLM response was missing a title or description.")

    return {"title": title, "description": description, "tags": tags}


def create_listing_draft(
    design_id: str,
    product_type: str = "poster",
    backend: Optional[str] = None,
    ollama_model: Optional[str] = None,
    claude_model: Optional[str] = None,
    use_llm: bool = True,
):
    designs = load_json(DESIGN_FILE, [])
    listings = load_json(LISTINGS_FILE, [])
    runs = load_json(SCRIBE_RUNS_FILE, [])

    design = find_by_id(designs, design_id)
    issues = []
    warnings = []

    if not design:
        issues.append("missing_design_package")

    economics = latest_economics_for_design(design_id)

    if not economics:
        issues.append("missing_unit_economics")
    elif economics.get("ledger_decision") != "PASS":
        issues.append(f"ledger_not_passed:{economics.get('ledger_decision')}")

    if design and not design.get("production_allowed", False):
        issues.append("design_production_gate_false")

    listing_allowed = not issues

    def template_copy():
        raw_title = design.get("title", "Original Design")
        return {
            "title": f"{raw_title[:95]} | Original {product_type.title()} Gift",
            "description": (
                f"Original {product_type} design based on a trend-safe concept.\n\n"
                f"Design concept:\n{design.get('design_concept', '')}\n\n"
                "Notes:\n"
                "- Original artwork direction.\n"
                "- No protected logos, characters, brand names, or celebrity likenesses intended.\n"
                "- Final listing/publishing remains blocked until Ledger, Sentinel, and Publisher gates pass.\n"
            ),
            "tags": generate_tags(design),
        }

    if design:
        copy = None

        if listing_allowed and use_llm:
            try:
                copy = generate_copy_with_llm(
                    design=design,
                    product_type=product_type,
                    backend=backend,
                    ollama_model=ollama_model,
                    claude_model=claude_model,
                )
            except Exception as exc:  # noqa: BLE001 - fall back rather than break the pipeline
                warnings.append(f"llm_copy_generation_failed:{exc}")

        if copy is None:
            copy = template_copy()

        title = copy["title"]
        description = copy["description"]
        tags = copy["tags"]
    else:
        title = ""
        description = ""
        tags = []

    listing = {
        "id": next_id("LISTING", listings),
        "type": "listing_draft",
        "status": "allowed" if listing_allowed else "blocked",
        "design_package_id": design_id,
        "unit_economics_card_id": economics.get("id") if economics else None,
        "product_type": product_type,
        "title": title,
        "description": description,
        "tags": tags,
        "materials": [product_type, "print on demand"],
        "occasion": ["gift", "home decor", "personal style"],
        "recipient": ["friend", "partner", "coworker", "self"],
        "seo_keyword_rationale": "Tags are generic trend-safe POD keywords. No protected brand/IP terms.",
        "listing_allowed": listing_allowed,
        "publish_allowed": False,
        "issues": issues,
        "warnings": warnings,
        "created_at": now_stamp(),
    }

    listings.append(listing)
    save_json(LISTINGS_FILE, listings)

    run = {
        "id": next_id("SCRIBERUN", runs),
        "type": "scribe_listing_run",
        "status": listing["status"],
        "design_package_id": design_id,
        "listing_draft_id": listing["id"],
        "issues": issues,
        "warnings": warnings,
        "created_at": now_stamp(),
    }

    runs.append(run)
    save_json(SCRIBE_RUNS_FILE, runs)

    return listing, run


def main():
    parser = argparse.ArgumentParser(description="Run Scribe on a design package.")
    parser.add_argument("--design-package-id", required=True)
    parser.add_argument("--product-type", default="poster")
    parser.add_argument("--no-llm", action="store_true", help="Skip Claude/Ollama copy generation and use the deterministic template instead.")
    parser.add_argument("--backend", default=None, choices=["claude", "ollama"], help="LLM backend for copy generation. Defaults to Claude if ANTHROPIC_API_KEY is set, else Ollama.")
    parser.add_argument("--model", default=None, help="Ollama model name (used when --backend ollama)")
    parser.add_argument("--claude-model", default=None, help="Anthropic model id/alias (used when --backend claude)")
    args = parser.parse_args()

    listing, run = create_listing_draft(
        args.design_package_id,
        args.product_type,
        backend=args.backend,
        ollama_model=args.model,
        claude_model=args.claude_model,
        use_llm=not args.no_llm,
    )

    print()
    print("# Scribe Listing Draft")
    print()
    print(f"Run ID: {run['id']}")
    print(f"Listing ID: {listing['id']}")
    print(f"Status: {listing['status']}")
    print(f"Listing Allowed: {listing['listing_allowed']}")
    print(f"Publish Allowed: {listing['publish_allowed']}")
    print(f"Issues: {', '.join(listing.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(listing.get('warnings', [])) or 'none'}")
    print()
    print("## Title")
    print(listing.get("title", ""))
    print()
    print("## Tags")
    print(", ".join(listing.get("tags", [])))
    print()


if __name__ == "__main__":
    main()
