from typing import Any, Dict, List, Optional, Tuple

from agent_plain_language_views import (
    STATE,
    as_list,
    blocked_reasons,
    count_status,
    first_present,
    is_connected,
    latest,
    load_json,
    money,
    money_text,
    now_stamp,
    save_json,
    simple_view,
    text,
)


TRANSCRIPT_TABS = [
    "ultron",
    "nova",
    "forge",
    "communications",
    "treasury",
    "scribe",
    "media",
    "vibes",
    "sentinel",
    "publisher",
    "archives",
    "armory",
]


STATE_SOURCES = {
    "ultron": [
        "pipeline_audits.json",
        "decision_queue.json",
        "spacecommand_cycle_reports.json",
        "product_candidate_board.json",
        "state_doctor_reports.json",
    ],
    "nova": [
        "public_source_snapshots.json",
        "connector_runs.json",
        "evidence_cards.json",
        "opportunity_cards.json",
    ],
    "forge": [
        "design_packages.json",
        "image_generation_requests.json",
        "image_generation_runs.json",
        "image_assets.json",
    ],
    "communications": ["communications_inbox.json"],
    "treasury": [
        "unit_economics_cards.json",
        "supplier_product_catalog.json",
        "supplier_catalog_checks.json",
        "pricing_rules.json",
        "supplier_costs.json",
    ],
    "scribe": ["listing_drafts.json", "scribe_listing_runs.json"],
    "media": ["media_upload_jobs.json"],
    "vibes": ["vibes_creative_assets.json"],
    "sentinel": ["visual_qa_reports.json", "image_file_inspections.json"],
    "publisher": ["publish_packages.json", "publish_runs.json", "publishing_connectors.json"],
    "archives": ["backup_reports.json", "state_doctor_reports.json", "artifact_index.json"],
    "armory": ["armory_upgrade_log.json"],
}


def ensure_optional_state_files() -> List[str]:
    touched: List[str] = []
    defaults: Dict[str, Any] = {
        "communications_inbox.json": [
            {
                "message_id": "COMMS-PLACEHOLDER-0001",
                "source_platform": "local_placeholder",
                "commenter": "Example customer",
                "comment": "Is this available in another color?",
                "received_at": now_stamp(),
                "sentiment": "neutral",
                "needs_reply": True,
                "suggested_reply": "Thanks for asking. I can check color options before this goes live.",
                "status": "placeholder_local_safe",
            }
        ],
        "vibes_creative_assets.json": [],
        "media_upload_jobs.json": [],
        "armory_upgrade_log.json": [
            {
                "upgrade_id": "ARMORY-TRANSCRIPT-V10",
                "agent": "Armory",
                "upgrade_title": "V10 Transcript Alignment Adapter",
                "status": "completed",
                "reason": "Thin adapter maps existing backbone state into transcript agent roles.",
                "created_at": now_stamp(),
            }
        ],
    }

    for file_name, default in defaults.items():
        path = STATE / file_name
        existing = load_json(file_name, None)
        if existing is None:
            save_json(file_name, default)
            touched.append(file_name)
            continue
        if file_name == "communications_inbox.json" and existing == []:
            save_json(file_name, default)
            touched.append(file_name)
        if file_name == "armory_upgrade_log.json" and existing == []:
            save_json(file_name, default)
            touched.append(file_name)
    return touched


