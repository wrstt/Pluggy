import { proxyJson } from "../../_proxy";
import { requireAdmin } from "../../_auth";

export async function POST(request: Request) {
  const denial = await requireAdmin(request);
  if (denial) return denial;
  const body = await request.text();
  return proxyJson(request, "/api/link-sources/import", {
    method: "POST",
    body
  });
}
