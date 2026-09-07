import argparse

from curator_image_kernel import enhance_image_asset


def parse_crop_box(raw):
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--crop-box must be 4 comma-separated integers: left,top,right,bottom")
    return tuple(int(p) for p in parts)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Curator: produce a quality-enhanced derivative of an image asset (auto-contrast, "
            "unsharp-mask sharpening, optional denoise, optional crop/resize/re-encode). Always "
            "records a NEW image_asset linked back via derived_from_image_asset_id — it does not "
            "modify the original file, and the new asset still needs its own Sentinel Visual QA "
            "before it can be used as a mockup or product image."
        )
    )
    parser.add_argument("--image-asset-id", required=True)

    parser.add_argument("--crop", choices=["none", "auto", "explicit"], default="none",
                         help="'auto' uses the border-step crop suggestion from analyze_image_asset.py; "
                              "'explicit' requires --crop-box.")
    parser.add_argument("--crop-box", type=parse_crop_box, default=None,
                         help="left,top,right,bottom in pixels. Required if --crop explicit.")

    parser.add_argument("--sharpen", dest="sharpen", action="store_true", default=True)
    parser.add_argument("--no-sharpen", dest="sharpen", action="store_false")
    parser.add_argument("--auto-contrast", dest="auto_contrast", action="store_true", default=True)
    parser.add_argument("--no-auto-contrast", dest="auto_contrast", action="store_false")
    parser.add_argument("--denoise", dest="denoise", action="store_true", default=False,
                         help="Median-filter denoise. Off by default — it softens fine detail, so only use it on visibly noisy scans.")

    parser.add_argument("--target-long-edge-px", type=int, default=None,
                         help="Resize so the longer edge is exactly this many pixels (up or down). Omit to keep native resolution.")
    parser.add_argument("--format", dest="output_format", choices=["jpg", "jpeg", "png", "webp"], default=None,
                         help="Defaults to the source file's own extension.")
    parser.add_argument("--quality", type=int, default=95, help="JPEG/WEBP quality, 1-100.")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    if args.crop == "explicit" and not args.crop_box:
        print()
        print("# Curator Enhance Blocked")
        print()
        print("--crop explicit requires --crop-box left,top,right,bottom")
        print()
        return

    result = enhance_image_asset(
        image_asset_id=args.image_asset_id,
        crop_mode=args.crop,
        crop_box=args.crop_box,
        auto_contrast=args.auto_contrast,
        sharpen=args.sharpen,
        denoise=args.denoise,
        target_long_edge_px=args.target_long_edge_px,
        output_format=args.output_format,
        quality=args.quality,
        notes=args.notes,
    )

    print()
    print("# Curator Enhance Result")
    print()
    print(f"Status: {result.get('status')}")

    if result.get("issues"):
        print(f"Issues: {', '.join(result['issues'])}")
        print()
        return

    print(f"New Image Asset ID: {result['id']}")
    print(f"Derived From: {result.get('derived_from_image_asset_id')}")
    print(f"Operations: {', '.join(result.get('derivation_operations', [])) or 'none'}")
    print(f"File Path: {result.get('file_path')}")
    print(f"Output Size: {result.get('output_width')}x{result.get('output_height')}")
    print()
    print("Next: run Sentinel Visual QA on this new asset before using it as a mockup or product image.")
    print()


if __name__ == "__main__":
    main()