def load_state() -> Dict[str, Any]:
    return {
        "public_snapshots": as_list(load_json("public_source_snapshots.json", [])),
        "connector_runs": as_list(load_json("connector_runs.json", [])),
        "evidence": as_list(load_json("evidence_cards.json", [])),
        "opportunities": as_list(load_json("opportunity_cards.json", [])),
        "designs": as_list(load_json("design_packages.json", [])),
        "image_requests": as_list(load_json("image_generation_requests.json", [])),
        "image_runs": as_list(load_json("image_generation_runs.json", [])),
        "image_assets": as_list(load_json("image_assets.json", [])),
        "visual_qa": as_list(load_json("visual_qa_reports.json", [])),
        "image_inspections": as_list(load_json("image_file_inspections.json", [])),
        "economics": as_list(load_json("unit_economics_cards.json", [])),
        "supplier_products": as_list(load_json("supplier_product_catalog.json", {})),
        "supplier_checks": as_list(load_json("supplier_catalog_checks.json", [])),
        "pricing_rules": load_json("pricing_rules.json", {}),
        "supplier_costs": as_list(load_json("supplier_costs.json", [])),
        "listings": as_list(load_json("listing_drafts.json", [])),
        "scribe_runs": as_list(load_json("scribe_listing_runs.json", [])),
        "publish_packages": as_list(load_json("publish_packages.json", [])),
        "publish_runs": as_list(load_json("publish_runs.json", [])),
        "publishing_connectors": as_list(load_json("publishing_connectors.json", {})),
        "audits": as_list(load_json("pipeline_audits.json", [])),
        "decisions": as_list(load_json("decision_queue.json", [])),
        "cycles": as_list(load_json("spacecommand_cycle_reports.json", [])),
        "board": as_list(load_json("product_candidate_board.json", [])),
        "backups": as_list(load_json("backup_reports.json", [])),
        "doctor": as_list(load_json("state_doctor_reports.json", [])),
        "artifact_index": load_json("artifact_index.json", {}),
        "communications": as_list(load_json("communications_inbox.json", [])),
        "vibes": as_list(load_json("vibes_creative_assets.json", [])),
        "media": as_list(load_json("media_upload_jobs.json", [])),
        "armory": as_list(load_json("armory_upgrade_log.json", [])),
    }


def exact_sales(item: Dict[str, Any]) -> Optional[Any]:
    direct = first_present(
        item,
        ["items_sold", "sales_count", "units_sold", "number_sold", "sold_count", "sales"],
    )
    if direct is not None:
        return direct
    metrics = item.get("metrics")
    if isinstance(metrics, dict):
        return first_present(metrics, ["items_sold", "sales_count", "units_sold", "number_sold", "sold_count", "sales"])
    return None


def recommended_product(item: Dict[str, Any]) -> str:
    fits = item.get("product_fit")
    if isinstance(fits, list) and fits:
        return text(fits[0], "a product concept")
    return text(first_present(item, ["product_category", "title", "theme", "query"], "a product concept"))


def nova_line(item: Dict[str, Any]) -> str:
    found = text(first_present(item, ["title", "keyword", "query", "theme", "source_title"], "a research item"))
    sold = exact_sales(item)
    time_frame = text(first_present(item, ["time_window", "time_frame", "candidate_window", "created_at"], "the available research window"))
    if sold is not None:
        return f"I found {found}. It sold {sold} in the last {time_frame}. I think we should make {recommended_product(item)}."
    return (
        f"I found {found}. I do not have exact sales numbers yet. The source says it is trending or relevant. "
        "This should stay research-only until stronger proof exists."
    )


def build_nova_view(state: Dict[str, Any]) -> Dict[str, Any]:
    records = state["opportunities"] + state["evidence"] + state["connector_runs"] + state["public_snapshots"]
    visible = [nova_line(item) for item in records[-8:]]
    return simple_view(
        "Nova Research",
        "working" if records else "waiting",
        f"Nova has {len(state['evidence'])} evidence cards, {len(state['opportunities'])} opportunities, {len(state['connector_runs'])} connector runs, and {len(state['public_snapshots'])} public snapshots.",
        "Keep public-source research separate from production until sales proof and costs are stronger.",
        {
            "public_source_snapshots": len(state["public_snapshots"]),
            "connector_runs": len(state["connector_runs"]),
            "evidence_cards": len(state["evidence"]),
            "opportunity_cards": len(state["opportunities"]),
        },
        visible or ["Nova is waiting for public research inputs."],
        ["Approve stronger research sources before production."] if state["opportunities"] else [],
    )


