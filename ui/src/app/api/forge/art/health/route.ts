import { checkComfyUiHealth } from "../../../../../server/services/comfyuiClient";

export async function GET(): Promise<Response> {
  const health = await checkComfyUiHealth();
  return Response.json(health);
}
