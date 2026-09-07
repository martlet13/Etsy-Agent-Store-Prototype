import argparse

from curator_image_kernel import FRAME_STYLES, ROOM_STYLES, generate_interior_mockup


def parse_size(raw):
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--canvas-size must be WIDTHxHEIGHT, e.g. 1600x1600")
    return (int(parts[0]), int(parts[1]))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Curator: generate a procedural 'framed print on a wall' interior placement mockup "
            "for an image asset — a rendered/stylized scene (gradient wall, soft shadow, mat + "
            "frame), not a photograph. Good for a listing's secondary photos to help buyers "
            "picture it in a room; not a substitute for a real photographed room template. "
            "Recorded separately in mockup_assets.json (not gated by Ledger/Sentinel)."
        )
    )
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--room-style", choices=list(ROOM_STYLES), default="warm_neutral")
    parser.add_argument("--frame-style", choices=list(FRAME_STYLES), default="black")
    parser.add_argument("--canvas-size", type=parse_size, default=(1600, 1600), help="WIDTHxHEIGHT in pixels. Default 1600x1600.")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    result = generate_interior_mockup(
        image_asset_id=args.image_asset_id,
        room_style=args.room_style,
        frame_style=args.frame_style,
        canvas_size=args.canvas_size,
        notes=args.notes,
    )

    print()
    print("# Curator Interior Mockup")
    print()
    print(f"Status: {result.get('status')}")

    if result.get("issues"):
        print(f"Issues: {', '.join(result['issues'])}")
        print()
        return

    print(f"Mockup ID: {result['id']}")
    print(f"Image Asset: {result.get('image_asset_id')}")
    print(f"Room Style: {result.get('room_style')} / Frame Style: {result.get('frame_style')}")
    print(f"Size: {result.get('width')}x{result.get('height')}")
    print(f"File Path: {result.get('file_path')}")
    print()
    print("This is a procedural render, not a photograph — label it accordingly if used in a listing.")
    print()


if __name__ == "__main__":
    main()
