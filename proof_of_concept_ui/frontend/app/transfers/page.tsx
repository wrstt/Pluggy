"use client";

import { useEffect, useMemo, useState } from "react";
import { ProviderAwareIcon } from "@/lib/ui/provider-aware-icon";

type Transfer = {
  id: string;
  sourceResultId: string;
  status: string;
  progress: number;
  speed?: string | null;
  error?: string | null;
};

export default function TransfersPage() {
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function loadTransfers() {
    try {
      const response = await fetch("/api/transfers", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Failed to load transfers");
      }
      setTransfers(Array.isArray(payload.transfers) ? payload.transfers : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load transfers");
    }
  }

  useEffect(() => {
    loadTransfers();
    const timer = setInterval(loadTransfers, 3000);
    return () => clearInterval(timer);
  }, []);

  async function runAction(transferId: string, action: "cancel" | "retry" | "pause" | "resume" | "delete") {
    setBusyId(transferId);
    setError(null);
    try {
      const endpoint =
        action === "delete"
          ? `/api/transfers/${encodeURIComponent(transferId)}`
          : `/api/transfers/${encodeURIComponent(transferId)}/${action}`;
      const response = await fetch(endpoint, { method: action === "delete" ? "DELETE" : "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? `Failed to ${action} transfer`);
      }
      await loadTransfers();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to ${action} transfer`);
    } finally {
      setBusyId(null);
    }
  }

  const grouped = useMemo(
    () => ({
      queued: transfers.filter((t) => t.status === "queued" || t.status === "resolving"),
      active: transfers.filter((t) => t.status === "downloading" || t.status === "paused"),
      done: transfers.filter((t) => t.status === "completed"),
      failed: transfers.filter((t) => t.status === "failed")
    }),
    [transfers]
  );

  function renderLane(title: string, items: Transfer[]) {
    return (
      <section className="rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="mb-3 text-lg font-semibold">{title}</h2>
        <div className="space-y-2">
          {items.map((transfer) => (
            <div
              key={transfer.id}
              className="motion-soft flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/10 bg-black/30 p-2 text-sm"
            >
              <div className="flex items-center gap-2">
                <ProviderAwareIcon
                  title={transfer.sourceResultId || transfer.id}
                  protocol={transfer.sourceResultId?.startsWith("src_") ? "torrent" : "http"}
                  size={28}
                />
                <div>
                  <p className="font-medium">{transfer.id}</p>
                  <p className="text-zinc-300">
                    {transfer.status} • {transfer.progress}% {transfer.speed ? `• ${transfer.speed}` : ""}
                  </p>
                  {transfer.error ? <p className="text-red-300">{transfer.error}</p> : null}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {(transfer.status === "downloading" || transfer.status === "resolving") && (
                  <button
                    onClick={() => runAction(transfer.id, "pause")}
                    disabled={busyId === transfer.id}
                    className="btn-secondary"
                  >
                    Pause
                  </button>
                )}
                {transfer.status === "paused" && (
                  <button
                    onClick={() => runAction(transfer.id, "resume")}
                    disabled={busyId === transfer.id}
                    className="btn-secondary"
                  >
                    Resume
                  </button>
                )}
                {(transfer.status === "queued" ||
                  transfer.status === "resolving" ||
                  transfer.status === "downloading" ||
                  transfer.status === "paused") && (
                  <button
                    onClick={() => runAction(transfer.id, "cancel")}
                    disabled={busyId === transfer.id}
                    className="btn-critical"
                  >
                    Cancel
                  </button>
                )}
                {transfer.status === "failed" && (
                  <button
                    onClick={() => runAction(transfer.id, "retry")}
                    disabled={busyId === transfer.id}
                    className="btn-primary"
                  >
                    Retry
                  </button>
                )}
                {(transfer.status === "completed" || transfer.status === "failed") && (
                  <button
                    onClick={() => runAction(transfer.id, "delete")}
                    disabled={busyId === transfer.id}
                    className="btn-secondary"
                  >
                    {busyId === transfer.id ? "Deleting..." : "Delete"}
                  </button>
                )}
              </div>
            </div>
          ))}
          {items.length === 0 ? <p className="text-sm text-zinc-300">No transfers.</p> : null}
        </div>
      </section>
    );
  }

  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">Transfers</h1>
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      {renderLane("Queued", grouped.queued)}
      {renderLane("Active", grouped.active)}
      {renderLane("Completed", grouped.done)}
      {renderLane("Failed", grouped.failed)}
    </main>
  );
}
