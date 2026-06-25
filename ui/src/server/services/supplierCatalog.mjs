import fs from "fs";
import path from "path";

const ROOT = path.resolve(process.cwd(), "..");
const STATE = path.join(ROOT, "_spacecommand_state");
const DATA = path.join(process.cwd(), "data");
const CATALOG_FILE = path.join(DATA, "supplier_product_catalog.json");
const LEGACY_CATALOG_FILE = path.join(STATE, "supplier_product_catalog.json");
const PRINTIFY_API_BASE = "https://api.printify.com/v1";
const PRINTFUL_API_BASE = "https://api.printful.com";

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) fs.mkdirSync(dirPath, { recursive: true });
}

function readJsonPath(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const text = fs.readFileSync(filePath, "utf8").trim();
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
}

function saveJsonPath(filePath, data) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
}

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function money(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function centsToDollars(value) {
  const number = money(value);
  if (number === null) return null;
  return number > 100 ? Number((number / 100).toFixed(2)) : Number(number.toFixed(2));
}

function words(value) {
  const raw = String(value || "").toLowerCase().replace(/[^a-z0-9\s-]+/g, " ").split(/\s+/).filter((word) => word.length > 2);
  const expanded = [];
  for (const word of raw) {
    expanded.push(word);
    if (["tee", "tshirt", "t-shirt"].includes(word)) expanded.push("shirt");
    if (word === "bag") expanded.push("tote");
    if (word === "print") expanded.push("poster");
  }
  return [...new Set(expanded)];
}

function detectProductType(...parts) {
  const text = parts.map((part) => String(part || "")).join(" ").toLowerCase();
  const tokens = words(text);
  const avoid = new Set(["printify", "printful", "custom", "all", "over", "print", "product"]);
  return tokens.find((token) => !avoid.has(token)) || "supplier_product";
}

async function fetchJson(url, init = {}) {
  const response = await fetch(url, init);
  const text = await response.text();
  let json = {};
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text };
  }
  if (!response.ok) {
    const message = json?.error?.message || json?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return json;
}

function normalizeLegacyProduct(row) {
  const cost = money(row.estimated_base_cost_usd);
  const productName = row.name || row.title || row.id || "Cached supplier product";
  return {
    supplier: row.supplier_preference || "local_cache",
    supplier_product_id: String(row.id || productName),
    supplier_blueprint_id: String(row.blueprint_id || row.id || ""),
    supplier_print_provider_id: String(row.print_provider_id || ""),
    product_name: productName,
    product_description: row.print_area_notes || row.forge_image_notes || "",
    product_type_detected: row.category || detectProductType(productName, row.category),
    category_detected: row.category || "",
    tags_detected: words(`${productName} ${row.category || ""} ${row.forge_image_notes || ""}`),
    variants: [
      {
        supplier_variant_id: String(row.variant_id || row.id || productName),
        name: productName,
        color: "",
        size: "",
        scent: "",
        material: "",
        other_options: {},
        production_cost: cost,
        availability_quantity: null,
        is_available: true,
        is_pod_made_to_order: true
      }
    ],
    variant_count: 1,
    has_variants: false,
    min_production_cost: cost,
    max_production_cost: cost,
    currency: "USD",
    source: "local_cache",
    fetched_at: new Date().toISOString()
  };
}

