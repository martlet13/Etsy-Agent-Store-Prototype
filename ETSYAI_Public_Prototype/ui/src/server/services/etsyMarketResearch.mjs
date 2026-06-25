import fs from "fs";
import path from "path";

const ROOT = path.resolve(process.cwd(), "..");
const STATE = path.join(ROOT, "_spacecommand_state");
const DATA = path.join(process.cwd(), "data");
const SEED_FILES = [path.join(DATA, "etsy_market_seed.json"), path.join(STATE, "etsy_market_seed.json")];
const MARKET_MEMORY_FILE = path.join(DATA, "market_performance_memory.json");

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
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
}

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function hasEtsyConnector() {
  return Boolean(process.env.ETSY_API_KEY && process.env.ETSY_ACCESS_TOKEN && process.env.ETSY_SHOP_ID);
}

export function getCurrentSeasonalContext(date = new Date()) {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const iso = date.toISOString().slice(0, 10);
  if (month === 4 || (month === 5 && day <= 12)) return { season: "Mother's Day", reason: "Mother's Day gift shopping window", urgency: month === 5 ? "high" : "medium", date_context: iso };
  if (month === 5 || (month === 6 && day <= 20)) return { season: "Father's Day", reason: "Father's Day gift shopping window", urgency: "high", date_context: iso };
  if (month === 5 || month === 6) return { season: "graduation", reason: "Graduation gift season", urgency: "medium", date_context: iso };
  if (month >= 6 && month <= 8) return { season: "summer/outdoor", reason: "Summer hobby and travel season", urgency: "medium", date_context: iso };
  if (month === 8 || month === 9) return { season: "back to school", reason: "Teacher/student gift and classroom season", urgency: "medium", date_context: iso };
  if (month === 10) return { season: "fall/Halloween", reason: "Halloween and fall decor season", urgency: "high", date_context: iso };
  if (month === 11 || month === 12) return { season: "Christmas/holiday gifts", reason: "Holiday gift buying season", urgency: "high", date_context: iso };
  return { season: "evergreen gifts", reason: "Evergreen gifting and hobby niches", urgency: "low", date_context: iso };
}

