declare const process: {
  cwd(): string;
  env: Record<string, string | undefined>;
};
declare function require(name: string): any;

const fs = require("node:fs");
const path = require("node:path");

export type SupplierResearchInput = {
  designPackageId: string;
  preferredSupplier?: "printify" | "printful" | "auto";
  productType?: string;
  destinationCountry?: string;
  destinationState?: string;
  destinationZip?: string;
  targetPrice?: number;
  maxOptions?: number;
};

export type SupplierResearchOption = {
  supplier: "printify" | "printful";
  productType: string;
  productId: string;
  variantId: string;
  productName: string;
  variantName?: string;
  providerName?: string;
  baseCost: number;
  shippingCost?: number;
  totalCost?: number;
  targetPrice?: number;
  shippingOverlapBuffer?: number;
  requiredPriceForLedgerPass?: number | null;
  requiredPriceForMargin?: number | null;
  currency: "USD";
  source: "live_api";
  supplierCostVerified: boolean;
  shippingCostVerified: boolean;
  available?: boolean;
  availability_quantity?: number | null;
  is_pod_made_to_order?: boolean;
  color?: string;
  size?: string;
  scent?: string;
  material?: string;
  estimatedProfit?: number;
  estimatedMarginPct?: number;
  ledgerWouldPass?: boolean;
  warnings?: string[];
  raw?: any;
};

export type SupplierResearchOutput = {
  ok: boolean;
  designPackageId: string;
  options: SupplierResearchOption[];
  savedCostRows: any[];
  recommendedOption?: SupplierResearchOption;
  error?: string;
  missingConnector?: string;
};

const ROOT = path.resolve(process.cwd(), "..");
const STATE = path.join(ROOT, "_spacecommand_state");
const PRINTIFY_API_BASE = "https://api.printify.com/v1";
const PRINTFUL_API_BASE = "https://api.printful.com";

