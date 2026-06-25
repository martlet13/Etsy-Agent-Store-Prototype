import argparse

from image_generation_budget import (
    IMAGE_GENERATION_RUNS_FILE,
    create_generation_run_decision,
    evaluate_image_request_budget,
    find_next_eligible_image_request,
    load_json,
)
from openai_image_provider import generate_openai_image_for_request


def existing_non_counting_gate_run(image_request_id):
    runs = load_json(IMAGE_GENERATION_RUNS_FILE, [])

    for run in reversed(runs):
        if (
            run.get("image_request_id") == image_request_id
            and run.get("status") in {"blocked_live_api_disabled", "blocked_budget_or_eligibility"}
            and not run.get("counts_against_budget", False)
        ):
            return run

    return None


def print_run(run, decision, reused=False):
    print()
    print("# Forge Image Provider Gate")
    print()

    if reused:
        print("Reused Existing Gate Run: True")

    print(f"Run ID: {run['id']}")
    print(f"Status: {run['status']}")
    print(f"Image Request: {run.get('image_request_id')}")
    print(f"Provider: {run.get('provider_id')}")
    print(f"Model: {run.get('model')}")
    print(f"Candidate Window: {run.get('candidate_window')}")
    print(f"Candidate Bucket: {run.get('candidate_bucket')}")
    print(f"Strongest Evidence: {run.get('strongest_evidence_strength')}")
    print(f"Eligible For Generation: {run.get('eligible_for_generation')}")
    print(f"Live API Enabled: {run.get('live_api_enabled')}")
    print(f"Live Generation Allowed: {run.get('live_generation_allowed')}")
    print()

    print("## Caps")
    print(f"Monthly Total: {run.get('monthly_total_count_before')} / {run.get('monthly_image_cap')}")
    print(f"Monthly Trend: {run.get('monthly_trend_count_before')} / {run.get('monthly_trend_image_cap')}")
    print(f"Weekly Trend: {run.get('weekly_trend_count_before')} / {run.get('weekly_trend_image_cap')}")
    print()

    print(f"Issues: {', '.join(run.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(run.get('warnings', [])) or 'none'}")

    if run["status"] == "blocked_live_api_disabled":
        print()
        print("Generation gate passed, but live API is disabled. No image was generated.")

    if run["status"] == "approved_waiting_for_provider_implementation":
        print()
        print("Live generation would be allowed, but live API provider implementation was not run.")

    if decision.get("context"):
        print()
        print("## Context")
        for key, value in decision["context"].items():
            print(f"- {key}: {value}")

    print()


def print_live_result(result):
    run = result.get("run", {})
    asset = result.get("asset")

    print()
    print("# Forge OpenAI Image Provider")
    print()
    print(f"OK: {result.get('ok')}")
    print(f"Message: {result.get('message')}")
    print(f"Run ID: {run.get('id')}")
    print(f"Run Status: {run.get('status')}")
    print(f"Image Request: {run.get('image_request_id')}")
    print(f"Model: {run.get('model')}")
    print(f"Counts Against Budget: {run.get('counts_against_budget')}")
    print(f"Candidate Window: {run.get('candidate_window')}")
    print(f"Candidate Bucket: {run.get('candidate_bucket')}")

    if run.get("openai_status_code"):
        print(f"OpenAI Status Code: {run.get('openai_status_code')}")

    if run.get("openai_error"):
        print()
        print("## OpenAI Error")
        print(run.get("openai_error"))

    if asset:
        print()
        print("## Image Asset Recorded")
        print(f"Asset ID: {asset.get('id')}")
        print(f"Status: {asset.get('status')}")
        print(f"File Path: {asset.get('file_path')}")
        print(f"Approved For Mockup: {asset.get('approved_for_mockup')}")
        print(f"Approved For Product: {asset.get('approved_for_product')}")
        print()
        print("Next: run Sentinel Visual QA before mockup/product/upload.")

    print()


def main():
    parser = argparse.ArgumentParser(description="Run Forge image provider gate or live OpenAI image provider.")
    parser.add_argument("--image-request-id", default="")
    parser.add_argument("--mode", choices=["gate_check", "manual_waiting", "live_api"], default="gate_check")
    parser.add_argument("--notes", default="")
    parser.add_argument("--force-new-run", choices=["true", "false"], default="false")
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], default="high")
    parser.add_argument("--output-format", choices=["png", "webp", "jpeg"], default="png")
    parser.add_argument("--force-live", choices=["true", "false"], default="false")

    args = parser.parse_args()

    image_request_id = args.image_request_id

    if not image_request_id:
        request = find_next_eligible_image_request()

        if not request:
            print()
            print("# Forge Image Provider")
            print()
            print("Status: no_eligible_image_request")
            print("No image request currently passes the monthly/weekly/popularity budget gates.")
            print()
            return

        image_request_id = request["id"]

    if args.mode == "live_api":
        result = generate_openai_image_for_request(
            image_request_id=image_request_id,
            quality=args.quality,
            output_format=args.output_format,
            force_live=args.force_live == "true",
        )
        print_live_result(result)
        return

    decision = evaluate_image_request_budget(image_request_id)

    if args.force_new_run != "true":
        existing = existing_non_counting_gate_run(image_request_id)
        if existing:
            print_run(existing, decision, reused=True)
            return

    run = create_generation_run_decision(
        image_request_id=image_request_id,
        mode=args.mode,
        result_notes=args.notes,
    )

    print_run(run, decision, reused=False)


if __name__ == "__main__":
    main()
