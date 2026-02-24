import { proxyJson } from "../../../_proxy";
import { requireAdmin } from "../../../_auth";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const denial = await requireAdmin(request);
  if (denial) return denial;
  const body = await request.json();
  const { id } = await params;
  return proxyJson(request, `/api/providers/${encodeURIComponent(id)}/toggle`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}
