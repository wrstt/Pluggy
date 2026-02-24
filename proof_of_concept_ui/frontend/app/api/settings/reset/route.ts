import { proxyJson } from "../../_proxy";
import { requireAdmin } from "../../_auth";

export async function POST(request: Request) {
  const denial = await requireAdmin(request);
  if (denial) return denial;
  return proxyJson(request, "/api/settings/reset", { method: "POST" });
}
