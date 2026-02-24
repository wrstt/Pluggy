import { proxyJson } from "../_proxy";
import { requireAdmin } from "../_auth";

export async function GET(request: Request) {
  return proxyJson(request, "/api/settings");
}

export async function PATCH(request: Request) {
  const denial = await requireAdmin(request);
  if (denial) return denial;
  const body = await request.json();
  return proxyJson(request, "/api/settings", {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}
