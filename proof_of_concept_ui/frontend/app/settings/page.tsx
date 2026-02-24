"use client";

import { useEffect, useMemo, useState } from "react";
import { DEFAULT_THEME_ID, THEME_PRESETS } from "@/lib/theme/presets";

type Provider = {
  id: string;
  name: string;
  enabled: boolean;
  health: string;
  purpose?: string;
  sourceHealth?: Record<string, unknown>;
};

type Capabilities = {
  downloadBackends: { id: string; selected: boolean; available: boolean; purpose: string }[];
  focus?: { goal?: string; includes?: string[]; excludes?: string[] };
};

type RDStatus = {
  rdConnected: boolean;
  status: "connected" | "pending" | "disconnected" | "failed";
  message?: string;
  account?: { username?: string; email?: string };
};

type AuthStatus = {
  authenticated: boolean;
  username?: string | null;
  role?: "admin" | "user" | null;
};

export default function SettingsPage() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [themeId, setThemeId] = useState(DEFAULT_THEME_ID);
  const [themeKey, setThemeKey] = useState("platswap:theme");
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [rdStatus, setRdStatus] = useState<RDStatus>({ rdConnected: false, status: "disconnected" });
  const [rdDevice, setRdDevice] = useState<{ userCode?: string; verificationUrl?: string; expiresIn?: number }>({});
  const [settingsJson, setSettingsJson] = useState("{}");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [providerDetails, setProviderDetails] = useState<Record<string, unknown> | null>(null);
  const [auditEvents, setAuditEvents] = useState<{ at: string; event: string; detail: Record<string, unknown> }[]>([]);
  const [verifyReport, setVerifyReport] = useState<Record<string, unknown> | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [adminPin, setAdminPin] = useState("");

  const simpleSettings = useMemo(
    () => ({
      min_seeds: Number(settings?.min_seeds ?? 0),
      pagination_size: Number(settings?.pagination_size ?? 20),
      max_concurrent_downloads: Number(settings?.max_concurrent_downloads ?? 3),
      download_backend: String(settings?.download_backend ?? "native"),
      rd_library_source_enabled: Boolean(settings?.rd_library_source_enabled ?? false),
      open_directory_enabled: Boolean(settings?.open_directory_enabled ?? true),
      http_playwright_fallback_enabled: Boolean(settings?.http_playwright_fallback_enabled ?? false),
      prowlarr_url: String(settings?.prowlarr_url ?? "http://127.0.0.1:9696"),
      prowlarr_api_key: String(settings?.prowlarr_api_key ?? ""),
      prowlarr_auto_fetch_api_key: Boolean(settings?.prowlarr_auto_fetch_api_key ?? true)
    }),
    [settings]
  );

  async function loadAll() {
    setError(null);
    try {
      const [settingsRes, providersRes, capsRes, rdRes, auditRes, authRes] = await Promise.all([
        fetch("/api/settings", { cache: "no-store" }),
        fetch("/api/providers", { cache: "no-store" }),
        fetch("/api/system/capabilities", { cache: "no-store" }),
        fetch("/api/session/rd/status", { cache: "no-store" }),
        fetch("/api/audit?limit=100", { cache: "no-store" }),
        fetch("/api/auth/status", { cache: "no-store" })
      ]);

      const settingsPayload = await settingsRes.json();
      const providersPayload = await providersRes.json();
      const capsPayload = await capsRes.json();
      const rdPayload = await rdRes.json();
      const auditPayload = await auditRes.json();
      const authPayload = await authRes.json();

      if (!settingsRes.ok) throw new Error(settingsPayload?.error?.message ?? "Failed loading settings");
      if (!providersRes.ok) throw new Error(providersPayload?.error?.message ?? "Failed loading providers");
      if (!capsRes.ok) throw new Error(capsPayload?.error?.message ?? "Failed loading capabilities");
      if (!rdRes.ok) throw new Error(rdPayload?.error?.message ?? "Failed loading RD status");
      if (!auditRes.ok) throw new Error(auditPayload?.error?.message ?? "Failed loading audit feed");

      setSettings(settingsPayload.settings ?? {});
      setSettingsJson(JSON.stringify(settingsPayload.settings ?? {}, null, 2));
      setProviders(
        (Array.isArray(providersPayload.providers) ? providersPayload.providers : []).filter(
          (provider: Provider) => String(provider.name || "").toLowerCase() !== "rutracker"
        )
      );
      setCapabilities(capsPayload);
      setRdStatus(rdPayload as RDStatus);
      setAuditEvents(Array.isArray(auditPayload.events) ? auditPayload.events : []);
      if (authRes.ok) {
        setAuthStatus(authPayload as AuthStatus);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed loading settings");
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    try {
      setShowAdvanced(window.localStorage.getItem("platswap:settings-advanced") === "1");
    } catch {}
  }, []);

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem("platswap:admin-pin") || "";
      setAdminPin(saved);
    } catch {}
  }, []);

  useEffect(() => {
    const legacyKey = "platswap:theme";
    const profileId = (authStatus as any)?.profileId ? String((authStatus as any).profileId) : "";
    const key = profileId ? `pluggy:theme:${profileId}` : legacyKey;
    setThemeKey(key);
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(key) : null;
    const legacy = typeof window !== "undefined" ? window.localStorage.getItem(legacyKey) : null;
    const active = saved || legacy || DEFAULT_THEME_ID;
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", active);
    }
    setThemeId(active);
  }, [authStatus]);

  useEffect(() => {
    const timer = setInterval(async () => {
      const response = await fetch("/api/audit?limit=100", { cache: "no-store" });
      const payload = await response.json();
      if (response.ok) {
        setAuditEvents(Array.isArray(payload.events) ? payload.events : []);
      }
    }, 6000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (rdStatus.status !== "pending") return;
    const timer = setInterval(async () => {
      const response = await fetch("/api/session/rd/status?poll=1", { cache: "no-store" });
      const payload = await response.json();
      if (response.ok) {
        setRdStatus(payload as RDStatus);
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [rdStatus.status]);

  const adminHeaders = useMemo(() => {
    const headers: Record<string, string> = {};
    if (adminPin.trim()) {
      headers["x-platswap-admin-pin"] = adminPin.trim();
    }
    return headers;
  }, [adminPin]);

  function rememberAdminPin(pin: string) {
    setAdminPin(pin);
    try {
      if (pin.trim()) {
        window.sessionStorage.setItem("platswap:admin-pin", pin.trim());
      } else {
        window.sessionStorage.removeItem("platswap:admin-pin");
      }
    } catch {}
  }

  function toggleAdvanced() {
    const next = !showAdvanced;
    setShowAdvanced(next);
    try {
      window.localStorage.setItem("platswap:settings-advanced", next ? "1" : "0");
    } catch {}
  }

  async function patchSettings(patch: Record<string, unknown>) {
    setBusy("settings");
    setError(null);
    try {
      const response = await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...adminHeaders },
        body: JSON.stringify(patch)
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Failed to save settings");
      }
      setSettings(payload.settings ?? {});
      setSettingsJson(JSON.stringify(payload.settings ?? {}, null, 2));
      await loadAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setBusy(null);
    }
  }

  async function connectRD() {
    setBusy("rd-connect");
    setError(null);
    try {
      const response = await fetch("/api/session/rd/connect", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Failed to start RD auth");
      }
      setRdStatus({ rdConnected: false, status: "pending" });
      setRdDevice(payload.device || {});
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start RD auth");
    } finally {
      setBusy(null);
    }
  }

  async function checkRD() {
    setBusy("rd-check");
    const response = await fetch("/api/session/rd/check", { method: "POST" });
    const payload = await response.json();
    if (response.ok) {
      setRdStatus({
        rdConnected: Boolean(payload.rdConnected),
        status: payload.status,
        message: payload.message
      });
      if (payload.rdConnected) {
        await loadAll();
      }
    } else {
      setError(payload?.error?.message ?? "RD check failed");
    }
    setBusy(null);
  }

  async function logoutRD() {
    setBusy("rd-logout");
    const response = await fetch("/api/session/rd/logout", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "RD logout failed");
    } else {
      setRdStatus({ rdConnected: false, status: "disconnected" });
      setRdDevice({});
    }
    setBusy(null);
  }

  async function toggleProvider(provider: Provider) {
    setBusy(`provider-${provider.id}`);
    setError(null);
    const response = await fetch(`/api/providers/${encodeURIComponent(provider.id)}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...adminHeaders },
      body: JSON.stringify({ enabled: !provider.enabled })
    });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Provider update failed");
    } else {
      setProviders((prev) => prev.map((p) => (p.id === provider.id ? { ...p, enabled: !p.enabled } : p)));
    }
    setBusy(null);
  }

  async function enableAllProviders() {
    const enabledSources: Record<string, boolean> = {};
    for (const provider of providers) {
      enabledSources[provider.name] = true;
    }
    await patchSettings({ enabled_sources: enabledSources });
  }

  async function testProvider(provider: Provider) {
    setBusy(`test-${provider.id}`);
    setError(null);
    const response = await fetch(`/api/providers/${encodeURIComponent(provider.id)}/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "vst plugin", timeoutSeconds: 10 })
    });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Provider test failed");
    } else {
      setProviderDetails({ provider: provider.name, test: payload });
    }
    setBusy(null);
  }

  async function inspectProvider(provider: Provider) {
    setBusy(`inspect-${provider.id}`);
    setError(null);
    const response = await fetch(`/api/providers/${encodeURIComponent(provider.id)}/details`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Provider inspect failed");
    } else {
      setProviderDetails(payload);
    }
    setBusy(null);
  }

  async function resetSettings() {
    setBusy("reset");
    const response = await fetch("/api/settings/reset", { method: "POST", headers: { ...adminHeaders } });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Reset failed");
    } else {
      setSettings(payload.settings ?? {});
      setSettingsJson(JSON.stringify(payload.settings ?? {}, null, 2));
      await loadAll();
    }
    setBusy(null);
  }

  async function runVerification() {
    setBusy("verify");
    setError(null);
    const response = await fetch("/api/system/verify", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Verification failed");
    } else {
      setVerifyReport(payload);
      await loadAll();
    }
    setBusy(null);
  }

  async function clearAudit() {
    setBusy("audit-clear");
    setError(null);
    const response = await fetch("/api/audit/clear", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload?.error?.message ?? "Failed to clear audit");
    } else {
      setAuditEvents([]);
      await loadAll();
    }
    setBusy(null);
  }

  function exportDiagnostics() {
    const report = {
      generatedAt: new Date().toISOString(),
      verifyReport,
      providerDetails,
      capabilities,
      auditEvents
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pluggy-diagnostics-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function saveJsonSettings() {
    try {
      const parsed = JSON.parse(settingsJson);
      await patchSettings(parsed);
    } catch {
      setError("Settings JSON is invalid");
    }
  }

  function applyTheme(nextThemeId: string) {
    setThemeId(nextThemeId);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", nextThemeId);
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(themeKey || "platswap:theme", nextThemeId);
    }
    fetch("/api/profiles/theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ themeId: nextThemeId })
    }).catch(() => {});
  }

  return (
    <main className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings & Source Management</h1>
      {authStatus ? (
        <p className="text-xs text-zinc-400">
          Signed in as {authStatus.username || "unknown"} ({authStatus.role || "user"})
        </p>
      ) : null}
      <button onClick={toggleAdvanced} className="btn-secondary px-3 py-1 text-xs">
        {showAdvanced ? "Hide Advanced" : "Show Advanced"}
      </button>
      {error ? <p className="text-sm text-red-300">{error}</p> : null}

      {showAdvanced ? (
        <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
          <h2 className="text-lg font-semibold">Admin PIN</h2>
          <p className="mt-1 text-sm text-zinc-200">Optional local PIN for admin-only actions when `PLATSWAP_ADMIN_PIN` is set.</p>
          <input
            type="password"
            value={adminPin}
            onChange={(event) => rememberAdminPin(event.target.value)}
            placeholder="Enter Admin PIN"
            className="mt-2 w-full max-w-sm rounded border border-white/20 bg-black/30 px-3 py-2"
          />
        </section>
      ) : null}

      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
        <h2 className="text-lg font-semibold">RealDebrid Auth</h2>
        <p className="mt-1 text-sm text-zinc-200">Status: {rdStatus.status}</p>
        {rdStatus.account?.username ? <p className="text-sm text-zinc-300">Account: {rdStatus.account.username}</p> : null}
        {rdStatus.message ? <p className="text-sm text-zinc-300">{rdStatus.message}</p> : null}
        {rdDevice.userCode ? (
          <p className="mt-2 text-sm text-zinc-100">
            Authorize with code <span className="font-semibold">{rdDevice.userCode}</span> at {rdDevice.verificationUrl}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={connectRD} disabled={busy === "rd-connect"} className="rounded bg-[var(--accent-primary)] px-3 py-1 text-black">
            {busy === "rd-connect" ? "Starting…" : "Start Device Auth"}
          </button>
          <button onClick={checkRD} disabled={busy === "rd-check"} className="rounded border border-white/20 bg-white/10 px-3 py-1">
            {busy === "rd-check" ? "Checking…" : "Check Authorization"}
          </button>
          <button onClick={logoutRD} disabled={busy === "rd-logout"} className="rounded border border-white/20 bg-white/10 px-3 py-1">
            {busy === "rd-logout" ? "Disconnecting…" : "Disconnect"}
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
        <h2 className="text-lg font-semibold">Theme Studio</h2>
        <p className="mt-1 text-sm text-zinc-200">Choose from 10 new visual styles plus the original cinematic base.</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {THEME_PRESETS.map((theme) => {
            const active = theme.id === themeId;
            return (
              <button
                key={theme.id}
                onClick={() => applyTheme(theme.id)}
                className={`rounded-xl border p-3 text-left transition ${
                  active ? "border-[var(--accent-primary)] bg-black/35" : "border-white/20 bg-black/20 hover:bg-black/30"
                }`}
              >
                <p className="font-medium">{theme.name}</p>
                <p className="mt-1 text-xs text-zinc-300">{theme.blurb}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
        <h2 className="text-lg font-semibold">Prowlarr</h2>
        <p className="mt-1 text-sm text-zinc-200">Optional: connect to your local Prowlarr for indexer-powered searches.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Prowlarr URL
            <input
              value={simpleSettings.prowlarr_url}
              onChange={(event) => patchSettings({ prowlarr_url: event.target.value })}
              placeholder="http://127.0.0.1:9696"
              className="rounded border border-white/20 bg-black/30 px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            API Key
            <input
              type="password"
              value={simpleSettings.prowlarr_api_key}
              onChange={(event) => patchSettings({ prowlarr_api_key: event.target.value })}
              placeholder="Paste from Prowlarr Settings -> General"
              className="rounded border border-white/20 bg-black/30 px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input
              type="checkbox"
              checked={simpleSettings.prowlarr_auto_fetch_api_key}
              onChange={(event) => patchSettings({ prowlarr_auto_fetch_api_key: event.target.checked })}
            />
            Auto-fetch key from <code className="rounded bg-black/30 px-1 py-0.5">/initialize.json</code> when auth is disabled
          </label>
        </div>
        <p className="mt-2 text-xs text-zinc-300">
          Enable the <span className="font-medium">Prowlarr</span> provider in the Providers section to include it in searches.
        </p>
      </section>

      {showAdvanced ? (
        <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
          <h2 className="text-lg font-semibold">Hosted-Local Controls</h2>
          <p className="mt-1 text-sm text-zinc-200">Run production-style local services with detached startup scripts.</p>
          <div className="mt-2 space-y-2 text-xs text-zinc-300">
            <p>
              Start: <code>./scripts/start_hosted_local.sh</code>
            </p>
            <p>
              Status: <code>./scripts/status_hosted_local.sh</code>
            </p>
            <p>
              Stop: <code>./scripts/stop_hosted_local.sh</code>
            </p>
            <p>
              Log: <code>./.reports/hosted-local/hosted-local.log</code>
            </p>
          </div>
        </section>
      ) : null}

      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
        <h2 className="text-lg font-semibold">Core Settings</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Min Seeds
            <input
              type="number"
              value={simpleSettings.min_seeds}
              onChange={(event) => patchSettings({ min_seeds: Number(event.target.value) })}
              className="rounded border border-white/20 bg-black/30 px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Results Per Page
            <input
              type="number"
              value={simpleSettings.pagination_size}
              onChange={(event) => patchSettings({ pagination_size: Number(event.target.value) })}
              className="rounded border border-white/20 bg-black/30 px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Max Concurrent Downloads
            <input
              type="number"
              value={simpleSettings.max_concurrent_downloads}
              onChange={(event) => patchSettings({ max_concurrent_downloads: Number(event.target.value) })}
              className="rounded border border-white/20 bg-black/30 px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Download Backend
            <select
              value={simpleSettings.download_backend}
              onChange={(event) => patchSettings({ download_backend: event.target.value })}
              className="rounded border border-white/20 bg-black/30 px-2 py-1"
            >
              <option value="native">native</option>
              <option value="aria2">aria2</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={simpleSettings.rd_library_source_enabled}
              onChange={(event) => patchSettings({ rd_library_source_enabled: event.target.checked })}
            />
            Enable RealDebrid Library Source
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={simpleSettings.open_directory_enabled}
              onChange={(event) => patchSettings({ open_directory_enabled: event.target.checked })}
            />
            Enable Open Directory Source
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={simpleSettings.http_playwright_fallback_enabled}
              onChange={(event) => patchSettings({ http_playwright_fallback_enabled: event.target.checked })}
            />
            Enable HTTP Playwright Fallback
          </label>
        </div>
        <button onClick={resetSettings} disabled={busy === "reset"} className="mt-4 rounded border border-white/20 bg-white/10 px-3 py-1 text-sm">
          {busy === "reset" ? "Resetting…" : "Reset to Defaults"}
        </button>
      </section>

      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
        <h2 className="text-lg font-semibold">Providers</h2>
        <div className="mt-2">
          <button onClick={enableAllProviders} disabled={busy === "settings"} className="btn-secondary px-3 py-1 text-xs">
            Enable All Providers
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {providers.map((provider) => (
            <article key={provider.id} className="rounded-xl border border-white/20 bg-black/20 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{provider.name}</p>
                  <p className="text-xs text-zinc-300">
                    {provider.health} • {provider.purpose ?? "source"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => toggleProvider(provider)}
                    disabled={busy === `provider-${provider.id}`}
                    className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                  >
                    {provider.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    onClick={() => testProvider(provider)}
                    disabled={busy === `test-${provider.id}`}
                    className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                  >
                    Test
                  </button>
                  <button
                    onClick={() => inspectProvider(provider)}
                    disabled={busy === `inspect-${provider.id}`}
                    className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs"
                  >
                    Inspect
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
        <h2 className="text-lg font-semibold">Backends & Purpose Verification</h2>
        <ul className="mt-2 space-y-2 text-sm text-zinc-200">
          {(capabilities?.downloadBackends || []).map((backend) => (
            <li key={backend.id} className="rounded-lg border border-white/20 bg-black/20 p-2">
              <span className="font-medium">{backend.id}</span> • {backend.available ? "available" : "not installed"}
              {backend.selected ? " • selected" : ""}
              <p className="text-xs text-zinc-300">{backend.purpose}</p>
            </li>
          ))}
        </ul>
        {capabilities?.focus ? (
          <p className="mt-2 text-xs text-zinc-300">
            Goal: {capabilities.focus.goal} • Includes: {(capabilities.focus.includes || []).join(", ")} • Excludes: {(capabilities.focus.excludes || []).join(", ")}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={runVerification} disabled={busy === "verify"} className="rounded bg-[var(--accent-primary)] px-3 py-1 text-black">
            {busy === "verify" ? "Running Verify…" : "Run Deep Verify"}
          </button>
          <button onClick={exportDiagnostics} className="rounded border border-white/20 bg-white/10 px-3 py-1 text-sm">
            Export Diagnostics JSON
          </button>
        </div>
      </section>

      {showAdvanced ? (
        <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
          <h2 className="text-lg font-semibold">Advanced JSON Settings</h2>
          <textarea
            value={settingsJson}
            onChange={(event) => setSettingsJson(event.target.value)}
            rows={12}
            className="mt-2 w-full rounded border border-white/20 bg-black/30 p-2 font-mono text-xs"
          />
          <button onClick={saveJsonSettings} disabled={busy === "settings"} className="btn-primary mt-2">
            {busy === "settings" ? "Saving…" : "Save JSON"}
          </button>
        </section>
      ) : null}

      {showAdvanced && providerDetails ? (
        <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
          <h2 className="text-lg font-semibold">Provider Diagnostics</h2>
          <pre className="mt-2 overflow-x-auto rounded bg-black/30 p-3 text-xs text-zinc-200">
            {JSON.stringify(providerDetails, null, 2)}
          </pre>
        </section>
      ) : null}

      {showAdvanced && verifyReport ? (
        <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
          <h2 className="text-lg font-semibold">Verification Report</h2>
          <pre className="mt-2 overflow-x-auto rounded bg-black/30 p-3 text-xs text-zinc-200">
            {JSON.stringify(verifyReport, null, 2)}
          </pre>
        </section>
      ) : null}

      {showAdvanced ? (
        <section className="rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Audit Feed</h2>
            <button onClick={clearAudit} disabled={busy === "audit-clear"} className="btn-secondary">
              {busy === "audit-clear" ? "Clearing…" : "Clear Audit"}
            </button>
          </div>
          <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">
            {auditEvents.map((evt, idx) => (
              <article key={`${evt.at}-${idx}`} className="rounded-lg border border-white/20 bg-black/20 p-2 text-xs">
                <p className="font-medium">{evt.event}</p>
                <p className="text-zinc-300">{new Date(evt.at).toLocaleString()}</p>
                <pre className="mt-1 overflow-x-auto text-zinc-300">{JSON.stringify(evt.detail, null, 2)}</pre>
              </article>
            ))}
            {auditEvents.length === 0 ? <p className="text-sm text-zinc-300">No audit events yet.</p> : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}