function defaultSeeds() {
  return [
    ["mother's day floral mom gift", "retro floral coffee gift", ["mug", "tote", "t-shirt"], "mug", "Mother's Day", ["mom mug", "mothers day gift", "floral mom gift", "mama coffee"], ["mom gift", "mothers day", "floral mug", "mama gift", "coffee mom"]],
    ["grandma garden mug", "garden flowers grandma gift", ["mug", "tote", "poster"], "mug", "Mother's Day", ["grandma mug", "garden grandma gift", "nana coffee mug"], ["grandma gift", "nana mug", "garden mug", "floral gift"]],
    ["pet mom gift", "sweet pet parent floral art", ["t-shirt", "mug", "tote"], "t-shirt", "Mother's Day", ["pet mom shirt", "dog mom gift", "cat mom mug"], ["pet mom", "dog mom", "cat mom", "pet gift"]],
    ["new mom coffee shirt", "cozy new mom coffee artwork", ["t-shirt", "mug"], "t-shirt", "Mother's Day", ["new mom shirt", "new mom coffee", "mom life tee"], ["new mom", "mom coffee", "mom life", "new mama"]],
    ["mother-in-law floral tote", "minimal floral gift tote", ["tote", "mug"], "tote", "Mother's Day", ["mother in law gift", "floral tote", "gift tote"], ["mother in law", "floral tote", "mom tote"]],
    ["cozy mom coffee mug", "cozy coffee cup with soft florals", ["mug"], "mug", "Mother's Day", ["mom coffee mug", "cozy mom gift"], ["mom mug", "coffee gift", "cozy mom"]],
    ["retro floral mama design", "retro mama floral typography-free art", ["t-shirt", "mug", "tote"], "t-shirt", "Mother's Day", ["mama shirt", "retro mama", "floral mama"], ["mama shirt", "retro floral", "mom gift"]],
    ["minimalist mom line art", "minimal line art mother gift", ["poster", "card", "tote"], "poster", "Mother's Day", ["mom line art", "minimal mom gift"], ["line art", "mom gift", "minimalist"]],
    ["dad garage shirt", "garage tools dad gift artwork", ["t-shirt", "mug"], "t-shirt", "Father's Day", ["dad garage shirt", "father's day shirt"], ["dad shirt", "garage dad", "father gift"]],
    ["grandpa fishing mug", "fishing lake grandpa mug art", ["mug", "t-shirt"], "mug", "Father's Day", ["grandpa fishing mug", "fishing gift"], ["grandpa mug", "fishing mug", "dad gift"]],
    ["blue collar dad humor", "workshop dad coffee art", ["t-shirt", "mug"], "t-shirt", "Father's Day", ["blue collar dad", "mechanic dad shirt"], ["dad shirt", "blue collar", "mechanic"]],
    ["grilling dad gift", "grill tools dad gift artwork", ["apron", "t-shirt", "mug"], "t-shirt", "Father's Day", ["grilling dad gift", "bbq dad shirt"], ["grill dad", "bbq gift", "dad gift"]],
    ["senior 2026 shirt", "graduation class of 2026 style art", ["t-shirt", "mug"], "t-shirt", "graduation", ["senior 2026 shirt", "graduation shirt"], ["senior 2026", "grad shirt", "class of 2026"]],
    ["graduation gift mug", "college bound celebration mug", ["mug", "tote"], "mug", "graduation", ["graduation mug", "college bound gift"], ["grad gift", "graduation mug"]],
    ["college bound tote", "college bound tote artwork", ["tote", "t-shirt"], "tote", "graduation", ["college bound tote", "grad tote"], ["college bound", "grad tote"]],
    ["lake weekend shirt", "lake weekend outdoor art", ["t-shirt", "mug"], "t-shirt", "summer/outdoor", ["lake weekend shirt", "summer lake shirt"], ["lake shirt", "summer shirt"]],
    ["camping mug", "campfire coffee mug art", ["mug", "t-shirt"], "mug", "summer/outdoor", ["camping mug", "camp coffee"], ["camping mug", "camp mug"]],
    ["beach tote", "beach day tote artwork", ["tote"], "tote", "summer/outdoor", ["beach tote", "summer tote"], ["beach tote", "summer bag"]],
    ["spooky coffee mug", "cute ghost coffee art", ["mug", "t-shirt"], "mug", "fall/Halloween", ["spooky coffee mug", "halloween coffee"], ["spooky mug", "ghost mug"]],
    ["pumpkin teacher shirt", "pumpkin teacher autumn art", ["t-shirt", "mug"], "t-shirt", "fall/Halloween", ["pumpkin teacher shirt", "fall teacher"], ["teacher shirt", "pumpkin shirt"]],
    ["ghost pet mom tote", "ghost pet parent tote art", ["tote", "t-shirt"], "tote", "fall/Halloween", ["ghost pet mom", "halloween dog mom"], ["pet mom", "ghost tote"]],
    ["Christmas family mug", "cozy holiday family mug", ["mug"], "mug", "Christmas/holiday gifts", ["christmas family mug", "holiday mug"], ["christmas mug", "family gift"]],
    ["grandma ornament design", "holiday grandma ornament art", ["ornament", "mug"], "ornament", "Christmas/holiday gifts", ["grandma ornament", "nana ornament"], ["grandma gift", "ornament"]],
    ["cozy holiday sweatshirt", "cozy winter holiday art", ["hoodie", "sweatshirt", "mug"], "hoodie", "Christmas/holiday gifts", ["holiday sweatshirt", "christmas sweatshirt"], ["holiday shirt", "cozy gift"]],
    ["pet memorial", "gentle pet memorial line art", ["poster", "mug"], "poster", "evergreen gifts", ["pet memorial", "dog memorial gift"], ["pet memorial", "pet loss"]],
    ["nurse appreciation", "soft floral nurse appreciation gift", ["mug", "tote", "t-shirt"], "mug", "evergreen gifts", ["nurse gift", "nurse appreciation"], ["nurse gift", "nurse mug"]],
    ["teacher gift", "classroom floral teacher gift", ["mug", "tote", "t-shirt"], "mug", "evergreen gifts", ["teacher gift", "teacher mug"], ["teacher gift", "teacher mug"]],
    ["blue collar mechanic humor", "garage coffee mechanic art", ["t-shirt", "mug"], "t-shirt", "evergreen gifts", ["mechanic shirt", "blue collar gift"], ["mechanic", "blue collar"]],
    ["western cowboy coffee", "western boot coffee art", ["mug", "t-shirt", "poster"], "mug", "evergreen gifts", ["western mug", "cowboy coffee"], ["western mug", "cowboy gift"]],
    ["funny animal coffee", "original animal coffee art", ["mug", "t-shirt"], "mug", "evergreen gifts", ["funny coffee mug", "animal coffee"], ["coffee mug", "animal gift"]]
  ].map(([marketKeyword, look, productTypes, primaryProductType, seasonality, seoKeywords, tags], index) => ({
    marketKeyword, itemLook: look, productTypes, primaryProductType, buyerIntent: "gift buyer", seasonality,
    seoKeywords, tags, blockedTerms: [], riskLevel: "low",
    notes: "Local seasonal market seed. Not a top-selling claim.", opportunity_id: `LOCAL-${String(index + 1).padStart(3, "0")}`
  }));
}

