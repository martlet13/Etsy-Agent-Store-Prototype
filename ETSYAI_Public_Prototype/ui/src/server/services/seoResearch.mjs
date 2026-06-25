import fs from "fs";
import path from "path";
import { researchEtsyTrends } from "./etsyMarketResearch.mjs";

const DATA = path.join(process.cwd(), "data");
const EVERBEE_SEED = path.join(DATA, "everbee_keyword_seed.json");
const EVERBEE_EXPORT = path.join(DATA, "everbee_keyword_exports.json");

function readJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const text = fs.readFileSync(filePath, "utf8").trim();
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
}

function saveJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
}

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function defaultKeywordSeed() {
  return [
    ["mom mug", ["mothers day mug", "mom coffee mug", "floral mom mug"], "mug"],
    ["grandma gift", ["grandma mug", "nana gift", "garden grandma mug"], "mug"],
    ["floral tote", ["mom tote bag", "floral gift tote", "mother in law tote"], "tote"],
    ["pet mom shirt", ["dog mom shirt", "cat mom shirt", "pet mom gift"], "t-shirt"],
    ["new mom coffee mug", ["new mom gift", "mom life mug", "new mama coffee"], "mug"],
    ["dad shirt", ["father's day shirt", "garage dad shirt", "grilling dad"], "t-shirt"],
    ["teacher gift", ["teacher mug", "teacher tote", "teacher appreciation"], "mug"],
    ["nurse gift", ["nurse mug", "nurse appreciation", "nurse tote"], "mug"],
    ["western mug", ["cowboy coffee mug", "western gift", "western coffee"], "mug"],
    ["mechanic shirt", ["blue collar shirt", "garage mechanic gift", "mechanic dad"], "t-shirt"],
    ["camping mug", ["camp coffee mug", "outdoor mug", "camping gift"], "mug"],
    ["Halloween coffee mug", ["spooky coffee mug", "ghost mug", "pumpkin mug"], "mug"],
    ["Christmas grandma gift", ["grandma ornament", "holiday grandma mug", "nana christmas gift"], "mug"]
  ].map(([keyword, relatedKeywords, productType]) => ({
    keyword,
    relatedKeywords,
    productType,
    notes: "Local SEO seed. No search-volume claim.",
    source: "local_seed"
  }));
}

function ensureSeed() {
  if (!fs.existsSync(EVERBEE_SEED)) saveJson(EVERBEE_SEED, defaultKeywordSeed());
}

function keywordRows() {
  ensureSeed();
  const exportRows = readJson(EVERBEE_EXPORT, []);
  if (Array.isArray(exportRows) && exportRows.length) return { provider: "everbee_export", rows: exportRows };
  return { provider: "local_seed", rows: readJson(EVERBEE_SEED, defaultKeywordSeed()) };
}

function cleanTag(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 20);
}

export async function researchSeoKeywords(input = {}) {
  const provider = input.provider || "auto";
  const marketKeyword = normalize(input.marketKeyword);
  const productType = normalize(input.productType);
  const maxResults = Math.max(1, Math.min(25, Number(input.maxResults || 13)));
  let rows = [];
  let providerUsed = "local_seed";
  const warnings = [];
  const diagnostics = {};

  if (provider === "etsy_api") {
    const trends = await researchEtsyTrends({ keyword: marketKeyword, productType, maxResults });
    providerUsed = trends.source === "etsy_api" ? "etsy_api" : "local_seed";
    rows = (trends.recommendedCombinations || []).map((item) => ({
      keyword: item.seoSeed?.primaryKeyword || item.marketKeyword,
      relatedKeywords: item.seoSeed?.supportingKeywords || [],
      productType,
      source: providerUsed
    }));
    warnings.push(...(trends.warnings || []));
    diagnostics.etsy = trends.diagnostics || {};
  } else {
    const source = keywordRows();
    providerUsed = provider === "everbee_export" && source.provider !== "everbee_export" ? "local_seed" : source.provider;
    rows = source.rows;
    if (source.provider !== "everbee_export") warnings.push("EverBee export not found; using local SEO seed without search-volume claims.");
  }

  const filtered = rows
    .filter((row) => !marketKeyword || normalize(row.marketKeyword || row.keyword).includes(marketKeyword) || normalize(row.relatedKeywords?.join(" ")).includes(marketKeyword) || marketKeyword.includes(normalize(row.keyword)))
    .filter((row) => !productType || !row.productType || normalize(row.productType) === productType)
    .slice(0, maxResults);
  const basis = filtered.length ? filtered : rows.slice(0, maxResults);
  const keywords = [...new Set(basis.flatMap((row) => [row.keyword, ...(row.relatedKeywords || [])]).filter(Boolean))].slice(0, maxResults);
  const tags = keywords.map(cleanTag).filter(Boolean).filter((tag, index, arr) => arr.indexOf(tag) === index).slice(0, 13);
  const titleAngles = keywords.slice(0, 4).map((keyword) => `${keyword} ${productType || "gift"}`.trim());

  return {
    ok: true,
    providerUsed,
    keywords,
    titleAngles,
    tags,
    warnings,
    missingConnector: providerUsed === "local_seed" ? "EVERBEE_EXPORT_OR_ETSY_API_NOT_AVAILABLE" : "",
    diagnostics: {
      ...diagnostics,
      everbee_seed_file: EVERBEE_SEED,
      everbee_export_file: EVERBEE_EXPORT,
      rows_considered: rows.length
    }
  };
}
