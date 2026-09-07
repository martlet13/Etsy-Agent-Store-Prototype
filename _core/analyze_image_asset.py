import argparse

from curator_image_kernel import analyze_image_asset


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Curator: analyze an image asset's sharpness/noise/contrast, check its DPI fit "
            "against common Etsy print sizes, and scan its borders for a likely watermark/"
            "citation-banner/scan-margin step so it can be cropped out. Read-only — never "
            "writes or modifies the image itself."
        )
    )
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--print-formats", default="4x6,5x7,8x10,11x14,16x20,18x24,12x12",
                         help="Comma list of sizes to check DPI fit against. See PRINT_FORMATS in curator_image_kernel.py.")

    args = parser.parse_args()

    report = analyze_image_asset(args.image_asset_id, print_formats=csv_list(args.print_formats))

    print()
    print("# Curator Image Analysis")
    print()
    print(f"ID: {report.get('id')}")
    print(f"Status: {report.get('status')}")
    print(f"Image Asset: {report.get('image_asset_id')}")

    if report.get("issues"):
        print(f"Issues: {', '.join(report['issues'])}")
        print()
        return

    print(f"Dimensions: {report['width']}x{report['height']} ({report['megapixels']} MP, ratio {report['aspect_ratio']})")
    print(f"File size: {report['file_size_bytes']:,} bytes")
    print()
    print("## Quality Signals")
    print(f"Sharpness score: {report['sharpness_score']} (higher = crisper edges)")
    print(f"Noise score: {report['noise_score']} (lower = cleaner)")
    print(f"Mean brightness: {report['mean_brightness']} / Contrast stddev: {report['contrast_stddev']}")
    print(f"Warnings: {', '.join(report['quality_warnings']) or 'none'}")

    print()
    print("## Print-Size DPI Fit")
    for name, fit in report["dpi_fit"].items():
        flag = "OK" if fit["meets_recommended_dpi"] else ("LOW" if fit["meets_minimum_dpi"] else "TOO LOW")
        print(f"  {name} ({fit['target_inches']}in): {fit['effective_dpi']} dpi [{flag}]")

    print()
    print("## Border/Watermark Crop Suggestion")
    crop = report["crop_suggestion"]
    if crop["any_side_flagged"]:
        print(f"Suggested crop box (left, top, right, bottom): {crop['crop_box']}")
        for side, finding in crop["sides_flagged"].items():
            if finding:
                print(f"  - {side}: cut {finding['cut_px_from_edge']}px (prominence {finding['prominence']})")
        print()
        print("Review this before applying — it's a suggestion, not an automatic crop.")
        print("Apply it with: enhance_image_asset.py --image-asset-id "
              f"{args.image_asset_id} --crop auto")
    else:
        print("No confident border step found — no crop suggested.")

    print()


if __name__ == "__main__":
    main()