function ensureSeedFile() {
  if (!fs.existsSync(SEED_FILES[0])) saveJsonPath(SEED_FILES[0], defaultSeeds());
}

function localSeedRows() {
  ensureSeedFile();
  for (const file of SEED_FILES) {
    const rows = readJsonPath(file, null);
    if (Array.isArray(rows) && rows.length) return rows;
  }
  return defaultSeeds();
}

export function scoreOpportunity(combination = {}) {
  const reasons = [];
  let score = 40;
  const source = combination.source || combination.demandSignal?.source || "local_seed";
  if (source === "etsy_api") { score += 20; reasons.push("Etsy API demand signal available."); }
  if (source === "everbee_export") { score += 18; reasons.push("EverBee export keyword signal available."); }
  if (source === "local_seed") { score += 8; reasons.push("Local seasonal seed fallback."); }
  const urgency = combination.seasonality?.urgency;
  if (urgency === "high") { score += 15; reasons.push("Strong seasonal timing."); }
  if (urgency === "medium") score += 8;
  if ((combination.itemLook?.riskLevel || combination.risk) === "low") score += 10;
  const products = combination.productFit?.productTypes || [];
  if (products.some((p) => !["sticker", "stickers"].includes(normalize(p)))) score += 8;
  if ((combination.seoSeed?.tags || []).length >= 10) score += 8;
  const memory = performanceMemoryFor(combination);
  if (memory?.orders > 0) {
    const boost = Math.min(20, Number(memory.score_adjustment || 0) || 8);
    score += boost;
    reasons.push(`Performance memory added ${boost} points from real sales.`);
  } else if (memory?.replace_when_sold_out || memory?.weak_signal) {
    score -= 10;
    reasons.push("Performance memory reduced score for a weak listing.");
  }
  score = Math.max(0, Math.min(100, Math.round(score)));
  const grade = score >= 80 ? "A" : score >= 65 ? "B" : score >= 50 ? "C" : "Reject";
  return { score, grade, reasons };
}

function performanceMemoryRows() {
  const rows = readJsonPath(MARKET_MEMORY_FILE, []);
  return Array.isArray(rows) ? rows : [];
}

function performanceMemoryFor(combination = {}) {
  const keyword = normalize(combination.marketKeyword);
  const products = (combination.productFit?.productTypes || []).map(normalize);
  return performanceMemoryRows().find((row) => {
    const rowKeyword = normalize(row.market_keyword);
    const rowProduct = normalize(row.product_type);
    return rowKeyword && keyword && (rowKeyword === keyword || keyword.includes(rowKeyword) || rowKeyword.includes(keyword))
      && (!rowProduct || products.includes(rowProduct));
  });
}

function combinationFromSeed(row, context, source = "local_seed") {
  const keyword = row.marketKeyword || row.keyword || "";
  const products = row.productTypes || row.productFitHints || ["mug", "t-shirt"];
  const primary = row.primaryProductType || products.find((p) => normalize(p) !== "sticker") || products[0] || "mug";
  const seasonality = { ...context, season: row.seasonality || context.season };
  const combo = {
    opportunity_id: row.opportunity_id || `${source}-${keyword}`.replace(/\W+/g, "-").toUpperCase(),
    marketKeyword: keyword,
    demandSignal: { source, searchSignal: source === "local_seed" ? "seasonal market seed" : "provider keyword signal", sellSignal: "not_available", confidence: source === "local_seed" ? 0.58 : 0.72, notes: row.notes || "" },
    itemLook: {
      style: row.style || row.itemLook || keyword,
      subject: row.subject || row.itemLook || keyword,
      colorHints: row.colorHints || (normalize(keyword).includes("floral") ? ["warm vintage", "soft floral"] : ["commercial palette"]),
      textMode: row.textMode || "minimal or no text",
      buyerIntent: row.buyerIntent || "gift buyer",
      riskLevel: row.riskLevel || "low",
      blockedTerms: row.blockedTerms || [],
      promptAngles: row.recommendedPromptAngles || row.promptAngles || [row.itemLook || keyword]
    },
    productFit: { productTypes: products, primaryProductType: primary, reason: row.notes || "Product types match gift intent and POD fit.", expectedBuyerUse: row.buyerIntent || "gift", supplierFitNotes: "Validate Printify/Printful economics before listing.", avoidProductTypes: row.avoidProductTypes || [] },
    seoSeed: { primaryKeyword: keyword, supportingKeywords: row.seoKeywords || [], tags: row.tags || [], titleAngles: row.titleAngles || [keyword] },
    seasonality,
    risk: row.riskLevel || "low",
    opportunityScore: 0,
    reason: row.notes || "Candidate opportunity from seasonal market seed.",
    source
  };
  const scored = scoreOpportunity(combo);
  combo.opportunityScore = scored.score;
  combo.grade = scored.grade;
  combo.scoreReasons = scored.reasons;
  return combo;
}

