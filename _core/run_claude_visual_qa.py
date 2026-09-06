import argparse

from claude_visual_qa import (
    finalize_autonomous,
    finalize_with_client_confirmation,
    propose_claude_visual_qa,
)


def print_proposal(result):
    proposal = result["proposal"]
    print()
    print("# Claude Visual QA Proposal")
    print()
    print(f"Image Asset: {result['image_asset_id']}")
    print(f"File: {result['file_path']}")
    print(f"Model: {result['model']}")
    print()
    print(f"Prompt Match Score: {proposal['prompt_match_score']}")
    print(f"Product Readiness Score: {proposal['product_readiness_score']}")
    print(f"Passed Checks: {', '.join(proposal['passed_checks']) or 'none'}")
    print(f"Failed Checks: {', '.join(proposal['failed_checks']) or 'none'}")
    print(f"Warning Flags: {', '.join(proposal['warning_flags']) or 'none'}")
    print()
    print("QA Notes:")
    print(proposal["qa_notes"])
    print()


def print_report(report):
    print("# Visual QA Report Written")
    print()
    print(f"ID: {report['id']}")
    print(f"Status: {report['status']}")
    print(f"Reviewer: {report.get('reviewer')}")
    print(f"Approved For Mockup: {report.get('approved_for_mockup')}")
    print(f"Approved For Product: {report.get('approved_for_product')}")
    print(f"Issues: {', '.join(report.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(report.get('warnings', [])) or 'none'}")
    print()


def prompt_edit(proposal: dict) -> dict:
    """Let the human tweak any field before it's written. Blank = keep as-is."""
    print("Press Enter to keep Claude's value for each field, or type a new one.")
    print()

    def edit_str(label, current):
        raw = input(f"{label} [{current}]: ").strip()
        return raw if raw else current

    def edit_csv(label, current):
        raw = input(f"{label} (comma-separated) [{', '.join(current)}]: ").strip()
        if not raw:
            return current
        return [x.strip() for x in raw.split(",") if x.strip()]

    def edit_int(label, current):
        raw = input(f"{label} [{current}]: ").strip()
        if not raw:
            return current
        try:
            return int(raw)
        except ValueError:
            print("Not a number, keeping original value.")
            return current

    edited = dict(proposal)
    edited["failed_checks"] = edit_csv("Failed checks", proposal["failed_checks"])
    edited["warning_flags"] = edit_csv("Warning flags", proposal["warning_flags"])
    edited["prompt_match_score"] = edit_int("Prompt match score", proposal["prompt_match_score"])
    edited["product_readiness_score"] = edit_int("Product readiness score", proposal["product_readiness_score"])
    edited["qa_notes"] = edit_str("QA notes", proposal["qa_notes"])
    return edited


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Use Claude (vision) as a Sentinel Visual QA reviewer for a generated image asset. "
            "Claude only proposes a review — it never writes a report by itself. You choose how "
            "that proposal gets finalized: autonomous (no human step, requires an explicit accept "
            "flag) or client-confirmed (interactive terminal confirmation, editable before it's written)."
        )
    )
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--claude-model", default=None)
    parser.add_argument(
        "--mode",
        choices=["propose", "autonomous", "client_confirm"],
        default="propose",
        help=(
            "propose: print Claude's assessment, write nothing (default, safe to script). "
            "autonomous: write immediately with no human step (requires --i-accept-autonomous-visual-qa). "
            "client_confirm: show the proposal, let you edit it, then ask for a typed YES before writing."
        ),
    )
    parser.add_argument(
        "--i-accept-autonomous-visual-qa",
        action="store_true",
        dest="accepted_autonomous",
        help="Required for --mode autonomous. Explicit acknowledgement that no human will review this asset.",
    )

    args = parser.parse_args()

    try:
        result = propose_claude_visual_qa(args.image_asset_id, claude_model=args.claude_model)
    except RuntimeError as exc:
        print()
        print("# Claude Visual QA Failed")
        print()
        print(str(exc))
        print()
        return

    print_proposal(result)

    if args.mode == "propose":
        print("Mode is 'propose' — nothing was written. Re-run with --mode autonomous or --mode client_confirm to finalize.")
        print()
        return

    if args.mode == "autonomous":
        if not args.accepted_autonomous:
            print("Blocked: --mode autonomous requires --i-accept-autonomous-visual-qa.")
            print()
            return
        report = finalize_autonomous(args.image_asset_id, result["proposal"], accepted_autonomous_review=True)
        print_report(report)
        return

    # client_confirm
    edit_choice = input("Edit any field before confirming? [y/N]: ").strip().lower()
    proposal = prompt_edit(result["proposal"]) if edit_choice == "y" else result["proposal"]

    print()
    confirm = input("Write this as the Visual QA report? Type YES to confirm: ").strip()
    if confirm != "YES":
        print()
        print("Not confirmed. Nothing was written.")
        print()
        return

    report = finalize_with_client_confirmation(args.image_asset_id, proposal, confirmed=True)
    print_report(report)


if __name__ == "__main__":
    main()
