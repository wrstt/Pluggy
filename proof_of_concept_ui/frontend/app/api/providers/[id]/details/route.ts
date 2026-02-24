import { proxyJson } from "../../../_proxy";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJson(request, `/api/providers/${encodeURIComponent(id)}/details`);
}
