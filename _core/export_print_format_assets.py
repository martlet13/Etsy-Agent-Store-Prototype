import argparse

from curator_image_kernel import PRINT_FORMATS, export_print_format_assets


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_rgb(raw):
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("--mat-color must be 3 comma-separated 0-255 values: R,G,B")
    return tuple(int(p) for p in parts)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Curator: export exact-pixel print-size crops (e.g. 8x10, 11x14, 16x20) at a target "
            f"DPI from an image asset. Known formats: {', '.join(PRINT_FORMATS)}. Each exported "
            "size is recorded as its OWN new image_asset, needing its own Sentinel Visual QA — "
            "these are print-ready master candidates, not previews."
        )
    )
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--formats", required=True, help="Comma list, e.g. '8x10,11x14,16x20'.")
    parser.add_argument("--dpi", type=int, default=300, help="Target DPI. Etsy print-on-demand suppliers typically want 300; 150 is a hard minimum for anything readable up close.")
    parser.add_argument("--fill-mode", choices=["crop", "pad"], default="crop",
                         help="'crop' fills the frame exactly (loses some edge content if aspect ratios differ). "
                              "'pad' keeps the whole image and adds a mat-color border instead.")
    parser.add_argument("--mat-color", type=parse_rgb, default=(255, 255, 255), help="R,G,B for --fill-mode pad's border. Default white.")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    result = export_print_format_assets(
        image_asset_id=args.image_asset_id,
        format_names=csv_list(args.formats),
        dpi=args.dpi,
        fill_mode=args.fill_mode,
        mat_color=args.mat_color,
        notes=args.notes,
    )

    print()
    print("# Curator Print-Format Export")
    print()
    print(f"Status: {result.get('status')}")
    print(f"Image Asset: {result.get('image_asset_id')}")

    if result.get("issues"):
        print(f"Issues: {', '.join(result['issues'])}")
        print()
        return

    if result.get("warnings"):
        print(f"Warnings: {', '.join(result['warnings'])}")

    print()
    print("## Exported Assets")
    for asset in result.get("assets", []):
        flag = " (needs_upscale — see notes)" if asset.get("needs_upscale") else ""
        print(f"  - {asset['id']}: {asset.get('print_format')} -> {asset.get('output_width')}x{asset.get('output_height')}px{flag}")
        print(f"    {asset.get('file_path')}")

    print()
    print("Next: run Sentinel Visual QA on each of these before using it as a print-ready master.")
    print()


if __name__ == "__main__":
    main()