function topMarketItemFromSeed(row, index, context, source = "local_seed") {
  const keyword = row.marketKeyword || row.keyword || "";
  const productFromMarket = row.primaryProductType || row.product_type_from_market || row.productType || "";
  return {
    rank: index + 1,
    market_keyword: keyword,
    buyer_intent: row.buyerIntent || "gift buyer",
    item_people_are_buying: keyword,
    product_type_from_market: productFromMarket,
    item_look: {
      style: row.style || row.itemLook || keyword,
      subject: row.subject || row.itemLook || keyword,
      buyerIntent: row.buyerIntent || "gift buyer",
      riskLevel: row.riskLevel || "low",
      blockedTerms: row.blockedTerms || []
    },
    search_signal: source === "local_seed" ? "local seasonal market seed" : "provider keyword signal",
    sell_signal: "not_available",
    seasonality: row.seasonality || context.season,
    confidence: source === "local_seed" ? 0.58 : 0.72,
    source,
    notes: row.notes || "Candidate opportunity. Not a top-selling claim."
  };
}

async function etsyApiDiagnostics() {
  return {
    etsy_key_present: Boolean(process.env.ETSY_API_KEY),
    etsy_tokens_present: Boolean(process.env.ETSY_ACCESS_TOKEN && process.env.ETSY_REFRESH_TOKEN),
    endpoint_attempted: "",
    response_status: null,
    results_count: 0,
    fallback_used: true
  };
}

export async function researchEtsyTrends(input = {}) {
  const maxResults = Math.max(1, Math.min(25, Number(input.maxResults || 8)));
  const keyword = normalize(input.keyword);
  const productType = normalize(input.productType);
  const context = getCurrentSeasonalContext(new Date());
  const diagnostics = await etsyApiDiagnostics();
  const source = hasEtsyConnector() ? "local_seed" : "local_seed";
  const warnings = hasEtsyConnector()
    ? ["Etsy API credentials are present, but marketplace demand search is limited in this build; using local seed fallback."]
    : ["Etsy connector is missing; using local seasonal market seed. These are not top-selling claims."];

  const rows = localSeedRows()
    .filter((row) => !keyword || normalize(row.marketKeyword || row.keyword).includes(keyword) || normalize(row.itemLook).includes(keyword))
    .filter((row) => !productType || (row.productTypes || []).map(normalize).includes(productType))
    .sort((a, b) => (normalize(b.seasonality) === normalize(context.season) ? 1 : 0) - (normalize(a.seasonality) === normalize(context.season) ? 1 : 0))
    .slice(0, maxResults);
  const topMarketItems = rows.slice(0, 5).map((row, index) => topMarketItemFromSeed(row, index, context, source));
  const recommendedCombinations = rows.map((row) => combinationFromSeed(row, context, source)).sort((a, b) => b.opportunityScore - a.opportunityScore);
  return {
    ok: true,
    source,
    seasonality: context,
    topMarketItems,
    supplierMatches: [],
    itemLooks: recommendedCombinations.map((item) => item.itemLook),
    productMatches: recommendedCombinations.map((item) => item.productFit),
    recommendedCombinations,
    trends: rows,
    blockedTerms: [...new Set(recommendedCombinations.flatMap((item) => item.itemLook.blockedTerms || []))],
    warnings,
    confidence: recommendedCombinations[0]?.demandSignal?.confidence || 0.55,
    diagnostics: { ...diagnostics, fallback_used: true },
    missingConnector: hasEtsyConnector() ? "" : "ETSY_API_KEY_OR_TOKEN"
  };
}
