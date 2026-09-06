import argparse

from qwen_edit_style_transfer import (
    DEFAULT_SPACE_ID,
    LORA_ADAPTERS,
    QwenEditSpaceError,
    run_qwen_edit_style_transfer,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Style-transfer an existing product photo using the community HF Space "
            "prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast. Edits an image you already "
            "have — it does not generate art from scratch. Result still needs Sentinel "
            "Visual QA before use, same as any other image source."
        )
    )
    parser.add_argument("--image-request-id", required=True, help="Existing Forge image_request id to attach this asset to.")
    parser.add_argument("--input-image", action="append", required=True, dest="input_images",
                         help="Path to an input image. Repeat for multi-image styles (e.g. Any-light, Style-Transfer).")
    parser.add_argument("--prompt", required=True, help="Edit instruction, e.g. 'Transform into anime.'")
    parser.add_argument("--lora-adapter", required=True, choices=LORA_ADAPTERS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--randomize-seed", action="store_true", default=True)
    parser.add_argument("--fixed-seed", dest="randomize_seed", action="store_false",
                         help="Use --seed exactly instead of randomizing it.")
    parser.add_argument("--guidance-scale", type=float, default=4.0)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--space-id", default=DEFAULT_SPACE_ID, help="Override if you fork/self-host this Space.")
    parser.add_argument("--hf-token", default=None,
                         help="Hugging Face token for higher ZeroGPU quota (or set HF_TOKEN in .env.local). "
                              "Anonymous calls hit 'exceeded your ZeroGPU runs limit' quickly.")

    args = parser.parse_args()

    try:
        result = run_qwen_edit_style_transfer(
            image_request_id=args.image_request_id,
            input_image_paths=args.input_images,
            prompt=args.prompt,
            lora_adapter=args.lora_adapter,
            seed=args.seed,
            randomize_seed=args.randomize_seed,
            guidance_scale=args.guidance_scale,
            steps=args.steps,
            space_id=args.space_id,
            hf_token=args.hf_token,
        )
    except QwenEditSpaceError as exc:
        print()
        print("# Qwen Edit Style Transfer Blocked")
        print()
        print(str(exc))
        print()
        return

    print()
    print("# Qwen Edit Style Transfer Result")
    print()
    print(f"OK: {result.get('ok')}")
    print(f"Message: {result.get('message')}")

    asset = result.get("asset")
    if asset:
        print()
        print("## Image Asset Recorded")
        print(f"Asset ID: {asset.get('id')}")
        print(f"Status: {asset.get('status')}")
        print(f"File Path: {asset.get('file_path')}")
        print(f"Approved For Mockup: {asset.get('approved_for_mockup')}")
        print(f"Approved For Product: {asset.get('approved_for_product')}")
        print()
        print("Next: run Sentinel Visual QA before mockup/product/upload.")

    print()


if __name__ == "__main__":
    main()
