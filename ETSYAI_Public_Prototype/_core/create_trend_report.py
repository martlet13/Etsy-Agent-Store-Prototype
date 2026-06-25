import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
CORE = ROOT / "_core"
STATE = ROOT / "_spacecommand_state"
NOVA = ROOT / "01_ResearchLab"

TREND_REPORTS_JSON = STATE / "trend_reports.json"
TREND_SOURCES_JSON = STATE / "trend_sources.json"
NOVA_RUNNER = CORE / "run_nova.py"


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_json(path, fallback):
    if not path.exists():
        return fallback

    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()

    if not text:
        return fallback

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_files():
    STATE.mkdir(parents=True, exist_ok=True)
    (NOVA / "trend_reports").mkdir(parents=True, exist_ok=True)

    if not TREND_REPORTS_JSON.exists():
        save_json(TREND_REPORTS_JSON, [])

    if not TREND_SOURCES_JSON.exists():
        save_json(
            TREND_SOURCES_JSON,
            {
                "daily_sources": [
                    {
                        "name": "Manual Etsy observation",
                        "access_type": "manual_observation",
                        "cadence": "daily",
                        "purpose": "Only actual user-provided observations, screenshots, exports, or copied marketplace findings count as evidence.",
                        "approval_required_for_live_access": False,
                    }
                ],
                "weekly_sources": [
                    {
                        "name": "Public Etsy Seller Handbook trend reports",
                        "access_type": "public_or_manual",
                        "cadence": "weekly",
                        "purpose": "Seasonal marketplace direction when actually provided, pasted, or fetched by an approved tool.",
                        "approval_required_for_live_access": False,
                    },
                    {
                        "name": "Printify/Printful public product guidance",
                        "access_type": "public_or_manual",
                        "cadence": "weekly",
                        "purpose": "POD product-format fit when actually provided, pasted, or fetched by an approved tool.",
                        "approval_required_for_live_access": False,
                    },
                ],
                "monthly_sources": [
                    {
                        "name": "Monthly local trend synthesis",
                        "access_type": "local_synthesis",
                        "cadence": "monthly",
                        "purpose": "Compare real saved evidence to decide what to scale, pause, or kill.",
                        "approval_required_for_live_access": False,
                    }
                ],
            },
        )


def detect_evidence_mode(notes):
    lower = (notes or "").lower()

    # Negative phrases win first.
    # This prevents "no export provided yet" from being read as "export provided".
    hard_missing_patterns = [
        "no live",
        "no live etsy",
        "no etsy",
        "no erank",
        "no everbee",
        "no export",
        "no exports",
        "no data",
        "no evidence",
        "not provided",
        "provided yet",
        "no live etsy or erank export provided yet",
        "mark evidence_missing",
        "evidence_missing",
    ]

    for pattern in hard_missing_patterns:
        if pattern in lower:
            return "evidence_missing"

    # Only exact phrases like these count as actual evidence.
    hard_provided_patterns = [
        "screenshot attached",
        "screenshots attached",
        "screenshot provided",
        "screenshots provided",
        "csv attached",
        "csv provided",
        "export attached",
        "export file attached",
        "keyword volume:",
        "sales number:",
        "favorites:",
        "cart count:",
        "bestseller badge:",
        "etsy search result copied:",
        "erank report attached",
        "everbee report attached",
        "printify cost provided",
        "printful cost provided",
        "google trends data provided",
    ]

    for pattern in hard_provided_patterns:
        if pattern in lower:
            return "evidence_provided"

    return "evidence_missing"


