import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


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


def create_listing_draft(design_id: str, product_type: str = "poster"):
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
    elif economics.get("decision") != "PASS":
        issues.append(f"ledger_not_passed:{economics.get('decision')}")

    if design and not design.get("production_allowed", False):
        issues.append("design_production_gate_false")

    listing_allowed = not issues

    if design:
        raw_title = design.get("title", "Original Design")
        title = f"{raw_title[:95]} | Original {product_type.title()} Gift"
        description = (
            f"Original {product_type} design based on a trend-safe concept.\n\n"
            f"Design concept:\n{design.get('design_concept', '')}\n\n"
            "Notes:\n"
            "- Original artwork direction.\n"
            "- No protected logos, characters, brand names, or celebrity likenesses intended.\n"
            "- Final listing/publishing remains blocked until Ledger, Sentinel, and Publisher gates pass.\n"
        )
        tags = generate_tags(design)
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
    args = parser.parse_args()

    listing, run = create_listing_draft(args.design_package_id, args.product_type)

    print()
    print("# Scribe Listing Draft")
    print()
    print(f"Run ID: {run['id']}")
    print(f"Listing ID: {listing['id']}")
    print(f"Status: {listing['status']}")
    print(f"Listing Allowed: {listing['listing_allowed']}")
    print(f"Publish Allowed: {listing['publish_allowed']}")
    print(f"Issues: {', '.join(listing.get('issues', [])) or 'none'}")
    print()
    print("## Title")
    print(listing.get("title", ""))
    print()
    print("## Tags")
    print(", ".join(listing.get("tags", [])))
    print()


if __name__ == "__main__":
    main()
