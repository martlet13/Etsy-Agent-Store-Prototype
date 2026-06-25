import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");
const PACKAGE_FILE = path.join(DATA_DIR, "product_packages.json");

function moneyOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function bool(value) {
  return value === true || value === "true" || value === 1 || value === "1";
}

function cleanKey(value) {
  return String(value || "").trim().toLowerCase();
}

function unique(values) {
  return [...new Set((Array.isArray(values) ? values : []).filter(Boolean))];
}

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

function packageIdFor(workId, existing = []) {
  const found = existing.find((item) => item.work_id === workId);
  if (found?.package_id) return found.package_id;
  let highest = 0;
  for (const item of existing) {
    const raw = String(item.package_id || item.id || "");
    if (!raw.startsWith("PRODPKG-")) continue;
    const number = Number(raw.split("-")[1]);
    if (Number.isFinite(number)) highest = Math.max(highest, number);
  }
  return `PRODPKG-${String(highest + 1).padStart(4, "0")}`;
}

function optionPrice(option) {
  return moneyOrNull(option?.target_price ?? option?.targetPrice ?? option?.item_price ?? option?.recommended_price ?? option?.recommendedPrice);
}

function optionProductionCost(option) {
  return moneyOrNull(option?.base_cost ?? option?.baseCost ?? option?.production_cost ?? option?.productionCost);
}

function optionProfit(option) {
  return moneyOrNull(option?.profit ?? option?.estimatedProfit ?? option?.estimated_profit ?? option?.pricing_debug?.profit);
}

function optionMargin(option) {
  const raw = moneyOrNull(option?.margin ?? option?.marginPct ?? option?.estimatedMarginPct ?? option?.ledger_margin ?? option?.pricing_debug?.marginPercent);
  if (raw === null) return null;
  return raw > 1 ? raw / 100 : raw;
}

function optionPassesLedger(option, minMargin) {
  const price = optionPrice(option);
  const cost = optionProductionCost(option);
  const profit = optionProfit(option);
  const margin = optionMargin(option);
  return Boolean(
    (option?.ledger_pass === true || option?.ledgerPassAfterCorrection === true || option?.ledger_decision === "PASS" || option?.ledgerDecision === "PASS")
    && price !== null
    && cost !== null
    && bool(option?.supplier_cost_verified ?? option?.supplierCostVerified ?? option?.verified_supplier_cost)
    && profit !== null
    && profit > 0
    && margin !== null
    && margin >= minMargin
  );
}

function opportunityGrade(workItem, novaResearch) {
  const combos = novaResearch?.recommendedCombinations || workItem?.nova_research?.recommendedCombinations || [];
  const match = combos.find((combo) => cleanKey(combo.marketKeyword) === cleanKey(workItem?.market_keyword)) || combos[0];
  const score = moneyOrNull(workItem?.opportunity_score ?? match?.opportunityScore ?? match?.score);
  const grade = String(match?.grade || workItem?.opportunity_grade || "").trim();
  if (grade) return { grade, score };
  if (score === null) return { grade: "B", score: null };
  return { grade: score >= 80 ? "A" : score >= 65 ? "B" : score >= 50 ? "C" : "Reject", score };
}

function selectedOptions(ledgerResult, minMargin) {
  const fromReview = [
    ...(Array.isArray(ledgerResult?.recommended_options) ? ledgerResult.recommended_options : []),
    ...(Array.isArray(ledgerResult?.product_options) ? ledgerResult.product_options : [])
  ];
  const pass = fromReview.filter((option) => optionPassesLedger(option, minMargin));
  const first = pass[0] || null;
  if (!first) return [];
  const productId = first.product_id || first.productId || "";
  const supplier = first.supplier || "";
  const productType = first.product_type || first.productType || "";
  const grouped = pass.filter((option) =>
    cleanKey(option.supplier) === cleanKey(supplier)
    && cleanKey(option.product_type || option.productType) === cleanKey(productType)
    && cleanKey(option.product_id || option.productId) === cleanKey(productId)
  );
  return grouped.length ? grouped : [first];
}

