declare const process: {
  cwd(): string;
  env: Record<string, string | undefined>;
};
declare const Buffer: {
  from(value: ArrayBuffer | Uint8Array): Uint8Array;
};
declare function require(name: string): any;

const fs = require("node:fs");
const path = require("node:path");

export type StoredArtMetadata = {
  provider: "comfyui";
  prompt: string;
  negativePrompt: string;
  promptId?: string;
  seed: number;
  title?: string;
  productType?: string;
  width: number;
  height: number;
  steps: number;
  cfg: number;
  checkpointName: string;
  comfyImage?: {
    filename: string;
    subfolder: string;
    type: string;
  };
  status: "completed" | "failed";
  error?: string;
  createdAt: string;
};

export type StoredArtResult = {
  localImagePath?: string;
  publicImageUrl?: string;
  metadataPath: string;
};

export function getArtOutputDir(): string {
  const configured = process.env.FORGE_ART_OUTPUT_DIR || "./data/generated-art";
  const resolved = path.resolve(process.cwd(), configured);
  fs.mkdirSync(resolved, { recursive: true });
  return resolved;
}

export function sanitizeFilename(value: string): string {
  return String(value || "forge-art")
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/-+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 96) || "forge-art";
}

export function assertInsideArtDir(candidatePath: string): string {
  const base = getArtOutputDir();
  const resolved = path.resolve(candidatePath);
  const relative = path.relative(base, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Blocked path traversal outside generated-art folder.");
  }
  return resolved;
}

export function publicUrlFor(filename: string): string {
  return `/api/generated-art/${encodeURIComponent(filename)}`;
}

export function saveAttemptMetadata(filenameStem: string, metadata: StoredArtMetadata): string {
  const safeStem = sanitizeFilename(filenameStem);
  const metadataPath = assertInsideArtDir(path.join(getArtOutputDir(), `${safeStem}.json`));
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), "utf8");
  return metadataPath;
}

export function savePngBytes(filenameStem: string, bytes: ArrayBuffer | Uint8Array): { localImagePath: string; publicImageUrl: string } {
  const safeStem = sanitizeFilename(filenameStem);
  const imagePath = assertInsideArtDir(path.join(getArtOutputDir(), `${safeStem}.png`));
  const buffer = bytes instanceof Uint8Array ? Buffer.from(bytes) : Buffer.from(bytes);
  fs.writeFileSync(imagePath, buffer);
  return {
    localImagePath: imagePath,
    publicImageUrl: publicUrlFor(path.basename(imagePath)),
  };
}

export function resolveGeneratedArtFile(filename: string): string | null {
  const safe = sanitizeFilename(path.basename(filename || ""));
  if (!safe || !/\.(png|json)$/i.test(safe)) return null;
  const filePath = assertInsideArtDir(path.join(getArtOutputDir(), safe));
  if (!fs.existsSync(filePath)) return null;
  return filePath;
}
