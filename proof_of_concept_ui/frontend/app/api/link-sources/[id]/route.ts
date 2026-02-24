import { proxyJson } from "../../_proxy";
import { requireAdmin } from "../../_auth";

export async function DELETE(request: Request, context: { params: Promise<{ id: string }> }) {
  const denial = await requireAdmin(request);
  if (denial) return denial;
  const { id } = await context.params;
  return proxyJson(request, `/api/link-sources/${encodeURIComponent(id)}`, {
    method: "DELETE"
  });
}