def build_prompt(window, theme, notes, sources, evidence_mode):
    return f"""
Create a Nova Trend Intelligence Report.

Evidence mode:
{evidence_mode}

Time window:
{window}

Theme/product area:
{theme}

User notes:
{notes}

Known trend source registry:
{json.dumps(sources, indent=2)}

Critical rules:
- A user instruction is not evidence.
- A theme request is not evidence.
- A business goal is not evidence.
- If evidence mode is evidence_missing, every opportunity is a hypothesis only.
- If evidence mode is evidence_missing, confidence must be Low.
- If evidence mode is evidence_missing, do not claim demand, popularity, best-selling status, current sales, or trend validation.
- Do not recommend developing, pricing, publishing, listing, or producing products until trend evidence and Ledger costs exist.
- Do not write a Sentinel verdict.
- Do not browse, scrape, log in, upload, publish, buy, sell, message, or create listings.
- Do not copy TV shows, movie names, character names, logos, quotes, celebrities, brands, sports teams, or protected phrases.
- Convert TV/movie/fandom-adjacent ideas into safe original genre/aesthetic lanes.

Required Ledger fields:
- likely_supplier: Printify / Printful / Gelato / MANUAL
- product_type: poster / shirt / mug / sticker / hoodie / tote / other
- variant: cost_data_missing unless verified
- production_cost: cost_data_missing unless verified
- shipping_cost_us: cost_data_missing unless verified
- verified_supplier_cost: false unless verified
- verified_shipping_cost: false unless verified

Required output:

# Nova Trend Intelligence Report

## Evidence Mode
{evidence_mode}

## Time Window
{window}

## Theme
{theme}

## Evidence Summary
State whether evidence exists. If missing, say this is hypothesis-only.

## Design Lane Hypotheses
For each:
- product_category
- design_lane
- design_style
- emotional_angle
- buyer_moment
- seasonal_timing
- product_fit
- copyright_trademark_risk
- original_safe_angle
- examples_of_safe_original_phrasing
- evidence_status
- confidence
- recommended_action

## Ledger Notes
Use exact fields:
- likely_supplier
- product_type
- variant
- production_cost
- shipping_cost_us
- verified_supplier_cost
- verified_shipping_cost

## Sentinel Review Notes
List what Sentinel should review later. Do not give a verdict.
""".strip()