function normalizePrintifyBlueprint(blueprint, provider = {}, variants = []) {
  const productName = blueprint.title || blueprint.name || `Printify ${blueprint.id}`;
  const normalizedVariants = variants.map((variant) => ({
    supplier_variant_id: String(variant.id || variant.variant_id || ""),
    name: variant.title || variant.name || String(variant.id || ""),
    color: variant.options?.color || variant.color || "",
    size: variant.options?.size || variant.size || "",
    scent: variant.options?.scent || variant.scent || "",
    material: variant.options?.material || variant.material || "",
    other_options: variant.options || {},
    production_cost: centsToDollars(variant.cost ?? variant.price),
    availability_quantity: null,
    is_available: variant.is_enabled !== false && variant.is_available !== false,
    is_pod_made_to_order: true
  })).filter((variant) => variant.supplier_variant_id || variant.name);
  const costs = normalizedVariants.map((variant) => variant.production_cost).filter((value) => value !== null);
  return {
    supplier: "printify",
    supplier_product_id: String(blueprint.id || ""),
    supplier_blueprint_id: String(blueprint.id || ""),
    supplier_print_provider_id: String(provider.id || ""),
    product_name: productName,
    product_description: blueprint.description || blueprint.brand || blueprint.model || "",
    product_type_detected: detectProductType(productName, blueprint.description, blueprint.brand, blueprint.model),
    category_detected: blueprint.brand || "",
    tags_detected: words(`${productName} ${blueprint.description || ""} ${blueprint.brand || ""} ${blueprint.model || ""}`),
    variants: normalizedVariants,
    variant_count: normalizedVariants.length,
    has_variants: normalizedVariants.length > 1,
    min_production_cost: costs.length ? Math.min(...costs) : null,
    max_production_cost: costs.length ? Math.max(...costs) : null,
    currency: "USD",
    source: "printify_api",
    fetched_at: new Date().toISOString()
  };
}

function normalizePrintfulProduct(product, variants = []) {
  const productName = product.title || product.name || `Printful ${product.id}`;
  const normalizedVariants = variants.map((variant) => ({
    supplier_variant_id: String(variant.id || variant.variant_id || ""),
    name: variant.name || variant.title || String(variant.id || ""),
    color: variant.color || "",
    size: variant.size || "",
    scent: "",
    material: variant.material || "",
    other_options: variant,
    production_cost: centsToDollars(variant.price ?? variant.retail_price),
    availability_quantity: variant.availability_quantity ?? null,
    is_available: variant.in_stock !== false && variant.available !== false,
    is_pod_made_to_order: true
  })).filter((variant) => variant.supplier_variant_id || variant.name);
  const costs = normalizedVariants.map((variant) => variant.production_cost).filter((value) => value !== null);
  return {
    supplier: "printful",
    supplier_product_id: String(product.id || ""),
    supplier_blueprint_id: "",
    supplier_print_provider_id: "",
    product_name: productName,
    product_description: product.description || product.type || "",
    product_type_detected: detectProductType(productName, product.description, product.type),
    category_detected: product.type || "",
    tags_detected: words(`${productName} ${product.description || ""} ${product.type || ""}`),
    variants: normalizedVariants,
    variant_count: normalizedVariants.length,
    has_variants: normalizedVariants.length > 1,
    min_production_cost: costs.length ? Math.min(...costs) : null,
    max_production_cost: costs.length ? Math.max(...costs) : null,
    currency: "USD",
    source: "printful_api",
    fetched_at: new Date().toISOString()
  };
}

