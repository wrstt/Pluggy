const encoder = new TextEncoder();
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
export type SessionRole = "admin" | "user";

function getSecret() {
  return process.env.PLATSWAP_AUTH_SECRET || "platswap-local-auth-secret";
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function fromHex(input: string): Uint8Array {
  if (input.length % 2 !== 0) return new Uint8Array();
  const out = new Uint8Array(input.length / 2);
  for (let i = 0; i < input.length; i += 2) {
    out[i / 2] = parseInt(input.slice(i, i + 2), 16);
  }
  return out;
}

async function sign(message: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(getSecret()), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return toHex(new Uint8Array(signature));
}

function timingSafeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a[i] ^ b[i];
  }
  return diff === 0;
}

async function verifySignature(message: string, signature: string): Promise<boolean> {
  const expected = await sign(message);
  return timingSafeEqual(fromHex(expected), fromHex(signature));
}

export async function createAuthToken(username: string, role: SessionRole): Promise<string> {
  const normalized = username.trim().toLowerCase();
  const safeRole: SessionRole = role === "admin" ? "admin" : "user";
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const body = `${normalized}.${safeRole}.${exp}`;
  const sig = await sign(body);
  return `${body}.${sig}`;
}

export async function verifyAuthToken(token: string): Promise<{ valid: boolean; username?: string; role?: SessionRole }> {
  const parts = token.split(".");
  if (parts.length !== 4) return { valid: false };
  const [username, roleRaw, expRaw, sig] = parts;
  const role: SessionRole = roleRaw === "admin" ? "admin" : "user";
  const exp = Number(expRaw);
  if (!username || !Number.isFinite(exp)) return { valid: false };
  if (exp < Math.floor(Date.now() / 1000)) return { valid: false };
  const body = `${username}.${role}.${exp}`;
  const ok = await verifySignature(body, sig);
  if (!ok) return { valid: false };
  return { valid: true, username, role };
}
