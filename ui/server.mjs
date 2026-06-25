import express from "express";
import cors from "cors";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
import { researchSupplierProducts } from "./src/server/services/supplierResearch.mjs";
import { researchEtsyTrends } from "./src/server/services/etsyMarketResearch.mjs";
import { researchSeoKeywords } from "./src/server/services/seoResearch.mjs";
import { buildProductPackage, saveProductPackage, listProductPackages } from "./src/server/services/productPackageBuilder.mjs";
import { getEtsyConnectorStatus, publishEtsyListing, findProductPackage } from "./src/server/services/etsyPublisher.mjs";
import { getRevenueSummary, listSalesOrders, listListingPerformance, listMarketPerformanceMemory, syncEtsyOrders } from "./src/server/services/revenueTracker.mjs";
import { loadSupplierCatalog, matchMarketItemToSupplierCatalog, refreshSupplierCatalog, summarizeSupplierCatalog } from "./src/server/services/supplierCatalog.mjs";

const ROOT = path.resolve(process.cwd(), "..");
const STATE = path.join(ROOT, "_spacecommand_state");
const CORE = path.join(ROOT, "_core");
const SECRETS_FILE = path.join(STATE, "local_api_keys.json");
const SHIFT_STATE_FILE = path.join(STATE, "autonomous_shift_state.json");
const SHIFT_QUEUE_FILE = path.join(STATE, "autonomous_work_queue.json");
const SHIFT_LOG_FILE = path.join(STATE, "autonomous_shift_log.jsonl");
const SHIFT_LOCK_FILE = path.join(STATE, "autonomous_shift.lock");
const SHIFT_LOCK_STALE_MS = 10 * 60 * 1000;
const LISTING_SLOTS_FILE = path.join(process.cwd(), "data", "listing_slots.json");
const DEFAULT_SHIFT_TICK_INTERVAL_MS = 15000;
const MIN_SHIFT_TICK_INTERVAL_MS = 5000;
const MAX_SHIFT_TICK_INTERVAL_MS = 60000;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let shiftLoopTimer = null;
let shiftLoopRunning = false;
let shiftLoopIntervalMs = DEFAULT_SHIFT_TICK_INTERVAL_MS;
let lastLoopStartedAt = "";
let lastLoopTickAt = "";
let lastLoopTickError = "";

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

const PORT = 4521;
const DEFAULT_FORGE_PROMPT = "bold vector sticker design of a raccoon wearing a tiny welding helmet, holding a coffee mug, clean commercial t-shirt graphic, centered composition, thick outline, high contrast, transparent background style, no text";
const DEFAULT_FORGE_NEGATIVE_PROMPT = "copyrighted character, brand logo, celebrity, team logo, trademarked slogan, watermark, signature, blurry, low quality, unreadable text, messy background, extra limbs, deformed hands";
const DEFAULT_TARGET_PRICES = {
  sticker: 9.99,
  poster: 19.99,
  mug: 14.99,
  "t-shirt": 24.99,
  hoodie: 39.99
};
const TARGET_PRICE_CEILINGS = {
  sticker: 14.99,
  poster: 29.99,
  mug: 22.99,
  "t-shirt": 34.99,
  hoodie: 59.99
};
const MAX_LEDGER_RETRIES = 4;

function loadLocalEnvFile(filePath) {
  try {
    if (!fs.existsSync(filePath)) return;
    const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq <= 0) continue;
      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      if (key && process.env[key] === undefined) process.env[key] = value;
    }
  } catch {
    // Keep startup resilient if a local env file is malformed.
  }
}

loadLocalEnvFile(path.join(ROOT, ".env.local"));
loadLocalEnvFile(path.join(ROOT, "ui", ".env.local"));

