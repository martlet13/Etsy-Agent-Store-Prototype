import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
PRODUCTS_FILE = STATE / "products.json"


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_products():
    if not PRODUCTS_FILE.exists():
        return []
    text = PRODUCTS_FILE.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return []
    return json.loads(text)


def save_products(products):
    PRODUCTS_FILE.write_text(json.dumps(products, indent=2), encoding="utf-8")


def next_product_id(products):
    highest = 0
    for p in products:
        raw = str(p.get("id", ""))
        if raw.startswith("PROD-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass
    return f"PROD-{highest + 1:04d}"


def main():
    parser = argparse.ArgumentParser(description="Seed a draft product candidate for Ledger testing.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--supplier", default="MANUAL")
    parser.add_argument("--product-type", default="manual_test_product")
    parser.add_argument("--variant", default="manual_test_variant")
    parser.add_argument("--item-price", type=float, required=True)
    parser.add_argument("--customer-shipping-paid", type=float, default=0.0)
    args = parser.parse_args()

    products = load_products()
    product_id = next_product_id(products)

    product = {
        "id": product_id,
        "status": "draft_candidate",
        "title": args.title,
        "theme": args.theme,
        "supplier": args.supplier,
        "product_type": args.product_type,
        "variant": args.variant,
        "item_price": args.item_price,
        "customer_shipping_paid": args.customer_shipping_paid,
        "created_at": now_stamp(),
        "nova_hypothesis": None,
        "forge_design_package": None,
        "ledger_decision": None,
        "ledger_gate": None,
        "scribe_listing_draft": None,
        "sentinel_listing_verdict": None
    }

    products.append(product)
    save_products(products)

    print()
    print("# Product Candidate Created")
    print()
    print(f"Product ID: {product_id}")
    print(f"Title: {args.title}")
    print(f"Supplier: {args.supplier}")
    print(f"Product Type: {args.product_type}")
    print(f"Variant: {args.variant}")
    print(f"Item Price: ${args.item_price}")
    print(f"Customer Shipping Paid: ${args.customer_shipping_paid}")
    print()


if __name__ == "__main__":
    main()
