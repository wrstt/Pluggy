import { readFile } from "node:fs/promises";
import path from "node:path";

export type AuthUser = {
  username: string;
  password: string;
  role: "admin" | "user";
};

type UserDbFile = {
  users?: AuthUser[];
};

// Keep the repo free of personal credentials. An empty fallback triggers bootstrap signup.
const FALLBACK_USERS: AuthUser[] = [];

const USER_DB_PATH = path.join(process.cwd(), "data", "auth-users.json");

export async function loadUsers(): Promise<AuthUser[]> {
  try {
    const raw = await readFile(USER_DB_PATH, "utf8");
    const parsed = JSON.parse(raw) as UserDbFile;
    const users = Array.isArray(parsed.users) ? parsed.users : [];
    const normalized: AuthUser[] = users
      .map((u) => ({
        username: String(u.username ?? "").trim().toLowerCase(),
        password: String(u.password ?? ""),
        role: (String((u as { role?: string }).role ?? "user").trim().toLowerCase() === "admin" ? "admin" : "user") as
          | "admin"
          | "user"
      }))
      .filter((u) => u.username.length > 0 && u.password.length > 0);
    return normalized.length ? normalized : FALLBACK_USERS;
  } catch {
    return FALLBACK_USERS;
  }
}

export async function verifyUser(username: string, password: string): Promise<boolean> {
  const user = await findUser(username, password);
  return Boolean(user);
}

export async function findUser(username: string, password: string): Promise<AuthUser | null> {
  const users = await loadUsers();
  const normalized = username.trim().toLowerCase();
  return users.find((u) => u.username === normalized && u.password === password) ?? null;
}