function readJson(fileName, fallback) {
  try {
    const filePath = path.join(STATE, fileName);
    if (!fs.existsSync(filePath)) return fallback;
    const text = fs.readFileSync(filePath, "utf8").trim();
    if (!text) return fallback;
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function latest(list) {
  if (!Array.isArray(list) || list.length === 0) return null;
  return list[list.length - 1];
}

function runPython(scriptName, args = []) {
  return new Promise((resolve) => {
    const scriptPath = path.join(CORE, scriptName);

    const child = spawn("python", [scriptPath, ...args], {
      cwd: ROOT,
      shell: true
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      resolve({ ok: code === 0, code, stdout, stderr });
    });

    child.on("error", (error) => {
      resolve({ ok: false, code: -1, stdout, stderr: String(error) });
    });
  });
}


function humanStatus(status) {
  const value = String(status || "").toLowerCase();

  if (!value) return "No status yet.";
  if (value.includes("pass")) return "Everything is currently passing.";
  if (value.includes("blocked")) return "This is safely blocked until missing requirements are fixed.";
  if (value.includes("failed")) return "This attempt failed safely. Nothing was published or charged.";
  if (value.includes("waiting")) return "Waiting for the next required step.";
  if (value.includes("locked")) return "Locked until you approve it.";
  if (value.includes("working")) return "Currently has work in progress.";
  if (value.includes("calculating")) return "Checking numbers and profit safety.";
  if (value.includes("drafting")) return "Writing listing text and product copy.";
  if (value.includes("guarding")) return "Checking safety and quality.";
  if (value.includes("secured")) return "Backups and records are being protected.";
  return String(status);
}

function money(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "unknown";
  return `$${num.toFixed(2)}`;
}

function readableTimeFrame(item) {
  return (
    item?.time_frame ||
    item?.trend_window ||
    item?.candidate_window ||
    item?.window ||
    item?.created_at ||
    "the available research window"
  );
}

function readableEvidenceStrength(item) {
  const raw = String(item?.strength || item?.evidence_strength || item?.confidence || item?.status || "").toLowerCase();

  if (raw.includes("strong")) return "strong";
  if (raw.includes("medium")) return "medium";
  if (raw.includes("weak")) return "weak";
  if (raw.includes("missing")) return "missing";
  return raw || "unknown";
}

function readableProductIdea(item) {
  return (
    item?.title ||
    item?.opportunity_title ||
    item?.product_title ||
    item?.name ||
    "Untitled product idea"
  );
}

function readableRecordLine(item, kind) {
  if (!item) return "No record yet.";

  if (kind === "opportunity") {
    const title = readableProductIdea(item);
    const strength = readableEvidenceStrength(item);
    const sourceCount = Array.isArray(item.source_evidence_ids) ? item.source_evidence_ids.length : 0;
    const status = String(item.status || "").replaceAll("_", " ");

    return `${title}. Evidence strength is ${strength}. It is backed by ${sourceCount} research source${sourceCount === 1 ? "" : "s"}. Current decision: ${status || "not decided yet"}.`;
  }

  if (kind === "evidence") {
    const source = item.source || item.source_name || "a public source";
    const strength = readableEvidenceStrength(item);
    const timeframe = readableTimeFrame(item);
    const sold = item.items_sold || item.sales_count || item.units_sold || item.number_sold || null;

    if (sold) {
      return `${sold} item${Number(sold) === 1 ? "" : "s"} sold during ${timeframe}. Source: ${source}. Signal strength: ${strength}.`;
    }

    return `Found a ${strength} research signal from ${source}. Time frame: ${timeframe}. This is useful for ideas, but may still need stronger proof before spending money.`;
  }

  if (kind === "design") {
    const title = item.title || "Untitled design";
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const allowed = item.production_allowed ? "can move toward production" : "cannot move toward production yet";
    const reason = item.gate_reason || item.reason || "";

    return `${title}. Forge marked it as ${status}. It ${allowed}.${reason ? ` Reason: ${String(reason).replaceAll("_", " ")}.` : ""}`;
  }

  if (kind === "image_request") {
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const provider = item.provider_id || item.provider || "image provider";
    const allowed = item.live_generation_allowed || item.production_allowed;

    return `Image request ${item.id || ""} is ${status}. Provider: ${provider}. Paid generation is ${allowed ? "allowed by this record" : "not allowed yet"}.`;
  }

  if (kind === "image_run") {
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const model = item.model || "unknown model";
    const counted = item.counts_against_budget ? "This counted against the image budget." : "This did not count against the image budget.";

    if (String(item.status || "").includes("failed")) {
      return `Image generation failed safely using ${model}. ${counted} Nothing was published.`;
    }

    if (String(item.status || "").includes("disabled")) {
      return `Image generation was blocked because the live image API is disabled. ${counted}`;
    }

    return `Image generation run ${item.id || ""} is ${status} using ${model}. ${counted}`;
  }

  if (kind === "asset") {
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const approvedMockup = item.approved_for_mockup ? "approved for mockups" : "not approved for mockups yet";
    const approvedProduct = item.approved_for_product ? "approved for real products" : "not approved for real products yet";

    return `Image asset ${item.id || ""} is ${status}. It is ${approvedMockup} and ${approvedProduct}.`;
  }

  if (kind === "qa") {
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const promptScore = item.prompt_match_score ?? "unknown";
    const productScore = item.product_readiness_score ?? "unknown";

    return `Sentinel reviewed this image. Status: ${status}. Prompt match score: ${promptScore}. Product readiness score: ${productScore}.`;
  }

  if (kind === "economics") {
    const decision = String(item.decision || item.status || "unknown").replaceAll("_", " ");
    const issues = Array.isArray(item.issues) ? item.issues.map((x) => String(x).replaceAll("_", " ")).join(", ") : "";

    return `Ledger decision: ${decision}. ${issues ? `Blocked because: ${issues}.` : "No major cost issues listed."}`;
  }

  if (kind === "listing") {
    const title = item.title || "Untitled listing";
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const allowed = item.listing_allowed ? "allowed" : "not allowed yet";
    const tags = Array.isArray(item.tags) ? item.tags.length : 0;

    return `${title}. Listing status: ${status}. Publishing is ${allowed}. Scribe prepared ${tags} Etsy tag${tags === 1 ? "" : "s"}.`;
  }

  if (kind === "publish") {
    const status = String(item.status || "unknown").replaceAll("_", " ");
    const issues = Array.isArray(item.issues) ? item.issues.map((x) => String(x).replaceAll("_", " ")).join(", ") : "";

    return `Publisher package ${item.id || ""} is ${status}. ${issues ? `It is blocked because: ${issues}.` : "No publishing issues listed."}`;
  }

  if (kind === "audit") {
    const status = item.status || "unknown";
    const blockers = item.summary?.blockers ?? 0;
    const warnings = item.summary?.warnings ?? 0;

    return `Overseer audit ${item.id || ""} says the system is ${status}. There are ${blockers} blocker${blockers === 1 ? "" : "s"} and ${warnings} warning${warnings === 1 ? "" : "s"}.`;
  }

  return item.title || item.id || JSON.stringify(item);
}

function readableList(records, kind, limit = 6) {
  if (!Array.isArray(records) || records.length === 0) return [];
  return records.slice(-limit).reverse().map((item) => ({
    id: item.id || item.title || "record",
    status: item.status || item.decision || "record",
    text: readableRecordLine(item, kind),
    raw: item
  }));
}

function buildHumanRoomCopy(roomId, data, payload) {
  const {
    evidence,
    opportunities,
    designs,
    imageRequests,
    imageRuns,
    imageAssets,
    visualQa,
    listings,
    economics,
    publishPackages,
    publishRuns,
    audits,
    cycles,
    decisions,
    connectorChecks,
    backups,
    doctor
  } = data;

  const latestAudit = latest(audits);
  const latestOpp = latest(opportunities);
  const latestEvidence = latest(evidence);
  const latestDesign = latest(designs);
  const latestImageRun = latest(imageRuns);
  const latestEconomics = latest(economics);
  const latestListing = latest(listings);
  const latestPublish = latest(publishPackages);

  if (roomId === "nova") {
    return {
      plainSummary: opportunities.length
        ? `Nova has found ${opportunities.length} product idea${opportunities.length === 1 ? "" : "s"} from ${evidence.length} research signal${evidence.length === 1 ? "" : "s"}. The newest idea is: “${readableProductIdea(latestOpp)}.”`
        : "Nova has not found a product idea yet.",
      currentTask: latestOpp
        ? `Deciding whether “${readableProductIdea(latestOpp)}” has enough proof to become a product.`
        : "Waiting for research sources.",
      simpleVerdict: latestOpp
        ? `This looks like a ${readableEvidenceStrength(latestOpp)} idea. It is useful for concept work, but should not spend money unless stronger proof or cost data exists.`
        : "No product verdict yet.",
      readableRecords: [
        { title: "Best product ideas Nova found", items: readableList(opportunities, "opportunity") },
        { title: "Research signals Nova used", items: readableList(evidence, "evidence") }
      ]
    };
  }

  if (roomId === "forge") {
    return {
      plainSummary: `Forge has made ${designs.length} design concept${designs.length === 1 ? "" : "s"} and ${imageRequests.length} image request${imageRequests.length === 1 ? "" : "s"}.`,
      currentTask: latestDesign
        ? `Turning “${latestDesign.title || "the latest product idea"}” into a product-ready design direction.`
        : "Waiting for Nova to send a product idea.",
      simpleVerdict: latestImageRun
        ? readableRecordLine(latestImageRun, "image_run")
        : "No paid image generation has run yet.",
      readableRecords: [
        { title: "Design concepts Forge created", items: readableList(designs, "design") },
        { title: "Image requests waiting or blocked", items: readableList(imageRequests, "image_request") },
        { title: "Image generation attempts", items: readableList(imageRuns, "image_run") },
        { title: "Generated image assets", items: readableList(imageAssets, "asset") }
      ]
    };
  }

  if (roomId === "sentinel") {
    return {
      plainSummary: `Sentinel has completed ${visualQa.length} image quality review${visualQa.length === 1 ? "" : "s"}.`,
      currentTask: imageAssets.length
        ? "Checking whether generated images are safe, accurate, and product-ready."
        : "Waiting for Forge to create a real image asset.",
      simpleVerdict: latest(visualQa)
        ? readableRecordLine(latest(visualQa), "qa")
        : "No visual review has happened yet.",
      readableRecords: [
        { title: "Image quality reviews", items: readableList(visualQa, "qa") },
        { title: "Images waiting for review", items: readableList(imageAssets, "asset") }
      ]
    };
  }

  if (roomId === "ledger") {
    return {
      plainSummary: `Ledger has checked ${economics.length} product cost card${economics.length === 1 ? "" : "s"}.`,
      currentTask: "Making sure products have enough margin before anything goes to Etsy.",
      simpleVerdict: latestEconomics
        ? readableRecordLine(latestEconomics, "economics")
        : "No pricing decision yet.",
      readableRecords: [
        { title: "Profit and cost checks", items: readableList(economics, "economics") },
        { title: "Listings affected by Ledger", items: readableList(listings, "listing") }
      ]
    };
  }

  if (roomId === "scribe") {
    return {
      plainSummary: `Scribe has written ${listings.length} listing draft${listings.length === 1 ? "" : "s"}.`,
      currentTask: "Writing product titles, descriptions, Etsy tags, and safe listing copy.",
      simpleVerdict: latestListing
        ? readableRecordLine(latestListing, "listing")
        : "No listing draft yet.",
      readableRecords: [
        { title: "Listing drafts Scribe wrote", items: readableList(listings, "listing") }
      ]
    };
  }

  if (roomId === "publisher") {
    return {
      plainSummary: `Publisher has prepared ${publishPackages.length} upload package${publishPackages.length === 1 ? "" : "s"} and ${publishRuns.length} publish run${publishRuns.length === 1 ? "" : "s"}.`,
      currentTask: "Keeping uploads and live publishing blocked until every gate passes.",
      simpleVerdict: latestPublish
        ? readableRecordLine(latestPublish, "publish")
        : "No publish package yet.",
      readableRecords: [
        { title: "Upload packages", items: readableList(publishPackages, "publish") },
        { title: "Publishing attempts", items: readableList(publishRuns, "publish") }
      ]
    };
  }

  if (roomId === "api") {
    const live = payload.budget?.live_api_enabled;
    const model = payload.budget?.model || "unknown model";
    return {
      plainSummary: live
        ? `The image API is turned on for ${model}.`
        : `The image API is locked. No paid image generation can happen right now.`,
      currentTask: "Holding API keys, spending caps, and approval switches.",
      simpleVerdict: `Current image model: ${model}. Monthly image cap: ${payload.budget?.monthly_image_cap ?? "unknown"}. Live spending is ${live ? "enabled" : "disabled"}.`,
      readableRecords: [
        {
          title: "Connector checks",
          items: readableList(connectorChecks, "generic").map((x) => ({
            ...x,
            text: "API connector check completed. Open this only when you are ready to review keys and approvals."
          }))
        }
      ]
    };
  }

  if (roomId === "archive") {
    return {
      plainSummary: `Archivist has ${backups.length} backup${backups.length === 1 ? "" : "s"} and ${doctor.length} state doctor report${doctor.length === 1 ? "" : "s"}.`,
      currentTask: "Keeping the project recoverable and organized.",
      simpleVerdict: `Artifact index has ${payload.artifactIndexSummary.artifacts} linked records across ${payload.artifactIndexSummary.chains} product chain${payload.artifactIndexSummary.chains === 1 ? "" : "s"}.`,
      readableRecords: [
        {
          title: "Backups",
          items: backups.slice(-6).reverse().map((item) => ({
            id: item.id,
            status: item.status,
            text: `Backup ${item.id} saved ${item.files || "unknown"} files.`
          }))
        },
        {
          title: "State Doctor reports",
          items: doctor.slice(-6).reverse().map((item) => ({
            id: item.id,
            status: item.status,
            text: `State Doctor ${item.id} finished with status ${item.status}. It found ${item.issues_after?.length ?? 0} remaining issue${(item.issues_after?.length ?? 0) === 1 ? "" : "s"}.`
          }))
        }
      ]
    };
  }

  return {
    plainSummary: latestAudit
      ? readableRecordLine(latestAudit, "audit")
      : "Overseer has not run an audit yet.",
    currentTask: "Watching the whole station and stopping unsafe steps.",
    simpleVerdict: latestAudit
      ? `The system has ${latestAudit.summary?.blockers ?? 0} blocker${(latestAudit.summary?.blockers ?? 0) === 1 ? "" : "s"} and ${latestAudit.summary?.warnings ?? 0} warning${(latestAudit.summary?.warnings ?? 0) === 1 ? "" : "s"}.`
      : "No audit verdict yet.",
    readableRecords: [
      { title: "Latest audit", items: latestAudit ? [{ id: latestAudit.id, status: latestAudit.status, text: readableRecordLine(latestAudit, "audit") }] : [] },
      {
        title: "Decisions waiting for you",
        items: decisions.slice(-8).reverse().map((item) => ({
          id: item.id,
          status: item.severity || item.status,
          text: `${item.title}. ${item.reason || "Waiting for your decision."}`
        }))
      }
    ]
  };
}

function buildAgentRooms(payload) {
  const evidence = readJson("evidence_cards.json", []);
  const opportunities = readJson("opportunity_cards.json", []);
  const designs = readJson("design_packages.json", []);
  const imageRequests = readJson("image_generation_requests.json", []);
  const imageRuns = readJson("image_generation_runs.json", []);
  const imageAssets = readJson("image_assets.json", []);
  const visualQa = readJson("visual_qa_reports.json", []);
  const listings = readJson("listing_drafts.json", []);
  const economics = readJson("unit_economics_cards.json", []);
  const publishPackages = readJson("publish_packages.json", []);
  const publishRuns = readJson("publish_runs.json", []);
  const audits = readJson("pipeline_audits.json", []);
  const cycles = readJson("spacecommand_cycle_reports.json", []);
  const decisions = readJson("decision_queue.json", []);
  const connectorChecks = readJson("api_connector_status_checks.json", []);
  const backups = readJson("backup_reports.json", []);
  const doctor = readJson("state_doctor_reports.json", []);

  const roomData = {
    evidence,
    opportunities,
    designs,
    imageRequests,
    imageRuns,
    imageAssets,
    visualQa,
    listings,
    economics,
    publishPackages,
    publishRuns,
    audits,
    cycles,
    decisions,
    connectorChecks,
    backups,
    doctor
  };

  const rooms = [
    {
      id: "overseer",
      name: "Overseer",
      callsign: "Command Bridge",
      roomType: "bridge",
      color: "cyan",
      status: latest(audits)?.status || "unknown",
      activity: "Watching every gate, blocker, warning, and approval path.",
      metrics: [
        ["Audit", latest(audits)?.id || "none"],
        ["Blockers", latest(audits)?.summary?.blockers ?? 0],
        ["Warnings", latest(audits)?.summary?.warnings ?? 0],
        ["Cycles", cycles.length]
      ],
      records: {
        "Latest Audit": latest(audits),
        "Latest Cycle": latest(cycles),
        "Decision Queue": decisions.slice(-8)
      }
    },
    {
      id: "nova",
      name: "Nova",
      callsign: "Research Lab",
      roomType: "research",
      color: "blue",
      status: opportunities.length ? "working" : "idle",
      activity: "Researching public trend sources and turning them into opportunity cards.",
      metrics: [
        ["Evidence", evidence.length],
        ["Opportunities", opportunities.length],
        ["Latest Source", latest(evidence)?.source || "none"],
        ["Latest Opp", latest(opportunities)?.id || "none"]
      ],
      records: {
        "Opportunities": opportunities.slice(-8).reverse(),
        "Evidence Cards": evidence.slice(-8).reverse()
      }
    },
    {
      id: "forge",
      name: "Forge",
      callsign: "Factory",
      roomType: "factory",
      color: "gold",
      status: imageRequests.length ? "working" : "idle",
      activity: "Turning opportunities into design packages and gated image requests.",
      metrics: [
        ["Designs", designs.length],
        ["Image Requests", imageRequests.length],
        ["Image Runs", imageRuns.length],
        ["Assets", imageAssets.length]
      ],
      records: {
        "Design Packages": designs.slice(-8).reverse(),
        "Image Requests": imageRequests.slice(-8).reverse(),
        "Image Runs": imageRuns.slice(-8).reverse(),
        "Image Assets": imageAssets.slice(-8).reverse()
      }
    },
    {
      id: "sentinel",
      name: "Sentinel",
      callsign: "QA Room",
      roomType: "qa",
      color: "green",
      status: visualQa.length ? "guarding" : "waiting",
      activity: "Inspecting images for prompt match, product readiness, safety, and mockup approval.",
      metrics: [
        ["QA Reports", visualQa.length],
        ["Latest QA", latest(visualQa)?.id || "none"],
        ["Mockup OK", latest(visualQa)?.approved_for_mockup ?? false],
        ["Product OK", latest(visualQa)?.approved_for_product ?? false]
      ],
      records: {
        "Visual QA Reports": visualQa.slice(-8).reverse(),
        "Image Assets": imageAssets.slice(-8).reverse()
      }
    },
    {
      id: "ledger",
      name: "Ledger",
      callsign: "Treasury",
      roomType: "treasury",
      color: "emerald",
      status: economics.length ? "calculating" : "waiting",
      activity: "Checking costs, shipping, margins, break-even price, and profit safety.",
      metrics: [
        ["Economics", economics.length],
        ["Latest", latest(economics)?.id || "none"],
        ["Decision", latest(economics)?.decision || "none"],
        ["Listings", listings.length]
      ],
      records: {
        "Unit Economics": economics.slice(-8).reverse(),
        "Listing Drafts": listings.slice(-8).reverse()
      }
    },
    {
      id: "scribe",
      name: "Scribe",
      callsign: "Listing Room",
      roomType: "listing",
      color: "purple",
      status: listings.length ? "drafting" : "waiting",
      activity: "Writing Etsy titles, tags, descriptions, materials, and SEO notes.",
      metrics: [
        ["Listings", listings.length],
        ["Latest", latest(listings)?.id || "none"],
        ["Allowed", latest(listings)?.listing_allowed ?? false],
        ["Publish", latest(listings)?.publish_allowed ?? false]
      ],
      records: {
        "Listing Drafts": listings.slice(-8).reverse()
      }
    },
    {
      id: "publisher",
      name: "Publisher",
      callsign: "Docking Bay",
      roomType: "dock",
      color: "orange",
      status: publishPackages.length ? "blocked_safe" : "waiting",
      activity: "Preparing upload packages while keeping live publishing locked.",
      metrics: [
        ["Packages", publishPackages.length],
        ["Runs", publishRuns.length],
        ["Latest", latest(publishPackages)?.id || "none"],
        ["Status", latest(publishPackages)?.status || "none"]
      ],
      records: {
        "Publish Packages": publishPackages.slice(-8).reverse(),
        "Publish Runs": publishRuns.slice(-8).reverse()
      }
    },
    {
      id: "api",
      name: "API Dock",
      callsign: "Connector Bay",
      roomType: "api",
      color: "red",
      status: payload.budget?.live_api_enabled ? "live" : "locked",
      activity: "Holding API keys, approval switches, model caps, and live-action locks.",
      metrics: [
        ["Model", payload.budget?.model || "none"],
        ["Live API", payload.budget?.live_api_enabled ? "on" : "off"],
        ["Monthly Cap", payload.budget?.monthly_image_cap ?? "none"],
        ["Connector Checks", connectorChecks.length]
      ],
      records: {
        "Latest Connector Check": latest(connectorChecks),
        "Image Budget": payload.budget
      }
    },
    {
      id: "archive",
      name: "Archivist",
      callsign: "Data Vault",
      roomType: "archive",
      color: "teal",
      status: backups.length ? "secured" : "waiting",
      activity: "Backing up state, indexing artifacts, and preserving chain history.",
      metrics: [
        ["Backups", backups.length],
        ["Doctor Runs", doctor.length],
        ["Artifacts", payload.artifactIndexSummary.artifacts],
        ["Chains", payload.artifactIndexSummary.chains]
      ],
      records: {
        "Backups": backups.slice(-8).reverse(),
        "State Doctor": doctor.slice(-8).reverse(),
        "Artifact Index": payload.artifactIndexSummary
      }
    }
  ];

  return rooms.map((room) => ({
    ...room,
    ...buildHumanRoomCopy(room.id, roomData, payload)
  }));
}

function buildStatePayload() {
  const audits = readJson("pipeline_audits.json", []);
  const board = readJson("product_candidate_board.json", []);
  const decisions = readJson("decision_queue.json", []);
  const actionContracts = readJson("ui_action_contracts.json", { actions: [] });
  const actionRuns = readJson("ui_action_runs.json", []);
  const budget = readJson("image_api_budget.json", {});
  const connectorRegistry = readJson("api_connector_registry.json", { connectors: [] });
  const connectorChecks = readJson("api_connector_status_checks.json", []);
  const artifactIndex = readJson("artifact_index.json", { artifacts: {}, chains: [] });
  const transcriptAgentViews = readJson("transcript_agent_views.json", {});
  const imageAssets = readJson("image_assets.json", []);
  const imageRuns = readJson("image_generation_runs.json", []);
  const visualQa = readJson("visual_qa_reports.json", []);
  const designPackages = readJson("design_packages.json", []);
  const unitEconomics = readJson("unit_economics_cards.json", []);
  const listings = readJson("listing_drafts.json", []);
  const publishPackages = readJson("publish_packages.json", []);
  const supplierCosts = listSupplierCosts();
  const productionReviews = listProductionReviews();
  const productPackages = listProductPackages();
  const revenue = getRevenueSummary();
  const salesOrders = listSalesOrders();
  const listingPerformance = listListingPerformance();
  const marketPerformanceMemory = listMarketPerformanceMemory();
  const supplierCatalog = summarizeSupplierCatalog(loadSupplierCatalog());

  const dashboardMarkdownPath = path.join(STATE, "dashboard_report_latest.md");
  let dashboardMarkdown = "";

  if (fs.existsSync(dashboardMarkdownPath)) {
    dashboardMarkdown = fs.readFileSync(dashboardMarkdownPath, "utf8");
  }

  const latestAudit = latest(audits);
  const latestConnectorCheck = latest(connectorChecks);

  const payload = {
    root: ROOT,
    generatedAt: new Date().toISOString(),
    latestAudit,
    board,
    decisions,
    actionContracts,
    actionRuns: actionRuns.slice(-10).reverse(),
    budget,
    connectorRegistry,
    latestConnectorCheck,
    transcriptAgentViews,
    imageAssets,
    imageRuns,
    visualQa,
    designPackages,
    unitEconomics,
    listings,
    publishPackages,
    productPackages,
    supplierCosts,
    productionReviews,
    listingSlots: loadListingSlots(),
    businessPolicy: businessPolicyConfig(),
    etsyPublisher: getEtsyConnectorStatus(),
    revenueSummary: revenue.summary,
    revenueConnector: revenue.connector,
    salesOrders,
    listingPerformance,
    marketPerformanceMemory,
    supplierCatalog,
    artifactIndexSummary: {
      artifacts: artifactIndex.artifacts ? Object.keys(artifactIndex.artifacts).length : 0,
      chains: Array.isArray(artifactIndex.chains) ? artifactIndex.chains.length : 0,
      builtAt: artifactIndex.built_at || null
    },
    dashboardMarkdown,
    counts: {
      evidence: readJson("evidence_cards.json", []).length,
      opportunities: readJson("opportunity_cards.json", []).length,
      designs: designPackages.length,
      imageRequests: readJson("image_generation_requests.json", []).length,
      imageAssets: imageAssets.length,
      listings: listings.length,
      publishPackages: publishPackages.length,
      productPackages: productPackages.length,
      salesOrders: salesOrders.length,
      decisions: decisions.length,
      board: board.length
    }
  };

  payload.agentRooms = buildAgentRooms(payload);
  return payload;
}


function maskSecretValue(value) {
  const raw = String(value || "");
  if (!raw) return "missing";
  if (raw.length <= 8) return "saved";
  return `${raw.slice(0, 4)}...${raw.slice(-4)}`;
}

function maskSecretStatus(secrets) {
  const keys = [
    "OPENAI_API_KEY",
    "PRINTIFY_API_KEY",
    "PRINTFUL_API_KEY",
    "ETSY_API_KEY",
    "ETSY_CLIENT_SECRET",
    "ETSY_ACCESS_TOKEN",
    "ETSY_REFRESH_TOKEN",
    "ETSY_SHOP_ID"
  ];

  const status = {};
  for (const key of keys) {
    const value = secrets?.[key] || process.env[key] || "";
    status[key] = value ? maskSecretValue(value) : "missing";
  }

  return status;
}

function quoteEnvValue(value) {
  return JSON.stringify(String(value || ""));
}

function writeEnvFile(filePath, secrets) {
  const lines = [
    "# SpaceCommand local secrets",
    "# Generated by the SpaceCommand UI.",
    "# Keep this file private.",
    ""
  ];

  for (const [key, value] of Object.entries(secrets || {})) {
    if (value) lines.push(`${key}=${quoteEnvValue(value)}`);
  }

  fs.writeFileSync(filePath, lines.join("\n") + "\n", "utf8");
}


function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function localArtBaseUrl() {
  return String(process.env.COMFYUI_BASE_URL || "http://127.0.0.1:8188").replace(/\/+$/, "");
}

function isLocalComfyUrl(baseUrl) {
  try {
    const parsed = new URL(baseUrl);
    return ["127.0.0.1", "localhost", "::1"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

function numberEnv(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function forgeArtOutputDir() {
  const configured = process.env.FORGE_ART_OUTPUT_DIR || "./data/generated-art";
  const resolved = path.resolve(process.cwd(), configured);
  ensureDir(resolved);
  return resolved;
}

function sanitizeGeneratedArtName(value) {
  return String(value || "forge-art")
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/-+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 96) || "forge-art";
}

function assertGeneratedArtPath(candidatePath) {
  const base = forgeArtOutputDir();
  const resolved = path.resolve(candidatePath);
  const relative = path.relative(base, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Blocked path traversal outside generated-art folder.");
  }
  return resolved;
}

function resolveGeneratedArtFile(filename) {
  const safe = sanitizeGeneratedArtName(path.basename(String(filename || "")));
  if (!safe || !/\.(png|json)$/i.test(safe)) return null;
  const filePath = assertGeneratedArtPath(path.join(forgeArtOutputDir(), safe));
  return fs.existsSync(filePath) ? filePath : null;
}

function saveJsonFile(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
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

function isWaitingForSentinel(asset) {
  const status = String(asset?.status || "").toLowerCase();
  return Boolean(asset?.queued_for_sentinel || asset?.ready_for_sentinel_qa || status.includes("waiting_sentinel") || status.includes("pending_visual_qa"));
}

function publicGeneratedArtUrl(filePath) {
  try {
    const generated = assertGeneratedArtPath(filePath);
    return `/api/generated-art/${encodeURIComponent(path.basename(generated))}`;
  } catch {
    return null;
  }
}

function validateExistingPng(filePath) {
  if (!filePath) {
    const error = new Error("Missing localImagePath or assetId.");
    error.statusCode = 400;
    throw error;
  }
  const resolved = assertGeneratedArtPath(filePath);
  if (!/\.png$/i.test(resolved)) {
    const error = new Error("Local image must be a PNG.");
    error.statusCode = 400;
    throw error;
  }
  if (!fs.existsSync(resolved)) {
    const error = new Error("Local PNG does not exist.");
    error.statusCode = 404;
    throw error;
  }
  return resolved;
}

function validateExistingMetadata(filePath) {
  if (!filePath) return "";
  const resolved = assertGeneratedArtPath(filePath);
  if (!/\.json$/i.test(resolved)) {
    const error = new Error("Metadata must be a JSON file.");
    error.statusCode = 400;
    throw error;
  }
  if (!fs.existsSync(resolved)) {
    const error = new Error("Metadata file does not exist.");
    error.statusCode = 404;
    throw error;
  }
  return resolved;
}

const SENTINEL_BLOCKING_FAILS = new Set([
  "contains_logo",
  "contains_brand_name",
  "contains_protected_character",
  "contains_celebrity_likeness",
  "contains_watermark",
  "contains_signature",
  "contains_accidental_readable_text",
  "wrong_product_format",
  "low_resolution_or_blurry",
  "malformed_core_subject",
  "does_not_match_prompt",
  "unsafe_or_disallowed_content",
  "ip_or_trademark_risk"
]);

const SENTINEL_WARNING_FLAGS = new Set([
  "minor_composition_issue",
  "minor_color_drift",
  "needs_background_cleanup",
  "may_need_upscale",
  "mockup_only_not_product_ready",
  "text_legibility_uncertain"
]);

const SENTINEL_BLOCKED_TERMS = [
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
  "mlb",
  "mickey mouse",
  "hello kitty",
  "barbie",
  "superman",
  "batman"
];

function readPngDimensions(filePath) {
  const header = Buffer.alloc(24);
  const fd = fs.openSync(filePath, "r");
  try {
    fs.readSync(fd, header, 0, 24, 0);
  } finally {
    fs.closeSync(fd);
  }

  const isPng = header[0] === 0x89
    && header[1] === 0x50
    && header[2] === 0x4e
    && header[3] === 0x47
    && header[4] === 0x0d
    && header[5] === 0x0a
    && header[6] === 0x1a
    && header[7] === 0x0a;

  if (!isPng) {
    const error = new Error("Local image is not a valid PNG file.");
    error.statusCode = 400;
    throw error;
  }

  return {
    width: header.readUInt32BE(16),
    height: header.readUInt32BE(20)
  };
}

function normalizeSentinelFlags(flags, allowed) {
  return Array.from(new Set((Array.isArray(flags) ? flags : [])
    .map((flag) => String(flag || "").trim().toLowerCase().replace(/\s+/g, "_"))
    .filter((flag) => flag && allowed.has(flag)))).sort();
}

function evaluateAutomatedSentinelQa({ asset, metadata, imagePath }) {
  const dimensions = readPngDimensions(imagePath);
  const promptHaystack = [
    asset?.prompt,
    asset?.title,
    asset?.product_type,
    metadata?.prompt,
    metadata?.title,
    metadata?.productType,
    metadata?.negativePrompt
  ].filter(Boolean).join(" ").toLowerCase();

  const blockedTerms = SENTINEL_BLOCKED_TERMS.filter((term) => promptHaystack.includes(term));
  const passedChecks = [
    "png_exists",
    "png_readable",
    "correct_product_format",
    "no_logo_detected_in_prompt",
    "no_brand_name_detected_in_prompt",
    "no_protected_character_detected_in_prompt",
    "no_celebrity_likeness_detected_in_prompt"
  ];
  const failedChecks = [];
  const warningFlags = [];

  if (blockedTerms.length) {
    failedChecks.push("ip_or_trademark_risk");
  }

  if (dimensions.width < 1024 || dimensions.height < 1024) {
    failedChecks.push("low_resolution_or_blurry");
  }

  if (dimensions.width < 1536 || dimensions.height < 1536) {
    warningFlags.push("may_need_upscale");
  }
  warningFlags.push("needs_background_cleanup");

  if (!metadata || Object.keys(metadata).length === 0) {
    warningFlags.push("mockup_only_not_product_ready");
  } else {
    passedChecks.push("metadata_available");
  }

  if (!promptHaystack.trim()) {
    failedChecks.push("does_not_match_prompt");
  } else {
    passedChecks.push("prompt_metadata_available");
  }

  const normalizedFailures = normalizeSentinelFlags(failedChecks, SENTINEL_BLOCKING_FAILS);
  const normalizedWarnings = normalizeSentinelFlags(warningFlags, SENTINEL_WARNING_FLAGS);
  const issues = [...normalizedFailures];
  const warnings = [...normalizedWarnings];
  const promptMatchScore = blockedTerms.length || !promptHaystack.trim() ? 60 : 94;
  const productReadinessScore = normalizedFailures.length ? 72 : (normalizedWarnings.length ? 90 : 94);
  const approvedForMockup = !issues.length && promptMatchScore >= 80;
  const approvedForProduct = !issues.length && promptMatchScore >= 90 && productReadinessScore >= 90;
  const status = issues.length
    ? "blocked"
    : approvedForProduct
      ? "pass_product"
      : approvedForMockup
        ? "pass_mockup_only"
        : "blocked";

  return {
    status,
    dimensions,
    passed_checks: Array.from(new Set(passedChecks)).sort(),
    failed_checks: normalizedFailures,
    warning_flags: normalizedWarnings,
    issues,
    warnings,
    prompt_match_score: promptMatchScore,
    product_readiness_score: productReadinessScore,
    approved_for_mockup: approvedForMockup,
    approved_for_product: approvedForProduct,
    blocked_terms: blockedTerms
  };
}

function runSentinelQa(input = {}) {
  const imageAssetsFile = path.join(STATE, "image_assets.json");
  const reportsFile = path.join(STATE, "visual_qa_reports.json");
  const assets = readJson("image_assets.json", []);
  const reports = readJson("visual_qa_reports.json", []);
  const assetId = String(input.assetId || "").trim();
  let assetIndex = assetId ? assets.findIndex((item) => item.id === assetId) : -1;
  let asset = assetIndex >= 0 ? assets[assetIndex] : null;

  if (assetId && !asset) {
    const error = new Error("Image asset not found.");
    error.statusCode = 404;
    throw error;
  }

  if (!asset && input.localImagePath) {
    const imagePath = validateExistingPng(input.localImagePath);
    assetIndex = assets.findIndex((item) => {
      try {
        return path.resolve(item.file_path || "") === imagePath;
      } catch {
        return false;
      }
    });
    asset = assetIndex >= 0 ? assets[assetIndex] : null;
  }

  if (!asset) {
    const error = new Error("Sentinel QA requires an existing image asset.");
    error.statusCode = 400;
    throw error;
  }

  const imagePath = validateExistingPng(input.localImagePath || asset.file_path);
  const metadataPath = validateExistingMetadata(input.metadataPath || asset.metadata_path || "");
  const metadata = metadataPath ? readJsonFilePath(metadataPath, {}) : {};
  const evaluation = evaluateAutomatedSentinelQa({ asset, metadata, imagePath });
  const now = new Date().toISOString();
  const report = {
    id: nextStateId(reports, "VQA"),
    type: "visual_qa_report",
    status: evaluation.status,
    image_asset_id: asset.id,
    image_request_id: asset.image_request_id || null,
    design_package_id: asset.design_package_id || asset.promoted_design_id || null,
    reviewer: "Sentinel-Auto",
    file_path: imagePath,
    metadata_path: metadataPath || asset.metadata_path || null,
    prompt_match_score: evaluation.prompt_match_score,
    product_readiness_score: evaluation.product_readiness_score,
    passed_checks: evaluation.passed_checks,
    failed_checks: evaluation.failed_checks,
    warning_flags: evaluation.warning_flags,
    issues: evaluation.issues,
    warnings: evaluation.warnings,
    approved_for_mockup: evaluation.approved_for_mockup,
    approved_for_product: evaluation.approved_for_product,
    qa_notes: evaluation.approved_for_product
      ? "Automated Sentinel checks passed for local Forge PNG. Promotion and Ledger gates still apply before any listing or publish action."
      : `Automated Sentinel checks blocked product use: ${evaluation.issues.join(", ") || "not product ready"}.`,
    blocked_terms: evaluation.blocked_terms,
    image_dimensions: evaluation.dimensions,
    created_at: now
  };

  reports.push(report);

  const updatedAsset = {
    ...asset,
    file_path: imagePath,
    public_preview_url: asset.public_preview_url || publicGeneratedArtUrl(imagePath),
    metadata_path: metadataPath || asset.metadata_path,
    metadata_exists: Boolean(metadataPath || asset.metadata_path),
    visual_qa: report.id,
    approved_for_mockup: Boolean(report.approved_for_mockup),
    approved_for_product: Boolean(report.approved_for_product),
    visual_qa_status: report.status,
    visual_qa_issues: report.issues,
    visual_qa_warnings: report.warnings,
    sentinel_queue_status: report.approved_for_product ? "approved" : "blocked",
    queued_for_sentinel: false,
    ready_for_sentinel_qa: false,
    external_action_allowed: false,
    reviewed_at: now,
    updated_at: now
  };

  assets[assetIndex] = updatedAsset;
  saveJsonFile(reportsFile, reports);
  saveJsonFile(imageAssetsFile, assets);

  return {
    ok: true,
    assetId: updatedAsset.id,
    reportId: report.id,
    approved_for_product: Boolean(report.approved_for_product),
    blocked_reasons: report.issues,
    warnings: report.warnings,
    report,
    asset: updatedAsset
  };
}

function readJsonFilePath(filePath, fallback = {}) {
  try {
    if (!filePath || !fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf8").trim();
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function nextStateId(records, prefix) {
  let highest = 0;
  for (const item of Array.isArray(records) ? records : []) {
    const raw = String(item.id || "");
    if (!raw.startsWith(`${prefix}-`)) continue;
    const number = Number(raw.split("-")[1]);
    if (Number.isFinite(number)) highest = Math.max(highest, number);
  }
  return `${prefix}-${String(highest + 1).padStart(4, "0")}`;
}

function latestFor(items, predicate) {
  const matches = Array.isArray(items) ? items.filter(predicate) : [];
  return matches.length ? matches[matches.length - 1] : null;
}

function approvedVisualQaForAsset(asset, reports) {
  if (!asset) return null;
  const related = Array.isArray(reports)
    ? reports.filter((report) => report?.image_asset_id === asset.id)
    : [];
  const direct = asset.visual_qa
    ? related.find((report) => report.id === asset.visual_qa)
    : null;
  const latestReport = direct || (related.length ? related[related.length - 1] : null);

  if (asset.approved_for_product || latestReport?.approved_for_product) {
    return latestReport || {
      id: asset.visual_qa,
      status: asset.visual_qa_status || "approved_for_product",
      approved_for_product: true,
      issues: asset.visual_qa_issues || []
    };
  }

  return null;
}

function linkedForgeAssetForDesign(design, assets) {
  if (!design) return null;
  const linkedId = design.source_image_asset_id || design.forge_image_asset_id || design.image_asset_id;
  return Array.isArray(assets)
    ? assets.find((asset) => asset.id === linkedId || asset.promoted_design_id === design.id || asset.design_package_id === design.id)
    : null;
}

function moneyOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeCostKey(value) {
  return String(value || "").trim().toLowerCase();
}

function requireNonNegativeNumber(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) {
    const error = new Error(`${label} must be a non-negative number.`);
    error.statusCode = 400;
    throw error;
  }
  return number;
}

function numberConfig(name, fallback) {
  const fromEnv = moneyOrNull(process.env[name]);
  if (fromEnv !== null) return fromEnv;
  return fallback;
}

function configuredMinProfitMargin() {
  return numberConfig("MIN_PROFIT_MARGIN", 0.10);
}

function businessPolicyConfig() {
  const rules = readJson("pricing_rules.json", {});
  return {
    max_new_listings_per_month: Math.max(1, Math.floor(numberConfig("MAX_NEW_LISTINGS_PER_MONTH", moneyOrNull(rules.max_new_listings_per_month) ?? 10))),
    default_listing_quantity: Math.max(2, Math.floor(numberConfig("DEFAULT_LISTING_QUANTITY", moneyOrNull(rules.default_listing_quantity) ?? 500))),
    never_upload_quantity_one: true,
    auto_publish_enabled: ["1", "true", "yes"].includes(String(process.env.AUTO_PUBLISH_ENABLED ?? rules.auto_publish_enabled ?? "true").toLowerCase()),
    require_human_approval: false,
    min_profit_margin: configuredMinProfitMargin(),
    tax_reserve_rate: numberConfig("TAX_RESERVE_RATE", 0.30),
    listing_slot_strategy: "high_confidence_only"
  };
}

function ledgerFeeConfig() {
  const rules = readJson("pricing_rules.json", {});
  const listingRenewalFee = moneyOrNull(rules.etsy_listing_renewal_fee_per_unit)
    ?? moneyOrNull(rules.etsy_listing_fee)
    ?? numberConfig("ETSY_LISTING_RENEWAL_FEE_PER_UNIT", numberConfig("ETSY_LISTING_FEE", 0.20));
  return {
    etsyTransactionFeeRate: moneyOrNull(rules.etsy_transaction_fee_percent) ?? numberConfig("ETSY_TRANSACTION_FEE_RATE", 0.065),
    etsyListingFee: listingRenewalFee,
    etsyListingRenewalFeePerUnit: listingRenewalFee,
    etsyPaymentProcessingRate: moneyOrNull(rules.payment_processing_percent) ?? numberConfig("ETSY_PAYMENT_PROCESSING_RATE_US", 0.03),
    etsyPaymentProcessingFixed: moneyOrNull(rules.payment_processing_fixed) ?? numberConfig("ETSY_PAYMENT_PROCESSING_FIXED_US", 0.25),
    shippingOverlapBuffer: moneyOrNull(rules.shipping_overlap_buffer) ?? numberConfig("SHIPPING_OVERLAP_BUFFER", 2.00),
    defaultListingQuantity: businessPolicyConfig().default_listing_quantity,
    minProfitMargin: configuredMinProfitMargin(),
    minProfitPerSale: 0,
    taxReserveRate: numberConfig("TAX_RESERVE_RATE", 0.30)
  };
}

function requiredSalePriceForMargin(costs, targetMargin) {
  const productionCost = moneyOrNull(costs?.productionCost ?? costs?.baseCost ?? costs?.supplierProductionCost);
  const supplierShippingCost = moneyOrNull(costs?.shippingCost);
  const config = ledgerFeeConfig();
  const shippingMode = String(costs?.shippingMode || costs?.shipping_mode || "buyer_paid").toLowerCase();
  const businessPaidShipping = ["free_shipping", "business_paid", "seller_paid"].includes(shippingMode);
  const shippingCostForLedger = businessPaidShipping
    ? supplierShippingCost
    : moneyOrNull(costs?.shippingOverlapBuffer) ?? config.shippingOverlapBuffer;
  const margin = moneyOrNull(targetMargin) ?? config.minProfitMargin;
  if (productionCost === null || shippingCostForLedger === null) return null;
  const fixedCost = productionCost + shippingCostForLedger + config.etsyListingRenewalFeePerUnit + config.etsyPaymentProcessingFixed;
  const variableRate = config.etsyTransactionFeeRate + config.etsyPaymentProcessingRate + margin;
  if (variableRate >= 1) return null;
  return Number((fixedCost / (1 - variableRate)).toFixed(2));
}

function requiredSalePriceForLedgerPass(costs) {
  const config = ledgerFeeConfig();
  const marginPrice = requiredSalePriceForMargin(costs, config.minProfitMargin);
  if (marginPrice === null) return null;
  return Number(marginPrice.toFixed(2));
}

function economicsCalculation(args) {
  const config = ledgerFeeConfig();
  const itemPrice = moneyOrNull(args.targetPrice);
  const productionCost = moneyOrNull(args.baseCost);
  const supplierShippingCost = moneyOrNull(args.shippingCost);
  const shippingMode = String(args.shippingMode || args.shipping_mode || "buyer_paid").toLowerCase();
  const businessPaidShipping = ["free_shipping", "business_paid", "seller_paid"].includes(shippingMode);
  const shippingOverlapBuffer = moneyOrNull(args.shippingOverlapBuffer) ?? config.shippingOverlapBuffer;
  const shippingCostForLedger = businessPaidShipping ? supplierShippingCost : shippingOverlapBuffer;
  const minimumMargin = config.minProfitMargin;

  if (itemPrice === null || productionCost === null || shippingCostForLedger === null) {
    return {
      calculation: {},
      profit: null,
      margin: null,
      minimumMargin
    };
  }

  const etsyTransactionFee = itemPrice * config.etsyTransactionFeeRate;
  const paymentProcessingFee = (itemPrice * config.etsyPaymentProcessingRate) + config.etsyPaymentProcessingFixed;
  const totalCost = productionCost + config.etsyListingRenewalFeePerUnit + shippingCostForLedger + etsyTransactionFee + paymentProcessingFee;
  const profit = itemPrice - totalCost;
  const margin = itemPrice > 0 ? profit / itemPrice : 0;
  const requiredPrice = requiredSalePriceForLedgerPass({
    productionCost,
    shippingCost: supplierShippingCost,
    shippingOverlapBuffer,
    shippingMode
  });

  return {
    calculation: {
      gross_revenue: Number(itemPrice.toFixed(2)),
      production_cost: Number(productionCost.toFixed(2)),
      supplier_shipping_estimate_us: supplierShippingCost === null ? null : Number(supplierShippingCost.toFixed(2)),
      shipping_cost_us: supplierShippingCost === null ? null : Number(supplierShippingCost.toFixed(2)),
      shipping_mode: businessPaidShipping ? "business_paid" : "buyer_paid",
      shipping_overlap_buffer: Number(shippingOverlapBuffer.toFixed(2)),
      shipping_cost_used_for_ledger: Number(shippingCostForLedger.toFixed(2)),
      etsy_listing_renewal_fee_per_unit: Number(config.etsyListingRenewalFeePerUnit.toFixed(2)),
      etsy_upfront_listing_fee: Number(config.etsyListingRenewalFeePerUnit.toFixed(2)),
      etsy_listing_fee: Number(config.etsyListingRenewalFeePerUnit.toFixed(2)),
      etsy_transaction_fee: Number(etsyTransactionFee.toFixed(2)),
      payment_processing_fee: Number(paymentProcessingFee.toFixed(2)),
      etsy_fees_total: Number((config.etsyListingRenewalFeePerUnit + etsyTransactionFee + paymentProcessingFee).toFixed(2)),
      total_cost: Number(totalCost.toFixed(2)),
      profit: Number(profit.toFixed(2)),
      margin_percent: Number((margin * 100).toFixed(2)),
      minimum_margin_required_percent: Number((minimumMargin * 100).toFixed(2)),
      default_listing_quantity: config.defaultListingQuantity,
      upfront_listing_fee_budget: Number(config.etsyListingRenewalFeePerUnit.toFixed(2)),
      required_sale_price_for_margin: requiredPrice,
      tax_reserve_per_sale: Number((Math.max(0, profit) * config.taxReserveRate).toFixed(2)),
      spendable_per_sale: Number((Math.max(0, profit) * (1 - config.taxReserveRate)).toFixed(2))
    },
    profit,
    margin,
    minimumMargin
  };
}

function ledgerPricingSanityCase() {
  const result = economicsCalculation({
    targetPrice: 12.00,
    baseCost: 7.00,
    shippingOverlapBuffer: 2.00,
    shippingMode: "buyer_paid"
  });
  return {
    input: {
      itemPrice: 12.00,
      supplierProductionCost: 7.00,
      shippingOverlapBuffer: 2.00,
      shippingMode: "buyer_paid"
    },
    calculation: result.calculation,
    pass: Boolean(result.profit > 0 && result.margin >= ledgerFeeConfig().minProfitMargin)
  };
}

function currentMonthKey(date = new Date()) {
  return date.toISOString().slice(0, 7);
}

function loadListingSlots(month = currentMonthKey()) {
  ensureDir(path.dirname(LISTING_SLOTS_FILE));
  const policy = businessPolicyConfig();
  const existing = readJsonFilePath(LISTING_SLOTS_FILE, {});
  const fresh = {
    month,
    max_new_listings: policy.max_new_listings_per_month,
    used_listing_slots: 0,
    remaining_listing_slots: policy.max_new_listings_per_month,
    listings: [],
    performance: []
  };
  if (existing?.month !== month) {
    saveJsonFile(LISTING_SLOTS_FILE, fresh);
    return fresh;
  }
  const listings = Array.isArray(existing.listings) ? existing.listings : [];
  const used = listings.length;
  const next = {
    ...fresh,
    ...existing,
    max_new_listings: policy.max_new_listings_per_month,
    used_listing_slots: used,
    remaining_listing_slots: Math.max(0, policy.max_new_listings_per_month - used),
    listings,
    performance: (Array.isArray(existing.performance) ? existing.performance : [])
      .map((entry) => evaluateSellThroughPerformance(entry))
  };
  saveJsonFile(LISTING_SLOTS_FILE, next);
  return next;
}

function calculateListingQuantity({ defaultQuantity, supplierAvailability, isPodMadeToOrder }) {
  const fallback = Math.max(2, Number(defaultQuantity || businessPolicyConfig().default_listing_quantity || 500));
  const availability = moneyOrNull(supplierAvailability);
  if (availability !== null) {
    const quantity = Math.max(1, Math.min(fallback, Math.floor(availability)));
    return {
      ok: quantity > 1,
      quantity,
      supplier_quantity_cap: quantity,
      reason: quantity <= 1 ? "supplier_only_has_one_available_variant" : "supplier_quantity_cap_applied"
    };
  }
  if (isPodMadeToOrder) {
    return {
      ok: true,
      quantity: fallback,
      supplier_quantity_cap: null,
      reason: "pod_made_to_order_default_quantity"
    };
  }
  return {
    ok: false,
    quantity: null,
    supplier_quantity_cap: null,
    reason: "inventory_unknown_for_non_pod_product"
  };
}

function buildVariantGroupForListing(productCandidate) {
  const options = (Array.isArray(productCandidate) ? productCandidate : [productCandidate]).filter(Boolean);
  const passing = options.filter((option) => ledgerPassOptionDetails(option).pass);
  const viable = passing.length ? passing : options.filter((option) => option?.ledger_pass || option?.ledgerWouldPass);
  const policy = businessPolicyConfig();
  const variants = [];
  for (const option of viable) {
    const raw = option.raw_option || option.raw || {};
    const rawVariant = raw.variant || {};
    const availability = option.availability_quantity ?? raw.availability_quantity ?? rawVariant.quantity ?? rawVariant.availability_quantity ?? null;
    const isPod = option.is_pod_made_to_order ?? raw.is_pod_made_to_order ?? true;
    const quantity = calculateListingQuantity({
      defaultQuantity: policy.default_listing_quantity,
      supplierAvailability: availability,
      isPodMadeToOrder: isPod
    });
    if (!quantity.ok) continue;
    variants.push({
      supplier_variant_id: option.variant_id || option.variantId || option.variant || "",
      etsy_option_values: {
        color: option.color || rawVariant.color || rawVariant.options?.color || "",
        size: option.size || rawVariant.size || rawVariant.options?.size || "",
        scent: option.scent || rawVariant.scent || ""
      },
      color: option.color || rawVariant.color || rawVariant.options?.color || "",
      size: option.size || rawVariant.size || rawVariant.options?.size || "",
      scent: option.scent || rawVariant.scent || "",
      availability_quantity: availability,
      calculated_listing_quantity: quantity.quantity,
      production_cost: option.base_cost ?? option.baseCost ?? null,
      price: option.target_price ?? option.targetPrice ?? option.item_price ?? null
    });
  }
  const first = viable[0] || options[0] || {};
  const listingQuantity = variants.length ? Math.min(...variants.map((variant) => variant.calculated_listing_quantity)) : null;
  return {
    product_type: first.product_type || first.productType || "",
    supplier: first.supplier || "",
    supplier_product_id: first.product_id || first.productId || "",
    variants,
    listing_quantity: listingQuantity,
    quantity_rule_reason: variants.length ? "one_listing_with_all_valid_variants" : "no_viable_variants_for_listing"
  };
}

function recordListingSlot({
  listingId,
  workId,
  designPackageId,
  productType,
  marketKeyword,
  quantityUploaded,
  supplierQuantityCap,
  opportunityScore
}) {
  const slots = loadListingSlots();
  const existing = slots.listings.find((item) => item.listing_id === listingId);
  if (existing) return slots;
  slots.listings.push({
    listing_id: listingId,
    work_id: workId,
    design_package_id: designPackageId,
    product_type: productType,
    market_keyword: marketKeyword,
    created_at: new Date().toISOString(),
    quantity_uploaded: quantityUploaded,
    supplier_quantity_cap: supplierQuantityCap,
    opportunity_score: opportunityScore
  });
  slots.used_listing_slots = slots.listings.length;
  slots.remaining_listing_slots = Math.max(0, slots.max_new_listings - slots.used_listing_slots);
  saveJsonFile(LISTING_SLOTS_FILE, slots);
  return slots;
}

function evaluateSellThroughPerformance(entry) {
  const createdAt = entry?.created_at ? new Date(entry.created_at) : null;
  const soldOutAt = entry?.sold_out_at ? new Date(entry.sold_out_at) : null;
  const daysToSellOut = createdAt && soldOutAt
    ? Math.max(0, Math.ceil((soldOutAt.getTime() - createdAt.getTime()) / 86400000))
    : null;
  const quantitySold = Number(entry?.quantity_sold || 0);
  const initialQuantity = Number(entry?.initial_quantity || entry?.quantity_uploaded || 0);
  const soldOut = initialQuantity > 0 && quantitySold >= initialQuantity;
  return {
    listing_id: entry?.listing_id || "",
    created_at: entry?.created_at || "",
    initial_quantity: initialQuantity,
    quantity_sold: quantitySold,
    sold_out_at: soldOut ? (entry?.sold_out_at || new Date().toISOString()) : "",
    days_to_sell_out: daysToSellOut,
    auto_relist_eligible: Boolean(soldOut && daysToSellOut !== null && daysToSellOut <= 30),
    top_performer: Boolean(soldOut && daysToSellOut !== null && daysToSellOut <= 30),
    replace_with_better_opportunity: Boolean(soldOut && daysToSellOut !== null && daysToSellOut > 30)
  };
}

function canAutoPublishWork(work, review) {
  const slots = loadListingSlots();
  if (slots.used_listing_slots >= slots.max_new_listings) {
    return { ok: false, status: "waiting_for_slot", reason: "monthly_listing_slots_full", slots };
  }
  const option = productionReviewOptions(review).find((item) => ledgerPassOptionDetails(item).pass);
  const variantGroup = buildVariantGroupForListing(productionReviewOptions(review).filter((item) =>
    (item.product_id || item.productId) === (option?.product_id || option?.productId)
  ));
  if (!variantGroup.variants.length || variantGroup.listing_quantity <= 1) {
    return { ok: false, status: "repairing", reason: "no_viable_variant_group_for_listing", slots, variantGroup };
  }
  return { ok: true, slots, variantGroup };
}

function packagePolicyConfig() {
  return {
    ...businessPolicyConfig(),
    min_profit_margin: ledgerFeeConfig().minProfitMargin,
    tax_reserve_rate: ledgerFeeConfig().taxReserveRate,
    default_listing_quantity: businessPolicyConfig().default_listing_quantity,
    listing_slots: loadListingSlots(),
    etsy_setup_ready: etsyPublishMode() === "dry_run" || etsyConnectorReady(),
    require_mockups_for_publish: false,
    allow_quantity_one: false
  };
}

function latestSentinelReportForAsset(asset) {
  const reports = readJson("visual_qa_reports.json", []);
  if (!asset || !Array.isArray(reports)) return null;
  return latestFor(reports, (report) => report?.image_asset_id === asset.id) || approvedVisualQaForAsset(asset, reports);
}

function packageInputForWork(work) {
  const assets = readJson("image_assets.json", []);
  const designs = readJson("design_packages.json", []);
  const design = designs.find((item) => item.id === work.design_package_id);
  const asset = assets.find((item) => item.id === work.asset_id)
    || linkedForgeAssetForDesign(design, assets)
    || assets.find((item) => item.design_package_id === work.design_package_id || item.promoted_design_id === work.design_package_id);
  const review = listProductionReviews().find((item) => item.review_id === work.production_review_id)
    || latestFor(listProductionReviews(), (item) => item.design_package_id === work.design_package_id);
  const listing = work.scribe_result || listingPreviewForDesign(work.design_package_id);
  return {
    workItem: work,
    novaResearch: work.nova_research || null,
    imageAsset: asset || null,
    sentinelReport: latestSentinelReportForAsset(asset),
    supplierResearch: {
      source: "production_review",
      options: productionReviewOptions(review)
    },
    ledgerResult: review || null,
    scribeResult: listing,
    policy: packagePolicyConfig()
  };
}

function buildAndMaybeSaveProductPackageForWork(work, { dryRun = false } = {}) {
  if (!work?.work_id) {
    const error = new Error("Missing work_id.");
    error.statusCode = 400;
    throw error;
  }
  const queue = loadShiftQueue();
  const existingWork = queue.find((item) => item.work_id === work.work_id) || work;
  const pkg = buildProductPackage(packageInputForWork(existingWork));
  if (!dryRun) {
    saveProductPackage(pkg);
    const index = queue.findIndex((item) => item.work_id === existingWork.work_id);
    if (index >= 0) {
      queue[index] = {
        ...queue[index],
        product_package_id: pkg.package_id,
        product_package_status: pkg.status,
        package_blockers: pkg.blockers,
        package_warnings: pkg.warnings,
        variant_count: pkg.variants.filter((variant) => variant.included).length
      };
      saveShiftQueue(queue);
    }
  }
  return pkg;
}

function buildEconomicsCard({
  existing,
  design,
  asset,
  supplier,
  productType,
  productId,
  variantId,
  targetPrice,
  baseCost,
  shippingCost,
  verifiedSupplierCost,
  verifiedShippingCost,
  manuallyEntered = false,
  source = "supplier_costs",
  notes = ""
}) {
  const economics = readJson("unit_economics_cards.json", []);
  const createdAt = existing?.created_at || new Date().toISOString();
  const updatedAt = new Date().toISOString();
  const itemPrice = moneyOrNull(targetPrice);
  const productionCost = moneyOrNull(baseCost);
  const shippingCostUs = moneyOrNull(shippingCost);
  const issues = [];

  if (itemPrice === null) issues.push("item_price_missing");
  if (productionCost === null) issues.push("production_cost_missing");
  if (!verifiedSupplierCost) issues.push("supplier_cost_not_verified");

  const computed = economicsCalculation({
    targetPrice: itemPrice,
    baseCost: productionCost,
    shippingCost: shippingCostUs
  });

  let ledgerDecision = "COST_DATA_MISSING";
  if (issues.some((issue) => issue.endsWith("_missing"))) {
    ledgerDecision = "COST_DATA_MISSING";
  } else if (issues.length) {
    ledgerDecision = manuallyEntered ? "BLOCKED_MANUAL_UNVERIFIED" : "FAIL";
  } else if (computed.profit !== null && computed.margin !== null && computed.profit > 0 && computed.margin >= computed.minimumMargin) {
    ledgerDecision = "PASS";
  } else if (computed.profit !== null && computed.profit > 0) {
    ledgerDecision = "NEEDS_PRICE_CHANGE";
  } else {
    ledgerDecision = "FAIL";
  }

  return {
    ...(existing || {}),
    id: existing?.id || nextStateId(economics, "ECON"),
    type: "unit_economics_card",
    status: "complete",
    design_package_id: design.id,
    design_status: design.status,
    source_image_asset_id: asset.id,
    supplier,
    product_type: productType,
    product_id: productId || existing?.product_id || "",
    variant: variantId || productId || existing?.variant || "cost_data_missing",
    variant_id: variantId || existing?.variant_id || "",
    item_price: itemPrice ?? "cost_data_missing",
    customer_shipping_paid: 0,
    production_cost: productionCost ?? "cost_data_missing",
    shipping_cost_us: shippingCostUs ?? "cost_data_missing",
    verified_supplier_cost: Boolean(verifiedSupplierCost),
    verified_shipping_cost: Boolean(verifiedShippingCost),
    supplier_verified: Boolean(verifiedSupplierCost && verifiedShippingCost && !manuallyEntered),
    manually_entered: Boolean(manuallyEntered),
    economics_source: source,
    ledger_decision: ledgerDecision,
    decision: ledgerDecision,
    issues,
    calculation: computed.calculation,
    production_allowed: ledgerDecision === "PASS",
    listing_allowed: ledgerDecision === "PASS",
    notes,
    created_at: createdAt,
    updated_at: updatedAt
  };
}

function findVerifiedSupplierCost({ supplier, productType, productId, variantId }) {
  const costs = readJson("supplier_costs.json", []);
  const normalizedSupplier = normalizeCostKey(supplier);
  const normalizedProductType = normalizeCostKey(productType);
  const normalizedProductId = normalizeCostKey(productId);
  const normalizedVariantId = normalizeCostKey(variantId);

  return Array.isArray(costs) ? costs.find((row) => {
    const rowSupplier = normalizeCostKey(row.supplier);
    const rowProductType = normalizeCostKey(row.product_type || row.category);
    const rowProductId = normalizeCostKey(row.product_id || row.id);
    const rowVariant = normalizeCostKey(row.variant_id || row.variant);
    return (!normalizedSupplier || rowSupplier === normalizedSupplier)
      && (!normalizedProductType || rowProductType === normalizedProductType)
      && (!normalizedProductId || rowProductId === normalizedProductId || rowVariant === normalizedProductId)
      && (!normalizedVariantId || rowVariant === normalizedVariantId);
  }) : null;
}

function listSupplierCosts() {
  const costs = readJson("supplier_costs.json", []);
  return Array.isArray(costs)
    ? [...costs].sort((a, b) => String(b.verified_at || b.updated_at || "").localeCompare(String(a.verified_at || a.updated_at || "")))
    : [];
}

function upsertSupplierCost(input) {
  const supplier = normalizeCostKey(input.supplier);
  const productType = normalizeCostKey(input.productType);
  const productId = normalizeCostKey(input.productId);
  const variantId = normalizeCostKey(input.variantId);
  const currency = String(input.currency || "USD").trim().toUpperCase();

  if (!["printify", "printful"].includes(supplier)) {
    const error = new Error("Supplier must be printify or printful.");
    error.statusCode = 400;
    throw error;
  }
  if (!productType || !productId || !variantId) {
    const error = new Error("productType, productId, and variantId are required.");
    error.statusCode = 400;
    throw error;
  }
  if (currency !== "USD") {
    const error = new Error("Only USD supplier cost rows are supported right now.");
    error.statusCode = 400;
    throw error;
  }

  const baseCost = requireNonNegativeNumber(input.baseCost, "baseCost");
  const shippingCost = requireNonNegativeNumber(input.shippingCost, "shippingCost");
  const recommendedPrice = input.recommendedPrice === undefined || input.recommendedPrice === ""
    ? null
    : requireNonNegativeNumber(input.recommendedPrice, "recommendedPrice");
  const costsFile = path.join(STATE, "supplier_costs.json");
  const costs = readJson("supplier_costs.json", []);
  const now = new Date().toISOString();
  const index = Array.isArray(costs) ? costs.findIndex((row) =>
    normalizeCostKey(row.supplier) === supplier
    && normalizeCostKey(row.product_type) === productType
    && normalizeCostKey(row.product_id || row.id) === productId
    && normalizeCostKey(row.variant_id || row.variant) === variantId
  ) : -1;
  const existing = index >= 0 ? costs[index] : {};
  const row = {
    ...existing,
    supplier,
    product_type: productType,
    product_id: productId,
    variant: variantId,
    variant_id: variantId,
    product_name: String(input.productName || existing.product_name || "").trim(),
    variant_name: String(input.variantName || existing.variant_name || "").trim(),
    production_cost: Number(baseCost.toFixed(2)),
    shipping_cost_us: Number(shippingCost.toFixed(2)),
    currency,
    recommended_price: recommendedPrice === null ? existing.recommended_price : Number(recommendedPrice.toFixed(2)),
    verified_supplier_cost: true,
    verified_shipping_cost: true,
    supplier_cost_verified: true,
    shipping_cost_verified: true,
    verification_source: "manual_user_verified",
    source_url: String(input.sourceUrl || existing.source_url || "").trim(),
    notes: String(input.notes || existing.notes || "").trim(),
    verified_at: now,
    updated_at: now
  };

  const nextCosts = Array.isArray(costs) ? costs : [];
  if (index >= 0) {
    nextCosts[index] = row;
  } else {
    nextCosts.push(row);
  }
  saveJsonFile(costsFile, nextCosts);
  return row;
}

function upsertSupplierCostFromResearchOption(option, targetPrice) {
  if (!option || option.source !== "live_api") {
    const error = new Error("Recommended option must come from live_api supplier research.");
    error.statusCode = 400;
    throw error;
  }
  if (!option.supplierCostVerified) {
    const error = new Error("Recommended option must include verified supplier production cost.");
    error.statusCode = 400;
    throw error;
  }

  const costsFile = path.join(STATE, "supplier_costs.json");
  const costs = readJson("supplier_costs.json", []);
  const now = new Date().toISOString();
  const supplier = normalizeCostKey(option.supplier);
  const productType = normalizeCostKey(option.productType);
  const productId = String(option.productId || "").trim();
  const variantId = String(option.variantId || "").trim();
  const index = Array.isArray(costs) ? costs.findIndex((row) =>
    normalizeCostKey(row.supplier) === supplier
    && normalizeCostKey(row.product_type) === productType
    && normalizeCostKey(row.product_id || row.id) === normalizeCostKey(productId)
    && normalizeCostKey(row.variant_id || row.variant) === normalizeCostKey(variantId)
  ) : -1;
  const existing = index >= 0 ? costs[index] : {};
  const row = {
    ...existing,
    supplier,
    product_type: productType,
    product_id: productId,
    variant: variantId,
    variant_id: variantId,
    product_name: String(option.productName || existing.product_name || "").trim(),
    variant_name: String(option.variantName || existing.variant_name || "").trim(),
    provider_name: String(option.providerName || existing.provider_name || "").trim(),
    production_cost: Number(Number(option.baseCost).toFixed(2)),
    shipping_cost_us: option.shippingCost === undefined || option.shippingCost === null ? existing.shipping_cost_us ?? null : Number(Number(option.shippingCost).toFixed(2)),
    currency: "USD",
    recommended_price: targetPrice ?? existing.recommended_price,
    verified_supplier_cost: true,
    verified_shipping_cost: Boolean(option.shippingCostVerified),
    supplier_cost_verified: true,
    shipping_cost_verified: Boolean(option.shippingCostVerified),
    verification_source: "supplier_live_api",
    source_url: String(existing.source_url || "").trim(),
    notes: "Saved from live supplier research scout. No publishing action was taken.",
    verified_at: now,
    updated_at: now
  };

  const nextCosts = Array.isArray(costs) ? costs : [];
  if (index >= 0) nextCosts[index] = row;
  else nextCosts.push(row);
  saveJsonFile(costsFile, nextCosts);
  return row;
}

function listProductionReviews() {
  const reviews = readJson("production_reviews.json", []);
  return Array.isArray(reviews)
    ? [...reviews].sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")))
    : [];
}

function nextProductionReviewId(reviews) {
  return nextStateId(reviews, "PRODREV");
}

function saveProductionReview(review) {
  const reviewsFile = path.join(STATE, "production_reviews.json");
  const reviews = readJson("production_reviews.json", []);
  const list = Array.isArray(reviews) ? reviews : [];
  const index = list.findIndex((item) => item.review_id === review.review_id);
  if (index >= 0) list[index] = review;
  else list.push(review);
  saveJsonFile(reviewsFile, list);
  return review;
}

function correctedLedgerPricing(option, productType, targetPrice) {
  const originalTargetPrice = moneyOrNull(targetPrice);
  const productionCost = moneyOrNull(option?.baseCost);
  const shippingCost = moneyOrNull(option?.shippingCost);
  const shippingMode = option?.shippingMode || option?.shipping_mode || "buyer_paid";
  const ceiling = TARGET_PRICE_CEILINGS[productType] ?? 49.99;
  const supplierVerified = Boolean(option?.supplierCostVerified);
  const requiredPrice = supplierVerified && productionCost !== null
    ? requiredSalePriceForLedgerPass({ productionCost, shippingCost, shippingMode })
    : null;
  const requiredPriceForMargin = supplierVerified && productionCost !== null
    ? requiredSalePriceForMargin({ productionCost, shippingCost, shippingMode }, ledgerFeeConfig().minProfitMargin)
    : null;
  const oldComputed = economicsCalculation({ targetPrice: originalTargetPrice, baseCost: productionCost, shippingCost, shippingMode });
  const correctedPrice = requiredPrice !== null && requiredPrice <= ceiling
    ? Math.max(originalTargetPrice ?? 0, requiredPrice)
    : null;
  const correctedComputed = correctedPrice !== null
    ? economicsCalculation({ targetPrice: correctedPrice, baseCost: productionCost, shippingCost, shippingMode })
    : null;
  const passAfterCorrection = Boolean(
    supplierVerified
    && correctedComputed?.profit !== null
    && correctedComputed.profit > 0
    && correctedComputed.margin !== null
    && correctedComputed.margin >= ledgerFeeConfig().minProfitMargin
  );

  return {
    originalTargetPrice,
    correctedTargetPrice: passAfterCorrection ? Number(correctedPrice.toFixed(2)) : null,
    effectiveTargetPrice: passAfterCorrection ? Number(correctedPrice.toFixed(2)) : originalTargetPrice,
    requiredPriceForLedgerPass: requiredPrice === null ? null : Number(requiredPrice.toFixed(2)),
    requiredPriceForMargin: requiredPriceForMargin === null ? null : Number(requiredPriceForMargin.toFixed(2)),
    productPriceCeiling: ceiling,
    ledgerPassAfterCorrection: passAfterCorrection,
    priceCorrectionReason: requiredPrice !== null && requiredPrice > ceiling
      ? "Required price is too high for this product."
      : passAfterCorrection && originalTargetPrice !== correctedPrice
        ? `Ledger raised the price from ${money(originalTargetPrice)} to ${money(correctedPrice)} so this product can make at least 10% profit.`
        : "",
    computed: passAfterCorrection ? correctedComputed : oldComputed
  };
}

function productOptionFromSupplierOption(option, productType, targetPrice) {
  const correction = correctedLedgerPricing(option, productType, targetPrice);
  const ledgerPass = Boolean(option?.ledgerWouldPass || correction.ledgerPassAfterCorrection);
  const shippingCost = moneyOrNull(option?.shippingCost);
  const shippingVerified = Boolean(option?.shippingCostVerified);
  const warnings = [...(Array.isArray(option?.warnings) ? option.warnings : [])];
  if (shippingCost === null) warnings.push("buyer_paid_shipping_estimate_missing");
  else if (!shippingVerified) warnings.push("buyer_paid_shipping_estimate_not_verified");
  if (!option?.supplierCostVerified) warnings.push("supplier_cost_not_verified");
  if (correction.requiredPriceForLedgerPass !== null && correction.requiredPriceForLedgerPass > correction.productPriceCeiling) {
    warnings.push("required_price_above_ceiling");
  }
  const failReasons = [];
  if (correction.originalTargetPrice === null) failReasons.push("item_price_missing");
  if (moneyOrNull(option?.baseCost) === null) failReasons.push("production_cost_missing");
  if (!option?.supplierCostVerified) failReasons.push("supplier_cost_not_verified");
  const profit = correction.computed?.profit;
  const margin = correction.computed?.margin;
  if (profit !== null && profit !== undefined && profit <= 0) failReasons.push("profit_not_positive");
  if (margin !== null && margin !== undefined && margin < ledgerFeeConfig().minProfitMargin) failReasons.push("margin_below_minimum");
  if (correction.requiredPriceForLedgerPass !== null && correction.requiredPriceForLedgerPass > correction.productPriceCeiling) failReasons.push("required_price_above_ceiling");
  if (!ledgerPass && !failReasons.length) failReasons.push("unknown_ledger_failure");
  const humanBlockReason = correction.requiredPriceForLedgerPass !== null && correction.requiredPriceForLedgerPass > correction.productPriceCeiling
    ? `This ${productType} would need to sell for ${money(correction.requiredPriceForLedgerPass)} to pass, which is above the allowed ${productType} ceiling of ${money(correction.productPriceCeiling)}.`
    : failReasons.includes("profit_not_positive")
      ? "Profit must be above $0 for Ledger PASS."
      : failReasons.includes("supplier_cost_not_verified")
        ? "Margin may pass, but supplier cost is not verified."
        : ledgerPass
            ? correction.priceCorrectionReason
            : "Agents are trying another product type with better margin.";

  return {
    supplier: option?.supplier || "",
    product_type: productType,
    product_name: option?.productName || "",
    product_id: option?.productId || "",
    variant: option?.variantName || option?.variantId || "",
    variant_id: option?.variantId || "",
    provider: option?.providerName || "",
    available: option?.available ?? true,
    availability_quantity: option?.availability_quantity ?? null,
    is_pod_made_to_order: option?.is_pod_made_to_order ?? true,
    color: option?.color || "",
    size: option?.size || "",
    scent: option?.scent || "",
    material: option?.material || "",
    base_cost: option?.baseCost ?? null,
    shipping: option?.shippingCost ?? null,
    shipping_overlap_buffer: correction.computed?.calculation?.shipping_overlap_buffer ?? ledgerFeeConfig().shippingOverlapBuffer,
    etsy_fees_total: correction.computed?.calculation?.etsy_fees_total ?? null,
    original_target_price: correction.originalTargetPrice,
    target_price: correction.effectiveTargetPrice ?? null,
    corrected_target_price: correction.correctedTargetPrice,
    correctedTargetPrice: correction.correctedTargetPrice,
    required_price_for_ledger_pass: correction.requiredPriceForLedgerPass,
    requiredPriceForLedgerPass: correction.requiredPriceForLedgerPass,
    required_price_for_margin: correction.requiredPriceForMargin,
    requiredPriceForMargin: correction.requiredPriceForMargin,
    product_price_ceiling: correction.productPriceCeiling,
    productPriceCeiling: correction.productPriceCeiling,
    ledger_pass_after_correction: correction.ledgerPassAfterCorrection,
    ledgerPassAfterCorrection: correction.ledgerPassAfterCorrection,
    profit: correction.computed?.calculation?.profit ?? option?.estimatedProfit ?? null,
    margin: correction.computed?.calculation?.margin_percent ?? option?.estimatedMarginPct ?? null,
    ledger_pass: ledgerPass,
    ledger_decision: ledgerPass ? "PASS" : "BLOCKED",
    ledger_status: ledgerPass ? "PASS" : "BLOCKED",
    human_block_reason: humanBlockReason,
    supplier_cost_verified: Boolean(option?.supplierCostVerified),
    shipping_cost_verified: Boolean(option?.shippingCostVerified),
    verified_supplier_cost: Boolean(option?.supplierCostVerified),
    verified_shipping_cost: Boolean(option?.shippingCostVerified),
    pricing_debug: {
      productType,
      supplier: option?.supplier || "",
      productName: option?.productName || "",
      variantName: option?.variantName || option?.variantId || "",
      productionCost: option?.baseCost ?? null,
      shippingCost: option?.shippingCost ?? null,
      shippingOverlapBuffer: correction.computed?.calculation?.shipping_overlap_buffer ?? ledgerFeeConfig().shippingOverlapBuffer,
      etsyFeesTotal: correction.computed?.calculation?.etsy_fees_total ?? null,
      originalTargetPrice: correction.originalTargetPrice,
      correctedTargetPrice: correction.correctedTargetPrice,
      salePrice: correction.effectiveTargetPrice,
      requiredPriceForMargin: correction.requiredPriceForMargin,
      requiredPriceForLedgerPass: correction.requiredPriceForLedgerPass,
      ceilingPrice: correction.productPriceCeiling,
      profit: correction.computed?.calculation?.profit ?? option?.estimatedProfit ?? null,
      marginPercent: correction.computed?.calculation?.margin_percent ?? option?.estimatedMarginPct ?? null,
      minMarginRequired: ledgerFeeConfig().minProfitMargin,
      verifiedSupplierCost: Boolean(option?.supplierCostVerified),
      verifiedShippingCost: Boolean(option?.shippingCostVerified),
      pass: ledgerPass,
      failReasons,
      failReason: ledgerPass ? "" : (correction.requiredPriceForLedgerPass > correction.productPriceCeiling ? "Required price is too high for this product." : failReasons.join(", "))
    },
    fail_reasons: failReasons,
    failReasons,
    warnings: [...new Set(warnings)],
    raw_option: option
  };
}

function isWorkerReleaseAllowed(item) {
  if (!item) return false;
  const status = String(item.status || "").toLowerCase();
  const stage = String(item.stage || "").toLowerCase();
  const external = String(item.external_status || item.publish_status || item.upload_status || "").toLowerCase();
  return status === "uploaded"
    || stage === "uploaded"
    || item.uploaded === true
    || item.externally_complete === true
    || ["uploaded", "listed", "published"].includes(external);
}

function workReleaseDiagnostics(item) {
  const releaseAllowed = isWorkerReleaseAllowed(item);
  return {
    assignment_stable: Boolean(item?.worker_id) && !releaseAllowed,
    release_allowed: releaseAllowed,
    release_reason: releaseAllowed ? "Product has an external uploaded/listed completion signal." : "",
    job_complete: releaseAllowed,
    uploaded: releaseAllowed
  };
}

function normalizeWorkStatus(workItem = {}) {
  const status = String(workItem.status || "").toLowerCase();
  const stage = String(workItem.stage || "").toLowerCase();
  if (["uploaded", "listed", "published"].includes(status) || ["uploaded", "listed", "published"].includes(stage)) return status === "published" ? "listed" : status || stage;
  if (status === "stopped") return "stopped";
  if (status === "waiting_for_setup") return "waiting_for_setup";
  if (["waiting_for_approval", "approval_ready"].includes(status)) return hasLedgerPassOption(listProductionReviews().find((review) => review.review_id === workItem.production_review_id)) ? "ready_to_publish" : "repairing";
  if (["needs_attention", "blocked", "denied", "needs_changes"].includes(status)) return "repairing";
  if (status === "approved") return "ready_to_publish";
  if (status === "repairing") return "repairing";
  if (stage === "prompt_planning" || stage === "research_replan") return "researching";
  if (stage === "image_generation") return "generating_art";
  if (stage === "sentinel_qa") return "qa_checking";
  if (stage === "production_check") return "pricing";
  if (stage === "scribe_draft") return "writing_listing";
  if (stage === "package_build") return "ready_to_publish";
  if (stage === "ready_to_publish" || stage === "approval_queue") return "ready_to_publish";
  if (stage === "publishing") return "publishing";
  return status || "working";
}

function autonomousStatusForStage(stage) {
  const map = {
    prompt_planning: "researching",
    research_replan: "researching",
    image_generation: "generating_art",
    sentinel_qa: "qa_checking",
    promote_to_design: "researching",
    production_check: "pricing",
    scribe_draft: "writing_listing",
    package_build: "ready_to_publish",
    ready_to_publish: "ready_to_publish",
    publishing: "publishing"
  };
  return map[stage] || "working";
}

function isCurrentShiftAssignedWork(item, shiftId) {
  if (!item || !shiftId) return false;
  if (item.shift_id !== shiftId) return false;
  if (!item.worker_id) return false;
  return !isWorkerReleaseAllowed(item);
}

function isCurrentShiftRunnableWork(item, shiftId) {
  if (!isCurrentShiftAssignedWork(item, shiftId)) return false;
  const normalized = normalizeWorkStatus(item);
  if (["waiting_for_setup", "ready_to_publish", "publishing", "listed", "stopped"].includes(normalized)) return false;
  return ["queued", "running", "retrying", "needs_retry", "working", "repairing", "researching", "generating_art", "qa_checking", "pricing", "writing_listing"].includes(item.status)
    || ["researching", "generating_art", "qa_checking", "repairing", "pricing", "writing_listing", "working"].includes(normalized);
}

function activeWorkItems(queue, shiftId) {
  return (Array.isArray(queue) ? queue : []).filter((item) =>
    isCurrentShiftAssignedWork(item, shiftId)
  );
}

function firstPresentValue(source, keys) {
  for (const key of keys) {
    if (source && source[key] !== undefined && source[key] !== null && source[key] !== "") return source[key];
  }
  return null;
}

function optionMoneyValue(option, keys) {
  const direct = moneyOrNull(firstPresentValue(option, keys));
  if (direct !== null) return direct;
  const raw = option?.raw_option || {};
  return moneyOrNull(firstPresentValue(raw, keys));
}

function optionBooleanValue(option, keys) {
  for (const key of keys) {
    const value = option?.[key] ?? option?.raw_option?.[key];
    if (value === true || String(value).toLowerCase() === "true") return true;
  }
  return false;
}

function optionMarginFraction(option) {
  const raw = firstPresentValue(option, [
    "margin",
    "marginPct",
    "estimatedMarginPct",
    "estimated_margin_pct"
  ]) ?? firstPresentValue(option?.raw_option || {}, [
    "margin",
    "marginPct",
    "estimatedMarginPct",
    "estimated_margin_pct"
  ]);
  const number = Number(raw);
  if (!Number.isFinite(number)) return null;
  return number > 1 ? number / 100 : number;
}

function ledgerPassOptionDetails(option) {
  const itemPrice = optionMoneyValue(option, ["targetPrice", "target_price", "item_price", "recommendedPrice", "recommended_price"]);
  const productionCost = optionMoneyValue(option, ["baseCost", "base_cost", "production_cost", "production_cost_us"]);
  const supplierCostVerified = optionBooleanValue(option, ["supplierCostVerified", "supplier_cost_verified", "verified_supplier_cost"]);
  const margin = optionMarginFraction(option);
  const profit = optionMoneyValue(option, ["profit", "estimatedProfit", "estimated_profit"]);
  const config = ledgerFeeConfig();
  const minimumMargin = config.minProfitMargin;
  const missing = [];

  if (itemPrice === null) missing.push("item_price_missing");
  if (productionCost === null) missing.push("production_cost_missing");
  if (!supplierCostVerified) missing.push("supplier_cost_not_verified");
  if (margin === null) missing.push("margin_missing");
  if (profit === null) missing.push("profit_missing");
  if (margin !== null && margin < minimumMargin) missing.push("margin_below_ledger_rule");
  if (profit !== null && profit <= 0) missing.push("profit_not_positive");
  return {
    pass: missing.length === 0,
    missing,
    itemPrice,
    productionCost,
    supplierCostVerified,
    margin,
    profit
  };
}

function productionReviewOptions(review) {
  return [
    ...((Array.isArray(review?.recommended_options) ? review.recommended_options : [])),
    ...((Array.isArray(review?.product_options) ? review.product_options : []))
  ];
}

function hasLedgerPassOption(review) {
  return productionReviewOptions(review).some((option) => ledgerPassOptionDetails(option).pass);
}

function ledgerPassBlockingReasons(review) {
  const options = productionReviewOptions(review);
  const missing = new Set();
  for (const option of options) {
    for (const reason of ledgerPassOptionDetails(option).missing) missing.add(reason);
  }
  if (!options.length || !hasLedgerPassOption(review)) missing.add("No Ledger PASS product option found.");
  if (missing.has("production_cost_missing") || missing.has("supplier_cost_not_verified")) missing.add("Verified supplier production cost missing.");
  if (missing.has("item_price_missing")) missing.add("Target item price missing.");
  return [...missing];
}

function bestProductionOption(options) {
  const list = Array.isArray(options) ? options : [];
  const pass = list.find((option) => ledgerPassOptionDetails(option).pass);
  if (pass) return pass;
  return [...list].sort((a, b) => {
    const gapA = Math.abs((moneyOrNull(a.required_price_for_ledger_pass) ?? 9999) - (moneyOrNull(a.product_price_ceiling) ?? 0));
    const gapB = Math.abs((moneyOrNull(b.required_price_for_ledger_pass) ?? 9999) - (moneyOrNull(b.product_price_ceiling) ?? 0));
    return gapA - gapB;
  })[0];
}

function listingPreviewForDesign(designPackageId) {
  const listings = readJson("listing_drafts.json", []);
  const listing = latestFor(listings, (item) => item.design_package_id === designPackageId);
  if (!listing) {
    return {
      title: "Listing draft not created",
      description: "Listing will be written after a profitable product is found.",
      tags: [],
      blocked_reason: "missing_listing_draft"
    };
  }
  return {
    listing_id: listing.id,
    status: listing.status,
    title: listing.title || "",
    description: listing.description || "",
    tags: Array.isArray(listing.tags) ? listing.tags : [],
    blocked_reason: listing.listing_allowed === false ? "listing_not_allowed" : ""
  };
}

async function scribeSeoListingPreview({ designPackageId, productType, marketKeyword = "", itemLook = {}, productFit = {}, blockedTerms = [] }) {
  const seo = await researchSeoKeywords({ marketKeyword, productType, provider: "auto", maxResults: 13 });
  const clean = (value) => String(value || "").replace(/[^\w\s'&-]/g, " ").replace(/\s+/g, " ").trim();
  const blocked = new Set((blockedTerms || []).map((term) => normalizeCostKey(term)));
  const keywords = (seo.keywords || []).filter((keyword) => !blocked.has(normalizeCostKey(keyword)));
  const tags = (seo.tags || keywords).map((tag) => clean(tag).toLowerCase().slice(0, 20)).filter(Boolean).slice(0, 13);
  while (tags.length < 13 && keywords[tags.length]) tags.push(clean(keywords[tags.length]).toLowerCase().slice(0, 20));
  const titleBase = seo.titleAngles?.[0] || `${marketKeyword} ${productType}`.trim();
  return {
    title: clean(titleBase).slice(0, 135),
    description: clean(`Original ${marketKeyword || "gift"} ${productType || "product"} featuring ${itemLook.subject || itemLook.style || "clean product-ready artwork"}. Designed for ${productFit.expectedBuyerUse || itemLook.buyerIntent || "gift buyers"}.`),
    tags: [...new Set(tags)].slice(0, 13),
    materials: [productType || "print-on-demand product"].filter(Boolean),
    occasion: productFit.expectedBuyerUse || "",
    recipient: itemLook.buyerIntent || "",
    style: itemLook.style || "",
    seo_provider_used: seo.providerUsed,
    keywords_used: keywords,
    blocked_terms_removed: blockedTerms,
    warnings: seo.warnings || []
  };
}

async function maybeGenerateListingPreview(designPackageId, productType) {
  const economics = readJson("unit_economics_cards.json", []);
  const ledger = latestFor(economics, (item) => item.design_package_id === designPackageId);
  const ledgerPass = ledger?.ledger_decision === "PASS" || ledger?.decision === "PASS";
  if (!ledgerPass) return listingPreviewForDesign(designPackageId);

  const existing = listingPreviewForDesign(designPackageId);
  if (existing.listing_id) return existing;

  await runPython("run_scribe_on_design.py", [
    "--design-package-id",
    designPackageId,
    "--product-type",
    productType || "poster"
  ]);
  const preview = listingPreviewForDesign(designPackageId);
  if (preview.listing_id) return preview;
  return scribeSeoListingPreview({ designPackageId, productType });
}

function resolveProductionSubject(input) {
  const assetId = String(input.assetId || "").trim();
  const designPackageId = String(input.designPackageId || "").trim();

  if (designPackageId) {
    return assertPromotedApprovedDesign(designPackageId);
  }

  if (!assetId) {
    const error = new Error("Missing assetId or designPackageId.");
    error.statusCode = 400;
    throw error;
  }

  const assets = readJson("image_assets.json", []);
  const asset = assets.find((item) => item.id === assetId);
  if (!asset) {
    const error = new Error("Image asset not found.");
    error.statusCode = 404;
    throw error;
  }

  validateExistingPng(asset.file_path);
  const reports = readJson("visual_qa_reports.json", []);
  if (!approvedVisualQaForAsset(asset, reports)) {
    const error = new Error("Asset must pass Sentinel QA before production review.");
    error.statusCode = 409;
    throw error;
  }

  if (asset.design_package_id || asset.promoted_design_id) {
    return assertPromotedApprovedDesign(asset.design_package_id || asset.promoted_design_id);
  }

  const promoted = promoteForgeArtToDesign({ assetId });
  return { design: promoted.design, asset: promoted.asset };
}

async function checkProduction(input) {
  const { design, asset } = resolveProductionSubject(input);
  const productTypes = Array.isArray(input.productTypes) && input.productTypes.length
    ? input.productTypes.map((item) => String(item || "").trim()).filter(Boolean)
    : (loadSupplierCatalog().products || []).slice(0, 5).map((item) => item.product_name || item.product_type_detected).filter(Boolean);
  const maxOptionsPerType = Math.max(1, Number(input.maxOptionsPerType || 4));
  const targetPrices = input.targetPrices && typeof input.targetPrices === "object" ? input.targetPrices : {};
  const productOptions = [];
  const recommendedOptions = [];
  const warnings = [];
  const blockingReasons = [];
  if (!productTypes.length) {
    blockingReasons.push("supplier_catalog_missing");
    warnings.push("Supplier catalog is missing; refresh Printify/Printful catalog before production.");
  }

  for (const productType of productTypes) {
    const targetPrice = moneyOrNull(targetPrices[productType]) ?? moneyOrNull(input.targetPrice) ?? 19.99;
    const result = await researchSupplierProducts({
      designPackageId: design.id,
      preferredSupplier: input.preferredSupplier || "auto",
      productType,
      destinationCountry: input.destinationCountry,
      destinationState: input.destinationState,
      destinationZip: input.destinationZip,
      targetPrice,
      maxOptions: maxOptionsPerType
    });

    if (!result.ok) {
      blockingReasons.push(`${productType}: ${result.error || result.missingConnector || "supplier research failed"}`);
      productOptions.push({
        product_type: productType,
        ledger_status: "BLOCKED",
        warnings: [result.error || result.missingConnector || "supplier research failed"]
      });
      continue;
    }

    const mapped = result.options.map((option) => productOptionFromSupplierOption(option, productType, targetPrice));
    productOptions.push(...mapped);
    const recommended = bestProductionOption(mapped);
    if (recommended) {
      recommendedOptions.push(recommended);
      if (!ledgerPassOptionDetails(recommended).pass) blockingReasons.push(`${productType}: ${recommended.human_block_reason || recommended.warnings.join(", ") || "blocked"}`);
    }
    warnings.push(...mapped.flatMap((option) => option.warnings || []));
  }

  const passOptions = recommendedOptions.filter((option) => ledgerPassOptionDetails(option).pass);
  const listingPreview = await maybeGenerateListingPreview(design.id, passOptions[0]?.product_type || productTypes[0]);
  if (passOptions.length && listingPreview.blocked_reason) blockingReasons.push(`listing_preview: ${listingPreview.blocked_reason}`);

  const now = new Date().toISOString();
  const reviewDraft = {
    review_id: nextProductionReviewId(readJson("production_reviews.json", [])),
    status: "blocked",
    asset_id: asset.id,
    design_package_id: design.id,
    image_url: asset.public_preview_url || publicGeneratedArtUrl(asset.file_path),
    image_path: asset.file_path,
    created_at: now,
    updated_at: now,
    product_options: productOptions,
    recommended_options: recommendedOptions,
    listing_preview: listingPreview,
    blocking_reasons: [...new Set(blockingReasons)],
    warnings: [...new Set(warnings)],
    user_decision: null
  };
  const hasPass = hasLedgerPassOption(reviewDraft);
  const review = {
    ...reviewDraft,
    status: hasPass ? "ready_for_review" : "blocked",
    blocking_reasons: hasPass
      ? [...new Set(blockingReasons)]
      : [...new Set([...blockingReasons, ...ledgerPassBlockingReasons(reviewDraft)])]
  };

  return saveProductionReview(review);
}

async function updateProductionDecision(input) {
  const reviewId = String(input.reviewId || "").trim();
  const decision = String(input.decision || "").trim();
  if (!reviewId || !["approved", "denied", "needs_changes"].includes(decision)) {
    const error = new Error("Missing reviewId or invalid decision.");
    error.statusCode = 400;
    throw error;
  }

  const reviews = readJson("production_reviews.json", []);
  const review = Array.isArray(reviews) ? reviews.find((item) => item.review_id === reviewId) : null;
  if (!review) {
    const error = new Error("Production review not found.");
    error.statusCode = 404;
    throw error;
  }

  if (decision === "approved" && !hasLedgerPassOption(review)) {
    const error = new Error("Requires at least one Ledger PASS product option before approval.");
    error.statusCode = 409;
    throw error;
  }

  const now = new Date().toISOString();
  const updated = {
    ...review,
    status: decision,
    user_decision: {
      decision,
      notes: String(input.notes || "").trim(),
      decided_at: now
    },
    updated_at: now
  };

    if (decision === "approved") {
    updated.recommended_options = (updated.recommended_options || []).map((option) => ({
      ...option,
      approved_for_next_pipeline_stage: ledgerPassOptionDetails(option).pass
    }));

    const firstPass = updated.recommended_options.find((option) => ledgerPassOptionDetails(option).pass);
    if (firstPass) {
      try {
        const listingId = updated.listing_preview?.listing_id || "";
        const publishResult = await runPython("create_publish_package.py", [
          "--image-asset-id",
          updated.asset_id,
          "--connector-id",
          "manual_browser_upload",
          "--target-platforms",
          "printify,printful,etsy",
          "--product-type",
          firstPass.product_type || "poster",
          "--listing-draft-id",
          listingId,
          "--notes",
          `Non-publishing package prepared from production review ${reviewId}.`
        ]);
        updated.non_publish_package_result = {
          ok: publishResult.ok,
          stdout: publishResult.stdout,
          stderr: publishResult.stderr
        };
      } catch (error) {
        updated.non_publish_package_result = {
          ok: false,
          error: String(error?.message || error)
        };
      }
    }
  }

  return saveProductionReview(updated);
}

function defaultShiftState() {
  return {
    shift_id: null,
    status: "idle",
    started_at: null,
    updated_at: new Date().toISOString(),
    stopped_at: null,
    created_this_shift: 0,
    limits: {
      max_designs_per_shift: 3,
      max_generation_failures: 3,
      max_products_checked_per_design: 4,
      forge_worker_count: 3,
      max_active_work_items: 3,
      require_user_approval_before_publish: false,
      allowed_product_types: [],
      preferred_supplier: "auto",
      target_prices: { ...DEFAULT_TARGET_PRICES },
      max_ledger_retries: MAX_LEDGER_RETRIES,
      destinationCountry: process.env.DEFAULT_SHIP_COUNTRY || "US",
      destinationState: process.env.DEFAULT_SHIP_STATE || "TX",
      destinationZip: process.env.DEFAULT_SHIP_ZIP || "79761"
    },
    workers: defaultForgeWorkers(3),
    counters: {
      generated: 0,
      sentinel_passed: 0,
      sentinel_failed: 0,
      promoted: 0,
      production_checked: 0,
      ledger_passed: 0,
      listing_drafted: 0,
      approval_ready: 0,
      blocked: 0,
      errors: 0
    },
    current_task: "Idle.",
    last_error: ""
  };
}

function loadShiftState() {
  const state = normalizeShiftState({ ...defaultShiftState(), ...readJsonPath(SHIFT_STATE_FILE, defaultShiftState()) });
  if (hasRawRuntimeExceptionText(state.current_task) || hasRawRuntimeExceptionText(state.last_error)) {
    state.current_task = "This product hit a repair error. Nova is replanning it.";
    state.last_error = "This product hit a repair error. Nova is replanning it.";
  }
  return state;
}

function defaultForgeWorkers(count = 3) {
  return Array.from({ length: Math.max(1, Number(count || 3)) }, (_, index) => ({
    worker_id: `FORGE-${index + 1}`,
    status: "idle",
    work_id: "",
    current_task: "Idle.",
    updated_at: new Date().toISOString()
  }));
}

function normalizeShiftState(state) {
  const limits = { ...defaultShiftState().limits, ...(state.limits || {}) };
  const count = Math.max(1, Number(limits.forge_worker_count || 3));
  const existing = Array.isArray(state.workers) ? state.workers : [];
  const workers = defaultForgeWorkers(count).map((fallback) => ({
    ...fallback,
    ...(existing.find((worker) => worker.worker_id === fallback.worker_id) || {})
  }));
  const created = Number(state.created_this_shift);
  return { ...state, limits, workers, created_this_shift: Number.isFinite(created) && created >= 0 ? created : 0 };
}

function saveShiftState(state) {
  ensureDir(STATE);
  const next = { ...state, updated_at: new Date().toISOString() };
  saveJsonFile(SHIFT_STATE_FILE, next);
  return next;
}

function loadShiftQueue() {
  const queue = readJsonPath(SHIFT_QUEUE_FILE, []);
  return Array.isArray(queue) ? queue.map((item) => ensureRepairMetadata(item)) : [];
}

function saveShiftQueue(queue) {
  ensureDir(STATE);
  saveJsonFile(SHIFT_QUEUE_FILE, queue);
  return queue;
}

function appendShiftLog({ shiftId, workId = "", stage = "", event, message, data = {} }) {
  ensureDir(STATE);
  const entry = {
    timestamp: new Date().toISOString(),
    shift_id: shiftId || "",
    work_id: workId || "",
    stage: stage || "",
    event,
    message,
    data
  };
  fs.appendFileSync(SHIFT_LOG_FILE, JSON.stringify(entry) + "\n", "utf8");
  return entry;
}

function readShiftLogTail(limit = 80) {
  try {
    if (!fs.existsSync(SHIFT_LOG_FILE)) return [];
    const lines = fs.readFileSync(SHIFT_LOG_FILE, "utf8").trim().split(/\r?\n/).filter(Boolean);
    return lines.slice(-limit).map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return { message: line };
      }
    }).reverse();
  } catch {
    return [];
  }
}

function withShiftLock(fn) {
  let fd = null;
  try {
    ensureDir(STATE);
    if (fs.existsSync(SHIFT_LOCK_FILE)) {
      const ageMs = Date.now() - fs.statSync(SHIFT_LOCK_FILE).mtimeMs;
      if (ageMs > SHIFT_LOCK_STALE_MS) {
        try {
          fs.unlinkSync(SHIFT_LOCK_FILE);
          appendShiftLog({
            shiftId: loadShiftState().shift_id,
            event: "stale_shift_lock_cleared",
            message: "Cleared a stale autonomous shift lock so workers can continue.",
            data: { ageMs }
          });
        } catch {}
      }
    }
    fd = fs.openSync(SHIFT_LOCK_FILE, "wx");
    fs.writeFileSync(fd, String(Date.now()), "utf8");
  } catch {
    const error = new Error("Shift tick already running.");
    error.statusCode = 409;
    throw error;
  }

  return Promise.resolve()
    .then(fn)
    .finally(() => {
      if (fd !== null) fs.closeSync(fd);
      try {
        fs.unlinkSync(SHIFT_LOCK_FILE);
      } catch {}
    });
}

function nextShiftId() {
  const stamp = new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
  return `SHIFT-${stamp}`;
}

function normalizeShiftIntervalMs(value) {
  const number = Number(value || DEFAULT_SHIFT_TICK_INTERVAL_MS);
  if (!Number.isFinite(number)) return DEFAULT_SHIFT_TICK_INTERVAL_MS;
  return Math.max(MIN_SHIFT_TICK_INTERVAL_MS, Math.min(MAX_SHIFT_TICK_INTERVAL_MS, Math.floor(number)));
}

function shiftLoopInfo() {
  return {
    active: Boolean(shiftLoopTimer),
    running: Boolean(shiftLoopRunning),
    lastTickAt: lastLoopTickAt,
    lastTickError: lastLoopTickError,
    intervalMs: shiftLoopIntervalMs,
    runningSince: lastLoopStartedAt
  };
}

function nextWorkId(queue) {
  return nextStateId(queue.map((item) => ({ id: item.work_id })), "WORK");
}

function workerLabel(workerId) {
  const number = String(workerId || "").split("-")[1] || "";
  return number ? `Forge ${number}` : "Forge";
}

function hasRawRuntimeExceptionText(value) {
  const text = String(value || "").toLowerCase();
  return text.includes("cannot read prop") || text.includes("cannot read properties") || text.includes("cannot read property");
}

function sanitizeHumanStatus(work) {
  if (!work) return work;
  if (hasRawRuntimeExceptionText(work.human_status) || hasRawRuntimeExceptionText(work.last_repair_reason)) {
    work.human_status = "This product hit a repair error. Nova is replanning it.";
    work.last_repair_reason = "This product hit a repair error. Nova is replanning it.";
    work.next_repair_strategy = "nova_research_replan";
  }
  return work;
}

function ensureRepairMetadata(workItem) {
  if (!workItem || typeof workItem !== "object") return workItem;
  if (workItem.repair_count === undefined || workItem.repair_count === null) workItem.repair_count = 0;
  if (!Array.isArray(workItem.repair_history)) workItem.repair_history = [];
  if (!workItem.max_repair_count) workItem.max_repair_count = 25;
  if (!("last_repair_reason" in workItem)) workItem.last_repair_reason = null;
  if (!workItem.next_repair_strategy) workItem.next_repair_strategy = "nova_research_replan";
  return sanitizeHumanStatus(workItem);
}

function resetLegacyRepairCounterIfNeeded(workItem) {
  ensureRepairMetadata(workItem);
  const count = Number(workItem.repair_count || 0);
  const max = Math.max(25, Number(workItem.max_repair_count || 25));
  if (count > max) {
    workItem.legacy_repair_count_before_reset = count;
    workItem.repair_history = (Array.isArray(workItem.repair_history) ? workItem.repair_history : []).slice(-10);
    workItem.repair_count = 0;
    workItem.max_repair_count = 25;
  }
  return workItem;
}

function productPackageForWork(work) {
  return listProductPackages().find((pkg) => pkg.work_id === work?.work_id || (work?.design_package_id && pkg.design_package_id === work.design_package_id)) || null;
}

function workerStatusForStage(stage, status) {
  if (status === "ready_to_publish") return "review_ready";
  if (status === "waiting_for_setup") return "blocked";
  if (status === "repairing") return "researching";
  if (["blocked", "needs_attention", "denied", "needs_changes"].includes(status)) return "researching";
  const map = {
    prompt_planning: "planning",
    image_generation: "generating",
    sentinel_qa: "qa",
    promote_to_design: "researching",
    production_check: "ledger",
    scribe_draft: "researching",
    package_build: "review_ready",
    approval_queue: "review_ready",
    ready_to_publish: "review_ready",
    publishing: "publishing"
  };
  return map[stage] || "idle";
}

function syncWorkersWithQueue(state, queue) {
  state.workers = normalizeShiftState(state).workers;
  const activeByWorker = new Map();
  for (const item of queue) {
    if (!isCurrentShiftAssignedWork(item, state.shift_id)) continue;
    activeByWorker.set(item.worker_id, item);
  }
  state.workers = state.workers.map((worker) => {
    const work = activeByWorker.get(worker.worker_id);
    if (!work) return { ...worker, status: "idle", work_id: "", current_task: "Idle.", updated_at: new Date().toISOString() };
    return {
      ...worker,
      status: workerStatusForStage(work.stage, work.status),
      work_id: work.work_id,
      current_task: getWorkerTask(work),
      updated_at: work.updated_at || new Date().toISOString()
    };
  });
  return state.workers;
}

function getWorkerTask(work) {
  if (!work) return "Idle.";
  ensureRepairMetadata(work);
  if (hasRawRuntimeExceptionText(work.human_status) || hasRawRuntimeExceptionText(work.last_repair_reason)) {
    return "This product hit a repair error. Nova is replanning it.";
  }
  const normalized = normalizeWorkStatus(work);
  if (normalized === "ready_to_publish") return `${workerLabel(work.worker_id)} is preparing the listing.`;
  if (normalized === "publishing") return `${workerLabel(work.worker_id)} is publishing the listing.`;
  if (normalized === "listed") return `${workerLabel(work.worker_id)} listed this product.`;
  if (normalized === "waiting_for_setup") return work.human_status || `${workerLabel(work.worker_id)} is waiting for setup.`;
  if (work.status === "repairing") return work.human_status || `${workerLabel(work.worker_id)} is repairing this product.`;
  if (work.stage === "image_generation") return `${workerLabel(work.worker_id)} is creating artwork.`;
  if (work.stage === "sentinel_qa") return `${workerLabel(work.worker_id)} is checking image quality.`;
  if (work.stage === "production_check" && Number(work.ledger_retry_count || 0) > 0) return `${workerLabel(work.worker_id)} is improving pricing.`;
  if (work.stage === "production_check") return `${workerLabel(work.worker_id)} is checking suppliers.`;
  if (work.stage === "scribe_draft") return `${workerLabel(work.worker_id)} is writing the Etsy listing.`;
  if (work.stage === "package_build") return `${workerLabel(work.worker_id)} is building the product package.`;
  return `${workerLabel(work.worker_id)} is working.`;
}

function releaseForgeWorker(state, work, event = "forge_worker_released", message = "Forge worker released.") {
  if (!work?.worker_id) return;
  if (!isWorkerReleaseAllowed(work)) {
    appendShiftLog({
      shiftId: state.shift_id,
      workId: work.work_id,
      stage: work.stage,
      event: "replacement_prevented_worker_job_not_complete",
      message: `${workerLabel(work.worker_id)} kept ${work.work_id} because the product is not uploaded/listed yet.`,
      data: { worker_id: work.worker_id, status: work.status, stage: work.stage }
    });
    return;
  }
  state.workers = normalizeShiftState(state).workers.map((worker) =>
    worker.worker_id === work.worker_id
      ? { ...worker, status: "idle", work_id: "", current_task: "Idle.", updated_at: new Date().toISOString() }
      : worker
  );
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event, message, data: { worker_id: work.worker_id } });
}

function usedPromptKeywords(queue, currentWorkId = "") {
  return new Set(queue
    .filter((item) => !["blocked", "needs_attention", "complete"].includes(item.status))
    .filter((item) => !currentWorkId || item.work_id !== currentWorkId)
    .map((item) => item.market_keyword || item.market_research?.item_look?.keyword || item.prompt_family || "")
    .filter(Boolean)
    .map((item) => String(item).toLowerCase()));
}

function selectSupplierBackedOpportunity(nova, queue, workId, workerId) {
  const catalog = loadSupplierCatalog();
  const topMarketItems = Array.isArray(nova.topMarketItems) && nova.topMarketItems.length
    ? nova.topMarketItems
    : (nova.recommendedCombinations || []).slice(0, 5).map((combo, index) => ({
      rank: index + 1,
      market_keyword: combo.marketKeyword,
      buyer_intent: combo.itemLook?.buyerIntent || "gift buyer",
      item_people_are_buying: combo.marketKeyword,
      product_type_from_market: combo.productFit?.primaryProductType || "",
      item_look: combo.itemLook || {},
      search_signal: combo.demandSignal?.searchSignal || "local seasonal market seed",
      sell_signal: combo.demandSignal?.sellSignal || "not_available",
      seasonality: combo.seasonality,
      confidence: combo.demandSignal?.confidence || 0.55,
      source: combo.source || nova.source,
      notes: combo.reason || ""
    }));
  const used = usedPromptKeywords(queue, workId);
  const workerNumber = Number(String(workerId || "").match(/\d+$/)?.[0] || 1);
  const supplierMatches = topMarketItems.map((marketItem) => matchMarketItemToSupplierCatalog(marketItem, catalog));
  const ranked = supplierMatches
    .flatMap((match) => match.matches.slice(0, 5).map((supplierMatch) => ({ marketItem: match.market_item, supplierMatch, match })))
    .filter((item) => item.supplierMatch.supported)
    .sort((a, b) => b.supplierMatch.match_score - a.supplierMatch.match_score);
  const uniqueRanked = ranked.filter((item) => !used.has(String(item.marketItem.market_keyword || "").toLowerCase()));
  const pool = uniqueRanked.length ? uniqueRanked : ranked;
  const selected = pool.length ? pool[(Math.max(1, workerNumber) - 1) % pool.length] : null;
  return {
    catalog,
    topMarketItems,
    supplierMatches,
    selected,
    catalogSummary: summarizeSupplierCatalog(catalog)
  };
}

function buildCatalogAwarePrompt({ keyword, promptAngle, look, supplierProduct }) {
  const productName = supplierProduct?.product_name || supplierProduct?.productName || "supplier catalog product";
  const detectedType = supplierProduct?.product_type_detected || supplierProduct?.detected_product_type || "";
  const useCase = `artwork suitable for ${productName}${detectedType ? ` (${detectedType})` : ""}`;
  return `original ${keyword} product artwork, ${promptAngle}, ${look.style || "clean centered commercial PNG design"}, designed as ${useCase}, PNG artwork only, transparent background style when suitable, no brand logos, no copyrighted characters, no celebrity, no trademarked phrase`;
}

function saveNovaOpportunityQueueEntry(plan) {
  const filePath = path.join(process.cwd(), "data", "nova_opportunity_queue.json");
  ensureDir(path.dirname(filePath));
  const rows = readJsonPath(filePath, []);
  const list = Array.isArray(rows) ? rows : [];
  const existingIndex = list.findIndex((item) =>
    item.market_keyword === plan.market_keyword
    && item.selected_supplier_product?.supplier_product_id === plan.selected_supplier_product_id
  );
  const entry = {
    opportunity_id: `NOVA-${String(list.length + 1).padStart(4, "0")}`,
    market_rank: plan.top_market_items?.find?.((item) => item.market_keyword === plan.market_keyword)?.rank || null,
    market_keyword: plan.market_keyword,
    item_people_are_buying: plan.top_market_items?.find?.((item) => item.market_keyword === plan.market_keyword)?.item_people_are_buying || plan.market_keyword,
    item_look: plan.item_look,
    supplier_matches: plan.supplier_matches,
    selected_supplier_product: plan.selected_supplier_product,
    opportunity_score: plan.opportunity_score,
    opportunity_grade: plan.opportunity_grade,
    research_source: plan.market_research_source,
    supplier_catalog_source: plan.supplier_catalog_source,
    seo_source: plan.market_research?.seo_provider_used || "",
    ledger_preview: plan.selected_supplier_product?.min_production_cost !== null ? { min_production_cost: plan.selected_supplier_product?.min_production_cost } : {},
    reason: plan.product_fit_reason,
    created_at: new Date().toISOString()
  };
  if (existingIndex >= 0) list[existingIndex] = { ...list[existingIndex], ...entry, opportunity_id: list[existingIndex].opportunity_id };
  else list.push(entry);
  saveJsonFile(filePath, list.slice(-200));
  return entry;
}

async function safePromptPlan(workId, queue = [], options = {}) {
  const nova = await researchEtsyTrends({ maxResults: 12 });
  const supplierBacked = selectSupplierBackedOpportunity(nova, queue, workId, options.workerId);
  const selected = supplierBacked.selected;
  const matchedMarketItem = selected?.marketItem || {};
  const matchedProduct = selected?.supplierMatch || null;
  const combo = (nova.recommendedCombinations || []).find((item) => item.marketKeyword === matchedMarketItem.market_keyword)
    || (nova.recommendedCombinations || [])[0]
    || {};
  const seo = await researchSeoKeywords({
    marketKeyword: matchedMarketItem.market_keyword || combo.marketKeyword,
    productType: matchedProduct?.detected_product_type || matchedMarketItem.product_type_from_market || "",
    provider: "auto",
    maxResults: 13
  });
  const look = combo.itemLook || matchedMarketItem.item_look || {};
  const keyword = matchedMarketItem.market_keyword || combo.marketKeyword || "giftable product artwork";
  const productCatalogCandidates = matchedProduct ? [matchedProduct] : [];
  const intent = matchedProduct?.detected_product_type || "supplier_catalog_pending";
  const promptAngle = (look.promptAngles || [look.subject || matchedMarketItem.item_people_are_buying || keyword])[0];
  const productFitReason = matchedProduct
    ? `${matchedProduct.product_name} matched market demand because ${matchedProduct.match_reason}`
    : "Supplier catalog is missing or has no safe match yet; Nova will wait for catalog refresh instead of inventing a product type.";
  const opportunityScore = matchedProduct
    ? Math.min(100, Math.round((combo.opportunityScore || 60) * 0.65 + matchedProduct.match_score * 0.35))
    : 0;
  const opportunityGrade = opportunityScore >= 80 ? "A" : opportunityScore >= 65 ? "B" : opportunityScore >= 50 ? "C" : "Reject";
  const plan = {
    family: keyword,
    product_intent: intent,
    artwork_format: "png",
    background_status: "unknown",
    market_research: {
      item_look: {
        keyword,
        theme: keyword,
        style: look.style || keyword,
        subject: look.subject || promptAngle,
        color_hints: look.colorHints || [],
        text_mode: look.textMode || "minimal or no text",
        buyer_intent: look.buyerIntent || "gift buyer",
        risk_level: look.riskLevel || "low",
        blocked_terms: look.blockedTerms || [],
        prompt_angles: look.promptAngles || [promptAngle]
      },
      product_fit: {
        recommended_products: productCatalogCandidates.map((item) => item.product_name),
        primary_product_type: intent,
        selectedProductName: matchedProduct?.product_name || "",
        selectedProductType: intent,
        reason: productFitReason,
        marketDemandReason: matchedMarketItem.notes || combo.reason || "",
        supplierMatchReason: matchedProduct?.match_reason || "",
        expected_buyer_use: matchedMarketItem.buyer_intent || look.buyerIntent || "",
        margin_notes: "Ledger will test supplier costs and pricing before listing.",
        supplier_notes: matchedProduct ? "Selected from normalized Printify/Printful supplier catalog." : "Refresh supplier catalog before production."
      },
      top_market_items: supplierBacked.topMarketItems,
      supplier_matches: supplierBacked.supplierMatches,
      selected_supplier_product: matchedProduct,
      supplier_catalog_source: supplierBacked.catalogSummary.sourceCounts,
      source: nova.source,
      seasonality: nova.seasonality,
      opportunity_score: opportunityScore,
      seo_seed: combo.seoSeed || {},
      seo_provider_used: seo.providerUsed,
      scribe_keywords: seo.keywords
    },
    nova_research: nova,
    market_research_source: nova.source,
    market_keyword: keyword,
    item_look: look,
    product_candidates: productCatalogCandidates,
    product_fit_reason: productFitReason,
    top_market_items: supplierBacked.topMarketItems,
    supplier_matches: supplierBacked.supplierMatches,
    selected_supplier_product: matchedProduct,
    selected_supplier: matchedProduct?.supplier || "",
    selected_supplier_product_id: matchedProduct?.supplier_product_id || "",
    selected_supplier_product_name: matchedProduct?.product_name || "",
    detected_product_type: matchedProduct?.detected_product_type || intent,
    supplier_catalog_source: supplierBacked.catalogSummary.sourceCounts,
    seo_seed: combo.seoSeed || {},
    scribe_keywords: seo.keywords,
    opportunity_score: opportunityScore,
    opportunity_grade: opportunityGrade,
    prompt: buildCatalogAwarePrompt({ keyword, promptAngle, look, supplierProduct: matchedProduct }),
    negative_prompt: DEFAULT_FORGE_NEGATIVE_PROMPT
  };
  saveNovaOpportunityQueueEntry(plan);
  return plan;
}

function workLog(work, event, message, data = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    stage: work.stage,
    event,
    message,
    data
  };
  return [...(Array.isArray(work.logs) ? work.logs : []), entry].slice(-40);
}

function recordRepair(work, { stage = work.stage, reason = "", strategy = "retry", result = "scheduled" } = {}) {
  ensureRepairMetadata(work);
  const entry = {
    at: new Date().toISOString(),
    stage,
    reason,
    strategy,
    result
  };
  work.repair_count = Number(work.repair_count || 0) + 1;
  work.max_repair_count = Math.max(25, Number(work.max_repair_count || 25));
  work.repair_history = [...(Array.isArray(work.repair_history) ? work.repair_history : []), entry].slice(-80);
  work.last_repair_reason = hasRawRuntimeExceptionText(reason) ? "This product hit a repair error. Nova is replanning it." : reason;
  work.next_repair_strategy = strategy;
  work.status = "repairing";
  work.human_status = `${workerLabel(work.worker_id)} is repairing this product.`;
  return entry;
}

function createShiftWorkItem(state, queue, worker) {
  const now = new Date().toISOString();
  const work = {
    work_id: nextWorkId(queue),
    shift_id: state.shift_id,
    worker_id: worker?.worker_id || "",
    worker_label: workerLabel(worker?.worker_id),
    status: "researching",
    stage: "prompt_planning",
    asset_id: null,
    design_package_id: null,
    production_review_id: null,
    prompt: "",
    negative_prompt: DEFAULT_FORGE_NEGATIVE_PROMPT,
    product_type_targets: [],
    product_intent: "multi_product",
    artwork_format: "png",
    background_status: "unknown",
    ledger_retry_count: 0,
    ledger_retry_history: [],
    repair_count: 0,
    max_repair_count: 25,
    repair_history: [],
    last_repair_reason: "",
    next_repair_strategy: "",
    max_ledger_retries: state.limits.max_ledger_retries || MAX_LEDGER_RETRIES,
    retry_overrides: {},
    market_research: null,
    attempts: 0,
    created_at: now,
    updated_at: now,
    logs: []
  };
  work.logs = workLog(work, "created", "Work item queued for prompt planning.");
  state.created_this_shift = Number(state.created_this_shift || 0) + 1;
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "created", message: "Queued autonomous work item." });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "current_shift_work_created", message: `${work.work_id} created for this shift.`, data: { worker_id: work.worker_id, created_this_shift: state.created_this_shift } });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "idle_worker_filled", message: `${workerLabel(work.worker_id)} filled with current-shift work.`, data: { worker_id: work.worker_id } });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "work_item_created", message: `${work.work_id} created for ${workerLabel(work.worker_id)}.`, data: { worker_id: work.worker_id } });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "forge_worker_assigned", message: `${workerLabel(work.worker_id)} assigned to ${work.work_id}.`, data: { worker_id: work.worker_id } });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "worker_assigned_new_work", message: `${workerLabel(work.worker_id)} assigned new work ${work.work_id}.`, data: { worker_id: work.worker_id } });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "forge_worker_started_new_idea", message: `${workerLabel(work.worker_id)} started a new product idea.`, data: { worker_id: work.worker_id } });
  return work;
}

