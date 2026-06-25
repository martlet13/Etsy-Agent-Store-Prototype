import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

MEMORY_FILE = STATE / "agent_memory_index.json"
DEDUPE_REPORTS_FILE = STATE / "dedupe_reports.json"
OPPORTUNITY_FILE = STATE / "opportunity_cards.json"
DESIGN_FILE = STATE / "design_packages.json"
IMAGE_REQUESTS_FILE = STATE / "image_generation_requests.json"
LISTINGS_FILE = STATE / "listing_drafts.json"


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


def norm(value):
    return " ".join(str(value).lower().strip().split())


def sha(value):
    return hashlib.sha256(norm(value).encode("utf-8")).hexdigest()[:16]


def run_dedupe_scan():
    memory = load_json(MEMORY_FILE, {
        "version": "V8.1",
        "seen_opportunity_titles": [],
        "seen_design_lanes": [],
        "seen_image_prompt_hashes": [],
        "seen_listing_titles": [],
        "blocked_duplicate_ideas": []
    })

    reports = load_json(DEDUPE_REPORTS_FILE, [])
    opportunities = load_json(OPPORTUNITY_FILE, [])
    designs = load_json(DESIGN_FILE, [])
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    listings = load_json(LISTINGS_FILE, [])

    duplicates = []
    warnings = []

    seen_opp = set(memory.get("seen_opportunity_titles", []))
    seen_lanes = set(memory.get("seen_design_lanes", []))
    seen_prompts = set(memory.get("seen_image_prompt_hashes", []))
    seen_listings = set(memory.get("seen_listing_titles", []))

    for opp in opportunities:
        title = norm(opp.get("title", ""))
        if title in seen_opp:
            duplicates.append({"type": "opportunity_title", "artifact_id": opp.get("id"), "value": title})
        else:
            seen_opp.add(title)

    for design in designs:
        lane = norm(design.get("design_concept", ""))[:120]
        if lane in seen_lanes:
            duplicates.append({"type": "design_lane", "artifact_id": design.get("id"), "value": lane})
        else:
            seen_lanes.add(lane)

    for req in requests:
        prompt_hash = sha(req.get("prompt", ""))
        if prompt_hash in seen_prompts:
            duplicates.append({"type": "image_prompt", "artifact_id": req.get("id"), "value": prompt_hash})
        else:
            seen_prompts.add(prompt_hash)

    for listing in listings:
        title = norm(listing.get("title", ""))
        if title in seen_listings:
            duplicates.append({"type": "listing_title", "artifact_id": listing.get("id"), "value": title})
        else:
            seen_listings.add(title)

    memory["seen_opportunity_titles"] = sorted(seen_opp)
    memory["seen_design_lanes"] = sorted(seen_lanes)
    memory["seen_image_prompt_hashes"] = sorted(seen_prompts)
    memory["seen_listing_titles"] = sorted(seen_listings)
    memory["blocked_duplicate_ideas"] = memory.get("blocked_duplicate_ideas", []) + duplicates

    save_json(MEMORY_FILE, memory)

    report = {
        "id": next_id("DEDUPE", reports),
        "type": "dedupe_report",
        "status": "duplicates_found" if duplicates else "pass",
        "duplicates": duplicates,
        "warnings": warnings,
        "summary": {
            "duplicates": len(duplicates),
            "opportunities": len(opportunities),
            "designs": len(designs),
            "image_requests": len(requests),
            "listings": len(listings)
        },
        "created_at": now_stamp()
    }

    reports.append(report)
    save_json(DEDUPE_REPORTS_FILE, reports)

    return report


def main():
    report = run_dedupe_scan()
    print()
    print("# Dedupe Report")
    print()
    print(f"ID: {report['id']}")
    print(f"Status: {report['status']}")
    print(f"Duplicates: {len(report.get('duplicates', []))}")
    if report.get("duplicates"):
        print()
        for dup in report["duplicates"]:
            print(f"- {dup.get('type')} {dup.get('artifact_id')}: {dup.get('value')}")
    print()


if __name__ == "__main__":
    main()
