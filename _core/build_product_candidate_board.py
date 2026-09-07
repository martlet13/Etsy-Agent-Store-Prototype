import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
BOARD_FILE = STATE / "product_candidate_board.json"


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


def latest(items):
    return items[-1] if items else None


def build_board():
    opportunities = load_json(STATE / "opportunity_cards.json", [])
    designs = load_json(STATE / "design_packages.json", [])
    economics = load_json(STATE / "unit_economics_cards.json", [])
    listings = load_json(STATE / "listing_drafts.json", [])
    image_requests = load_json(STATE / "image_generation_requests.json", [])
    image_runs = load_json(STATE / "image_generation_runs.json", [])
    image_assets = load_json(STATE / "image_assets.json", [])
    visual_qa = load_json(STATE / "visual_qa_reports.json", [])
    publish_packages = load_json(STATE / "publish_packages.json", [])

    cards = []

    for opp in opportunities:
        opp_id = opp.get("id")
        opp_designs = [d for d in designs if d.get("opportunity_id") == opp_id]
        design = latest(opp_designs)

        reqs = [r for r in image_requests if design and r.get("design_package_id") == design.get("id")]
        req = latest(reqs)

        runs = [r for r in image_runs if req and r.get("image_request_id") == req.get("id")]
        run = latest(runs)

        assets = [a for a in image_assets if req and a.get("image_request_id") == req.get("id")]
        asset = latest(assets)

        qas = [q for q in visual_qa if asset and q.get("image_asset_id") == asset.get("id")]
        qa = latest(qas)

        econs = [e for e in economics if design and e.get("design_package_id") == design.get("id")]
        econ = latest(econs)

        lists = [l for l in listings if design and l.get("design_package_id") == design.get("id")]
        listing = latest(lists)

        pubs = [p for p in publish_packages if asset and p.get("image_asset_id") == asset.get("id")]
        pub = latest(pubs)

        blocked_reasons = []
        next_action = "review"

        if not design:
            next_action = "forge_create_design"
        elif not req:
            next_action = "forge_create_image_request"
        elif not run:
            next_action = "run_image_budget_gate"
        elif run.get("status") in {"blocked_live_api_disabled", "openai_api_failed", "openai_api_failed_safe"}:
            next_action = "resolve_image_provider_or_generate_later"
            blocked_reasons.append(run.get("status"))
        elif not asset:
            next_action = "wait_for_generated_image_asset"
        elif not qa:
            next_action = "sentinel_visual_qa"
        elif not econ or econ.get("ledger_decision") != "PASS":
            next_action = "ledger_costs_required"
            blocked_reasons.append("ledger_not_passed")
        elif not listing or not listing.get("listing_allowed", False):
            next_action = "scribe_listing_required"
            blocked_reasons.append("listing_not_allowed")
        elif not pub or pub.get("issues"):
            next_action = "publisher_package_blocked_or_required"
        else:
            next_action = "ready_for_user_review"

        card = {
            "candidate_id": f"CAND-{len(cards)+1:04d}",
            "opportunity_id": opp_id,
            "title": opp.get("title"),
            "evidence_strength": "linked" if opp.get("source_evidence_ids") else "missing",
            "opportunity_status": opp.get("status"),
            "product_category": opp.get("product_category"),
            "product_fit": opp.get("product_fit", []),
            "design_id": design.get("id") if design else None,
            "design_status": design.get("status") if design else None,
            "image_request_id": req.get("id") if req else None,
            "image_run_status": run.get("status") if run else None,
            "image_asset_id": asset.get("id") if asset else None,
            "qa_status": qa.get("status") if qa else None,
            "ledger_status": econ.get("ledger_decision") if econ else None,
            "listing_status": listing.get("status") if listing else None,
            "publisher_status": pub.get("status") if pub else None,
            "next_action": next_action,
            "blocked_reasons": blocked_reasons,
            "updated_at": now_stamp()
        }

        cards.append(card)

    BOARD_FILE.write_text(json.dumps(cards, indent=2), encoding="utf-8")
    return cards


def main():
    cards = build_board()
    print()
    print("# Product Candidate Board Built")
    print()
    print(f"Cards: {len(cards)}")
    for card in cards:
        print(f"- {card['candidate_id']} {card.get('opportunity_id')}: {card.get('next_action')}")
    print(f"Saved: {BOARD_FILE}")
    print()


if __name__ == "__main__":
    main()