def build_forge_view(state: Dict[str, Any]) -> Dict[str, Any]:
    designs = state["designs"]
    requests = state["image_requests"]
    runs = state["image_runs"]
    assets = state["image_assets"]
    waiting = []
    for design in designs:
        if not design.get("production_allowed"):
            waiting.append(f"{text(design.get('id'))} is waiting on QA, Treasury, or approval before production.")
    updates = [
        f"Images generated: {len(assets)} asset record(s) and {len(runs)} generation run record(s).",
        f"Image requests waiting: {count_status(requests, 'ready', 'waiting', 'blocked')} of {len(requests)}.",
        f"Product concepts prepared: {len(designs)} design package(s).",
    ] + waiting[-5:]
    return simple_view(
        "Forge Product/Image Factory",
        "working" if designs or requests else "waiting",
        "Forge is adapting existing design packages, image requests, image runs, and image assets into a factory view.",
        "Prepare product concepts and keep blocked concepts out of publishing.",
        {
            "design_packages": len(designs),
            "image_generation_requests": len(requests),
            "image_generation_runs": len(runs),
            "image_assets": len(assets),
            "production_allowed": sum(1 for item in designs if item.get("production_allowed")),
        },
        updates,
        [line for line in waiting if "approval" in line][:5],
    )


def sentinel_status(item: Dict[str, Any]) -> str:
    status = text(item.get("status")).replace("_", " ")
    safe = not blocked_reasons(item)
    product_ready = bool(item.get("approved_for_product")) or "pass" in text(item.get("status"), "").lower()
    if item.get("file_exists") is False:
        return f"{text(item.get('id'))} needs repair because the image file is missing."
    if product_ready and safe:
        return f"{text(item.get('id'))} looks safe, accurate, and product-ready."
    if product_ready:
        return f"{text(item.get('id'))} is partly ready but still has warnings: {', '.join(blocked_reasons(item)) or status}."
    return f"{text(item.get('id'))} is not product-ready yet. Status: {status}."


def build_sentinel_view(state: Dict[str, Any]) -> Dict[str, Any]:
    records = state["visual_qa"] + state["image_inspections"]
    updates = [sentinel_status(item) for item in records[-8:]]
    return simple_view(
        "Sentinel QA",
        "guarding" if records else "waiting",
        f"Sentinel has {len(state['visual_qa'])} visual QA reports and {len(state['image_inspections'])} image file inspections.",
        "Check whether images are safe, accurate, product-ready, or need repair.",
        {
            "visual_qa_reports": len(state["visual_qa"]),
            "image_file_inspections": len(state["image_inspections"]),
            "product_ready": sum(1 for item in state["visual_qa"] if item.get("approved_for_product")),
            "needs_repair": count_status(state["visual_qa"] + state["image_inspections"], "blocked", "failed", "repair"),
        },
        updates or ["Sentinel is waiting for image files to inspect."],
        [sentinel_status(item) for item in records if "repair" in sentinel_status(item).lower()][:5],
    )


def economics_total(item: Dict[str, Any], pricing_rules: Dict[str, Any]) -> Tuple[Optional[float], Dict[str, str]]:
    product_cost = money(first_present(item, ["production_cost", "product_cost", "item_price"]))
    shipping_cost = money(first_present(item, ["shipping_cost_us", "shipping_cost"]))
    supplier_cost = money(first_present(item, ["supplier_cost", "base_cost"]))
    image_cost = money(first_present(item, ["api_image_cost", "image_cost"]))
    etsy_listing_fee = money(pricing_rules.get("etsy_listing_fee"))
    pieces = {
        "product_cost": money_text(product_cost),
        "shipping_cost": money_text(shipping_cost),
        "supplier_cost": money_text(supplier_cost),
        "etsy_fees": money_text(etsy_listing_fee),
        "api_image_cost": money_text(image_cost),
    }
    required = [product_cost, shipping_cost]
    if any(value is None for value in required):
        return None, pieces
    total = sum(value for value in [product_cost, shipping_cost, supplier_cost, etsy_listing_fee, image_cost] if value is not None)
    return total, pieces


