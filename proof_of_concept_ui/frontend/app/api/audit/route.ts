import { proxyJson } from "../_proxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") ?? "200";
  return proxyJson(request, `/api/audit?limit=${encodeURIComponent(limit)}`);
}
