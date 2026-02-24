import { NextResponse } from "next/server";
import { verifyAuthToken } from "@/lib/auth/token";

function readAuthCookie(request: Request): string {
  const cookie = request.headers.get("cookie") || "";
  const authCookie = cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("platswap_auth="));
  return authCookie ? decodeURIComponent(authCookie.split("=").slice(1).join("=")) : "";
}

export async function requireAdmin(request: Request): Promise<NextResponse | null> {
  const token = readAuthCookie(request);
  const verified = await verifyAuthToken(token);
  if (!verified.valid) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Login required" } }, { status: 401 });
  }
  if (verified.role !== "admin") {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Admin role required" } }, { status: 403 });
  }
  const expectedPin = (process.env.PLATSWAP_ADMIN_PIN || "").trim();
  if (expectedPin) {
    const submittedPin = (request.headers.get("x-platswap-admin-pin") || "").trim();
    if (!submittedPin || submittedPin !== expectedPin) {
      return NextResponse.json({ error: { code: "FORBIDDEN", message: "Admin PIN required" } }, { status: 403 });
    }
  }
  return null;
}
