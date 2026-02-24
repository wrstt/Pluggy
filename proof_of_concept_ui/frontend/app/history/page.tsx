"use client";

import { useEffect, useState } from "react";

type Transfer = {
  id: string;
  status: string;
  updatedAt: string;
  error?: string | null;
};

export default function HistoryPage() {
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [density, setDensity] = useState<"cozy" | "compact">("cozy");
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  useEffect(() => {
    fetch("/api/transfers", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.error?.message ?? "Failed to load history");
        }
        const all = Array.isArray(payload.transfers) ? payload.transfers : [];
        setTransfers(all.filter((entry: Transfer) => entry.status === "completed" || entry.status === "failed"));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load history"));
  }, []);

  async function deleteTransfer(transferId: string) {
    setDeletingId(transferId);
    setError(null);
    try {
      const response = await fetch(`/api/transfers/${encodeURIComponent(transferId)}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Failed to delete history item");
      }
      setTransfers((prev) => prev.filter((entry) => entry.id !== transferId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete history item");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">History</h1>
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-zinc-300">Density</span>
        <button className={`btn-secondary ${density === "cozy" ? "border-[var(--accent-primary)]" : ""}`} onClick={() => setTableDensity("cozy")}>
          Cozy
        </button>
        <button className={`btn-secondary ${density === "compact" ? "border-[var(--accent-primary)]" : ""}`} onClick={() => setTableDensity("compact")}>
          Compact
        </button>
      </div>
      <div className={`rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-zinc-300 ${density === "compact" ? "density-compact" : "density-cozy"}`}>
        {transfers.length === 0 ? (
          "No completed or failed transfers yet."
        ) : (
          <div className="overflow-x-auto">
            <table className="table-enterprise">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>Error</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {transfers.map((transfer) => (
                  <tr key={transfer.id} className="motion-soft">
                    <td className="font-medium">{transfer.id}</td>
                    <td>{transfer.status}</td>
                    <td>{new Date(transfer.updatedAt).toLocaleString()}</td>
                    <td className={transfer.error ? "text-red-300" : "text-zinc-500"}>{transfer.error || "-"}</td>
                    <td>
                      <button
                        className="btn-secondary"
                        onClick={() => deleteTransfer(transfer.id)}
                        disabled={deletingId === transfer.id}
                      >
                        {deletingId === transfer.id ? "Deleting..." : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
