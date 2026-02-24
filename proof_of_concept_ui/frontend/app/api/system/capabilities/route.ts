import { proxyJson } from "../../_proxy";

export async function GET(request: Request) {
  return proxyJson(request, "/api/system/capabilities");
}