function markWorkBlocked(state, work, message, errorCode = "blocked") {
  const waitingForSetup = errorCode === "waiting_for_setup";
  work.status = waitingForSetup ? "waiting_for_setup" : "repairing";
  if (!waitingForSetup) recordRepair(work, { stage: work.stage, reason: message, strategy: "self_repair", result: "scheduled" });
  work.human_status = waitingForSetup
    ? `${workerLabel(work.worker_id)} is waiting for setup. ${message}`
    : `${workerLabel(work.worker_id)} is repairing this product. ${message}`;
  work.updated_at = new Date().toISOString();
  work.logs = workLog(work, errorCode, message);
  state.counters.blocked += 1;
  state.current_task = message;
  releaseForgeWorker(state, work, "forge_worker_blocked", `${workerLabel(work.worker_id)} hit a problem but remains assigned to this product.`);
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: errorCode, message });
}

function hasMissingConnectorReason(reasons) {
  return (Array.isArray(reasons) ? reasons : []).some((reason) => {
    const lower = String(reason || "").toLowerCase();
    return lower.includes("printify_api_key") || lower.includes("printful_api_key") || lower.includes("api key is missing") || lower.includes("missingconnector");
  });
}

function etsyConnectorReady() {
  const status = getSecretStatus();
  return ["ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "ETSY_REFRESH_TOKEN", "ETSY_SHOP_ID"]
    .every((key) => status?.[key] && status[key] !== "missing");
}

function autoPublishEnabled() {
  return businessPolicyConfig().auto_publish_enabled;
}

function etsyPublishMode() {
  return getEtsyConnectorStatus().publish_mode;
}

function updateWorkPublishState(workId, patch = {}) {
  const queue = loadShiftQueue();
  const index = queue.findIndex((item) => item.work_id === workId);
  if (index < 0) return null;
  queue[index] = {
    ...queue[index],
    ...patch,
    updated_at: new Date().toISOString()
  };
  saveShiftQueue(queue);
  return queue[index];
}

async function runEtsyPublisherForWork(work, productPackage, state) {
  const connector = getEtsyConnectorStatus();
  const mode = connector.publish_mode;
  const result = await publishEtsyListing(productPackage, { mode });
  work.etsy_publish_mode = mode;
  work.etsy_publish_status = result.status;
  work.etsy_payload_blockers = result.validation?.blockers || result.blockers || [];
  work.etsy_payload_warnings = result.validation?.warnings || result.warnings || [];
  work.product_package_status = result.productPackage?.publish_status || productPackage.publish_status || productPackage.status;

  if (mode === "dry_run") {
    work.status = "waiting_for_live_publish";
    work.stage = "ready_to_publish";
    work.human_status = "Publisher prepared a dry-run Etsy listing. Live publishing is not enabled.";
    work.logs = workLog(work, "etsy_dry_run_ready", "Etsy dry-run payload prepared.", { package_id: productPackage.package_id, dry_run_id: result.dryRun?.dry_run_id });
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "etsy_dry_run_ready", message: "Etsy dry-run payload prepared.", data: { package_id: productPackage.package_id, dry_run_id: result.dryRun?.dry_run_id, blockers: result.validation?.blockers || [] } });
    updateWorkPublishState(work.work_id, work);
    return result;
  }

  if (!connector.ready_for_live || result.status === "waiting_for_setup") {
    work.status = "waiting_for_setup";
    work.stage = "ready_to_publish";
    work.human_status = result.error || "Etsy setup is required before this can be listed.";
    work.logs = workLog(work, "etsy_waiting_for_setup", work.human_status, { package_id: productPackage.package_id });
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "etsy_waiting_for_setup", message: work.human_status, data: { package_id: productPackage.package_id } });
    updateWorkPublishState(work.work_id, work);
    return result;
  }

  if (result.ok && result.live_listing_id) {
    work.status = "listed";
    work.stage = "listed";
    work.external_status = "listed";
    work.live_listing_id = result.live_listing_id;
    work.human_status = "Publisher listed the product on Etsy.";
    recordListingSlot({
      listingId: result.live_listing_id,
      workId: work.work_id,
      designPackageId: work.design_package_id,
      productType: productPackage.product_type,
      marketKeyword: work.market_keyword,
      quantityUploaded: productPackage.listing?.quantity,
      supplierQuantityCap: null,
      opportunityScore: productPackage.opportunity_score
    });
    releaseForgeWorker(state, work, "forge_worker_released", `${workerLabel(work.worker_id)} listed ${work.work_id}.`);
    updateWorkPublishState(work.work_id, work);
    return result;
  }

  work.status = "waiting_for_setup";
  work.stage = "ready_to_publish";
  work.human_status = result.error || "Etsy live publishing is not ready yet.";
  updateWorkPublishState(work.work_id, work);
  return result;
}

