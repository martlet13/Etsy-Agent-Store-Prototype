import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive,
  Brain,
  Clapperboard,
  Coins,
  Factory,
  Image as ImageIcon,
  KeyRound,
  Mail,
  Music,
  RefreshCw,
  Shield,
  Sparkles,
  Store,
  Sword,
  Upload
} from "lucide-react";
import "./styles.css";

const API_BASE = "http://127.0.0.1:4521";

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function money(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "$0.00";
  return `$${num.toFixed(2)}`;
}

function cleanSystemPhrase(value) {
  const text = String(value || "").trim();
  if (!text) return "";

  return text
    .replaceAll("forge_create_design", "Forge should create the next design concept")
    .replace(/\bOPP-\d+\b/g, "this product idea")
    .replace(/\bAUDIT-\d+\b/g, "the latest audit")
    .replace(/\bDECISION-\d+\b/g, "a decision")
    .replace(/\bEVID-\d+\b/g, "a research source")
    .replace(/\bIMGREQ-\d+\b/g, "an image request")
    .replace(/\bDESIGN-\d+\b/g, "a design")
    .replace(/\bECON-\d+\b/g, "a Treasury check")
    .replace(/\s+/g, " ")
    .trim();
}

function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatusPill({ status }) {
  const raw = status || "unknown";
  const lowered = String(raw).toLowerCase();

  let tone = "neutral";
  if (["pass", "ready", "allowed", "live", "completed", "created", "working", "secured", "guarding", "calculating", "drafting", "safe"].some((x) => lowered.includes(x))) tone = "good";
  if (["blocked", "failed", "missing", "disabled", "locked", "waiting", "idle", "planned", "not connected", "warning", "approval"].some((x) => lowered.includes(x))) tone = "warn";
  if (["critical", "publish", "cost", "danger"].some((x) => lowered.includes(x))) tone = "danger";

  return <span className={`pill ${tone}`}>{raw}</span>;
}

const BLOCKED_IP_TERMS = [
  "disney",
  "marvel",
  "pokemon",
  "star wars",
  "harry potter",
  "taylor swift",
  "nike",
  "adidas",
  "nfl",
  "nba",
  "mlb"
];

function isWaitingForSentinel(asset) {
  const status = String(asset?.status || "").toLowerCase();
  return Boolean(asset?.queued_for_sentinel || asset?.ready_for_sentinel_qa || status.includes("waiting_sentinel") || status.includes("pending_visual_qa"));
}

function findBlockedTerms(asset, result, prompt) {
  const haystack = [
    asset?.prompt,
    asset?.title,
    result?.prompt,
    prompt
  ].filter(Boolean).join(" ").toLowerCase();

  return BLOCKED_IP_TERMS.filter((term) => haystack.includes(term));
}

function latestMatch(items, predicate) {
  const matches = safeArray(items).filter(predicate);
  return matches.length ? matches[matches.length - 1] : null;
}

function latestVisualQaForAsset(state, asset) {
  if (!asset) return null;
  const direct = asset.visual_qa
    ? safeArray(state?.visualQa).find((report) => report.id === asset.visual_qa)
    : null;
  return direct || latestMatch(state?.visualQa, (report) => report.image_asset_id === asset.id);
}

function sentinelProductApproved(state, asset) {
  const report = latestVisualQaForAsset(state, asset);
  return Boolean(asset?.approved_for_product || report?.approved_for_product);
}

function linkedPipelineForAsset(state, asset) {
  const designId = asset?.promoted_design_id || asset?.design_package_id;
  const design = designId
    ? safeArray(state?.designPackages).find((item) => item.id === designId)
    : null;
  const ledger = design
    ? latestMatch(state?.unitEconomics, (item) => item.design_package_id === design.id)
    : null;
  const listing = design
    ? latestMatch(state?.listings, (item) => item.design_package_id === design.id)
    : null;
  const publishPackage = asset
    ? latestMatch(state?.publishPackages, (item) => item.image_asset_id === asset.id)
    : null;

  return { design, ledger, listing, publishPackage };
}

function normalizedKey(value) {
  return String(value || "").trim().toLowerCase();
}

function matchingSupplierCost(state, form) {
  const supplier = normalizedKey(form.supplier);
  const productType = normalizedKey(form.productType);
  const productId = normalizedKey(form.productId);
  const variantId = normalizedKey(form.variantId);

  return safeArray(state?.supplierCosts).find((row) => {
    const rowSupplier = normalizedKey(row.supplier);
    const rowProductType = normalizedKey(row.product_type || row.category);
    const rowProductId = normalizedKey(row.product_id || row.id);
    const rowVariant = normalizedKey(row.variant_id || row.variant);
    return rowSupplier === supplier
      && rowProductType === productType
      && rowProductId === productId
      && rowVariant === variantId
      && Boolean(row.verified_supplier_cost || row.supplier_cost_verified);
  });
}

const REVIEW_PRODUCT_TYPES = ["sticker", "poster", "mug", "t-shirt"];

function productTypeMatches(option, productType) {
  const wanted = normalizedKey(productType).replace("-", "");
  const actual = normalizedKey(option?.productType).replace("-", "");
  const haystack = `${actual} ${normalizedKey(option?.productName)} ${normalizedKey(option?.variantName)}`.replace("-", "");
  if (wanted === "tshirt") return haystack.includes("shirt") || haystack.includes("tee");
  if (wanted === "sticker") return haystack.includes("sticker");
  if (wanted === "poster") return haystack.includes("poster") || haystack.includes("print");
  if (wanted === "mug") return haystack.includes("mug");
  return haystack.includes(wanted);
}

function recommendedProductRows(options, targetPrice) {
  return REVIEW_PRODUCT_TYPES.map((productType) => {
    const option = safeArray(options).find((item) => productTypeMatches(item, productType));
    if (!option) {
      return {
        productType,
        status: "BLOCKED",
        badge: "Ledger BLOCKED",
        warning: "Run supplier research for this product type."
      };
    }
    const details = ledgerOptionDetails(option);

    return {
      productType,
      supplier: option.supplier,
      productName: option.productName,
      variant: option.variantName || option.variantId,
      provider: option.providerName,
      baseCost: option.baseCost,
      shipping: option.shippingCost,
      targetPrice,
      profit: option.estimatedProfit,
      margin: option.estimatedMarginPct,
      status: details.pass ? "Ledger PASS" : "Ledger BLOCKED",
      badge: details.badge,
      warning: details.pass ? "" : (safeArray(option.warnings).concat(details.missing).filter(Boolean).join(", ") || "Ledger margin/cost gate has not passed.")
    };
  });
}

