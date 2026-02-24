import { proxyJson } from "../../../_proxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const poll = searchParams.get("poll") === "1";
  return proxyJson(request, `/api/session/rd/status${poll ? "?poll=true" : ""}`);
}