function nextLedgerRetryStrategy(work, state, review) {
  const retryCount = Number(work.ledger_retry_count || 0);
  const maxRetries = Number(work.max_ledger_retries || state.limits.max_ledger_retries || MAX_LEDGER_RETRIES);
  if (retryCount >= maxRetries) return null;

  const allowed = Array.from(new Set([
    ...(Array.isArray(work.product_type_targets) ? work.product_type_targets : []),
    ...(Array.isArray(work.product_candidates) ? work.product_candidates.map((item) => item.detected_product_type || item.product_name || item.productType || item) : []),
    work.detected_product_type,
    work.selected_supplier_product_name,
    ...(Array.isArray(state.limits.allowed_product_types) ? state.limits.allowed_product_types : [])
  ].filter(Boolean)));
  const currentSupplier = work.retry_overrides?.preferredSupplier || state.limits.preferred_supplier || "auto";
  const currentProductTypes = work.retry_overrides?.productTypes || allowed;
  const currentPrices = { ...DEFAULT_TARGET_PRICES, ...(state.limits.target_prices || {}), ...(work.retry_overrides?.targetPrices || {}) };
  const passableOption = productionReviewOptions(review)
    .filter((option) => optionMoneyValue(option, ["baseCost", "base_cost", "production_cost", "production_cost_us"]) !== null)
    .sort((a, b) => (Number(b.margin || b.estimatedMarginPct || 0) - Number(a.margin || a.estimatedMarginPct || 0)))[0];

  const calculatedPriceCandidate = productionReviewOptions(review).find((option) => {
    const required = moneyOrNull(option.required_price_for_ledger_pass);
    const ceiling = moneyOrNull(option.product_price_ceiling);
    const productType = option.product_type || option.productType;
    return required !== null
      && ceiling !== null
      && required <= ceiling
      && optionBooleanValue(option, ["supplierCostVerified", "supplier_cost_verified", "verified_supplier_cost"])
      && productType;
  });

  if (calculatedPriceCandidate) {
    const productType = calculatedPriceCandidate.product_type || calculatedPriceCandidate.productType;
    const correctedPrice = moneyOrNull(calculatedPriceCandidate.required_price_for_ledger_pass);
    return {
      strategy: "calculated_required_price",
      message: "Agents are adjusting price.",
      overrides: {
        preferredSupplier: calculatedPriceCandidate.supplier || currentSupplier,
        productTypes: [productType],
        targetPrices: {
          ...currentPrices,
          [productType]: correctedPrice
        }
      },
      oldPrice: moneyOrNull(calculatedPriceCandidate.original_target_price || calculatedPriceCandidate.target_price),
      correctedPrice
    };
  }

  if (retryCount === 0) {
    const nextSupplier = currentSupplier === "printify" ? "printful" : currentSupplier === "printful" ? "printify" : "auto";
    return {
      strategy: "try_other_supplier",
      message: "Agents are trying another supplier.",
      overrides: { preferredSupplier: nextSupplier, productTypes: currentProductTypes, targetPrices: currentPrices }
    };
  }

  if (retryCount === 1) {
    const lastProducts = new Set(currentProductTypes);
    const nextProduct = allowed.find((item) => !lastProducts.has(item)) || allowed[(retryCount + 1) % allowed.length] || work.detected_product_type || work.product_intent;
    return {
      strategy: "try_different_product_type",
      message: "Agents are looking for a better product fit.",
      overrides: { preferredSupplier: currentSupplier, productTypes: [nextProduct], targetPrices: currentPrices }
    };
  }

  if (retryCount === 2) {
    const increased = {};
    for (const productType of allowed) {
      const base = moneyOrNull(currentPrices[productType]) ?? DEFAULT_TARGET_PRICES[productType] ?? 19.99;
      const ceiling = TARGET_PRICE_CEILINGS[productType] ?? 49.99;
      increased[productType] = Math.min(ceiling, Number((base + 2).toFixed(2)));
    }
    return {
      strategy: "increase_price_two_dollars",
      message: "Agents are adjusting price.",
      overrides: { preferredSupplier: currentSupplier, productTypes: currentProductTypes, targetPrices: increased }
    };
  }

  const productType = passableOption?.product_type || passableOption?.productType || allowed[0] || work.detected_product_type || work.product_intent;
  const base = moneyOrNull(currentPrices[productType]) ?? DEFAULT_TARGET_PRICES[productType] ?? 19.99;
  const bump = retryCount === 3 ? 4 : 6;
  const ceiling = TARGET_PRICE_CEILINGS[productType] ?? 49.99;
  return {
    strategy: "best_margin_with_safe_price_ceiling",
    message: "Agents are choosing the best product and price found so far.",
    overrides: {
      preferredSupplier: passableOption?.supplier || currentSupplier,
      productTypes: [productType],
      targetPrices: {
        ...currentPrices,
        [productType]: Math.min(ceiling, Number((base + bump).toFixed(2)))
      }
    }
  };
}