async function fetchPrintifyCatalog(maxProducts = 40) {
  if (!process.env.PRINTIFY_API_KEY) return { products: [], warning: "PRINTIFY_API_KEY missing" };
  const blueprintsJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints.json`, {
    headers: { Authorization: `Bearer ${process.env.PRINTIFY_API_KEY}` }
  });
  const blueprints = (Array.isArray(blueprintsJson) ? blueprintsJson : blueprintsJson.data || []).slice(0, maxProducts);
  const products = [];
  const warnings = [];
  for (const blueprint of blueprints) {
    try {
      const providersJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints/${blueprint.id}/print_providers.json`, {
        headers: { Authorization: `Bearer ${process.env.PRINTIFY_API_KEY}` }
      });
      const provider = (Array.isArray(providersJson) ? providersJson : providersJson.data || [])[0] || {};
      let variants = [];
      if (provider.id) {
        const variantsJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints/${blueprint.id}/print_providers/${provider.id}/variants.json`, {
          headers: { Authorization: `Bearer ${process.env.PRINTIFY_API_KEY}` }
        });
        variants = Array.isArray(variantsJson?.variants) ? variantsJson.variants : variantsJson.data || [];
      }
      products.push(normalizePrintifyBlueprint(blueprint, provider, variants));
    } catch (error) {
      warnings.push(`Printify ${blueprint.title || blueprint.id}: ${String(error.message || error)}`);
      products.push(normalizePrintifyBlueprint(blueprint, {}, []));
    }
  }
  return { products, warning: "", warnings };
}

async function fetchPrintfulCatalog(maxProducts = 80) {
  if (!process.env.PRINTFUL_API_KEY) return { products: [], warning: "PRINTFUL_API_KEY missing" };
  const productsJson = await fetchJson(`${PRINTFUL_API_BASE}/products`, {
    headers: { Authorization: `Bearer ${process.env.PRINTFUL_API_KEY}` }
  });
  const rows = (Array.isArray(productsJson?.result) ? productsJson.result : productsJson.data || []).slice(0, maxProducts);
  const products = [];
  const warnings = [];
  for (const product of rows) {
    try {
      const detailJson = await fetchJson(`${PRINTFUL_API_BASE}/products/${product.id}`, {
        headers: { Authorization: `Bearer ${process.env.PRINTFUL_API_KEY}` }
      });
      const detail = detailJson.result || detailJson.data || {};
      products.push(normalizePrintfulProduct(detail.product || product, detail.variants || []));
    } catch (error) {
      warnings.push(`Printful ${product.title || product.id}: ${String(error.message || error)}`);
      products.push(normalizePrintfulProduct(product, []));
    }
  }
  return { products, warning: "", warnings };
}

function readCachedCatalog() {
  const current = readJsonPath(CATALOG_FILE, null);
  if (Array.isArray(current?.products)) return current;
  const legacy = readJsonPath(LEGACY_CATALOG_FILE, null);
  if (Array.isArray(legacy?.products)) {
    const products = legacy.products.map(normalizeLegacyProduct);
    return {
      ok: true,
      products,
      sourceCounts: { local_cache: products.length },
      totalProducts: products.length,
      totalVariants: products.reduce((sum, item) => sum + item.variant_count, 0),
      suppliers: [...new Set(products.map((item) => item.supplier))],
      warnings: ["Using legacy local supplier catalog cache. Refresh Printify/Printful for live catalog products."],
      diagnostics: { fallback_used: true },
      fetched_at: new Date().toISOString()
    };
  }
  return {
    ok: false,
    products: [],
    sourceCounts: {},
    totalProducts: 0,
    totalVariants: 0,
    suppliers: [],
    warnings: ["No supplier catalog cache found."],
    diagnostics: { fallback_used: false },
    missingConnector: "PRINTIFY_API_KEY_OR_PRINTFUL_API_KEY"
  };
}

export function loadSupplierCatalog() {
  return readCachedCatalog();
}

export async function refreshSupplierCatalog(input = {}) {
  const maxPrintify = Math.max(1, Math.min(120, Number(input.maxPrintify || 50)));
  const maxPrintful = Math.max(1, Math.min(160, Number(input.maxPrintful || 100)));
  const warnings = [];
  const diagnostics = {
    printify_key_present: Boolean(process.env.PRINTIFY_API_KEY),
    printful_key_present: Boolean(process.env.PRINTFUL_API_KEY),
    endpoints_attempted: []
  };
  const products = [];

  try {
    diagnostics.endpoints_attempted.push("printify:/catalog/blueprints.json");
    const result = await fetchPrintifyCatalog(maxPrintify);
    products.push(...result.products);
    warnings.push(...(result.warning ? [result.warning] : []), ...(result.warnings || []));
  } catch (error) {
    warnings.push(`Printify catalog refresh failed: ${String(error.message || error)}`);
  }

  try {
    diagnostics.endpoints_attempted.push("printful:/products");
    const result = await fetchPrintfulCatalog(maxPrintful);
    products.push(...result.products);
    warnings.push(...(result.warning ? [result.warning] : []), ...(result.warnings || []));
  } catch (error) {
    warnings.push(`Printful catalog refresh failed: ${String(error.message || error)}`);
  }

  if (!products.length) {
    const cached = readCachedCatalog();
    return { ...cached, warnings: [...(cached.warnings || []), ...warnings], diagnostics: { ...cached.diagnostics, ...diagnostics, used_cache: Boolean(cached.products?.length) } };
  }

  const sourceCounts = products.reduce((map, item) => ({ ...map, [item.source]: (map[item.source] || 0) + 1 }), {});
  const payload = {
    ok: true,
    sourceCounts,
    totalProducts: products.length,
    totalVariants: products.reduce((sum, item) => sum + item.variant_count, 0),
    suppliers: [...new Set(products.map((item) => item.supplier))],
    products,
    warnings,
    diagnostics,
    fetched_at: new Date().toISOString()
  };
  saveJsonPath(CATALOG_FILE, payload);
  return payload;
}

function marketItemText(marketItem) {
  return [
    marketItem.market_keyword,
    marketItem.item_people_are_buying,
    marketItem.product_type_from_market,
    marketItem.itemLook?.style,
    marketItem.itemLook?.subject,
    marketItem.buyer_intent
  ].filter(Boolean).join(" ");
}

export function matchMarketItemToSupplierCatalog(marketItem = {}, supplierCatalog = {}) {
  const products = Array.isArray(supplierCatalog.products) ? supplierCatalog.products : [];
  const marketWords = words(marketItemText(marketItem));
  const marketPhrase = normalize(marketItemText(marketItem));
  const matches = products.map((product) => {
    const searchable = [
      product.product_name,
      product.product_description,
      product.product_type_detected,
      product.category_detected,
      ...(product.tags_detected || []),
      ...(product.variants || []).map((variant) => `${variant.name || ""} ${variant.color || ""} ${variant.size || ""}`)
    ].flat().join(" ");
    const productWords = words(searchable);
    const overlap = marketWords.filter((word) => productWords.includes(word));
    const phraseBonus = marketPhrase && normalize(searchable).includes(marketPhrase) ? 35 : 0;
    const typeBonus = marketItem.product_type_from_market && normalize(searchable).includes(normalize(marketItem.product_type_from_market)) ? 35 : 0;
    const intentBonus = marketWords.some((word) => normalize(product.product_name).includes(word)) ? 15 : 0;
    const costBonus = product.min_production_cost !== null && product.min_production_cost !== undefined ? 8 : 0;
    const matchScore = Math.min(100, phraseBonus + typeBonus + intentBonus + costBonus + overlap.length * 7);
    return {
      supplier: product.supplier,
      supplier_product_id: product.supplier_product_id,
      product_name: product.product_name,
      detected_product_type: product.product_type_detected,
      match_score: matchScore,
      match_reason: overlap.length
        ? `Matched catalog terms: ${overlap.slice(0, 8).join(", ")}.`
        : "Weak keyword overlap; kept only if no stronger supplier-backed match exists.",
      variant_count: product.variant_count,
      min_production_cost: product.min_production_cost,
      estimated_margin_potential: product.min_production_cost !== null ? "cost_available_for_ledger" : "cost_missing",
      supported: matchScore >= 20,
      catalog_product: product
    };
  }).filter((match) => match.supported).sort((a, b) => b.match_score - a.match_score);

  return {
    market_item: marketItem,
    matches,
    no_match_reason: matches.length ? "" : "No supplier catalog product matched this market item strongly enough."
  };
}

export function summarizeSupplierCatalog(catalog = loadSupplierCatalog()) {
  return {
    ok: Boolean(catalog.ok),
    sourceCounts: catalog.sourceCounts || {},
    totalProducts: catalog.totalProducts || catalog.products?.length || 0,
    totalVariants: catalog.totalVariants || (catalog.products || []).reduce((sum, item) => sum + Number(item.variant_count || 0), 0),
    suppliers: catalog.suppliers || [...new Set((catalog.products || []).map((item) => item.supplier))],
    warnings: catalog.warnings || [],
    diagnostics: catalog.diagnostics || {},
    fetched_at: catalog.fetched_at || "",
    missingConnector: catalog.missingConnector || ""
  };
}
