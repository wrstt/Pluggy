"use client";

import { useEffect, useMemo, useState } from "react";
import { DEFAULT_THEME_ID } from "@/lib/theme/presets";

type Profile = { id: string; name: string; avatar?: string | null; themeId?: string | null };

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [manage, setManage] = useState(false);
  const [renameDraft, setRenameDraft] = useState<Record<string, string>>({});

  const canCreate = useMemo(() => name.trim().length >= 2 && profiles.length < 8, [name, profiles.length]);

  async function refresh() {
    const statusResp = await fetch("/api/auth/status", { cache: "no-store" });
    const statusPayload = await statusResp.json().catch(() => ({}));
    setStatus(statusPayload);
    if (!statusResp.ok || !statusPayload?.authenticated) {
      window.location.assign("/auth?next=/profiles");
      return;
    }
    const resp = await fetch("/api/profiles", { cache: "no-store" });
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to load profiles");
    setProfiles(Array.isArray(payload?.profiles) ? payload.profiles : []);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Failed to load profiles");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createProfile() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() })
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to create profile");
      setName("");
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Failed to create profile");
    } finally {
      setBusy(false);
    }
  }

  async function selectProfile(profileId: string) {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/profiles/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profileId })
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to select profile");
      window.location.assign("/");
    } catch (e: any) {
      setError(e?.message || "Failed to select profile");
    } finally {
      setBusy(false);
    }
  }

  async function patchProfile(profileId: string, patch: Record<string, unknown>) {
    const resp = await fetch(`/api/profiles/${encodeURIComponent(profileId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    });
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to update profile");
    await refresh();
  }

  async function deleteProfile(profileId: string) {
    if (!confirm("Delete this profile? (Its settings will be removed.)")) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(payload?.detail ?? payload?.error?.message ?? "Failed to delete profile");
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Failed to delete profile");
    } finally {
      setBusy(false);
    }
  }

  async function uploadAvatar(profileId: string, file: File | null) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Avatar must be an image.");
      return;
    }
    if (file.size > 220_000) {
      setError("Avatar too large. Please use an image under ~200KB.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("Failed reading image."));
        reader.readAsDataURL(file);
      });
      await patchProfile(profileId, { avatar: dataUrl });
    } catch (e: any) {
      setError(e?.message || "Failed to upload avatar");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError(null);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.assign("/auth");
    }
  }

  return (
    <main className="mx-auto mt-16 max-w-4xl px-6">
      <div className="rounded-2xl border border-white/15 bg-white/10 p-6 shadow-[0_14px_40px_rgba(4,8,20,0.55)] backdrop-blur-2xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Choose a profile</h1>
            <p className="mt-1 text-sm text-zinc-300">
              Profiles keep themes, sources, and Real-Debrid settings isolated. Up to 8 profiles per user.
            </p>
          </div>
          <button
            onClick={logout}
            disabled={busy}
            className="rounded-lg border border-white/20 bg-black/20 px-3 py-2 text-sm text-zinc-200 hover:bg-black/30 disabled:opacity-60"
          >
            Sign out
          </button>
        </div>

        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            onClick={() => setManage((v) => !v)}
            disabled={busy}
            className="rounded-lg border border-white/15 bg-black/20 px-3 py-2 text-sm text-zinc-200 hover:bg-black/30 disabled:opacity-60"
          >
            {manage ? "Done" : "Manage profiles"}
          </button>
          <div className="text-xs text-zinc-400">Avatars + rename/delete live here.</div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-black/20 p-4">
            <div className="text-sm font-semibold text-zinc-200">Create profile</div>
            <div className="mt-3 flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Profile name"
                className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm"
              />
              <button
                onClick={createProfile}
                disabled={!canCreate || busy}
                className="rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-sm font-semibold text-black disabled:opacity-60"
              >
                Add
              </button>
            </div>
            <div className="mt-2 text-xs text-zinc-400">
              {profiles.length}/8 profiles {status?.username ? `for ${status.username}` : ""}
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-black/20 p-4">
            <div className="text-sm font-semibold text-zinc-200">Tip</div>
            <p className="mt-2 text-xs text-zinc-400">
              If you want everyone to share the same Real-Debrid account, enable “Share RD across profiles” in Settings
              after selecting a profile.
            </p>
          </div>
        </div>

        {error ? <p className="mt-4 text-sm text-red-300">{error}</p> : null}

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {profiles.map((p) => {
            const Shell: any = manage ? "div" : "button";
            return (
              <Shell
                key={p.id}
                onClick={() => {
                  if (manage) return;
                  // Apply theme immediately on select, no flash.
                  const theme = String(p.themeId || DEFAULT_THEME_ID);
                  document.documentElement.setAttribute("data-theme", theme);
                  window.localStorage.setItem(`pluggy:theme:${p.id}`, theme);
                  selectProfile(p.id);
                }}
                disabled={manage ? undefined : busy}
                className="group relative overflow-hidden rounded-2xl border border-white/12 bg-gradient-to-b from-white/10 to-black/20 p-4 text-left shadow-[0_12px_30px_rgba(0,0,0,0.35)] backdrop-blur-xl transition-transform hover:-translate-y-0.5 disabled:opacity-60"
              >
              <div className="flex items-center gap-3">
                {p.avatar ? (
                  <img
                    src={p.avatar}
                    alt=""
                    className="h-12 w-12 rounded-xl border border-white/15 object-cover"
                  />
                ) : (
                  <div className="grid h-12 w-12 place-items-center rounded-xl border border-white/15 bg-black/30 text-lg font-semibold text-zinc-200">
                    {(p.name || "?").slice(0, 1).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold text-zinc-100">{p.name}</div>
                  <div className="mt-0.5 text-xs text-zinc-400">{p.themeId ? `Theme: ${p.themeId}` : "Default theme"}</div>
                </div>
              </div>
              {manage ? (
                <div className="mt-4 space-y-2">
                  <div className="flex gap-2">
                    <input
                      value={renameDraft[p.id] ?? p.name}
                      onChange={(e) => setRenameDraft((m) => ({ ...m, [p.id]: e.target.value }))}
                      className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm"
                    />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setBusy(true);
                        setError(null);
                        patchProfile(p.id, { name: (renameDraft[p.id] ?? p.name).trim() })
                          .catch((err) => setError(err?.message || "Failed to rename"))
                          .finally(() => setBusy(false));
                      }}
                      disabled={busy}
                      className="rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-sm font-semibold text-black disabled:opacity-60"
                    >
                      Save
                    </button>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <label className="text-xs text-zinc-300">
                      Avatar
                      <input
                        type="file"
                        accept="image/*"
                        className="mt-1 block w-full text-xs text-zinc-200"
                        onChange={(e) => uploadAvatar(p.id, e.target.files?.[0] ?? null)}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        deleteProfile(p.id);
                      }}
                      disabled={busy}
                      className="h-9 rounded-lg bg-red-500/90 px-3 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-60"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mt-4 inline-flex rounded-full border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-zinc-300">
                  Select
                </div>
              )}
              <div className="pointer-events-none absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100">
                <div className="absolute -left-24 top-8 h-40 w-40 rounded-full bg-[var(--accent-primary)]/10 blur-3xl" />
                <div className="absolute -right-24 bottom-0 h-40 w-40 rounded-full bg-[var(--accent-secondary)]/10 blur-3xl" />
              </div>
              </Shell>
            );
          })}
        </div>
      </div>
    </main>
  );
}
