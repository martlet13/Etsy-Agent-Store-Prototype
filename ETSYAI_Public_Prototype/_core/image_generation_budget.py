import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

IMAGE_API_BUDGET_FILE = STATE / "image_api_budget.json"
IMAGE_GENERATION_RUNS_FILE = STATE / "image_generation_runs.json"
IMAGE_REQUESTS_FILE = STATE / "image_generation_requests.json"
IMAGE_ASSETS_FILE = STATE / "image_assets.json"
DESIGN_FILE = STATE / "design_packages.json"
OPPORTUNITY_FILE = STATE / "opportunity_cards.json"
EVIDENCE_FILE = STATE / "evidence_cards.json"


STRENGTH_RANK = {
    "missing": 0,
    "hypothesis": 1,
    "weak": 2,
    "provided": 3,
    "verified": 4,
}


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_stamp(value: str) -> Optional[datetime]:
    if not value:
        return None

    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ]:
        try:
            return datetime.strptime(str(value), fmt)
        except Exception:
            pass

    return None


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


def find_by_id(records: List[Dict[str, Any]], record_id: str) -> Optional[Dict[str, Any]]:
    for record in records:
        if record.get("id") == record_id:
            return record

    return None


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def previous_month(dt: datetime) -> datetime:
    first = dt.replace(day=1)
    return first - timedelta(days=1)


def classify_candidate_window(evidence: Dict[str, Any], now: datetime) -> str:
    created = parse_stamp(evidence.get("created_at")) or now
    time_window = str(evidence.get("time_window", "")).lower()

    current_month = month_key(now)
    prev_month = month_key(previous_month(now))

    current_week = week_key(now)
    prev_week = week_key(now - timedelta(days=7))

    evidence_month = month_key(created)
    evidence_week = week_key(created)

    if time_window == "monthly":
        if evidence_month == current_month:
            return "current_month"
        if evidence_month == prev_month:
            return "previous_month"
        return "old_month"

    if time_window == "weekly":
        if evidence_week == current_week:
            return "current_week"
        if evidence_week == prev_week:
            return "previous_week"
        return "old_week"

    if time_window == "daily":
        if evidence_week == current_week:
            return "current_week"
        if evidence_week == prev_week:
            return "previous_week"
        return "old_week"

    return "unknown"


def candidate_bucket(candidate_window: str) -> str:
    if candidate_window in {"current_month", "previous_month"}:
        return "monthly_trend"

    if candidate_window in {"current_week", "previous_week"}:
        return "weekly_trend"

    return "unknown"


def successful_generation_runs(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        run for run in runs
        if run.get("counts_against_budget", False)
        and run.get("status") in {
            "generated_asset_recorded",
            "manual_generated_asset_recorded",
            "live_generation_completed",
        }
    ]


def count_current_month_runs(runs: List[Dict[str, Any]], now: datetime) -> int:
    key = month_key(now)
    count = 0

    for run in successful_generation_runs(runs):
        created = parse_stamp(run.get("created_at"))

        if created and month_key(created) == key:
            count += 1

    return count


def count_current_month_bucket_runs(runs: List[Dict[str, Any]], now: datetime, bucket: str) -> int:
    key = month_key(now)
    count = 0

    for run in successful_generation_runs(runs):
        created = parse_stamp(run.get("created_at"))

        if created and month_key(created) == key and run.get("candidate_bucket") == bucket:
            count += 1

    return count


def count_current_week_bucket_runs(runs: List[Dict[str, Any]], now: datetime, bucket: str) -> int:
    key = week_key(now)
    count = 0

    for run in successful_generation_runs(runs):
        created = parse_stamp(run.get("created_at"))

        if created and week_key(created) == key and run.get("candidate_bucket") == bucket:
            count += 1

    return count


def image_request_already_has_successful_run(image_request_id: str, runs: List[Dict[str, Any]]) -> bool:
    for run in successful_generation_runs(runs):
        if run.get("image_request_id") == image_request_id:
            return True

    return False


def build_request_context(image_request_id: str) -> Dict[str, Any]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    designs = load_json(DESIGN_FILE, [])
    opportunities = load_json(OPPORTUNITY_FILE, [])
    evidence_cards = load_json(EVIDENCE_FILE, [])

    request = find_by_id(requests, image_request_id)

    if not request:
        return {
            "request": None,
            "design": None,
            "opportunity": None,
            "evidence": [],
        }

    design = find_by_id(designs, request.get("design_package_id", ""))
    opportunity = None
    evidence = []

    if design:
        opportunity = find_by_id(opportunities, design.get("opportunity_id", ""))

    if opportunity:
        evidence_ids = opportunity.get("source_evidence_ids", [])
        for evidence_id in evidence_ids:
            card = find_by_id(evidence_cards, evidence_id)
            if card:
                evidence.append(card)

    return {
        "request": request,
        "design": design,
        "opportunity": opportunity,
        "evidence": evidence,
    }


