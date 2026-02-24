import { proxyJson } from "../_proxy";
import { requireAdmin } from "../_auth";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const enabledOnly = searchParams.get("enabled_only") === "1";
  const exportMode = searchParams.get("export") === "1";
  const params = new URLSearchParams();
  if (enabledOnly) params.set("enabled_only", "true");
  if (exportMode) params.set("export", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return proxyJson(request, `/api/link-sources${suffix}`);
}

export async function POST(request: Request) {
  const denial = await requireAdmin(request);
  if (denial) return denial;
  const body = await request.text();
  return proxyJson(request, "/api/link-sources", {
    method: "POST",
    body
  });
}
