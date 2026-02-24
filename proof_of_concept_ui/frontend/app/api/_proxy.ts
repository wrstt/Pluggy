import { NextResponse } from "next/server";

const DEFAULT_API_BASE = "http://127.0.0.1:8787";

export function getApiBaseUrl() {
  return process.env.PLUGGY_API_BASE_URL ?? DEFAULT_API_BASE;
}

export async function proxyJson(request: Request, path: string, init?: RequestInit) {
  const cookie = request.headers.get("cookie") || "";
  const method = String(init?.method ?? request.method ?? "GET").toUpperCase();

  // Most of our API routes just proxy through; forward the body by default for non-GET requests.
  // This avoids subtle 422s where the backend expects JSON but receives an empty body.
  let body: BodyInit | undefined = init?.body as BodyInit | undefined;
  if (!body && method !== "GET" && method !== "HEAD") {
    const text = await request.text().catch(() => "");
    if (text) body = text;
  }

  const headers: Record<string, string> = {};
  const requestContentType = request.headers.get("content-type") || "";
  if (requestContentType) headers["Content-Type"] = requestContentType;
  else headers["Content-Type"] = "application/json";
  if (cookie) headers["cookie"] = cookie;
  for (const [k, v] of Object.entries((init?.headers as Record<string, string>) ?? {})) {
    headers[k] = v;
  }

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      method,
      body,
      headers,
      cache: "no-store"
    });
  } catch (err: any) {
    const message = err?.cause?.message || err?.message || "Upstream API request failed";
    return NextResponse.json({ error: { code: "UPSTREAM_UNREACHABLE", message } }, { status: 502 });
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { error: { code: "UPSTREAM_ERROR", message: await response.text() } };

  if (!response.ok) {
    // Preserve upstream `{error:{code,message}}` shape so the UI can react to specific codes.
    if (payload?.error?.code) {
      return NextResponse.json(payload, { status: response.status });
    }
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : payload?.error?.message ?? "Upstream API request failed";
    return NextResponse.json({ error: { code: "UPSTREAM_ERROR", message: detail } }, { status: response.status });
  }

  const out = NextResponse.json(payload);
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) {
    out.headers.set("set-cookie", setCookie);
  }
  return out;
}
