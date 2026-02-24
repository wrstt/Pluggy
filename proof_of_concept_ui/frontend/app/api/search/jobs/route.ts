import { proxyJson } from "../../_proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  return proxyJson(request, "/api/search/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

