import { generateForgeLocalArt } from "../../../../../server/services/comfyuiClient";

const DEFAULT_PROMPT =
  "bold vector sticker design of a raccoon wearing a tiny welding helmet, holding a coffee mug, clean commercial t-shirt graphic, centered composition, thick outline, high contrast, transparent background style, no text";

const DEFAULT_NEGATIVE_PROMPT =
  "copyrighted character, logo, brand name, celebrity, blurry, low quality, watermark, signature, unreadable text, trademark, messy background, extra limbs, deformed hands";

export async function POST(request: Request): Promise<Response> {
  let body: {
    prompt?: string;
    negativePrompt?: string;
    title?: string;
    productType?: string;
  } = {};

  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const result = await generateForgeLocalArt({
    prompt: body.prompt || DEFAULT_PROMPT,
    negativePrompt: body.negativePrompt || DEFAULT_NEGATIVE_PROMPT,
    title: body.title || "Forge local test design",
    productType: body.productType || "sticker",
  });

  return Response.json(result, { status: result.ok ? 200 : 503 });
}