function listingQuantity({ option, policy }) {
  const defaultQuantity = Math.max(2, Number(policy?.default_listing_quantity || 500));
  const availability = moneyOrNull(option?.availability_quantity ?? option?.availabilityQuantity);
  const isPod = option?.is_pod_made_to_order !== false;
  if (availability !== null) {
    const quantity = Math.max(1, Math.min(defaultQuantity, Math.floor(availability)));
    return {
      quantity,
      supplier_quantity_cap: quantity,
      ok: quantity > 1 || policy?.allow_quantity_one === true,
      reason: quantity <= 1 ? "supplier_only_has_one_available_variant" : "supplier_quantity_cap_applied"
    };
  }
  if (isPod) {
    return {
      quantity: defaultQuantity,
      supplier_quantity_cap: null,
      ok: true,
      reason: "pod_made_to_order_default_quantity"
    };
  }
  return {
    quantity: null,
    supplier_quantity_cap: null,
    ok: false,
    reason: "inventory_unknown_for_non_pod_product"
  };
}

function variantFromOption(option, policy, minMargin) {
  const quantity = listingQuantity({ option, policy });
  const margin = optionMargin(option);
  const profit = optionProfit(option);
  const included = Boolean(quantity.ok && optionPassesLedger(option, minMargin));
  return {
    supplier_variant_id: String(option?.variant_id || option?.variantId || option?.variant || ""),
    variant_name: String(option?.variant || option?.variant_name || option?.variantName || option?.variantId || ""),
    color: String(option?.color || option?.raw_option?.variant?.color || option?.raw?.variant?.color || ""),
    size: String(option?.size || option?.raw_option?.variant?.size || option?.raw?.variant?.size || ""),
    scent: String(option?.scent || ""),
    material: String(option?.material || ""),
    availability_quantity: option?.availability_quantity ?? null,
    listing_quantity: quantity.quantity,
    production_cost: optionProductionCost(option),
    item_price: optionPrice(option),
    ledger_margin: margin === null ? null : Number((margin * 100).toFixed(2)),
    ledger_profit: profit === null ? null : Number(profit.toFixed(2)),
    included,
    exclusion_reason: included ? "" : quantity.reason || "ledger_gate_not_passed"
  };
}

function scribeListing(scribeResult, ledgerResult, workItem) {
  const preview = scribeResult || ledgerResult?.listing_preview || {};
  const tags = unique(preview.tags || workItem?.seo_seed?.tags || workItem?.scribe_keywords || []).slice(0, 13);
  return {
    title: String(preview.title || "").trim(),
    description: String(preview.description || "").trim(),
    tags,
    materials: Array.isArray(preview.materials) ? preview.materials : [],
    occasion: preview.occasion || "",
    recipient: preview.recipient || "",
    style: preview.style || "",
    seo_provider_used: preview.seo_provider_used || workItem?.seo_provider_used || "",
    keywords_used: preview.keywords_used || workItem?.scribe_keywords || []
  };
}

function artworkFromAsset(imageAsset = {}) {
  const pngPath = imageAsset.file_path || imageAsset.localImagePath || imageAsset.path || "";
  return {
    png_path: pngPath,
    png_url: imageAsset.public_preview_url || imageAsset.image_url || "",
    width: imageAsset.width || null,
    height: imageAsset.height || null,
    transparent_ready: bool(imageAsset.transparent_png_ready ?? imageAsset.transparent_ready),
    file_type: String(imageAsset.file_type || path.extname(pngPath).replace(".", "") || "").toLowerCase()
  };
}