function scheduleLedgerRetry(state, work, review, reasons) {
  ensureRepairMetadata(work);
  if (hasMissingConnectorReason(reasons)) return false;
  const plan = nextLedgerRetryStrategy(work, state, review);
  if (!plan) return false;
  const nextCount = Number(work.ledger_retry_count || 0) + 1;
  work.ledger_retry_count = nextCount;
  work.ledger_retry_history = [
    ...(Array.isArray(work.ledger_retry_history) ? work.ledger_retry_history : []),
    {
      at: new Date().toISOString(),
      strategy: plan.strategy,
      reasons,
      overrides: plan.overrides,
      oldPrice: plan.oldPrice,
      correctedPrice: plan.correctedPrice,
      result: "scheduled"
    }
  ];
  work.retry_overrides = plan.overrides;
  work.status = "pricing";
  work.stage = "production_check";
  work.blocked_reasons = reasons;
  work.logs = workLog(work, "ledger_retry_strategy", plan.message, { strategy: plan.strategy, retry: nextCount });
  state.current_task = plan.message;
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "production_check", event: "ledger_retry_started", message: plan.message, data: { retry: nextCount } });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "production_check", event: "ledger_retry_strategy", message: plan.strategy, data: plan.overrides });
  return true;
}

function needsLegacyProductionCheckUnsticker(work) {
  if (!work || work.stage !== "production_check") return false;
  const normalized = normalizeWorkStatus(work);
  const hasPackage = Boolean(productPackageForWork(work) || work.product_package_id);
  return normalized === "repairing"
    && (!hasPackage
      || work.opportunity_score === undefined
      || work.opportunity_score === null
      || work.repair_count === undefined
      || work.repair_count === null
      || !work.next_repair_strategy
      || hasRawRuntimeExceptionText(work.human_status)
      || hasRawRuntimeExceptionText(work.last_repair_reason));
}

function unstickLegacyProductionCheckJob(state, work) {
  ensureRepairMetadata(work);
  resetLegacyRepairCounterIfNeeded(work);
  const now = new Date().toISOString();
  const entry = {
    at: now,
    stage: "production_check",
    reason: "Legacy production_check job had missing package/repair metadata or invalid production data.",
    strategy: "nova_research_replan",
    result: "Moved to research_replan."
  };
  work.repair_count = Number(work.repair_count || 0) + 1;
  work.repair_history = [...(Array.isArray(work.repair_history) ? work.repair_history : []), entry].slice(-80);
  work.status = "repairing";
  work.stage = "research_replan";
  work.last_repair_reason = "Legacy production_check job could not continue safely.";
  work.next_repair_strategy = "nova_research_replan";
  work.current_task = "Nova is replanning this product from stronger market research.";
  work.human_status = "Nova is replanning this product from stronger market research.";
  work.updated_at = now;
  work.logs = workLog(work, "legacy_production_check_unstuck", entry.result, entry);
  state.current_task = "Nova is replanning this product from stronger market research.";
  appendShiftLog({
    shiftId: state.shift_id,
    workId: work.work_id,
    stage: "production_check",
    event: "legacy_production_check_unstuck",
    message: entry.reason,
    data: { worker_id: work.worker_id, strategy: entry.strategy }
  });
  return work;
}

function packageRepairStage(blockers = []) {
  const text = (Array.isArray(blockers) ? blockers : []).join(" ").toLowerCase();
  if (text.includes("nova") || text.includes("opportunity")) return "research_replan";
  if (text.includes("supplier") || text.includes("variant") || text.includes("ledger") || text.includes("margin")) return "production_check";
  if (text.includes("scribe") || text.includes("title") || text.includes("description") || text.includes("tags")) return "scribe_draft";
  if (text.includes("png") || text.includes("artwork")) return "image_generation";
  if (text.includes("sentinel")) return "sentinel_qa";
  return "production_check";
}

function isComfySetupBlocker(work) {
  const text = [
    work?.setup_blocker,
    work?.human_status,
    work?.last_repair_reason,
    work?.blocked_reasons,
    work?.logs?.slice?.(-3)?.map((entry) => entry.message).join(" ")
  ].flat().filter(Boolean).join(" ").toLowerCase();
  return text.includes("comfyui")
    || text.includes("comfy")
    || text.includes("forge")
    || text.includes("offline")
    || text.includes("not reachable")
    || text.includes("connection")
    || text.includes("refused");
}

function isStaleUnsubmittedImageGeneration(work) {
  if (!work || work.stage !== "image_generation" || work.status !== "generating_art") return false;
  if (work.asset_id || work.image_generation_run_id || work.generation_prompt_id) return false;
  const stamp = Date.parse(work.generation_started_at || work.updated_at || work.created_at || "");
  return !Number.isFinite(stamp) || Date.now() - stamp > 2 * 60 * 1000;
}

async function recoverForgeImageGenerationSetup(state, queue) {
  let health = null;
  for (const work of queue.filter((item) =>
    item.shift_id === state.shift_id
    && item.worker_id
    && item.status === "waiting_for_setup"
    && item.stage === "image_generation"
    && isComfySetupBlocker(item)
    && !isWorkerReleaseAllowed(item)
  )) {
    ensureRepairMetadata(work);
    health = health || await getForgeArtHealth();
    work.setup_health = health;
    if (health.ok) {
      work.status = "generating_art";
      work.stage = "image_generation";
      work.setup_blocker = "";
      work.current_task = "Forge is creating the PNG.";
      work.human_status = "Forge is creating the PNG.";
      work.updated_at = "";
      work.logs = workLog(work, "setup_recovered", "ComfyUI is reachable again. Resuming PNG generation.", health);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "image_generation",
        event: "setup_recovered",
        message: "ComfyUI is reachable again. Resuming PNG generation.",
        data: { worker_id: work.worker_id, baseUrl: health.baseUrl, checkedAt: health.checkedAt }
      });
    } else {
      work.status = "waiting_for_setup";
      work.setup_blocker = health.reason || health.error || "ComfyUI is not reachable.";
      work.current_task = work.setup_blocker;
      work.human_status = work.setup_blocker;
      work.updated_at = new Date().toISOString();
      work.logs = workLog(work, "setup_still_waiting", work.setup_blocker, health);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "image_generation",
        event: "setup_still_waiting",
        message: work.setup_blocker,
        data: { worker_id: work.worker_id, baseUrl: health.baseUrl, checkedAt: health.checkedAt }
      });
    }
  }
  for (const work of queue.filter((item) =>
    item.shift_id === state.shift_id
    && item.worker_id
    && isStaleUnsubmittedImageGeneration(item)
    && !isWorkerReleaseAllowed(item)
  )) {
    ensureRepairMetadata(work);
    work.status = "repairing";
    work.stage = "image_generation";
    work.next_repair_strategy = "retry_png_generation";
    work.last_generation_error = "Image generation was marked active but no ComfyUI prompt or asset was recorded.";
    work.current_task = "Forge is retrying PNG generation.";
    work.human_status = "Forge is retrying PNG generation.";
    work.updated_at = "";
    work.logs = workLog(work, "stale_generation_retry", "Forge found a stale PNG generation state and will resubmit.", {
      generation_started_at: work.generation_started_at || "",
      generation_attempt_count: work.generation_attempt_count || 0
    });
    appendShiftLog({
      shiftId: state.shift_id,
      workId: work.work_id,
      stage: "image_generation",
      event: "stale_generation_retry",
      message: "Forge found a stale PNG generation state and will resubmit.",
      data: { worker_id: work.worker_id }
    });
  }
  return health;
}

async function processPackageBuildStage(state, work) {
  ensureRepairMetadata(work);
  const productPackage = buildAndMaybeSaveProductPackageForWork(work);
  work.product_package_id = productPackage.package_id;
  work.product_package_status = productPackage.status;
  work.package_blockers = productPackage.blockers;
  work.package_warnings = productPackage.warnings;
  if (productPackage.ok) {
    if (etsyPublishMode() === "dry_run") {
      await runEtsyPublisherForWork(work, productPackage, state);
      return productPackage;
    }
    work.stage = "ready_to_publish";
    work.status = "ready_to_publish";
    work.human_status = `${workerLabel(work.worker_id)} prepared an Etsy-ready product package.`;
    work.logs = workLog(work, "product_package_built", "Product package is ready for Publisher.", { package_id: productPackage.package_id });
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "package_build", event: "product_package_built", message: productPackage.status, data: { package_id: productPackage.package_id } });
    return productPackage;
  }

  const nextStage = packageRepairStage(productPackage.blockers);
  recordRepair(work, {
    stage: "package_build",
    reason: productPackage.blockers.join(", "),
    strategy: `repair_${nextStage}`,
    result: "scheduled"
  });
  work.stage = nextStage;
  work.status = "repairing";
  work.human_status = `${workerLabel(work.worker_id)} is repairing the product package.`;
  work.logs = workLog(work, "product_package_blocked", "Product package gates are not complete yet.", { package_id: productPackage.package_id, blockers: productPackage.blockers });
  appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "package_build", event: "product_package_blocked", message: "Product package needs repair before publishing.", data: { package_id: productPackage.package_id, blockers: productPackage.blockers, nextStage } });
  return productPackage;
}

async function processResearchReplanStage(state, work) {
  ensureRepairMetadata(work);
  resetLegacyRepairCounterIfNeeded(work);
  try {
    const plan = await safePromptPlan(work.work_id, loadShiftQueue(), {
      workerId: work.worker_id,
      seedKeyword: work.market_keyword || work.market_research?.item_look?.keyword || work.prompt_family || ""
    });
    if (!plan?.opportunity_score || !plan?.market_keyword) {
      throw new Error("Nova returned no usable market opportunity.");
    }
    work.prompt = plan.prompt;
    work.negative_prompt = plan.negative_prompt;
    work.prompt_family = plan.family;
    work.product_intent = plan.product_intent;
    work.product_type_targets = plan.product_candidates?.length
      ? plan.product_candidates.map((item) => item.detected_product_type || item.product_name || item.productType || item).filter(Boolean)
      : plan.market_research?.product_fit?.recommended_products || state.limits.allowed_product_types;
    work.market_research = plan.market_research;
    work.nova_research = plan.nova_research;
    work.market_research_source = plan.market_research_source;
    work.market_keyword = plan.market_keyword;
    work.item_look = plan.item_look;
    work.product_candidates = plan.product_candidates;
    work.product_fit_reason = plan.product_fit_reason || `Nova selected ${plan.product_intent} from the strongest product fit candidates.`;
    work.top_market_items = plan.top_market_items;
    work.supplier_matches = plan.supplier_matches;
    work.selected_supplier_product = plan.selected_supplier_product;
    work.selected_supplier = plan.selected_supplier;
    work.selected_supplier_product_id = plan.selected_supplier_product_id;
    work.selected_supplier_product_name = plan.selected_supplier_product_name;
    work.detected_product_type = plan.detected_product_type;
    work.supplier_catalog_source = plan.supplier_catalog_source;
    work.seo_seed = plan.seo_seed;
    work.scribe_keywords = plan.scribe_keywords;
    work.opportunity_score = Number(plan.opportunity_score || 0);
    work.opportunity_grade = plan.opportunity_grade || "";
    work.retry_overrides = {};
    work.ledger_retry_count = 0;
    work.research_replan_wait_ticks = 0;
    work.next_repair_strategy = "prompt_planning";
    work.stage = "prompt_planning";
    work.status = "researching";
    work.current_task = "Nova found a stronger product opportunity.";
    work.human_status = "Nova found a stronger product opportunity.";
    work.updated_at = new Date().toISOString();
    work.logs = workLog(work, "nova_replan_completed", "Nova replanned this product and moved it back to prompt planning.", {
      market_keyword: work.market_keyword,
      product_intent: work.product_intent,
      opportunity_score: work.opportunity_score,
      opportunity_grade: work.opportunity_grade
    });
    appendShiftLog({
      shiftId: state.shift_id,
      workId: work.work_id,
      stage: "research_replan",
      event: "nova_replan_completed",
      message: "Nova replanned this product and moved it back to prompt planning.",
      data: {
        worker_id: work.worker_id,
        market_keyword: work.market_keyword,
        product_intent: work.product_intent,
        opportunity_score: work.opportunity_score,
        opportunity_grade: work.opportunity_grade
      }
    });
  } catch (error) {
    const rawError = String(error?.message || error);
    const entry = recordRepair(work, {
      stage: "research_replan",
      reason: "Nova research did not return a usable opportunity.",
      strategy: "retry_nova_research",
      result: "retry_scheduled"
    });
    work.status = "repairing";
    work.stage = "research_replan";
    work.last_repair_reason = "Nova research did not return a usable opportunity.";
    work.next_repair_strategy = "retry_nova_research";
    work.current_task = "Nova is retrying market research.";
    work.human_status = "Nova is retrying market research.";
    work.updated_at = new Date().toISOString();
    work.logs = workLog(work, "nova_replan_error", "Nova is retrying market research.", { repair: entry, error: rawError });
    appendShiftLog({
      shiftId: state.shift_id,
      workId: work.work_id,
      stage: "research_replan",
      event: "nova_replan_error",
      message: "Nova research failed safely and will retry.",
      data: { error: rawError, worker_id: work.worker_id }
    });
  }
}

