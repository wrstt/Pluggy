"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Provider = {
  id: string;
  name: string;
  enabled: boolean;
  health: string;
  purpose?: string;
  sourceHealth?: Record<string, unknown>;
};

type LinkSource = {
  id: string;
  title: string;
  url: string;
  description?: string;
  contentType?: string;
  licenseType?: string;
  platforms?: string[];
  formats?: string[];
  tags?: string[];
  trust?: number;
  enabled?: boolean;
};

type AuthStatus = {
  authenticated: boolean;
  username?: string | null;
  role?: "admin" | "user" | null;
};

type SourcePreset = {
  id: string;
  name: string;
  importTags: string;
  importPlatforms: string;
  importContentType: string;
  importLicenseType: string;
  importTrust: number;
};

export default function SourcesPage() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [links, setLinks] = useState<LinkSource[]>([]);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [importLines, setImportLines] = useState("");
  const [importTags, setImportTags] = useState("pc-games,roms");
  const [importPlatforms, setImportPlatforms] = useState("windows,emulator");
  const [importContentType, setImportContentType] = useState("roms");
  const [importLicenseType, setImportLicenseType] = useState("unknown");
  const [importTrust, setImportTrust] = useState(62);
  const [suggestions, setSuggestions] = useState<{ tags: string[]; platforms: string[] }>({ tags: [], platforms: [] });
  const [presetName, setPresetName] = useState("");
  const [presets, setPresets] = useState<SourcePreset[]>([]);
  const [editingLinkId, setEditingLinkId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<LinkSource>>({});
  const [editTagsText, setEditTagsText] = useState("");
  const [editPlatformsText, setEditPlatformsText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const presetStorageKey = `platswap:source-presets:${authStatus?.username || "local"}`;

  async function loadAll() {
    fetch("/api/auth/status", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (response.ok) {
          setAuthStatus(payload as AuthStatus);
        }
      })
      .catch(() => {});
    fetch("/api/providers", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.error?.message ?? "Failed loading providers");
        }
        setProviders(
          (Array.isArray(payload.providers) ? payload.providers : []).filter(
            (provider: Provider) => String(provider.name || "").toLowerCase() !== "rutracker"
          )
        );
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed loading providers"));
    fetch("/api/link-sources", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.error?.message ?? "Failed loading link sources");
        }
        setLinks(Array.isArray(payload.links) ? payload.links : []);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed loading link sources"));
    fetch("/api/link-sources/suggestions", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (response.ok) {
          setSuggestions({
            tags: Array.isArray(payload.tags) ? payload.tags : [],
            platforms: Array.isArray(payload.platforms) ? payload.platforms : []
          });
        }
      })
      .catch(() => {});
  }

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    try {
      setShowAdvanced(window.localStorage.getItem("platswap:sources-advanced") === "1");
    } catch {}
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(presetStorageKey);
      const parsed = raw ? (JSON.parse(raw) as SourcePreset[]) : [];
      setPresets(Array.isArray(parsed) ? parsed : []);
    } catch {
      setPresets([]);
    }
  }, [presetStorageKey]);

  function toggleAdvanced() {
    const next = !showAdvanced;
    setShowAdvanced(next);
    try {
      window.localStorage.setItem("platswap:sources-advanced", next ? "1" : "0");
    } catch {}
  }

  function persistPresets(next: SourcePreset[]) {
    setPresets(next);
    try {
      window.localStorage.setItem(presetStorageKey, JSON.stringify(next));
    } catch {}
  }

  function savePreset() {
    const name = presetName.trim();
    if (!name) return;
    const entry: SourcePreset = {
      id: `srcpreset-${Date.now()}`,
      name,
      importTags,
      importPlatforms,
      importContentType,
      importLicenseType,
      importTrust
    };
    persistPresets([entry, ...presets].slice(0, 20));
    setPresetName("");
  }

  function applyPreset(id: string) {
    const found = presets.find((p) => p.id === id);
    if (!found) return;
    setImportTags(found.importTags);
    setImportPlatforms(found.importPlatforms);
    setImportContentType(found.importContentType);
    setImportLicenseType(found.importLicenseType);
    setImportTrust(found.importTrust);
  }

  function deletePreset(id: string) {
    persistPresets(presets.filter((p) => p.id !== id));
  }

  async function importSources() {
    setBusy("import");
    setError(null);
    try {
      const lines = importLines
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      const tags = importTags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);
      const response = await fetch("/api/link-sources/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lines,
          contentType: importContentType,
          licenseType: importLicenseType,
          platforms: importPlatforms
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          tags,
          trust: importTrust
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Import failed");
      }
      setImportLines("");
      await loadAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(null);
    }
  }

  async function removeLink(id: string) {
    setBusy(`delete-${id}`);
    setError(null);
    try {
      const response = await fetch(`/api/link-sources/${encodeURIComponent(id)}`, {
        method: "DELETE"
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Delete failed");
      }
      await loadAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(null);
    }
  }

  async function toggleLinkEnabled(link: LinkSource) {
    setBusy(`toggle-${link.id}`);
    setError(null);
    try {
      const response = await fetch("/api/link-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: link.id,
          title: link.title,
          url: link.url,
          description: link.description || "",
          contentType: link.contentType || "software",
          licenseType: link.licenseType || "unknown",
          platforms: link.platforms || [],
          formats: link.formats || [],
          tags: link.tags || [],
          trust: link.trust || 60,
          enabled: !(link.enabled ?? true)
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Toggle failed");
      }
      await loadAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Toggle failed");
    } finally {
      setBusy(null);
    }
  }

  async function toggleAllLinks(enabled: boolean) {
    setBusy(`bulk-${enabled ? "on" : "off"}`);
    setError(null);
    try {
      const response = await fetch("/api/link-sources/bulk-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Bulk toggle failed");
      }
      await loadAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Bulk toggle failed");
    } finally {
      setBusy(null);
    }
  }

  async function exportLinks() {
    const response = await fetch("/api/link-sources?export=1", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Export failed");
      return;
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `platswap-link-sources-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function startEdit(link: LinkSource) {
    setEditingLinkId(link.id);
    setEditDraft({
      id: link.id,
      title: link.title,
      url: link.url,
      description: link.description || "",
      contentType: link.contentType || "software",
      licenseType: link.licenseType || "unknown",
      platforms: link.platforms || [],
      tags: link.tags || [],
      trust: link.trust || 60,
      enabled: link.enabled ?? true
    });
    setEditTagsText((link.tags || []).join(","));
    setEditPlatformsText((link.platforms || []).join(","));
  }

  async function saveEdit() {
    if (!editingLinkId) return;
    setBusy(`edit-${editingLinkId}`);
    setError(null);
    try {
      const response = await fetch("/api/link-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: editingLinkId,
          ...editDraft,
          platforms: editPlatformsText
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          tags: editTagsText
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean)
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Update failed");
      }
      setEditingLinkId(null);
      setEditDraft({});
      setEditTagsText("");
      setEditPlatformsText("");
      await loadAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">Sources</h1>
      <p className="text-sm text-zinc-300">
        Provider enable/disable, diagnostics, and tests are in <Link href="/settings" className="underline">Settings</Link>.
      </p>
      {authStatus ? (
        <p className="text-xs text-zinc-400">
          Signed in as {authStatus.username || "unknown"} ({authStatus.role || "user"})
        </p>
      ) : null}
      <button onClick={toggleAdvanced} className="btn-secondary px-3 py-1 text-xs">
        {showAdvanced ? "Hide Advanced" : "Show Advanced"}
      </button>
      {error ? <p className="text-sm text-red-300">{error}</p> : null}

      <section className="rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="text-lg font-semibold">Import Link Sources</h2>
        <p className="text-xs text-zinc-400">Paste one URL per line to create quick source entries.</p>
        {suggestions.tags.length > 0 ? (
          <p className="mt-1 text-xs text-zinc-400">Suggested tags: {suggestions.tags.slice(0, 8).join(", ")}</p>
        ) : null}
        <textarea
          rows={6}
          value={importLines}
          onChange={(event) => setImportLines(event.target.value)}
          placeholder="https://example.com/path"
          className="mt-2 w-full rounded border border-white/20 bg-black/30 p-2 text-xs"
        />
        <label className="mt-2 block text-xs text-zinc-300">
          Tags (comma-separated)
          <input
            value={importTags}
            onChange={(event) => setImportTags(event.target.value)}
            className="mt-1 w-full rounded border border-white/20 bg-black/30 px-2 py-1"
          />
        </label>
        {showAdvanced ? (
          <>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <label className="text-xs text-zinc-300">
                Platforms (comma-separated)
                <input
                  value={importPlatforms}
                  onChange={(event) => setImportPlatforms(event.target.value)}
                  className="mt-1 w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                />
              </label>
              <label className="text-xs text-zinc-300">
                Content Type
                <input
                  value={importContentType}
                  onChange={(event) => setImportContentType(event.target.value)}
                  className="mt-1 w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                />
              </label>
              <label className="text-xs text-zinc-300">
                License Type
                <input
                  value={importLicenseType}
                  onChange={(event) => setImportLicenseType(event.target.value)}
                  className="mt-1 w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                />
              </label>
              <label className="text-xs text-zinc-300">
                Trust
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={importTrust}
                  onChange={(event) => setImportTrust(Number(event.target.value) || 0)}
                  className="mt-1 w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                />
              </label>
            </div>
            <div className="mt-2 rounded border border-white/10 bg-black/20 p-2">
              <p className="text-xs text-zinc-300">Per-User Source Presets</p>
              <div className="mt-1 flex flex-wrap gap-2">
                <input
                  value={presetName}
                  onChange={(event) => setPresetName(event.target.value)}
                  placeholder="Preset name"
                  className="rounded border border-white/20 bg-black/30 px-2 py-1 text-xs"
                />
                <button onClick={savePreset} className="btn-secondary px-2 py-1 text-xs">
                  Save Preset
                </button>
                {presets.map((preset) => (
                  <div key={preset.id} className="flex items-center gap-1 rounded border border-white/20 bg-black/30 px-2 py-1 text-xs">
                    <button onClick={() => applyPreset(preset.id)}>{preset.name}</button>
                    <button onClick={() => deletePreset(preset.id)} className="text-zinc-400">
                      x
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}
        <button
          onClick={importSources}
          disabled={busy === "import"}
          className="mt-2 rounded bg-[var(--accent-primary)] px-3 py-1 text-black"
        >
          {busy === "import" ? "Importing..." : "Import URLs"}
        </button>
      </section>

      <section className="space-y-2 rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Curated Link Sources</h2>
          {showAdvanced ? (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => toggleAllLinks(true)}
                disabled={busy === "bulk-on"}
                className="btn-secondary px-2 py-1 text-xs"
              >
                Enable All
              </button>
              <button
                onClick={() => toggleAllLinks(false)}
                disabled={busy === "bulk-off"}
                className="btn-secondary px-2 py-1 text-xs"
              >
                Disable All
              </button>
              <button onClick={exportLinks} className="btn-secondary px-2 py-1 text-xs">
                Export JSON
              </button>
            </div>
          ) : null}
        </div>
        <p className="text-xs text-zinc-400">
          Enable only the sources you want queried. OpenDirectory and FTP entries are preloaded.
        </p>
        {links.length === 0 ? <p className="text-sm text-zinc-300">No custom link sources yet.</p> : null}
        {links.map((link) => (
          <article key={link.id} className="rounded-lg border border-white/10 bg-black/20 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                {editingLinkId === link.id ? (
                  <div className="space-y-1 text-xs">
                    <input
                      value={String(editDraft.title ?? "")}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, title: event.target.value }))}
                      className="w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                    />
                    <input
                      value={String(editDraft.url ?? "")}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, url: event.target.value }))}
                      className="w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                    />
                    <input
                      value={editTagsText}
                      onChange={(event) => setEditTagsText(event.target.value)}
                      placeholder="tags comma-separated"
                      className="w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                    />
                    <input
                      value={editPlatformsText}
                      onChange={(event) => setEditPlatformsText(event.target.value)}
                      placeholder="platforms comma-separated"
                      className="w-full rounded border border-white/20 bg-black/30 px-2 py-1"
                    />
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={Number(editDraft.trust ?? 0)}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, trust: Number(event.target.value) || 0 }))}
                      className="w-28 rounded border border-white/20 bg-black/30 px-2 py-1"
                    />
                  </div>
                ) : (
                  <>
                    <p className="font-medium">{link.title}</p>
                    <a className="text-xs text-zinc-300 underline" href={link.url} target="_blank" rel="noreferrer">
                      {link.url}
                    </a>
                    <p className="text-xs text-zinc-400">
                      {link.contentType} • {link.licenseType} • trust {link.trust ?? 0}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {(link.tags || []).slice(0, 6).join(" • ") || "no tags"}
                    </p>
                  </>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => toggleLinkEnabled(link)}
                  disabled={busy === `toggle-${link.id}`}
                  className={`rounded border px-2 py-1 text-xs ${
                    link.enabled
                      ? "border-emerald-400/40 bg-emerald-500/20 text-emerald-100"
                      : "border-white/20 bg-white/10 text-zinc-200"
                  }`}
                >
                  {busy === `toggle-${link.id}` ? "Saving..." : link.enabled ? "Enabled" : "Disabled"}
                </button>
                {editingLinkId === link.id ? (
                  <>
                    <button
                      onClick={saveEdit}
                      disabled={busy === `edit-${link.id}`}
                      className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => {
                        setEditingLinkId(null);
                        setEditDraft({});
                        setEditTagsText("");
                        setEditPlatformsText("");
                      }}
                      className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                    >
                      Cancel
                    </button>
                  </>
                ) : showAdvanced ? (
                  <>
                    <button
                      onClick={() => startEdit(link)}
                      className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => removeLink(link.id)}
                      disabled={busy === `delete-${link.id}`}
                      className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                    >
                      Remove
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          </article>
        ))}
      </section>

      <div className="space-y-2">
        {providers.map((provider) => (
          <article key={provider.id} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <h2 className="font-semibold">{provider.name}</h2>
            <p className="text-sm text-zinc-300">
              {provider.health} • {provider.enabled ? "enabled" : "disabled"}
            </p>
            <p className="text-xs text-zinc-400">{provider.purpose}</p>
          </article>
        ))}
      </div>
    </main>
  );
}
