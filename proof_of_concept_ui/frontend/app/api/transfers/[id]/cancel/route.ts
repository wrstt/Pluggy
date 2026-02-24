import { proxyJson } from "../../../_proxy";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJson(request, `/api/transfers/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}