function economicsFromOption(option, policy) {
  const profit = optionProfit(option);
  const margin = optionMargin(option);
  const taxRate = moneyOrNull(policy?.tax_reserve_rate) ?? 0.30;
  const debug = option?.pricing_debug || {};
  return {
    margin: margin === null ? null : Number((margin * 100).toFixed(2)),
    projected_profit: profit === null ? null : Number(profit.toFixed(2)),
    projected_tax_reserve: profit === null ? null : Number((Math.max(0, profit) * taxRate).toFixed(2)),
    projected_spendable: profit === null ? null : Number((Math.max(0, profit) * (1 - taxRate)).toFixed(2)),
    etsy_fees: {
      transaction_fee: debug.etsyTransactionFee ?? option?.etsy_transaction_fee ?? null,
      payment_processing_fee: debug.paymentProcessingFee ?? option?.payment_processing_fee ?? null,
      listing_renewal_fee_per_sale: debug.etsyListingRenewalFee ?? option?.etsy_listing_renewal_fee_per_unit ?? null,
      total: debug.etsyFeesTotal ?? option?.etsy_fees_total ?? null
    },
    shipping_buffer: debug.shippingOverlapBuffer ?? option?.shipping_overlap_buffer ?? null
  };
}

function gate(id, passed, message) {
  return { id, passed: Boolean(passed), message };
}