function firstPresentValue(source, keys) {
  for (const key of keys) {
    if (source && source[key] !== undefined && source[key] !== null && source[key] !== "") return source[key];
  }
  return null;
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function optionMoneyValue(option, keys) {
  const direct = numberOrNull(firstPresentValue(option, keys));
  if (direct !== null) return direct;
  return numberOrNull(firstPresentValue(option?.raw_option || {}, keys));
}

function optionBooleanValue(option, keys) {
  return keys.some((key) => {
    const value = option?.[key] ?? option?.raw_option?.[key];
    return value === true || String(value).toLowerCase() === "true";
  });
}

function optionMarginValue(option) {
  return numberOrNull(firstPresentValue(option, ["margin", "marginPct", "estimatedMarginPct", "estimated_margin_pct"])
    ?? firstPresentValue(option?.raw_option || {}, ["margin", "marginPct", "estimatedMarginPct", "estimated_margin_pct"]));
}

function ledgerOptionDetails(option) {
  const targetPrice = optionMoneyValue(option, ["targetPrice", "target_price", "item_price", "recommendedPrice", "recommended_price"]);
  const baseCost = optionMoneyValue(option, ["baseCost", "base_cost", "production_cost", "production_cost_us"]);
  const supplierVerified = optionBooleanValue(option, ["supplierCostVerified", "supplier_cost_verified", "verified_supplier_cost"]);
  const margin = optionMarginValue(option);
  const profit = optionMoneyValue(option, ["profit", "estimatedProfit", "estimated_profit"]);
  const missing = [];

  if (targetPrice === null) missing.push("item_price_missing");
  if (baseCost === null) missing.push("production_cost_missing");
  if (!supplierVerified) missing.push("supplier_cost_not_verified");
  if (margin === null) missing.push("margin_missing");
  if (profit === null) missing.push("profit_missing");
  if (profit !== null && profit < 0) missing.push("profit_below_ledger_rule");
  if (margin !== null && margin < 0.1) missing.push("margin_below_ledger_rule");

  return {
    pass: missing.length === 0,
    missing,
    badge: missing.includes("item_price_missing")
      ? "Missing price"
      : missing.includes("production_cost_missing") || missing.includes("supplier_cost_not_verified")
        ? "Missing verified cost"
        : missing.includes("shipping_cost_missing") || missing.includes("shipping_cost_not_verified")
          ? "Missing verified shipping"
          : missing.length
            ? "Ledger BLOCKED"
            : "Ledger PASS"
  };
}

function hasLedgerPassOption(review) {
  const options = [
    ...safeArray(review?.recommended_options),
    ...safeArray(review?.product_options)
  ];
  return options.some((option) => ledgerOptionDetails(option).pass);
}

function normalizeWorkStatus(item = {}, review = null) {
  const status = String(item?.status || review?.status || "").toLowerCase();
  const stage = String(item?.stage || "").toLowerCase();
  if (["uploaded", "listed", "published"].includes(status) || ["uploaded", "listed", "published"].includes(stage)) return "listed";
  if (status === "stopped") return "stopped";
  if (status === "waiting_for_setup") return "waiting_for_setup";
  if (["needs_attention", "blocked", "denied", "needs_changes"].includes(status)) return "repairing";
  if (["approval_ready", "waiting_for_approval", "approved", "ready_for_review"].includes(status)) return hasLedgerPassOption(review) ? "ready_to_publish" : "repairing";
  if (status === "ready_to_publish") return "ready_to_publish";
  if (status === "publishing") return "publishing";
  if (status === "repairing") return "repairing";
  if (stage === "prompt_planning" || stage === "research_replan") return "researching";
  if (stage === "image_generation") return "generating_art";
  if (stage === "sentinel_qa") return "qa_checking";
  if (stage === "production_check") return "pricing";
  if (stage === "scribe_draft") return "writing_listing";
  if (stage === "approval_queue" || stage === "ready_to_publish") return "ready_to_publish";
  if (stage === "publishing") return "publishing";
  return status || "working";
}

function getFriendlyStage(stage, item = {}) {
  const status = normalizeWorkStatus({ ...item, stage });
  if (status === "waiting_for_setup") return "Waiting for setup";
  if (status === "repairing") return "Repairing this product";
  if (status === "ready_to_publish") return "Ready to publish";
  if (status === "publishing") return "Publishing";
  if (status === "listed") return "Listed";

  const map = {
    prompt_planning: "Nova is researching a product opportunity",
    research_replan: "Nova is researching a better product opportunity",
    image_generation: "Forge is creating the PNG",
    sentinel_qa: "Sentinel is checking quality",
    promote_to_design: "Turning artwork into a product concept",
    production_check: "Ledger is pricing for profit",
    scribe_draft: "Scribe is writing the Etsy listing",
    ready_to_publish: "Publisher is preparing the listing",
    publishing: "Publisher is listing the product"
  };
  return map[stage] || titleCase(stage || status || "Working");
}

function getFriendlyBlockReason(reason) {
  const text = String(reason || "").trim();
  const lower = text.toLowerCase();
  if (!text) return "";
  if (lower.includes("production_cost_missing") || lower.includes("supplier_cost_not_verified")) return "Real supplier production cost is missing.";
  if (lower.includes("shipping_cost_missing") || lower.includes("shipping_cost_not_verified")) return "Buyer-paid shipping estimate is missing.";
  if (lower.includes("item_price_missing")) return "Selling price is missing.";
  if (lower.includes("printify_api_key") || lower.includes("printify")) return "Printify is not connected yet.";
  if (lower.includes("printful_api_key") || lower.includes("printful")) return "Printful is not connected yet.";
  if (lower.includes("no ledger pass")) return "No product option has passed the profit check yet.";
  if (lower.includes("listing_preview")) return "The listing draft is not ready yet.";
  return titleCase(text).replaceAll(" Api Key", " API key");
}

function projectAsset(item, state) {
  if (!item) return null;
  if (item.asset) return item.asset;
  if (safeArray(item.assets).length) return item.assets[0];
  if (item.representative) return projectAsset(item.representative, state);
  const assetId = item.asset_id || item.assetId || item.source_image_asset_id;
  return safeArray(state?.imageAssets).find((asset) => asset.id === assetId)
    || safeArray(state?.imageAssets).find((asset) => asset.design_package_id === item.design_package_id || asset.promoted_design_id === item.design_package_id)
    || null;
}

function projectReview(item, state, shiftData) {
  if (!item) return null;
  if (item.review) return item.review;
  if (safeArray(item.reviews).length) return item.reviews[0];
  if (item.representative) return projectReview(item.representative, state, shiftData);
  const reviews = [
    ...safeArray(shiftData?.reviews),
    ...safeArray(state?.productionReviews)
  ];
  return reviews.find((review) => review.review_id === item.production_review_id)
    || reviews.find((review) => review.asset_id === item.asset_id)
    || reviews.find((review) => review.design_package_id === item.design_package_id)
    || null;
}

function getProjectImageUrl(item, state) {
  const asset = item?.image_path || item?.image_url ? item : projectAsset(item, state);
  if (asset?.image_url) return asset.image_url.startsWith("/api") ? `${API_BASE}${asset.image_url}` : asset.image_url;
  if (asset?.public_preview_url) return `${API_BASE}${asset.public_preview_url}`;
  if (asset?.file_path) return "";
  return "";
}

function friendlyTitleFromText(text, productType = "") {
  const value = String(text || "").toLowerCase();
  const product = String(productType || "").toLowerCase();
  const kind = product.includes("mug") ? "Mug" : product.includes("shirt") ? "T-Shirt" : product.includes("poster") ? "Poster" : "Sticker";
  if (value.includes("blue collar") || value.includes("workshop") || value.includes("mechanic")) return `Blue Collar Workshop ${kind}`;
  if (value.includes("western") || value.includes("cowboy")) return `Western Cowboy ${kind}`;
  if (value.includes("coffee")) return `Coffee Humor ${kind}`;
  if (value.includes("teacher") || value.includes("nurse") || value.includes("mom") || value.includes("dad")) return "Teacher Nurse Gift Design";
  if (value.includes("seasonal")) return `Seasonal ${kind}`;
  if (value.includes("gym")) return `Gym ${kind}`;
  if (value.includes("fishing") || value.includes("outdoor")) return `Outdoor ${kind}`;
  if (value.includes("retro")) return `Retro Mascot ${kind}`;
  return `New ${kind} Design`;
}

function getProjectTitle(item, state, review = null) {
  const asset = projectAsset(item, state);
  const listing = review?.listing_preview;
  const firstOption = safeArray(review?.recommended_options)[0] || safeArray(review?.product_options)[0];
  const rawTitle = asset?.title || item?.title || item?.prompt_family || "";
  const titleLooksTechnical = /\bWORK-\d+\b/i.test(rawTitle) || rawTitle.toLowerCase().startsWith("autonomous ");
  return listing?.title && !String(listing.title).toLowerCase().includes("not created")
    ? listing.title
    : firstOption?.product_name && !String(firstOption.product_name).toLowerCase().includes("not selected")
      ? firstOption.product_name
      : rawTitle && !titleLooksTechnical
        ? rawTitle
        : friendlyTitleFromText(`${asset?.prompt || ""} ${item?.prompt || ""} ${item?.prompt_family || ""}`, asset?.product_type || firstOption?.product_type || "");
}

function getFriendlyStatus(item, review) {
  const status = normalizeWorkStatus(item, review);
  if (item?.human_status) return item.human_status;
  if (safeArray(item?.ledger_retry_history).length && !["waiting_for_setup", "ready_to_publish"].includes(status)) return "Ledger is improving pricing";
  if (status === "ready_to_publish") return "Publisher is preparing the listing";
  if (status === "waiting_for_setup") return "Agents are waiting for setup";
  if (status === "repairing") return "Agents are repairing this product";
  if (status === "researching") return "Nova is researching a product opportunity";
  if (status === "generating_art") return "Forge is creating the PNG";
  if (status === "qa_checking") return "Sentinel is checking quality";
  if (status === "pricing") return "Ledger is pricing for profit";
  if (status === "writing_listing") return "Scribe is writing the Etsy listing";
  if (status === "publishing") return "Publisher is publishing the listing";
  if (status === "listed") return "Listed";
  if (status === "running" || status === "queued") return "Agents are working";
  return status ? titleCase(status) : "Agents are working";
}

function getWorkerLine(project) {
  const item = project.representative || project;
  const label = item.worker_label || (item.worker_id ? `Forge ${String(item.worker_id).split("-")[1] || ""}`.trim() : "");
  if (!label) return "";
  const step = getFriendlyStage(item.stage, item).toLowerCase();
  return `${label} is ${step}.`;
}

function getProjectRevenue(item, state) {
  const sales = safeArray(state?.salesOrders);
  const idSet = new Set([
    item?.asset_id,
    item?.design_package_id,
    item?.production_review_id,
    item?.review_id
  ].filter(Boolean));
  const total = sales.reduce((sum, sale) => {
    const saleIds = [
      sale.asset_id,
      sale.design_package_id,
      sale.production_review_id,
      sale.review_id,
      sale.product_id,
      sale.listing_id
    ].filter(Boolean);
    if (!saleIds.some((id) => idSet.has(id))) return sum;
    const value = Number(sale.item_price ?? 0) * Number(sale.quantity || 1);
    return Number.isFinite(value) ? sum + value : sum;
  }, 0);
  return total;
}

function actualSalesRecords(state) {
  return safeArray(state?.salesOrders).filter((sale) => ["etsy_api", "manual_import"].includes(sale.source));
}

function calculateActualRevenue(state) {
  const summaryRevenue = Number(state?.revenueSummary?.gross_revenue);
  if (Number.isFinite(summaryRevenue)) return summaryRevenue;
  const realSales = actualSalesRecords(state);
  return realSales.reduce((sum, sale) => {
    const value = Number(sale.item_price ?? 0) * Number(sale.quantity || 1);
    return Number.isFinite(value) ? sum + value : sum;
  }, 0);
}

function calculateActualNetProfit(state) {
  const summaryProfit = Number(state?.revenueSummary?.net_profit);
  if (Number.isFinite(summaryProfit)) return summaryProfit;
  const realSales = actualSalesRecords(state);
  return realSales.reduce((sum, sale) => {
    const explicit = Number(sale.net_profit);
    if (Number.isFinite(explicit)) return sum + explicit;
    const revenue = Number(sale.revenue ?? sale.total ?? sale.amount ?? sale.order_total);
    const cost = Number(sale.total_cost ?? sale.cost ?? sale.expense ?? sale.fees);
    if (Number.isFinite(revenue) && Number.isFinite(cost)) return sum + (revenue - cost);
    return sum;
  }, 0);
}

function calculateTaxReserve(netProfit) {
  const value = Number(netProfit);
  return Number.isFinite(value) && value > 0 ? value * 0.30 : 0;
}

function calculateSpendable(netProfit) {
  const value = Number(netProfit);
  return Number.isFinite(value) && value > 0 ? value * 0.70 : 0;
}

function totalRevenue(state) {
  return calculateActualRevenue(state);
}

function moneySplit(state) {
  if (state?.revenueSummary) {
    return {
      revenue: Number(state.revenueSummary.gross_revenue || 0),
      netProfit: Number(state.revenueSummary.net_profit || 0),
      taxReserve: Number(state.revenueSummary.saved_for_taxes || 0),
      spendable: Number(state.revenueSummary.spendable || 0)
    };
  }
  const netProfit = calculateActualNetProfit(state);
  return {
    revenue: calculateActualRevenue(state),
    netProfit,
    taxReserve: calculateTaxReserve(netProfit),
    spendable: calculateSpendable(netProfit)
  };
}

function mainAgentStatus(shift, projects) {
  if (shift?.status !== "running") return "Agents are idle.";
  const active = safeArray(projects);
  if (active.some((project) => normalizeWorkStatus(project, project.review) === "ready_to_publish")) return "Agents are preparing products to publish.";
  if (active.some((project) => safeArray(project.ledger_retry_history).length || safeArray(project.representative?.ledger_retry_history).length)) return "Agents are improving product choices.";
  if (active.some((project) => {
    const reasons = [...safeArray(project.blocked_reasons), ...safeArray(project.review?.blocking_reasons)].join(" ").toLowerCase();
    return reasons.includes("api key") || reasons.includes("connector");
  })) return "Agents are waiting for setup.";
  return "Agents are working.";
}

function totalRevenueLegacy(state) {
  const realSales = [
    ...safeArray(state?.sales),
    ...safeArray(state?.orders),
    ...safeArray(state?.etsyOrders)
  ];
  if (realSales.length) {
    return realSales.reduce((sum, sale) => {
      const value = Number(sale.revenue ?? sale.total ?? sale.amount ?? sale.order_total ?? 0);
      return Number.isFinite(value) ? sum + value : sum;
    }, 0);
  }
  return Number(state?.businessMetrics?.totalRevenue || 0) || 0;
}

function buildProjectTimeline(item, state, shiftData) {
  const review = projectReview(item, state, shiftData);
  const asset = projectAsset(item, state);
  const listing = review?.listing_preview;
  const hasPass = hasLedgerPassOption(review);
  const productPackage = productPackageForProject(item, state);
  return [
    ["Forge", asset ? "Created the artwork." : "Preparing artwork."],
    ["Sentinel", asset?.approved_for_product ? "Checked quality and risk." : "Checking quality and risk."],
    ["Nova", review ? "Researched buyer demand, item look, and supplier product fit." : "Researching what buyers are looking for."],
    ["Ledger", hasPass ? "Protected profit with price, cost, fee, and margin checks." : "Pricing the product for profit."],
    ["Scribe", listing?.listing_id || productPackage?.listing?.title ? "Wrote Etsy SEO listing text." : "Writing Etsy SEO."],
    ["Publisher", productPackage ? `Package status: ${String(productPackage.publish_status || productPackage.status || "preparing").replaceAll("_", " ")}.` : "Preparing the Etsy listing package."]
  ];
}

function productPackageForProject(project, state) {
  return safeArray(state?.productPackages).find((pkg) =>
    safeArray(project?.relatedItems).some((item) => item.work_id && item.work_id === pkg.work_id)
    || (project?.design_package_id && pkg.design_package_id === project.design_package_id)
    || (project?.work_id && pkg.work_id === project.work_id)
  );
}

function projectProductOption(project, state, shiftData) {
  const review = project.review || projectReview(project, state, shiftData);
  const productPackage = productPackageForProject(project, state);
  if (productPackage?.variants?.length) {
    const variant = productPackage.variants.find((item) => item.included) || productPackage.variants[0];
    return {
      product_type: productPackage.product_type,
      product_name: productPackage.supplier_product_name,
      margin: productPackage.economics?.margin,
      profit: productPackage.economics?.projected_profit,
      target_price: variant?.item_price,
      supplier: productPackage.supplier
    };
  }
  return safeArray(review?.recommended_options).find((option) => option.ledger_pass)
    || safeArray(review?.recommended_options)[0]
    || safeArray(review?.product_options)[0]
    || null;
}

function projectSales(project, state) {
  const ids = new Set([
    project?.work_id,
    project?.design_package_id,
    productPackageForProject(project, state)?.package_id
  ].filter(Boolean));
  return safeArray(state?.salesOrders).filter((sale) =>
    [sale.work_id, sale.design_package_id, sale.package_id, sale.listing_id].some((id) => id && ids.has(id))
  );
}

function productGroupKey(project, state) {
  const review = project.review || projectReview(project, state, null);
  const asset = projectAsset(project, state);
  const imageUrl = getProjectImageUrl(project, state);
  const imagePath = review?.image_path || asset?.file_path || project.localImagePath || project.image_path || "";
  const stableKey = review?.design_package_id
    || project.design_package_id
    || asset?.design_package_id
    || asset?.promoted_design_id
    || review?.asset_id
    || project.asset_id
    || asset?.id
    || review?.image_url
    || imageUrl
    || imagePath;
  if (stableKey) return stableKey;
  if (project.status && !["complete", "approved", "denied", "needs_changes"].includes(project.status)) {
    return project.work_id || review?.review_id || `active-${project.worker_id || ""}-${project.created_at || ""}`;
  }
  return project.work_id || review?.review_id || `${project.worker_id || "product"}-${project.created_at || ""}`;
}

const PROJECT_STATUS_PRIORITY = {
  waiting_for_setup: 4,
  needs_attention: 4,
  blocked: 4,
  ready_for_review: 3,
  waiting_for_approval: 3,
  approval_ready: 3,
  repairing: 2,
  working: 2,
  running: 2,
  queued: 2,
  approved: 1,
  denied: 1,
  needs_changes: 1,
  complete: 1,
  completed: 1
};

const PROJECT_STAGE_PRIORITY = {
  blocked: 90,
  production_check: 80,
  approval_queue: 75,
  scribe_draft: 70,
  promote_to_design: 60,
  sentinel_qa: 50,
  image_generation: 40,
  prompt_planning: 30,
  complete: 10
};

function mergeProjectIntoGroup(groups, project, state, completed = false) {
  const key = productGroupKey(project, state);
  const existing = groups.get(key) || {
    ...project,
    group_key: key,
    representative: project,
    relatedItems: [],
    reviews: [],
    assets: [],
    blocked_reasons: [],
    completed_group: completed
  };
  const review = project.review || projectReview(project, state, null);
  const asset = projectAsset(project, state);
  existing.relatedItems.push(project);
  if (review && !existing.reviews.some((item) => item.review_id === review.review_id)) existing.reviews.push(review);
  if (asset && !existing.assets.some((item) => item.id === asset.id)) existing.assets.push(asset);
  existing.blocked_reasons = Array.from(new Set([
    ...safeArray(existing.blocked_reasons),
    ...safeArray(project.blocked_reasons),
    ...safeArray(review?.blocking_reasons),
    ...safeArray(review?.warnings)
  ]));

  const existingStatusPriority = PROJECT_STATUS_PRIORITY[existing.status] || 0;
  const projectStatus = review?.status === "blocked" ? "needs_attention" : (project.status || review?.status || "queued");
  const projectStatusPriority = PROJECT_STATUS_PRIORITY[projectStatus] || 0;
  const existingStagePriority = PROJECT_STAGE_PRIORITY[existing.stage] || 0;
  const projectStagePriority = PROJECT_STAGE_PRIORITY[project.stage] || 0;
  if (projectStatusPriority > existingStatusPriority || projectStagePriority > existingStagePriority) {
    existing.representative = project;
    existing.status = projectStatus;
    existing.stage = project.stage || existing.stage;
    existing.review = review || existing.review;
    existing.asset = asset || existing.asset;
  }
  existing.completed_group = existing.completed_group && completed;
  groups.set(key, existing);
}

function buildProductProjects(state, shiftData) {
  const queue = safeArray(shiftData?.queue);
  const reviews = [
    ...safeArray(shiftData?.reviews),
    ...safeArray(state?.productionReviews)
  ];
  const activeGroups = new Map();
  const completedGroups = new Map();

  queue.forEach((item) => {
    const review = projectReview(item, state, shiftData);
    const project = { ...item, review };
    if (item.status === "complete") {
      mergeProjectIntoGroup(completedGroups, project, state, true);
    } else {
      mergeProjectIntoGroup(activeGroups, project, state, false);
    }
  });

  reviews.forEach((review) => {
    const decision = review?.user_decision?.decision;
    const project = {
      status: decision || review.status,
      stage: decision ? "complete" : (review.status === "ready_for_review" ? "approval_queue" : "production_check"),
      asset_id: review.asset_id,
      design_package_id: review.design_package_id,
      production_review_id: review.review_id,
      review
    };
  if (decision || ["approved", "denied", "needs_changes"].includes(review.status)) {
      mergeProjectIntoGroup(completedGroups, project, state, true);
    } else {
      mergeProjectIntoGroup(activeGroups, project, state, false);
    }
  });

  return {
    active: [...activeGroups.values()],
    completed: [...completedGroups.values()]
  };
}

function productionReviewRows(review) {
  const recommended = safeArray(review?.recommended_options);
  return REVIEW_PRODUCT_TYPES.map((productType) => {
    const option = recommended.find((item) => normalizedKey(item.product_type) === normalizedKey(productType))
      || safeArray(review?.product_options).find((item) => normalizedKey(item.product_type) === normalizedKey(productType));
    if (!option) {
      return {
        productType,
        status: "BLOCKED",
        warning: "No saved production review option for this product type."
      };
    }
    const details = ledgerOptionDetails(option);
    return {
      productType,
      supplier: option.supplier,
      productName: option.product_name,
      variant: option.variant,
      provider: option.provider,
      baseCost: option.base_cost,
      shipping: option.shipping,
      targetPrice: option.target_price,
      profit: option.profit,
      margin: option.margin,
      status: details.pass ? "Ledger PASS" : "Ledger BLOCKED",
      badge: details.badge,
      warning: details.pass ? "" : (safeArray(option.warnings).concat(details.missing).filter(Boolean).join(", "))
    };
  });
}

function roomById(rooms, id) {
  return safeArray(rooms).find((room) => room.id === id);
}

function normalizeRecordItems(items) {
  return safeArray(items).map((item) => {
    if (typeof item === "string") {
      return {
        id: "Update",
        status: "info",
        text: cleanSystemPhrase(item)
      };
    }

    return {
      id: "Update",
      status: item.status || "info",
      text: cleanSystemPhrase(item.text || item.summary || item.title || item.id || "No update yet.")
    };
  }).filter((item) => item.text);
}

function normalizeRecords(groups) {
  const normalized = safeArray(groups).flatMap((group) => normalizeRecordItems(group.items || group));
  if (!normalized.length) return [];

  return [
    {
      title: "Updates",
      items: normalized
    }
  ];
}

function metricsToPairs(metrics) {
  if (!metrics) return [];

  if (Array.isArray(metrics)) {
    return metrics.map((pair) => {
      if (Array.isArray(pair)) return [titleCase(pair[0]), pair[1]];
      if (typeof pair === "object") return [titleCase(pair.label || pair.name), pair.value ?? pair.count ?? "—"];
      return ["Metric", pair];
    });
  }

  if (typeof metrics === "object") {
    return Object.entries(metrics).map(([key, value]) => [titleCase(key), value]);
  }

  return [];
}

function plainUpdatesToRecords(updates, needsUserAction) {
  const actionItems = safeArray(needsUserAction)
    .map(cleanSystemPhrase)
    .filter(Boolean)
    .map((text) => ({
      id: "Needs attention",
      status: "needs approval",
      text: text.endsWith(".") ? text : `${text}.`
    }));

  const updateItems = safeArray(updates)
    .map(cleanSystemPhrase)
    .filter(Boolean)
    .map((text) => ({
      id: "Update",
      status: "info",
      text
    }));

  const groups = [];

  if (actionItems.length) {
    groups.push({
      title: "Needs your attention",
      items: actionItems
    });
  }

  if (updateItems.length) {
    groups.push({
      title: "Updates",
      items: updateItems
    });
  }

  return groups;
}

function viewToTab(view, fallback) {
  if (!view) return fallback;

  const metrics = metricsToPairs(view.metrics);
  const records = plainUpdatesToRecords(view.plain_updates, view.needs_user_action);

  return {
    ...fallback,
    label: view.title || fallback.label,
    status: view.status || fallback.status,
    summary: cleanSystemPhrase(view.summary || fallback.summary),
    task: cleanSystemPhrase(view.current_job || fallback.task),
    verdict: cleanSystemPhrase(view.verdict || fallback.verdict),
    metrics: metrics.length ? metrics : fallback.metrics,
    records: records.length ? records : fallback.records
  };
}

function makeUltronTab(view, state, fallback) {
  if (!view) return fallback;

  const blockers = state?.latestAudit?.summary?.blockers ?? 0;
  const warnings = state?.latestAudit?.summary?.warnings ?? 0;
  const decisions = safeArray(state?.decisions).length;
  const candidates =
    safeArray(state?.board).length ||
    safeArray(state?.productCandidateBoard).length ||
    state?.counts?.product_candidate_board_items ||
    0;

  const safeLine = blockers === 0
    ? "Everything is safe right now."
    : `${blockers} blocker${blockers === 1 ? "" : "s"} need attention.`;

  const currentJob = cleanSystemPhrase(view.current_job || fallback.task || "No next action yet.");

  const actionItems = safeArray(view.needs_user_action)
    .map(cleanSystemPhrase)
    .filter(Boolean)
    .map((text) => ({
      id: "Needs attention",
      status: "needs approval",
      text: text.endsWith(".") ? text : `${text}.`
    }));

  const updateItems = safeArray(view.plain_updates)
    .map(cleanSystemPhrase)
    .filter(Boolean)
    .filter((line) => {
      const lower = line.toLowerCase();
      return !lower.includes("latest pipeline audit is pass")
        && !lower.includes("blockers:")
        && !lower.includes("decision queue has")
        && !lower.includes("product candidate board has");
    })
    .map((text) => ({
      id: "Warning",
      status: text.toLowerCase().startsWith("warning") ? "warning" : "info",
      text
    }));

  const records = [
    {
      title: "Commander summary",
      items: [
        { id: "Summary", status: "safe", text: safeLine },
        { id: "Warnings", status: warnings ? "warning" : "safe", text: `${warnings} warning${warnings === 1 ? "" : "s"}.` },
        { id: "Approvals", status: decisions ? "needs approval" : "clear", text: `${decisions} decision${decisions === 1 ? "" : "s"} need your approval.` },
        { id: "Products", status: "info", text: `${candidates} product candidate${candidates === 1 ? "" : "s"} are being tracked.` }
      ]
    },
    {
      title: "Next best action",
      items: [
        { id: "Next", status: "next", text: currentJob.endsWith(".") ? currentJob : `${currentJob}.` }
      ]
    }
  ];

  if (actionItems.length) {
    records.push({ title: "Needs your attention", items: actionItems });
  }

  if (updateItems.length) {
    records.push({ title: "Warnings", items: updateItems });
  }

  return {
    ...fallback,
    status: view.status || fallback.status,
    summary: "Ultron is watching the whole operation and only stops the agents when something is unsafe, missing, or needs your approval.",
    task: currentJob,
    verdict: `${safeLine} ${warnings} warning${warnings === 1 ? "" : "s"}. ${decisions} decision${decisions === 1 ? "" : "s"} need your approval.`,
    metrics: [
      ["Blockers", blockers],
      ["Warnings", warnings],
      ["Approvals", decisions],
      ["Products", candidates]
    ],
    records
  };
}

function makeTabs(state) {
  const rooms = safeArray(state?.agentRooms);
  const transcriptViews = state?.transcriptAgentViews || {};

  const overseer = roomById(rooms, "overseer");
  const nova = roomById(rooms, "nova");
  const forge = roomById(rooms, "forge");
  const sentinel = roomById(rooms, "sentinel");
  const ledger = roomById(rooms, "ledger");
  const scribe = roomById(rooms, "scribe");
  const publisher = roomById(rooms, "publisher");
  const api = roomById(rooms, "api");
  const archive = roomById(rooms, "archive");

  const fallbackTabs = {
    ultron: {
      id: "ultron",
      label: "Ultron",
      subtitle: "Overseer",
      icon: Shield,
      status: overseer?.status || state?.latestAudit?.status || "unknown",
      summary: overseer?.plainSummary || "Ultron watches the whole system and blocks unsafe steps.",
      task: overseer?.currentTask || "Checking what the agents have been doing.",
      verdict: overseer?.simpleVerdict || "No full summary yet.",
      metrics: [
        ["Audit", state?.latestAudit?.status || "unknown"],
        ["Blockers", state?.latestAudit?.summary?.blockers ?? 0],
        ["Warnings", state?.latestAudit?.summary?.warnings ?? 0],
        ["Approvals", safeArray(state?.decisions).length]
      ],
      records: normalizeRecords(overseer?.readableRecords)
    },
    nova: {
      id: "nova",
      label: "Nova",
      subtitle: "Research",
      icon: Brain,
      status: nova?.status || "waiting",
      summary: nova?.plainSummary || "Nova researches what people are buying.",
      task: nova?.currentTask || "Looking for products worth making.",
      verdict: nova?.simpleVerdict || "No product recommendation yet.",
      metrics: nova?.metrics || [],
      records: normalizeRecords(nova?.readableRecords)
    },
    forge: {
      id: "forge",
      label: "Forge",
      subtitle: "Images / Etsy",
      icon: Factory,
      status: forge?.status || "waiting",
      summary: forge?.plainSummary || "Forge creates images and product concepts for Etsy.",
      task: forge?.currentTask || "Waiting for a product idea from Nova.",
      verdict: forge?.simpleVerdict || "No paid image has been generated yet.",
      metrics: forge?.metrics || [],
      records: normalizeRecords(forge?.readableRecords)
    },
    communications: {
      id: "communications",
      label: "Comms",
      subtitle: "Comments",
      icon: Mail,
      status: "not connected yet",
      summary: "Communications collects comments and messages from YouTube, TikTok, Etsy, email, and other external sources.",
      task: "Waiting for platform connectors.",
      verdict: "Once connected, this should read like: Sarah said “Can I get this in blue?” on Etsy.",
      metrics: [
        ["YouTube", "not connected"],
        ["TikTok", "not connected"],
        ["Etsy", "not connected"],
        ["Email", "not connected"]
      ],
      records: [
        {
          title: "Updates",
          items: [
            { id: "Update", status: "planned", text: "Commenter name said “comment text” on TikTok, YouTube, Etsy, or email." }
          ]
        }
      ]
    },
    treasury: {
      id: "treasury",
      label: "Treasury",
      subtitle: "Money",
      icon: Coins,
      status: ledger?.status || "waiting",
      summary: ledger?.plainSummary || "Treasury shows profits, costs, items sold, ad spend, platform fees, and product margins.",
      task: ledger?.currentTask || "Waiting for cost and sales data.",
      verdict: ledger?.simpleVerdict || "No profit breakdown yet because live stores are not connected.",
      metrics: [
        ["Revenue", money(state?.businessMetrics?.totalRevenue)],
        ["Profit", money(state?.businessMetrics?.estimatedProfit)],
        ["Costs", money(state?.businessMetrics?.totalCost)],
        ["Products", state?.businessMetrics?.activeProducts ?? 0]
      ],
      records: normalizeRecords(ledger?.readableRecords)
    },
    scribe: {
      id: "scribe",
      label: "Scribe",
      subtitle: "Listings",
      icon: Store,
      status: scribe?.status || "waiting",
      summary: scribe?.plainSummary || "Scribe writes Etsy listings, titles, tags, and descriptions.",
      task: scribe?.currentTask || "Waiting for approved products.",
      verdict: scribe?.simpleVerdict || "No approved listing yet.",
      metrics: scribe?.metrics || [],
      records: normalizeRecords(scribe?.readableRecords)
    },
    media: {
      id: "media",
      label: "Media",
      subtitle: "Uploads",
      icon: Clapperboard,
      status: "planned",
      summary: "Media uploads videos to TikTok and YouTube. It can handle manual videos you drop in or content created by Vibes.",
      task: "Waiting for video upload workflow.",
      verdict: "This should eventually prepare captions, tags, schedules, and upload jobs.",
      metrics: [
        ["TikTok", "planned"],
        ["YouTube", "planned"],
        ["Scheduled", "planned"],
        ["Uploaded", "planned"]
      ],
      records: []
    },
    vibes: {
      id: "vibes",
      label: "Vibes",
      subtitle: "DJ / Assets",
      icon: Music,
      status: "planned",
      summary: "Vibes creates game assets, Fiverr YouTube thumbnails, music, and DJ-style beats.",
      task: "Waiting for creative tool workflow.",
      verdict: "This is a later expansion business after the Etsy/POD loop is stable.",
      metrics: [
        ["Music", "planned"],
        ["Game assets", "planned"],
        ["Thumbnails", "planned"],
        ["Fiverr", "planned"]
      ],
      records: []
    },
    sentinel: {
      id: "sentinel",
      label: "Sentinel",
      subtitle: "QA",
      icon: ImageIcon,
      status: sentinel?.status || "waiting",
      summary: sentinel?.plainSummary || "Sentinel checks images for quality and product readiness.",
      task: sentinel?.currentTask || "Waiting for images to review.",
      verdict: sentinel?.simpleVerdict || "No QA verdict yet.",
      metrics: sentinel?.metrics || [],
      records: normalizeRecords(sentinel?.readableRecords)
    },
    publisher: {
      id: "publisher",
      label: "Publisher",
      subtitle: "Products",
      icon: Upload,
      status: publisher?.status || "waiting",
      summary: publisher?.plainSummary || "Publisher prepares upload packages while live publishing stays locked.",
      task: publisher?.currentTask || "Waiting for products that pass every gate.",
      verdict: publisher?.simpleVerdict || "No publish package yet.",
      metrics: publisher?.metrics || [],
      records: normalizeRecords(publisher?.readableRecords)
    },
    archives: {
      id: "archives",
      label: "Archives",
      subtitle: "Memory",
      icon: Archive,
      status: archive?.status || "waiting",
      summary: archive?.plainSummary || "Archives stores memory, backups, state reports, and long-term records.",
      task: archive?.currentTask || "Keeping the project recoverable.",
      verdict: archive?.simpleVerdict || "No archive verdict yet.",
      metrics: archive?.metrics || [],
      records: normalizeRecords(archive?.readableRecords)
    },
    armory: {
      id: "armory",
      label: "Armory",
      subtitle: "Upgrades",
      icon: Sword,
      status: "planned",
      summary: "Armory tells you what upgrades have been made to the agents and what upgrades still need to be made.",
      task: "Waiting for upgrade tracking.",
      verdict: "This should become your agent improvement board.",
      metrics: [
        ["Upgrades made", "planned"],
        ["Upgrades needed", "planned"],
        ["Broken skills", "planned"],
        ["New tools", "planned"]
      ],
      records: []
    }
  };

  return [
    makeUltronTab(transcriptViews.ultron, state, fallbackTabs.ultron),
    viewToTab(transcriptViews.nova, fallbackTabs.nova),
    viewToTab(transcriptViews.forge, fallbackTabs.forge),
    viewToTab(transcriptViews.communications, fallbackTabs.communications),
    viewToTab(transcriptViews.treasury, fallbackTabs.treasury),
    viewToTab(transcriptViews.scribe, fallbackTabs.scribe),
    viewToTab(transcriptViews.media, fallbackTabs.media),
    viewToTab(transcriptViews.vibes, fallbackTabs.vibes),
    viewToTab(transcriptViews.sentinel, fallbackTabs.sentinel),
    viewToTab(transcriptViews.publisher, fallbackTabs.publisher),
    viewToTab(transcriptViews.archives, fallbackTabs.archives),
    viewToTab(transcriptViews.armory, fallbackTabs.armory)
  ];
}

function AgentDot({ index }) {
  const colors = ["gold", "blue", "cyan", "purple", "green", "orange", "red", "teal"];
  const color = colors[index % colors.length];

  return (
    <span
      className={`agent-dot ${color}`}
      style={{
        "--delay": `${index * -1.1}s`,
        "--x": `${10 + (index * 13) % 78}%`,
        "--y": `${18 + (index * 17) % 62}%`
      }}
    />
  );
}

function MapHalf({ state }) {
  return (
    <section className="map-half">
      <div className="map-bg" />
      <div className="scanlines" />

      {Array.from({ length: 18 }).map((_, index) => (
        <AgentDot key={index} index={index} />
      ))}

      <div className="money-badge">
        <b>{money(state?.businessMetrics?.totalRevenue)}</b>
      </div>
    </section>
  );
}

function TabButton({ tab, active, onClick }) {
  const Icon = tab.icon;

  return (
    <button className={`agent-tab ${active ? "active" : ""}`} onClick={onClick}>
      <Icon size={18} />
      <b>{tab.label}</b>
    </button>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b>{String(value ?? "—")}</b>
    </div>
  );
}

function DetailPanel({ tab }) {
  return (
    <section className="detail-panel">
      <div className="detail-head">
        <div>
          <span>{tab.subtitle}</span>
          <h1>{tab.label}</h1>
        </div>
        <StatusPill status={tab.status} />
      </div>

      <div className="simple-card">
        <h2>{tab.summary}</h2>
        <p>{tab.verdict}</p>
      </div>

      <div className="task-card">
        <span>Current job</span>
        <p>{tab.task}</p>
      </div>

      <div className="metric-grid">
        {safeArray(tab.metrics).map(([label, value]) => (
          <Metric key={label} label={label} value={value} />
        ))}
      </div>

      <div className="records clean-records">
        {safeArray(tab.records).length ? (
          safeArray(tab.records).flatMap((group) => safeArray(group.items)).length ? (
            safeArray(tab.records)
              .flatMap((group) => safeArray(group.items))
              .map((item, idx) => (
                <article className="record-card clean-card" key={idx}>
                  <p>{item.text}</p>
                </article>
              ))
          ) : (
            <div className="empty-state">Nothing here yet.</div>
          )
        ) : (
          <div className="empty-state">Nothing here yet.</div>
        )}
      </div>
    </section>
  );
}

function ChecklistRow({ ok, label, detail }) {
  return (
    <div className={`check-row ${ok ? "ok" : "needs"}`}>
      <span>{ok ? "PASS" : "CHECK"}</span>
      <b>{label}</b>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function ShiftMetric({ label, value }) {
  return (
    <div className="shift-metric">
      <span>{label}</span>
      <b>{String(value ?? 0)}</b>
    </div>
  );
}

function AutonomousShiftPanel() {
  const [shiftData, setShiftData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sentinelBusyId, setSentinelBusyId] = useState("");
  const [lastTickAt, setLastTickAt] = useState("");
  const [settings, setSettings] = useState({
    maxDesignsPerShift: "3",
    tickIntervalMs: "15000",
    allowedProductTypes: "sticker,poster,mug,t-shirt",
    preferredSupplier: "auto",
    destinationCountry: "US",
    destinationState: "TX",
    destinationZip: "79761",
    sticker: "11.99",
    poster: "19.99",
    mug: "18.99",
    tshirt: "24.99"
  });

  async function loadShiftStatus() {
    const res = await fetch(`${API_BASE}/api/agents/shift/status`);
    const data = await res.json();
    setShiftData(data);
  }

  async function shiftAction(action, body = {}) {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/agents/shift/${action}`, {
        method: action === "status" ? "GET" : "POST",
        headers: { "Content-Type": "application/json" },
        body: action === "status" ? undefined : JSON.stringify(body)
      });
      const data = await res.json();
      setShiftData(data);
      if (action === "tick") setLastTickAt(new Date().toLocaleTimeString());
    } finally {
      setBusy(false);
    }
  }

  function startShift() {
    shiftAction("start", {
      maxDesignsPerShift: Number(settings.maxDesignsPerShift),
      allowedProductTypes: settings.allowedProductTypes.split(",").map((item) => item.trim()).filter(Boolean),
      preferredSupplier: settings.preferredSupplier,
      destinationCountry: settings.destinationCountry,
      destinationState: settings.destinationState,
      destinationZip: settings.destinationZip,
      tickIntervalMs: Number(settings.tickIntervalMs),
      targetPrices: {
        sticker: Number(settings.sticker),
        poster: Number(settings.poster),
        mug: Number(settings.mug),
        "t-shirt": Number(settings.tshirt)
      }
    });
  }

  async function runSentinelForWork(item) {
    if (!item?.asset_id) return;
    setSentinelBusyId(item.work_id);
    try {
      await fetch(`${API_BASE}/api/sentinel/qa/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assetId: item.asset_id })
      });
      await loadShiftStatus();
    } finally {
      setSentinelBusyId("");
    }
  }

  useEffect(() => {
    loadShiftStatus();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      loadShiftStatus();
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const shift = shiftData?.shift || {};
  const loop = shiftData?.loop || {};
  const counters = shift.counters || {};
  const queue = safeArray(shiftData?.queue);
  const reviews = safeArray(shiftData?.reviews);
  const reviewById = (id) => reviews.find((review) => review.review_id === id);
  const publishReady = queue.filter((item) => ["approval_ready", "waiting_for_approval", "ready_to_publish", "waiting_for_live_publish"].includes(item.status) && hasLedgerPassOption(reviewById(item.production_review_id)));
  const attention = queue.filter((item) => ["blocked", "needs_attention", "waiting_for_setup"].includes(item.status)
    || (["approval_ready", "waiting_for_approval"].includes(item.status) && !hasLedgerPassOption(reviewById(item.production_review_id))));
  const blockedReviews = reviews.filter((review) => review.status === "blocked" || !hasLedgerPassOption(review));

  return (
    <section className="shift-panel">
      <div className="ledger-head">
        <div>
          <span>Autonomous Agents</span>
          <h3>Autonomous Shift</h3>
        </div>
        <StatusPill status={shift.status || "idle"} />
      </div>

      <div className="shift-actions">
        <button onClick={startShift} disabled={busy}>{shift.status === "running" && loop.active ? "Running automatically" : "Start Shift"}</button>
        <button onClick={() => shiftAction("pause")} disabled={busy}>Pause</button>
        <button onClick={() => shiftAction("resume")} disabled={busy}>Resume</button>
        <button onClick={() => shiftAction("stop")} disabled={busy}>Stop</button>
        <button onClick={() => shiftAction("tick")} disabled={busy}>Run One Tick Debug</button>
      </div>

      <div className="shift-settings">
        <label><span>Max designs</span><input type="number" min="1" max="10" value={settings.maxDesignsPerShift} onChange={(e) => setSettings({ ...settings, maxDesignsPerShift: e.target.value })} /></label>
        <label><span>Tick interval ms</span><input type="number" min="5000" max="60000" step="1000" value={settings.tickIntervalMs} onChange={(e) => setSettings({ ...settings, tickIntervalMs: e.target.value })} /></label>
        <label><span>Product types</span><input value={settings.allowedProductTypes} onChange={(e) => setSettings({ ...settings, allowedProductTypes: e.target.value })} /></label>
        <label><span>Supplier</span><select value={settings.preferredSupplier} onChange={(e) => setSettings({ ...settings, preferredSupplier: e.target.value })}><option value="auto">Auto</option><option value="printify">Printify</option><option value="printful">Printful</option></select></label>
        <label><span>Country</span><input value={settings.destinationCountry} onChange={(e) => setSettings({ ...settings, destinationCountry: e.target.value })} /></label>
        <label><span>State</span><input value={settings.destinationState} onChange={(e) => setSettings({ ...settings, destinationState: e.target.value })} /></label>
        <label><span>ZIP</span><input value={settings.destinationZip} onChange={(e) => setSettings({ ...settings, destinationZip: e.target.value })} /></label>
        <label><span>Sticker $</span><input type="number" step="0.01" value={settings.sticker} onChange={(e) => setSettings({ ...settings, sticker: e.target.value })} /></label>
        <label><span>Poster $</span><input type="number" step="0.01" value={settings.poster} onChange={(e) => setSettings({ ...settings, poster: e.target.value })} /></label>
        <label><span>Mug $</span><input type="number" step="0.01" value={settings.mug} onChange={(e) => setSettings({ ...settings, mug: e.target.value })} /></label>
        <label><span>T-shirt $</span><input type="number" step="0.01" value={settings.tshirt} onChange={(e) => setSettings({ ...settings, tshirt: e.target.value })} /></label>
        <div><span>Autonomous publish gates</span><b>No per-product approval</b></div>
      </div>

      <div className="shift-status-line">
        <p>{shift.current_task || "No active shift."}</p>
        <small>Agent loop: {loop.active ? `active every ${loop.intervalMs}ms` : "inactive"} {loop.running ? " / ticking now" : ""}</small>
        <small>Last automatic tick: {loop.lastTickAt || "not yet"} {shiftData?.locked ? " / tick locked" : ""}</small>
        <small>Last manual debug tick: {lastTickAt || "not yet"}</small>
        {shift.status === "running" && !loop.active ? <small className="loop-warning">Shift is marked running, but backend loop is inactive. Click Resume.</small> : null}
        {loop.lastTickError ? <small>{loop.lastTickError}</small> : null}
        {shift.last_error ? <small>{shift.last_error}</small> : null}
      </div>

      <div className="shift-metrics">
        {Object.entries(counters).map(([key, value]) => (
          <ShiftMetric key={key} label={titleCase(key)} value={value} />
        ))}
      </div>

      <div className="shift-queue">
        <span>Queue</span>
        {queue.length ? queue.map((item) => (
          <article key={item.work_id}>
            <div>
              <b>{item.work_id}</b>
              <StatusPill status={item.status} />
            </div>
            <p>{item.stage}</p>
            <small>{item.asset_id || "no asset"} {item.production_review_id ? ` / ${item.production_review_id}` : ""}</small>
            {item.sentinel_report_id || item.stage === "sentinel_qa" ? (
              <div className="sentinel-inline">
                <StatusPill status={item.approved_for_product ? "Sentinel approved" : (item.sentinel_status || "Sentinel pending")} />
                {item.sentinel_report_id ? <small>{item.sentinel_report_id}</small> : null}
                {safeArray(item.blocked_reasons).length ? <p>{safeArray(item.blocked_reasons).join(", ")}</p> : null}
                {safeArray(item.warnings).length ? <small>{safeArray(item.warnings).join(", ")}</small> : null}
              </div>
            ) : null}
            {item.asset_id ? (
              <button className="small-action" onClick={() => runSentinelForWork(item)} disabled={Boolean(sentinelBusyId)}>
                {sentinelBusyId === item.work_id ? "Running Sentinel..." : "Run Sentinel QA"}
              </button>
            ) : null}
          </article>
        )) : <p>No work queued.</p>}
      </div>

      <div className="shift-queue">
        <span>Ready To Publish</span>
        {publishReady.length ? publishReady.map((item) => (
          <article key={`publish-${item.work_id}`}>
            <div><b>{item.work_id}</b><StatusPill status={item.status} /></div>
            <p>{item.product_package_id || item.production_review_id || "Publisher package is being prepared."}</p>
          </article>
        )) : <p>No publish-ready packages.</p>}
      </div>

      <div className="shift-queue">
        <span>Repair / Setup Queue</span>
        {attention.length ? attention.map((item) => (
          <article key={`attention-${item.work_id}`}>
            <div><b>{item.work_id}</b><StatusPill status={item.status} /></div>
            <p>{safeArray(item.logs).slice(-1)[0]?.message || item.stage}</p>
            {safeArray(item.blocked_reasons).length ? <small>{safeArray(item.blocked_reasons).join(", ")}</small> : null}
          </article>
        )) : <p>No blocked items need attention.</p>}
      </div>

      <div className="shift-queue">
        <span>Blocked Production Reviews</span>
        {blockedReviews.length ? blockedReviews.slice(0, 6).map((review) => (
          <article key={`blocked-review-${review.review_id}`}>
            <div><b>{review.review_id}</b><StatusPill status="blocked" /></div>
            <p>{safeArray(review.blocking_reasons).slice(0, 4).join(", ") || "No Ledger PASS product option found."}</p>
          </article>
        )) : <p>No blocked production reviews.</p>}
      </div>

      <div className="shift-log">
        <span>Log</span>
        {safeArray(shiftData?.logTail).slice(0, 10).map((entry, index) => (
          <p key={`${entry.timestamp}-${index}`}>{entry.event}: {entry.message}</p>
        ))}
      </div>
    </section>
  );
}

function ForgeLocalArtPanel({ state, onStateChanged }) {
  const [health, setHealth] = useState(null);
  const [prompt, setPrompt] = useState("bold vector sticker design of a raccoon wearing a tiny welding helmet, holding a coffee mug, clean commercial t-shirt graphic, centered composition, thick outline, high contrast, transparent background style, no text");
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [sentinelBusy, setSentinelBusy] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [scribeBusy, setScribeBusy] = useState(false);
  const [economicsBusy, setEconomicsBusy] = useState(false);
  const [costBusy, setCostBusy] = useState(false);
  const [researchBusy, setResearchBusy] = useState(false);
  const [productionBusy, setProductionBusy] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [pipelineMessage, setPipelineMessage] = useState("");
  const [economicsForm, setEconomicsForm] = useState({
    supplier: "printify",
    productType: "poster",
    productId: "",
    variantId: "",
    targetPrice: "19.99",
    baseCost: "",
    shippingCost: ""
  });
  const [costForm, setCostForm] = useState({
    supplier: "printify",
    productType: "poster",
    productId: "",
    variantId: "",
    productName: "",
    variantName: "",
    baseCost: "",
    shippingCost: "",
    recommendedPrice: "",
    sourceUrl: "",
    notes: ""
  });
  const [researchForm, setResearchForm] = useState({
    preferredSupplier: "auto",
    productType: "poster",
    targetPrice: "19.99",
    destinationCountry: "US",
    destinationState: "TX",
    destinationZip: "79761",
    maxOptions: "8"
  });
  const [researchResult, setResearchResult] = useState(null);
  const [productionReview, setProductionReview] = useState(null);
  const [decisionNotes, setDecisionNotes] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const localAssets = safeArray(state?.imageAssets)
    .filter((asset) => asset?.provider_id === "local_comfyui" || String(asset?.status || "").includes("local_generated"))
    .sort((a, b) => String(b.created_at || b.updated_at || "").localeCompare(String(a.created_at || a.updated_at || "")));
  const resultAsset = result?.assetId
    ? localAssets.find((asset) => asset.id === result.assetId)
    : null;
  const latestAsset = resultAsset || result?.asset || localAssets[0] || null;
  const blockedTerms = findBlockedTerms(latestAsset, result, prompt);
  const waitingForSentinel = isWaitingForSentinel(latestAsset);
  const visualQa = latestVisualQaForAsset(state, latestAsset);
  const approvedBySentinel = sentinelProductApproved(state, latestAsset);
  const pipeline = linkedPipelineForAsset(state, latestAsset);
  const linkedDesignId = pipeline.design?.id || result?.design?.id || latestAsset?.promoted_design_id;
  const ledgerDecision = pipeline.ledger?.ledger_decision || pipeline.ledger?.decision || result?.ledger?.ledger_decision || result?.ledger?.decision || "missing";
  const nextAction = result?.nextSuggestedAction || (linkedDesignId ? "run_scribe_listing_draft" : "");
  const ledgerIssues = safeArray(pipeline.ledger?.issues || result?.economics?.issues);
  const ledgerCalc = pipeline.ledger?.calculation || result?.economics?.calculation || {};
  const matchedCostRow = matchingSupplierCost(state, economicsForm);
  const recentSupplierCosts = safeArray(state?.supplierCosts).slice(0, 5);
  const researchOptions = safeArray(researchResult?.options);
  const recommendedResearchOption = researchResult?.recommendedOption || researchOptions[0] || null;
  const savedReview = latestAsset
    ? safeArray(state?.productionReviews).find((review) => review.asset_id === latestAsset.id || review.design_package_id === linkedDesignId)
    : null;
  const activeProductionReview = productionReview || savedReview;
  const activeReviewCanApprove = hasLedgerPassOption(activeProductionReview);
  const reviewProductRows = activeProductionReview
    ? productionReviewRows(activeProductionReview)
    : recommendedProductRows(researchOptions, researchForm.targetPrice || economicsForm.targetPrice);
  const listingPreview = activeProductionReview?.listing_preview || pipeline.listing || {};
  const listingTags = safeArray(listingPreview.tags);

  async function refreshHealth() {
    try {
      const res = await fetch(`${API_BASE}/api/forge/art/health`);
      const data = await res.json();
      setHealth(data);
    } catch {
      setHealth({
        ok: false,
        provider: "comfyui",
        baseUrl: "http://127.0.0.1:8188",
        error: "SpaceCommand API is not reachable."
      });
    }
  }

  async function generateTestDesign() {
    setBusy(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/forge/art/generate-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          title: "Forge local test design",
          productType: "sticker"
        })
      });
      const data = await res.json();
      setResult(data);
      if (data.asset) {
        await onStateChanged?.();
      }
      if (!data.ok) {
        setError(data.error || "Local generation failed safely.");
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
      refreshHealth();
    }
  }

  async function sendToSentinel() {
    if (!latestAsset && !result?.localImagePath) return;

    setSending(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/art/send-to-sentinel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assetId: latestAsset?.id || result?.assetId,
          localImagePath: latestAsset?.file_path || result?.localImagePath,
          metadataPath: latestAsset?.metadata_path || result?.metadataPath
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not queue this image for Sentinel QA.");
        return;
      }
      setResult((current) => ({ ...(current || {}), asset: data.asset, assetId: data.asset?.id }));
      await onStateChanged?.();
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setSending(false);
    }
  }

  async function runSentinelQa() {
    if (!latestAsset?.id) return;

    setSentinelBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/sentinel/qa/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assetId: latestAsset.id,
          localImagePath: latestAsset.file_path,
          metadataPath: latestAsset.metadata_path
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Sentinel QA could not run.");
        return;
      }
      setResult((current) => ({
        ...(current || {}),
        asset: data.asset,
        assetId: data.asset?.id,
        sentinelReport: data.report
      }));
      setPipelineMessage(data.approved_for_product
        ? `Sentinel approved product use in ${data.reportId}.`
        : `Sentinel blocked product use: ${safeArray(data.blocked_reasons).join(", ") || "not product ready"}.`);
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setSentinelBusy(false);
    }
  }

  async function promoteToDesign() {
    if (!latestAsset?.id) return;

    setPromoting(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/art/promote-to-design`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assetId: latestAsset.id })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not promote this asset to a design.");
        return;
      }
      setResult((current) => ({
        ...(current || {}),
        asset: data.asset,
        assetId: data.asset?.id,
        design: data.design,
        ledger: data.ledger,
        nextSuggestedAction: data.nextSuggestedAction
      }));
      setPipelineMessage(`Linked design ${data.design?.id || "created"}.`);
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setPromoting(false);
    }
  }

  async function runScribeListingDraft() {
    if (!linkedDesignId) return;

    setScribeBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/art/run-scribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          designId: linkedDesignId,
          productType: latestAsset?.product_type || pipeline.design?.product_fit?.[0] || "poster"
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.stderr || data.error || "Scribe could not create a listing draft.");
        return;
      }
      setPipelineMessage("Scribe run finished. Listing draft status is shown below.");
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setScribeBusy(false);
    }
  }

  async function attachProductEconomics() {
    if (!linkedDesignId) return;

    setEconomicsBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/art/attach-product-economics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          designPackageId: linkedDesignId,
          supplier: economicsForm.supplier,
          productType: economicsForm.productType,
          productId: economicsForm.productId,
          variantId: economicsForm.variantId,
          targetPrice: economicsForm.targetPrice === "" ? null : Number(economicsForm.targetPrice)
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not attach product economics.");
        return;
      }
      setResult((current) => ({
        ...(current || {}),
        economics: data.economics,
        nextSuggestedAction: data.nextSuggestedAction
      }));
      setPipelineMessage(data.economics?.ledger_decision === "PASS"
        ? "Ledger PASS. Scribe can create the listing draft."
        : (data.connector?.message || "Ledger remains blocked until verified supplier costs pass."));
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setEconomicsBusy(false);
    }
  }

  async function attachManualEconomics() {
    if (!linkedDesignId) return;

    setEconomicsBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/art/manual-economics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          designPackageId: linkedDesignId,
          supplier: economicsForm.supplier,
          productType: economicsForm.productType,
          baseCost: economicsForm.baseCost === "" ? null : Number(economicsForm.baseCost),
          shippingCost: economicsForm.shippingCost === "" ? null : Number(economicsForm.shippingCost),
          targetPrice: economicsForm.targetPrice === "" ? null : Number(economicsForm.targetPrice),
          currency: "USD"
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not save manual economics.");
        return;
      }
      setResult((current) => ({
        ...(current || {}),
        economics: data.economics,
        nextSuggestedAction: data.nextSuggestedAction
      }));
      setPipelineMessage("Manual economics saved as unverified local test data. Publisher final publish remains blocked.");
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setEconomicsBusy(false);
    }
  }

  async function saveVerifiedCostRow() {
    setCostBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/supplier-costs/upsert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          supplier: costForm.supplier,
          productType: costForm.productType,
          productId: costForm.productId,
          variantId: costForm.variantId,
          productName: costForm.productName,
          variantName: costForm.variantName,
          baseCost: costForm.baseCost === "" ? null : Number(costForm.baseCost),
          shippingCost: costForm.shippingCost === "" ? null : Number(costForm.shippingCost),
          recommendedPrice: costForm.recommendedPrice === "" ? null : Number(costForm.recommendedPrice),
          currency: "USD",
          sourceUrl: costForm.sourceUrl,
          notes: costForm.notes
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not save verified supplier cost row.");
        return;
      }
      setPipelineMessage(`Verified cost row saved for ${data.row?.supplier} ${data.row?.product_id} / ${data.row?.variant_id}.`);
      setEconomicsForm((current) => ({
        ...current,
        supplier: data.row?.supplier || current.supplier,
        productType: data.row?.product_type || current.productType,
        productId: data.row?.product_id || current.productId,
        variantId: data.row?.variant_id || current.variantId,
        targetPrice: data.row?.recommended_price ? String(data.row.recommended_price) : current.targetPrice
      }));
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setCostBusy(false);
    }
  }

  async function researchSupplierCosts() {
    if (!linkedDesignId) return;

    setResearchBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/research/supplier-costs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          designPackageId: linkedDesignId,
          preferredSupplier: researchForm.preferredSupplier,
          productType: researchForm.productType,
          destinationCountry: researchForm.destinationCountry,
          destinationState: researchForm.destinationState,
          destinationZip: researchForm.destinationZip,
          targetPrice: researchForm.targetPrice === "" ? null : Number(researchForm.targetPrice),
          maxOptions: researchForm.maxOptions === "" ? 8 : Number(researchForm.maxOptions)
        })
      });
      const data = await res.json();
      setResearchResult(data);
      if (!data.ok) {
        setError(data.error || (data.missingConnector ? `Missing connector: ${data.missingConnector}` : "No supplier options found."));
        return;
      }
      setPipelineMessage(`Found ${safeArray(data.options).length} supplier option${safeArray(data.options).length === 1 ? "" : "s"}.`);
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setResearchBusy(false);
    }
  }

  async function applyRecommendedEconomics(option = recommendedResearchOption) {
    if (!linkedDesignId || !option) return;

    setEconomicsBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/research/apply-recommended-economics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          designPackageId: linkedDesignId,
          option,
          targetPrice: researchForm.targetPrice === "" ? null : Number(researchForm.targetPrice)
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not apply recommended economics.");
        return;
      }
      setResult((current) => ({
        ...(current || {}),
        economics: data.economics,
        nextSuggestedAction: data.nextSuggestedAction
      }));
      setPipelineMessage(data.economics?.ledger_decision === "PASS"
        ? "Recommended economics applied. Ledger PASS."
        : "Recommended economics applied, but Ledger remains blocked.");
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setEconomicsBusy(false);
    }
  }

  async function checkProduction() {
    if (!latestAsset?.id && !linkedDesignId) return;

    setProductionBusy(true);
    setError("");
    setPipelineMessage("Researching products, costs, shipping, Ledger fit, and listing preview...");

    try {
      const price = researchForm.targetPrice === "" ? 19.99 : Number(researchForm.targetPrice);
      const res = await fetch(`${API_BASE}/api/forge/production/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assetId: latestAsset?.id,
          designPackageId: linkedDesignId,
          preferredSupplier: researchForm.preferredSupplier,
          productTypes: REVIEW_PRODUCT_TYPES,
          destinationCountry: researchForm.destinationCountry,
          destinationState: researchForm.destinationState,
          destinationZip: researchForm.destinationZip,
          targetPrices: {
            sticker: price,
            poster: price,
            mug: price,
            "t-shirt": price
          },
          maxOptionsPerType: researchForm.maxOptions === "" ? 4 : Number(researchForm.maxOptions)
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Production check failed.");
        return;
      }
      setProductionReview(data.review);
      setPipelineMessage(`Production review saved: ${data.review?.review_id}.`);
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setProductionBusy(false);
    }
  }

  async function saveProductionDecision(decision) {
    const reviewId = activeProductionReview?.review_id;
    if (!reviewId) return;

    setDecisionBusy(true);
    setError("");
    setPipelineMessage("");

    try {
      const res = await fetch(`${API_BASE}/api/forge/production/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewId,
          decision,
          notes: decisionNotes
        })
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error || "Could not save production decision.");
        return;
      }
      setProductionReview(data.review);
      setPipelineMessage(`Production review ${data.review?.review_id} is ${data.review?.status}.`);
      if (data.state) {
        await onStateChanged?.();
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setDecisionBusy(false);
    }
  }

  useEffect(() => {
    refreshHealth();
  }, []);

  const imageUrl = result?.publicImageUrl
    ? `${API_BASE}${result.publicImageUrl}`
    : latestAsset?.public_preview_url
      ? `${API_BASE}${latestAsset.public_preview_url}`
    : "";

  return (
    <section className="forge-art-panel">
      <div className="forge-art-head">
        <div>
          <span>Local ComfyUI</span>
          <h2>Forge Local Art Generator</h2>
        </div>
        <StatusPill status={health?.ok ? "online" : "offline"} />
      </div>

      <p className="guardrail-copy">
        Local-only product art. Use clean product-ready PNG prompts with no copyrighted characters,
        no brands or logos, no celebrities, and no trademarked slogans.
      </p>

      <div className="health-line">
        <b>ComfyUI</b>
        <span>{health?.ok ? `Ready at ${health.baseUrl}` : (health?.error || "Checking local ComfyUI...")}</span>
      </div>

      <label className="prompt-box">
        <span>Product-art prompt</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={6}
        />
      </label>

      <button className="generate-art-button" onClick={generateTestDesign} disabled={busy}>
        {busy ? "Generating locally..." : "Generate Test Design"}
      </button>

      {error ? <p className="art-error">{error}</p> : null}

      {imageUrl ? (
        <div className="art-preview">
          <span className="preview-label">Generated image preview</span>
          <img src={imageUrl} alt="Generated Forge product art preview" />
          <div className="art-actions">
            {waitingForSentinel ? (
              <button className="generate-art-button queued" disabled>Waiting for Sentinel QA</button>
            ) : (
              <button className="generate-art-button" onClick={sendToSentinel} disabled={sending}>
                {sending ? "Sending..." : "Send to Sentinel QA"}
              </button>
            )}
            {latestAsset?.id ? (
              <button className="generate-art-button" onClick={runSentinelQa} disabled={sentinelBusy}>
                {sentinelBusy ? "Running Sentinel..." : "Run Sentinel QA"}
              </button>
            ) : null}
            {approvedBySentinel ? (
              <button className="generate-art-button" onClick={promoteToDesign} disabled={promoting}>
                {promoting ? "Promoting..." : "Promote to Design"}
              </button>
            ) : (
              <button className="generate-art-button queued" disabled>Requires Sentinel QA approval first</button>
            )}
          </div>
          {visualQa || latestAsset?.visual_qa_status ? (
            <div className="sentinel-inline">
              <StatusPill status={approvedBySentinel ? "approved_for_product" : (visualQa?.status || latestAsset?.visual_qa_status)} />
              <small>{visualQa?.id || latestAsset?.visual_qa || "Sentinel report pending"}</small>
              {safeArray(visualQa?.issues || latestAsset?.visual_qa_issues).length ? (
                <p>{safeArray(visualQa?.issues || latestAsset?.visual_qa_issues).join(", ")}</p>
              ) : null}
              {safeArray(visualQa?.warnings || latestAsset?.visual_qa_warnings).length ? (
                <small>{safeArray(visualQa?.warnings || latestAsset?.visual_qa_warnings).join(", ")}</small>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {imageUrl ? (
        <div className="product-review-panel">
          <div className="ledger-head">
            <div>
              <span>Review</span>
              <h3>Product Recommendation</h3>
            </div>
            <StatusPill status={activeProductionReview?.status || "draft"} />
          </div>

          <button className="generate-art-button" onClick={checkProduction} disabled={productionBusy || (!latestAsset?.id && !linkedDesignId)}>
            {productionBusy ? "Researching products, costs, shipping, Ledger fit, and listing preview..." : "Check Production"}
          </button>

          <div className="review-product-list">
            {reviewProductRows.map((row) => (
              <article className={row.status === "Ledger PASS" ? "review-pass" : ""} key={row.productType}>
                <div className="review-product-title">
                  <b>{row.productType}</b>
                  <StatusPill status={row.status} />
                </div>
                <StatusPill status={row.badge || row.status} />
                <div><span>Supplier</span><b>{row.supplier || "not researched"}</b></div>
                <div><span>Product</span><b>{row.productName || "not selected"}</b></div>
                <div><span>Variant</span><b>{row.variant || "not selected"}</b></div>
                <div><span>Base cost</span><b>{row.baseCost ?? "missing"}</b></div>
                <div><span>Shipping</span><b>{row.shipping ?? "missing"}</b></div>
                <div><span>Target price</span><b>{row.targetPrice || "missing"}</b></div>
                <div><span>Profit</span><b>{row.profit ?? "unknown"}</b></div>
                <div><span>Margin</span><b>{row.margin !== undefined ? `${row.margin}%` : "unknown"}</b></div>
                {row.warning ? <p>{row.warning}</p> : null}
              </article>
            ))}
          </div>

          <div className="listing-preview">
            <span>Listing preview</span>
            <h3>{listingPreview.title || "No listing draft yet"}</h3>
            <p>{listingPreview.description || listingPreview.blocked_reason || "Run Scribe Listing Draft after Ledger PASS to preview listing copy."}</p>
            <div className="tag-list">
              {listingTags.length ? listingTags.map((tag) => <b key={tag}>{tag}</b>) : <b>tags pending</b>}
            </div>
          </div>

        </div>
      ) : null}

      {latestAsset || result ? (
        <div className="readiness-list">
          <ChecklistRow ok={Boolean(latestAsset?.file_exists || latestAsset?.file_path || result?.localImagePath)} label="PNG exists" />
          <ChecklistRow ok={Boolean(latestAsset?.metadata_exists || latestAsset?.metadata_path || result?.metadataPath)} label="metadata exists" />
          <ChecklistRow ok={!blockedTerms.length} label="no known blocked IP terms" detail={blockedTerms.length ? blockedTerms.join(", ") : ""} />
          <ChecklistRow ok={waitingForSentinel} label="ready for Sentinel QA" />
          <ChecklistRow ok={approvedBySentinel} label="Sentinel QA status" detail={visualQa?.status || latestAsset?.visual_qa_status || "Sentinel has not approved this image for product use yet"} />
          <ChecklistRow ok={Boolean(latestAsset?.visual_qa || latestAsset?.visual_qa_status)} label="background review needed" detail={latestAsset?.visual_qa_status || "Sentinel has not reviewed this image yet"} />
        </div>
      ) : null}

      {linkedDesignId || pipelineMessage ? (
        <div className="pipeline-bridge">
          {pipelineMessage ? <p>{pipelineMessage}</p> : null}
          {linkedDesignId ? <div><span>Design</span><b>{linkedDesignId}</b></div> : null}
          <div><span>Ledger</span><b>{ledgerDecision}</b></div>
          <div><span>Listing</span><b>{pipeline.listing?.status || "not created"}</b></div>
          <div><span>Publish package</span><b>{pipeline.publishPackage?.status || "not created"}</b></div>
          {nextAction === "run_scribe_listing_draft" || linkedDesignId ? (
            <button className="generate-art-button" onClick={runScribeListingDraft} disabled={scribeBusy || !linkedDesignId}>
              {scribeBusy ? "Running Scribe..." : "Run Scribe Listing Draft"}
            </button>
          ) : null}
        </div>
      ) : null}

      {linkedDesignId ? (
        <div className="ledger-panel">
          <div className="ledger-head">
            <div>
              <span>Product Economics</span>
              <h3>Ledger</h3>
            </div>
            <StatusPill status={ledgerDecision} />
          </div>

          <div className="ledger-fields">
            <label>
              <span>Supplier</span>
              <select
                value={economicsForm.supplier}
                onChange={(event) => setEconomicsForm({ ...economicsForm, supplier: event.target.value })}
              >
                <option value="printify">Printify</option>
                <option value="printful">Printful</option>
                <option value="manual">Manual</option>
              </select>
            </label>
            <label>
              <span>Product type</span>
              <input
                value={economicsForm.productType}
                onChange={(event) => setEconomicsForm({ ...economicsForm, productType: event.target.value })}
                placeholder="poster"
              />
            </label>
            <label>
              <span>Product ID</span>
              <input
                value={economicsForm.productId}
                onChange={(event) => setEconomicsForm({ ...economicsForm, productId: event.target.value })}
                placeholder="poster_8x10"
              />
            </label>
            <label>
              <span>Variant ID</span>
              <input
                value={economicsForm.variantId}
                onChange={(event) => setEconomicsForm({ ...economicsForm, variantId: event.target.value })}
                placeholder="optional"
              />
            </label>
            <label>
              <span>Target price</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={economicsForm.targetPrice}
                onChange={(event) => setEconomicsForm({ ...economicsForm, targetPrice: event.target.value })}
              />
            </label>
            <label>
              <span>Manual base cost</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={economicsForm.baseCost}
                onChange={(event) => setEconomicsForm({ ...economicsForm, baseCost: event.target.value })}
                placeholder="manual only"
              />
            </label>
            <label>
              <span>Manual shipping</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={economicsForm.shippingCost}
                onChange={(event) => setEconomicsForm({ ...economicsForm, shippingCost: event.target.value })}
                placeholder="manual only"
              />
            </label>
          </div>

          <div className="cost-match-hint">
            <p>Ledger PASS requires a verified supplier_costs.json row matching supplier, product type, product ID, and variant ID.</p>
            <b>{matchedCostRow ? `Matching verified row found: ${matchedCostRow.product_name || matchedCostRow.product_id} / ${matchedCostRow.variant_name || matchedCostRow.variant_id}` : "No matching verified row yet."}</b>
          </div>

          <div className="ledger-actions">
            <button className="generate-art-button" onClick={attachProductEconomics} disabled={economicsBusy}>
              {economicsBusy ? "Checking economics..." : "Attach Product Economics"}
            </button>
            <button className="generate-art-button queued" onClick={attachManualEconomics} disabled={economicsBusy}>
              Manual Economics
            </button>
          </div>

          <div className="ledger-results">
            <div><span>Missing fields</span><b>{ledgerIssues.length ? ledgerIssues.join(", ") : "none"}</b></div>
            <div><span>Product cost</span><b>{ledgerCalc.production_cost ?? pipeline.ledger?.production_cost ?? "missing"}</b></div>
            <div><span>Etsy transaction fee</span><b>{ledgerCalc.etsy_transaction_fee ?? "unknown"}</b></div>
            <div><span>Etsy payment processing fee</span><b>{ledgerCalc.payment_processing_fee ?? "unknown"}</b></div>
            <div><span>Etsy listing/renewal fee per sale</span><b>{ledgerCalc.etsy_listing_renewal_fee_per_unit ?? ledgerCalc.etsy_listing_fee ?? "unknown"}</b></div>
            <div><span>Shipping buffer</span><b>{ledgerCalc.shipping_overlap_buffer ?? "2.00"}</b></div>
            <div><span>Estimated profit</span><b>{ledgerCalc.profit ?? "unknown"}</b></div>
            <div><span>Tax reserve</span><b>{ledgerCalc.tax_reserve_per_sale ?? "unknown"}</b></div>
            <div><span>Spendable per sale</span><b>{ledgerCalc.spendable_per_sale ?? "unknown"}</b></div>
            <div><span>Margin</span><b>{ledgerCalc.margin_percent !== undefined ? `${ledgerCalc.margin_percent}%` : "unknown"}</b></div>
            <div><span>Required margin</span><b>10%</b></div>
          </div>
        </div>
      ) : null}

      {linkedDesignId ? (
        <div className="supplier-research-panel">
          <div className="ledger-head">
            <div>
              <span>Research</span>
              <h3>Supplier Costs</h3>
            </div>
          </div>

          <div className="ledger-fields">
            <label>
              <span>Preferred supplier</span>
              <select
                value={researchForm.preferredSupplier}
                onChange={(event) => setResearchForm({ ...researchForm, preferredSupplier: event.target.value })}
              >
                <option value="auto">Auto</option>
                <option value="printify">Printify</option>
                <option value="printful">Printful</option>
              </select>
            </label>
            <label>
              <span>Product type</span>
              <input value={researchForm.productType} onChange={(event) => setResearchForm({ ...researchForm, productType: event.target.value })} placeholder="poster" />
            </label>
            <label>
              <span>Target price</span>
              <input type="number" min="0" step="0.01" value={researchForm.targetPrice} onChange={(event) => setResearchForm({ ...researchForm, targetPrice: event.target.value })} />
            </label>
            <label>
              <span>Ship country</span>
              <input value={researchForm.destinationCountry} onChange={(event) => setResearchForm({ ...researchForm, destinationCountry: event.target.value })} placeholder="US" />
            </label>
            <label>
              <span>Ship state</span>
              <input value={researchForm.destinationState} onChange={(event) => setResearchForm({ ...researchForm, destinationState: event.target.value })} placeholder="TX" />
            </label>
            <label>
              <span>Ship ZIP</span>
              <input value={researchForm.destinationZip} onChange={(event) => setResearchForm({ ...researchForm, destinationZip: event.target.value })} placeholder="79761" />
            </label>
            <label>
              <span>Max options</span>
              <input type="number" min="1" max="20" step="1" value={researchForm.maxOptions} onChange={(event) => setResearchForm({ ...researchForm, maxOptions: event.target.value })} />
            </label>
          </div>

          <button className="generate-art-button" onClick={researchSupplierCosts} disabled={researchBusy}>
            {researchBusy ? "Researching..." : "Research Costs"}
          </button>

          {researchResult?.missingConnector ? (
            <p className="research-message">Missing connector: {researchResult.missingConnector}</p>
          ) : null}

          {recommendedResearchOption ? (
            <div className="recommended-option">
              <span>Recommended</span>
              <b>{recommendedResearchOption.supplier} / {recommendedResearchOption.productName}</b>
              <small>{recommendedResearchOption.variantName || recommendedResearchOption.variantId}</small>
              <button className="generate-art-button" onClick={() => applyRecommendedEconomics(recommendedResearchOption)} disabled={economicsBusy}>
                {economicsBusy ? "Applying..." : "Apply Recommended Economics"}
              </button>
            </div>
          ) : null}

          <div className="supplier-options">
            {researchOptions.length ? researchOptions.map((option, index) => (
              <article className={option.ledgerWouldPass ? "option-pass" : ""} key={`${option.supplier}-${option.productId}-${option.variantId}-${index}`}>
                <div>
                  <span>{option.supplier}</span>
                  <b>{option.productName}</b>
                  <small>{option.variantName || option.variantId}</small>
                </div>
                <div><span>Provider</span><b>{option.providerName || "supplier"}</b></div>
                <div><span>Base</span><b>{option.baseCost ?? "?"}</b></div>
                <div><span>Shipping</span><b>{option.shippingCost ?? "missing"}</b></div>
                <div><span>Total</span><b>{option.totalCost ?? "unknown"}</b></div>
                <div><span>Profit</span><b>{option.estimatedProfit ?? "unknown"}</b></div>
                <div><span>Margin</span><b>{option.estimatedMarginPct !== undefined ? `${option.estimatedMarginPct}%` : "unknown"}</b></div>
                <div><span>Ledger</span><b>{option.ledgerWouldPass ? "would pass" : "blocked"}</b></div>
                {safeArray(option.warnings).length ? <p>{safeArray(option.warnings).join(", ")}</p> : null}
              </article>
            )) : (
              <p className="research-message">No researched supplier options yet.</p>
            )}
          </div>
        </div>
      ) : null}

      {linkedDesignId ? (
        <div className="supplier-cost-panel">
          <div className="ledger-head">
            <div>
              <span>Fallback Admin</span>
              <h3>Verified Supplier Cost Rows</h3>
            </div>
          </div>

          <div className="ledger-fields">
            <label>
              <span>Supplier</span>
              <select
                value={costForm.supplier}
                onChange={(event) => setCostForm({ ...costForm, supplier: event.target.value })}
              >
                <option value="printify">Printify</option>
                <option value="printful">Printful</option>
              </select>
            </label>
            <label>
              <span>Product type</span>
              <input value={costForm.productType} onChange={(event) => setCostForm({ ...costForm, productType: event.target.value })} placeholder="poster" />
            </label>
            <label>
              <span>Product ID</span>
              <input value={costForm.productId} onChange={(event) => setCostForm({ ...costForm, productId: event.target.value })} placeholder="poster_8x10" />
            </label>
            <label>
              <span>Variant ID</span>
              <input value={costForm.variantId} onChange={(event) => setCostForm({ ...costForm, variantId: event.target.value })} placeholder="blueprint-or-variant-id" />
            </label>
            <label>
              <span>Product name</span>
              <input value={costForm.productName} onChange={(event) => setCostForm({ ...costForm, productName: event.target.value })} placeholder="Poster 8x10" />
            </label>
            <label>
              <span>Variant name</span>
              <input value={costForm.variantName} onChange={(event) => setCostForm({ ...costForm, variantName: event.target.value })} placeholder="Matte / US" />
            </label>
            <label>
              <span>Base cost</span>
              <input type="number" min="0" step="0.01" value={costForm.baseCost} onChange={(event) => setCostForm({ ...costForm, baseCost: event.target.value })} />
            </label>
            <label>
              <span>Shipping cost</span>
              <input type="number" min="0" step="0.01" value={costForm.shippingCost} onChange={(event) => setCostForm({ ...costForm, shippingCost: event.target.value })} />
            </label>
            <label>
              <span>Suggested price</span>
              <input type="number" min="0" step="0.01" value={costForm.recommendedPrice} onChange={(event) => setCostForm({ ...costForm, recommendedPrice: event.target.value })} />
            </label>
            <label>
              <span>Source URL</span>
              <input value={costForm.sourceUrl} onChange={(event) => setCostForm({ ...costForm, sourceUrl: event.target.value })} placeholder="Printify/Printful page you checked" />
            </label>
            <label>
              <span>Notes</span>
              <input value={costForm.notes} onChange={(event) => setCostForm({ ...costForm, notes: event.target.value })} placeholder="How you verified the row" />
            </label>
          </div>

          <button className="generate-art-button" onClick={saveVerifiedCostRow} disabled={costBusy}>
            {costBusy ? "Saving..." : "Save Verified Cost Row"}
          </button>

          <div className="supplier-cost-table">
            {recentSupplierCosts.length ? recentSupplierCosts.map((row, index) => (
              <div key={`${row.supplier}-${row.product_id}-${row.variant_id}-${index}`}>
                <span>{row.supplier} / {row.product_type}</span>
                <b>{row.product_id || "product"} / {row.variant_id || row.variant || "variant"}</b>
                <small>Cost {row.production_cost ?? "?"} + ship {row.shipping_cost_us ?? "?"}</small>
              </div>
            )) : (
              <p>No verified supplier rows saved yet.</p>
            )}
          </div>
        </div>
      ) : null}

      {latestAsset || result ? (
        <div className="art-metadata">
          <div><span>Asset</span><b>{latestAsset?.id || result?.assetId || "not recorded yet"}</b></div>
          <div><span>Status</span><b>{latestAsset?.status || result?.asset?.status || "not queued"}</b></div>
          <div><span>Provider</span><b>{latestAsset?.provider_id || result?.provider || "comfyui"}</b></div>
          <div><span>Prompt</span><b>{result?.promptId || latestAsset?.image_generation_run_id || "not queued"}</b></div>
          <div><span>Seed</span><b>{result?.seed || "unknown"}</b></div>
          <div><span>Local path</span><b>{latestAsset?.file_path || result?.localImagePath || "none yet"}</b></div>
        </div>
      ) : null}
    </section>
  );
}

function ApiKeysModal({ state, onClose, onSaved }) {
  const [form, setForm] = useState({
    OPENAI_API_KEY: "",
    PRINTIFY_API_KEY: "",
    PRINTFUL_API_KEY: "",
    ETSY_API_KEY: "",
    ETSY_CLIENT_SECRET: "",
    ETSY_ACCESS_TOKEN: "",
    ETSY_REFRESH_TOKEN: "",
    ETSY_SHOP_ID: ""
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function saveKeys() {
    setSaving(true);
    setMessage("");

    try {
      const cleaned = {};
      Object.entries(form).forEach(([key, value]) => {
        if (String(value || "").trim()) cleaned[key] = value.trim();
      });

      const res = await fetch(`${API_BASE}/api/secrets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleaned)
      });

      const raw = await res.text();
      let data;

      try {
        data = JSON.parse(raw);
      } catch {
        setMessage("The backend did not return JSON. Make sure the SpaceCommand API server is running on http://127.0.0.1:4521.");
        return;
      }

      if (!data.ok) {
        setMessage(data.error || "Could not save keys.");
        return;
      }

      onSaved(data.state);
      setMessage("Saved. Agents can now read these keys from the local project secret files.");

      setForm({
        OPENAI_API_KEY: "",
        PRINTIFY_API_KEY: "",
        PRINTFUL_API_KEY: "",
        ETSY_API_KEY: "",
        ETSY_CLIENT_SECRET: "",
        ETSY_ACCESS_TOKEN: "",
        ETSY_REFRESH_TOKEN: "",
        ETSY_SHOP_ID: "",
    ETSY_CLIENT_SECRET: "",
    ETSY_ACCESS_TOKEN: "",
    ETSY_REFRESH_TOKEN: "",
    ETSY_SHOP_ID: ""
      });
    } catch (error) {
      setMessage(String(error?.message || error));
    } finally {
      setSaving(false);
    }
  }

  const rows = [
    ["OPENAI_API_KEY", "OpenAI Images"],
    ["PRINTIFY_API_KEY", "Printify"],
    ["PRINTFUL_API_KEY", "Printful"],
    ["ETSY_API_KEY", "Etsy API Key"],
    ["ETSY_CLIENT_SECRET", "Etsy Shared Secret"],
    ["ETSY_ACCESS_TOKEN", "Etsy Access Token"],
    ["ETSY_REFRESH_TOKEN", "Etsy Refresh Token"],
    ["ETSY_SHOP_ID", "Etsy Shop ID"]
  ];

  return (
    <div className="modal-backdrop">
      <aside className="api-modal">
        <div className="modal-head">
          <div>
            <span>Connector Bay</span>
            <h2>API Keys</h2>
          </div>
          <button onClick={onClose}>Close</button>
        </div>

        <div className="simple-card">
          <h2>Paste the key once. SpaceCommand saves it where the agents can use it.</h2>
          <p>
            Saved locally to _spacecommand_state/local_api_keys.json, .env.local, and ui/.env.local.
            Full keys are not shown back on screen.
          </p>
        </div>

        <div className="key-form">
          {rows.map(([key, label]) => (
            <label key={key}>
              <span>{label}</span>
              <small>Current: {state?.secretStatus?.[key] || "missing"}</small>
              <input
                type="password"
                value={form[key]}
                placeholder={`Paste ${label} key`}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </label>
          ))}

          <button className="save-key-button" onClick={saveKeys} disabled={saving}>
            {saving ? "Saving..." : "Save API Keys"}
          </button>

          {message ? <p className="save-message">{message}</p> : null}
        </div>
      </aside>
    </div>
  );
}

