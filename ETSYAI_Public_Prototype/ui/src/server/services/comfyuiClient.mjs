import fs from "fs";
import path from "path";
import { buildSimpleTextToImageWorkflow } from "./comfyuiWorkflow.mjs";

const ROOT = path.resolve(process.cwd(), "..");
const GENERATED_ART_DIR = path.resolve(process.cwd(), process.env.FORGE_ART_OUTPUT_DIR || "./data/generated-art");
const DEFAULT_NEGATIVE_PROMPT = "copyrighted character, brand logo, celebrity, team logo, trademarked slogan, watermark, signature, blurry, low quality, unreadable text, messy background, extra limbs, deformed hands";

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) fs.mkdirSync(dirPath, { recursive: true });
}

function baseUrl() {
  return String(process.env.COMFYUI_BASE_URL || "http://127.0.0.1:8188").replace(/\/+$/, "");
}

function isLocalComfyUrl(url) {
  try {
    const parsed = new URL(url);
    return ["127.0.0.1", "localhost", "::1"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

function sanitizeFilename(value) {
  return String(value || "forge-art")
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/-+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 96) || "forge-art";
}

function numberFromEnv(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, init = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function getForgeArtHealth() {
  const url = baseUrl();
  const checkedAt = new Date().toISOString();
  const checkpointName = process.env.COMFYUI_CHECKPOINT_NAME || "sd_xl_base_1.0.safetensors";
  if (!isLocalComfyUrl(url)) {
    return {
      ok: false,
      provider: "comfyui",
      baseUrl: url,
      reason: "ComfyUI must stay local. Use http://127.0.0.1:8188 or localhost.",
      checkpointName,
      checkedAt
    };
  }
  try {
    const response = await fetchWithTimeout(`${url}/system_stats`, {}, 4000);
    if (!response.ok) {
      return {
        ok: false,
        provider: "comfyui",
        baseUrl: url,
        reason: `ComfyUI responded with HTTP ${response.status}.`,
        checkpointName,
        checkedAt
      };
    }
    return { ok: true, provider: "comfyui", baseUrl: url, reason: "ComfyUI is reachable.", checkpointName, checkedAt };
  } catch {
    return {
      ok: false,
      provider: "comfyui",
      baseUrl: url,
      reason: "ComfyUI is not reachable. Start ComfyUI locally on http://127.0.0.1:8188, then try again.",
      checkpointName,
      checkedAt
    };
  }
}

export async function checkComfyUiHealth() {
  return getForgeArtHealth();
}

function findSavedImage(history, promptId) {
  const promptHistory = history?.[promptId] || history;
  const outputs = promptHistory?.outputs;
  if (!outputs || typeof outputs !== "object") return null;
  for (const output of Object.values(outputs)) {
    if (Array.isArray(output?.images) && output.images.length && output.images[0]?.filename) return output.images[0];
  }
  return null;
}

function writeMetadata(filenameStem, data) {
  ensureDir(GENERATED_ART_DIR);
  const metadataPath = path.join(GENERATED_ART_DIR, `${filenameStem}.json`);
  fs.writeFileSync(metadataPath, JSON.stringify(data, null, 2), "utf8");
  return metadataPath;
}

function writePng(filenameStem, bytes) {
  ensureDir(GENERATED_ART_DIR);
  const localImagePath = path.join(GENERATED_ART_DIR, `${filenameStem}.png`);
  fs.writeFileSync(localImagePath, Buffer.from(bytes));
  return {
    localImagePath,
    publicImageUrl: `/generated-art/${path.basename(localImagePath)}`
  };
}

export async function generateForgeLocalArt(input = {}) {
  const prompt = String(input.prompt || "").trim();
  const negativePrompt = String(input.negativePrompt || DEFAULT_NEGATIVE_PROMPT).trim();
  const seed = Number.isFinite(Number(input.seed)) ? Number(input.seed) : Math.floor(Math.random() * 1000000000);
  const width = Number(input.width || numberFromEnv("FORGE_DEFAULT_WIDTH", 1024));
  const height = Number(input.height || numberFromEnv("FORGE_DEFAULT_HEIGHT", 1024));
  const steps = Number(input.steps || numberFromEnv("FORGE_DEFAULT_STEPS", 28));
  const cfg = Number(input.cfg || numberFromEnv("FORGE_DEFAULT_CFG", 7));
  const checkpointName = process.env.COMFYUI_CHECKPOINT_NAME || "sd_xl_base_1.0.safetensors";
  const filenameStem = sanitizeFilename(`forge-${Date.now()}-${input.productType || "product"}-${input.title || "local-art"}`);

  if (!prompt) return { ok: false, provider: "comfyui", prompt, negativePrompt, seed, error: "Prompt is required." };
  const health = await getForgeArtHealth();
  if (!health.ok) {
    const metadataPath = writeMetadata(filenameStem, { provider: "comfyui", prompt, negativePrompt, seed, title: input.title, productType: input.productType, width, height, steps, cfg, checkpointName, status: "failed", error: health.reason, createdAt: new Date().toISOString() });
    return { ok: false, provider: "comfyui", prompt, negativePrompt, metadataPath, seed, error: health.reason };
  }

  try {
    const workflow = buildSimpleTextToImageWorkflow({ prompt, negativePrompt, width, height, steps, cfg, seed, checkpointName, filenamePrefix: filenameStem });
    const queueResponse = await fetchWithTimeout(`${baseUrl()}/prompt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: workflow }) }, 10000);
    if (!queueResponse.ok) throw new Error(`ComfyUI rejected the workflow with HTTP ${queueResponse.status}.`);
    const queued = await queueResponse.json();
    const promptId = queued?.prompt_id;
    if (!promptId) throw new Error("ComfyUI did not return a prompt_id.");

    let savedImage = null;
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      await delay(1500);
      const historyResponse = await fetchWithTimeout(`${baseUrl()}/history/${encodeURIComponent(promptId)}`, {}, 8000);
      if (!historyResponse.ok) continue;
      savedImage = findSavedImage(await historyResponse.json(), promptId);
      if (savedImage) break;
    }
    if (!savedImage) throw new Error("ComfyUI did not finish an image before the timeout.");

    const params = new URLSearchParams({ filename: savedImage.filename, subfolder: savedImage.subfolder || "", type: savedImage.type || "output" });
    const imageResponse = await fetchWithTimeout(`${baseUrl()}/view?${params.toString()}`, {}, 30000);
    if (!imageResponse.ok) throw new Error(`Could not download ComfyUI image. HTTP ${imageResponse.status}.`);
    const stored = writePng(filenameStem, await imageResponse.arrayBuffer());
    const metadataPath = writeMetadata(filenameStem, { provider: "comfyui", prompt, negativePrompt, promptId, seed, title: input.title, productType: input.productType, width, height, steps, cfg, checkpointName, file_type: "png", status: "completed", root: ROOT, createdAt: new Date().toISOString() });
    return { ok: true, provider: "comfyui", prompt, negativePrompt, ...stored, metadataPath, promptId, seed };
  } catch (error) {
    const message = String(error?.message || error);
    const metadataPath = writeMetadata(filenameStem, { provider: "comfyui", prompt, negativePrompt, seed, title: input.title, productType: input.productType, width, height, steps, cfg, checkpointName, file_type: "png", status: "failed", error: message, createdAt: new Date().toISOString() });
    return { ok: false, provider: "comfyui", prompt, negativePrompt, metadataPath, seed, error: message };
  }
}