def strongest_evidence_strength(evidence_cards: List[Dict[str, Any]]) -> str:
    best = "missing"
    best_rank = 0

    for card in evidence_cards:
        strength = str(card.get("evidence_strength", "missing")).lower()
        rank = STRENGTH_RANK.get(strength, 0)

        if rank > best_rank:
            best = strength
            best_rank = rank

    return best


def choose_candidate_window(evidence_cards: List[Dict[str, Any]], now: datetime) -> str:
    ranked = {
        "current_week": 6,
        "previous_week": 5,
        "current_month": 4,
        "previous_month": 3,
        "old_week": 2,
        "old_month": 1,
        "unknown": 0,
    }

    best = "unknown"
    best_score = -1

    for card in evidence_cards:
        window = classify_candidate_window(card, now)
        score = ranked.get(window, 0)

        if score > best_score:
            best = window
            best_score = score

    return best


def find_next_eligible_image_request() -> Optional[Dict[str, Any]]:
    requests = load_json(IMAGE_REQUESTS_FILE, [])
    runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])

    for request in requests:
        request_id = request.get("id")

        if not request_id:
            continue

        if image_request_already_has_successful_run(request_id, runs):
            continue

        decision = evaluate_image_request_budget(request_id)

        if decision.get("eligible_for_generation"):
            return request

    return None


def evaluate_image_request_budget(image_request_id: str) -> Dict[str, Any]:
    now = datetime.now()

    budget = load_json(IMAGE_API_BUDGET_FILE, {})
    runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])

    context = build_request_context(image_request_id)

    request = context["request"]
    design = context["design"]
    opportunity = context["opportunity"]
    evidence = context["evidence"]

    issues = []
    warnings = []

    if not request:
        issues.append("missing_image_request")

    if budget.get("require_design_package", True) and not design:
        issues.append("missing_design_package")

    if budget.get("require_opportunity_card", True) and not opportunity:
        issues.append("missing_opportunity_card")

    if not evidence:
        issues.append("missing_evidence_card")

    if opportunity and opportunity.get("status") == "hypothesis_only":
        issues.append("opportunity_hypothesis_only")

    if request and request.get("status") not in {"ready_manual_generation", "ready_api_generation", "ready_provider_generation"}:
        warnings.append(f"image_request_status:{request.get('status')}")

    strongest = strongest_evidence_strength(evidence)
    minimum = str(budget.get("minimum_evidence_strength", "weak")).lower()

    if STRENGTH_RANK.get(strongest, 0) < STRENGTH_RANK.get(minimum, 2):
        issues.append(f"evidence_strength_below_minimum:{strongest}")

    candidate_window = choose_candidate_window(evidence, now)
    candidate_bucket_name = candidate_bucket(candidate_window)

    if candidate_window not in budget.get("allowed_candidate_windows", []):
        issues.append(f"candidate_window_not_allowed:{candidate_window}")

    monthly_total_count = count_current_month_runs(runs, now)
    monthly_bucket_count = count_current_month_bucket_runs(runs, now, "monthly_trend")
    weekly_bucket_count = count_current_week_bucket_runs(runs, now, "weekly_trend")

    if monthly_total_count >= int(budget.get("monthly_image_cap", 10)):
        issues.append("monthly_image_cap_reached")

    if candidate_bucket_name == "monthly_trend":
        if monthly_bucket_count >= int(budget.get("monthly_trend_image_cap", 5)):
            issues.append("monthly_trend_image_cap_reached")

    elif candidate_bucket_name == "weekly_trend":
        if weekly_bucket_count >= int(budget.get("weekly_trend_image_cap", 1)):
            issues.append("weekly_trend_image_cap_reached")
    else:
        issues.append(f"unknown_candidate_bucket:{candidate_bucket_name}")

    if image_request_already_has_successful_run(image_request_id, runs):
        issues.append("image_request_already_generated")

    live_api_enabled = bool(budget.get("live_api_enabled", False))

    eligible_for_generation = len(issues) == 0
    live_generation_allowed = eligible_for_generation and live_api_enabled

    return {
        "image_request_id": image_request_id,
        "eligible_for_generation": eligible_for_generation,
        "live_generation_allowed": live_generation_allowed,
        "live_api_enabled": live_api_enabled,
        "model": budget.get("model", "gpt-image-2"),
        "provider_id": budget.get("provider_id", "openai_images_gpt_image_2"),
        "candidate_window": candidate_window,
        "candidate_bucket": candidate_bucket_name,
        "strongest_evidence_strength": strongest,
        "monthly_total_count": monthly_total_count,
        "monthly_image_cap": budget.get("monthly_image_cap", 10),
        "monthly_trend_count": monthly_bucket_count,
        "monthly_trend_image_cap": budget.get("monthly_trend_image_cap", 5),
        "weekly_trend_count": weekly_bucket_count,
        "weekly_trend_image_cap": budget.get("weekly_trend_image_cap", 1),
        "per_cycle_image_cap": budget.get("per_cycle_image_cap", 1),
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "context": {
            "design_package_id": design.get("id") if design else None,
            "opportunity_id": opportunity.get("id") if opportunity else None,
            "evidence_ids": [card.get("id") for card in evidence],
            "opportunity_status": opportunity.get("status") if opportunity else None,
            "design_status": design.get("status") if design else None,
        },
    }


