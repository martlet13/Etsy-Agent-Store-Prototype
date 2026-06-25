import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
INDEX_FILE = STATE / "artifact_index.json"


FILES = {
    "evidence": "evidence_cards.json",
    "opportunity": "opportunity_cards.json",
    "design": "design_packages.json",
    "economics": "unit_economics_cards.json",
    "listing": "listing_drafts.json",
    "image_request": "image_generation_requests.json",
    "image_run": "image_generation_runs.json",
    "image_asset": "image_assets.json",
    "visual_qa": "visual_qa_reports.json",
    "publish_package": "publish_packages.json",
    "publish_run": "publish_runs.json",
    "handoff": "agent_handoffs.json",
}


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any):
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def add_artifact(index, artifact_type, item):
    artifact_id = item.get("id")
    if not artifact_id:
        return
    index["artifacts"][artifact_id] = {
        "id": artifact_id,
        "type": artifact_type,
        "status": item.get("status") or item.get("decision") or "unknown",
        "title": item.get("title") or item.get("name") or item.get("source") or "",
        "links": [],
        "raw_ref": {
            "file_type": artifact_type
        }
    }


def add_link(index, source, target, relation):
    if not source or not target:
        return
    if source not in index["artifacts"] or target not in index["artifacts"]:
        return
    link = {"target": target, "relation": relation}
    if link not in index["artifacts"][source]["links"]:
        index["artifacts"][source]["links"].append(link)


def build_index():
    data = {kind: load_json(STATE / filename, []) for kind, filename in FILES.items()}

    index = {
        "version": "V8.4",
        "built_at": now_stamp(),
        "artifacts": {},
        "chains": []
    }

    for kind, items in data.items():
        for item in items:
            add_artifact(index, kind, item)

    for opp in data["opportunity"]:
        opp_id = opp.get("id")
        for evid in opp.get("source_evidence_ids", []):
            add_link(index, evid, opp_id, "supports_opportunity")

    for design in data["design"]:
        add_link(index, design.get("opportunity_id"), design.get("id"), "creates_design")

    for econ in data["economics"]:
        add_link(index, econ.get("design_package_id"), econ.get("id"), "priced_by_ledger")

    for listing in data["listing"]:
        add_link(index, listing.get("design_package_id"), listing.get("id"), "listed_by_scribe")
        add_link(index, listing.get("unit_economics_card_id"), listing.get("id"), "enables_listing")

    for req in data["image_request"]:
        add_link(index, req.get("design_package_id"), req.get("id"), "requests_image")

    for run in data["image_run"]:
        add_link(index, run.get("image_request_id"), run.get("id"), "image_generation_run")

    for asset in data["image_asset"]:
        add_link(index, asset.get("image_request_id"), asset.get("id"), "generated_asset")

    for vqa in data["visual_qa"]:
        add_link(index, vqa.get("image_asset_id"), vqa.get("id"), "reviewed_by_sentinel")

    for pkg in data["publish_package"]:
        add_link(index, pkg.get("image_asset_id"), pkg.get("id"), "prepared_for_publish")
        add_link(index, pkg.get("listing_draft_id"), pkg.get("id"), "listing_for_publish")

    for run in data["publish_run"]:
        add_link(index, run.get("publish_package_id"), run.get("id"), "publish_run")

    chains = []
    for opp in data["opportunity"]:
        chain = {
            "opportunity_id": opp.get("id"),
            "title": opp.get("title"),
            "evidence_ids": opp.get("source_evidence_ids", []),
            "design_ids": [d.get("id") for d in data["design"] if d.get("opportunity_id") == opp.get("id")],
            "image_request_ids": [],
            "image_asset_ids": [],
            "visual_qa_ids": [],
            "economics_ids": [],
            "listing_ids": [],
            "publish_package_ids": [],
        }

        for design_id in chain["design_ids"]:
            chain["image_request_ids"].extend([r.get("id") for r in data["image_request"] if r.get("design_package_id") == design_id])
            chain["economics_ids"].extend([e.get("id") for e in data["economics"] if e.get("design_package_id") == design_id])
            chain["listing_ids"].extend([l.get("id") for l in data["listing"] if l.get("design_package_id") == design_id])

        for req_id in chain["image_request_ids"]:
            chain["image_asset_ids"].extend([a.get("id") for a in data["image_asset"] if a.get("image_request_id") == req_id])

        for asset_id in chain["image_asset_ids"]:
            chain["visual_qa_ids"].extend([v.get("id") for v in data["visual_qa"] if v.get("image_asset_id") == asset_id])
            chain["publish_package_ids"].extend([p.get("id") for p in data["publish_package"] if p.get("image_asset_id") == asset_id])

        chains.append(chain)

    index["chains"] = chains
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def main():
    index = build_index()
    print()
    print("# Artifact Index Built")
    print()
    print(f"Built At: {index['built_at']}")
    print(f"Artifacts: {len(index['artifacts'])}")
    print(f"Chains: {len(index['chains'])}")
    print(f"Saved: {INDEX_FILE}")
    print()


if __name__ == "__main__":
    main()
