import { proxyJson } from "../_proxy";

export async function GET(request: Request) {
  return proxyJson(request, "/api/profiles");
}

export async function POST(request: Request) {
  return proxyJson(request, "/api/profiles", { method: "POST" });
}
