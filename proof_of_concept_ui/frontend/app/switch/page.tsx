"use client";

import { useEffect, useState } from "react";
import { DEFAULT_THEME_ID } from "@/lib/theme/presets";

type Profile = { id: string; name: string; avatar?: string | null; themeId?: string | null };

export default function SwitchPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [who, setWho] = useState<string>("");

  async function load() {
    const resp = await fetch("/api/auth/status", { cache: "no-store" });
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok || !payload?.authenticated) {
      window.location.assign("/auth?next=/switch");
      return;
    }
    setWho(String(payload?.username || ""));
    setProfiles(Array.isArray(payload?.profiles) ? payload.profiles : []);
  }

  useEffect(() => {
    load().catch((e) => setError(e?.message || "Failed to load"));
  }, []);

  async function selectProfile(profileId: string, themeId?: string | null) {
    setBusy(true);
    setError(null);
    try {
      // Apply theme immediately for a clean switch.
      const theme = String(themeId || DEFAULT_THEME_ID);
      document.documentElement.setAttribute("data-theme", theme);
      window.localStorage.setItem(`pluggy:theme:${profileId}`, theme);

      const resp = await fetch("/api/profiles/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profileId })
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to switch profile");
      window.location.assign("/");
    } catch (e: any) {
      setError(e?.message || "Failed to switch profile");
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    setError(null);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.assign("/auth");
    }
  }

  async function shutdown() {
    setBusy(true);
    setError(null);
    try {
      await fetch("/api/system/shutdown", { method: "POST" });
    } catch {
      // ignore
    } finally {
      // In WebView builds this closes the app; in browser it may be ignored.
      window.close();
      window.location.assign("/auth");
    }
  }

  async function resetLocalData() {
    if (busy) return;
    const confirmed = window.confirm(
      "Reset local Pluggy data on this machine? This deletes local accounts, profiles, settings, and saved Real-Debrid login from the app, then closes Pluggy."
    );
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/system/reset-local-data", { method: "POST" });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to reset local data");
    } catch (e: any) {
      setError(e?.message || "Failed to reset local data");
      setBusy(false);
      return;
    }
    window.close();
    window.location.assign("/auth");
  }

  return (
    <main className="mx-auto mt-16 max-w-4xl px-6">
      <div className="rounded-2xl border border-white/15 bg-white/10 p-6 shadow-[0_14px_40px_rgba(4,8,20,0.55)] backdrop-blur-2xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Switch profile</h1>
            <p className="mt-1 text-sm text-zinc-300">
              {who ? `Signed in as ${who}. ` : ""}Choose a profile, sign out, shut down Pluggy, or reset local app data.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={signOut}
              disabled={busy}
              className="rounded-lg border border-white/20 bg-black/20 px-3 py-2 text-sm text-zinc-200 hover:bg-black/30 disabled:opacity-60"
            >
              Sign out
            </button>
            <button
              onClick={resetLocalData}
              disabled={busy}
              className="rounded-lg border border-amber-300/30 bg-amber-400/10 px-3 py-2 text-sm font-semibold text-amber-100 hover:bg-amber-400/20 disabled:opacity-60"
              title="Deletes local accounts/profiles/settings on this machine and closes Pluggy"
            >
              Reset local data
            </button>
            <button
              onClick={shutdown}
              disabled={busy}
              className="rounded-lg bg-red-500/90 px-3 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-60"
            >
              Shut down
            </button>
          </div>
        </div>

        {error ? <p className="mt-4 text-sm text-red-300">{error}</p> : null}

        <div className="mt-6">
          <a
            href="/profiles"
            className="text-sm text-zinc-300 underline decoration-white/20 underline-offset-4 hover:text-white"
          >
            Manage profiles (rename, delete, avatar)
          </a>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {profiles.map((p) => (
            <button
              key={p.id}
              onClick={() => selectProfile(p.id, p.themeId)}
              disabled={busy}
              className="group relative overflow-hidden rounded-2xl border border-white/12 bg-gradient-to-b from-white/10 to-black/20 p-4 text-left shadow-[0_12px_30px_rgba(0,0,0,0.35)] backdrop-blur-xl transition-transform hover:-translate-y-0.5 disabled:opacity-60"
            >
              <div className="flex items-center gap-3">
                {p.avatar ? (
                  <img src={p.avatar} alt="" className="h-12 w-12 rounded-xl border border-white/15 object-cover" />
                ) : (
                  <div className="grid h-12 w-12 place-items-center rounded-xl border border-white/15 bg-black/30 text-lg font-semibold text-zinc-200">
                    {(p.name || "?").slice(0, 1).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold text-zinc-100">{p.name}</div>
                  <div className="mt-0.5 text-xs text-zinc-400">{p.themeId ? `Theme: ${p.themeId}` : "Theme: default"}</div>
                </div>
              </div>
              <div className="mt-4 inline-flex rounded-full border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-zinc-300">
                Switch
              </div>
              <div className="pointer-events-none absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100">
                <div className="absolute -left-24 top-8 h-40 w-40 rounded-full bg-[var(--accent-primary)]/10 blur-3xl" />
                <div className="absolute -right-24 bottom-0 h-40 w-40 rounded-full bg-[var(--accent-secondary)]/10 blur-3xl" />
              </div>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