def build_treasury_view(state: Dict[str, Any]) -> Dict[str, Any]:
    updates: List[str] = []
    actions: List[str] = []
    for item in state["economics"][-8:]:
        total, pieces = economics_total(item, state["pricing_rules"])
        if total is None:
            line = "This product cannot publish yet because costs are missing."
            actions.append(f"{text(item.get('id'))}: {line}")
        else:
            safe_price = total * 1.10
            decision = text(first_present(item, ["ledger_decision", "decision", "status"]))
            line = (
                f"{text(item.get('id'))}: product cost {pieces['product_cost']}, shipping cost {pieces['shipping_cost']}, "
                f"supplier cost {pieces['supplier_cost']}, Etsy fees {pieces['etsy_fees']}, API/image cost {pieces['api_image_cost']}. "
                f"Minimum safe price is ${safe_price:.2f}. Status: {decision}."
            )
            if "pass" not in decision.lower():
                actions.append(f"{text(item.get('id'))}: blocked until Treasury passes.")
        updates.append(line)
    return simple_view(
        "Treasury Cost/Profit Control",
        "blocked" if actions else ("safe" if updates else "waiting"),
        "Treasury summarizes existing unit economics and supplier data without replacing the cost system.",
        "Keep any product with missing or unverified costs out of publishing.",
        {
            "unit_economics_cards": len(state["economics"]),
            "supplier_products": len(state["supplier_products"]),
            "supplier_catalog_checks": len(state["supplier_checks"]),
            "supplier_cost_records": len(state["supplier_costs"]),
            "blocked_or_missing_costs": len(actions),
        },
        updates or ["This product cannot publish yet because costs are missing."],
        actions[:8],
    )


def build_scribe_view(state: Dict[str, Any]) -> Dict[str, Any]:
    updates = []
    actions = []
    for item in state["listings"][-8:]:
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        blocked = not item.get("listing_allowed") or not item.get("publish_allowed")
        line = (
            f"Title: {text(item.get('title'), 'Untitled listing')}. "
            f"Description: {text(item.get('description'), 'missing')[:180]}. "
            f"Tags: {', '.join(tags) if tags else 'missing'}. "
            f"SEO status: {text(first_present(item, ['seo_status', 'seo_keyword_rationale'], 'draft'))}. "
            f"Blocked: {'yes' if blocked else 'no'}."
        )
        updates.append(line)
        if blocked:
            actions.append(f"{text(item.get('id'))} listing is blocked.")
    return simple_view(
        "Scribe Listing/SEO",
        "blocked" if actions else ("drafting" if updates else "waiting"),
        f"Scribe has {len(state['listings'])} listing draft(s) and {len(state['scribe_runs'])} listing run(s).",
        "Write titles, descriptions, tags, and SEO notes while respecting production gates.",
        {"listing_drafts": len(state["listings"]), "scribe_listing_runs": len(state["scribe_runs"]), "blocked": len(actions)},
        updates or ["Scribe is waiting for a design and Treasury approval."],
        actions[:8],
    )


def build_publisher_view(state: Dict[str, Any]) -> Dict[str, Any]:
    connectors = state["publishing_connectors"]
    by_platform = {text(item.get("platform"), "").lower(): item for item in connectors}
    updates = []
    actions = []
    for item in state["publish_packages"][-8:]:
        reasons = blocked_reasons(item)
        live_locked = not item.get("live_upload_allowed") or not item.get("live_publish_allowed")
        line = (
            f"{text(item.get('id'))} is {'ready' if not reasons and not live_locked else 'blocked'}. "
            f"Live publishing is locked because {', '.join(reasons) if reasons else 'user approval or connector approval is still required'}."
        )
        updates.append(line)
        if reasons or live_locked:
            actions.append(line)
    for platform in ("printify", "printful", "etsy"):
        connector = by_platform.get(platform) or next((item for item in connectors if platform in text(item.get("id"), "").lower()), {})
        updates.append(f"{platform.title()} connected: {'yes' if connector and is_connected(connector) else 'no'}.")
    return simple_view(
        "Publisher Publishing Packages",
        "blocked" if actions else ("ready" if state["publish_packages"] else "waiting"),
        f"Publisher has {len(state['publish_packages'])} package(s) and {len(state['publish_runs'])} publish run(s).",
        "Prepare packages but keep live publishing locked until every gate and connector approval passes.",
        {"publish_packages": len(state["publish_packages"]), "publish_runs": len(state["publish_runs"]), "connectors": len(connectors), "blocked": len(actions)},
        updates or ["Publisher is waiting for approved assets, costs, listings, and connector approval."],
        actions[:8],
    )