function ProjectThumbnail({ project, state }) {
  const imageUrl = getProjectImageUrl(project, state);
  return imageUrl ? (
    <img className="project-thumb" src={imageUrl} alt="" />
  ) : (
    <div className="project-thumb empty"><ImageIcon size={22} /></div>
  );
}

function ProjectCard({ project, state, shiftData, onOpen }) {
  const review = project.review || projectReview(project, state, shiftData);
  const representative = project.representative || project;
  const option = projectProductOption(project, state, shiftData);
  const marketKeyword = representative.market_keyword || representative.market_research?.item_look?.keyword || representative.prompt_family || project.market_research?.item_look?.keyword || "";
  const productIntent = option?.product_type || representative.product_intent || project.product_intent || "";
  const margin = option?.margin ?? option?.ledger_margin ?? option?.pricing_debug?.marginPercent;
  const warning = safeArray(project.blocked_reasons).map(getFriendlyBlockReason).filter(Boolean)[0]
    || safeArray(review?.blocking_reasons).map(getFriendlyBlockReason).filter(Boolean)[0]
    || safeArray(review?.warnings).map(getFriendlyBlockReason).filter(Boolean)[0];
  return (
    <button className="project-card" onClick={() => onOpen(project)}>
      <ProjectThumbnail project={project} state={state} />
      <div>
        <span>{getFriendlyStage(project.stage, project)}</span>
        <h3>{getProjectTitle(project, state, review)}</h3>
        <p>{getFriendlyStatus(project, review)}</p>
        {getWorkerLine(project) ? <i>{getWorkerLine(project)}</i> : null}
        {marketKeyword ? <i>Market idea: {marketKeyword}</i> : null}
        <i>{productIntent ? `Product: ${titleCase(productIntent)}` : "Product: choosing best fit"}{margin !== null && margin !== undefined && margin !== "" ? ` | Margin: ${margin}%` : ""}</i>
        {warning ? <small>{warning}</small> : null}
        {safeArray(project.relatedItems).length > 1 ? <em>{project.relatedItems.length} related agent tasks</em> : null}
      </div>
    </button>
  );
}

