import { proxyJson } from "../../_proxy";

export async function POST(request: Request) {
  return proxyJson(request, "/api/profiles/select", { method: "POST" });
}