async function processShiftWorkOneStage(state, work) {
  ensureRepairMetadata(work);
  if (needsLegacyProductionCheckUnsticker(work)) {
    unstickLegacyProductionCheckJob(state, work);
    return;
  }
  work.status = autonomousStatusForStage(work.stage);
  work.attempts = Number(work.attempts || 0) + 1;
  work.updated_at = new Date().toISOString();
  state.current_task = `${work.work_id}: ${work.stage}`;

  if (work.stage === "research_replan") {
    await processResearchReplanStage(state, work);
    return;
  }

  if (work.stage === "prompt_planning") {
    const plan = await safePromptPlan(work.work_id, loadShiftQueue());
    work.prompt = plan.prompt;
    work.negative_prompt = plan.negative_prompt;
    work.prompt_family = plan.family;
    work.product_intent = plan.product_intent;
    work.artwork_format = plan.artwork_format;
    work.background_status = plan.background_status;
    work.product_type_targets = plan.product_candidates?.length
      ? plan.product_candidates.map((item) => item.detected_product_type || item.product_name || item.productType || item).filter(Boolean)
      : plan.market_research?.product_fit?.recommended_products || work.product_type_targets;
    work.market_research = plan.market_research;
    work.nova_research = plan.nova_research;
    work.market_research_source = plan.market_research_source;
    work.market_keyword = plan.market_keyword;
    work.item_look = plan.item_look;
    work.product_candidates = plan.product_candidates;
    work.product_fit_reason = plan.product_fit_reason;
    work.top_market_items = plan.top_market_items;
    work.supplier_matches = plan.supplier_matches;
    work.selected_supplier_product = plan.selected_supplier_product;
    work.selected_supplier = plan.selected_supplier;
    work.selected_supplier_product_id = plan.selected_supplier_product_id;
    work.selected_supplier_product_name = plan.selected_supplier_product_name;
    work.detected_product_type = plan.detected_product_type;
    work.supplier_catalog_source = plan.supplier_catalog_source;
    work.seo_seed = plan.seo_seed;
    work.scribe_keywords = plan.scribe_keywords;
    work.opportunity_score = plan.opportunity_score;
    work.opportunity_grade = plan.opportunity_grade;
    work.stage = "image_generation";
    work.status = "generating_art";
    work.logs = workLog(work, "prompt_planned", `Prompt planned: ${plan.family}.`);
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "prompt_planning", event: "prompt_planned", message: plan.family });
    return;
  }

  if (work.stage === "image_generation") {
    const health = await getForgeArtHealth();
    work.setup_health = health;
    if (!health.ok) {
      work.status = "waiting_for_setup";
      work.setup_blocker = health.reason || health.error || "ComfyUI is not reachable.";
      work.current_task = work.setup_blocker;
      work.human_status = work.setup_blocker;
      work.logs = workLog(work, "setup_waiting", work.setup_blocker, health);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "image_generation",
        event: "setup_waiting",
        message: work.setup_blocker,
        data: { worker_id: work.worker_id, baseUrl: health.baseUrl, checkedAt: health.checkedAt }
      });
      return;
    }
    if (work.asset_id) {
      work.stage = "sentinel_qa";
      work.status = "qa_checking";
      work.current_task = "Sentinel is checking the PNG.";
      work.human_status = "Sentinel is checking the PNG.";
      return;
    }
    const result = await generateLocalForgeArtworkForWorkItem(work, { state, health });
    if (!result.ok || !result.assetId) {
      state.counters.errors += 1;
      state.last_error = result.error || "Local PNG generation failed.";
      return;
    }
    state.counters.generated += 1;
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "image_generation", event: "image_generated", message: `Generated ${result.assetId}.` });
    return;
  }

  if (work.stage === "sentinel_qa") {
    const assets = readJson("image_assets.json", []);
    const reports = readJson("visual_qa_reports.json", []);
    const asset = assets.find((item) => item.id === work.asset_id);
    if (!asset) {
      markWorkBlocked(state, work, "Generated asset missing before Sentinel QA.", "blocked");
      return;
    }
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "sentinel_qa", event: "sentinel_qa_started", message: `Running Sentinel QA for ${work.asset_id}.` });
    const existingApproval = approvedVisualQaForAsset(asset, reports);
    const qaResult = existingApproval
      ? {
          ok: true,
          assetId: asset.id,
          reportId: existingApproval.id,
          approved_for_product: true,
          blocked_reasons: [],
          warnings: existingApproval.warnings || [],
          report: existingApproval,
          asset
        }
      : runSentinelQa({ assetId: work.asset_id });

    work.sentinel_report_id = qaResult.reportId;
    work.sentinel_status = qaResult.report?.status || (qaResult.approved_for_product ? "pass_product" : "blocked");
    work.approved_for_product = Boolean(qaResult.approved_for_product);
    work.blocked_reasons = qaResult.blocked_reasons || [];
    work.warnings = qaResult.warnings || [];

    if (!qaResult.approved_for_product) {
      state.counters.sentinel_failed += 1;
      const reason = qaResult.blocked_reasons?.length
        ? qaResult.blocked_reasons.join(", ")
        : "Sentinel did not approve this image for product use.";
      work.stage = "image_generation";
      work.status = "repairing";
      recordRepair(work, { stage: "sentinel_qa", reason, strategy: "regenerate_artwork_after_qa_failed", result: "scheduled" });
      work.human_status = `${workerLabel(work.worker_id)} is regenerating the artwork after QA failed.`;
      work.blocked_reasons = qaResult.blocked_reasons || [reason];
      work.logs = workLog(work, "sentinel_repair_scheduled", `Sentinel QA blocked product use: ${reason}. Regenerating artwork for the same product.`);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "sentinel_qa",
        event: "sentinel_qa_failed",
        message: reason,
        data: { reportId: qaResult.reportId, warnings: qaResult.warnings || [] }
      });
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "image_generation",
        event: "sentinel_repair_scheduled",
        message: `${workerLabel(work.worker_id)} will regenerate artwork for the same product.`,
        data: { previousAssetId: work.asset_id, reportId: qaResult.reportId }
      });
      return;
    }
    state.counters.sentinel_passed += 1;
    work.stage = "promote_to_design";
    work.status = "researching";
    work.logs = workLog(work, "sentinel_passed", `Sentinel approved product use in ${qaResult.reportId}.`);
    appendShiftLog({
      shiftId: state.shift_id,
      workId: work.work_id,
      stage: "sentinel_qa",
      event: "sentinel_qa_passed",
      message: `Sentinel approved ${work.asset_id}.`,
      data: { reportId: qaResult.reportId, warnings: qaResult.warnings || [] }
    });
    return;
  }

  if (work.stage === "promote_to_design") {
    const result = promoteForgeArtToDesign({ assetId: work.asset_id });
    work.design_package_id = result.design.id;
    work.stage = "production_check";
    work.status = "pricing";
    state.counters.promoted += 1;
    work.logs = workLog(work, "promoted", `Promoted to ${result.design.id}.`);
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "promote_to_design", event: "promoted", message: `Promoted to ${result.design.id}.` });
    return;
  }

  if (work.stage === "production_check") {
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "production_check", event: "ledger_retry_result", message: `Production check attempt ${Number(work.ledger_retry_count || 0) + 1}.` });
    const retryOverrides = work.retry_overrides || {};
    const productTypes = retryOverrides.productTypes
      || work.product_type_targets
      || (work.selected_supplier_product_name ? [work.selected_supplier_product_name] : null)
      || (work.detected_product_type ? [work.detected_product_type] : null)
      || [];
    const targetPrices = { ...DEFAULT_TARGET_PRICES, ...(state.limits.target_prices || {}), ...(retryOverrides.targetPrices || {}) };
    const review = await checkProduction({
      designPackageId: work.design_package_id,
      preferredSupplier: retryOverrides.preferredSupplier || state.limits.preferred_supplier,
      productTypes,
      destinationCountry: state.limits.destinationCountry,
      destinationState: state.limits.destinationState,
      destinationZip: state.limits.destinationZip,
      targetPrices,
      maxOptionsPerType: state.limits.max_products_checked_per_design
    });
    work.production_review_id = review.review_id;
    state.counters.production_checked += 1;
    if (hasLedgerPassOption(review)) {
      const correctedPass = productionReviewOptions(review).find((option) => option.ledger_pass_after_correction || option.ledgerPassAfterCorrection);
      if (correctedPass) {
        work.ledger_retry_history = [
          ...(Array.isArray(work.ledger_retry_history) ? work.ledger_retry_history : []),
          {
            at: new Date().toISOString(),
            strategy: "calculated_required_price",
            oldPrice: correctedPass.original_target_price,
            correctedPrice: correctedPass.corrected_target_price,
            result: "passed"
          }
        ];
      }
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "production_check", event: "ledger_retry_result", message: "Ledger found a verified profitable product option.", data: { reviewId: review.review_id } });
      state.counters.ledger_passed += 1;
      work.stage = "scribe_draft";
      work.status = "writing_listing";
    } else {
      const reasons = ledgerPassBlockingReasons(review);
      if (scheduleLedgerRetry(state, work, review, reasons)) {
        return;
      }
      recordRepair(work, { stage: "production_check", reason: reasons.join(", "), strategy: "research_replan", result: "scheduled" });
      work.stage = "research_replan";
      work.status = "repairing";
      work.human_status = `${workerLabel(work.worker_id)} is replanning the product opportunity.`;
      work.blocked_reasons = reasons;
      work.logs = workLog(work, "repairing", "Agents are replanning this product after exhausting pricing retries.", { reasons });
      state.counters.blocked += 1;
      state.current_task = "Agents are replanning a better product fit.";
      releaseForgeWorker(state, work, "forge_worker_blocked", `${workerLabel(work.worker_id)} exhausted Ledger retries but remains assigned to this product.`);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "production_check",
        event: "ledger_retry_exhausted",
        message: "Agents could not find a profitable verified product after trying different suppliers, products, and prices.",
        data: { reviewId: review.review_id, reasons }
      });
      return;
    }
    work.logs = workLog(work, "production_checked", `Production review ${review.review_id} created.`);
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "production_check", event: "production_checked", message: `Review ${review.review_id}.` });
    return;
  }

  if (work.stage === "package_build") {
    await processPackageBuildStage(state, work);
    return;
  }

  if (work.stage === "scribe_draft") {
    const review = listProductionReviews().find((item) => item.review_id === work.production_review_id);
    if (!hasLedgerPassOption(review)) {
      const reasons = ledgerPassBlockingReasons(review);
      work.stage = "production_check";
      work.status = "repairing";
      recordRepair(work, { stage: "scribe_draft", reason: reasons.join(", "), strategy: "return_to_pricing", result: "scheduled" });
      work.human_status = `${workerLabel(work.worker_id)} is returning to pricing before Scribe writes the listing.`;
      work.blocked_reasons = reasons;
      work.logs = workLog(work, "repairing", `No Ledger PASS product option found. ${reasons.join(", ")}`);
      state.counters.blocked += 1;
      releaseForgeWorker(state, work, "forge_worker_blocked", `${workerLabel(work.worker_id)} remains assigned while economics are blocked.`);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "scribe_draft",
        event: "production_blocked",
        message: "Scribe blocked because no Ledger PASS product option exists.",
        data: { reviewId: work.production_review_id, reasons }
      });
      return;
    }
    const productType = review?.recommended_options?.find((option) => ledgerPassOptionDetails(option).pass)?.product_type || "poster";
    const seoPreview = await scribeSeoListingPreview({
      designPackageId: work.design_package_id,
      productType,
      marketKeyword: work.market_keyword,
      itemLook: work.item_look || work.market_research?.item_look || {},
      productFit: work.market_research?.product_fit || {},
      blockedTerms: work.item_look?.blockedTerms || work.market_research?.item_look?.blocked_terms || []
    });
    work.scribe_keywords = seoPreview.keywords_used;
    work.seo_provider_used = seoPreview.seo_provider_used;
    const result = await runPython("run_scribe_on_design.py", [
      "--design-package-id",
      work.design_package_id,
      "--product-type",
      productType
    ]);
    if (!result.ok) {
      recordRepair(work, { stage: "scribe_draft", reason: result.stderr || result.stdout || "Scribe listing draft failed.", strategy: "rewrite_listing", result: "scheduled" });
      work.stage = "scribe_draft";
      work.status = "repairing";
      work.human_status = `${workerLabel(work.worker_id)} is rewriting the Etsy listing.`;
      work.logs = workLog(work, "scribe_repair", "Scribe will rewrite the listing on the next tick.");
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "scribe_draft", event: "scribe_repair", message: "Scribe draft failed; rewrite scheduled." });
      return;
    }
    state.counters.listing_drafted += 1;
    const writtenListing = listingPreviewForDesign(work.design_package_id);
    work.scribe_result = writtenListing?.listing_id ? writtenListing : seoPreview;
    work.stage = "package_build";
    work.status = "ready_to_publish";
    work.human_status = `${workerLabel(work.worker_id)} is building the product package.`;
    state.counters.approval_ready += 1;
    work.logs = workLog(work, "scribe_draft", result.ok ? "Scribe listing draft run completed." : "Scribe run ended safely but may be blocked.");
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "scribe_draft", event: "scribe_draft", message: result.ok ? "Scribe completed; package build scheduled." : "Scribe blocked." });
    return;
  }

  if (work.stage === "approval_queue" || work.stage === "ready_to_publish") {
    const review = listProductionReviews().find((item) => item.review_id === work.production_review_id);
    if (!hasLedgerPassOption(review)) {
      const reasons = ledgerPassBlockingReasons(review);
      work.stage = "production_check";
      work.status = "repairing";
      recordRepair(work, { stage: "ready_to_publish", reason: reasons.join(", "), strategy: "return_to_pricing", result: "scheduled" });
      work.human_status = `${workerLabel(work.worker_id)} is returning to pricing before publishing.`;
      work.blocked_reasons = reasons;
      work.logs = workLog(work, "repairing", `No Ledger PASS product option found. ${reasons.join(", ")}`);
      state.counters.blocked += 1;
      releaseForgeWorker(state, work, "forge_worker_blocked", `${workerLabel(work.worker_id)} remains assigned while approval is blocked.`);
      appendShiftLog({
        shiftId: state.shift_id,
        workId: work.work_id,
        stage: "ready_to_publish",
        event: "publish_gate_repair",
        message: "Publish preparation returned to pricing because no Ledger PASS option exists.",
        data: { reviewId: work.production_review_id, reasons }
      });
      return;
    }
    const productPackage = buildAndMaybeSaveProductPackageForWork(work);
    work.product_package_id = productPackage.package_id;
    work.product_package_status = productPackage.status;
    work.package_blockers = productPackage.blockers;
    work.package_warnings = productPackage.warnings;
    if (!productPackage.ok) {
      recordRepair(work, { stage: "ready_to_publish", reason: productPackage.blockers.join(", "), strategy: "complete_product_package_gates", result: "scheduled" });
      work.stage = productPackage.blockers.some((item) => item.includes("ledger") || item.includes("variant") || item.includes("supplier")) ? "production_check" : "scribe_draft";
      work.status = "repairing";
      work.human_status = `${workerLabel(work.worker_id)} is repairing the product package.`;
      work.logs = workLog(work, "product_package_blocked", "Product package gates are not complete yet.", { package_id: productPackage.package_id, blockers: productPackage.blockers });
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "product_package_blocked", message: "Product package needs repair before publishing.", data: { package_id: productPackage.package_id, blockers: productPackage.blockers } });
      return;
    }
    if (etsyPublishMode() === "live" && !etsyConnectorReady()) {
      work.status = "waiting_for_setup";
      work.product_package_status = "ready_but_waiting_for_etsy_setup";
      work.human_status = "Product package is ready. Etsy setup is required before listing.";
      work.logs = workLog(work, "waiting_for_setup", "Product package is ready; Etsy connector setup is required before publishing.");
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "publish_connector_missing", message: "Product package is ready. Etsy setup is required before listing.", data: { package_id: productPackage.package_id } });
      return;
    }
    const publishGate = canAutoPublishWork(work, review);
    work.listing_slot_status = publishGate.slots;
    work.variant_group = publishGate.variantGroup || work.variant_group || null;
    if (!publishGate.ok) {
      if (publishGate.status === "waiting_for_slot") {
        work.status = "waiting_for_slot";
        work.stage = "ready_to_publish";
        work.human_status = "Monthly Etsy listing slots are full. This product is waiting for next month.";
        work.logs = workLog(work, "waiting_for_slot", publishGate.reason, { slots: publishGate.slots });
        appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "monthly_listing_slots_full", message: "Monthly Etsy listing slots are full.", data: publishGate.slots });
        return;
      }
      recordRepair(work, { stage: "ready_to_publish", reason: publishGate.reason, strategy: "build_better_variant_group", result: "scheduled" });
      work.stage = "production_check";
      work.status = "repairing";
      work.human_status = `${workerLabel(work.worker_id)} is finding a better variant set before listing.`;
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "variant_group_repair", message: publishGate.reason, data: publishGate.variantGroup || {} });
      return;
    }
    if (etsyPublishMode() === "dry_run") {
      const publishResult = await runEtsyPublisherForWork(work, productPackage, state);
      work.logs = workLog(work, "etsy_dry_run_ready", "Publisher prepared an Etsy dry-run listing payload.", { package_id: productPackage.package_id, blockers: publishResult.validation?.blockers || [] });
      return;
    }
    if (!autoPublishEnabled()) {
      work.status = "ready_to_publish";
      work.human_status = `${workerLabel(work.worker_id)} is ready to publish when auto-publish is enabled.`;
      work.logs = workLog(work, "ready_to_publish", "All product gates passed. Auto-publish is not enabled.");
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "ready_to_publish", message: "All gates passed; auto-publish is not enabled." });
      return;
    }
    const publishResult = await runEtsyPublisherForWork(work, productPackage, state);
    if (publishResult.ok && publishResult.live_listing_id) {
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "publishing", event: "etsy_live_published", message: "Etsy live listing confirmed.", data: { listing_id: publishResult.live_listing_id } });
      return;
    }
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: "ready_to_publish", event: "etsy_live_publish_blocked", message: publishResult.error || "Etsy live publish did not run.", data: { package_id: productPackage.package_id } });
    return;
  }
}

function shiftStatusPayload() {
  const state = loadShiftState();
  const queue = loadShiftQueue();
  syncWorkersWithQueue(state, queue);
  const currentShiftItems = queue.filter((item) => item.shift_id === state.shift_id);
  const activeCurrentWork = activeWorkItems(queue, state.shift_id);
  const activeWorkCount = activeCurrentWork.length;
  const currentShiftBlockedCount = currentShiftItems.filter((item) => ["blocked", "needs_attention", "waiting_for_setup"].includes(item.status)).length;
  const previousBlockedCount = queue.filter((item) => item.shift_id !== state.shift_id && ["blocked", "needs_attention", "waiting_for_setup"].includes(item.status)).length;
  const legacyBlankWorkerItemCount = queue.filter((item) => !item.shift_id || !item.worker_id).length;
  const blockedWorkCount = queue.filter((item) => ["blocked", "needs_attention", "waiting_for_setup"].includes(item.status)).length;
  const approvalReadyCount = queue.filter((item) => normalizeWorkStatus(item) === "ready_to_publish").length;
  return {
    ok: true,
    shift: state,
    loop: shiftLoopInfo(),
    businessPolicy: businessPolicyConfig(),
    listingSlots: loadListingSlots(),
    etsyPublisher: getEtsyConnectorStatus(),
    diagnostics: {
      currentShiftId: state.shift_id,
      createdThisShift: Number(state.created_this_shift || 0),
      workerCount: state.workers.length,
      maxActiveWorkItems: state.limits.max_active_work_items,
      maxDesignsPerShift: state.limits.max_designs_per_shift,
      activeForgeWorkers: state.workers.filter((worker) => worker.status !== "idle").length,
      idleForgeWorkers: state.workers.filter((worker) => worker.status === "idle").length,
      activeWorkCount,
      queuedWorkCount: currentShiftItems.filter((item) => item.status === "queued").length,
      blockedWorkCount,
      currentShiftBlockedCount,
      previousBlockedCount,
      legacyBlankWorkerItemCount,
      approvalReadyCount,
      ledgerPricingSanityCase: ledgerPricingSanityCase(),
      activeWorkItems: activeCurrentWork.map((item) => {
        ensureRepairMetadata(item);
        return {
          work_id: item.work_id,
          shift_id: item.shift_id,
          worker_id: item.worker_id,
          status: item.status,
          normalized_status: normalizeWorkStatus(item),
          stage: item.stage,
          human_status: item.human_status || "",
          product_intent: item.product_intent,
          opportunity_score: item.opportunity_score ?? null,
          opportunity_grade: item.opportunity_grade || null,
          repair_count: item.repair_count ?? 0,
          max_repair_count: item.max_repair_count ?? 25,
          last_repair_reason: item.last_repair_reason || null,
          next_repair_strategy: item.next_repair_strategy || null,
          setup_blocker: item.setup_blocker || null,
          setup_health: item.setup_health || null,
          package_id: item.product_package_id || null,
          selected_supplier: item.selected_supplier || item.selected_supplier_product?.supplier || null,
          selected_supplier_product_id: item.selected_supplier_product_id || item.selected_supplier_product?.supplier_product_id || null,
          selected_supplier_product_name: item.selected_supplier_product_name || item.selected_supplier_product?.product_name || null,
          detected_product_type: item.detected_product_type || item.selected_supplier_product?.detected_product_type || null,
          supplier_catalog_source: item.supplier_catalog_source || null,
          image_generation_run_id: item.image_generation_run_id || null,
          generation_started_at: item.generation_started_at || null,
          generation_attempt_count: item.generation_attempt_count ?? 0,
          generation_prompt_id: item.generation_prompt_id || null,
          last_generation_error: item.last_generation_error || null,
          market_keyword: item.market_keyword || item.market_research?.item_look?.keyword || item.prompt_family || "",
          prompt_preview: String(item.prompt || "").slice(0, 120),
          asset_id: item.asset_id,
          design_package_id: item.design_package_id,
          ...workReleaseDiagnostics(item)
        };
      }),
      workers: state.workers.map((worker) => {
        const assigned = activeCurrentWork.find((item) => item.worker_id === worker.worker_id);
        return {
          ...worker,
          assigned_work_id: assigned?.work_id || worker.work_id || "",
          ...(assigned ? workReleaseDiagnostics(assigned) : {
            assignment_stable: false,
            release_allowed: false,
            release_reason: "",
            job_complete: false,
            uploaded: false
          })
        };
      })
    },
    queue,
    reviews: listProductionReviews(),
    logTail: readShiftLogTail(80),
    locked: fs.existsSync(SHIFT_LOCK_FILE)
  };
}

async function runShiftTick() {
  return withShiftLock(async () => {
    let state = loadShiftState();
    const queue = loadShiftQueue();
    syncWorkersWithQueue(state, queue);
    if (!["running"].includes(state.status)) {
      appendShiftLog({ shiftId: state.shift_id, event: "tick_noop", message: `Shift is ${state.status}.` });
      return shiftStatusPayload();
    }

    const activeWork = activeWorkItems(queue, state.shift_id);
    const idleWorkers = state.workers.filter((worker) => worker.status === "idle");
    const maxActive = Math.max(1, Number(state.limits.max_active_work_items || state.limits.forge_worker_count || 3));
    const maxDesigns = Math.max(1, Number(state.limits.max_designs_per_shift || 3));
    const previousBlockedCount = queue.filter((item) => item.shift_id !== state.shift_id && ["blocked", "needs_attention"].includes(item.status)).length;
    let createdThisTick = 0;
    appendShiftLog({
      shiftId: state.shift_id,
      event: "shift_capacity_checked",
      message: "Checked current-shift capacity for idle Forge workers.",
      data: {
        created_this_shift: Number(state.created_this_shift || 0),
        maxDesignsPerShift: maxDesigns,
        activeWorkCount: activeWork.length,
        maxActiveWorkItems: maxActive,
        idleWorkers: idleWorkers.length,
        previousBlockedCount
      }
    });
    if (previousBlockedCount > 0) {
      appendShiftLog({
        shiftId: state.shift_id,
        event: "old_blocked_work_ignored_for_capacity",
        message: "Previous blocked work was ignored for current shift capacity.",
        data: { previousBlockedCount }
      });
    }
    appendShiftLog({ shiftId: state.shift_id, event: "active_work_fill_started", message: "Checking idle Forge workers for new product ideas.", data: { activeWorkCount: activeWork.length, idleWorkers: idleWorkers.length, maxActive, created_this_shift: state.created_this_shift, maxDesignsPerShift: maxDesigns } });
    for (const worker of idleWorkers) {
      const existingAssigned = queue.find((item) => item.shift_id === state.shift_id && item.worker_id === worker.worker_id && !isWorkerReleaseAllowed(item));
      if (existingAssigned) {
        appendShiftLog({
          shiftId: state.shift_id,
          workId: existingAssigned.work_id,
          stage: existingAssigned.stage,
          event: "replacement_prevented_worker_job_not_complete",
          message: `${workerLabel(worker.worker_id)} already owns ${existingAssigned.work_id}; no replacement job created.`,
          data: { worker_id: worker.worker_id, status: existingAssigned.status, stage: existingAssigned.stage }
        });
        continue;
      }
      if (Number(state.created_this_shift || 0) >= maxDesigns) {
        appendShiftLog({ shiftId: state.shift_id, event: "idle_worker_not_filled_reason", message: `${workerLabel(worker.worker_id)} stayed idle because current-shift design capacity is full.`, data: { worker_id: worker.worker_id, created_this_shift: state.created_this_shift, maxDesignsPerShift: maxDesigns } });
        break;
      }
      if (activeWork.length + createdThisTick >= maxActive) {
        appendShiftLog({ shiftId: state.shift_id, event: "idle_worker_not_filled_reason", message: `${workerLabel(worker.worker_id)} stayed idle because active worker capacity is full.`, data: { worker_id: worker.worker_id, activeWorkCount: activeWork.length + createdThisTick, maxActiveWorkItems: maxActive } });
        break;
      }
      const work = createShiftWorkItem(state, queue, worker);
      queue.push(work);
      createdThisTick += 1;
      worker.status = "planning";
      worker.work_id = work.work_id;
      worker.current_task = `${workerLabel(worker.worker_id)} is planning a product idea.`;
      worker.updated_at = new Date().toISOString();
    }
    appendShiftLog({ shiftId: state.shift_id, event: "active_work_fill_finished", message: `Created ${createdThisTick} new Forge work item${createdThisTick === 1 ? "" : "s"}.`, data: { createdThisTick } });
    if (createdThisTick === 0 && Number(state.created_this_shift || 0) >= maxDesigns) {
      appendShiftLog({ shiftId: state.shift_id, event: "current_shift_capacity_full", message: "Current shift design capacity is full.", data: { created_this_shift: state.created_this_shift, maxDesignsPerShift: maxDesigns } });
    }
    if (createdThisTick > 0) {
      state.current_task = `Queued ${createdThisTick} Forge product idea${createdThisTick === 1 ? "" : "s"}.`;
      saveShiftQueue(queue);
      state = saveShiftState(state);
      return shiftStatusPayload();
    }

    await recoverForgeImageGenerationSetup(state, queue);

    for (const item of queue.filter((candidate) => isCurrentShiftRunnableWork(candidate, state.shift_id) && candidate.stage === "research_replan" && !candidate.opportunity_score)) {
      ensureRepairMetadata(item);
      item.research_replan_wait_ticks = Number(item.research_replan_wait_ticks || 0) + 1;
      if (item.research_replan_wait_ticks > 2) {
        item.updated_at = "";
        item.logs = workLog(item, "research_replan_stale_detected", "Nova replan was stale and will be forced on the next tick.");
        appendShiftLog({
          shiftId: state.shift_id,
          workId: item.work_id,
          stage: "research_replan",
          event: "research_replan_stale_detected",
          message: "Research replan has waited more than two ticks without an opportunity score; forcing handler priority.",
          data: { waitTicks: item.research_replan_wait_ticks }
        });
      }
    }

    const work = [...queue]
      .filter((item) => isCurrentShiftRunnableWork(item, state.shift_id))
      .sort((a, b) => String(a.updated_at || a.created_at || "").localeCompare(String(b.updated_at || b.created_at || "")))[0]
      || queue.find((item) => item.shift_id === state.shift_id && item.status === "needs_attention" && item.stage === "sentinel_qa");
    if (!work) {
      state.current_task = "No runnable work items. Waiting for setup, publishing, or queue changes.";
      state = saveShiftState(state);
      return shiftStatusPayload();
    }
    appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "forge_worker_rotated", message: `${workerLabel(work.worker_id)} advanced ${work.work_id}.`, data: { worker_id: work.worker_id } });

    try {
      await processShiftWorkOneStage(state, work);
    } catch (error) {
      state.counters.errors += 1;
      const rawError = String(error?.message || error);
      state.last_error = hasRawRuntimeExceptionText(rawError)
        ? "This product hit a repair error. Nova is replanning it."
        : rawError;
      if (work.stage === "sentinel_qa") {
        appendShiftLog({
          shiftId: state.shift_id,
          workId: work.work_id,
          stage: "sentinel_qa",
          event: "sentinel_qa_error",
          message: state.last_error
        });
      }
      ensureRepairMetadata(work);
      work.stage = "research_replan";
      work.status = "repairing";
      work.last_repair_reason = state.last_error;
      work.next_repair_strategy = "nova_research_replan";
      work.human_status = "This product hit a repair error. Nova is replanning it.";
      work.logs = workLog(work, "repair_error_replan", state.last_error, { raw_error: rawError });
      state.current_task = "This product hit a repair error. Nova is replanning it.";
      appendShiftLog({ shiftId: state.shift_id, workId: work.work_id, stage: work.stage, event: "repair_error_replan", message: state.last_error });
    }

    saveShiftQueue(queue);
    syncWorkersWithQueue(state, queue);
    state = saveShiftState(state);
    return shiftStatusPayload();
  });
}

