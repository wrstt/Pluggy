"use client";

import { useEffect, useState } from "react";
import { Rail } from "@/components/shared/Rail";

type HomeRail = {
  id: string;
  title: string;
  items: {
    id: string;
    title: string;
    provider?: string;
    subtitle: string;
    protocol: "http" | "torrent";
    sourceResultId?: string;
  }[];
};

type TransferQueueItem = {
  sourceResultId: string;
  status: string;
};

type HomeToast = {
  id: string;
  tone: "success" | "info" | "error";
  message: string;
};

export default function HomePage() {
  const [rails, setRails] = useState<HomeRail[]>([]);
  const [health, setHealth] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [rdPending, setRdPending] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [queuedBySourceId, setQueuedBySourceId] = useState<Record<string, string>>({});
  const [toasts, setToasts] = useState<HomeToast[]>([]);
  const [warmupSeconds, setWarmupSeconds] = useState(0);

  async function fetchJsonWithTimeout(url: string, timeoutMs: number) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { cache: "no-store", signal: controller.signal });
      const payload = await response.json().catch(() => ({}));
      return { response, payload };
    } finally {
      clearTimeout(timer);
    }
  }

  function pushToast(tone: HomeToast["tone"], message: string) {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((prev) => [...prev, { id, tone, message }].slice(-4));
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3400);
  }

  useEffect(() => {
    let cancelled = false;
    const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
    const warmupStartedAt = Date.now();
    let finished = false;
    let slowNoticeShown = false;
    const completeWarmup = (next: { error?: string | null; notice?: string | null } = {}) => {
      if (cancelled || finished) return;
      finished = true;
      setLoading(false);
      if (typeof next.error !== "undefined") setError(next.error);
      if (typeof next.notice !== "undefined") setNotice(next.notice);
    };

    (async () => {
      let attempt = 0;
      while (!cancelled) {
        attempt += 1;
        if (cancelled) return;
        try {
          const { response, payload } = await fetchJsonWithTimeout(
            `/api/home?force_refresh=${attempt > 1 ? "true" : "false"}`,
            7000
          );
          if (!response.ok) {
            throw new Error(payload?.error?.message ?? "Failed to load home rails");
          }
          const nextRails = Array.isArray(payload.rails) ? payload.rails : [];
          const nextHealth = payload.health || {};
          const providersTotal = Number(nextHealth.providersTotal ?? 0);
          const populatedRails = nextRails.filter(
            (rail: HomeRail) => Array.isArray(rail?.items) && rail.items.length > 0
          ).length;
          const itemCount = nextRails.reduce(
            (sum: number, rail: HomeRail) => sum + (Array.isArray(rail?.items) ? rail.items.length : 0),
            0
          );
          const ready = providersTotal > 0 && populatedRails >= 2 && itemCount >= 8;
          setRails(nextRails);
          setHealth(nextHealth);
          if (ready) {
            completeWarmup();
            return;
          }
        } catch (err: unknown) {
          const message =
            err instanceof Error && err.name === "AbortError"
              ? "Home data timed out while warming up."
              : err instanceof Error
              ? err.message
              : "Failed to load home rails";
          // Keep polling forever; show error but don't stop warmup.
          setError(message);
        }
        if (!slowNoticeShown && Date.now() - warmupStartedAt > 12000) {
          slowNoticeShown = true;
          setNotice("Home is still loading. Showing live status while sources warm up.");
        }
        // Backoff slightly to reduce pressure during long warmups.
        await delay(attempt < 8 ? 800 : attempt < 20 ? 1200 : 1800);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();

    const pollRd = async () => {
      try {
        const { response, payload } = await fetchJsonWithTimeout("/api/session/rd/status?poll=1", 5500);
        if (!response.ok || cancelled) {
          return;
        }
        const connected = Boolean(payload?.rdConnected);
        if (connected) {
          setHealth((prev) => ({ ...prev, rdConnected: true }));
          setRdPending(false);
          return;
        }
      } catch {
        // ignore and continue polling during warmup window
      }

      if (Date.now() - startedAt > 12000 && !cancelled) {
        setHealth((prev) => ({ ...prev, rdConnected: false }));
        setRdPending(false);
      }
    };

    pollRd();
    const timer = setInterval(() => {
      if (cancelled || !rdPending) return;
      pollRd();
    }, 2000);
    const hardStop = setTimeout(() => {
      if (!cancelled) {
        setRdPending(false);
      }
    }, 15000);

    return () => {
      cancelled = true;
      clearInterval(timer);
      clearTimeout(hardStop);
    };
  }, [rdPending]);

  useEffect(() => {
    if (!loading && !rdPending) {
      setWarmupSeconds(0);
      return;
    }
    const started = Date.now();
    setWarmupSeconds(0);
    const timer = setInterval(() => {
      setWarmupSeconds(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [loading, rdPending]);

  useEffect(() => {
    let cancelled = false;
    const refreshTransfers = async () => {
      try {
        const response = await fetch("/api/transfers", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || !Array.isArray(payload.transfers) || cancelled) {
          return;
        }
        const map: Record<string, string> = {};
        for (const transfer of payload.transfers as TransferQueueItem[]) {
          const sourceResultId = String(transfer?.sourceResultId || "");
          const status = String(transfer?.status || "");
          if (!sourceResultId || status === "failed") continue;
          map[sourceResultId] = status || "queued";
        }
        setQueuedBySourceId(map);
      } catch {
        // ignore polling failures
      }
    };
    refreshTransfers();
    const timer = setInterval(refreshTransfers, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  async function sendToRd(sourceResultId: string) {
    const existing = queuedBySourceId[sourceResultId];
    if (existing && existing !== "failed") {
      const message = `Already sent to RD (${existing}). Check Transfers.`;
      setNotice(message);
      pushToast("info", message);
      return;
    }
    setSendingId(sourceResultId);
    setError(null);
    setNotice(null);
    setQueuedBySourceId((prev) => ({ ...prev, [sourceResultId]: "queued" }));
    try {
      const response = await fetch("/api/rd", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceResultId })
      });
      const payload = await response.json();
      if (!response.ok) {
        setQueuedBySourceId((prev) => {
          const next = { ...prev };
          delete next[sourceResultId];
          return next;
        });
        throw new Error(payload?.error?.message ?? "Send to RD failed");
      }
      const transferStatus = String(payload?.transfer?.status || "queued");
      setQueuedBySourceId((prev) => ({ ...prev, [sourceResultId]: transferStatus }));
      const message = "Sent to RD. Tracking in Transfers.";
      setNotice(message);
      pushToast("success", message);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Send to RD failed";
      setError(message);
      pushToast("error", message);
    } finally {
      setSendingId(null);
    }
  }

  return (
    <main className="space-y-8">
      <section className="rounded-2xl border border-white/20 bg-white/10 p-6 shadow-[0_12px_40px_rgba(6,11,19,0.45)] backdrop-blur-xl">
        <h1 className="text-2xl font-semibold">Software-first discovery. Torrent-ready workflow.</h1>
        <p className="mt-2 text-sm text-zinc-200">
          Focused ranking for VSTs, Windows installers, and macOS downloads. Movies/TV noise is deprioritized.
        </p>
        <div className="kpi-grid">
          <article className="kpi-card">
            <p className="kpi-label">RD Connected</p>
            <p className="kpi-value">{loading || rdPending ? "..." : String(Boolean(health.rdConnected))}</p>
          </article>
          <article className="kpi-card">
            <p className="kpi-label">Providers Online</p>
            <p className="kpi-value">
              {loading ? "..." : `${String(health.providersOnline ?? 0)}/${String(health.providersTotal ?? 0)}`}
            </p>
          </article>
          <article className="kpi-card">
            <p className="kpi-label">Last Refresh</p>
            <p className="kpi-value text-base">{loading ? "..." : String(health.lastIndexRefreshAt ?? "n/a")}</p>
          </article>
        </div>
        {loading || rdPending ? (
          <div className="mt-4 rounded-lg border border-white/15 bg-black/25 p-3">
            <p className="text-sm text-zinc-200">{loading ? "Preparing home rails..." : "Finalizing Real-Debrid status..."}</p>
            <div className="home-loader-track mt-2">
              <div className="home-loader-sweep" />
            </div>
            <p className="mt-2 text-xs text-zinc-400">
              {loading
                ? `Warming sources and rails... ${warmupSeconds}s elapsed.`
                : `Checking RD session... ${warmupSeconds}s elapsed.`}
            </p>
          </div>
        ) : null}
        {notice ? <p className="mt-3 text-sm text-emerald-300">{notice}</p> : null}
        {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
      </section>
      {rails.map((rail) => (
        <Rail
          key={rail.id}
          title={rail.title}
          items={rail.items || []}
          sendingId={sendingId}
          queuedBySourceId={queuedBySourceId}
          onSendToRd={sendToRd}
        />
      ))}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(360px,92vw)] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-lg border px-3 py-2 text-sm shadow-[0_10px_30px_rgba(6,11,19,0.45)] backdrop-blur-xl ${
              toast.tone === "success"
                ? "border-emerald-300/40 bg-emerald-500/20 text-emerald-100"
                : toast.tone === "error"
                ? "border-red-300/40 bg-red-500/20 text-red-100"
                : "border-sky-300/40 bg-sky-500/20 text-sky-100"
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </main>
  );
}
