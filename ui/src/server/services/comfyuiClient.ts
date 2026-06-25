import { saveAttemptMetadata, savePngBytes, sanitizeFilename } from "./artStorage";
import { buildSimpleTextToImageWorkflow } from "./comfyuiWorkflow";

declare const process: {
  env: Record<string, string | undefined>;
};

export type ForgeLocalArtRequest = {
  prompt: string;
  negativePrompt?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
  seed?: number;
  title?: string;
  productType?: string;
};

export type ForgeLocalArtResult = {
  ok: boolean;
  provider: "comfyui";
  prompt: string;
  negativePrompt: string;
  localImagePath?: string;
  publicImageUrl?: string;
  metadataPath?: string;
  promptId?: string;
  seed?: number;
  error?: string;
};

type ComfyImageOutput = {
  filename: string;
  subfolder?: string;
  type?: string;
};

const DEFAULT_NEGATIVE_PROMPT =
  "copyrighted character, logo, brand name, celebrity, blurry, low quality, watermark, signature, unreadable text, trademark, messy background, extra limbs, deformed hands";

function baseUrl(): string {
  return (process.env.COMFYUI_BASE_URL || "http://127.0.0.1:8188").replace(/\/+$/, "");
}

function isLocalComfyUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return ["127.0.0.1", "localhost", "::1"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

function numberFromEnv(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = 8000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function checkComfyUiHealth(): Promise<{ ok: boolean; provider: "comfyui"; baseUrl: string; error?: string }> {
  const url = baseUrl();
  if (!isLocalComfyUrl(url)) {
    return {
      ok: false,
      provider: "comfyui",
      baseUrl: url,
      error: "ComfyUI must stay local. Use http://127.0.0.1:8188 or localhost.",
    };
  }
  try {
    const response = await fetchWithTimeout(`${url}/system_stats`, {}, 4000);
    if (!response.ok) {
      return { ok: false, provider: "comfyui", baseUrl: url, error: `ComfyUI responded with HTTP ${response.status}.` };
    }
    return { ok: true, provider: "comfyui", baseUrl: url };
  } catch {
    return {
      ok: false,
      provider: "comfyui",
      baseUrl: url,
      error: "ComfyUI is not reachable. Start ComfyUI locally on http://127.0.0.1:8188, then try again.",
    };
  }
}

function findSavedImage(history: unknown, promptId: string): ComfyImageOutput | null {
  const root = history as Record<string, any>;
  const promptHistory = root?.[promptId] || root;
  const outputs = promptHistory?.outputs;
  if (!outputs || typeof outputs !== "object") return null;

  for (const output of Object.values(outputs) as Array<any>) {
    const images = output?.images;
    if (Array.isArray(images) && images.length) {
      const first = images[0];
      if (first?.filename) return first;
    }
  }

  return null;
}

export async function generateForgeLocalArt(input: ForgeLocalArtRequest): Promise<ForgeLocalArtResult> {
  const prompt = String(input.prompt || "").trim();
  const negativePrompt = String(input.negativePrompt || DEFAULT_NEGATIVE_PROMPT).trim();
  const seed = Number.isFinite(Number(input.seed)) ? Number(input.seed) : Math.floor(Math.random() * 1_000_000_000);
  const width = Number(input.width || numberFromEnv("FORGE_DEFAULT_WIDTH", 1024));
  const height = Number(input.height || numberFromEnv("FORGE_DEFAULT_HEIGHT", 1024));
  const steps = Number(input.steps || numberFromEnv("FORGE_DEFAULT_STEPS", 28));
  const cfg = Number(input.cfg || numberFromEnv("FORGE_DEFAULT_CFG", 7));
  const checkpointName = process.env.COMFYUI_CHECKPOINT_NAME || "sd_xl_base_1.0.safetensors";
  const filenameStem = sanitizeFilename(`forge-${Date.now()}-${input.productType || "product"}-${input.title || "local-art"}`);

  if (!prompt) {
    return { ok: false, provider: "comfyui", prompt, negativePrompt, seed, error: "Prompt is required." };
  }

  const health = await checkComfyUiHealth();
  if (!health.ok) {
    const metadataPath = saveAttemptMetadata(filenameStem, {
      provider: "comfyui",
      prompt,
      negativePrompt,
      seed,
      title: input.title,
      productType: input.productType,
      width,
      height,
      steps,
      cfg,
      checkpointName,
      status: "failed",
      error: health.error,
      createdAt: new Date().toISOString(),
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
      filenamePrefix: filenameStem,
    });

    const queueResponse = await fetchWithTimeout(`${baseUrl()}/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: workflow }),
    }, 10000);

    if (!queueResponse.ok) {
      throw new Error(`ComfyUI rejected the workflow with HTTP ${queueResponse.status}.`);
    }

    const queued = await queueResponse.json() as { prompt_id?: string };
    const promptId = queued.prompt_id;
    if (!promptId) throw new Error("ComfyUI did not return a prompt_id.");

    let savedImage: ComfyImageOutput | null = null;
    const deadline = Date.now() + 180000;

    while (Date.now() < deadline) {
      await delay(1500);
      const historyResponse = await fetchWithTimeout(`${baseUrl()}/history/${encodeURIComponent(promptId)}`, {}, 8000);
      if (!historyResponse.ok) continue;
      const history = await historyResponse.json();
      savedImage = findSavedImage(history, promptId);
      if (savedImage) break;
    }

    if (!savedImage) {
      throw new Error("ComfyUI did not finish an image before the timeout.");
    }

    const params = new URLSearchParams({
      filename: savedImage.filename,
      subfolder: savedImage.subfolder || "",
      type: savedImage.type || "output",
    });
    const imageResponse = await fetchWithTimeout(`${baseUrl()}/view?${params.toString()}`, {}, 30000);
    if (!imageResponse.ok) {
      throw new Error(`Could not download ComfyUI image. HTTP ${imageResponse.status}.`);
    }

    const bytes = await imageResponse.arrayBuffer();
    const stored = savePngBytes(filenameStem, bytes);
    const metadataPath = saveAttemptMetadata(filenameStem, {
      provider: "comfyui",
      prompt,
      negativePrompt,
      promptId,
      seed,
      title: input.title,
      productType: input.productType,
      width,
      height,
      steps,
      cfg,
      checkpointName,
      comfyImage: {
        filename: savedImage.filename,
        subfolder: savedImage.subfolder || "",
        type: savedImage.type || "output",
      },
      status: "completed",
      createdAt: new Date().toISOString(),
    });

    return {
      ok: true,
      provider: "comfyui",
      prompt,
      negativePrompt,
      localImagePath: stored.localImagePath,
      publicImageUrl: stored.publicImageUrl,
      metadataPath,
      promptId,
      seed,
    };
  } catch (error) {
    const message = String((error as Error)?.message || error);
    const metadataPath = saveAttemptMetadata(filenameStem, {
      provider: "comfyui",
      prompt,
      negativePrompt,
      seed,
      title: input.title,
      productType: input.productType,
      width,
      height,
      steps,
      cfg,
      checkpointName,
      status: "failed",
      error: message,
      createdAt: new Date().toISOString(),
    });
    return { ok: false, provider: "comfyui", prompt, negativePrompt, metadataPath, seed, error: message };
  }
}