def build_ultron_view(state: Dict[str, Any]) -> Dict[str, Any]:
    audit = latest(state["audits"]) or {}
    blockers = audit.get("findings") if isinstance(audit.get("findings"), list) else []
    warnings = audit.get("warnings") if isinstance(audit.get("warnings"), list) else []
    decisions = [item for item in state["decisions"] if text(item.get("status"), "").lower() in ("pending", "open", "waiting")]
    board = state["board"]
    next_action = text(first_present(latest(board) or {}, ["next_action"], "run the next safe gated pipeline step"))
    updates = [
        f"Latest pipeline audit {text(audit.get('id'), 'none')} is {text(audit.get('status'), 'unknown')}.",
        f"Blockers: {len(blockers)}. Warnings: {len(warnings)}.",
        f"Decision queue has {len(decisions)} item(s) needing user approval.",
        f"Product candidate board has {len(board)} candidate(s). Next best action: {next_action}.",
    ]
    updates += [f"Warning: {text(item.get('message'), text(item))}" for item in warnings[:5]]
    return simple_view(
        "Ultron Overseer Summary",
        text(audit.get("status"), "unknown"),
        "Ultron summarizes the existing audit, blockers, warnings, decision queue, cycle reports, and product board.",
        next_action,
        {
            "latest_audit": text(audit.get("id"), "none"),
            "blockers": len(blockers),
            "warnings": len(warnings),
            "decision_queue": len(decisions),
            "cycle_reports": len(state["cycles"]),
            "product_candidates": len(board),
        },
        updates,
        [f"{text(item.get('id'))}: {text(item.get('title'))}" for item in decisions[:8]],
    )


def build_communications_view(state: Dict[str, Any]) -> Dict[str, Any]:
    updates = [
        f"{text(item.get('commenter'))} said '{text(item.get('comment'))}' on {text(item.get('source_platform'))}."
        for item in state["communications"][-8:]
    ]
    actions = [text(item.get("message_id")) for item in state["communications"] if item.get("needs_reply")]
    return simple_view(
        "Communications External Comments/Messages",
        "needs_reply" if actions else "clear",
        f"Communications has {len(state['communications'])} inbox message(s).",
        "Track external comments and suggested replies locally.",
        {"messages": len(state["communications"]), "needs_reply": len(actions)},
        updates or ["Communications has no messages yet."],
        actions,
    )


def build_vibes_view(state: Dict[str, Any]) -> Dict[str, Any]:
    updates = [
        f"{text(item.get('asset_id'))}: {text(item.get('asset_type'))} for {text(item.get('target_marketplace'))} is {text(item.get('status'))}."
        for item in state["vibes"][-8:]
    ]
    return simple_view(
        "Vibes Creative Assets",
        "working" if state["vibes"] else "waiting",
        "Vibes tracks local-safe creative briefs for game assets, thumbnails, music, beats, and video backgrounds.",
        "Hold creative asset placeholders until a safe local or approved generation path exists.",
        {"creative_assets": len(state["vibes"])},
        updates or ["No creative asset jobs yet. No real music, image, or video APIs were called."],
        [text(item.get("asset_id")) for item in state["vibes"] if text(item.get("status"), "").lower() in ("blocked", "needs_approval")],
    )


def build_media_view(state: Dict[str, Any]) -> Dict[str, Any]:
    updates = [
        f"{text(item.get('upload_job_id'))}: {text(item.get('target_platform'))} upload is {text(item.get('upload_status'))}; live upload allowed: {bool(item.get('live_upload_allowed'))}."
        for item in state["media"][-8:]
    ]
    actions = [text(item.get("upload_job_id")) for item in state["media"] if item.get("blocked_reasons")]
    return simple_view(
        "Media TikTok/YouTube Packaging",
        "blocked" if actions else ("packaging" if state["media"] else "waiting"),
        "Media tracks video, thumbnail, music, title, and description packaging without real uploads.",
        "Package upload jobs only; live upload stays locked unless explicitly allowed.",
        {"upload_jobs": len(state["media"]), "blocked": len(actions)},
        updates or ["No media upload jobs yet. No real uploads were attempted."],
        actions,
    )