function CompletedRow({ project, state, shiftData, onOpen }) {
  const review = project.review || projectReview(project, state, shiftData);
  const productPackage = productPackageForProject(project, state);
  const status = productPackage?.publish_status === "dry_run_ready"
    ? "Listing package ready"
    : normalizeWorkStatus(project, review) === "listed"
      ? "Listed"
      : review?.listing_preview?.listing_id
        ? "Listing draft ready"
        : "Completed";
  return (
    <button className="completed-row" onClick={() => onOpen(project)}>
      <ProjectThumbnail project={project} state={state} />
      <div>
        <b>{getProjectTitle(project, state, review)}</b>
        <span>{status}</span>
      </div>
      <strong>{money(getProjectRevenue({ ...project, review_id: review?.review_id }, state))}</strong>
    </button>
  );
}

function ProductDetail({ project, state, shiftData, onBack, onDecisionSaved }) {
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState("");
  const review = project.review || projectReview(project, state, shiftData);
  const title = getProjectTitle(project, state, review);
  const imageUrl = getProjectImageUrl(review || project, state);
  const canDecide = false;
  const timeline = buildProjectTimeline(project, state, shiftData);
  const reasons = [
    ...safeArray(project.blocked_reasons),
    ...safeArray(review?.blocking_reasons),
    ...safeArray(review?.warnings)
  ].map(getFriendlyBlockReason).filter(Boolean);
  const firstOption = safeArray(review?.recommended_options)[0] || safeArray(review?.product_options)[0];
  const productOptions = safeArray(project.reviews).flatMap((item) => [
    ...safeArray(item.recommended_options),
    ...safeArray(item.product_options)
  ]);
  const relatedIds = safeArray(project.relatedItems).map((item) => item.work_id).filter(Boolean);
  const listing = review?.listing_preview || {};
  const market = project.market_research || project.representative?.market_research || projectAsset(project, state)?.market_research;
  const productPackage = productPackageForProject(project, state);
  const actualSales = projectSales(project, state);
  const actualRevenue = actualSales.reduce((sum, sale) => sum + (Number(sale.item_price || 0) * Number(sale.quantity || 1)), 0);
  const actualProfit = actualSales.reduce((sum, sale) => sum + Number(sale.net_profit || 0), 0);
  const calc = firstOption?.raw_option?.calculation || firstOption?.calculation || {};
  const projectedProfit = Number(firstOption?.profit ?? firstOption?.raw_option?.estimatedProfit ?? calc.profit);
  const projectedTax = Number.isFinite(projectedProfit) && projectedProfit > 0 ? projectedProfit * 0.30 : 0;
  const projectedSpendable = Number.isFinite(projectedProfit) && projectedProfit > 0 ? projectedProfit * 0.70 : 0;
  const retryActive = safeArray(project.ledger_retry_history).length || safeArray(project.representative?.ledger_retry_history).length;
  const correctedOption = productOptions.find((option) => option.corrected_target_price || option.correctedTargetPrice);
  const overCeilingOption = productOptions.find((option) => {
    const required = Number(option.required_price_for_ledger_pass ?? option.requiredPriceForLedgerPass);
    const ceiling = Number(option.product_price_ceiling ?? option.productPriceCeiling);
    return Number.isFinite(required) && Number.isFinite(ceiling) && required > ceiling;
  });

  async function saveDecision(decision) {
    if (!review?.review_id) return;
    setDecisionBusy(true);
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/forge/production/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewId: review.review_id, decision, notes })
      });
      const data = await res.json();
      if (!data.ok) {
        setMessage(data.error || "Could not save decision.");
        return;
      }
      setMessage(`Saved: ${data.review?.status || decision}.`);
      await onDecisionSaved?.();
    } finally {
      setDecisionBusy(false);
    }
  }

  return (
    <section className="product-detail">
      <button className="back-button" onClick={onBack}>Back</button>
      {imageUrl ? <img className="detail-image" src={imageUrl} alt="" /> : <div className="detail-image empty"><ImageIcon size={34} /></div>}
      <div className="detail-copy">
        <span>{getFriendlyStage(project.stage, project)}</span>
        <h2>{title}</h2>
        <p>{listing.description || "SpaceCommand is working this product through artwork, quality checks, supplier research, profit checks, and listing preparation."}</p>
      </div>

      {firstOption ? (
        <div className="detail-stats">
          <div><span>Supplier</span><b>{firstOption.supplier || "Not selected"}</b></div>
          <div><span>Product</span><b>{firstOption.product_name || firstOption.product_type || "Product pending"}</b></div>
          <div><span>Product cost</span><b>{firstOption.base_cost ?? "Missing"}</b></div>
          <div><span>Buyer-paid shipping estimate</span><b>{firstOption.shipping ?? "Not needed for item margin"}</b></div>
          <div><span>Shipping buffer</span><b>{firstOption.pricing_debug?.shippingOverlapBuffer ?? firstOption.raw_option?.shippingOverlapBuffer ?? "2.00"}</b></div>
          <div><span>Estimated profit</span><b>{firstOption.profit ?? "Unknown"}</b></div>
          <div><span>Margin</span><b>{firstOption.margin !== null && firstOption.margin !== undefined ? `${firstOption.margin}%` : "Unknown"}</b></div>
          <div><span>Projected spendable</span><b>{money(projectedSpendable)}</b></div>
          <div><span>Projected tax reserve</span><b>{money(projectedTax)}</b></div>
        </div>
      ) : null}

      {productPackage ? (
        <div className="plain-warning market-note">
          <b>Product package: {String(productPackage.publish_status || productPackage.status || "building").replaceAll("_", " ")}</b>
          <p>Selected product: {productPackage.supplier_product_name || productPackage.product_type || "pending"} with {safeArray(productPackage.variants).filter((variant) => variant.included).length} included variant{safeArray(productPackage.variants).filter((variant) => variant.included).length === 1 ? "" : "s"}.</p>
          <p>Quantity: {productPackage.listing?.quantity || "pending"} | Price: {Object.values(productPackage.listing?.prices || {})[0] ? money(Object.values(productPackage.listing.prices)[0]) : "pending"} | Margin: {productPackage.economics?.margin ?? "pending"}%</p>
          {safeArray(productPackage.blockers).length ? <p>{getFriendlyBlockReason(productPackage.blockers[0])}</p> : <p>Publisher has the package shape ready for the next safe listing step.</p>}
        </div>
      ) : null}

      <div className="detail-stats">
        <div><span>Actual sales</span><b>{actualSales.length}</b></div>
        <div><span>Actual revenue</span><b>{money(actualRevenue)}</b></div>
        <div><span>Actual profit</span><b>{money(actualProfit)}</b></div>
      </div>

      {market ? (
        <div className="plain-warning market-note">
          <b>Nova found: {market.item_look?.keyword || market.item_look?.theme || market.itemLook || "Product-ready design"}</b>
          <p>Item look: {market.item_look?.style || market.item_look?.subject || "Product-ready artwork"}</p>
          <p>Product direction: {safeArray(market.product_fit?.recommended_products).join(", ") || "product fit pending"}</p>
          <p>Research source: {market.source || "local_seed"} | SEO source: {market.seo_provider_used || project.seo_provider_used || "local_seed"} | Opportunity score: {market.opportunity_score ?? project.opportunity_score ?? "pending"}</p>
          <p>{market.product_fit?.reason || project.product_fit_reason || "Nova matched item look, seasonality, and product fit before Forge generated artwork."}</p>
        </div>
      ) : null}

      {retryActive ? (
        <div className="plain-warning market-note">
          <b>SpaceCommand is trying another product, supplier, or price.</b>
          <p>The agents are improving the product choice before it reaches Publisher.</p>
        </div>
      ) : null}

      {correctedOption ? (
        <div className="plain-warning market-note">
          <b>Ledger adjusted the price.</b>
          <p>Ledger raised the price from {money(correctedOption.original_target_price)} to {money(correctedOption.corrected_target_price || correctedOption.correctedTargetPrice)} so this product can make at least 10% profit.</p>
        </div>
      ) : overCeilingOption ? (
        <div className="plain-warning">
          <b>Agents are trying a better-margin product.</b>
          <p>This {overCeilingOption.product_type || "product"} would need to sell for {money(overCeilingOption.required_price_for_ledger_pass || overCeilingOption.requiredPriceForLedgerPass)} to pass, which is above the allowed ceiling of {money(overCeilingOption.product_price_ceiling || overCeilingOption.productPriceCeiling)}.</p>
        </div>
      ) : null}

      {productOptions.length ? (
        <div className="detail-options">
          <h3>Product options</h3>
          {productOptions.slice(0, 6).map((option, index) => (
            <div key={`${option.product_type || "option"}-${option.variant_id || index}`}>
              <b>{option.product_name || titleCase(option.product_type || "Product")}</b>
              <span>{option.supplier || "supplier pending"} / {option.variant || option.variant_id || "variant pending"}</span>
            </div>
          ))}
        </div>
      ) : null}

      {reasons.length ? (
        <div className="plain-warning">
          <b>Repairing</b>
          <p>{reasons[0]}</p>
        </div>
      ) : null}

      <div className="timeline">
        {timeline.map(([name, text]) => (
          <div key={name}>
            <b>{name}</b>
            <p>{text}</p>
          </div>
        ))}
      </div>

      {relatedIds.length ? (
        <details className="advanced-detail">
          <summary>Advanced details</summary>
          <p>{relatedIds.join(", ")}</p>
          <p>{safeArray(project.blocked_reasons).join(", ")}</p>
          {productOptions.length ? (
            <pre>{JSON.stringify(productOptions.map((option) => option.pricing_debug || {
              productType: option.product_type,
              supplier: option.supplier,
              productionCost: option.base_cost,
              shippingCost: option.shipping,
              originalTargetPrice: option.original_target_price,
              correctedTargetPrice: option.corrected_target_price,
              requiredPriceForLedgerPass: option.required_price_for_ledger_pass,
              ceilingPrice: option.product_price_ceiling,
              profit: option.profit,
              margin: option.margin,
              pass: option.ledger_pass,
              failReason: option.human_block_reason || safeArray(option.warnings).join(", ")
            }), null, 2)}</pre>
          ) : null}
        </details>
      ) : null}
    </section>
  );
}

