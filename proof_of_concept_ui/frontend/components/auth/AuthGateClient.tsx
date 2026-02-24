"use client";

import { useEffect, useMemo, useState } from "react";

export function AuthGateClient({ nextPath }: { nextPath: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [needsBootstrap, setNeedsBootstrap] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);
  const [intent, setIntent] = useState<"login" | "signup">("login");

  const mode = useMemo(() => {
    if (needsBootstrap === null) return "unknown";
    return needsBootstrap ? "bootstrap" : "login";
  }, [needsBootstrap]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch("/api/auth/status", { cache: "no-store" });
        const payload = await resp.json().catch(() => ({}));
        if (cancelled) return;
        setNeedsBootstrap(Boolean(payload?.needsBootstrap));
      } catch {
        if (!cancelled) setNeedsBootstrap(false);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    let redirected = false;
    try {
      const endpoint =
        mode === "bootstrap" ? "/api/auth/bootstrap" : intent === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 12000);
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: controller.signal
      });
      clearTimeout(timer);

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail ?? payload?.error?.message ?? "Login failed");
      }

      const statusResponse = await fetch("/api/auth/status", { cache: "no-store" });
      const statusPayload = await statusResponse.json().catch(() => ({}));
      if (!statusResponse.ok || !statusPayload?.authenticated) {
        throw new Error("Login session was not established. Please try again.");
      }

      redirected = true;
      const hasProfile = Boolean(statusPayload?.profileId);
      if (!hasProfile) {
        window.location.assign("/profiles");
      } else {
        window.location.assign(nextPath || "/");
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setError("Login request timed out. Please try again.");
      } else {
        setError(err instanceof Error ? err.message : "Login failed");
      }
    } finally {
      if (!redirected) {
        setBusy(false);
      }
    }
  }

  return (
    <main className="mx-auto mt-24 max-w-md rounded-2xl border border-white/20 bg-white/10 p-6 shadow-[0_14px_40px_rgba(4,8,20,0.55)] backdrop-blur-2xl">
      <h1 className="text-2xl font-semibold">Pluggy</h1>
      {checking ? (
        <p className="mt-1 text-sm text-zinc-300">Checking setup…</p>
      ) : mode === "bootstrap" ? (
        <p className="mt-1 text-sm text-zinc-300">Create the first admin account for this Pluggy install.</p>
      ) : (
        <p className="mt-1 text-sm text-zinc-300">
          {intent === "signup" ? "Create a new account for this Pluggy install." : "Sign in with your username and password."}
        </p>
      )}
      <form className="mt-4 space-y-3" onSubmit={submit}>
        <input
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="Username"
          autoComplete="username"
          className="w-full rounded-md border border-white/20 bg-black/30 px-3 py-2"
        />
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          className="w-full rounded-md border border-white/20 bg-black/30 px-3 py-2"
        />
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
        <button
          type="submit"
          disabled={busy || checking || mode === "unknown"}
          className="w-full rounded-md bg-[var(--accent-primary)] px-3 py-2 font-semibold text-black disabled:opacity-60"
        >
          {busy ? "Unlocking…" : mode === "bootstrap" ? "Create Admin" : intent === "signup" ? "Create Account" : "Unlock"}
        </button>
      </form>
      {mode !== "bootstrap" ? (
        <div className="mt-3 flex items-center justify-between">
          <button
            type="button"
            disabled={busy || checking || mode === "unknown"}
            onClick={() => setIntent((v) => (v === "login" ? "signup" : "login"))}
            className="text-sm text-zinc-300 underline decoration-white/20 underline-offset-4 hover:text-white disabled:opacity-60"
          >
            {intent === "login" ? "Create an account" : "I already have an account"}
          </button>
          <span className="text-xs text-zinc-500">Local install</span>
        </div>
      ) : null}
    </main>
  );
}
