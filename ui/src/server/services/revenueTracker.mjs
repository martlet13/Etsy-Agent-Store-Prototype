import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");
const SALES_ORDERS_FILE = path.join(DATA_DIR, "sales_orders.json");
const REVENUE_SUMMARY_FILE = path.join(DATA_DIR, "revenue_summary.json");
const LISTING_PERFORMANCE_FILE = path.join(DATA_DIR, "listing_performance.json");
const MARKET_MEMORY_FILE = path.join(DATA_DIR, "market_performance_memory.json");
const PRODUCT_PACKAGES_FILE = path.join(DATA_DIR, "product_packages.json");

function readJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const text = fs.readFileSync(filePath, "utf8").trim();
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
}

function money(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function round(value) {
  return Number(money(value).toFixed(2));
}

function envNumber(name, fallback) {
  const number = Number(process.env[name]);
  return Number.isFinite(number) ? number : fallback;
}

function feeConfig() {
  return {
    etsyTransactionFeeRate: envNumber("ETSY_TRANSACTION_FEE_RATE", 0.065),
    etsyProcessingRate: envNumber("ETSY_PAYMENT_PROCESSING_RATE_US", 0.03),
    etsyProcessingFixed: envNumber("ETSY_PAYMENT_PROCESSING_FIXED_US", 0.25),
    etsyListingRenewalFee: envNumber("ETSY_LISTING_RENEWAL_FEE_PER_UNIT", 0.20),
    shippingOverlapBuffer: envNumber("SHIPPING_OVERLAP_BUFFER", 2.00),
    taxReserveRate: envNumber("TAX_RESERVE_RATE", 0.30)
  };
}

function connectorStatus() {
  return {
    api_key_present: Boolean(process.env.ETSY_API_KEY),
    access_token_present: Boolean(process.env.ETSY_ACCESS_TOKEN),
    refresh_token_present: Boolean(process.env.ETSY_REFRESH_TOKEN),
    shop_id_present: Boolean(process.env.ETSY_SHOP_ID),
    order_sync_ready: Boolean(process.env.ETSY_API_KEY && process.env.ETSY_ACCESS_TOKEN && process.env.ETSY_SHOP_ID)
  };
}

export function calculateOrderProfit(input = {}) {
  const fees = feeConfig();
  const itemPrice = money(input.item_price ?? input.price ?? input.total);
  const quantity = Math.max(1, Math.floor(money(input.quantity, 1)));
  const supplierProductCost = money(input.supplier_product_cost ?? input.production_cost);
  const etsyTransactionFee = money(input.etsy_transaction_fee, itemPrice * fees.etsyTransactionFeeRate);
  const etsyProcessingFee = money(input.etsy_processing_fee, itemPrice * fees.etsyProcessingRate + fees.etsyProcessingFixed);
  const etsyListingRenewalFee = money(input.etsy_listing_renewal_fee, fees.etsyListingRenewalFee);
  const shippingMode = String(input.shipping_mode || input.shippingMode || "buyer_paid").toLowerCase();
  const businessPaid = ["free_shipping", "business_paid", "seller_paid"].includes(shippingMode);
  const shippingOverlapBuffer = money(input.shipping_overlap_buffer, fees.shippingOverlapBuffer);
  const actualShipping = money(input.actual_shipping_cost_if_business_paid ?? input.actual_shipping_cost, 0);
  const perUnitProfit = businessPaid
    ? itemPrice - supplierProductCost - actualShipping - etsyTransactionFee - etsyProcessingFee - etsyListingRenewalFee
    : itemPrice - supplierProductCost - etsyTransactionFee - etsyProcessingFee - etsyListingRenewalFee - shippingOverlapBuffer;
  const netProfit = perUnitProfit * quantity;
  return {
    item_price: round(itemPrice),
    quantity,
    supplier_product_cost: round(supplierProductCost),
    etsy_transaction_fee: round(etsyTransactionFee),
    etsy_processing_fee: round(etsyProcessingFee),
    etsy_listing_renewal_fee: round(etsyListingRenewalFee),
    shipping_overlap_buffer: businessPaid ? 0 : round(shippingOverlapBuffer),
    actual_shipping_cost_if_business_paid: businessPaid ? round(actualShipping) : 0,
    net_profit: round(netProfit),
    tax_reserved: round(Math.max(0, netProfit) * fees.taxReserveRate),
    spendable: round(Math.max(0, netProfit) * (1 - fees.taxReserveRate))
  };
}

export function normalizeSalesOrder(input = {}) {
  const computed = calculateOrderProfit(input);
  return {
    order_id: String(input.order_id || input.receipt_id || input.id || `ORDER-${Date.now()}`),
    source: input.source === "etsy_api" || input.source === "manual_import" || input.source === "test_seed" ? input.source : "manual_import",
    listing_id: String(input.listing_id || input.listingId || ""),
    package_id: String(input.package_id || input.packageId || ""),
    work_id: String(input.work_id || input.workId || ""),
    sold_at: input.sold_at || input.created_timestamp || input.created_at || new Date().toISOString(),
    item_price: computed.item_price,
    shipping_paid_by_customer: round(input.shipping_paid_by_customer || 0),
    quantity: computed.quantity,
    supplier_product_cost: computed.supplier_product_cost,
    etsy_transaction_fee: computed.etsy_transaction_fee,
    etsy_processing_fee: computed.etsy_processing_fee,
    etsy_listing_renewal_fee: computed.etsy_listing_renewal_fee,
    shipping_overlap_buffer: computed.shipping_overlap_buffer,
    actual_shipping_cost_if_business_paid: computed.actual_shipping_cost_if_business_paid,
    net_profit: computed.net_profit,
    tax_reserved: computed.tax_reserved,
    spendable: computed.spendable,
    raw: input.raw || input
  };
}

export function listSalesOrders() {
  const orders = readJson(SALES_ORDERS_FILE, []);
  return Array.isArray(orders)
    ? [...orders].sort((a, b) => String(b.sold_at || "").localeCompare(String(a.sold_at || "")))
    : [];
}

export function saveSalesOrders(orders = []) {
  const existing = listSalesOrders();
  const byId = new Map(existing.map((order) => [order.order_id, order]));
  for (const order of orders) byId.set(order.order_id, order);
  const merged = [...byId.values()].sort((a, b) => String(b.sold_at || "").localeCompare(String(a.sold_at || "")));
  writeJson(SALES_ORDERS_FILE, merged);
  updateRevenueSummary(merged);
  updateListingPerformance(merged);
  updateMarketPerformanceMemory(merged);
  return merged;
}

export function buildRevenueSummary(orders = listSalesOrders()) {
  const realOrders = (Array.isArray(orders) ? orders : []).filter((order) => ["etsy_api", "manual_import"].includes(order.source));
  const summary = realOrders.reduce((acc, order) => {
    acc.gross_revenue += money(order.item_price) * Math.max(1, money(order.quantity, 1));
    acc.net_profit += money(order.net_profit);
    acc.saved_for_taxes += money(order.tax_reserved);
    acc.spendable += money(order.spendable);
    acc.order_count += 1;
    acc.units_sold += Math.max(1, money(order.quantity, 1));
    return acc;
  }, {
    gross_revenue: 0,
    net_profit: 0,
    saved_for_taxes: 0,
    spendable: 0,
    order_count: 0,
    units_sold: 0,
    updated_at: new Date().toISOString()
  });
  return {
    gross_revenue: round(summary.gross_revenue),
    net_profit: round(summary.net_profit),
    saved_for_taxes: round(summary.saved_for_taxes),
    spendable: round(summary.spendable),
    order_count: summary.order_count,
    units_sold: summary.units_sold,
    updated_at: summary.updated_at
  };
}

export function updateRevenueSummary(orders = listSalesOrders()) {
  const summary = buildRevenueSummary(orders);
  writeJson(REVENUE_SUMMARY_FILE, summary);
  return summary;
}

export function getRevenueSummary() {
  const orders = listSalesOrders();
  const summary = updateRevenueSummary(orders);
  return {
    ok: true,
    summary,
    connector: connectorStatus(),
    missingConnector: connectorStatus().order_sync_ready ? "" : "ETSY_ORDER_CONNECTOR_MISSING_OR_INCOMPLETE"
  };
}

function daysBetween(start, end) {
  const startDate = start ? new Date(start) : null;
  const endDate = end ? new Date(end) : null;
  if (!startDate || !endDate || Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return null;
  return Math.max(0, Math.ceil((endDate.getTime() - startDate.getTime()) / 86400000));
}

export function updateListingPerformance(orders = listSalesOrders()) {
  const packages = readJson(PRODUCT_PACKAGES_FILE, []);
  const existing = readJson(LISTING_PERFORMANCE_FILE, []);
  const byListing = new Map((Array.isArray(existing) ? existing : []).map((item) => [item.listing_id, item]));
  for (const pkg of Array.isArray(packages) ? packages : []) {
    const listingId = String(pkg.live_listing_id || pkg.etsy_listing_id || pkg.listing_id || "");
    if (!listingId) continue;
    if (!byListing.has(listingId)) {
      byListing.set(listingId, {
        listing_id: listingId,
        package_id: pkg.package_id || "",
        work_id: pkg.work_id || "",
        created_at: pkg.listed_at || pkg.updated_at || pkg.created_at || new Date().toISOString(),
        initial_quantity: Number(pkg.listing?.quantity || 500),
        current_quantity: Number(pkg.listing?.quantity || 500),
        quantity_sold: 0,
        sold_out_at: "",
        days_to_sell_out: null,
        top_performer: false,
        auto_relist_eligible: false,
        replace_when_sold_out: false
      });
    }
  }
  for (const order of orders) {
    if (!order.listing_id) continue;
    const current = byListing.get(order.listing_id) || {
      listing_id: order.listing_id,
      package_id: order.package_id || "",
      work_id: order.work_id || "",
      created_at: order.sold_at,
      initial_quantity: 500,
      current_quantity: 500,
      quantity_sold: 0,
      sold_out_at: "",
      days_to_sell_out: null,
      top_performer: false,
      auto_relist_eligible: false,
      replace_when_sold_out: false
    };
    current.quantity_sold = money(current.quantity_sold) + Math.max(1, money(order.quantity, 1));
    current.current_quantity = Math.max(0, money(current.initial_quantity, 500) - current.quantity_sold);
    if (current.current_quantity === 0 && !current.sold_out_at) current.sold_out_at = order.sold_at || new Date().toISOString();
    current.days_to_sell_out = current.sold_out_at ? daysBetween(current.created_at, current.sold_out_at) : daysBetween(current.created_at, new Date().toISOString());
    const soldOut = current.current_quantity === 0;
    current.top_performer = Boolean(soldOut && current.days_to_sell_out !== null && current.days_to_sell_out <= 30);
    current.auto_relist_eligible = current.top_performer;
    current.replace_when_sold_out = Boolean(current.days_to_sell_out !== null && current.days_to_sell_out > 30);
    byListing.set(order.listing_id, current);
  }
  const rows = [...byListing.values()].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  writeJson(LISTING_PERFORMANCE_FILE, rows);
  return rows;
}

export function updateMarketPerformanceMemory(orders = listSalesOrders()) {
  const packages = readJson(PRODUCT_PACKAGES_FILE, []);
  const byPackage = new Map((Array.isArray(packages) ? packages : []).map((pkg) => [pkg.package_id, pkg]));
  const memory = new Map();
  for (const order of orders) {
    const pkg = byPackage.get(order.package_id) || {};
    const key = [
      pkg.market_keyword || "unknown",
      pkg.product_type || "unknown",
      pkg.supplier || "unknown"
    ].join("|").toLowerCase();
    const current = memory.get(key) || {
      market_keyword: pkg.market_keyword || "",
      product_type: pkg.product_type || "",
      item_look_style: pkg.item_look?.style || "",
      supplier: pkg.supplier || "",
      margin: pkg.economics?.margin ?? null,
      views: null,
      favorites: null,
      orders: 0,
      units_sold: 0,
      net_profit: 0,
      sell_through_speed: null,
      score_adjustment: 0
    };
    current.orders += 1;
    current.units_sold += Math.max(1, money(order.quantity, 1));
    current.net_profit = round(current.net_profit + money(order.net_profit));
    current.score_adjustment = Math.min(20, 5 + current.units_sold * 2 + Math.max(0, current.net_profit));
    memory.set(key, current);
  }
  const rows = [...memory.values()].sort((a, b) => b.score_adjustment - a.score_adjustment);
  writeJson(MARKET_MEMORY_FILE, rows);
  return rows;
}

export function listListingPerformance() {
  updateListingPerformance(listSalesOrders());
  const rows = readJson(LISTING_PERFORMANCE_FILE, []);
  return Array.isArray(rows) ? rows : [];
}

export function listMarketPerformanceMemory() {
  const rows = readJson(MARKET_MEMORY_FILE, []);
  return Array.isArray(rows) ? rows : [];
}

export async function syncEtsyOrders() {
  const status = connectorStatus();
  if (!status.order_sync_ready) {
    updateRevenueSummary(listSalesOrders());
    return {
      ok: false,
      missingConnector: "ETSY_ORDER_CONNECTOR_MISSING_OR_INCOMPLETE",
      connector: status,
      ordersSynced: 0,
      summary: buildRevenueSummary(listSalesOrders()),
      diagnostics: {
        endpoint_attempted: "",
        read_only: true,
        mutation: false
      }
    };
  }
  updateRevenueSummary(listSalesOrders());
  return {
    ok: false,
    missingConnector: "ETSY_ORDER_FETCH_NOT_IMPLEMENTED",
    connector: status,
    ordersSynced: 0,
    summary: buildRevenueSummary(listSalesOrders()),
    diagnostics: {
      endpoint_attempted: "Etsy receipts/orders read-only endpoint pending implementation",
      read_only: true,
      mutation: false
    }
  };
}
