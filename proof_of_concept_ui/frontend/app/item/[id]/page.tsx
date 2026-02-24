"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ItemHeader } from "@/components/item/ItemHeader";
import { ProviderAwareIcon } from "@/lib/ui/provider-aware-icon";

type ItemPayload = {
  item: { id: string; title: string; aliases: string[] };
  releases: { id: string; provider: string; protocol: string; size: string; seeders: number }[];
};

type TransferQueueItem = {
  sourceResultId: string;
  status: string;
};

function rdButtonLabel(status?: string, isSubmitting?: boolean) {
  if (isSubmitting) return "Sending…";
  if (!status) return "Send to RD";
  if (status === "completed") return "Done";
  if (status === "downloading" || status === "paused") return "In Transfer";
  if (status === "queued" || status === "resolving") return "Queued";
  return "Sent";
}

export default function ItemDetailPage() {
  const params = useParams<{ id: string }>();
  const itemId = params?.id ?? "";
  const [payload, setPayload] = useState<ItemPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [queuedBySourceId, setQueuedBySourceId] = useState<Record<string, string>>({});
  const [density, setDensity] = useState<"cozy" | "compact">("cozy");

  useEffect(() => {
    if (!itemId) {
      return;
    }
    fetch(`/api/item/${encodeURIComponent(itemId)}`, { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) {
          throw new Error(body?.error?.message ?? "Failed to load item");
        }
        setPayload(body as ItemPayload);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load item"));
  }, [itemId]);

  useEffect(() => {
    let cancelled = false;
    const refreshTransfers = async () => {
      try {
        const response = await fetch("/api/transfers", { cache: "no-store" });
        const body = await response.json();
        if (!response.ok || !Array.isArray(body.transfers) || cancelled) return;
        const map: Record<string, string> = {};
        for (const transfer of body.transfers as TransferQueueItem[]) {
          const sourceResultId = String(transfer?.sourceResultId || "");
          const status = String(transfer?.status || "");
          if (!sourceResultId || status === "failed") continue;
          map[sourceResultId] = status || "queued";
        }
        setQueuedBySourceId(map);
      } catch {
        // keep page usable if transfer polling fails
      }
    };
    refreshTransfers();
    const timer = setInterval(refreshTransfers, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("platswap:table-density");
      if (saved === "cozy" || saved === "compact") {
        setDensity(saved);
      }
    } catch {}
  }, []);

  function setTableDensity(next: "cozy" | "compact") {
    setDensity(next);
    try {
      window.localStorage.setItem("platswap:table-density", next);
    } catch {}
  }

  async function sendToRd(sourceResultId: string) {
    const existing = queuedBySourceId[sourceResultId];
    if (existing && existing !== "failed") {
      setNotice(`Already sent to RD (${existing}). Check Transfers.`);
      return;
    }
    setBusyId(sourceResultId);
    setError(null);
    setNotice(null);
    setQueuedBySourceId((prev) => ({ ...prev, [sourceResultId]: "queued" }));
    try {
      const response = await fetch("/api/rd", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceResultId })
      });
      const body = await response.json();
      if (!response.ok) {
        setQueuedBySourceId((prev) => {
          const next = { ...prev };
          delete next[sourceResultId];
          return next;
        });
        throw new Error(body?.error?.message ?? "Failed to queue transfer");
      }
      const transferStatus = String(body?.transfer?.status || "queued");
      setQueuedBySourceId((prev) => ({ ...prev, [sourceResultId]: transferStatus }));
      setNotice("Sent to RD. Tracking in Transfers.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to queue transfer");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="space-y-4">
      {payload ? <ItemHeader title={payload.item.title} aliases={payload.item.aliases} /> : null}
      {notice ? <p className="text-sm text-emerald-300">{notice}</p> : null}
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      {!payload ? (
        <p className="text-sm text-zinc-300">Loading…</p>
      ) : (
        <section className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Releases</h2>
            <div className="flex items-center gap-2 text-xs">
              <button className={`btn-secondary ${density === "cozy" ? "border-[var(--accent-primary)]" : ""}`} onClick={() => setTableDensity("cozy")}>
                Cozy
              </button>
              <button className={`btn-secondary ${density === "compact" ? "border-[var(--accent-primary)]" : ""}`} onClick={() => setTableDensity("compact")}>
                Compact
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className={`table-enterprise ${density === "compact" ? "density-compact" : "density-cozy"}`}>
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Protocol</th>
                  <th>Size</th>
                  <th>Seeders</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {payload.releases.map((release) => (
                  <tr key={release.id}>
                    <td>
                      <div className="flex items-center gap-2">
                        <ProviderAwareIcon
                          title={payload.item.title}
                          provider={release.provider}
                          protocol={release.protocol}
                          size={24}
                        />
                        <span>{release.provider}</span>
                      </div>
                    </td>
                    <td>{release.protocol}</td>
                    <td>{release.size}</td>
                    <td>{release.seeders}</td>
                    <td>
                      <button
                        onClick={() => sendToRd(release.id)}
                        disabled={busyId === release.id || Boolean(queuedBySourceId[release.id])}
                        className={queuedBySourceId[release.id] ? "btn-secondary" : "btn-primary"}
                      >
                        {rdButtonLabel(queuedBySourceId[release.id], busyId === release.id)}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
