import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");
const PACKAGES_FILE = path.join(DATA_DIR, "product_packages.json");
const DRY_RUNS_FILE = path.join(DATA_DIR, "etsy_publish_dry_runs.json");
const RESULTS_FILE = path.join(DATA_DIR, "etsy_publish_results.json");

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

function moneyOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function cleanTag(value) {
  return String(value || "").trim().slice(0, 20);
}

function publishMode(mode) {
  const requested = String(mode || process.env.ETSY_PUBLISH_MODE || "dry_run").trim().toLowerCase();
  return requested === "live" ? "live" : "dry_run";
}

function truthySecret(name) {
  return Boolean(String(process.env[name] || "").trim());
}

function listPackages() {
  const packages = readJson(PACKAGES_FILE, []);
  return Array.isArray(packages) ? packages : [];
}

function savePackage(pkg) {
  const packages = listPackages();
  const index = packages.findIndex((item) => item.package_id === pkg.package_id);
  if (index >= 0) packages[index] = pkg;
  else packages.push(pkg);
  writeJson(PACKAGES_FILE, packages);
  return pkg;
}

function updatePackage(packageId, patch) {
  const packages = listPackages();
  const index = packages.findIndex((item) => item.package_id === packageId);
  if (index < 0) return null;
  const updated = {
    ...packages[index],
    ...patch,
    updated_at: new Date().toISOString()
  };
  packages[index] = updated;
  writeJson(PACKAGES_FILE, packages);
  return updated;
}

function safeImageFile(filePath) {
  if (!filePath) return null;
  const resolved = path.resolve(filePath);
  return {
    path: resolved,
    exists: fs.existsSync(resolved),
    file_type: path.extname(resolved).replace(".", "").toLowerCase()
  };
}

function includedVariants(productPackage = {}) {
  return (Array.isArray(productPackage.variants) ? productPackage.variants : [])
    .filter((variant) => variant?.included !== false);
}

function firstPrice(productPackage = {}) {
  const prices = productPackage?.listing?.prices || {};
  const first = Object.values(prices).find((value) => moneyOrNull(value) !== null);
  return moneyOrNull(first);
}

export function getEtsyConnectorStatus() {
  const status = {
    api_key_present: truthySecret("ETSY_API_KEY"),
    client_secret_present: truthySecret("ETSY_CLIENT_SECRET"),
    access_token_present: truthySecret("ETSY_ACCESS_TOKEN"),
    refresh_token_present: truthySecret("ETSY_REFRESH_TOKEN"),
    shop_id_present: truthySecret("ETSY_SHOP_ID"),
    publish_mode: publishMode(),
    ready_for_dry_run: true,
    ready_for_live: false
  };
  status.ready_for_live = Boolean(
    status.api_key_present
    && status.client_secret_present
    && status.access_token_present
    && status.refresh_token_present
    && status.shop_id_present
    && status.publish_mode === "live"
  );
  return status;
}

export function buildEtsyListingPayload(productPackage = {}) {
  const listing = productPackage.listing || {};
  const variants = includedVariants(productPackage);
  const artwork = productPackage.artwork || {};
  const mockups = Array.isArray(productPackage.mockups) ? productPackage.mockups : [];
  const imageFiles = [
    safeImageFile(artwork.png_path),
    ...mockups.map((mockup) => safeImageFile(mockup.path || mockup.file_path || mockup.url))
  ].filter(Boolean);
  const quantity = Math.max(0, Number(listing.quantity || 0));
  const price = firstPrice(productPackage) ?? moneyOrNull(variants[0]?.item_price);
  return {
    package_id: productPackage.package_id || "",
    work_id: productPackage.work_id || "",
    design_package_id: productPackage.design_package_id || "",
    title: String(listing.title || "").trim(),
    description: String(listing.description || "").trim(),
    tags: (Array.isArray(listing.tags) ? listing.tags : []).map(cleanTag).filter(Boolean).slice(0, 13),
    price,
    quantity,
    who_made: listing.who_made || "i_did",
    when_made: listing.when_made || "made_to_order",
    taxonomy_id: listing.category_id || listing.taxonomy_id || null,
    shipping_profile_id: listing.shipping_profile_id || null,
    return_policy_id: listing.return_policy_id || null,
    materials: Array.isArray(listing.materials) ? listing.materials : [],
    image_files: imageFiles,
    variants: variants.map((variant) => ({
      supplier_variant_id: variant.supplier_variant_id || "",
      variant_name: variant.variant_name || "",
      color: variant.color || "",
      size: variant.size || "",
      scent: variant.scent || "",
      material: variant.material || "",
      sku: [
        productPackage.package_id,
        variant.supplier_variant_id || variant.variant_name
      ].filter(Boolean).join("-").replace(/[^a-z0-9_-]+/gi, "-").slice(0, 64),
      price: moneyOrNull(variant.item_price) ?? price,
      quantity: Number(variant.listing_quantity || quantity || 0),
      production_cost: moneyOrNull(variant.production_cost)
    })),
    sku: [productPackage.package_id, productPackage.product_type].filter(Boolean).join("-").replace(/[^a-z0-9_-]+/gi, "-").slice(0, 64),
    state: "draft",
    blocked_terms: productPackage.blocked_terms || [],
    production_partner: productPackage.production_partner || {
      required: false,
      partner_id: null
    },
    source_status: productPackage.status || ""
  };
}