function ProductionHome({ state, shiftData, onStart, onStop, onResume, onViewWork, onOpenProject, startBusy, hasEnteredDashboard }) {
  const shift = shiftData?.shift || {};
  const split = moneySplit(state);
  const { active, completed } = buildProductProjects(state, shiftData);
  const running = shift.status === "running";
  const plainStatus = mainAgentStatus(shift, active);

  if (!hasEnteredDashboard) {
    const hasPreviousWork = active.length || completed.length || shift.status === "running" || shift.status === "paused" || shift.status === "error";
    return (
      <main className="production-home idle-home">
        <div className="revenue-hero">
          <span>Revenue</span>
          <h1>{money(split.revenue)}</h1>
          <div className="money-split">
            <div><span>Spendable</span><b>{money(split.spendable)}</b></div>
            <div><span>Saved for Taxes</span><b>{money(split.taxReserve)}</b></div>
          </div>
          <p>{split.revenue > 0 ? "Sales are being recorded." : "No sales recorded yet."}</p>
        </div>
        <button className="start-shift-button" onClick={onStart} disabled={startBusy}>
          {startBusy ? "Starting..." : "Start Shift"}
        </button>
        <p className="idle-subtitle">Agents are idle. Start a shift to begin creating products.</p>
        {hasPreviousWork ? (
          <div className="previous-work">
            <p>Previous work is saved.</p>
            <div>
              <button onClick={onResume} disabled={startBusy}>{startBusy ? "Resuming..." : "Resume Previous Shift"}</button>
              <button onClick={onViewWork}>View Work</button>
            </div>
          </div>
        ) : null}
      </main>
    );
  }

  return (
    <main className="production-home running-home">
      <section className="production-top">
        <div>
          <span>Revenue</span>
          <h1>{money(split.revenue)}</h1>
          <div className="money-split">
            <div><span>Spendable</span><b>{money(split.spendable)}</b></div>
            <div><span>Saved for Taxes</span><b>{money(split.taxReserve)}</b></div>
          </div>
          <p>{split.revenue > 0 ? "Sales are being recorded." : "No sales recorded yet."}</p>
        </div>
        <div className={running ? "working-indicator active" : "working-indicator"}>
          <b>{plainStatus}</b>
          <span>{active.length ? `${active.length} product project${active.length === 1 ? "" : "s"}` : "Ready when you are"}</span>
        </div>
        <button className="stop-shift-inline" onClick={running ? onStop : onStart} disabled={startBusy}>
          {running ? "Stop" : "Start Shift"}
        </button>
      </section>

      <section className="production-section">
        <h2>Products Being Worked On</h2>
        <div className="project-grid">
          {active.length ? active.map((project, index) => (
            <ProjectCard key={project.group_key || project.work_id || project.production_review_id || index} project={project} state={state} shiftData={shiftData} onOpen={onOpenProject} />
          )) : <p className="empty-state">No active products right now.</p>}
        </div>
      </section>

      <section className="production-section completed-section">
        <h2>Completed / Listed Products</h2>
        <div className="completed-list">
          {completed.length ? completed.map((project, index) => (
            <CompletedRow key={project.group_key || project.work_id || project.production_review_id || index} project={project} state={state} shiftData={shiftData} onOpen={onOpenProject} />
          )) : <p className="empty-state">No completed products yet.</p>}
        </div>
      </section>
    </main>
  );
}

