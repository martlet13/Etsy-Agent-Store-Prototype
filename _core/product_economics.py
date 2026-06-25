import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

PRODUCTS_FILE = STATE / "products.json"
PRICING_RULES_FILE = STATE / "pricing_rules.json"
SUPPLIER_COSTS_FILE = STATE / "supplier_costs.json"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return fallback
    return json.loads(text)


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_products() -> List[Dict[str, Any]]:
    return load_json(PRODUCTS_FILE, [])


def save_products(products: List[Dict[str, Any]]) -> None:
    save_json(PRODUCTS_FILE, products)


def load_rules() -> Dict[str, Any]:
    return load_json(PRICING_RULES_FILE, {})


def load_supplier_costs() -> List[Dict[str, Any]]:
    return load_json(SUPPLIER_COSTS_FILE, [])


def match_supplier_cost(product: Dict[str, Any], costs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    supplier = str(product.get("supplier", "")).strip().lower()
    product_type = str(product.get("product_type", "")).strip().lower()
    variant = str(product.get("variant", "")).strip().lower()

    for row in costs:
        if (
            str(row.get("supplier", "")).strip().lower() == supplier
            and str(row.get("product_type", "")).strip().lower() == product_type
            and str(row.get("variant", "")).strip().lower() == variant
        ):
            return row

    return None


def money(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except Exception:
        return None


def calculate_product(product: Dict[str, Any], rules: Dict[str, Any], cost_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    issues = []
    warnings = []

    item_price = money(product.get("item_price"))
    customer_shipping_paid = money(product.get("customer_shipping_paid", 0.0)) or 0.0

    if item_price is None:
        issues.append("item_price_missing")

    production_cost = None
    shipping_cost = None
    verified_supplier_cost = False
    verified_shipping_cost = False

    if cost_row:
        production_cost = money(cost_row.get("production_cost"))
        shipping_cost = money(cost_row.get("shipping_cost_us"))
        verified_supplier_cost = bool(cost_row.get("verified_supplier_cost", False))
        verified_shipping_cost = bool(cost_row.get("verified_shipping_cost", False))
    else:
        issues.append("supplier_cost_row_missing")

    if production_cost is None:
        issues.append("production_cost_missing")

    if shipping_cost is None:
        issues.append("shipping_cost_missing")

    if rules.get("require_verified_supplier_cost", True) and not verified_supplier_cost:
        issues.append("supplier_cost_not_verified")

    if rules.get("require_verified_shipping_cost", True) and not verified_shipping_cost:
        issues.append("shipping_cost_not_verified")

    if rules.get("fail_if_shipping_unknown", True) and shipping_cost is None:
        issues.append("shipping_unknown_blocks_gate")

    if rules.get("fail_if_production_unknown", True) and production_cost is None:
        issues.append("production_unknown_blocks_gate")

    if item_price is None or production_cost is None or shipping_cost is None:
        return {
            "product_id": product.get("id"),
            "decision": "FAIL",
            "reason": "missing_required_cost_or_price_data",
            "issues": issues,
            "warnings": warnings,
            "calculation": {},
            "calculated_at": now_stamp(),
        }

    gross_revenue = item_price + customer_shipping_paid

    listing_fee = money(rules.get("etsy_listing_fee", 0.20)) or 0.20
    expected_units = money(rules.get("expected_units_before_relist", 1)) or 1
    listing_fee_allocated = listing_fee / max(expected_units, 1)

    etsy_transaction_fee_percent = money(rules.get("etsy_transaction_fee_percent", 0.065)) or 0.065
    etsy_transaction_fee = gross_revenue * etsy_transaction_fee_percent

    processing_percent = money(rules.get("payment_processing_percent", 0.03)) or 0.03
    processing_fixed = money(rules.get("payment_processing_fixed", 0.25)) or 0.25
    payment_processing_fee = (gross_revenue * processing_percent) + processing_fixed

    return_reprint_allowance_percent = money(rules.get("return_reprint_allowance_percent", 0.05)) or 0.05
    return_reprint_allowance = gross_revenue * return_reprint_allowance_percent

    offsite_ads_fee = 0.0
    if bool(rules.get("include_offsite_ads_in_gate", False)):
        offsite_ads_percent = money(rules.get("offsite_ads_percent", 0.15)) or 0.15
        offsite_ads_fee = gross_revenue * offsite_ads_percent
    else:
        warnings.append("offsite_ads_not_included_in_gate")

    supplier_cost_total = production_cost + shipping_cost

    total_cost = (
        supplier_cost_total
        + listing_fee_allocated
        + etsy_transaction_fee
        + payment_processing_fee
        + return_reprint_allowance
        + offsite_ads_fee
    )

    profit = gross_revenue - total_cost
    margin = profit / gross_revenue if gross_revenue > 0 else 0.0

    minimum_profit = money(rules.get("minimum_profit_dollars", 5.0)) or 5.0
    minimum_margin = money(rules.get("minimum_margin_percent", 0.25)) or 0.25

    if profit >= minimum_profit and margin >= minimum_margin and not issues:
        decision = "PASS"
        reason = "meets_profit_and_margin_gate"
    elif not issues and profit > 0:
        decision = "NEEDS_PRICE_CHANGE"
        reason = "positive_profit_but_below_required_profit_or_margin"
    else:
        decision = "FAIL"
        reason = "does_not_meet_profit_gate"

    recommended_min_price_for_profit = item_price + max(0.0, minimum_profit - profit)
    if margin < minimum_margin:
        # Solve rough price target ignoring nonlinear fee changes except percent fees; conservative enough for draft gate.
        variable_fee_percent = etsy_transaction_fee_percent + processing_percent + return_reprint_allowance_percent
        if bool(rules.get("include_offsite_ads_in_gate", False)):
            variable_fee_percent += money(rules.get("offsite_ads_percent", 0.15)) or 0.15

        fixed_costs = supplier_cost_total + listing_fee_allocated + processing_fixed
        target_revenue = fixed_costs / max(0.01, 1.0 - variable_fee_percent - minimum_margin)
        recommended_min_price_for_margin = max(0.0, target_revenue - customer_shipping_paid)
    else:
        recommended_min_price_for_margin = item_price

    recommended_min_price = max(recommended_min_price_for_profit, recommended_min_price_for_margin)

    return {
        "product_id": product.get("id"),
        "decision": decision,
        "reason": reason,
        "issues": issues,
        "warnings": warnings,
        "calculation": {
            "item_price": round(item_price, 2),
            "customer_shipping_paid": round(customer_shipping_paid, 2),
            "gross_revenue": round(gross_revenue, 2),
            "production_cost": round(production_cost, 2),
            "supplier_shipping_cost": round(shipping_cost, 2),
            "supplier_cost_total": round(supplier_cost_total, 2),
            "listing_fee_allocated": round(listing_fee_allocated, 2),
            "etsy_transaction_fee": round(etsy_transaction_fee, 2),
            "payment_processing_fee": round(payment_processing_fee, 2),
            "return_reprint_allowance": round(return_reprint_allowance, 2),
            "offsite_ads_fee": round(offsite_ads_fee, 2),
            "total_cost": round(total_cost, 2),
            "profit": round(profit, 2),
            "margin_percent": round(margin * 100, 2),
            "minimum_profit_required": round(minimum_profit, 2),
            "minimum_margin_required_percent": round(minimum_margin * 100, 2),
            "recommended_min_price": round(recommended_min_price, 2),
        },
        "calculated_at": now_stamp(),
    }


def run_gate(update_products: bool = True) -> List[Dict[str, Any]]:
    products = load_products()
    rules = load_rules()
    costs = load_supplier_costs()

    results = []

    for product in products:
        cost_row = match_supplier_cost(product, costs)
        result = calculate_product(product, rules, cost_row)
        results.append(result)

        if update_products:
            product["ledger_gate"] = result
            product["ledger_decision"] = result["decision"]
            product["ledger_checked_at"] = result["calculated_at"]

    if update_products:
        save_products(products)

    return results


def print_report(results: List[Dict[str, Any]]) -> None:
    print()
    print("# Ledger Product Economics Report")
    print()
    print(f"Generated: {now_stamp()}")
    print()

    if not results:
        print("No products found.")
        return

    for result in results:
        calc = result.get("calculation", {})
        print(f"## {result.get('product_id')}")
        print()
        print(f"- Decision: {result.get('decision')}")
        print(f"- Reason: {result.get('reason')}")
        print(f"- Issues: {', '.join(result.get('issues') or []) or 'none'}")
        print(f"- Warnings: {', '.join(result.get('warnings') or []) or 'none'}")

        if calc:
            print(f"- Gross revenue: ${calc.get('gross_revenue')}")
            print(f"- Total cost: ${calc.get('total_cost')}")
            print(f"- Profit: ${calc.get('profit')}")
            print(f"- Margin: {calc.get('margin_percent')}%")
            print(f"- Recommended minimum price: ${calc.get('recommended_min_price')}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SpaceCommand product unit-economics gate.")
    parser.add_argument("--no-update", action="store_true", help="Do not update products.json")
    args = parser.parse_args()

    results = run_gate(update_products=not args.no_update)
    print_report(results)


if __name__ == "__main__":
    main()
