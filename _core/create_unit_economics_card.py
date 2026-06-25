import argparse
from datetime import datetime

from pipeline_contracts import (
    DESIGN_FILE,
    ECONOMICS_FILE,
    load_json,
    save_json,
    next_id,
    create_handoff,
)


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_float_or_none(value):
    if value is None:
        return None

    raw = str(value).strip().lower()

    if raw in {"", "none", "null", "missing", "cost_data_missing"}:
        return None

    try:
        return float(raw)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Create a SpaceCommand V6 Ledger unit economics card.")
    parser.add_argument("--design-package-id", required=True)
    parser.add_argument("--supplier", default="MANUAL")
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--variant", default="cost_data_missing")
    parser.add_argument("--item-price", default="cost_data_missing")
    parser.add_argument("--customer-shipping-paid", default="0")
    parser.add_argument("--production-cost", default="cost_data_missing")
    parser.add_argument("--shipping-cost-us", default="cost_data_missing")
    parser.add_argument("--verified-supplier-cost", choices=["true", "false"], default="false")
    parser.add_argument("--verified-shipping-cost", choices=["true", "false"], default="false")
    parser.add_argument("--etsy-listing-fee", default="0.20")
    parser.add_argument("--etsy-transaction-fee-percent", default="0.065")
    parser.add_argument("--payment-processing-percent", default="0.03")
    parser.add_argument("--payment-processing-fixed", default="0.25")
    parser.add_argument("--return-reprint-allowance-percent", default="0.05")
    parser.add_argument("--minimum-profit-dollars", default="5.00")
    parser.add_argument("--minimum-margin-percent", default="0.25")
    parser.add_argument("--notes", default="")
    parser.add_argument("--create-handoff", action="store_true")

    args = parser.parse_args()

    designs = load_json(DESIGN_FILE, [])
    design_ids = {x.get("id") for x in designs}

    if args.design_package_id not in design_ids:
        print()
        print("# Unit Economics Card Blocked")
        print()
        print(f"Missing design package: {args.design_package_id}")
        print("Ledger cannot create unit economics without a valid design_package_id.")
        return

    design = next(x for x in designs if x.get("id") == args.design_package_id)

    economics_cards = load_json(ECONOMICS_FILE, [])

    item_price = parse_float_or_none(args.item_price)
    customer_shipping_paid = parse_float_or_none(args.customer_shipping_paid) or 0.0
    production_cost = parse_float_or_none(args.production_cost)
    shipping_cost_us = parse_float_or_none(args.shipping_cost_us)

    verified_supplier_cost = args.verified_supplier_cost == "true"
    verified_shipping_cost = args.verified_shipping_cost == "true"

    listing_fee = parse_float_or_none(args.etsy_listing_fee) or 0.20
    transaction_percent = parse_float_or_none(args.etsy_transaction_fee_percent) or 0.065
    processing_percent = parse_float_or_none(args.payment_processing_percent) or 0.03
    processing_fixed = parse_float_or_none(args.payment_processing_fixed) or 0.25
    allowance_percent = parse_float_or_none(args.return_reprint_allowance_percent) or 0.05
    minimum_profit = parse_float_or_none(args.minimum_profit_dollars) or 5.0
    minimum_margin = parse_float_or_none(args.minimum_margin_percent) or 0.25

    issues = []

    if not design.get("production_allowed", False):
        issues.append("design_not_production_allowed")

    if item_price is None:
        issues.append("item_price_missing")

    if production_cost is None:
        issues.append("production_cost_missing")

    if shipping_cost_us is None:
        issues.append("shipping_cost_missing")

    if not verified_supplier_cost:
        issues.append("supplier_cost_not_verified")

    if not verified_shipping_cost:
        issues.append("shipping_cost_not_verified")

    calculation = {}

    if item_price is not None and production_cost is not None and shipping_cost_us is not None:
        gross_revenue = item_price + customer_shipping_paid
        etsy_transaction_fee = gross_revenue * transaction_percent
        payment_processing_fee = (gross_revenue * processing_percent) + processing_fixed
        return_reprint_allowance = gross_revenue * allowance_percent
        total_cost = (
            production_cost
            + shipping_cost_us
            + listing_fee
            + etsy_transaction_fee
            + payment_processing_fee
            + return_reprint_allowance
        )
        profit = gross_revenue - total_cost
        margin = profit / gross_revenue if gross_revenue > 0 else 0.0

        calculation = {
            "gross_revenue": round(gross_revenue, 2),
            "production_cost": round(production_cost, 2),
            "shipping_cost_us": round(shipping_cost_us, 2),
            "etsy_listing_fee": round(listing_fee, 2),
            "etsy_transaction_fee": round(etsy_transaction_fee, 2),
            "payment_processing_fee": round(payment_processing_fee, 2),
            "return_reprint_allowance": round(return_reprint_allowance, 2),
            "total_cost": round(total_cost, 2),
            "profit": round(profit, 2),
            "margin_percent": round(margin * 100, 2),
            "minimum_profit_required": round(minimum_profit, 2),
            "minimum_margin_required_percent": round(minimum_margin * 100, 2),
        }
    else:
        profit = None
        margin = None

    if issues:
        if any(x in issues for x in ["production_cost_missing", "shipping_cost_missing", "item_price_missing"]):
            ledger_decision = "COST_DATA_MISSING"
        else:
            ledger_decision = "FAIL"
    elif profit is not None and margin is not None and profit >= minimum_profit and margin >= minimum_margin:
        ledger_decision = "PASS"
    elif profit is not None and profit > 0:
        ledger_decision = "NEEDS_PRICE_CHANGE"
    else:
        ledger_decision = "FAIL"

    listing_allowed = ledger_decision == "PASS"
    production_allowed = ledger_decision == "PASS"

    card = {
        "id": next_id("ECON", economics_cards),
        "type": "unit_economics_card",
        "status": "complete",
        "design_package_id": args.design_package_id,
        "design_status": design.get("status"),
        "supplier": args.supplier,
        "product_type": args.product_type,
        "variant": args.variant,
        "item_price": item_price if item_price is not None else "cost_data_missing",
        "customer_shipping_paid": customer_shipping_paid,
        "production_cost": production_cost if production_cost is not None else "cost_data_missing",
        "shipping_cost_us": shipping_cost_us if shipping_cost_us is not None else "cost_data_missing",
        "verified_supplier_cost": verified_supplier_cost,
        "verified_shipping_cost": verified_shipping_cost,
        "ledger_decision": ledger_decision,
        "issues": issues,
        "calculation": calculation,
        "production_allowed": production_allowed,
        "listing_allowed": listing_allowed,
        "notes": args.notes,
        "created_at": now_stamp(),
    }

    economics_cards.append(card)
    save_json(ECONOMICS_FILE, economics_cards)

    handoff = None
    if args.create_handoff:
        if listing_allowed:
            to_agent = "Scribe"
            required_next_action = "Scribe may create listing drafts because Ledger PASS exists."
            status = "ready_for_listing"
        else:
            to_agent = "Overseer"
            required_next_action = "Pipeline must remain blocked until evidence, production permission, verified supplier cost, verified shipping cost, and profitable price exist."
            status = "blocked_by_ledger"

        handoff = create_handoff(
            from_agent="Ledger",
            to_agent=to_agent,
            artifact_type="unit_economics_card",
            artifact_id=card["id"],
            summary=f"Ledger decision: {ledger_decision}. Listing allowed: {listing_allowed}",
            required_next_action=required_next_action,
            status=status,
        )

    print()
    print("# Unit Economics Card Created")
    print()
    print(f"ID: {card['id']}")
    print(f"Design Package ID: {card['design_package_id']}")
    print(f"Ledger Decision: {card['ledger_decision']}")
    print(f"Issues: {', '.join(card['issues']) or 'none'}")
    print(f"Production Allowed: {card['production_allowed']}")
    print(f"Listing Allowed: {card['listing_allowed']}")

    if calculation:
        print(f"Profit: ${calculation['profit']}")
        print(f"Margin: {calculation['margin_percent']}%")

    if handoff:
        print()
        print("# Handoff Created")
        print(f"ID: {handoff['id']}")
        print(f"From: {handoff['from_agent']}")
        print(f"To: {handoff['to_agent']}")
        print(f"Status: {handoff['status']}")
        print(f"Artifact: {handoff['artifact_id']}")

    print()


if __name__ == "__main__":
    main()
