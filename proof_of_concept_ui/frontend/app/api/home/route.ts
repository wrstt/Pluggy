import { proxyJson } from "../_proxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const force = searchParams.get("forceRefresh");
  const suffix = force === "1" ? "?force_refresh=true" : "";
  return proxyJson(request, `/api/home${suffix}`);
}
