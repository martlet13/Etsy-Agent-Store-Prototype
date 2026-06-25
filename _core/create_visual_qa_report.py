import argparse

from sentinel_visual_qa import create_visual_qa_report, csv_list


def main():
    parser = argparse.ArgumentParser(description="Create Sentinel Visual QA report for a Forge image asset.")
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--reviewer", default="Sentinel")
    parser.add_argument("--passed-checks", default="")
    parser.add_argument("--failed-checks", default="")
    parser.add_argument("--warning-flags", default="")
    parser.add_argument("--prompt-match-score", type=int, required=True)
    parser.add_argument("--product-readiness-score", type=int, required=True)
    parser.add_argument("--qa-notes", default="")

    args = parser.parse_args()

    report = create_visual_qa_report(
        image_asset_id=args.image_asset_id,
        reviewer=args.reviewer,
        passed_checks=csv_list(args.passed_checks),
        failed_checks=csv_list(args.failed_checks),
        warning_flags=csv_list(args.warning_flags),
        prompt_match_score=args.prompt_match_score,
        product_readiness_score=args.product_readiness_score,
        qa_notes=args.qa_notes,
    )

    print()
    print("# Sentinel Visual QA Report Created")
    print()
    print(f"ID: {report['id']}")
    print(f"Status: {report['status']}")
    print(f"Image Asset: {report.get('image_asset_id')}")
    print(f"Prompt Match Score: {report.get('prompt_match_score')}")
    print(f"Product Readiness Score: {report.get('product_readiness_score')}")
    print(f"Approved For Mockup: {report.get('approved_for_mockup')}")
    print(f"Approved For Product: {report.get('approved_for_product')}")
    print(f"Issues: {', '.join(report.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(report.get('warnings', [])) or 'none'}")
    print()


if __name__ == "__main__":
    main()
