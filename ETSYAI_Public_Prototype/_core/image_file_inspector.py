import argparse
import json
import struct
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

IMAGE_ASSETS_FILE = STATE / "image_assets.json"
INSPECTIONS_FILE = STATE / "image_file_inspections.json"
SUPPLIER_CATALOG_FILE = STATE / "supplier_product_catalog.json"


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def next_id(prefix: str, records: List[Dict[str, Any]]) -> str:
    highest = 0
    for item in records:
        raw = str(item.get("id", ""))
        if raw.startswith(prefix + "-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass
    return f"{prefix}-{highest + 1:04d}"


def find_by_id(records, record_id):
    for item in records:
        if item.get("id") == record_id:
            return item
    return None


def get_png_size(path: Path):
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) < 24:
        return None
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def inspect_image_asset(image_asset_id: str, product_id: str = "") -> Dict[str, Any]:
    assets = load_json(IMAGE_ASSETS_FILE, [])
    inspections = load_json(INSPECTIONS_FILE, [])
    catalog = load_json(SUPPLIER_CATALOG_FILE, {"products": []})

    asset = find_by_id(assets, image_asset_id)
    issues = []
    warnings = []

    if not asset:
        issues.append("missing_image_asset")
        inspection = {
            "id": next_id("IMGINSPECT", inspections),
            "status": "blocked",
            "image_asset_id": image_asset_id,
            "issues": issues,
            "warnings": warnings,
            "created_at": now_stamp(),
        }
        inspections.append(inspection)
        save_json(INSPECTIONS_FILE, inspections)
        return inspection

    file_path = Path(asset.get("file_path", ""))
    exists = file_path.exists()

    if not exists:
        issues.append("file_missing")

    ext = file_path.suffix.lower().replace(".", "")
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        warnings.append(f"unusual_file_type:{ext or 'none'}")

    width = None
    height = None

    if exists and ext == "png":
        size = get_png_size(file_path)
        if size:
            width, height = size
        else:
            warnings.append("could_not_read_png_dimensions")
    elif exists:
        warnings.append("dimension_check_only_supports_png_without_extra_libraries")

    product = None
    if product_id:
        for item in catalog.get("products", []):
            if item.get("id") == product_id:
                product = item
                break

        if not product:
            issues.append("unknown_product_id")

    if product and width and height:
        if width < int(product.get("minimum_width_px", 0)):
            issues.append("width_below_product_minimum")
        if height < int(product.get("minimum_height_px", 0)):
            issues.append("height_below_product_minimum")

    inspection = {
        "id": next_id("IMGINSPECT", inspections),
        "type": "image_file_inspection",
        "status": "blocked" if issues else "pass",
        "image_asset_id": image_asset_id,
        "file_path": str(file_path),
        "file_exists": exists,
        "file_type": ext,
        "width": width,
        "height": height,
        "product_id": product_id,
        "product_name": product.get("name") if product else None,
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "created_at": now_stamp(),
    }

    inspections.append(inspection)
    save_json(INSPECTIONS_FILE, inspections)

    for item in assets:
        if item.get("id") == image_asset_id:
            item["image_file_inspection"] = inspection["id"]
            item["image_file_inspection_status"] = inspection["status"]
            item["image_file_inspection_issues"] = inspection["issues"]
            break

    save_json(IMAGE_ASSETS_FILE, assets)
    return inspection


def main():
    parser = argparse.ArgumentParser(description="Inspect image asset file dimensions and product fit.")
    parser.add_argument("--image-asset-id", required=True)
    parser.add_argument("--product-id", default="")
    args = parser.parse_args()

    result = inspect_image_asset(args.image_asset_id, args.product_id)

    print()
    print("# Image File Inspection")
    print()
    print(f"ID: {result['id']}")
    print(f"Status: {result['status']}")
    print(f"Image Asset: {result.get('image_asset_id')}")
    print(f"File Exists: {result.get('file_exists')}")
    print(f"File Type: {result.get('file_type')}")
    print(f"Width: {result.get('width')}")
    print(f"Height: {result.get('height')}")
    print(f"Product: {result.get('product_id')} / {result.get('product_name')}")
    print(f"Issues: {', '.join(result.get('issues', [])) or 'none'}")
    print(f"Warnings: {', '.join(result.get('warnings', [])) or 'none'}")
    print()


if __name__ == "__main__":
    main()
