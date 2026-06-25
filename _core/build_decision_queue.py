import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
DECISION_FILE = STATE / "decision_queue.json"


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


def add_decision(queue, title, action, artifact_id="", severity="normal", reason="", can_cost_money=False, can_upload=False, can_publish=False):
    queue.append({
        "id": f"DECISION-{len(queue)+1:04d}",
        "title": title,
        "action": action,
        "artifact_id": artifact_id,
        "severity": severity,
        "reason": reason,
        "can_cost_money": can_cost_money,
        "can_upload": can_upload,
        "can_publish": can_publish,
        "requires_confirmation": True,
        "created_at": now_stamp(),
        "status": "pending"
    })


def build_queue():
    queue = []
    budget = load_json(STATE / "image_api_budget.json", {})
    api_checks = load_json(STATE / "api_connector_status_checks.json", [])
    board = load_json(STATE / "product_candidate_board.json", [])
    audits = load_json(STATE / "pipeline_audits.json", [])

    if not budget.get("live_api_enabled", False):
        add_decision(
            queue,
            "OpenAI image API is disabled",
            "review_enable_openai_images",
            "image_api_budget",
            "normal",
            "Enable only after org verification/API key/budget review.",
            can_cost_money=True
        )

    if budget.get("model") == "gpt-image-2":
        add_decision(
            queue,
            "Verify OpenAI organization for gpt-image-2",
            "verify_openai_org",
            "openai_images",
            "normal",
            "gpt-image-2 failed until organization verification is complete.",
            can_cost_money=False
        )

    if api_checks:
        latest = api_checks[-1]
        for result in latest.get("results", []):
            if result.get("computed_status") == "key_present_waiting_for_user_approval":
                add_decision(
                    queue,
                    f"Approve API connector: {result.get('name')}",
                    "approve_api_connector",
                    result.get("connector_id"),
                    "normal",
                    "Key exists but user approval is false."
                )

    for card in board:
        if card.get("next_action") == "ledger_costs_required":
            add_decision(
                queue,
                f"Add Ledger costs for {card.get('opportunity_id')}",
                "add_ledger_costs",
                card.get("design_id"),
                "high",
                "Product cannot list/upload until Ledger PASS."
            )
        elif card.get("next_action") == "sentinel_visual_qa":
            add_decision(
                queue,
                f"Run Sentinel QA for {card.get('image_asset_id')}",
                "run_visual_qa",
                card.get("image_asset_id"),
                "normal",
                "Image asset exists and needs QA."
            )
        elif card.get("next_action") == "resolve_image_provider_or_generate_later":
            add_decision(
                queue,
                f"Resolve image provider for {card.get('image_request_id')}",
                "resolve_image_provider",
                card.get("image_request_id"),
                "normal",
                "Image request is blocked by disabled API or provider failure.",
                can_cost_money=True
            )

    if audits:
        latest_audit = audits[-1]
        if latest_audit.get("status") == "blocked":
            add_decision(
                queue,
                "Audit is blocked",
                "run_state_doctor",
                latest_audit.get("id"),
                "critical",
                "Run State Doctor or inspect blockers."
            )

    DECISION_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return queue


def main():
    queue = build_queue()
    print()
    print("# Decision Queue Built")
    print()
    print(f"Decisions: {len(queue)}")
    for item in queue:
        print(f"- {item['id']}: {item['title']} [{item['severity']}]")
    print(f"Saved: {DECISION_FILE}")
    print()


if __name__ == "__main__":
    main()
