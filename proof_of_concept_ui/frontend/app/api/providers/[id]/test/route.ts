import { proxyJson } from "../../../_proxy";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  const { id } = await params;
  return proxyJson(request, `/api/providers/${encodeURIComponent(id)}/test`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}