export function buildProductPackage({
  workItem = {},
  novaResearch = null,
  imageAsset = null,
  sentinelReport = null,
  supplierResearch = null,
  ledgerResult = null,
  scribeResult = null,
  policy = {}
} = {}) {
  const existing = readJson(PACKAGE_FILE, []);
  const minMargin = moneyOrNull(policy.min_profit_margin) ?? 0.10;
  const now = new Date().toISOString();
  const grade = opportunityGrade(workItem, novaResearch);
  const selected = selectedOptions(ledgerResult, minMargin);
  const primary = selected[0] || {};
  const variants = selected.map((option) => variantFromOption(option, policy, minMargin));
  const includedVariants = variants.filter((variant) => variant.included);
  const listing = scribeListing(scribeResult, ledgerResult, workItem);
  const artwork = artworkFromAsset(imageAsset || {});
  const pngExists = Boolean(artwork.png_path && fs.existsSync(artwork.png_path));
  const isPng = artwork.file_type === "png" || /\.png$/i.test(artwork.png_path);
  const tagsWithoutBlocked = listing.tags.filter((tag) => !(workItem?.item_look?.blockedTerms || workItem?.market_research?.item_look?.blocked_terms || []).some((term) => cleanKey(tag).includes(cleanKey(term))));
  const slots = policy.listing_slots || {};
  const monthlySlotAvailable = slots.remaining_listing_slots === undefined || Number(slots.remaining_listing_slots) > 0;
  const etsyReady = policy.etsy_setup_ready === true;
  const mockups = Array.isArray(workItem.mockups) ? workItem.mockups : [];
  const requireMockups = policy.require_mockups_for_publish === true;

  const gates = [
    gate("nova_opportunity_grade_a_or_b", ["A", "B"].includes(grade.grade), `Nova grade is ${grade.grade}.`),
    gate("sentinel_approved_for_product", sentinelReport?.approved_for_product === true || imageAsset?.approved_for_product === true, "Sentinel approved the artwork for products."),
    gate("artwork_file_exists", pngExists, "Artwork PNG exists on disk."),
    gate("artwork_is_png", isPng, "Artwork file is PNG."),
    gate("product_type_selected", Boolean(primary.product_type || primary.productType), "Product type selected."),
    gate("supplier_selected", Boolean(primary.supplier), "Supplier selected."),
    gate("variant_included", includedVariants.length > 0, "At least one variant is included."),
    gate("quantity_rule_passes", includedVariants.every((variant) => variant.listing_quantity > 1 || policy.allow_quantity_one === true), "Listing quantity passes policy."),
    gate("ledger_margin_passes", includedVariants.every((variant) => moneyOrNull(variant.ledger_margin) !== null && Number(variant.ledger_margin) >= minMargin * 100), "Ledger margin is at least 10%."),
    gate("etsy_fees_included", moneyOrNull(primary.etsy_fees_total ?? primary.pricing_debug?.etsyFeesTotal) !== null, "Etsy fees are included."),
    gate("shipping_buffer_included", moneyOrNull(primary.shipping_overlap_buffer ?? primary.pricing_debug?.shippingOverlapBuffer) !== null, "Shipping overlap buffer is included."),
    gate("scribe_title_exists", Boolean(listing.title), "Scribe title exists."),
    gate("scribe_description_exists", Boolean(listing.description), "Scribe description exists."),
    gate("scribe_tags_exist", tagsWithoutBlocked.length > 0, "Scribe tags exist."),
    gate("blocked_terms_absent", tagsWithoutBlocked.length === listing.tags.length, "Blocked terms are absent from tags."),
    gate("monthly_listing_slot_available", monthlySlotAvailable, "Monthly listing slot is available."),
    gate("mockups_ready_or_not_required", !requireMockups || mockups.length > 0, "Mockups are ready or not required by policy.")
  ];

  const blockers = gates.filter((item) => !item.passed).map((item) => item.id);
  const productGatesPass = blockers.length === 0;
  const status = productGatesPass
    ? (etsyReady ? "ready_to_publish" : "ready_but_waiting_for_etsy_setup")
    : "repairing";
  const listingQuantityValue = includedVariants.length
    ? Math.min(...includedVariants.map((variant) => Number(variant.listing_quantity || 0)).filter(Boolean))
    : policy.default_listing_quantity || 500;
  const prices = {};
  for (const variant of includedVariants) {
    prices[variant.supplier_variant_id || variant.variant_name || `variant_${Object.keys(prices).length + 1}`] = variant.item_price;
  }

  const warnings = unique([
    ...(Array.isArray(ledgerResult?.warnings) ? ledgerResult.warnings : []),
    ...(Array.isArray(scribeResult?.warnings) ? scribeResult.warnings : []),
    ...(mockups.length ? [] : ["mockup_generation_pending"]),
    ...(etsyReady ? [] : ["etsy_setup_required_before_live_listing"])
  ]);

  return {
    ok: productGatesPass,
    package_id: packageIdFor(workItem.work_id, existing),
    status,
    work_id: workItem.work_id || "",
    design_package_id: workItem.design_package_id || ledgerResult?.design_package_id || "",
    market_keyword: workItem.market_keyword || "",
    opportunity_score: grade.score,
    supplier: primary.supplier || "",
    product_type: primary.product_type || primary.productType || "",
    supplier_product_id: primary.product_id || primary.productId || "",
    supplier_product_name: primary.product_name || primary.productName || "",
    artwork,
    mockups,
    variants,
    listing: {
      title: listing.title,
      description: listing.description,
      tags: tagsWithoutBlocked.slice(0, 13),
      quantity: listingQuantityValue,
      prices,
      shipping_mode: primary.shipping_mode || primary.shippingMode || "buyer_paid",
      shipping_profile_id: "",
      category_id: "",
      attributes: {},
      materials: listing.materials,
      occasion: listing.occasion,
      recipient: listing.recipient,
      style: listing.style
    },
    economics: economicsFromOption(primary, policy),
    gates,
    warnings,
    blockers,
    supplier_research_summary: {
      source: supplierResearch?.source || "",
      option_count: Array.isArray(supplierResearch?.options) ? supplierResearch.options.length : selected.length
    },
    created_at: existing.find((item) => item.work_id === workItem.work_id)?.created_at || now,
    updated_at: now
  };
}

export function saveProductPackage(pkg) {
  const packages = readJson(PACKAGE_FILE, []);
  const list = Array.isArray(packages) ? packages : [];
  const index = list.findIndex((item) => item.package_id === pkg.package_id || (pkg.work_id && item.work_id === pkg.work_id));
  if (index >= 0) list[index] = pkg;
  else list.push(pkg);
  writeJson(PACKAGE_FILE, list);
  return pkg;
}

export function listProductPackages() {
  const packages = readJson(PACKAGE_FILE, []);
  return Array.isArray(packages)
    ? [...packages].sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")))
    : [];
}