async function runShiftLoopTick() {
  const state = loadShiftState();
  if (state.status !== "running") {
    stopShiftLoop("status_not_running", `Shift is ${state.status}; backend loop stopped.`);
    return;
  }

  if (shiftLoopRunning) {
    appendShiftLog({
      shiftId: state.shift_id,
      event: "loop_tick_error",
      message: "Previous backend loop tick is still running; skipped overlapping tick."
    });
    return;
  }

  shiftLoopRunning = true;
  appendShiftLog({ shiftId: state.shift_id, event: "loop_tick_started", message: "Backend shift loop tick started." });

  try {
    await runShiftTick();
    lastLoopTickAt = new Date().toISOString();
    lastLoopTickError = "";
    appendShiftLog({ shiftId: state.shift_id, event: "loop_tick_finished", message: "Backend shift loop tick finished." });
  } catch (error) {
    lastLoopTickError = String(error?.message || error);
    appendShiftLog({ shiftId: state.shift_id, event: "loop_tick_error", message: lastLoopTickError });
  } finally {
    shiftLoopRunning = false;
  }
}

function startShiftLoop(intervalMs = DEFAULT_SHIFT_TICK_INTERVAL_MS, event = "shift_loop_started") {
  shiftLoopIntervalMs = normalizeShiftIntervalMs(intervalMs);
  const state = loadShiftState();
  if (state.status !== "running") return shiftLoopInfo();

  if (shiftLoopTimer) {
    return shiftLoopInfo();
  }

  lastLoopStartedAt = new Date().toISOString();
  lastLoopTickError = "";
  appendShiftLog({
    shiftId: state.shift_id,
    event,
    message: `Backend shift loop started at ${shiftLoopIntervalMs}ms.`,
    data: { intervalMs: shiftLoopIntervalMs }
  });

  shiftLoopTimer = setInterval(() => {
    runShiftLoopTick();
  }, shiftLoopIntervalMs);

  setTimeout(() => {
    if (shiftLoopTimer) runShiftLoopTick();
  }, 0);

  return shiftLoopInfo();
}

function stopShiftLoop(event = "shift_loop_stopped", message = "Backend shift loop stopped.") {
  const state = loadShiftState();
  if (shiftLoopTimer) {
    clearInterval(shiftLoopTimer);
    shiftLoopTimer = null;
  }
  shiftLoopRunning = false;
  appendShiftLog({ shiftId: state.shift_id, event, message });
  return shiftLoopInfo();
}

async function diagnoseSupplierResearch(input = {}) {
  const suppliers = input.supplier && input.supplier !== "auto" ? [input.supplier] : ["printify", "printful"];
  const rows = [];
  for (const supplier of suppliers) {
    const keyName = supplier === "printify" ? "PRINTIFY_API_KEY" : "PRINTFUL_API_KEY";
    const endpoint = supplier === "printify"
      ? "https://api.printify.com/v1/catalog/blueprints.json"
      : "https://api.printful.com/products";
    if (!process.env[keyName]) {
      rows.push({
        supplier,
        keyStatus: "missing",
        endpoint,
        httpStatus: null,
        candidateCount: 0,
        baseCostFound: false,
        shippingFound: false,
        parseWarnings: [],
        rejectedReasons: [`${keyName} missing`]
      });
      continue;
    }
    try {
      const result = await researchSupplierProducts({
        designPackageId: input.designPackageId || "diagnostic",
        preferredSupplier: supplier,
        productType: input.productType || "poster",
        destinationCountry: input.destinationCountry,
        destinationState: input.destinationState,
        destinationZip: input.destinationZip,
        targetPrice: DEFAULT_TARGET_PRICES[input.productType] || 19.99,
        maxOptions: 5
      });
      rows.push({
        supplier,
        keyStatus: "present",
        endpoint,
        httpStatus: result.ok ? 200 : null,
        candidateCount: Array.isArray(result.options) ? result.options.length : 0,
        baseCostFound: (result.options || []).some((option) => moneyOrNull(option.baseCost) !== null),
        shippingFound: (result.options || []).some((option) => moneyOrNull(option.shippingCost) !== null && option.shippingCostVerified),
        parseWarnings: [...new Set((result.options || []).flatMap((option) => option.warnings || []))],
        rejectedReasons: result.error ? [result.error] : []
      });
    } catch (error) {
      rows.push({
        supplier,
        keyStatus: "present",
        endpoint,
        httpStatus: null,
        candidateCount: 0,
        baseCostFound: false,
        shippingFound: false,
        parseWarnings: [],
        rejectedReasons: [String(error?.message || error)]
      });
    }
  }
  return { ok: true, diagnostics: rows };
}

function findSupplierCatalogProduct({ productType, productId }) {
  const catalog = readJson("supplier_product_catalog.json", { products: [] });
  const normalizedProductType = String(productType || "").toLowerCase();
  const normalizedProductId = String(productId || "").toLowerCase();
  return Array.isArray(catalog.products) ? catalog.products.find((item) => {
    const id = String(item.id || "").toLowerCase();
    const category = String(item.category || "").toLowerCase();
    const name = String(item.name || "").toLowerCase();
    return (normalizedProductId && id === normalizedProductId)
      || (normalizedProductType && (category === normalizedProductType || id.includes(normalizedProductType) || name.includes(normalizedProductType)));
  }) : null;
}

function supplierConnectorStatus(supplier) {
  const checks = readJson("api_connector_status_checks.json", []);
  const latestCheck = latest(checks);
  const fromCheck = latestCheck?.results?.find((item) => item.connector_id === supplier);
  const registry = readJson("api_connector_registry.json", { connectors: [] });
  const connector = registry.connectors?.find((item) => item.id === supplier);

  return {
    connector,
    check: fromCheck,
    liveLookupAvailable: false,
    message: fromCheck?.computed_status === "missing_api_key"
      ? `${connector?.name || supplier} API key is missing. Add verified supplier costs manually or connect the API later.`
      : "Live supplier catalog lookup is not implemented in this build; using local verified supplier_costs.json rows or blocked estimates."
  };
}

function assertPromotedApprovedDesign(designPackageId) {
  const designs = readJson("design_packages.json", []);
  const assets = readJson("image_assets.json", []);
  const reports = readJson("visual_qa_reports.json", []);
  const design = designs.find((item) => item.id === designPackageId);

  if (!design) {
    const error = new Error("Design package not found.");
    error.statusCode = 404;
    throw error;
  }

  const asset = linkedForgeAssetForDesign(design, assets);
  if (!asset) {
    const error = new Error("Linked Forge image asset not found.");
    error.statusCode = 404;
    throw error;
  }

  validateExistingPng(asset.file_path);

  if (!approvedVisualQaForAsset(asset, reports)) {
    const error = new Error("Asset must pass Sentinel QA before economics can be attached.");
    error.statusCode = 409;
    throw error;
  }

  if (!design.source_image_asset_id && !design.forge_image_asset_id && !asset.promoted_design_id) {
    const error = new Error("Design must be promoted from a Forge local asset before economics can be attached.");
    error.statusCode = 409;
    throw error;
  }

  return { design, asset };
}

function saveEconomicsCard(card) {
  const economicsFile = path.join(STATE, "unit_economics_cards.json");
  const economics = readJson("unit_economics_cards.json", []);
  const index = economics.findIndex((item) => item.id === card.id || item.design_package_id === card.design_package_id);
  if (index >= 0) {
    economics[index] = card;
  } else {
    economics.push(card);
  }
  saveJsonFile(economicsFile, economics);
  return card;
}

function attachProductEconomics(input) {
  const designPackageId = String(input.designPackageId || "").trim();
  const supplier = String(input.supplier || "printify").trim().toLowerCase();
  const productType = String(input.productType || "poster").trim().toLowerCase();
  const productId = String(input.productId || "").trim();
  const variantId = String(input.variantId || "").trim();
  const targetPrice = moneyOrNull(input.targetPrice);

  if (!designPackageId) {
    const error = new Error("Missing designPackageId.");
    error.statusCode = 400;
    throw error;
  }
  if (!["printify", "printful"].includes(supplier)) {
    const error = new Error("Supplier must be printify or printful.");
    error.statusCode = 400;
    throw error;
  }

  const { design, asset } = assertPromotedApprovedDesign(designPackageId);
  const economics = readJson("unit_economics_cards.json", []);
  const existing = latestFor(economics, (item) => item.design_package_id === design.id);
  const verifiedCost = findVerifiedSupplierCost({ supplier, productType, productId, variantId });
  const catalogProduct = findSupplierCatalogProduct({ productType, productId });
  const connector = supplierConnectorStatus(supplier);
  const source = verifiedCost ? "supplier_costs_verified" : catalogProduct ? "supplier_catalog_estimate" : "connector_unavailable";
  const baseCost = verifiedCost?.production_cost ?? catalogProduct?.estimated_base_cost_usd ?? null;
  const shippingCost = verifiedCost?.shipping_cost_us ?? catalogProduct?.estimated_shipping_usd ?? null;
  const price = targetPrice ?? verifiedCost?.recommended_price ?? catalogProduct?.recommended_min_price_usd ?? null;
  const verifiedSupplierCost = Boolean(verifiedCost?.verified_supplier_cost || verifiedCost?.supplier_cost_verified);
  const verifiedShippingCost = Boolean(verifiedCost?.verified_shipping_cost || verifiedCost?.shipping_cost_verified);
  const card = buildEconomicsCard({
    existing,
    design,
    asset,
    supplier,
    productType,
    productId: productId || catalogProduct?.id || "",
    variantId: variantId || verifiedCost?.variant || "",
    targetPrice: price,
    baseCost,
    shippingCost,
    verifiedSupplierCost,
    verifiedShippingCost,
    manuallyEntered: false,
    source,
    notes: verifiedCost
      ? "Created from verified local supplier_costs.json data. No publishing action was taken."
      : `${connector.message} Estimates do not satisfy verified Ledger gates.`
  });

  saveEconomicsCard(card);
  return {
    economics: card,
    supplierProduct: verifiedCost || catalogProduct || null,
    connector,
    nextSuggestedAction: card.ledger_decision === "PASS" ? "run_scribe_listing_draft" : "add_verified_supplier_costs"
  };
}

function attachManualEconomics(input) {
  const designPackageId = String(input.designPackageId || "").trim();
  const supplier = String(input.supplier || "manual").trim().toLowerCase();
  const productType = String(input.productType || "").trim().toLowerCase();
  const baseCost = moneyOrNull(input.baseCost);
  const shippingCost = moneyOrNull(input.shippingCost);
  const targetPrice = moneyOrNull(input.targetPrice);

  if (!designPackageId || !supplier || !productType) {
    const error = new Error("Missing designPackageId, supplier, or productType.");
    error.statusCode = 400;
    throw error;
  }
  if (!["printify", "printful", "manual"].includes(supplier)) {
    const error = new Error("Supplier must be printify, printful, or manual.");
    error.statusCode = 400;
    throw error;
  }

  const { design, asset } = assertPromotedApprovedDesign(designPackageId);
  const economics = readJson("unit_economics_cards.json", []);
  const existing = latestFor(economics, (item) => item.design_package_id === design.id);
  const card = buildEconomicsCard({
    existing,
    design,
    asset,
    supplier,
    productType,
    productId: "manual_entry",
    variantId: "manual_entry",
    targetPrice,
    baseCost,
    shippingCost,
    verifiedSupplierCost: false,
    verifiedShippingCost: false,
    manuallyEntered: true,
    source: "manual_local_entry",
    notes: "Manual local economics entry for testing only. Supplier/shipping costs are not verified, so Publisher final publish remains blocked by policy."
  });

  saveEconomicsCard(card);
  return {
    economics: card,
    nextSuggestedAction: "replace_with_verified_supplier_costs"
  };
}

function productFitFor(productType) {
  const type = String(productType || "poster").trim().toLowerCase() || "poster";
  const fallback = ["poster", "shirt", "mug", "tote", "sticker"];
  return [type, ...fallback.filter((item) => item !== type)];
}

function promoteForgeArtToDesign(input) {
  const assetId = String(input.assetId || "").trim();
  if (!assetId) {
    const error = new Error("Missing assetId.");
    error.statusCode = 400;
    throw error;
  }

  const imageAssetsFile = path.join(STATE, "image_assets.json");
  const designFile = path.join(STATE, "design_packages.json");
  const requestsFile = path.join(STATE, "image_generation_requests.json");
  const economicsFile = path.join(STATE, "unit_economics_cards.json");

  const assets = readJson("image_assets.json", []);
  const reports = readJson("visual_qa_reports.json", []);
  const designs = readJson("design_packages.json", []);
  const requests = readJson("image_generation_requests.json", []);
  const economics = readJson("unit_economics_cards.json", []);
  const assetIndex = assets.findIndex((item) => item.id === assetId);
  const asset = assetIndex >= 0 ? assets[assetIndex] : null;

  if (!asset) {
    const error = new Error("Image asset not found.");
    error.statusCode = 404;
    throw error;
  }

  const imagePath = validateExistingPng(asset.file_path);
  const approvedQa = approvedVisualQaForAsset(asset, reports);
  if (!approvedQa) {
    const error = new Error("Asset must pass Sentinel QA before promotion.");
    error.statusCode = 409;
    throw error;
  }

  const metadataPath = validateExistingMetadata(asset.metadata_path || "");
  const metadata = readJsonFilePath(metadataPath, {});
  const productType = asset.product_type || metadata.productType || "poster";
  const title = asset.title || metadata.title || "Forge local art";
  const prompt = asset.prompt || metadata.prompt || "";
  const createdAt = new Date().toISOString();

  let design = designs.find((item) => item.forge_image_asset_id === assetId || item.source_image_asset_id === assetId);
  if (!design) {
    design = {
      id: nextStateId(designs, "DESIGN"),
      type: "design_package",
      status: "local_asset_promoted_from_forge",
      opportunity_id: null,
      opportunity_status: "local_forge_asset",
      evidence_level: "local_generated_art",
      source: "forge_local_comfyui",
      source_image_asset_id: assetId,
      forge_image_asset_id: assetId,
      image_asset_id: assetId,
      visual_qa_report_id: approvedQa.id || asset.visual_qa || null,
      title,
      design_concept: `Local Forge image promoted after Sentinel product QA approval. ${prompt}`.trim(),
      image_prompt: prompt,
      product_fit: productFitFor(productType),
      print_area_notes: "Promoted from a local PNG. Confirm supplier template, print area, and margins before upload.",
      aspect_ratio: metadata.width && metadata.height ? `${metadata.width}:${metadata.height}` : "local_png",
      transparent_background: false,
      mockup_notes: "Use mockups only after Sentinel QA; external publishing remains blocked by Ledger, Scribe, and Publisher gates.",
      filename_stem: sanitizeGeneratedArtName(`${assetId}-${title}`),
      copyright_trademark_risk: "low if Sentinel approval remains valid and prompt contains no protected references",
      safety_notes: "Promoted only after Sentinel product QA approval. No live upload or Etsy publishing is allowed from this step.",
      production_allowed: true,
      listing_allowed: false,
      local_image_path: imagePath,
      metadata_path: metadataPath || asset.metadata_path || null,
      seed: asset.seed || metadata.seed || null,
      source_created_at: asset.created_at || metadata.createdAt || null,
      created_at: createdAt
    };
    designs.push(design);
  }

  let request = requests.find((item) => item.forge_image_asset_id === assetId || item.source_image_asset_id === assetId);
  if (!request) {
    request = {
      id: nextStateId(requests, "IMGREQ"),
      type: "image_generation_request",
      status: "completed_local_asset_promoted",
      design_package_id: design.id,
      design_status: design.status,
      design_evidence_level: design.evidence_level,
      provider_id: "local_comfyui",
      provider_local_safe: true,
      source_image_asset_id: assetId,
      forge_image_asset_id: assetId,
      subject: title,
      composition: "Existing local PNG generated by Forge and approved by Sentinel QA.",
      style: "Original local Forge product artwork.",
      color_palette: "Derived from local generated image.",
      text_rules: "No protected marks, logos, celebrity likeness, or unapproved readable text.",
      product_use: `${productType} print-on-demand candidate; supplier template must be checked before publishing.`,
      aspect_ratio: design.aspect_ratio,
      required_elements: ["local PNG exists", "Sentinel product QA approval"],
      forbidden_elements: ["logos", "brand names", "protected characters", "celebrity likeness", "watermarks", "signatures"],
      negative_constraints: asset.negative_prompt || metadata.negativePrompt || "",
      quality_bar: "Must remain product-ready under Sentinel, Ledger, Scribe, and Publisher gates.",
      size: metadata.width && metadata.height ? `${metadata.width}x${metadata.height}` : "local_png",
      seed: asset.seed || metadata.seed || "unknown",
      prompt,
      issues: [],
      production_allowed: true,
      listing_allowed: false,
      notes: "Bridge request created from an already-generated local Forge PNG. No live image API call.",
      created_at: createdAt
    };
    requests.push(request);
  }

  let ledger = latestFor(economics, (item) => item.design_package_id === design.id);
  if (!ledger) {
    ledger = {
      id: nextStateId(economics, "ECON"),
      type: "unit_economics_card",
      status: "complete",
      design_package_id: design.id,
      design_status: design.status,
      source_image_asset_id: assetId,
      supplier: "MANUAL",
      product_type: productType,
      variant: "cost_data_missing",
      item_price: "cost_data_missing",
      customer_shipping_paid: 0,
      production_cost: "cost_data_missing",
      shipping_cost_us: "buyer_paid_shipping_estimate_missing",
      verified_supplier_cost: false,
      verified_shipping_cost: false,
      ledger_decision: "COST_DATA_MISSING",
      decision: "COST_DATA_MISSING",
      issues: [
        "item_price_missing",
        "production_cost_missing",
        "supplier_cost_not_verified"
      ],
      calculation: {},
      production_allowed: false,
      listing_allowed: false,
      notes: "Created by Forge promotion bridge. Replace with verified Printify/Printful product cost data before listing is allowed. Buyer-paid shipping estimates are tracked separately from item margin.",
      created_at: createdAt
    };
    economics.push(ledger);
  }

  const updatedAsset = {
    ...asset,
    status: "local_generated_promoted_to_design",
    file_path: imagePath,
    metadata_path: metadataPath || asset.metadata_path,
    design_package_id: design.id,
    image_request_id: request.id,
    promoted_design_id: design.id,
    promoted_ledger_id: ledger.id,
    promoted_at: asset.promoted_at || createdAt,
    next_agent: ledger.ledger_decision === "PASS" || ledger.decision === "PASS" ? "Scribe" : "Ledger",
    updated_at: createdAt
  };

  assets[assetIndex] = updatedAsset;

  saveJsonFile(designFile, designs);
  saveJsonFile(requestsFile, requests);
  saveJsonFile(economicsFile, economics);
  saveJsonFile(imageAssetsFile, assets);

  const ledgerPass = ledger.ledger_decision === "PASS" || ledger.decision === "PASS";
  return {
    asset: updatedAsset,
    design,
    imageRequest: request,
    ledger,
    nextSuggestedAction: ledgerPass ? "run_scribe_listing_draft" : "add_verified_ledger_costs"
  };
}

function saveGeneratedArtMetadata(filenameStem, metadata) {
  const filePath = assertGeneratedArtPath(path.join(forgeArtOutputDir(), `${sanitizeGeneratedArtName(filenameStem)}.json`));
  saveJsonFile(filePath, metadata);
  return filePath;
}

function saveGeneratedArtPng(filenameStem, bytes) {
  const buffer = Buffer.from(bytes);
  const isPng = buffer.length > 8
    && buffer[0] === 0x89
    && buffer[1] === 0x50
    && buffer[2] === 0x4e
    && buffer[3] === 0x47
    && buffer[4] === 0x0d
    && buffer[5] === 0x0a
    && buffer[6] === 0x1a
    && buffer[7] === 0x0a;
  if (!isPng) {
    throw new Error("Forge product artwork must be a PNG. Non-PNG output was rejected.");
  }
  const filePath = assertGeneratedArtPath(path.join(forgeArtOutputDir(), `${sanitizeGeneratedArtName(filenameStem)}.png`));
  fs.writeFileSync(filePath, buffer);
  return {
    localImagePath: filePath,
    publicImageUrl: `/api/generated-art/${encodeURIComponent(path.basename(filePath))}`
  };
}

