import argparse

from forge_image_kernel import record_image_asset


def main():
    parser = argparse.ArgumentParser(description="Record a generated image asset for Forge QA tracking.")
    parser.add_argument("--image-request-id", required=True)
    parser.add_argument("--file-path", required=True)
    parser.add_argument("--provider-id", default="manual_image_generation")
    parser.add_argument("--generation-notes", default="")

    args = parser.parse_args()

    asset = record_image_asset(
        image_request_id=args.image_request_id,
        file_path=args.file_path,
        provider_id=args.provider_id,
        generation_notes=args.generation_notes,
    )

    print()
    print("# Forge Image Asset Recorded")
    print()
    print(f"ID: {asset['id']}")
    print(f"Status: {asset['status']}")
    print(f"Image Request ID: {asset.get('image_request_id')}")
    print(f"Design Package ID: {asset.get('design_package_id')}")
    print(f"File Path: {asset.get('file_path')}")
    print(f"Approved For Mockup: {asset.get('approved_for_mockup')}")
    print(f"Approved For Product: {asset.get('approved_for_product')}")
    print()


if __name__ == "__main__":
    main()
