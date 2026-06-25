import argparse

from publishing_dock import create_publish_package


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(description="Create a Publishing Dock package from an approved image asset.")
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--connector-id", default="manual_browser_upload")
    parser.add_argument("--target-platforms", default="printify,printful,etsy")
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--listing-draft-id", default="")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    package = create_publish_package(
        image_asset_id=args.image_asset_id,
        connector_id=args.connector_id,
        target_platforms=csv_list(args.target_platforms),
        product_type=args.product_type,
        listing_draft_id=args.listing_draft_id,
        notes=args.notes,
    )

    print()
    print("# Publish Package Created")
    print()
    print(f"ID: {package['id']}")
    print(f"Status: {package['status']}")
    print(f"Connector: {package.get('connector_id')}")
    print(f"Targets: {', '.join(package.get('target_platforms', []))}")
    print(f"Image Asset: {package.get('image_asset_id')}")
    print(f"Design Package: {package.get('design_package_id')}")
    print(f"Listing Draft: {package.get('listing_draft_id')}")
    print(f"Live Upload Allowed: {package.get('live_upload_allowed')}")
    print(f"Live Publish Allowed: {package.get('live_publish_allowed')}")
    print(f"Etsy Sync Allowed: {package.get('etsy_sync_allowed')}")
    print(f"Issues: {', '.join(package.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(package.get('warnings', [])) or 'none'}")

    print()
    print("## Upload Checklist")
    for item in package.get("upload_checklist", []):
        print(f"- {item}")

    fields = package.get("copy_paste_fields", {})
    if fields:
        print()
        print("## Copy/Paste Fields")
        print(f"Title: {fields.get('title')}")
        print(f"Price: {fields.get('price')}")
        print(f"SKU: {fields.get('sku')}")
        print(f"Tags: {', '.join(fields.get('tags', [])) if isinstance(fields.get('tags'), list) else fields.get('tags')}")
        print()
        print("Description:")
        print(fields.get("description", ""))

    print()


if __name__ == "__main__":
    main()