export function validateEtsyListingPayload(payload = {}) {
  const blockers = [];
  const warnings = [];
  if (!payload.title) blockers.push("title_missing");
  if (!payload.description) blockers.push("description_missing");
  if (!Array.isArray(payload.tags) || payload.tags.length === 0) blockers.push("tags_missing");
  const imageFiles = Array.isArray(payload.image_files) ? payload.image_files : [];
  if (!imageFiles.length) blockers.push("image_files_missing");
  if (imageFiles.some((file) => !file.exists)) blockers.push("image_file_missing_on_disk");
  if (imageFiles.some((file) => file.file_type !== "png")) warnings.push("non_png_mockup_or_image_file_present");
  if (moneyOrNull(payload.price) === null) blockers.push("price_missing_or_invalid");
  if (!Number.isFinite(Number(payload.quantity)) || Number(payload.quantity) < 2) blockers.push("quantity_must_be_at_least_2");
  if (Number(payload.quantity) === 1) blockers.push("quantity_one_not_allowed");
  if (!payload.taxonomy_id) blockers.push("taxonomy_id_required");
  if (!payload.shipping_profile_id) blockers.push("shipping_profile_id_required");
  if (!Array.isArray(payload.variants) || payload.variants.length === 0) blockers.push("variants_missing");
  for (const variant of Array.isArray(payload.variants) ? payload.variants : []) {
    if (moneyOrNull(variant.price) === null) blockers.push("variant_price_missing");
    if (!Number.isFinite(Number(variant.quantity)) || Number(variant.quantity) < 2) blockers.push("variant_quantity_invalid");
  }
  const blockedTerms = Array.isArray(payload.blocked_terms) ? payload.blocked_terms : [];
  const searchable = `${payload.title} ${payload.description} ${(payload.tags || []).join(" ")}`.toLowerCase();
  for (const term of blockedTerms) {
    if (term && searchable.includes(String(term).toLowerCase())) blockers.push(`blocked_term_present:${term}`);
  }
  if (payload.production_partner?.required && !payload.production_partner?.partner_id) blockers.push("production_partner_required");
  return {
    ok: blockers.length === 0,
    blockers: [...new Set(blockers)],
    warnings: [...new Set(warnings)]
  };
}

function appendRecord(filePath, record, key = "id") {
  const rows = readJson(filePath, []);
  const list = Array.isArray(rows) ? rows : [];
  const index = list.findIndex((item) => record[key] && item[key] === record[key]);
  if (index >= 0) list[index] = record;
  else list.push(record);
  writeJson(filePath, list);
  return record;
}

export async function publishEtsyListing(productPackage = {}, { mode } = {}) {
  const effectiveMode = publishMode(mode);
  const connector = getEtsyConnectorStatus();
  const payload = buildEtsyListingPayload(productPackage);
  const validation = validateEtsyListingPayload(payload);
  const now = new Date().toISOString();

  if (effectiveMode === "dry_run") {
    const dryRun = {
      dry_run_id: `ETSYDRY-${Date.now()}`,
      package_id: productPackage.package_id || "",
      created_at: now,
      mode: "dry_run",
      payload,
      validation,
      connector_status: connector
    };
    appendRecord(DRY_RUNS_FILE, dryRun, "dry_run_id");
    const updatedPackage = updatePackage(productPackage.package_id, {
      publish_status: "dry_run_ready",
      publish_mode: "dry_run",
      dry_run_id: dryRun.dry_run_id,
      etsy_payload_validation: validation,
      etsy_payload_blockers: validation.blockers,
      etsy_payload_warnings: validation.warnings
    }) || savePackage({
      ...productPackage,
      publish_status: "dry_run_ready",
      publish_mode: "dry_run",
      dry_run_id: dryRun.dry_run_id,
      etsy_payload_validation: validation
    });
    return {
      ok: true,
      mode: "dry_run",
      status: "dry_run_ready",
      payload,
      validation,
      dryRun,
      productPackage: updatedPackage,
      warnings: validation.warnings,
      blockers: validation.blockers
    };
  }

  if (effectiveMode !== "live") {
    return { ok: false, mode: effectiveMode, status: "blocked", error: "Invalid Etsy publish mode.", payload, validation };
  }

  if (process.env.ETSY_PUBLISH_MODE !== "live") {
    return { ok: false, mode: "live", status: "blocked", error: "ETSY_PUBLISH_MODE must be live for live publishing.", payload, validation };
  }

  if (!connector.ready_for_live) {
    return {
      ok: false,
      mode: "live",
      status: "waiting_for_setup",
      error: "Etsy credentials are incomplete.",
      connector_status: connector,
      payload,
      validation
    };
  }

  if (!validation.ok) {
    return {
      ok: false,
      mode: "live",
      status: "waiting_for_setup",
      error: "Etsy listing payload is missing required setup fields.",
      payload,
      validation
    };
  }

  const result = {
    result_id: `ETSYPUB-${Date.now()}`,
    package_id: productPackage.package_id || "",
    created_at: now,
    mode: "live",
    status: "blocked_not_implemented",
    payload,
    error: "Etsy live publish image/variant step not implemented yet."
  };
  appendRecord(RESULTS_FILE, result, "result_id");
  updatePackage(productPackage.package_id, {
    publish_status: "waiting_for_setup",
    publish_mode: "live",
    etsy_live_blocker: result.error,
    etsy_payload_validation: validation
  });
  return {
    ok: false,
    mode: "live",
    status: "waiting_for_setup",
    error: result.error,
    payload,
    validation,
    result
  };
}

export function findProductPackage(packageId) {
  return listPackages().find((item) => item.package_id === packageId) || null;
}
