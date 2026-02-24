import { proxyJson } from "../../../_proxy";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return proxyJson(request, `/api/search/jobs/${encodeURIComponent(id)}`);
}