function readJson(fileName: string, fallback: any): any {
  try {
    const filePath = path.join(STATE, fileName);
    if (!fs.existsSync(filePath)) return fallback;
    const text = fs.readFileSync(filePath, "utf8").trim();
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
}

function saveJson(fileName: string, data: any): void {
  fs.mkdirSync(STATE, { recursive: true });
  fs.writeFileSync(path.join(STATE, fileName), JSON.stringify(data, null, 2), "utf8");
}

function money(value: any): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function centsToDollars(value: any): number | null {
  const number = money(value);
  if (number === null) return null;
  return number > 100 ? number / 100 : number;
}

function normalizeKey(value: any): string {
  return String(value || "").trim().toLowerCase();
}

function productTerms(productType = ""): string[] {
  const raw = normalizeKey(productType);
  const terms = new Set<string>([raw]);
  if (raw === "poster") ["poster", "print", "wall art"].forEach((x) => terms.add(x));
  if (raw === "shirt" || raw === "tshirt" || raw === "t-shirt") ["shirt", "t-shirt", "tee"].forEach((x) => terms.add(x));
  if (raw === "sticker" || raw === "stickers") terms.add("sticker");
  if (raw === "mug") terms.add("mug");
  if (raw === "tote") ["tote", "bag"].forEach((x) => terms.add(x));
  return [...terms].filter(Boolean);
}

function textMatchesProduct(text: string, productType?: string): boolean {
  const haystack = normalizeKey(text);
  return productTerms(productType || "").some((term) => haystack.includes(term));
}

function numberConfig(name: string, fallback: number): number {
  const number = money(process.env[name]);
  return number === null ? fallback : number;
}

function computeProfit(option: SupplierResearchOption, targetPrice?: number): SupplierResearchOption {
  const price = money(targetPrice);
  const base = money(option.baseCost);
  const rules = readJson("pricing_rules.json", {});
  if (price === null || base === null) return option;

  const listingFee = money(rules.etsy_listing_renewal_fee_per_unit) ?? money(rules.etsy_listing_fee) ?? numberConfig("ETSY_LISTING_RENEWAL_FEE_PER_UNIT", numberConfig("ETSY_LISTING_FEE", 0.20));
  const txRate = money(rules.etsy_transaction_fee_percent) ?? numberConfig("ETSY_TRANSACTION_FEE_RATE", 0.065);
  const processingRate = money(rules.payment_processing_percent) ?? numberConfig("ETSY_PAYMENT_PROCESSING_RATE_US", 0.03);
  const processingFixed = money(rules.payment_processing_fixed) ?? numberConfig("ETSY_PAYMENT_PROCESSING_FIXED_US", 0.25);
  const shippingBuffer = money(rules.shipping_overlap_buffer) ?? numberConfig("SHIPPING_OVERLAP_BUFFER", 2.00);
  const minProfit = 0;
  const tx = price * txRate;
  const processing = price * processingRate + processingFixed;
  const totalCost = base + shippingBuffer + listingFee + tx + processing;
  const profit = price - totalCost;
  const margin = price > 0 ? profit / price : 0;
  const minMargin = numberConfig("MIN_PROFIT_MARGIN", 0.10);
  const fixedCost = base + shippingBuffer + listingFee + processingFixed;
  const variableRate = txRate + processingRate + minMargin;
  const requiredPriceForMargin = variableRate >= 1 ? null : fixedCost / (1 - variableRate);
  const requiredPrice = requiredPriceForMargin;

  return {
    ...option,
    targetPrice: price,
    totalCost: Number(totalCost.toFixed(2)),
    estimatedProfit: Number(profit.toFixed(2)),
    estimatedMarginPct: Number((margin * 100).toFixed(2)),
    shippingOverlapBuffer: Number(shippingBuffer.toFixed(2)),
    requiredPriceForMargin: requiredPriceForMargin === null ? null : Number(requiredPriceForMargin.toFixed(2)),
    requiredPriceForLedgerPass: requiredPrice === null ? null : Number(requiredPrice.toFixed(2)),
    ledgerWouldPass: Boolean(option.supplierCostVerified && profit > minProfit && margin >= minMargin)
  };
}

function dedupeOptions(options: SupplierResearchOption[]): SupplierResearchOption[] {
  const map = new Map<string, SupplierResearchOption>();
  for (const option of options || []) {
    const key = [
      normalizeKey(option.supplier),
      normalizeKey(option.productType),
      normalizeKey(option.productId || option.productName),
      normalizeKey(option.variantId || option.variantName),
      money(option.baseCost),
      money(option.shippingCost)
    ].join("|");
    const existing = map.get(key);
    if (!existing || ((option as any).score || 0) > ((existing as any).score || 0)) map.set(key, option);
  }
  return [...map.values()];
}

export function normalizeSupplierCostRow(raw: any): any {
  const verifiedAt = raw.verifiedAt || raw.verified_at || new Date().toISOString();
  return {
    ...(raw.existing || {}),
    supplier: normalizeKey(raw.supplier),
    product_type: normalizeKey(raw.productType || raw.product_type),
    product_id: String(raw.productId || raw.product_id || "").trim(),
    variant: String(raw.variantId || raw.variant_id || raw.variant || "").trim(),
    variant_id: String(raw.variantId || raw.variant_id || raw.variant || "").trim(),
    product_name: String(raw.productName || raw.product_name || "").trim(),
    variant_name: String(raw.variantName || raw.variant_name || "").trim(),
    provider_name: String(raw.providerName || raw.provider_name || "").trim(),
    production_cost: Number((money(raw.baseCost ?? raw.production_cost ?? 0) ?? 0).toFixed(2)),
    shipping_cost_us: raw.shippingCost === undefined || raw.shippingCost === null ? raw.existing?.shipping_cost_us ?? null : Number((money(raw.shippingCost) ?? 0).toFixed(2)),
    currency: "USD",
    recommended_price: raw.targetPrice ?? raw.recommended_price ?? raw.existing?.recommended_price,
    verified_supplier_cost: Boolean(raw.supplierCostVerified || raw.verified_supplier_cost),
    verified_shipping_cost: Boolean(raw.shippingCostVerified || raw.verified_shipping_cost),
    supplier_cost_verified: Boolean(raw.supplierCostVerified || raw.supplier_cost_verified),
    shipping_cost_verified: Boolean(raw.shippingCostVerified || raw.shipping_cost_verified),
    verification_source: raw.source === "live_api" ? "supplier_live_api" : raw.verification_source || "supplier_verified",
    source_url: raw.sourceUrl || raw.source_url || raw.existing?.source_url || "",
    notes: raw.notes || raw.existing?.notes || "Saved by supplier research scout. No publishing action was taken.",
    raw_api_excerpt: raw.raw ? { supplier: raw.supplier, productId: raw.productId, variantId: raw.variantId } : raw.existing?.raw_api_excerpt,
    verified_at: verifiedAt,
    updated_at: verifiedAt
  };
}

function upsertSavedCostRows(rows: SupplierResearchOption[]): any[] {
  const current = readJson("supplier_costs.json", []);
  const list = Array.isArray(current) ? current : [];
  const now = new Date().toISOString();
  const saved: any[] = [];
  for (const option of rows) {
    if (!option.supplierCostVerified) continue;
    const index = list.findIndex((row: any) =>
      normalizeKey(row.supplier) === normalizeKey(option.supplier)
      && normalizeKey(row.product_type) === normalizeKey(option.productType)
      && normalizeKey(row.product_id || row.id) === normalizeKey(option.productId)
      && normalizeKey(row.variant_id || row.variant) === normalizeKey(option.variantId)
    );
    const row = normalizeSupplierCostRow({ ...option, existing: index >= 0 ? list[index] : {}, verifiedAt: now });
    if (index >= 0) list[index] = row;
    else list.push(row);
    saved.push(row);
  }
  saveJson("supplier_costs.json", list);
  return saved;
}

export function scoreSupplierOption(option: SupplierResearchOption, designPackage: any): SupplierResearchOption & { score: number } {
  let score = 0;
  const warnings = [...(option.warnings || [])];
  const title = `${option.productName || ""} ${option.variantName || ""}`.toLowerCase();
  const productFit = Array.isArray(designPackage?.product_fit) ? designPackage.product_fit.map(normalizeKey) : [];
  if (productFit.includes(normalizeKey(option.productType))) score += 15;
  if (textMatchesProduct(title, option.productType)) score += 10;
  if (option.supplierCostVerified) score += 25;
  else warnings.push("base_cost_not_verified");
  if (option.shippingCostVerified) score += 25;
  else warnings.push("shipping_not_verified");
  if (option.ledgerWouldPass) score += 30;
  if (Number.isFinite(option.estimatedMarginPct)) score += Math.max(-10, Math.min(20, Number(option.estimatedMarginPct) / 2));
  return { ...option, warnings: [...new Set(warnings)], score: Number(score.toFixed(2)) };
}

async function fetchJson(url: string, init: RequestInit = {}): Promise<any> {
  const response = await fetch(url, init);
  const text = await response.text();
  let json: any = {};
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text };
  }
  if (!response.ok) throw new Error(json?.error?.message || json?.message || `HTTP ${response.status}`);
  return json;
}

function printifyHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${process.env.PRINTIFY_API_KEY}`, "Content-Type": "application/json" };
}

function printfulHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${process.env.PRINTFUL_API_KEY}`, "Content-Type": "application/json" };
}

function extractPrintifyShipping(shippingJson: any): number | null {
  const profiles = Array.isArray(shippingJson?.profiles) ? shippingJson.profiles : [];
  const rows = profiles.flatMap((profile: any) => Array.isArray(profile?.countries) ? profile.countries : []);
  const us = rows.find((row: any) => normalizeKey(row.country) === "united states" || normalizeKey(row.country_code) === "us") || rows[0];
  const first = Array.isArray(us?.shipping_costs) ? us.shipping_costs[0] : null;
  return centsToDollars(first?.first_item?.cost ?? first?.cost ?? us?.first_item_cost ?? us?.cost);
}

export async function researchPrintifyProducts(input: SupplierResearchInput): Promise<SupplierResearchOutput> {
  if (!process.env.PRINTIFY_API_KEY) return { ok: false, designPackageId: input.designPackageId, options: [], savedCostRows: [], missingConnector: "PRINTIFY_API_KEY", error: "Printify API key is missing." };
  const maxOptions = Math.max(1, Number(input.maxOptions || 6));
  const blueprintsJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints.json`, { headers: printifyHeaders() });
  const blueprints = (Array.isArray(blueprintsJson) ? blueprintsJson : blueprintsJson.data || []).filter((item: any) => textMatchesProduct(`${item.title || ""} ${item.brand || ""} ${item.model || ""}`, input.productType || "poster")).slice(0, 4);
  const options: SupplierResearchOption[] = [];
  for (const blueprint of blueprints) {
    const providersJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints/${blueprint.id}/print_providers.json`, { headers: printifyHeaders() });
    const providers = (Array.isArray(providersJson) ? providersJson : providersJson.data || []).slice(0, 3);
    for (const provider of providers) {
      const variantsJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints/${blueprint.id}/print_providers/${provider.id}/variants.json`, { headers: printifyHeaders() });
      let shippingCost: number | null = null;
      let shippingVerified = false;
      try {
        const shippingJson = await fetchJson(`${PRINTIFY_API_BASE}/catalog/blueprints/${blueprint.id}/print_providers/${provider.id}/shipping.json`, { headers: printifyHeaders() });
        shippingCost = extractPrintifyShipping(shippingJson);
        shippingVerified = shippingCost !== null;
      } catch {}
      const variants = (Array.isArray(variantsJson) ? variantsJson : variantsJson.variants || variantsJson.data || []).filter((variant: any) => variant.is_enabled !== false).slice(0, 4);
      for (const variant of variants) {
        const baseCost = centsToDollars(variant.cost ?? variant.price ?? variant.production_cost);
        if (baseCost === null) continue;
        options.push({
          supplier: "printify",
          productType: normalizeKey(input.productType || blueprint.title || "product"),
          productId: String(blueprint.id),
          variantId: String(variant.id),
          productName: blueprint.title || blueprint.name || `Printify ${blueprint.id}`,
          variantName: variant.title || String(variant.id),
          providerName: provider.title || provider.name || String(provider.id),
          baseCost: Number(baseCost.toFixed(2)),
          shippingCost: shippingCost === null ? undefined : Number(shippingCost.toFixed(2)),
          totalCost: shippingCost === null ? undefined : Number((baseCost + shippingCost).toFixed(2)),
          currency: "USD",
          source: "live_api",
          supplierCostVerified: true,
          shippingCostVerified: shippingVerified,
          available: variant.is_enabled !== false && variant.is_available !== false,
          availability_quantity: Number.isFinite(Number(variant.quantity ?? variant.availability_quantity)) ? Number(variant.quantity ?? variant.availability_quantity) : null,
          is_pod_made_to_order: true,
          color: variant.options?.color || variant.color || "",
          size: variant.options?.size || variant.size || "",
          scent: variant.options?.scent || "",
          material: variant.options?.material || variant.material || "",
          warnings: shippingVerified ? [] : ["shipping_not_available_from_printify_catalog"],
          raw: { blueprint, provider, variant }
        });
      }
    }
  }
  return { ok: true, designPackageId: input.designPackageId, options: options.slice(0, maxOptions), savedCostRows: [] };
}

function destinationFromInput(input: SupplierResearchInput): any | null {
  const country = input.destinationCountry || process.env.DEFAULT_SHIP_COUNTRY;
  const state = input.destinationState || process.env.DEFAULT_SHIP_STATE;
  const zip = input.destinationZip || process.env.DEFAULT_SHIP_ZIP;
  if (!country || !zip) return null;
  return { country_code: country, state_code: state || "", zip };
}

async function printfulShippingFor(variantId: string, input: SupplierResearchInput): Promise<{ shippingCost: number | null; verified: boolean; warning: string }> {
  const recipient = destinationFromInput(input);
  if (!recipient) return { shippingCost: null, verified: false, warning: "missing_destination_for_printful_shipping" };
  const json = await fetchJson(`${PRINTFUL_API_BASE}/shipping/rates`, {
    method: "POST",
    headers: printfulHeaders(),
    body: JSON.stringify({ recipient, items: [{ variant_id: Number(variantId), quantity: 1 }], currency: "USD" })
  });
  const rates = Array.isArray(json?.result) ? json.result : [];
  const rate = money(rates[0]?.rate);
  return { shippingCost: rate, verified: rate !== null, warning: rate === null ? "printful_shipping_rate_missing" : "" };
}

export async function researchPrintfulProducts(input: SupplierResearchInput): Promise<SupplierResearchOutput> {
  if (!process.env.PRINTFUL_API_KEY) return { ok: false, designPackageId: input.designPackageId, options: [], savedCostRows: [], missingConnector: "PRINTFUL_API_KEY", error: "Printful API key is missing." };
  const maxOptions = Math.max(1, Number(input.maxOptions || 6));
  const productsJson = await fetchJson(`${PRINTFUL_API_BASE}/products`, { headers: printfulHeaders() });
  const products = (Array.isArray(productsJson?.result) ? productsJson.result : []).filter((item: any) => textMatchesProduct(`${item.title || ""} ${item.type || ""} ${item.name || ""}`, input.productType || "poster")).slice(0, 5);
  const options: SupplierResearchOption[] = [];
  for (const product of products) {
    const productId = product.id || product.product_id;
    const detail = await fetchJson(`${PRINTFUL_API_BASE}/products/${productId}`, { headers: printfulHeaders() });
    const variants = (Array.isArray(detail?.result?.variants) ? detail.result.variants : Array.isArray(detail?.result) ? detail.result : []).slice(0, 6);
    for (const variant of variants) {
      const baseCost = money(variant.price ?? variant.retail_price ?? variant.cost);
      if (baseCost === null) continue;
      const shipping = await printfulShippingFor(String(variant.id), input);
      options.push({
        supplier: "printful",
        productType: normalizeKey(input.productType || product.type || product.title || "product"),
        productId: String(productId),
        variantId: String(variant.id),
        productName: product.title || product.name || `Printful ${productId}`,
        variantName: variant.name || variant.title || String(variant.id),
        providerName: "Printful",
        baseCost: Number(baseCost.toFixed(2)),
        shippingCost: shipping.shippingCost === null ? undefined : Number(shipping.shippingCost.toFixed(2)),
        totalCost: shipping.shippingCost === null ? undefined : Number((baseCost + shipping.shippingCost).toFixed(2)),
        currency: "USD",
        source: "live_api",
        supplierCostVerified: true,
        shippingCostVerified: shipping.verified,
        available: variant.in_stock !== false && variant.is_available !== false,
        availability_quantity: Number.isFinite(Number(variant.quantity ?? variant.availability_quantity)) ? Number(variant.quantity ?? variant.availability_quantity) : null,
        is_pod_made_to_order: true,
        color: variant.color || variant.options?.color || "",
        size: variant.size || variant.options?.size || "",
        scent: variant.scent || "",
        material: variant.material || "",
        warnings: shipping.warning ? [shipping.warning] : [],
        raw: { product, variant }
      });
    }
  }
  return { ok: true, designPackageId: input.designPackageId, options: options.slice(0, maxOptions), savedCostRows: [] };
}

export async function researchSupplierProducts(input: SupplierResearchInput): Promise<SupplierResearchOutput> {
  const designPackages = readJson("design_packages.json", []);
  const designPackage = designPackages.find((item: any) => item.id === input.designPackageId);
  const suppliers = input.preferredSupplier === "printify" ? ["printify"] : input.preferredSupplier === "printful" ? ["printful"] : ["printify", "printful"];
  const allOptions: SupplierResearchOption[] = [];
  let firstError = "";
  let missingConnector = "";
  for (const supplier of suppliers) {
    try {
      const result = supplier === "printify" ? await researchPrintifyProducts(input) : await researchPrintfulProducts(input);
      if (result.missingConnector && !missingConnector) missingConnector = result.missingConnector;
      if (result.error && !firstError) firstError = result.error;
      allOptions.push(...result.options);
    } catch (error: any) {
      if (!firstError) firstError = String(error?.message || error);
    }
  }
  const scored = dedupeOptions(allOptions)
    .map((option) => computeProfit(option, input.targetPrice))
    .map((option) => scoreSupplierOption(option, designPackage))
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, Math.max(1, Number(input.maxOptions || 8)));
  const savedCostRows = upsertSavedCostRows(scored);
  const recommendedOption = scored.find((option) => option.ledgerWouldPass) || scored[0];
  return {
    ok: scored.length > 0,
    designPackageId: input.designPackageId,
    options: scored,
    savedCostRows,
    recommendedOption,
    error: scored.length ? undefined : firstError || "No supplier options found.",
    missingConnector: scored.length ? undefined : missingConnector
  };
}
