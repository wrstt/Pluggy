import { proxyJson } from "../_proxy";

export async function POST(request: Request) {
  const body = await request.json();
  return proxyJson(request, "/api/rd", {
    method: "POST",
    body: JSON.stringify(body)
  });
}
