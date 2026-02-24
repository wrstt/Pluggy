import { proxyJson } from "../_proxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status");
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return proxyJson(request, `/api/transfers${suffix}`);
}

export async function POST(request: Request) {
  const body = await request.json();
  return proxyJson(request, "/api/transfers", {
    method: "POST",
    body: JSON.stringify(body)
  });
}
