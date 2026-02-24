import { proxyJson } from "../../../_proxy";

export async function POST(request: Request) {
  return proxyJson(request, "/api/session/rd/connect", { method: "POST" });
}