def build_archives_view(state: Dict[str, Any]) -> Dict[str, Any]:
    artifact_index = state["artifact_index"] if isinstance(state["artifact_index"], dict) else {}
    artifacts = artifact_index.get("artifacts") if isinstance(artifact_index.get("artifacts"), dict) else {}
    chains = artifact_index.get("chains") if isinstance(artifact_index.get("chains"), list) else []
    return simple_view(
        "Archives Memory/Backups/State History",
        "secured" if state["backups"] else "waiting",
        f"Archives has {len(state['backups'])} backup report(s), {len(state['doctor'])} state doctor report(s), and {len(artifacts)} indexed artifact(s).",
        "Keep memory, backups, state history, and artifact chains available.",
        {"backup_reports": len(state["backups"]), "state_doctor_reports": len(state["doctor"]), "artifacts": len(artifacts), "chains": len(chains)},
        [
            f"Latest backup: {text((latest(state['backups']) or {}).get('id'), 'none')}.",
            f"Latest state doctor: {text((latest(state['doctor']) or {}).get('id'), 'none')}.",
        ],
        [],
    )


def build_armory_view(state: Dict[str, Any]) -> Dict[str, Any]:
    updates = [
        f"{text(item.get('upgrade_id'))}: {text(item.get('upgrade_title'))} for {text(item.get('agent'))} is {text(item.get('status'))}. Reason: {text(item.get('reason'))}."
        for item in state["armory"][-8:]
    ]
    actions = [text(item.get("upgrade_id")) for item in state["armory"] if text(item.get("status"), "").lower() in ("needed", "blocked")]
    return simple_view(
        "Armory Agent Upgrades",
        "needs_work" if actions else "ready",
        "Armory tracks transcript-layer upgrades made, needed, or blocked.",
        "Record future agent upgrades without replacing the backbone.",
        {"upgrade_records": len(state["armory"]), "needed_or_blocked": len(actions)},
        updates or ["Armory has no upgrade records yet."],
        actions,
    )


def build_transcript_agent_views(state: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    state = state or load_state()
    return {
        "ultron": build_ultron_view(state),
        "nova": build_nova_view(state),
        "forge": build_forge_view(state),
        "communications": build_communications_view(state),
        "treasury": build_treasury_view(state),
        "scribe": build_scribe_view(state),
        "media": build_media_view(state),
        "vibes": build_vibes_view(state),
        "sentinel": build_sentinel_view(state),
        "publisher": build_publisher_view(state),
        "archives": build_archives_view(state),
        "armory": build_armory_view(state),
    }


def build_handoff_map() -> Dict[str, Any]:
    return {
        "version": "V10",
        "generated_at": now_stamp(),
        "purpose": "Map existing SpaceCommand backbone state into transcript agent role tabs without replacing pipelines.",
        "tabs": {
            tab: {
                "sources": STATE_SOURCES[tab],
                "writes": ["transcript_agent_views.json"],
            }
            for tab in TRANSCRIPT_TABS
        },
        "role_map": {
            "Ultron": "overseer summary",
            "Nova": "research",
            "Forge": "product/image factory",
            "Sentinel": "QA",
            "Treasury": "cost/profit control",
            "Scribe": "listing/SEO",
            "Publisher": "publishing packages",
            "Communications": "external comments/messages",
            "Vibes": "creative assets/music/thumbnails/game assets",
            "Media": "TikTok/YouTube upload packaging",
            "Armory": "agent upgrades made/needed",
            "Archives": "memory/backups/state history",
        },
    }


def build_ultron_plain_summary(views: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ultron = views["ultron"]
    return {
        "version": "V10",
        "generated_at": now_stamp(),
        "title": ultron["title"],
        "status": ultron["status"],
        "summary": ultron["summary"],
        "next_best_action": ultron["current_job"],
        "needs_user_action": ultron["needs_user_action"],
        "plain_updates": ultron["plain_updates"],
        "source": "transcript_alignment_adapter",
    }


def run_alignment() -> Dict[str, Any]:
    ensured = ensure_optional_state_files()
    state = load_state()
    views = build_transcript_agent_views(state)
    handoff_map = build_handoff_map()
    ultron_summary = build_ultron_plain_summary(views)

    save_json("transcript_handoff_map.json", handoff_map)
    save_json("transcript_agent_views.json", views)
    save_json("ultron_plain_summary.json", ultron_summary)

    return {
        "generated_at": now_stamp(),
        "ensured_optional_files": ensured,
        "updated_files": [
            "transcript_handoff_map.json",
            "transcript_agent_views.json",
            "ultron_plain_summary.json",
        ],
        "tabs": list(views.keys()),
        "status": views["ultron"]["status"],
        "needs_user_action": len(views["ultron"]["needs_user_action"]),
    }
