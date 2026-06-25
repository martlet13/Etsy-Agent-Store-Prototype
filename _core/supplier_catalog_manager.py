import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

CATALOG_FILE = STATE / "supplier_product_catalog.json"
CHECKS_FILE = STATE / "supplier_catalog_checks.json"
DESIGN_FILE = STATE / "design_packages.json"


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


def get_products() -> List[Dict[str, Any]]:
    catalog = load_json(CATALOG_FILE, {"products": []})
    return catalog.get("products", [])


def get_product(product_id: str) -> Dict[str, Any] | None:
    for product in get_products():
        if product.get("id") == product_id:
            return product
    return None


def list_products() -> str:
    lines = ["# Supplier Product Catalog", ""]
    for product in get_products():
        lines.append(f"## {product.get('name')} ({product.get('id')})")
        lines.append(f"- Category: {product.get('category')}")
        lines.append(f"- Minimum Size: {product.get('minimum_width_px')}x{product.get('minimum_height_px')}")
        lines.append(f"- Transparent Required: {product.get('transparent_background_required')}")
        lines.append(f"- Recommended Min Price: ${product.get('recommended_min_price_usd')}")
        lines.append(f"- Forge Notes: {product.get('forge_image_notes')}")
        lines.append("")
    return "\n".join(lines)


def match_product_for_design(design_package_id: str, preferred_product_id: str = "") -> Dict[str, Any]:
    designs = load_json(DESIGN_FILE, [])
    checks = load_json(CHECKS_FILE, [])
    products = get_products()

    design = None
    for item in designs:
        if item.get("id") == design_package_id:
            design = item
            break

    issues = []
    warnings = []

    if not design:
        issues.append("missing_design_package")

    chosen = None

    if preferred_product_id:
        chosen = get_product(preferred_product_id)
        if not chosen:
            issues.append("unknown_preferred_product")
    elif design:
        product_fit = [str(x).lower() for x in design.get("product_fit", [])]
        title = str(design.get("title", "")).lower()
        concept = str(design.get("design_concept", "")).lower()
        haystack = " ".join(product_fit + [title, concept])

        if "mug" in haystack:
            chosen = get_product("mug_11oz")
        elif "shirt" in haystack or "apparel" in haystack:
            chosen = get_product("shirt_bella_canvas_3001")
        elif "tote" in haystack:
            chosen = get_product("tote_bag")
        elif "sticker" in haystack:
            chosen = get_product("sticker_sheet")
        else:
            chosen = get_product("poster_8x10")

    if not chosen:
        issues.append("no_product_match")

    check = {
        "id": next_id("SUPCHECK", checks),
        "type": "supplier_catalog_check",
        "status": "blocked" if issues else "matched",
        "design_package_id": design_package_id,
        "preferred_product_id": preferred_product_id,
        "matched_product_id": chosen.get("id") if chosen else None,
        "matched_product_name": chosen.get("name") if chosen else None,
        "issues": issues,
        "warnings": warnings,
        "product": chosen,
        "created_at": now_stamp(),
    }

    checks.append(check)
    save_json(CHECKS_FILE, checks)
    return check


def main():
    parser = argparse.ArgumentParser(description="Supplier catalog manager.")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--match-design", default="")
    parser.add_argument("--preferred-product-id", default="")
    args = parser.parse_args()

    if args.list:
        print()
        print(list_products())
        print()
        return

    if args.match_design:
        check = match_product_for_design(args.match_design, args.preferred_product_id)
        print()
        print("# Supplier Product Match")
        print()
        print(f"ID: {check['id']}")
        print(f"Status: {check['status']}")
        print(f"Design: {check.get('design_package_id')}")
        print(f"Matched Product: {check.get('matched_product_id')} / {check.get('matched_product_name')}")
        print(f"Issues: {', '.join(check.get('issues', [])) or 'none'}")
        print()


if __name__ == "__main__":
    main()