def create_generation_run_decision(
    image_request_id: str,
    mode: str = "gate_check",
    result_notes: str = "",
) -> Dict[str, Any]:
    runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])
    decision = evaluate_image_request_budget(image_request_id)

    if decision.get("eligible_for_generation") and not decision.get("live_api_enabled"):
        status = "blocked_live_api_disabled"
    elif decision.get("live_generation_allowed"):
        status = "approved_waiting_for_provider_implementation"
    else:
        status = "blocked_budget_or_eligibility"

    run = {
        "id": next_id("IMGRUN", runs),
        "type": "image_generation_run",
        "status": status,
        "mode": mode,
        "provider_id": decision.get("provider_id"),
        "model": decision.get("model"),
        "image_request_id": image_request_id,
        "candidate_window": decision.get("candidate_window"),
        "candidate_bucket": decision.get("candidate_bucket"),
        "strongest_evidence_strength": decision.get("strongest_evidence_strength"),
        "eligible_for_generation": decision.get("eligible_for_generation"),
        "live_generation_allowed": decision.get("live_generation_allowed"),
        "live_api_enabled": decision.get("live_api_enabled"),
        "counts_against_budget": False,
        "monthly_total_count_before": decision.get("monthly_total_count"),
        "monthly_image_cap": decision.get("monthly_image_cap"),
        "monthly_trend_count_before": decision.get("monthly_trend_count"),
        "monthly_trend_image_cap": decision.get("monthly_trend_image_cap"),
        "weekly_trend_count_before": decision.get("weekly_trend_count"),
        "weekly_trend_image_cap": decision.get("weekly_trend_image_cap"),
        "issues": decision.get("issues", []),
        "warnings": decision.get("warnings", []),
        "context": decision.get("context", {}),
        "result_notes": result_notes,
        "created_at": now_stamp(),
    }

    runs.append(run)
    save_json(IMAGE_GENERATION_RUNS_FILE, runs)

    return run


def audit_image_generation_budget() -> Dict[str, Any]:
    budget = load_json(IMAGE_API_BUDGET_FILE, {})
    runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])
    now = datetime.now()

    findings = []
    warnings = []

    monthly_total_count = count_current_month_runs(runs, now)
    monthly_trend_count = count_current_month_bucket_runs(runs, now, "monthly_trend")
    weekly_trend_count = count_current_week_bucket_runs(runs, now, "weekly_trend")

    if monthly_total_count > int(budget.get("monthly_image_cap", 10)):
        findings.append({
            "severity": "blocker",
            "code": "monthly_image_cap_exceeded",
            "artifact_id": "image_api_budget",
            "message": "Image monthly cap has been exceeded.",
        })

    if monthly_trend_count > int(budget.get("monthly_trend_image_cap", 5)):
        findings.append({
            "severity": "blocker",
            "code": "monthly_trend_image_cap_exceeded",
            "artifact_id": "image_api_budget",
            "message": "Monthly trend image cap has been exceeded.",
        })

    if weekly_trend_count > int(budget.get("weekly_trend_image_cap", 1)):
        findings.append({
            "severity": "blocker",
            "code": "weekly_trend_image_cap_exceeded",
            "artifact_id": "image_api_budget",
            "message": "Weekly trend image cap has been exceeded.",
        })

    for run in runs:
        run_id = run.get("id")

        if run.get("live_generation_allowed", False) and not budget.get("live_api_enabled", False):
            findings.append({
                "severity": "blocker",
                "code": "image_run_live_allowed_while_api_disabled",
                "artifact_id": run_id,
                "message": "Image run claims live generation allowed while API is disabled.",
            })

        if run.get("status") == "blocked_budget_or_eligibility":
            warnings.append({
                "code": "image_generation_blocked",
                "artifact_id": run_id,
                "message": f"Image generation run blocked: {run.get('issues')}",
            })

        if run.get("status") == "blocked_live_api_disabled":
            warnings.append({
                "code": "image_generation_live_api_disabled",
                "artifact_id": run_id,
                "message": "Image request passed eligibility gates but live API is disabled.",
            })

    return {
        "status": "blocked" if findings else "pass",
        "summary": {
            "image_generation_runs": len(runs),
            "monthly_generated_images": monthly_total_count,
            "monthly_image_cap": budget.get("monthly_image_cap", 10),
            "monthly_trend_generated_images": monthly_trend_count,
            "monthly_trend_image_cap": budget.get("monthly_trend_image_cap", 5),
            "weekly_trend_generated_images": weekly_trend_count,
            "weekly_trend_image_cap": budget.get("weekly_trend_image_cap", 1),
            "live_api_enabled": budget.get("live_api_enabled", False),
            "model": budget.get("model", "gpt-image-2"),
            "blockers": len(findings),
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
        "created_at": now_stamp(),
    }