def sanitize_missing_evidence_report(output, evidence_mode):
    if evidence_mode != "evidence_missing":
        return output

    text = output or ""

    # Force evidence mode label.
    text = re.sub(
        r"Evidence Mode:\s*(mixed_or_unclear|evidence_provided)",
        "Evidence Mode: evidence_missing",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"## Evidence Mode\s*\n\s*(mixed_or_unclear|evidence_provided)",
        "## Evidence Mode\nEvidence Mode: evidence_missing",
        text,
        flags=re.IGNORECASE,
    )

    # Remove fake Sentinel verdicts.
    text = re.sub(
        r"\*\*?Sentinel Review:?\*\*?\s*\n?\s*(APPROVED|NEEDS_REVISION|REJECTED|REQUIRES_HUMAN_APPROVAL)",
        "Sentinel Review Notes: Pending real Sentinel review.",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(APPROVED|NEEDS_REVISION|REJECTED|REQUIRES_HUMAN_APPROVAL)\b",
        "Pending real Sentinel review",
        text,
    )

    replacements = {
        "popular time": "hypothesis-only seasonal window",
        "popular": "hypothesis-only",
        "growing interest": "unverified possible interest",
        "strong demand": "unverified possible demand",
        "high demand": "unverified possible demand",
        "significant potential market": "unverified possible market",
        "potential market": "unverified possible market",
        "high-potential": "hypothesis-only",
        "current trends": "unverified seasonal assumptions",
        "currently relevant": "possibly relevant but unverified",
        "trend includes": "hypothesis may include",
        "possibly suited for": "possibly suited for",
        "Why it could work": "Hypothesis for why it might work",
        "Develop and price": "Collect real trend evidence and verified Ledger costs before developing or pricing",
        "develop and price": "collect real trend evidence and verified Ledger costs before developing or pricing",
        "Create and publish": "Do not create or publish yet; collect real trend evidence and verified Ledger costs first",
        "create and publish": "do not create or publish yet; collect real trend evidence and verified Ledger costs first",
        "Recommended Action: Develop": "Recommended Action: collect real trend evidence before production; hypothesis only:",
        "Recommended Action:** Develop": "Recommended Action:** collect real trend evidence before production; hypothesis only:",
        "Safe next step: Convert": "Safe next step: collect real trend evidence first, then convert",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Force confidence down.
    text = re.sub(r"Confidence:\s*High", "Confidence: Low", text, flags=re.IGNORECASE)
    text = re.sub(r"Confidence:\s*Medium", "Confidence: Low", text, flags=re.IGNORECASE)
    text = re.sub(r"Confidence:\s*Medium-Low", "Confidence: Low", text, flags=re.IGNORECASE)
    text = re.sub(r"confidence:\s*High", "confidence: Low", text, flags=re.IGNORECASE)
    text = re.sub(r"confidence:\s*Medium", "confidence: Low", text, flags=re.IGNORECASE)
    text = re.sub(r"confidence:\s*Medium-Low", "confidence: Low", text, flags=re.IGNORECASE)

    # Force evidence wording.
    text = re.sub(
        r"evidence_status:\s*manually observed",
        "evidence_status: evidence_missing",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"evidence status:\s*manually observed",
        "evidence status: evidence_missing",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"Evidence:\s*User-provided observations[^\n]*",
        "Evidence: evidence_missing; no real trend export, screenshot, or marketplace data provided.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"Evidence:\s*Hypothesis based on[^\n]*",
        "Evidence: evidence_missing; hypothesis only.",
        text,
        flags=re.IGNORECASE,
    )

    # Force a deterministic Ledger correction to appear at the end.
    correction = """
## Deterministic Ledger Correction

- likely_supplier: Printify / Printful / Gelato / MANUAL
- product_type: poster / shirt / mug / sticker / hoodie / tote / other
- variant: cost_data_missing
- production_cost: cost_data_missing
- shipping_cost_us: cost_data_missing
- verified_supplier_cost: false
- verified_shipping_cost: false
"""

    if "## Deterministic Ledger Correction" not in text:
        text += "\n\n" + correction.strip() + "\n"

    prefix = """# Deterministic Evidence Correction

Evidence Mode: evidence_missing

This report is hypothesis-only. No live Etsy, eRank, EverBee, marketplace export, screenshot, keyword-volume report, or verified sales evidence was provided. Do not treat any design lane below as validated demand. Do not move to production, listing drafts, pricing, publishing, or store actions until real trend evidence and verified Ledger supplier/shipping costs are collected.

---

"""

    if "Deterministic Evidence Correction" not in text:
        text = prefix + text

    return text


def run_nova_trend_report(window, theme, notes):
    ensure_files()

    if not NOVA_RUNNER.exists():
        return {
            "success": False,
            "exit_code": 1,
            "output": f"Nova runner not found: {NOVA_RUNNER}",
            "evidence_mode": "error",
        }

    sources = load_json(TREND_SOURCES_JSON, {})
    evidence_mode = detect_evidence_mode(notes)
    prompt = build_prompt(window, theme, notes, sources, evidence_mode)

    result = subprocess.run(
        [
            "python",
            str(NOVA_RUNNER),
            prompt,
            "--save-brief",
            "--title",
            f"{window.capitalize()} Trend Report {theme}",
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\n\n[stderr]\n" + result.stderr

    # Force missing mode again after model call based on original notes.
    evidence_mode = detect_evidence_mode(notes)
    output = sanitize_missing_evidence_report(output.strip(), evidence_mode)

    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output,
        "evidence_mode": evidence_mode,
    }


def main():
    parser = argparse.ArgumentParser(description="Create a Nova trend intelligence report.")
    parser.add_argument("--window", choices=["daily", "weekly", "monthly"], required=True)
    parser.add_argument("--theme", default="general POD products")
    parser.add_argument(
        "--notes",
        default="No user-provided notes. Evidence is missing unless supported by stored local sources.",
    )
    args = parser.parse_args()

    ensure_files()

    result = run_nova_trend_report(args.window, args.theme, args.notes)

    reports = load_json(TREND_REPORTS_JSON, [])
    report_id = f"TREND-{len(reports) + 1:04d}"

    record = {
        "id": report_id,
        "window": args.window,
        "theme": args.theme,
        "notes": args.notes,
        "evidence_mode": result.get("evidence_mode"),
        "created_at": now_stamp(),
        "success": result["success"],
        "exit_code": result["exit_code"],
        "output": result["output"],
    }

    reports.append(record)
    save_json(TREND_REPORTS_JSON, reports)

    report_dir = NOVA / "trend_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    safe_theme = "".join(c for c in args.theme if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_theme = safe_theme.replace(" ", "_")[:50] or "trend"

    report_path = report_dir / f"{file_stamp()}_{report_id}_{args.window}_{safe_theme}.md"
    report_path.write_text(result["output"], encoding="utf-8")

    print()
    print("# Nova Trend Report Created")
    print()
    print(f"Report ID: {report_id}")
    print(f"Window: {args.window}")
    print(f"Theme: {args.theme}")
    print(f"Evidence Mode: {result.get('evidence_mode')}")
    print(f"Success: {result['success']}")
    print(f"Saved: {report_path}")
    print()
    print(result["output"])


if __name__ == "__main__":
    main()