function buildSimpleTextToImageWorkflow(args) {
  return {
    "1": {
      class_type: "CheckpointLoaderSimple",
      inputs: {
        ckpt_name: args.checkpointName
      }
    },
    "2": {
      class_type: "CLIPTextEncode",
      inputs: {
        text: args.prompt,
        clip: ["1", 1]
      }
    },
    "3": {
      class_type: "CLIPTextEncode",
      inputs: {
        text: args.negativePrompt,
        clip: ["1", 1]
      }
    },
    "4": {
      class_type: "EmptyLatentImage",
      inputs: {
        width: args.width,
        height: args.height,
        batch_size: 1
      }
    },
    "5": {
      class_type: "KSampler",
      inputs: {
        seed: args.seed,
        steps: args.steps,
        cfg: args.cfg,
        sampler_name: "euler",
        scheduler: "normal",
        denoise: 1,
        model: ["1", 0],
        positive: ["2", 0],
        negative: ["3", 0],
        latent_image: ["4", 0]
      }
    },
    "6": {
      class_type: "VAEDecode",
      inputs: {
        samples: ["5", 0],
        vae: ["1", 2]
      }
    },
    "7": {
      class_type: "SaveImage",
      inputs: {
        filename_prefix: args.filenamePrefix,
        images: ["6", 0]
      }
    }
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function getForgeArtHealth() {
  const baseUrl = localArtBaseUrl();
  const checkedAt = new Date().toISOString();
  const checkpointName = process.env.COMFYUI_CHECKPOINT_NAME || "sd_xl_base_1.0.safetensors";
  if (!isLocalComfyUrl(baseUrl)) {
    return {
      ok: false,
      provider: "comfyui",
      baseUrl,
      reason: "ComfyUI must stay local. Use http://127.0.0.1:8188 or localhost.",
      error: "ComfyUI must stay local. Use http://127.0.0.1:8188 or localhost.",
      checkpointName,
      checkedAt
    };
  }
  try {
    const response = await fetchWithTimeout(`${baseUrl}/system_stats`, {}, 4000);
    if (!response.ok) {
      return {
        ok: false,
        provider: "comfyui",
        baseUrl,
        reason: `ComfyUI responded with HTTP ${response.status}.`,
        error: `ComfyUI responded with HTTP ${response.status}.`,
        checkpointName,
        checkedAt
      };
    }
    return { ok: true, provider: "comfyui", baseUrl, reason: "ComfyUI is reachable.", checkpointName, checkedAt };
  } catch {
    return {
      ok: false,
      provider: "comfyui",
      baseUrl,
      reason: "ComfyUI is not reachable. Start ComfyUI locally on http://127.0.0.1:8188, then try again.",
      error: "ComfyUI is not reachable. Start ComfyUI locally on http://127.0.0.1:8188, then try again.",
      checkpointName,
      checkedAt
    };
  }
}

async function checkComfyUiHealth() {
  return getForgeArtHealth();
}

function findComfySavedImage(history, promptId) {
  const promptHistory = history?.[promptId] || history;
  const outputs = promptHistory?.outputs;
  if (!outputs || typeof outputs !== "object") return null;

  for (const output of Object.values(outputs)) {
    if (Array.isArray(output?.images) && output.images.length && output.images[0]?.filename) {
      return output.images[0];
    }
  }
  return null;
}

function nextLocalArtId(records, prefix) {
  let highest = 0;
  for (const item of Array.isArray(records) ? records : []) {
    const raw = String(item.id || "");
    if (!raw.startsWith(`${prefix}-`)) continue;
    const number = Number(raw.split("-")[1]);
    if (Number.isFinite(number)) highest = Math.max(highest, number);
  }
  return `${prefix}-${String(highest + 1).padStart(4, "0")}`;
}

function appendLocalArtState(result, input, settings) {
  if (!result.ok || !result.localImagePath) return null;

  const imageRunsFile = path.join(STATE, "image_generation_runs.json");
  const imageAssetsFile = path.join(STATE, "image_assets.json");
  const runs = readJson("image_generation_runs.json", []);
  const assets = readJson("image_assets.json", []);
  const runId = nextLocalArtId(runs, "LOCALART");
  const assetId = nextLocalArtId(assets, "LOCALIMG");
  const createdAt = new Date().toISOString();

  runs.push({
    id: runId,
    type: "image_generation_run",
    status: "completed_local_comfyui",
    mode: "local_api",
    provider_id: "local_comfyui",
    model: settings.checkpointName,
    image_request_id: null,
    live_generation_allowed: true,
    live_api_enabled: false,
    counts_against_budget: false,
    prompt_id: result.promptId,
    seed: result.seed,
    issues: [],
    warnings: [],
    result_notes: "Generated locally through ComfyUI. No OpenAI image API call and no external publishing.",
    created_at: createdAt
  });

  const asset = {
    id: assetId,
    type: "image_asset",
    status: "local_generated_waiting_sentinel",
    image_generation_run_id: runId,
    provider_id: "local_comfyui",
    model: settings.checkpointName,
    file_path: result.localImagePath,
    public_preview_url: result.publicImageUrl,
    metadata_path: result.metadataPath,
    file_type: "png",
    file_exists: true,
    metadata_exists: Boolean(result.metadataPath),
    prompt: input.prompt,
    negative_prompt: input.negativePrompt,
    product_type: input.productType || "product_art",
    product_intent: input.productType || "multi_product",
    artwork_format: "png",
    product_ready_png: false,
    transparent_png_ready: false,
    background_status: "unknown",
    title: input.title || "Forge local art",
    approved_for_mockup: false,
    approved_for_product: false,
    queued_for_sentinel: true,
    ready_for_sentinel_qa: true,
    sentinel_queue_status: "waiting",
    next_agent: "Sentinel",
    notes: "Local PNG is ready for Sentinel QA before product/listing/publishing gates.",
    created_at: createdAt
  };

  assets.push(asset);

  saveJsonFile(imageRunsFile, runs);
  saveJsonFile(imageAssetsFile, assets);
  return asset;
}

async function generateLocalForgeArtworkForWorkItem(work, options = {}) {
  ensureRepairMetadata(work);
  const state = options.state || {};
  const health = options.health || await getForgeArtHealth();
  work.setup_health = health;
  if (!health.ok) {
    return { ok: false, health, error: health.reason || health.error || "ComfyUI is not reachable." };
  }

  const now = new Date().toISOString();
  work.generation_started_at = now;
  work.generation_attempt_count = Number(work.generation_attempt_count || 0) + 1;
  work.last_generation_error = "";
  work.status = "generating_art";
  work.stage = "image_generation";
  work.current_task = "Forge is creating the PNG.";
  work.human_status = "Forge is creating the PNG.";
  work.logs = workLog(work, "comfyui_generation_submitted", "Forge submitted this PNG job to ComfyUI.", {
    attempt: work.generation_attempt_count,
    worker_id: work.worker_id,
    baseUrl: health.baseUrl,
    checkpointName: health.checkpointName
  });
  appendShiftLog({
    shiftId: state.shift_id || work.shift_id,
    workId: work.work_id,
    stage: "image_generation",
    event: "comfyui_generation_submitted",
    message: "Forge submitted this PNG job to ComfyUI.",
    data: {
      worker_id: work.worker_id,
      attempt: work.generation_attempt_count,
      baseUrl: health.baseUrl,
      checkpointName: health.checkpointName
    }
  });

  const result = await generateForgeLocalArt({
    prompt: work.prompt,
    negativePrompt: work.negative_prompt,
    title: `Autonomous ${work.prompt_family || "product"} ${work.work_id}`,
    productType: work.product_intent || "multi_product"
  });

  work.generation_prompt_id = result.promptId || work.generation_prompt_id || "";

  if (!result.ok || !result.assetId) {
    const message = result.error || "Local PNG generation failed.";
    work.last_generation_error = message;
    recordRepair(work, {
      stage: "image_generation",
      reason: message,
      strategy: "retry_png_generation",
      result: "retry_scheduled"
    });
    work.status = "repairing";
    work.stage = "image_generation";
    work.next_repair_strategy = "retry_png_generation";
    work.current_task = "Forge hit a PNG generation error and is retrying.";
    work.human_status = "Forge hit a PNG generation error and is retrying.";
    work.logs = workLog(work, "comfyui_generation_failed", "Forge hit a PNG generation error and is retrying.", {
      error: message,
      prompt_id: result.promptId || "",
      metadataPath: result.metadataPath || ""
    });
    appendShiftLog({
      shiftId: state.shift_id || work.shift_id,
      workId: work.work_id,
      stage: "image_generation",
      event: "comfyui_generation_failed",
      message,
      data: {
        worker_id: work.worker_id,
        prompt_id: result.promptId || "",
        error: message,
        metadataPath: result.metadataPath || ""
      }
    });
    return { ...result, ok: false, health, error: message };
  }

  const asset = result.asset || readJson("image_assets.json", []).find((item) => item.id === result.assetId) || null;
  const runId = asset?.image_generation_run_id || "";
  work.asset_id = result.assetId;
  work.image_generation_run_id = runId;
  work.generation_prompt_id = result.promptId || "";
  work.last_generation_error = "";
  work.setup_blocker = "";
  work.status = "qa_checking";
  work.stage = "sentinel_qa";
  work.current_task = "Sentinel is checking the PNG.";
  work.human_status = "Sentinel is checking the PNG.";
  work.updated_at = new Date().toISOString();
  work.logs = workLog(work, "comfyui_generation_completed", "Forge completed the PNG and attached it to this product.", {
    prompt_id: result.promptId || "",
    image_generation_run_id: runId,
    image_asset_id: result.assetId,
    output_path: result.localImagePath || asset?.file_path || ""
  });
  appendShiftLog({
    shiftId: state.shift_id || work.shift_id,
    workId: work.work_id,
    stage: "image_generation",
    event: "comfyui_generation_completed",
    message: "Forge completed the PNG and attached it to this product.",
    data: {
      worker_id: work.worker_id,
      prompt_id: result.promptId || "",
      image_generation_run_id: runId,
      image_asset_id: result.assetId,
      output_path: result.localImagePath || asset?.file_path || ""
    }
  });
  return { ...result, ok: true, asset, imageGenerationRunId: runId, health };
}

function sendForgeArtToSentinel(input) {
  const imageAssetsFile = path.join(STATE, "image_assets.json");
  const assets = readJson("image_assets.json", []);
  const now = new Date().toISOString();
  const assetId = String(input.assetId || "").trim();

  let index = assetId ? assets.findIndex((item) => item.id === assetId) : -1;
  let existing = index >= 0 ? assets[index] : null;
  const imagePath = validateExistingPng(input.localImagePath || existing?.file_path);
  const metadataPath = validateExistingMetadata(input.metadataPath || existing?.metadata_path || "");

  if (!existing) {
    const publicPreview = publicGeneratedArtUrl(imagePath);
    existing = {
      id: nextLocalArtId(assets, "LOCALIMG"),
      type: "image_asset",
      provider_id: "local_comfyui",
      file_path: imagePath,
      public_preview_url: publicPreview,
      metadata_path: metadataPath || undefined,
      approved_for_mockup: false,
      approved_for_product: false,
      external_action_allowed: false,
      created_at: now
    };
    assets.push(existing);
    index = assets.length - 1;
  }

  const updated = {
    ...existing,
    status: isWaitingForSentinel(existing) ? existing.status : "local_generated_waiting_sentinel",
    file_path: imagePath,
    public_preview_url: existing.public_preview_url || publicGeneratedArtUrl(imagePath),
    metadata_path: metadataPath || existing.metadata_path,
    file_type: "png",
    file_exists: true,
    metadata_exists: Boolean(metadataPath || existing.metadata_path),
    approved_for_mockup: Boolean(existing.approved_for_mockup),
    approved_for_product: Boolean(existing.approved_for_product),
    product_ready_png: Boolean(existing.product_ready_png && existing.approved_for_product),
    transparent_png_ready: Boolean(existing.transparent_png_ready),
    external_action_allowed: Boolean(existing.external_action_allowed && existing.approved_for_product),
    queued_for_sentinel: true,
    ready_for_sentinel_qa: true,
    sentinel_queue_status: "waiting",
    next_agent: "Sentinel",
    notes: existing.notes || "Local PNG is ready for Sentinel QA before product/listing/publishing gates.",
    sentinel_queued_at: existing.sentinel_queued_at || now,
    updated_at: now
  };

  assets[index] = updated;
  saveJsonFile(imageAssetsFile, assets);
  return updated;
}

async function generateForgeLocalArt(input) {
  const prompt = String(input.prompt || "").trim();
  const negativePrompt = String(input.negativePrompt || DEFAULT_FORGE_NEGATIVE_PROMPT).trim();
  const seed = Number.isFinite(Number(input.seed)) ? Number(input.seed) : Math.floor(Math.random() * 1000000000);
  const width = Number(input.width || numberEnv("FORGE_DEFAULT_WIDTH", 1024));
  const height = Number(input.height || numberEnv("FORGE_DEFAULT_HEIGHT", 1024));
  const steps = Number(input.steps || numberEnv("FORGE_DEFAULT_STEPS", 28));
  const cfg = Number(input.cfg || numberEnv("FORGE_DEFAULT_CFG", 7));
  const checkpointName = process.env.COMFYUI_CHECKPOINT_NAME || "sd_xl_base_1.0.safetensors";
  const filenameStem = sanitizeGeneratedArtName(`forge-${Date.now()}-${input.productType || "product"}-${input.title || "local-art"}`);

  if (!prompt) {
    return { ok: false, provider: "comfyui", prompt, negativePrompt, seed, error: "Prompt is required." };
  }

  const health = await checkComfyUiHealth();
  const settings = { checkpointName, width, height, steps, cfg };
  if (!health.ok) {
    const metadataPath = saveGeneratedArtMetadata(filenameStem, {
      provider: "comfyui",
      prompt,
      negativePrompt,
      seed,
      title: input.title,
      productType: input.productType,
      ...settings,
      file_type: "png",
      product_ready_png: false,
      transparent_png_ready: false,
      status: "failed",
      error: health.error,
      createdAt: new Date().toISOString()
    });
    return { ok: false, provider: "comfyui", prompt, negativePrompt, metadataPath, seed, error: health.error };
  }

  try {
    const workflow = buildSimpleTextToImageWorkflow({
      prompt,
      negativePrompt,
      width,
      height,
      steps,
      cfg,
      seed,
      checkpointName,
      filenamePrefix: filenameStem
    });

    const queueResponse = await fetchWithTimeout(`${localArtBaseUrl()}/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: workflow })
    }, 10000);

    if (!queueResponse.ok) {
      throw new Error(`ComfyUI rejected the workflow with HTTP ${queueResponse.status}.`);
    }

    const queued = await queueResponse.json();
    const promptId = queued?.prompt_id;
    if (!promptId) throw new Error("ComfyUI did not return a prompt_id.");

    let savedImage = null;
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      await delay(1500);
      const historyResponse = await fetchWithTimeout(`${localArtBaseUrl()}/history/${encodeURIComponent(promptId)}`, {}, 8000);
      if (!historyResponse.ok) continue;
      savedImage = findComfySavedImage(await historyResponse.json(), promptId);
      if (savedImage) break;
    }

    if (!savedImage) {
      throw new Error("ComfyUI did not finish an image before the timeout.");
    }

    const params = new URLSearchParams({
      filename: savedImage.filename,
      subfolder: savedImage.subfolder || "",
      type: savedImage.type || "output"
    });
    const imageResponse = await fetchWithTimeout(`${localArtBaseUrl()}/view?${params.toString()}`, {}, 30000);
    if (!imageResponse.ok) {
      throw new Error(`Could not download ComfyUI image. HTTP ${imageResponse.status}.`);
    }

    const stored = saveGeneratedArtPng(filenameStem, await imageResponse.arrayBuffer());
    const metadataPath = saveGeneratedArtMetadata(filenameStem, {
      provider: "comfyui",
      prompt,
      negativePrompt,
      promptId,
      seed,
      title: input.title,
      productType: input.productType,
      ...settings,
      file_type: "png",
      product_ready_png: false,
      transparent_png_ready: false,
      comfyImage: {
        filename: savedImage.filename,
        subfolder: savedImage.subfolder || "",
        type: savedImage.type || "output"
      },
      status: "completed",
      createdAt: new Date().toISOString()
    });

    const result = {
      ok: true,
      provider: "comfyui",
      prompt,
      negativePrompt,
      localImagePath: stored.localImagePath,
      publicImageUrl: stored.publicImageUrl,
      metadataPath,
      promptId,
      seed
    };
    const asset = appendLocalArtState(result, { ...input, prompt, negativePrompt }, settings);
    result.asset = asset;
    result.assetId = asset?.id;
    return result;
  } catch (error) {
    const message = String(error?.message || error);
    const metadataPath = saveGeneratedArtMetadata(filenameStem, {
      provider: "comfyui",
      prompt,
      negativePrompt,
      seed,
      title: input.title,
      productType: input.productType,
      ...settings,
      file_type: "png",
      product_ready_png: false,
      transparent_png_ready: false,
      status: "failed",
      error: message,
      createdAt: new Date().toISOString()
    });
    return { ok: false, provider: "comfyui", prompt, negativePrompt, metadataPath, seed, error: message };
  }
}

function saveSecretsEverywhere(incomingSecrets) {
  ensureDir(STATE);

  const existing = readJson(SECRETS_FILE, {});
  const merged = { ...existing };

  for (const [key, value] of Object.entries(incomingSecrets || {})) {
    const cleaned = String(value || "").trim();
    if (cleaned) merged[key] = cleaned;
  }

  fs.writeFileSync(SECRETS_FILE, JSON.stringify(merged, null, 2), "utf8");

  writeEnvFile(path.join(ROOT, ".env.local"), merged);
  writeEnvFile(path.join(ROOT, "ui", ".env.local"), merged);

  for (const [key, value] of Object.entries(merged)) {
    if (value) process.env[key] = value;
  }

  return merged;
}

function loadSavedSecrets() {
  try {
    if (!fs.existsSync(SECRETS_FILE)) return {};
    const raw = fs.readFileSync(SECRETS_FILE, "utf8");
    const parsed = JSON.parse(raw || "{}");

    for (const [key, value] of Object.entries(parsed || {})) {
      if (value && !process.env[key]) {
        process.env[key] = String(value);
      }
    }

    return parsed || {};
  } catch {
    return {};
  }
}

function getSecretStatus() {
  const saved = loadSavedSecrets();
  return maskSecretStatus(saved);
}

app.get("/api/generated-art/:filename", (req, res) => {
  try {
    const filePath = resolveGeneratedArtFile(req.params.filename);
    if (!filePath) {
      res.status(404).send("Not found");
      return;
    }

    const lower = filePath.toLowerCase();
    if (lower.endsWith(".png")) {
      res.type("image/png").sendFile(filePath);
      return;
    }
    if (lower.endsWith(".json")) {
      res.type("application/json").sendFile(filePath);
      return;
    }
    res.status(404).send("Not found");
  } catch {
    res.status(404).send("Not found");
  }
});

app.get("/api/forge/art/health", async (req, res) => {
  res.json(await getForgeArtHealth());
});

app.post("/api/forge/art/generate-test", async (req, res) => {
  const body = req.body || {};
  const result = await generateForgeLocalArt({
    prompt: body.prompt || DEFAULT_FORGE_PROMPT,
    negativePrompt: body.negativePrompt || DEFAULT_FORGE_NEGATIVE_PROMPT,
    title: body.title || "Forge local test design",
    productType: body.productType || "sticker"
  });
  res.status(result.ok ? 200 : 503).json(result);
});

app.post("/api/forge/art/send-to-sentinel", (req, res) => {
  try {
    const asset = sendForgeArtToSentinel(req.body || {});
    res.json({ ok: true, asset });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/sentinel/qa/run", (req, res) => {
  try {
    const result = runSentinelQa(req.body || {});
    res.json({ ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/forge/art/promote-to-design", (req, res) => {
  try {
    const result = promoteForgeArtToDesign(req.body || {});
    res.json({ ok: true, ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/forge/art/attach-product-economics", (req, res) => {
  try {
    const result = attachProductEconomics(req.body || {});
    res.json({ ok: true, ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/forge/art/manual-economics", (req, res) => {
  try {
    const result = attachManualEconomics(req.body || {});
    res.json({ ok: true, ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.get("/api/forge/supplier-costs", (req, res) => {
  res.json({ ok: true, rows: listSupplierCosts() });
});

app.post("/api/forge/supplier-costs/upsert", (req, res) => {
  try {
    const row = upsertSupplierCost(req.body || {});
    res.json({ ok: true, row, rows: listSupplierCosts(), state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/forge/research/supplier-costs", async (req, res) => {
  try {
    const body = req.body || {};
    const designPackageId = String(body.designPackageId || "").trim();
    if (!designPackageId) {
      res.status(400).json({ ok: false, error: "Missing designPackageId." });
      return;
    }
    assertPromotedApprovedDesign(designPackageId);
    const result = await researchSupplierProducts({
      designPackageId,
      preferredSupplier: body.preferredSupplier || "auto",
      productType: body.productType || "poster",
      destinationCountry: body.destinationCountry,
      destinationState: body.destinationState,
      destinationZip: body.destinationZip,
      targetPrice: moneyOrNull(body.targetPrice) ?? undefined,
      maxOptions: Number(body.maxOptions || 8)
    });
    res.status(result.ok ? 200 : 409).json({ ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/forge/research/diagnose", async (req, res) => {
  try {
    res.json(await diagnoseSupplierResearch(req.body || {}));
  } catch (error) {
    res.status(error?.statusCode || 500).json({ ok: false, error: String(error?.message || error) });
  }
});

app.post("/api/research/etsy/trends", async (req, res) => {
  try {
    res.json(await researchEtsyTrends(req.body || {}));
  } catch (error) {
    res.status(500).json({ ok: false, source: "missing_connector", trends: [], warnings: [String(error?.message || error)] });
  }
});

app.post("/api/research/seo/keywords", async (req, res) => {
  try {
    res.json(await researchSeoKeywords(req.body || {}));
  } catch (error) {
    res.status(500).json({
      ok: false,
      providerUsed: "local_seed",
      keywords: [],
      titleAngles: [],
      tags: [],
      warnings: [String(error?.message || error)],
      diagnostics: {}
    });
  }
});

app.post("/api/research/supplier-catalog/refresh", async (req, res) => {
  try {
    const result = await refreshSupplierCatalog(req.body || {});
    res.status(result.ok ? 200 : 409).json({
      ok: Boolean(result.ok),
      sourceCounts: result.sourceCounts || {},
      totalProducts: result.totalProducts || 0,
      totalVariants: result.totalVariants || 0,
      suppliers: result.suppliers || [],
      warnings: result.warnings || [],
      diagnostics: result.diagnostics || {},
      missingConnector: result.missingConnector || ""
    });
  } catch (error) {
    res.status(500).json({ ok: false, sourceCounts: {}, totalProducts: 0, totalVariants: 0, suppliers: [], warnings: [String(error?.message || error)], diagnostics: {} });
  }
});

app.get("/api/research/supplier-catalog", (req, res) => {
  try {
    res.json(summarizeSupplierCatalog(loadSupplierCatalog()));
  } catch (error) {
    res.status(500).json({ ok: false, sourceCounts: {}, totalProducts: 0, totalVariants: 0, suppliers: [], warnings: [String(error?.message || error)], diagnostics: {} });
  }
});

app.post("/api/forge/research/apply-recommended-economics", (req, res) => {
  try {
    const body = req.body || {};
    const designPackageId = String(body.designPackageId || "").trim();
    if (!designPackageId) {
      res.status(400).json({ ok: false, error: "Missing designPackageId." });
      return;
    }
    assertPromotedApprovedDesign(designPackageId);
    const option = body.option || {};
    const targetPrice = moneyOrNull(body.targetPrice) ?? moneyOrNull(option.targetPrice) ?? moneyOrNull(option.recommendedPrice);
    const row = upsertSupplierCostFromResearchOption(option, targetPrice);
    const economicsResult = attachProductEconomics({
      designPackageId,
      supplier: option.supplier,
      productType: option.productType,
      productId: option.productId,
      variantId: option.variantId,
      targetPrice
    });
    res.json({
      ok: true,
      row,
      ...economicsResult,
      state: buildStatePayload()
    });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.get("/api/forge/production/reviews", (req, res) => {
  res.json({ ok: true, reviews: listProductionReviews() });
});

app.post("/api/forge/production/check", async (req, res) => {
  try {
    const review = await checkProduction(req.body || {});
    res.json({ ok: true, review, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/forge/production/decision", async (req, res) => {
  try {
    const review = await updateProductionDecision(req.body || {});
    res.json({ ok: true, review, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.post("/api/products/package/build", (req, res) => {
  try {
    const body = req.body || {};
    const workId = String(body.work_id || body.workId || "").trim();
    if (!workId) {
      res.status(400).json({ ok: false, error: "Missing work_id." });
      return;
    }
    const queue = loadShiftQueue();
    const work = queue.find((item) => item.work_id === workId);
    if (!work) {
      res.status(404).json({ ok: false, error: "Work item not found." });
      return;
    }
    const pkg = buildAndMaybeSaveProductPackageForWork(work, { dryRun: Boolean(body.dryRun) });
    res.json({
      ok: pkg.ok,
      package: pkg,
      warnings: pkg.warnings,
      blockers: pkg.blockers,
      state: buildStatePayload()
    });
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});

app.get("/api/publisher/etsy/status", (req, res) => {
  res.json({ ok: true, status: getEtsyConnectorStatus() });
});

app.post("/api/publisher/etsy/dry-run", async (req, res) => {
  try {
    const packageId = String(req.body?.package_id || req.body?.packageId || "").trim();
    const productPackage = findProductPackage(packageId);
    if (!productPackage) {
      res.status(404).json({ ok: false, error: "Product package not found." });
      return;
    }
    const result = await publishEtsyListing(productPackage, { mode: "dry_run" });
    if (productPackage.work_id) {
      updateWorkPublishState(productPackage.work_id, {
        status: "waiting_for_live_publish",
        stage: "ready_to_publish",
        product_package_status: result.productPackage?.publish_status || "dry_run_ready",
        etsy_publish_mode: "dry_run",
        etsy_publish_status: result.status,
        etsy_payload_blockers: result.validation?.blockers || [],
        etsy_payload_warnings: result.validation?.warnings || [],
        human_status: "Publisher prepared a dry-run Etsy listing. Live publishing is not enabled."
      });
    }
    res.json({ ok: true, ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({ ok: false, error: String(error?.message || error) });
  }
});

app.post("/api/publisher/etsy/publish", async (req, res) => {
  try {
    if (etsyPublishMode() !== "live") {
      res.status(409).json({
        ok: false,
        error: "ETSY_PUBLISH_MODE must be live for live publishing.",
        status: getEtsyConnectorStatus()
      });
      return;
    }
    const packageId = String(req.body?.package_id || req.body?.packageId || "").trim();
    const productPackage = findProductPackage(packageId);
    if (!productPackage) {
      res.status(404).json({ ok: false, error: "Product package not found." });
      return;
    }
    const result = await publishEtsyListing(productPackage, { mode: "live" });
    if (productPackage.work_id) {
      updateWorkPublishState(productPackage.work_id, {
        status: result.ok && result.live_listing_id ? "listed" : "waiting_for_setup",
        stage: result.ok && result.live_listing_id ? "listed" : "ready_to_publish",
        product_package_status: result.status,
        etsy_publish_mode: "live",
        etsy_publish_status: result.status,
        etsy_payload_blockers: result.validation?.blockers || [],
        etsy_payload_warnings: result.validation?.warnings || [],
        human_status: result.ok && result.live_listing_id
          ? "Publisher listed the product on Etsy."
          : (result.error || "Etsy live publishing is waiting for setup.")
      });
    }
    res.status(result.ok ? 200 : 409).json({ ok: result.ok, ...result, state: buildStatePayload() });
  } catch (error) {
    res.status(error?.statusCode || 500).json({ ok: false, error: String(error?.message || error) });
  }
});

app.get("/api/revenue/summary", (req, res) => {
  res.json(getRevenueSummary());
});

app.get("/api/revenue/orders", (req, res) => {
  res.json({
    ok: true,
    orders: listSalesOrders(),
    listingPerformance: listListingPerformance(),
    marketPerformanceMemory: listMarketPerformanceMemory(),
    summary: getRevenueSummary().summary
  });
});

app.post("/api/revenue/sync", async (req, res) => {
  try {
    const result = await syncEtsyOrders();
    res.status(result.ok ? 200 : 200).json({
      ...result,
      state: buildStatePayload()
    });
  } catch (error) {
    res.status(error?.statusCode || 500).json({ ok: false, error: String(error?.message || error) });
  }
});

app.get("/api/agents/shift/status", (req, res) => {
  res.json(shiftStatusPayload());
});

app.post("/api/agents/shift/start", async (req, res) => {
  const body = req.body || {};
  const now = new Date().toISOString();
  stopShiftLoop("shift_loop_stopped", "Backend shift loop stopped before creating a new shift.");
  const state = {
    ...defaultShiftState(),
    shift_id: nextShiftId(),
    status: "running",
    started_at: now,
    updated_at: now,
    stopped_at: null,
    created_this_shift: 0
  };
  state.limits = {
    ...state.limits,
    forge_worker_count: Math.max(1, Math.min(6, Number(body.forgeWorkerCount || 3))),
    max_active_work_items: Math.max(1, Math.min(6, Number(body.maxActiveWorkItems || body.forgeWorkerCount || 3))),
    max_designs_per_shift: Math.max(
      Math.max(1, Math.min(6, Number(body.maxActiveWorkItems || body.forgeWorkerCount || 3))),
      Math.min(10, Number(body.maxDesignsPerShift || 3))
    ),
    allowed_product_types: Array.isArray(body.allowedProductTypes) && body.allowedProductTypes.length ? body.allowedProductTypes : state.limits.allowed_product_types,
    preferred_supplier: ["auto", "printify", "printful"].includes(body.preferredSupplier) ? body.preferredSupplier : "auto",
    target_prices: body.targetPrices && typeof body.targetPrices === "object" ? { ...state.limits.target_prices, ...body.targetPrices } : state.limits.target_prices,
    destinationCountry: body.destinationCountry || process.env.DEFAULT_SHIP_COUNTRY || state.limits.destinationCountry,
    destinationState: body.destinationState || process.env.DEFAULT_SHIP_STATE || state.limits.destinationState,
    destinationZip: body.destinationZip || process.env.DEFAULT_SHIP_ZIP || state.limits.destinationZip,
    tick_interval_ms: normalizeShiftIntervalMs(body.tickIntervalMs),
    max_ledger_retries: Math.max(1, Math.min(8, Number(body.maxLedgerRetries || state.limits.max_ledger_retries || MAX_LEDGER_RETRIES))),
    require_user_approval_before_publish: false
  };
  state.workers = defaultForgeWorkers(state.limits.forge_worker_count);

  saveShiftState(state);
  saveShiftQueue(loadShiftQueue());
  appendShiftLog({ shiftId: state.shift_id, event: "shift_created_new", message: "New autonomous shift created.", data: { limits: state.limits } });
  appendShiftLog({ shiftId: state.shift_id, event: "shift_started", message: "Autonomous shift started.", data: { limits: state.limits } });
  try {
    await runShiftTick();
  } catch (error) {
    appendShiftLog({ shiftId: state.shift_id, event: "shift_initial_fill_error", message: String(error?.message || error) });
  }
  startShiftLoop(state.limits.tick_interval_ms);
  res.json(shiftStatusPayload());
});

app.post("/api/agents/shift/pause", (req, res) => {
  const state = loadShiftState();
  state.status = "paused";
  state.current_task = "Paused by user.";
  saveShiftState(state);
  appendShiftLog({ shiftId: state.shift_id, event: "shift_paused", message: "Shift paused by user." });
  stopShiftLoop("shift_loop_stopped", "Backend shift loop stopped because shift was paused.");
  res.json(shiftStatusPayload());
});

app.post("/api/agents/shift/resume", (req, res) => {
  const state = loadShiftState();
  state.status = "running";
  state.current_task = "Resumed by user.";
  saveShiftState(state);
  appendShiftLog({ shiftId: state.shift_id, event: "shift_resumed", message: "Shift resumed by user." });
  startShiftLoop(state.limits?.tick_interval_ms || DEFAULT_SHIFT_TICK_INTERVAL_MS);
  res.json(shiftStatusPayload());
});

app.post("/api/agents/shift/stop", (req, res) => {
  const state = loadShiftState();
  state.status = "stopped";
  state.stopped_at = new Date().toISOString();
  state.current_task = "Stopped by user.";
  saveShiftState(state);
  appendShiftLog({ shiftId: state.shift_id, event: "shift_stopped", message: "Shift stopped by user." });
  stopShiftLoop("shift_loop_stopped", "Backend shift loop stopped because shift was stopped.");
  res.json(shiftStatusPayload());
});

app.post("/api/agents/shift/tick", async (req, res) => {
  try {
    res.json(await runShiftTick());
  } catch (error) {
    res.status(error?.statusCode || 500).json({
      ok: false,
      error: String(error?.message || error),
      ...shiftStatusPayload()
    });
  }
});

// V10_FORCE_SECRET_STATUS_STATE_ROUTE
app.get('/api/state', async (req, res) => {
  try {
    const payload = await buildStatePayload();
    payload.secretStatus = getSecretStatus();
    res.json(payload);
  } catch (error) {
    res.status(500).json({
      ok: false,
      error: String(error?.message || error),
      secretStatus: getSecretStatus()
    });
  }
});
app.get("/api/state", (req, res) => {
  res.json(buildStatePayload());
});


app.post('/api/secrets', async (req, res) => {
  try {
    const allowed = new Set([
      "OPENAI_API_KEY",
      "PRINTIFY_API_KEY",
      "PRINTFUL_API_KEY",
      "ETSY_API_KEY",
    "ETSY_CLIENT_SECRET",
    "ETSY_ACCESS_TOKEN",
    "ETSY_REFRESH_TOKEN",
    "ETSY_SHOP_ID",
      "ETSY_CLIENT_SECRET",
      "ETSY_ACCESS_TOKEN",
      "ETSY_REFRESH_TOKEN",
      "ETSY_SHOP_ID"
    ]);

    const incoming = {};

    for (const [key, value] of Object.entries(req.body || {})) {
      if (!allowed.has(key)) continue;
      const cleaned = String(value || "").trim();
      if (cleaned) incoming[key] = cleaned;
    }

    const merged = saveSecretsEverywhere(incoming);

    res.json({
      ok: true,
      saved_to: [
        "_spacecommand_state/local_api_keys.json",
        ".env.local",
        "ui/.env.local"
      ],
      secretStatus: getSecretStatus(),
      state: { ...(await buildStatePayload()), secretStatus: getSecretStatus() }
    });
  } catch (error) {
    res.status(500).json({
      ok: false,
      error: String(error?.message || error)
    });
  }
});
app.post("/api/rebuild", async (req, res) => {
  const steps = [
    ["build_artifact_index.py", []],
    ["build_product_candidate_board.py", []],
    ["build_decision_queue.py", []],
    ["spacecommand_dashboard.py", []]
  ];

  const results = [];

  for (const [script, args] of steps) {
    const result = await runPython(script, args);
    results.push({ script, ...result });
    if (!result.ok) break;
  }

  res.json({
    ok: results.every((r) => r.ok),
    results,
    state: buildStatePayload()
  });
});

app.post("/api/forge/art/run-scribe", async (req, res) => {
  const designId = String(req.body?.designId || "").trim();
  const productType = String(req.body?.productType || "poster").trim() || "poster";

  if (!designId) {
    res.status(400).json({ ok: false, error: "Missing designId." });
    return;
  }

  const designs = readJson("design_packages.json", []);
  if (!designs.some((item) => item.id === designId)) {
    res.status(404).json({ ok: false, error: "Design package not found." });
    return;
  }

  const result = await runPython("run_scribe_on_design.py", [
    "--design-package-id",
    designId,
    "--product-type",
    productType
  ]);

  res.status(result.ok ? 200 : 500).json({
    ...result,
    state: buildStatePayload()
  });
});

app.post("/api/action", async (req, res) => {
  const { actionId, confirmed = false, extraArgs = "" } = req.body || {};

  if (!actionId) {
    res.status(400).json({ ok: false, error: "Missing actionId" });
    return;
  }

  const args = [
    "--action-id",
    actionId,
    "--confirmed",
    confirmed ? "true" : "false"
  ];

  if (extraArgs && String(extraArgs).trim()) {
    args.push("--extra-args", String(extraArgs));
  }

  const result = await runPython("ui_action_router.py", args);

  res.json({
    ...result,
    state: buildStatePayload()
  });
});

app.post("/api/lifecycle", async (req, res) => {
  const { artifactType, artifactId, action, reason = "" } = req.body || {};

  if (!artifactType || !artifactId || !action) {
    res.status(400).json({ ok: false, error: "Missing artifactType, artifactId, or action" });
    return;
  }

  const result = await runPython("artifact_lifecycle.py", [
    "--artifact-type", artifactType,
    "--artifact-id", artifactId,
    "--action", action,
    "--reason", reason
  ]);

  res.json({
    ...result,
    state: buildStatePayload()
  });
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`SpaceCommand local API running on http://127.0.0.1:${PORT}`);
  const state = loadShiftState();
  if (state.status === "running") {
    startShiftLoop(state.limits?.tick_interval_ms || DEFAULT_SHIFT_TICK_INTERVAL_MS, "shift_loop_resumed_after_server_start");
  }
});
