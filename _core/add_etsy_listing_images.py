import argparse

from curator_image_kernel import MOCKUP_ASSETS_FILE
from forge_image_kernel import IMAGE_ASSETS_FILE, load_json
from image_generation_budget import find_by_id
from publishing_dock import add_etsy_listing_images


def resolve_paths(mockup_ids, image_asset_ids, explicit_paths):
    paths = []
    missing = []

    if mockup_ids:
        mockups = load_json(MOCKUP_ASSETS_FILE, [])
        for mockup_id in mockup_ids:
            mockup = find_by_id(mockups, mockup_id)
            if mockup and mockup.get("file_path"):
                paths.append(mockup["file_path"])
            else:
                missing.append(mockup_id)

    if image_asset_ids:
        assets = load_json(IMAGE_ASSETS_FILE, [])
        for asset_id in image_asset_ids:
            asset = find_by_id(assets, asset_id)
            if asset and asset.get("file_path"):
                paths.append(asset["file_path"])
            else:
                missing.append(asset_id)

    paths.extend(explicit_paths or [])
    return paths, missing


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Add additional photos (e.g. Curator interior mockups) to an EXISTING Etsy draft "
            "listing. Etsy shows up to 20 photos per listing; rank 1 is usually the primary "
            "product photo uploaded when create_etsy_draft.py first created the draft, so this "
            "defaults to starting at rank 2. Never changes the listing's state."
        )
    )
    parser.add_argument("--etsy-listing-id", type=int, required=True,
                         help="The real numeric Etsy listing id printed by create_etsy_draft.py (e.g. 4570931272), not a local id like PUBPKG-0001.")
    parser.add_argument("--mockup-id", action="append", dest="mockup_ids", default=[],
                         help="A mockup_assets.json id from generate_interior_mockup.py (e.g. MOCKUP-0001). Repeatable.")
    parser.add_argument("--image-asset-id", action="append", dest="image_asset_ids", default=[],
                         help="An image_assets.json id (e.g. IMGASSET-0002). Repeatable.")
    parser.add_argument("--image-path", action="append", dest="image_paths", default=[],
                         help="An arbitrary local file path. Repeatable.")
    parser.add_argument("--starting-rank", type=int, default=2,
                         help="Photo position to start at (1 is normally already taken by the primary product photo).")
    parser.add_argument("--i-approve-this-live-etsy-action", action="store_true", dest="approved",
                         help="Required. Explicit acknowledgement that this will make a real write call to your Etsy shop.")

    args = parser.parse_args()

    if not args.approved:
        print()
        print("# Add Etsy Listing Images Blocked")
        print()
        print("Re-run with --i-approve-this-live-etsy-action to confirm you want this")
        print("script to make a real write call to your Etsy shop.")
        print()
        return

    paths, missing = resolve_paths(args.mockup_ids, args.image_asset_ids, args.image_paths)

    if missing:
        print()
        print("# Add Etsy Listing Images Blocked")
        print()
        print(f"Could not resolve a file path for: {', '.join(missing)}")
        print()
        return

    if not paths:
        print()
        print("# Add Etsy Listing Images Blocked")
        print()
        print("No images to upload. Pass --mockup-id, --image-asset-id, and/or --image-path (repeatable).")
        print()
        return

    run = add_etsy_listing_images(
        etsy_listing_id=args.etsy_listing_id,
        image_paths=paths,
        user_approved_live_action=True,
        starting_rank=args.starting_rank,
    )

    print()
    print("# Add Etsy Listing Images Result")
    print()
    print(f"Status: {run.get('status')}")
    print(f"Etsy Listing ID: {run.get('etsy_listing_id')}")

    if run.get("issues"):
        print(f"Issues: {', '.join(run['issues'])}")

    if run.get("images_uploaded"):
        print()
        print("## Uploaded")
        for item in run["images_uploaded"]:
            print(f"  - rank {item['rank']}: listing_image_id={item.get('listing_image_id')} <- {item['file_path']}")

    if run.get("upload_errors"):
        print()
        print("## Failed")
        for item in run["upload_errors"]:
            print(f"  - rank {item['rank']}: {item['error']} <- {item['file_path']}")

    print()


if __name__ == "__main__":
    main()
