import argparse

from forge_image_kernel import create_image_request


def csv_list(raw):
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main():
    parser = argparse.ArgumentParser(description="Create a strict Forge image generation request.")
    parser.add_argument("--design-package-id", required=True)
    parser.add_argument("--provider-id", default="manual_image_generation")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--composition", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--color-palette", required=True)
    parser.add_argument("--text-rules", required=True)
    parser.add_argument("--product-use", required=True)
    parser.add_argument("--aspect-ratio", required=True)
    parser.add_argument("--required-elements", default="")
    parser.add_argument("--forbidden-elements", default="")
    parser.add_argument("--negative-constraints", required=True)
    parser.add_argument("--quality-bar", required=True)
    parser.add_argument("--size", default="1024x1280")
    parser.add_argument("--seed", default="none")
    parser.add_argument("--notes", default="")

    args = parser.parse_args()

    request = create_image_request(
        design_package_id=args.design_package_id,
        provider_id=args.provider_id,
        subject=args.subject,
        composition=args.composition,
        style=args.style,
        color_palette=args.color_palette,
        text_rules=args.text_rules,
        product_use=args.product_use,
        aspect_ratio=args.aspect_ratio,
        required_elements=csv_list(args.required_elements),
        forbidden_elements=csv_list(args.forbidden_elements),
        negative_constraints=args.negative_constraints,
        quality_bar=args.quality_bar,
        size=args.size,
        seed=args.seed,
        notes=args.notes,
    )

    print()
    print("# Forge Image Generation Request Created")
    print()
    print(f"ID: {request['id']}")
    print(f"Status: {request['status']}")
    print(f"Design Package ID: {request.get('design_package_id')}")
    print(f"Provider: {request.get('provider_id')}")
    print(f"Production Allowed: {request.get('production_allowed')}")
    print(f"Listing Allowed: {request.get('listing_allowed')}")
    print(f"Issues: {', '.join(request.get('issues', [])) or 'none'}")
    print()
    print("## Prompt")
    print(request.get("prompt", ""))


if __name__ == "__main__":
    main()