function AdvancedTools({ state, shiftData, loadState, rebuild, busy, setApiOpen, tabs, activeTab, activeId, setActiveId }) {
  const [open, setOpen] = useState(false);
  const diagnostics = shiftData?.diagnostics || {};
  const etsyPublisher = shiftData?.etsyPublisher || state?.etsyPublisher || {};
  const revenueSummary = state?.revenueSummary || {};
  const performance = safeArray(state?.listingPerformance);
  const topPerformers = performance.filter((item) => item.top_performer).length;
  const weakListings = performance.filter((item) => item.replace_when_sold_out).length;
  return (
    <section className="advanced-tools">
      <button className="advanced-toggle" onClick={() => setOpen(!open)}>
        {open ? "Hide Advanced" : "Advanced"}
      </button>
      {open ? (
        <div className="advanced-body">
          <p className="advanced-debug-line">
            Current shift: created {diagnostics.createdThisShift ?? 0} / {diagnostics.maxDesignsPerShift ?? 0} | Active workers: {diagnostics.activeForgeWorkers ?? 0} / {diagnostics.workerCount ?? 0} | Previous blocked work: {diagnostics.previousBlockedCount ?? 0} | Queued: {diagnostics.queuedWorkCount ?? 0} | Ready to publish: {diagnostics.approvalReadyCount ?? 0}
          </p>
          <p className="advanced-debug-line">
            Listing slots: {shiftData?.listingSlots?.used_listing_slots ?? 0} used / {shiftData?.listingSlots?.max_new_listings ?? 10} monthly | Remaining: {shiftData?.listingSlots?.remaining_listing_slots ?? 10}
          </p>
          <p className="advanced-debug-line">
            Etsy publisher: {etsyPublisher.publish_mode || "dry_run"} | Dry-run: {etsyPublisher.ready_for_dry_run ? "ready" : "blocked"} | Live: {etsyPublisher.ready_for_live ? "ready" : "not ready"} | Missing: {[
              !etsyPublisher.api_key_present ? "API key" : "",
              !etsyPublisher.client_secret_present ? "client secret" : "",
              !etsyPublisher.access_token_present ? "access token" : "",
              !etsyPublisher.refresh_token_present ? "refresh token" : "",
              !etsyPublisher.shop_id_present ? "shop ID" : ""
            ].filter(Boolean).join(", ") || "none"}
          </p>
          <p className="advanced-debug-line">
            Steward: {safeArray(state?.salesOrders).length} orders synced | Last revenue update: {revenueSummary.updated_at || "never"} | Net profit: {money(revenueSummary.net_profit)} | Tax reserve: {money(revenueSummary.saved_for_taxes)} | Top performers: {topPerformers} | Weak listings: {weakListings}
          </p>
          <div className="toolbar">
            <button onClick={loadState} disabled={busy}><RefreshCw size={15} /> Refresh</button>
            <button onClick={rebuild} disabled={busy}><Sparkles size={15} /> Rebuild</button>
            <button onClick={() => setApiOpen(true)}><KeyRound size={15} /> API Keys</button>
          </div>

          <div className="tab-grid">
            {tabs.map((tab) => (
              <TabButton key={tab.id} tab={tab} active={activeId === tab.id} onClick={() => setActiveId(tab.id)} />
            ))}
          </div>

          <DetailPanel tab={activeTab} />
          {activeTab?.id === "forge" ? (
            <>
              <AutonomousShiftPanel />
              <ForgeLocalArtPanel state={state} onStateChanged={loadState} />
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function App() {
  const [state, setState] = useState(null);
  const [shiftData, setShiftData] = useState(null);
  const [activeId, setActiveId] = useState("ultron");
  const [busy, setBusy] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [apiOpen, setApiOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState(null);
  const [hasEnteredDashboard, setHasEnteredDashboard] = useState(false);

  async function loadState() {
    const res = await fetch(`${API_BASE}/api/state`);
    const data = await res.json();
    setState(data);
  }

  async function loadShiftStatus() {
    const res = await fetch(`${API_BASE}/api/agents/shift/status`);
    const data = await res.json();
    setShiftData(data);
  }

  async function refreshAll() {
    await Promise.all([loadState(), loadShiftStatus()]);
  }

  async function rebuild() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/rebuild`, { method: "POST" });
      const data = await res.json();
      setState(data.state);
      await loadShiftStatus();
    } finally {
      setBusy(false);
    }
  }

  async function startShift() {
    setStartBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/agents/shift/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const data = await res.json();
      setShiftData(data);
      await loadState();
      setHasEnteredDashboard(true);
    } finally {
      setStartBusy(false);
    }
  }

  async function resumeShift() {
    setStartBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/agents/shift/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const data = await res.json();
      setShiftData(data);
      await loadState();
      setHasEnteredDashboard(true);
    } finally {
      setStartBusy(false);
    }
  }

  async function stopShift() {
    setStartBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/agents/shift/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const data = await res.json();
      setShiftData(data);
      await loadState();
    } finally {
      setStartBusy(false);
    }
  }

  function openProject(project) {
    setHasEnteredDashboard(true);
    setSelectedProject(project);
  }

  useEffect(() => {
    refreshAll();
    const timer = setInterval(refreshAll, 5000);
    return () => clearInterval(timer);
  }, []);

  const tabs = useMemo(() => makeTabs(state), [state]);
  const activeTab = tabs.find((tab) => tab.id === activeId) || tabs[0];

  if (!state) {
    return (
      <div className="boot">
        <div className="boot-orb" />
        <h1>SpaceCommand</h1>
        <p>Loading production dashboard...</p>
      </div>
    );
  }

  return (
    <div className="production-app">
      {selectedProject ? (
        <ProductDetail
          project={selectedProject}
          state={state}
          shiftData={shiftData}
          onBack={() => setSelectedProject(null)}
          onDecisionSaved={refreshAll}
        />
      ) : (
        <ProductionHome
          state={state}
          shiftData={shiftData}
          onStart={startShift}
          onStop={stopShift}
          onResume={resumeShift}
          onViewWork={() => setHasEnteredDashboard(true)}
          onOpenProject={openProject}
          startBusy={startBusy}
          hasEnteredDashboard={hasEnteredDashboard}
        />
      )}

      <AdvancedTools
        state={state}
        shiftData={shiftData}
        loadState={refreshAll}
        rebuild={rebuild}
        busy={busy}
        setApiOpen={setApiOpen}
        tabs={tabs}
        activeTab={activeTab}
        activeId={activeId}
        setActiveId={setActiveId}
      />

      {apiOpen && (
        <ApiKeysModal
          state={state}
          onClose={() => setApiOpen(false)}
          onSaved={(newState) => setState(newState)}
        />
      )}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
